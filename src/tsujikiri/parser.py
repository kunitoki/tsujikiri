"""Parse a C++ translation unit into an IRModule.

This is a pure extraction pass — no filtering is applied here.
Filtering happens in filters.py after the full IR is built.
"""

from __future__ import annotations

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


def _parse_parameters(cursor) -> List[IRParameter]:
    return [
        IRParameter(name=arg.spelling, type_spelling=arg.type.spelling)
        for arg in cursor.get_arguments()
    ]


def _is_noexcept(cursor) -> bool:
    kind = cursor.exception_specification_kind
    return kind in (
        cindex.ExceptionSpecificationKind.BASIC_NOEXCEPT,
        cindex.ExceptionSpecificationKind.COMPUTED_NOEXCEPT,
    )


def _is_explicit(cursor) -> bool:
    """Return True if the cursor has the explicit specifier (checked via tokens)."""
    return any(tok.spelling == "explicit" for tok in cursor.get_tokens())


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
            values.append(IREnumValue(name=child.spelling, value=child.enum_value))
    return IREnum(name=cursor.spelling, qualified_name=qualified, values=values)


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
            method = IRMethod(
                name=m.spelling,
                spelling=m.spelling,
                qualified_name=f"{qualified}::{m.spelling}",
                return_type=m.result_type.spelling,
                parameters=_parse_parameters(m),
                is_static=m.is_static_method(),
                is_const=m.is_const_method(),
                is_virtual=m.is_virtual_method(),
                is_pure_virtual=m.is_pure_virtual_method(),
                is_noexcept=_is_noexcept(m),
                is_overload=is_overload,
                source_file=_source_file(m),
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
        ))

    # --- Virtual / abstract class flags ---
    ir_class.has_virtual_methods = any(m.is_virtual for m in ir_class.methods)
    ir_class.is_abstract = any(m.is_pure_virtual for m in ir_class.methods)

    # --- Fields ---
    for child in cursor.get_children():
        if child.kind == CursorKind.FIELD_DECL and child.access_specifier == AccessSpecifier.PUBLIC:
            ir_class.fields.append(IRField(
                name=child.spelling,
                type_spelling=child.type.spelling,
                is_const="const" in child.type.spelling,
                is_static=False,
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
    # Ensure we parse as C++ by default if not already specified
    if "-x" not in args:
        args = ["-x", "c++"] + args

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
            module.functions.append(IRFunction(
                name=fn_cursor.spelling,
                qualified_name=qualified,
                namespace=ns_name,
                return_type=fn_cursor.result_type.spelling,
                parameters=_parse_parameters(fn_cursor),
                is_overload=is_overload,
                is_noexcept=_is_noexcept(fn_cursor),
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
