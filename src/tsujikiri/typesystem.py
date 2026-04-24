"""Typesystem dataclasses and utilities for tsujikiri."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PrimitiveTypeEntry:
    """Maps a C++ type name to a target-language primitive name."""

    cpp_name: str
    target_name: str


@dataclass
class TypedefTypeEntry:
    """Declares a C++ typedef as an alias for a target type."""

    cpp_name: str
    target_name: str


@dataclass
class CustomTypeEntry:
    """Declares a type that exists externally — no binding is generated."""

    cpp_name: str


@dataclass
class ContainerTypeEntry:
    """Declares a C++ container to wrap with a Python sequence protocol."""

    cpp_name: str
    kind: str  # "list", "map", "set", "pair"


@dataclass
class SmartPointerTypeEntry:
    """Declares a smart-pointer wrapper for ownership tracking."""

    cpp_name: str
    kind: str  # "shared", "unique", "weak"
    getter: str = "get"


@dataclass
class ConversionRuleEntry:
    """Declares native ↔ target conversion code for a C++ type."""

    cpp_type: str
    native_to_target: str  # C expression; %%in = input value
    target_to_native: str  # C expression; %%in = input value


@dataclass
class DeclaredFunctionEntry:
    """Manually declared function for parser-blind APIs (templates, wrappers)."""

    name: str
    namespace: str = ""
    return_type: str = "void"
    parameters: List[Dict[str, str]] = field(default_factory=list)
    wrapper_code: Optional[str] = None
    doc: Optional[str] = None


@dataclass
class TypesystemConfig:
    """First-class typesystem declarations for the binding generator."""

    primitive_types: List[PrimitiveTypeEntry] = field(default_factory=list)
    typedef_types: List[TypedefTypeEntry] = field(default_factory=list)
    custom_types: List[CustomTypeEntry] = field(default_factory=list)
    container_types: List[ContainerTypeEntry] = field(default_factory=list)
    smart_pointer_types: List[SmartPointerTypeEntry] = field(default_factory=list)
    declared_functions: List[DeclaredFunctionEntry] = field(default_factory=list)
    conversion_rules: List[ConversionRuleEntry] = field(default_factory=list)


def _parse_typesystem_config(ts_raw: Dict[str, Any]) -> TypesystemConfig:
    """Parse the ``typesystem:`` block from a raw YAML dict."""
    return TypesystemConfig(
        primitive_types=[
            PrimitiveTypeEntry(cpp_name=e["cpp_name"], target_name=e["target_name"])
            for e in ts_raw.get("primitive_types", [])
        ],
        typedef_types=[
            TypedefTypeEntry(cpp_name=e["cpp_name"], target_name=e["target_name"])
            for e in ts_raw.get("typedef_types", [])
        ],
        custom_types=[CustomTypeEntry(cpp_name=e["cpp_name"]) for e in ts_raw.get("custom_types", [])],
        container_types=[
            ContainerTypeEntry(cpp_name=e["cpp_name"], kind=e["kind"]) for e in ts_raw.get("container_types", [])
        ],
        smart_pointer_types=[
            SmartPointerTypeEntry(
                cpp_name=e["cpp_name"],
                kind=e["kind"],
                getter=e.get("getter", "get"),
            )
            for e in ts_raw.get("smart_pointer_types", [])
        ],
        declared_functions=[
            DeclaredFunctionEntry(
                name=e["name"],
                namespace=e.get("namespace", ""),
                return_type=e.get("return_type", "void"),
                parameters=e.get("parameters", []),
                wrapper_code=e.get("wrapper_code"),
                doc=e.get("doc"),
            )
            for e in ts_raw.get("declared_functions", [])
        ],
        conversion_rules=[
            ConversionRuleEntry(
                cpp_type=e["cpp_type"],
                native_to_target=e["native_to_target"],
                target_to_native=e["target_to_native"],
            )
            for e in ts_raw.get("conversion_rules", [])
        ],
    )


def merge_typesystems(priority: TypesystemConfig, base: TypesystemConfig) -> TypesystemConfig:
    """Return a new TypesystemConfig combining priority and base.

    Priority entries come first in each list so first-match lookups in the
    generator resolve them before base entries.
    """
    return TypesystemConfig(
        primitive_types=priority.primitive_types + base.primitive_types,
        typedef_types=priority.typedef_types + base.typedef_types,
        custom_types=priority.custom_types + base.custom_types,
        container_types=priority.container_types + base.container_types,
        smart_pointer_types=priority.smart_pointer_types + base.smart_pointer_types,
        declared_functions=priority.declared_functions + base.declared_functions,
        conversion_rules=priority.conversion_rules + base.conversion_rules,
    )
