"""
Jinja2 filters and helper functions for code generation templates.
"""

import re
from typing import Any, Dict, List


def param_pairs(params: List[Dict[str, Any]], name_key: str, sep: str, type_key: str, joiner: str) -> str:
    """Jinja2 filter helper to format parameter lists."""
    return joiner.join(f"{p[name_key]}{sep}{p[type_key]}" for p in params)


def camel_to_snake(name: str) -> str:
    """Convert CamelCase to snake_case for variable naming."""
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()
