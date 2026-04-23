"""Parse a C++ translation unit into an IRModule.

This is a pure extraction pass — no filtering is applied here.
Filtering happens in filters.py after the full IR is built.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

from clang import cindex
from clang.cindex import AccessSpecifier, AvailabilityKind, CursorKind

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
    IRUsingDeclaration,
)
from tsujikiri.tir import TIRModule, upgrade_module


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


def _is_deleted(cursor) -> bool:
    """Return True if the cursor's declaration has '= delete'."""
    tokens = list(cursor.get_tokens())
    for i, tok in enumerate(tokens):
        if tok.spelling == "=" and i + 1 < len(tokens) and tokens[i + 1].spelling == "delete":
            return True
    return False


def _is_deprecated(cursor) -> bool:
    """Return True if the cursor is marked as deprecated."""
    return cursor.availability == AvailabilityKind.DEPRECATED


def _get_deprecation_message(cursor) -> Optional[str]:
    """Return the deprecation message if present, or None.

    Scans tokens for [[deprecated("msg")]] or __attribute__((deprecated("msg"))) patterns.
    """
    for tok in cursor.get_tokens():
        if tok.spelling == "deprecated":
            pass  # found the keyword; scan surrounding tokens
    # Scan source text for deprecated("msg") pattern
    if cursor.location.file is None:
        return None
    lines = _read_source_lines(cursor.location.file.name)
    if not lines:
        return None
    start_line = cursor.extent.start.line
    # Check current and previous lines for deprecated message
    check_range = range(max(0, start_line - 3), min(len(lines), start_line + 1))
    for idx in check_range:
        line = lines[idx]
        m = re.search(r'deprecated\s*\(\s*"([^"]*)"\s*\)', line)
        if m:
            return m.group(1)
    return None


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


def _is_scoped_enum(cursor) -> bool:
    """Return True if the enum is declared as 'enum class' or 'enum struct'."""
    tokens = list(cursor.get_tokens())
    for i, tok in enumerate(tokens):
        if tok.spelling == "enum":
            if i + 1 < len(tokens) and tokens[i + 1].spelling in ("class", "struct"):
                return True
            break
    return False


def _is_anonymous_enum(cursor) -> bool:
    """Return True if the enum is anonymous (has no user-defined name)."""
    # libclang Python reports anonymous types with spellings like
    # "(unnamed enum at /path/file.hpp:17:1)" rather than empty string.
    s = cursor.spelling
    return not s or s.startswith("(") or "unnamed" in s


def _parse_enum(cursor, namespace: str) -> IREnum:
    is_anonymous = _is_anonymous_enum(cursor)
    name = cursor.spelling if not is_anonymous else f"__anon_enum_{cursor.location.line}"
    qualified = f"{namespace}::{name}" if namespace else name
    values = []
    for child in cursor.get_children():
        if child.kind == CursorKind.ENUM_CONSTANT_DECL:
            values.append(IREnumValue(
                name=child.spelling,
                value=child.enum_value,
                attributes=_get_attributes(child),
            ))
    return IREnum(
        name=name,
        qualified_name=qualified,
        values=values,
        is_scoped=_is_scoped_enum(cursor),
        is_anonymous=is_anonymous,
        is_deprecated=_is_deprecated(cursor),
        deprecation_message=_get_deprecation_message(cursor) if _is_deprecated(cursor) else None,
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
            deprecated = _is_deprecated(m)
            is_varargs = m.type.is_function_variadic()
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
                is_varargs=is_varargs,
                is_overload=is_overload,
                is_operator=is_op,
                operator_type=op_type,
                source_file=_source_file(m),
                is_deprecated=deprecated,
                deprecation_message=_get_deprecation_message(m) if deprecated else None,
                attributes=_get_attributes(m),
            )
            # Collect public and protected methods; protected methods are suppressed by default
            if m.access_specifier == AccessSpecifier.PUBLIC:
                ir_class.methods.append(method)
            elif m.access_specifier == AccessSpecifier.PROTECTED:
                method.access = "protected"
                ir_class.methods.append(method)

    # --- Conversion operators ---
    for child in cursor.get_children():
        if child.kind == CursorKind.CONVERSION_FUNCTION and child.access_specifier == AccessSpecifier.PUBLIC:
            deprecated = _is_deprecated(child)
            method = IRMethod(
                name=child.spelling,
                spelling=child.spelling,
                qualified_name=f"{qualified}::{child.spelling}",
                return_type=child.result_type.spelling,
                parameters=[],
                is_static=False,
                is_const=child.is_const_method(),
                is_virtual=child.is_virtual_method(),
                is_pure_virtual=child.is_pure_virtual_method(),
                is_noexcept=_is_noexcept(child),
                is_overload=False,
                is_operator=True,
                operator_type=child.spelling,  # e.g. "operator bool"
                is_conversion_operator=True,
                conversion_target_type=child.result_type.spelling,
                source_file=_source_file(child),
                is_deprecated=deprecated,
                deprecation_message=_get_deprecation_message(child) if deprecated else None,
                attributes=_get_attributes(child),
            )
            ir_class.methods.append(method)

    # --- Constructors ---
    all_ctors = [
        c for c in cursor.get_children()
        if c.kind == CursorKind.CONSTRUCTOR
    ]
    # Detect deleted copy/move constructors for move-only type inference
    class_name_for_ctor = class_name
    for ctor in all_ctors:
        params = _parse_parameters(ctor)
        if len(params) == 1:
            t = params[0].type_spelling
            # Copy constructor: takes const ClassName& or ClassName const&
            if (f"const {class_name_for_ctor} &" in t or f"{class_name_for_ctor} const &" in t
                    or t.strip() == f"const {class_name_for_ctor} &"):
                if _is_deleted(ctor) or ctor.access_specifier != AccessSpecifier.PUBLIC:
                    ir_class.has_deleted_copy_constructor = True
            # Move constructor: takes ClassName&&
            elif f"{class_name_for_ctor} &&" in t or f"{class_name_for_ctor}&&" in t:
                if _is_deleted(ctor) or ctor.access_specifier != AccessSpecifier.PUBLIC:
                    ir_class.has_deleted_move_constructor = True

    public_ctors = [c for c in all_ctors if c.access_specifier == AccessSpecifier.PUBLIC and not _is_deleted(c)]
    is_ctor_overload = len(public_ctors) > 1
    for ctor in public_ctors:
        deprecated = _is_deprecated(ctor)
        ir_class.constructors.append(IRConstructor(
            parameters=_parse_parameters(ctor),
            is_overload=is_ctor_overload,
            is_noexcept=_is_noexcept(ctor),
            is_explicit=_is_explicit(ctor),
            is_varargs=ctor.type.is_function_variadic(),
            is_deprecated=deprecated,
            deprecation_message=_get_deprecation_message(ctor) if deprecated else None,
            attributes=_get_attributes(ctor),
        ))

    # --- Virtual / abstract class flags ---
    ir_class.has_virtual_methods = any(m.is_virtual for m in ir_class.methods)
    ir_class.is_abstract = any(m.is_pure_virtual for m in ir_class.methods)

    # --- Class-level deprecation ---
    ir_class.is_deprecated = _is_deprecated(cursor)
    if ir_class.is_deprecated:
        ir_class.deprecation_message = _get_deprecation_message(cursor)

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
        elif child.kind == CursorKind.VAR_DECL and _tracked_access == AccessSpecifier.PUBLIC:
            # Static member variables (class-level, not instance fields)
            ir_class.fields.append(IRField(
                name=child.spelling,
                type_spelling=child.type.spelling,
                is_const="const" in child.type.spelling,
                is_static=True,
                attributes=_get_attributes(child),
            ))

    # --- Using declarations ---
    for child in cursor.get_children():
        if child.kind == CursorKind.USING_DECLARATION:
            access = _access_str(child.access_specifier)
            member_name = child.spelling
            # Extract base class qualified name from child TYPE_REF cursor
            base_qname = ""
            for ch in child.get_children():
                if ch.kind == CursorKind.TYPE_REF:
                    base_qname = ch.type.get_canonical().spelling
                    break
            ir_class.using_declarations.append(IRUsingDeclaration(
                member_name=member_name,
                base_qualified_name=base_qname,
                access=access,
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


_CLANG_SEVERITY: dict[int, str] = {
    0: "ignored",
    1: "note",
    2: "warning",
    3: "error",
    4: "fatal",
}


def _is_inline_namespace(cursor: "cindex.Cursor") -> bool:
    """Return True if this NAMESPACE cursor is declared as 'inline namespace ...'."""
    tokens = list(cursor.get_tokens())
    return bool(tokens) and tokens[0].spelling == "inline"


def _namespace_in_filter(path: str, filters: List[str]) -> bool:
    """True if path exactly matches any filter entry."""
    return path in filters


def _namespace_should_recurse(path: str, filters: List[str]) -> bool:
    """True if we should enter a namespace at this path.

    We recurse if:
    - path equals a filter entry (already matched, collect its descendants)
    - path is a strict ancestor of a filter ("outer" when filter is "outer::inner")
    - path is a strict descendant of a filter ("outer::inner::detail" when filter is "outer::inner")
    """
    if not filters:
        return True
    for f in filters:
        if path == f:
            return True
        if f.startswith(path + "::"):
            return True
        if path.startswith(f + "::"):
            return True
    return False


def _iter_scope_decls(cursors, filter_prefixes: List[str], current_path: str = ""):
    """Recursively yield (decl_cursor, scope_path) for CLASS_DECL, STRUCT_DECL,
    FUNCTION_DECL, and ENUM_DECL reachable under namespaces matching filter_prefixes,
    or at global scope when filter_prefixes is empty.

    Inline namespaces are transparent: a declaration inside 'inline namespace v2'
    nested under 'outer' is treated as being in 'outer'.
    """
    for cursor in cursors:
        if cursor.kind == CursorKind.NAMESPACE:
            if _is_inline_namespace(cursor):
                # Transparent: keep parent path for both matching and storage
                child_path = current_path
            else:
                child_path = f"{current_path}::{cursor.spelling}" if current_path else cursor.spelling

            if _namespace_should_recurse(child_path, filter_prefixes):
                yield from _iter_scope_decls(cursor.get_children(), filter_prefixes, child_path)

        elif cursor.kind in (
            CursorKind.CLASS_DECL,
            CursorKind.STRUCT_DECL,
            CursorKind.FUNCTION_DECL,
            CursorKind.ENUM_DECL,
        ):
            if not filter_prefixes or _namespace_in_filter(current_path, filter_prefixes):
                yield (cursor, current_path)


def parse_translation_unit(
    source: SourceConfig,
    namespaces: List[str],
    module_name: str,
    *,
    verbose: bool = False,
) -> TIRModule:
    """Parse a C++ translation unit and return a fully populated IRModule.

    No filtering is applied — all discovered entities are added with emit=True.
    When *verbose* is True, all clang diagnostics are printed to stderr; errors
    and fatals are always printed regardless of *verbose*.
    """
    source_path = Path(source.path)
    if not source_path.exists():
        raise FileNotFoundError(f"Source file not found: {source_path.resolve()}")

    args = list(source.parse_args)
    args += [f"-I{p}" for p in source.include_paths]
    args += [f"-isystem{p}" for p in source.system_include_paths]
    args += [f"-D{d}" for d in source.defines]
    # Ensure we parse as C++ by default if not already specified
    if "-x" not in args:
        args = ["-x", "c++"] + args
    # Ensure sysroot and C++ stdlib headers on darwin.
    if sys.platform == "darwin":
        if "-isysroot" not in args:
            try:
                sysroot = subprocess.check_output(
                    ["xcrun", "--show-sdk-path"], text=True, stderr=subprocess.DEVNULL
                ).strip()
            except (subprocess.CalledProcessError, FileNotFoundError):
                sysroot = "/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk"
            args += ["-isysroot", sysroot]

        # Point libclang at Xcode's clang resource directory so it uses the correct built-in headers (stdarg.h, stddef.h, …).
        if "-resource-dir" not in args:
            try:
                resource_dir = subprocess.check_output(
                    ["xcrun", "clang", "-print-resource-dir"], text=True, stderr=subprocess.DEVNULL
                ).strip()
            except (subprocess.CalledProcessError, FileNotFoundError):
                resource_dir = ""
            if resource_dir and Path(resource_dir).is_dir():
                args += ["-resource-dir", resource_dir]

    elif sys.platform.startswith("linux"):
        # On Linux, libclang pip package ships without builtin headers; point it at the
        # system clang resource dir so stddef.h/stdarg.h etc. are found.
        if "-resource-dir" not in args:
            resource_dir = ""
            for clang_bin in ["clang-18", "clang-17", "clang-16", "clang"]:
                try:
                    candidate = subprocess.check_output(
                        [clang_bin, "-print-resource-dir"], text=True, stderr=subprocess.DEVNULL
                    ).strip()
                    if candidate and Path(candidate).is_dir():
                        resource_dir = candidate
                        break
                except (subprocess.CalledProcessError, FileNotFoundError):
                    continue
            if resource_dir:
                args += ["-resource-dir", resource_dir]

    if verbose:
        print(f"[parse] {source_path}: args={args}", file=sys.stderr)

    index = cindex.Index.create()
    # CXTranslationUnit_KeepGoing (0x200): continue past fatal "too many errors" stops.
    # libclang 18 hits the error limit from cascading stdlib header failures and aborts
    # before processing all namespaces in the translation unit.
    tu = index.parse(str(source_path.absolute()), args=args, options=0x200)

    # Print diagnostics: errors/fatals always, all diags when verbose.
    for diag in tu.diagnostics:
        if diag.severity >= 3 or verbose:
            loc = diag.location
            loc_str = f"{loc.file.name}:{loc.line}:{loc.column}" if loc.file else "<unknown>"
            sev = _CLANG_SEVERITY.get(diag.severity, str(diag.severity))
            print(f"[clang:{sev}] {loc_str}: {diag.spelling}", file=sys.stderr)

    module = IRModule(name=module_name, namespaces=list(namespaces))

    # Gather all declarations under matching scopes (includes global scope when namespaces=[])
    all_decls = list(_iter_scope_decls(tu.cursor.get_children(), namespaces, current_path=""))

    # --- Free functions ---
    fn_groups: Dict[str, list] = defaultdict(list)
    for cursor, scope_path in all_decls:
        if cursor.kind == CursorKind.FUNCTION_DECL:
            fn_groups[cursor.spelling].append((cursor, scope_path))

    for entries in fn_groups.values():
        is_overload = len(entries) > 1
        for fn_cursor, scope_path in entries:
            qualified = f"{scope_path}::{fn_cursor.spelling}" if scope_path else fn_cursor.spelling
            fn_params = _parse_parameters(fn_cursor)
            fn_is_op = (fn_cursor.spelling.startswith("operator")
                        and not fn_cursor.spelling[len("operator"):].isalpha())
            fn_op_type = _canonicalize_operator(fn_cursor.spelling, len(fn_params)) if fn_is_op else None
            fn_deprecated = _is_deprecated(fn_cursor)
            module.functions.append(IRFunction(
                name=fn_cursor.spelling,
                qualified_name=qualified,
                namespace=scope_path,
                return_type=fn_cursor.result_type.spelling,
                parameters=fn_params,
                is_overload=is_overload,
                is_noexcept=_is_noexcept(fn_cursor),
                is_varargs=fn_cursor.type.is_function_variadic(),
                is_operator=fn_is_op,
                operator_type=fn_op_type,
                is_deprecated=fn_deprecated,
                deprecation_message=_get_deprecation_message(fn_cursor) if fn_deprecated else None,
                attributes=_get_attributes(fn_cursor),
            ))
            if scope_path and scope_path not in module.namespaces:
                module.namespaces.append(scope_path)

    # --- Top-level enums ---
    for cursor, scope_path in all_decls:
        if cursor.kind == CursorKind.ENUM_DECL:
            module.enums.append(_parse_enum(cursor, scope_path))
            if scope_path and scope_path not in module.namespaces:
                module.namespaces.append(scope_path)

    # --- Classes ---
    for cursor, scope_path in all_decls:
        if cursor.kind not in (CursorKind.CLASS_DECL, CursorKind.STRUCT_DECL):
            continue
        if not cursor.is_definition():
            continue
        ir_class = _parse_class(cursor, namespace=scope_path)
        module.classes.append(ir_class)
        module.class_by_name[ir_class.name] = ir_class
        if scope_path and scope_path not in module.namespaces:
            module.namespaces.append(scope_path)

    if verbose:
        ns_summary = ", ".join(module.namespaces) or "(global)"
        print(
            f"[parse] {source_path}: IR built — "
            f"{len(module.classes)} class(es), "
            f"{len(module.functions)} function(s), "
            f"{len(module.enums)} enum(s) "
            f"in namespaces [{ns_summary}]",
            file=sys.stderr,
        )

    return upgrade_module(module)
