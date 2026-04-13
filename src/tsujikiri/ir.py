"""Intermediate Representation (IR) for the C++ binding generator.

All IR nodes are pure Python dataclasses with no libclang references.
Every node carries an `emit` flag (default True) that filters and transforms
use to suppress generation; the generator skips nodes where emit=False.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class IRCodeInjection:
    """A snippet of code to be injected at a specific position in the output."""
    position: str   # "beginning" or "end"
    code: str


@dataclass
class IRParameter:
    name: str
    type_spelling: str
    emit: bool = True                        # False = removed from binding signature
    rename: Optional[str] = None             # binding-visible name override
    type_override: Optional[str] = None      # replaces type_spelling in output only
    default_override: Optional[str] = None   # replaces default expression in output
    default_value: Optional[str] = None      # raw C++ default extracted by parser; used as fallback
    ownership: str = "none"                  # "none" | "cpp" | "script"


@dataclass
class IRBase:
    qualified_name: str
    access: str = "public"   # "public", "protected", or "private"
    emit: bool = True        # False = suppressed by suppress_base transform


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
    is_overload: bool = False   # set during IR build when multiple same-name methods exist
    is_operator: bool = False   # True if this is a C++ operator overload
    operator_type: Optional[str] = None  # canonical operator spelling e.g. "operator+", "operator-unary"
    source_file: Optional[str] = None
    emit: bool = True
    rename: Optional[str] = None    # set by transforms to change the binding name
    attributes: List[str] = field(default_factory=list)   # raw [[...]] attribute contents
    return_type_override: Optional[str] = None   # overrides return_type in output only
    return_ownership: str = "none"               # "none" | "cpp" | "script"
    return_keep_alive: bool = False              # True → py::keep_alive<0, 1>() (return kept alive by self)
    allow_thread: bool = False                   # hint: release GIL around call
    wrapper_code: Optional[str] = None           # if set, template emits lambda instead of &Class::method
    doc: Optional[str] = None                    # documentation string from [[tsujikiri::doc("…")]]
    code_injections: List[IRCodeInjection] = field(default_factory=list)


@dataclass
class IRConstructor:
    parameters: List[IRParameter] = field(default_factory=list)
    is_overload: bool = False   # set when multiple constructors exist
    is_noexcept: bool = False
    is_explicit: bool = False
    emit: bool = True
    doc: Optional[str] = None               # documentation string
    attributes: List[str] = field(default_factory=list)
    code_injections: List[IRCodeInjection] = field(default_factory=list)


@dataclass
class IRField:
    name: str
    type_spelling: str
    is_const: bool = False
    is_static: bool = False
    emit: bool = True
    rename: Optional[str] = None
    read_only: bool = False   # force read-only even if not const in C++
    type_override: Optional[str] = None     # replaces type_spelling in output only
    doc: Optional[str] = None               # documentation string
    attributes: List[str] = field(default_factory=list)


@dataclass
class IREnumValue:
    name: str
    value: int
    emit: bool = True
    rename: Optional[str] = None            # binding-visible name override
    doc: Optional[str] = None               # documentation string from [[tsujikiri::doc("…")]]
    attributes: List[str] = field(default_factory=list)


@dataclass
class IREnum:
    name: str
    qualified_name: str
    values: List[IREnumValue] = field(default_factory=list)
    emit: bool = True
    rename: Optional[str] = None            # binding-visible name override
    doc: Optional[str] = None               # documentation string
    attributes: List[str] = field(default_factory=list)


@dataclass
class IRProperty:
    """A synthetic property binding backed by getter/setter methods."""
    name: str
    getter: str
    setter: Optional[str] = None   # None = read-only property
    type_spelling: str = ""
    emit: bool = True
    doc: Optional[str] = None


@dataclass
class IRClass:
    name: str
    qualified_name: str
    namespace: str
    bases: List[IRBase] = field(default_factory=list)        # base classes with access specifier
    inner_classes: List[IRClass] = field(default_factory=list)
    constructors: List[IRConstructor] = field(default_factory=list)
    methods: List[IRMethod] = field(default_factory=list)
    fields: List[IRField] = field(default_factory=list)
    enums: List[IREnum] = field(default_factory=list)
    properties: List[IRProperty] = field(default_factory=list)  # synthetic getter/setter properties
    has_virtual_methods: bool = False   # True if any method is virtual or pure virtual
    is_abstract: bool = False           # True if any method is pure virtual
    emit: bool = True
    rename: Optional[str] = None
    doc: Optional[str] = None               # documentation string
    variable_name: str = ""         # camelCase binding variable name
    parent_class: Optional[str] = None   # for inner classes
    source_file: Optional[str] = None
    attributes: List[str] = field(default_factory=list)
    copyable: Optional[bool] = None     # None = infer from C++; True/False = forced
    movable: Optional[bool] = None      # None = infer from C++; True/False = forced
    force_abstract: bool = False        # suppress constructors even if C++ is not abstract
    holder_type: Optional[str] = None   # e.g. "std::shared_ptr" — affects binding declaration
    code_injections: List[IRCodeInjection] = field(default_factory=list)


@dataclass
class IRFunction:
    name: str
    qualified_name: str
    namespace: str
    return_type: str
    parameters: List[IRParameter] = field(default_factory=list)
    is_overload: bool = False
    is_noexcept: bool = False
    is_operator: bool = False   # True if this is a C++ operator overload (free function)
    operator_type: Optional[str] = None  # canonical operator spelling e.g. "operator<<"
    emit: bool = True
    rename: Optional[str] = None
    attributes: List[str] = field(default_factory=list)
    return_type_override: Optional[str] = None   # overrides return_type in output only (mirrors IRMethod)
    return_ownership: str = "none"               # "none" | "cpp" | "script" (mirrors IRMethod)
    return_keep_alive: bool = False              # True → py::keep_alive<0, 1>() (mirrors IRMethod)
    allow_thread: bool = False                   # hint: release GIL around call (mirrors IRMethod)
    wrapper_code: Optional[str] = None           # if set, template emits lambda instead of &qualified_name
    doc: Optional[str] = None                    # documentation string


@dataclass
class IRModule:
    """Root IR object for an entire parsed translation unit."""
    name: str
    namespaces: List[str] = field(default_factory=list)
    classes: List[IRClass] = field(default_factory=list)
    functions: List[IRFunction] = field(default_factory=list)
    enums: List[IREnum] = field(default_factory=list)
    class_by_name: Dict[str, IRClass] = field(default_factory=dict)  # for topo-sort
    code_injections: List[IRCodeInjection] = field(default_factory=list)


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
