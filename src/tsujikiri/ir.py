"""Intermediate Representation (IR) for the C++ binding generator.

All IR nodes are pure dataclasses containing only what libclang provides.
No filtering, transformation, or augmentation data is stored here — that lives
in the TIR* (Transformed IR) layer defined in tir.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class IRCodeInjection:
    """A snippet of code to be injected at a specific position in the output."""
    position: str   # "beginning", "end", or "declaration" (inside class/trampoline body)
    code: str


@dataclass
class IRParameter:
    name: str
    type_spelling: str
    default_value: Optional[str] = None      # raw C++ default extracted by parser
    attributes: List[str] = field(default_factory=list)  # raw [[...]] attribute contents


@dataclass
class IRBase:
    qualified_name: str
    access: str = "public"   # "public", "protected", or "private"


@dataclass
class IRMethod:
    name: str
    spelling: str           # original C++ name (for &ClassName::spelling)
    qualified_name: str     # ClassName::spelling
    return_type: str
    parameters: List[IRParameter] = field(default_factory=list)
    is_static: bool = False
    is_const: bool = False
    is_virtual: bool = False
    is_pure_virtual: bool = False
    is_noexcept: bool = False
    is_varargs: bool = False
    is_overload: bool = False
    is_operator: bool = False
    operator_type: Optional[str] = None
    is_conversion_operator: bool = False
    conversion_target_type: Optional[str] = None
    access: str = "public"    # "public", "protected", or "public_via_trampoline"
    source_file: Optional[str] = None
    is_deprecated: bool = False
    deprecation_message: Optional[str] = None
    attributes: List[str] = field(default_factory=list)


@dataclass
class IRConstructor:
    parameters: List[IRParameter] = field(default_factory=list)
    is_overload: bool = False
    is_noexcept: bool = False
    is_explicit: bool = False
    is_deleted: bool = False
    is_varargs: bool = False
    is_deprecated: bool = False
    deprecation_message: Optional[str] = None
    attributes: List[str] = field(default_factory=list)


@dataclass
class IRField:
    name: str
    type_spelling: str
    is_const: bool = False
    is_static: bool = False
    attributes: List[str] = field(default_factory=list)


@dataclass
class IREnumValue:
    name: str
    value: int
    attributes: List[str] = field(default_factory=list)


@dataclass
class IREnum:
    name: str
    qualified_name: str
    values: List[IREnumValue] = field(default_factory=list)
    is_scoped: bool = False
    is_anonymous: bool = False
    is_deprecated: bool = False
    deprecation_message: Optional[str] = None
    attributes: List[str] = field(default_factory=list)


@dataclass
class IRProperty:
    """A synthetic property binding backed by getter/setter methods."""
    name: str
    getter: str
    setter: Optional[str] = None
    type_spelling: str = ""
    emit: bool = True
    doc: Optional[str] = None


@dataclass
class IRUsingDeclaration:
    """A C++ using declaration that re-exports an inherited member (e.g. using Base::method)."""
    member_name: str
    base_qualified_name: str
    access: str = "public"


@dataclass
class IRClass:
    name: str
    qualified_name: str
    namespace: str
    parent_class: Optional[str] = None
    source_file: Optional[str] = None
    variable_name: str = ""
    bases: List[IRBase] = field(default_factory=list)
    inner_classes: List[IRClass] = field(default_factory=list)
    constructors: List[IRConstructor] = field(default_factory=list)
    methods: List[IRMethod] = field(default_factory=list)
    fields: List[IRField] = field(default_factory=list)
    enums: List[IREnum] = field(default_factory=list)
    using_declarations: List[IRUsingDeclaration] = field(default_factory=list)
    has_virtual_methods: bool = False
    is_abstract: bool = False
    has_deleted_copy_constructor: bool = False
    has_deleted_move_constructor: bool = False
    is_deprecated: bool = False
    deprecation_message: Optional[str] = None
    attributes: List[str] = field(default_factory=list)


@dataclass
class IRExceptionRegistration:
    """Registration of a C++ exception type as a target exception class."""
    cpp_exception_type: str
    target_exception_name: str
    base_target_exception: str = "Exception"


@dataclass
class IRFunction:
    name: str
    qualified_name: str
    namespace: str
    return_type: str
    parameters: List[IRParameter] = field(default_factory=list)
    is_overload: bool = False
    is_noexcept: bool = False
    is_varargs: bool = False
    is_operator: bool = False
    operator_type: Optional[str] = None
    is_deprecated: bool = False
    deprecation_message: Optional[str] = None
    attributes: List[str] = field(default_factory=list)


@dataclass
class IRModule:
    """Root IR object for a parsed translation unit (clang data only)."""
    name: str
    namespaces: List[str] = field(default_factory=list)
    classes: List[IRClass] = field(default_factory=list)
    functions: List[IRFunction] = field(default_factory=list)
    enums: List[IREnum] = field(default_factory=list)
    class_by_name: Dict[str, IRClass] = field(default_factory=dict)


def merge_modules(modules: List[IRModule]) -> IRModule:
    """Merge multiple IRModules into one, preserving insertion order."""
    if not modules:
        raise ValueError("merge_modules requires at least one module")
    if len(modules) == 1:
        return modules[0]
    merged = IRModule(name=modules[0].name)
    for m in modules:
        for ns in m.namespaces:
            if ns not in merged.namespaces:
                merged.namespaces.append(ns)
        merged.classes.extend(m.classes)
        merged.functions.extend(m.functions)
        merged.enums.extend(m.enums)
        merged.class_by_name.update(m.class_by_name)
    return merged
