"""
Jinja2 filters and helper functions for code generation templates.
"""

import re
from typing import Any, Dict, List


def param_name(param: Dict[str, Any], name_key: str, index: int) -> str:
    """Return the parameter name if it exists, otherwise generate a default name like 'p0', 'p1', etc.

    Usage in templates::
        {% for param in list %}{{ param | param_name("name", loop.index0) }}{% endfor %}
    """
    name = param.get(name_key, None)
    return name if name else f"p{index}"


def param_pairs(params: List[Dict[str, Any]], name_key: str, sep: str, type_key: str, joiner: str) -> str:
    """Format parameter lists.

    Usage in templates::
        {{ params | param_pairs("name", ": ", "type", ", ") }}
    """
    return joiner.join(f"{param_name(p, name_key, i)}{sep}{p.get(type_key, '')}" for i, p in enumerate(params))


def camel_to_snake(name: str) -> str:
    """Convert CamelCase to snake_case for variable naming.

    Usage in templates::
        {{ "MyVariableName" | camel_to_snake }}  # Outputs: my_variable
    """
    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def snake_to_camel(name: str, uppercase_first: bool = True) -> str:
    """Convert snake_case to CamelCase for variable naming.

    Usage in templates::
        {{ "my_variable_name" | snake_to_camel }}  # Outputs: MyVariableName
        {{ "my_variable_name" | snake_to_camel(uppercase_first=False) }}  # Outputs: myVariableName
    """
    components = name.split("_")
    if uppercase_first:
        return "".join(x.title() for x in components)
    else:
        return components[0] + "".join(x.title() for x in components[1:])


def _param_docs(entity: Dict[str, Any]) -> List[tuple[str, str]]:
    """Return ``(name, doc)`` pairs for parameters that carry documentation."""
    pairs: List[tuple[str, str]] = []
    for param in entity.get("params", []) or []:
        doc = param.get("doc")
        if doc:
            pairs.append((param.get("name", ""), doc))
    return pairs


def entity_has_doc(entity: Dict[str, Any]) -> bool:
    """Return ``True`` if the entity, its return value, or any parameter is documented.

    Usage in templates::
        {% if method | entity_has_doc %}...{% endif %}
    """
    return bool(entity.get("doc") or entity.get("return_doc") or _param_docs(entity))


def docstring_body(entity: Dict[str, Any], indent: str = "") -> str:
    """Build a Google-style docstring body (without the surrounding quotes).

    The leading description stays on the opening-quote line; ``Args:``/``Returns:``
    sections (and the closing-quote alignment) are only emitted when parameter or
    return documentation exists, so simply-documented entities render on one line.

    Usage in templates::
        \"\"\"{{ method | docstring_body("        ") }}\"\"\"
    """
    head = entity.get("doc") or ""
    param_docs = _param_docs(entity)
    return_doc = entity.get("return_doc")
    if not param_docs and not return_doc:
        return head
    inner = indent + "    "
    lines: List[str] = [head]
    if param_docs:
        lines.append("")
        lines.append(f"{indent}Args:")
        lines.extend(f"{inner}{name}: {doc}" for name, doc in param_docs)
    if return_doc:
        lines.append("")
        lines.append(f"{indent}Returns:")
        lines.append(f"{inner}{return_doc}")
    lines.append(indent)
    return "\n".join(lines)


def cpp_docstring(entity: Dict[str, Any]) -> str:
    """Build a Google-style docstring as a C++ string literal body (escaped).

    Backslashes, double quotes and newlines are escaped so the result can be
    embedded directly inside a ``"..."`` literal (pybind11 docstrings).

    Usage in templates::
        , "{{ method | cpp_docstring }}"
    """
    head = entity.get("doc") or ""
    param_docs = _param_docs(entity)
    return_doc = entity.get("return_doc")
    lines: List[str] = [head] if head else []
    if param_docs:
        if lines:
            lines.append("")
        lines.append("Args:")
        lines.extend(f"    {name}: {doc}" for name, doc in param_docs)
    if return_doc:
        if lines:
            lines.append("")
        lines.append("Returns:")
        lines.append(f"    {return_doc}")
    body = "\n".join(lines)
    return body.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def lua_doc_comment(entity: Dict[str, Any], indent: str = "") -> str:
    """Build ``//`` comment lines documenting an entity (LuaBridge3 has no doc slot).

    Returns an empty string when the entity has no documentation. Each produced
    line is prefixed with ``indent`` so it can be emitted verbatim before the
    corresponding ``.addFunction(...)`` call.

    Usage in templates::
        {{ method | lua_doc_comment("        ") }}
    """
    head = entity.get("doc") or ""
    param_docs = _param_docs(entity)
    return_doc = entity.get("return_doc")
    if not head and not param_docs and not return_doc:
        return ""
    lines: List[str] = []
    if head:
        lines.append(head)
    lines.extend(f"@param {name} {doc}" for name, doc in param_docs)
    if return_doc:
        lines.append(f"@return {return_doc}")
    return "\n".join(f"{indent}// {line}" for line in lines)


def code_at(injections: List[Dict[str, Any]], position: str) -> str:
    """Return injected code snippets for a given position, joined by newlines.

    Usage in templates::
        {{ cls.code_injections | code_at("beginning") }}
        {{ code_injections | code_at("end") }}
    """
    parts = [inj["code"] for inj in injections if inj["position"] == position]
    return "\n".join(parts)
