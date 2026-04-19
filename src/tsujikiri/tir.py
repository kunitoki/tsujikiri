"""Transformed Intermediate Representation (TIR) for the C++ binding generator.

TIR* classes extend their IR* counterparts with:
  - ``binding_name`` property: always returns the correct name for the binding
    output (``rename`` if set, otherwise ``name``).
  - ``origin``: reference to the pre-transform IR* snapshot (set by upgrade
    functions, may be None when objects are constructed directly in tests).
  - All transformation and augmentation fields (emit, rename, doc, type
    overrides, ownership hints, API versioning, code injections, etc.).

Use ``upgrade_module`` to convert a parsed IRModule to a TIRModule before
running the filter/attribute/transform pipeline.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from tsujikiri.ir import (
    IRBase,
    IRClass,
    IRCodeInjection,
    IRConstructor,
    IREnum,
    IREnumValue,
    IRExceptionRegistration,
    IRField,
    IRFunction,
    IRMethod,
    IRModule,
    IRParameter,
    IRProperty,
    IRUsingDeclaration,
)


# ---------------------------------------------------------------------------
# TIR leaf nodes
# ---------------------------------------------------------------------------

@dataclass
class TIRParameter(IRParameter):
    """IRParameter augmented with binding-layer overrides."""

    origin: Optional[IRParameter] = field(default=None, init=False, repr=False, compare=False)
    emit: bool = True
    rename: Optional[str] = None
    type_override: Optional[str] = None
    default_override: Optional[str] = None
    ownership: str = "none"

    @property
    def binding_name(self) -> str:
        return self.rename or self.name


@dataclass
class TIRBase(IRBase):
    """IRBase augmented with binding-layer emit flag."""

    origin: Optional[IRBase] = field(default=None, init=False, repr=False, compare=False)
    emit: bool = True


@dataclass
class TIRMethod(IRMethod):
    """IRMethod augmented with all transform and annotation fields."""

    origin: Optional[IRMethod] = field(default=None, init=False, repr=False, compare=False)
    emit: bool = True
    rename: Optional[str] = None
    return_type_override: Optional[str] = None
    return_ownership: str = "none"
    return_keep_alive: bool = False
    allow_thread: bool = False
    wrapper_code: Optional[str] = None
    doc: Optional[str] = None
    code_injections: List[IRCodeInjection] = field(default_factory=list)
    overload_priority: Optional[int] = None
    exception_policy: Optional[str] = None
    api_since: Optional[str] = None
    api_until: Optional[str] = None

    @property
    def binding_name(self) -> str:
        return self.rename or self.name


@dataclass
class TIRConstructor(IRConstructor):
    """IRConstructor augmented with transform and annotation fields."""

    origin: Optional[IRConstructor] = field(default=None, init=False, repr=False, compare=False)
    emit: bool = True
    doc: Optional[str] = None
    code_injections: List[IRCodeInjection] = field(default_factory=list)


@dataclass
class TIRField(IRField):
    """IRField augmented with binding-layer overrides."""

    origin: Optional[IRField] = field(default=None, init=False, repr=False, compare=False)
    emit: bool = True
    rename: Optional[str] = None
    read_only: bool = False
    type_override: Optional[str] = None
    doc: Optional[str] = None

    @property
    def binding_name(self) -> str:
        return self.rename or self.name


@dataclass
class TIREnumValue(IREnumValue):
    """IREnumValue augmented with binding-layer overrides."""

    origin: Optional[IREnumValue] = field(default=None, init=False, repr=False, compare=False)
    emit: bool = True
    rename: Optional[str] = None
    doc: Optional[str] = None

    @property
    def binding_name(self) -> str:
        return self.rename or self.name


@dataclass
class TIREnum(IREnum):
    """IREnum augmented with transform and annotation fields."""

    origin: Optional[IREnum] = field(default=None, init=False, repr=False, compare=False)
    emit: bool = True
    rename: Optional[str] = None
    doc: Optional[str] = None
    is_arithmetic: bool = False
    api_since: Optional[str] = None
    api_until: Optional[str] = None

    @property
    def binding_name(self) -> str:
        return self.rename or self.name


@dataclass
class TIRUsingDeclaration(IRUsingDeclaration):
    """IRUsingDeclaration augmented with emit flag."""

    origin: Optional[IRUsingDeclaration] = field(default=None, init=False, repr=False, compare=False)
    emit: bool = True


@dataclass
class TIRClass(IRClass):
    """IRClass augmented with all transform, hint, and annotation fields."""

    origin: Optional[IRClass] = field(default=None, init=False, repr=False, compare=False)
    emit: bool = True
    rename: Optional[str] = None
    doc: Optional[str] = None
    copyable: Optional[bool] = None
    movable: Optional[bool] = None
    force_abstract: bool = False
    holder_type: Optional[str] = None
    generate_hash: bool = False
    smart_pointer_kind: Optional[str] = None
    smart_pointer_managed_type: Optional[str] = None
    properties: List[IRProperty] = field(default_factory=list)
    code_injections: List[IRCodeInjection] = field(default_factory=list)
    api_since: Optional[str] = None
    api_until: Optional[str] = None

    @property
    def binding_name(self) -> str:
        return self.rename or self.name


@dataclass
class TIRFunction(IRFunction):
    """IRFunction augmented with all transform and annotation fields."""

    origin: Optional[IRFunction] = field(default=None, init=False, repr=False, compare=False)
    emit: bool = True
    rename: Optional[str] = None
    return_type_override: Optional[str] = None
    return_ownership: str = "none"
    return_keep_alive: bool = False
    allow_thread: bool = False
    wrapper_code: Optional[str] = None
    doc: Optional[str] = None
    overload_priority: Optional[int] = None
    exception_policy: Optional[str] = None
    api_since: Optional[str] = None
    api_until: Optional[str] = None

    @property
    def binding_name(self) -> str:
        return self.rename or self.name


@dataclass
class TIRModule(IRModule):
    """IRModule augmented with transform-injected data."""

    origin: Optional[IRModule] = field(default=None, init=False, repr=False, compare=False)
    code_injections: List[IRCodeInjection] = field(default_factory=list)
    exception_registrations: List[IRExceptionRegistration] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Upgrade helpers
# ---------------------------------------------------------------------------

def _ir_fields_dict(ir: object) -> dict:
    """Return a dict of init-visible dataclass fields from *ir*."""
    return {f.name: getattr(ir, f.name)
            for f in dataclasses.fields(ir)  # type: ignore[arg-type]
            if f.init}


def upgrade_parameter(ir: IRParameter) -> TIRParameter:
    tir = TIRParameter(**_ir_fields_dict(ir))
    tir.origin = ir
    return tir


def upgrade_base(ir: IRBase) -> TIRBase:
    tir = TIRBase(**_ir_fields_dict(ir))
    tir.origin = ir
    return tir


def upgrade_method(ir: IRMethod) -> TIRMethod:
    tir = TIRMethod(**_ir_fields_dict(ir))
    tir.origin = ir
    tir.parameters = [upgrade_parameter(p) for p in ir.parameters]  # type: ignore[assignment]
    if ir.access == "protected":
        tir.emit = False
    return tir


def upgrade_constructor(ir: IRConstructor) -> TIRConstructor:
    tir = TIRConstructor(**_ir_fields_dict(ir))
    tir.origin = ir
    tir.parameters = [upgrade_parameter(p) for p in ir.parameters]  # type: ignore[assignment]
    return tir


def upgrade_field(ir: IRField) -> TIRField:
    tir = TIRField(**_ir_fields_dict(ir))
    tir.origin = ir
    return tir


def upgrade_enum_value(ir: IREnumValue) -> TIREnumValue:
    tir = TIREnumValue(**_ir_fields_dict(ir))
    tir.origin = ir
    return tir


def upgrade_enum(ir: IREnum) -> TIREnum:
    tir = TIREnum(**_ir_fields_dict(ir))
    tir.origin = ir
    tir.values = [upgrade_enum_value(v) for v in ir.values]  # type: ignore[assignment]
    return tir


def upgrade_using_declaration(ir: IRUsingDeclaration) -> TIRUsingDeclaration:
    tir = TIRUsingDeclaration(**_ir_fields_dict(ir))
    tir.origin = ir
    return tir


def upgrade_class(ir: IRClass) -> TIRClass:
    tir = TIRClass(**_ir_fields_dict(ir))
    tir.origin = ir
    tir.bases = [upgrade_base(b) for b in ir.bases]  # type: ignore[assignment]
    tir.inner_classes = [upgrade_class(c) for c in ir.inner_classes]  # type: ignore[assignment]
    tir.constructors = [upgrade_constructor(c) for c in ir.constructors]  # type: ignore[assignment]
    tir.methods = [upgrade_method(m) for m in ir.methods]  # type: ignore[assignment]
    tir.fields = [upgrade_field(f) for f in ir.fields]  # type: ignore[assignment]
    tir.enums = [upgrade_enum(e) for e in ir.enums]  # type: ignore[assignment]
    tir.using_declarations = [upgrade_using_declaration(u) for u in ir.using_declarations]  # type: ignore[assignment]
    if ir.has_deleted_copy_constructor:
        tir.copyable = False
    if ir.has_deleted_move_constructor:
        tir.movable = False
    return tir


def upgrade_function(ir: IRFunction) -> TIRFunction:
    tir = TIRFunction(**_ir_fields_dict(ir))
    tir.origin = ir
    tir.parameters = [upgrade_parameter(p) for p in ir.parameters]  # type: ignore[assignment]
    return tir


def upgrade_module(ir: IRModule) -> TIRModule:
    """Convert a parsed IRModule to a TIRModule, upgrading all nested nodes."""
    tir = TIRModule(name=ir.name, namespaces=list(ir.namespaces))
    tir.origin = ir
    tir.classes = [upgrade_class(c) for c in ir.classes]  # type: ignore[assignment]
    tir.functions = [upgrade_function(f) for f in ir.functions]  # type: ignore[assignment]
    tir.enums = [upgrade_enum(e) for e in ir.enums]  # type: ignore[assignment]
    tir.class_by_name = {c.name: c for c in tir.classes}  # type: ignore[assignment]
    return tir


def merge_tir_modules(modules: List[TIRModule]) -> TIRModule:
    """Merge multiple TIRModules into one, preserving insertion order."""
    if not modules:
        raise ValueError("merge_tir_modules requires at least one module")
    if len(modules) == 1:
        return modules[0]
    merged = TIRModule(name=modules[0].name)
    for m in modules:
        for ns in m.namespaces:
            if ns not in merged.namespaces:
                merged.namespaces.append(ns)
        merged.classes.extend(m.classes)  # type: ignore[arg-type]
        merged.functions.extend(m.functions)  # type: ignore[arg-type]
        merged.enums.extend(m.enums)  # type: ignore[arg-type]
        merged.class_by_name.update(m.class_by_name)  # type: ignore[arg-type]
        merged.code_injections.extend(m.code_injections)
        merged.exception_registrations.extend(m.exception_registrations)
    return merged
