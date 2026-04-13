"""Parse a C++ translation unit into an IRModule.

This is a pure extraction pass — no filtering is applied here.
Filtering happens in filters.py after the full IR is built.
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

from clang import cindex

from tsujikiri.clang_base_enumerations import AccessSpecifier, CursorKind
from tsujikiri.configurations import SourceConfig
from tsujikiri.ir import (
    IRBase,
    IRClass,
    IRConstructor,
    IREnum,
    IREnumValue,
    IRField,
    IRFunction,
    IRMethod,
    IRModule,
    IRParameter,
)


def _to_camel_case(string: str) -> str:
    parts = string.split("_")
    return parts[0] + "".join(f"{x[0].title()}{x[1:]}" for x in parts[1:] if x)


def _source_file(cursor) -> Optional[str]:
    if cursor.location and cursor.location.file:
        return cursor.location.file.name
    return None


def _get_default_value(cursor) -> Optional[str]:
    """Return the raw C++ default expression for a parameter cursor, or None.

    libclang does not expose a dedicated default-value API, so we scan the
    parameter cursor's token stream for a ``=`` token and collect everything
    that follows it within the cursor's extent.
    """
    tokens = list(cursor.get_tokens())
    for i, tok in enumerate(tokens):
        if tok.spelling == "=":
            rest = [t.spelling for t in tokens[i + 1:]]
            return " ".join(rest).strip() if rest else None
    return None


def _type_from_tokens(cursor) -> str:
    """Extract parameter type spelling from source tokens.

    Works around a libclang bug where some parameter types in constructors
    with initializer lists using std::move are reported with the wrong type
    (e.g. 'int' instead of 'std::string'). Source tokens are always correct.
    """
    name = cursor.spelling
    tokens = list(cursor.get_tokens())
    if not name or not tokens:
        return cursor.type.spelling
    for i, tok in enumerate(tokens):
        if tok.spelling == name:
            if i == 0:
                return cursor.type.spelling
            raw = " ".join(t.spelling for t in tokens[:i])
            return re.sub(r"\s*::\s*", "::", raw).strip() or cursor.type.spelling
    return cursor.type.spelling


def _parse_parameters(cursor) -> List[IRParameter]:
    # Use PARM_DECL children and token-based type extraction to avoid a
    # libclang bug where constructors with initializer lists using std::move
    # cause parameter types to be reported incorrectly via cursor.type.spelling.
    return [
        IRParameter(
            name=arg.spelling,
            type_spelling=_type_from_tokens(arg),
            default_value=_get_default_value(arg),
        )
        for arg in cursor.get_children()
        if arg.kind == CursorKind.PARM_DECL
    ]


# ---------------------------------------------------------------------------
# Attribute extraction — source-text scanning
# ---------------------------------------------------------------------------

# Matches [[content]] where content has no unbalanced brackets.
_ATTR_BLOCK_RE = re.compile(r"\[\[([^\[\]]+?)\]\]")

# Per-parse file cache to avoid re-reading the same file for each cursor.
_SOURCE_CACHE: Dict[str, List[str]] = {}


def _read_source_lines(file_path: str) -> List[str]:
    """Return cached source lines for *file_path*."""
    if file_path not in _SOURCE_CACHE:
        try:
            with open(file_path, encoding="utf-8", errors="replace") as f:
                _SOURCE_CACHE[file_path] = f.readlines()
        except OSError:
            _SOURCE_CACHE[file_path] = []
    return _SOURCE_CACHE[file_path]


def _collect_attr_blocks(text: str) -> List[str]:
    """Return attribute name strings found in ``[[...]]`` blocks in *text*.

    A single block ``[[a, b]]`` yields two entries.  The text is assumed to
    not start inside a line comment; callers are responsible for that check.
    """
    result = []
    for m in _ATTR_BLOCK_RE.finditer(text):
        for part in m.group(1).split(","):
            part = part.strip()
            if part:
                result.append(part)
    return result


def _get_attributes(cursor) -> List[str]:
    """Extract C++ ``[[...]]`` attribute contents by scanning source text.

    Covers the three practical placements:

    * Leading on the same line: ``[[attr]] void method()``
    * Trailing on the same line: ``void method() [[attr]]``
    * Leading on its own previous line::

        [[attr]]
        void method();

    libclang does not expose custom namespace attributes as child cursors, so we parse the source text directly.
    """
    if cursor.location.file is None:
        return []

    lines = _read_source_lines(cursor.location.file.name)
    if not lines:
        return []

    start_line = cursor.extent.start.line   # 1-indexed
    end_line = cursor.extent.end.line       # 1-indexed
    start_col = cursor.extent.start.column  # 1-indexed
    end_col = cursor.extent.end.column      # 1-indexed

    attrs: List[str] = []

    # Text before the cursor start on the same line (leading attr, same line)
    before = lines[start_line - 1][:start_col - 1]
    attrs.extend(_collect_attr_blocks(before))

    # Text after the cursor end on the same line (trailing attr)
    after = lines[end_line - 1][end_col - 1:]
    attrs.extend(_collect_attr_blocks(after))

    # Previous line — only scan if it contains [[ and no statement terminators
    # (;, {, }) so we don't accidentally pick up attributes from sibling decls.
    if start_line > 1:
        prev = lines[start_line - 2]
        has_bracket = "[[" in prev
        has_terminator = any(c in prev for c in (";", "{", "}"))
        # Skip if [[ is inside a line comment
        bracket_pos = prev.find("[[")
        comment_pos = prev.find("//")
        inside_comment = has_bracket and comment_pos != -1 and comment_pos < bracket_pos
        if has_bracket and not has_terminator and not inside_comment:
            attrs.extend(_collect_attr_blocks(prev))

    return attrs


def _is_noexcept(cursor) -> bool:
    kind = cursor.exception_specification_kind
    return kind in (
        cindex.ExceptionSpecificationKind.BASIC_NOEXCEPT,
        cindex.ExceptionSpecificationKind.COMPUTED_NOEXCEPT,
    )


def _is_explicit(cursor) -> bool:
    """Return True if the cursor has the explicit specifier (checked via tokens)."""
    return any(tok.spelling == "explicit" for tok in cursor.get_tokens())


def _canonicalize_operator(spelling: str, num_params: int) -> str:
    """Return a canonical operator type string, disambiguating unary/binary cases."""
    if spelling in ("operator-", "operator+") and num_params == 0:
        return f"{spelling}unary"
    if spelling == "operator++" and num_params == 0:
        return "operator++prefix"
    if spelling == "operator++" and num_params == 1:
        return "operator++postfix"
    if spelling == "operator--" and num_params == 0:
        return "operator--prefix"
    if spelling == "operator--" and num_params == 1:
        return "operator--postfix"
    return spelling


def _access_str(access_specifier) -> str:
    if access_specifier == AccessSpecifier.PUBLIC:
        return "public"
    if access_specifier == AccessSpecifier.PROTECTED:
        return "protected"
    return "private"


def _parse_enum(cursor, namespace: str) -> IREnum:
    qualified = f"{namespace}::{cursor.spelling}" if namespace else cursor.spelling
    values = []
    for child in cursor.get_children():
        if child.kind == CursorKind.ENUM_CONSTANT_DECL:
            values.append(IREnumValue(
                name=child.spelling,
                value=child.enum_value,
                attributes=_get_attributes(child),
            ))
    return IREnum(
        name=cursor.spelling,
        qualified_name=qualified,
        values=values,
        attributes=_get_attributes(cursor),
    )


def _parse_class(cursor, namespace: str, parent_name: Optional[str] = None) -> IRClass:
    class_name = cursor.spelling
    if parent_name:
        qualified = f"{parent_name}::{class_name}"
        var_name = _to_camel_case(f"class_{parent_name}_{class_name}")
    else:
        qualified = f"{namespace}::{class_name}" if namespace else class_name
        var_name = _to_camel_case(f"class_{class_name}")

    ir_class = IRClass(
        name=class_name,
        qualified_name=qualified,
        namespace=namespace,
        variable_name=var_name,
        parent_class=parent_name,
        source_file=_source_file(cursor),
        attributes=_get_attributes(cursor),
    )

    # --- Bases ---
    for child in cursor.get_children():
        if child.kind == CursorKind.CXX_BASE_SPECIFIER:
            ir_class.bases.append(IRBase(
                qualified_name=child.type.get_canonical().spelling,
                access=_access_str(child.access_specifier),
            ))

    # --- Methods ---
    methods_by_name: Dict[str, list] = defaultdict(list)
    for child in cursor.get_children():
        if child.kind == CursorKind.CXX_METHOD:
            methods_by_name[child.spelling].append(child)

    for spell, cursors in methods_by_name.items():
        is_overload = len(cursors) > 1
        for m in cursors:
            params = _parse_parameters(m)
            is_op = m.spelling.startswith("operator") and not m.spelling[len("operator"):].isalpha()
            op_type = _canonicalize_operator(m.spelling, len(params)) if is_op else None
            method = IRMethod(
                name=m.spelling,
                spelling=m.spelling,
                qualified_name=f"{qualified}::{m.spelling}",
                return_type=m.result_type.spelling,
                parameters=params,
                is_static=m.is_static_method(),
                is_const=m.is_const_method(),
                is_virtual=m.is_virtual_method(),
                is_pure_virtual=m.is_pure_virtual_method(),
                is_noexcept=_is_noexcept(m),
                is_overload=is_overload,
                is_operator=is_op,
                operator_type=op_type,
                source_file=_source_file(m),
                attributes=_get_attributes(m),
            )
            # access filter: only public
            if m.access_specifier == AccessSpecifier.PUBLIC:
                ir_class.methods.append(method)

    # --- Constructors ---
    ctors = [
        c for c in cursor.get_children()
        if c.kind == CursorKind.CONSTRUCTOR
        and c.access_specifier == AccessSpecifier.PUBLIC
    ]
    is_ctor_overload = len(ctors) > 1
    for ctor in ctors:
        ir_class.constructors.append(IRConstructor(
            parameters=_parse_parameters(ctor),
            is_overload=is_ctor_overload,
            is_noexcept=_is_noexcept(ctor),
            is_explicit=_is_explicit(ctor),
            attributes=_get_attributes(ctor),
        ))

    # --- Virtual / abstract class flags ---
    ir_class.has_virtual_methods = any(m.is_virtual for m in ir_class.methods)
    ir_class.is_abstract = any(m.is_pure_virtual for m in ir_class.methods)

    # --- Fields ---
    # Derive access from CXX_ACCESS_SPEC_DECL nodes rather than trusting
    # FIELD_DECL.access_specifier directly.  libclang 16 on Linux misreports
    # the access specifier of private fields that have in-class default member
    # initialisers (e.g. `std::string name_ = "entity";`), causing them to
    # appear as PUBLIC.  CXX_ACCESS_SPEC_DECL cursors always carry the correct
    # access level because they are derived straight from the `public:` /
    # `private:` / `protected:` keyword tokens.
    _default_access: object = (
        AccessSpecifier.PRIVATE
        if cursor.kind == CursorKind.CLASS_DECL
        else AccessSpecifier.PUBLIC
    )
    _tracked_access: object = _default_access
    for child in cursor.get_children():
        if child.kind == CursorKind.CXX_ACCESS_SPEC_DECL:
            _tracked_access = child.access_specifier
        elif child.kind == CursorKind.FIELD_DECL and _tracked_access == AccessSpecifier.PUBLIC:
            ir_class.fields.append(IRField(
                name=child.spelling,
                type_spelling=child.type.spelling,
                is_const="const" in child.type.spelling,
                is_static=False,
                attributes=_get_attributes(child),
            ))

    # --- Nested enums ---
    for child in cursor.get_children():
        if child.kind == CursorKind.ENUM_DECL and child.access_specifier == AccessSpecifier.PUBLIC:
            ir_class.enums.append(_parse_enum(child, qualified))

    # --- Inner classes ---
    for child in cursor.get_children():
        if (child.kind in (CursorKind.CLASS_DECL, CursorKind.STRUCT_DECL)
                and child.access_specifier == AccessSpecifier.PUBLIC):
            ir_class.inner_classes.append(_parse_class(child, namespace, parent_name=qualified))

    return ir_class


def _collect_namespace_cursors(top_level, namespaces: List[str]):
    """Yield namespace cursors matching the filter (or all if namespaces is empty)."""
    for entry in top_level:
        if entry.kind != CursorKind.NAMESPACE:
            continue
        if not namespaces or entry.spelling in namespaces:
            yield entry


def parse_translation_unit(source: SourceConfig, namespaces: List[str], module_name: str) -> IRModule:
    """Parse a C++ translation unit and return a fully populated IRModule.

    No filtering is applied — all discovered entities are added with emit=True.
    """
    source_path = Path(source.path)
    if not source_path.exists():
        raise FileNotFoundError(f"Source file not found: {source_path.resolve()}")

    args = list(source.parse_args)
    args += [f"-I{p}" for p in source.include_paths]
    args += [f"-D{d}" for d in source.defines]
    # Ensure we parse as C++ by default if not already specified
    if "-x" not in args:
        args = ["-x", "c++"] + args
    # Ensure sysroot on darwin
    if sys.platform == "darwin" and "-isysroot" not in args:
        args += ["-isysroot", "/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk"]

    index = cindex.Index.create()
    tu = index.parse(str(source_path.absolute()), args=args)

    module = IRModule(name=module_name, namespaces=list(namespaces))

    namespace_cursors = list(_collect_namespace_cursors(
        tu.cursor.get_children(),
        namespaces,
    ))

    # --- Free functions ---
    fn_names: Dict[str, list] = defaultdict(list)
    for ns in namespace_cursors:
        for child in ns.get_children():
            if child.kind == CursorKind.FUNCTION_DECL:
                fn_names[child.spelling].append((child, ns.spelling))

    for entries in fn_names.values():
        is_overload = len(entries) > 1
        for fn_cursor, ns_name in entries:
            qualified = f"{ns_name}::{fn_cursor.spelling}" if ns_name else fn_cursor.spelling
            fn_params = _parse_parameters(fn_cursor)
            fn_is_op = (fn_cursor.spelling.startswith("operator")
                        and not fn_cursor.spelling[len("operator"):].isalpha())
            fn_op_type = _canonicalize_operator(fn_cursor.spelling, len(fn_params)) if fn_is_op else None
            module.functions.append(IRFunction(
                name=fn_cursor.spelling,
                qualified_name=qualified,
                namespace=ns_name,
                return_type=fn_cursor.result_type.spelling,
                parameters=fn_params,
                is_overload=is_overload,
                is_noexcept=_is_noexcept(fn_cursor),
                is_operator=fn_is_op,
                operator_type=fn_op_type,
                attributes=_get_attributes(fn_cursor),
            ))

    # --- Top-level enums ---
    for ns in namespace_cursors:
        for child in ns.get_children():
            if child.kind == CursorKind.ENUM_DECL:
                module.enums.append(_parse_enum(child, ns.spelling))

    # --- Classes ---
    all_class_cursors = []
    for ns in namespace_cursors:
        for child in ns.get_children():
            if child.kind in (CursorKind.CLASS_DECL, CursorKind.STRUCT_DECL):
                all_class_cursors.append((child, ns.spelling))

    for cls_cursor, ns_name in all_class_cursors:
        ir_class = _parse_class(cls_cursor, namespace=ns_name)
        module.classes.append(ir_class)
        module.class_by_name[ir_class.name] = ir_class

    return module
