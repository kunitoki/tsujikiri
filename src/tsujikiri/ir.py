"""Intermediate Representation (IR) for the C++ binding generator.

All IR nodes are pure Python dataclasses with no libclang references.
Every node carries an `emit` flag (default True) that filters and transforms
use to suppress generation; the generator skips nodes where emit=False.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class IRParameter:
    name: str
    type_spelling: str


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
    is_overload: bool = False   # set during IR build when multiple same-name methods exist
    source_file: Optional[str] = None
    emit: bool = True
    rename: Optional[str] = None    # set by transforms to change the binding name


@dataclass
class IRConstructor:
    parameters: List[IRParameter] = field(default_factory=list)
    is_overload: bool = False   # set when multiple constructors exist
    emit: bool = True


@dataclass
class IRField:
    name: str
    type_spelling: str
    is_const: bool = False
    is_static: bool = False
    emit: bool = True
    rename: Optional[str] = None


@dataclass
class IREnumValue:
    name: str
    value: int
    emit: bool = True


@dataclass
class IREnum:
    name: str
    qualified_name: str
    values: List[IREnumValue] = field(default_factory=list)
    emit: bool = True


@dataclass
class IRClass:
    name: str
    qualified_name: str
    namespace: str
    bases: List[str] = field(default_factory=list)          # base class qualified names
    inner_classes: List[IRClass] = field(default_factory=list)
    constructors: List[IRConstructor] = field(default_factory=list)
    methods: List[IRMethod] = field(default_factory=list)
    fields: List[IRField] = field(default_factory=list)
    enums: List[IREnum] = field(default_factory=list)
    emit: bool = True
    rename: Optional[str] = None
    variable_name: str = ""         # camelCase binding variable name
    parent_class: Optional[str] = None   # for inner classes
    source_file: Optional[str] = None


@dataclass
class IRFunction:
    name: str
    qualified_name: str
    namespace: str
    return_type: str
    parameters: List[IRParameter] = field(default_factory=list)
    is_overload: bool = False
    emit: bool = True
    rename: Optional[str] = None


@dataclass
class IRModule:
    """Root IR object for an entire parsed translation unit."""
    name: str
    namespaces: List[str] = field(default_factory=list)
    classes: List[IRClass] = field(default_factory=list)
    functions: List[IRFunction] = field(default_factory=list)
    enums: List[IREnum] = field(default_factory=list)
    class_by_name: Dict[str, IRClass] = field(default_factory=dict)  # for topo-sort
