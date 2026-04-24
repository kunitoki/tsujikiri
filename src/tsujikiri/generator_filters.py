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


def code_at(injections: List[Dict[str, Any]], position: str) -> str:
    """Return injected code snippets for a given position, joined by newlines.

    Usage in templates::
        {{ cls.code_injections | code_at("beginning") }}
        {{ code_injections | code_at("end") }}
    """
    parts = [inj["code"] for inj in injections if inj["position"] == position]
    return "\n".join(parts)
