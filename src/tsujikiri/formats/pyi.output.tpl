{%- block prologue -%}
# DO NOT EDIT - Auto-generated Python stubs for {{ module_name }} by tsujikiri
from __future__ import annotations
import enum
from typing import Callable, overload
{{ code_injections | code_at("beginning") }}
{%- endblock %}
{%- block api_version %}
{%- if api_version %}

__api_version__: str
{%- endif %}
{%- endblock %}
{%- for cls in classes %}
{%- block class scoped %}

class {{ cls.name }}{% if cls.public_bases %}({{ cls.public_bases | map(attribute='short_name') | join(', ') }}){% endif %}:
{%- set operators = namespace(names=[]) %}
{%- for group in cls.method_groups %}{% for method in group.methods if method.is_operator and method.operator_name %}{% set operators.names = operators.names + [method.operator_name] %}{% endfor %}{% endfor %}
{%- for group in cls.free_operator_groups if group.operator_name %}{% for fn in group.functions %}{% set operators.names = operators.names + [group.operator_name] %}{% endfor %}{% endfor %}
{%- if cls.has_free_ostream_op %}{% set operators.names = operators.names + ["__repr__"] %}{% endif %}
{%- set class_body %}
{%- if cls.doc %}
    """{{ cls.doc }}"""
{%- endif %}
{%- block class_fields scoped %}
{%- for field in cls.fields %}
{%- block class_field scoped %}
{%- if field.is_static %}
    {{ field.name }}: {{ field.type }}  # static{% if field.read_only %}, read-only{% endif %}
{%- else %}
    {{ field.name }}: {{ field.type }}{% if field.read_only %}  # read-only{% endif %}
{%- endif %}
{%- if field.doc %}
    """{{ field.doc }}"""
{%- endif %}
{%- endblock %}
{%- endfor %}
{%- endblock %}
{%- block class_constructors scoped %}
{%- if not cls.force_abstract %}
{%- for ctor in cls.constructor_group.constructors %}
{%- block class_constructor scoped %}
    def __init__(self{% for p in ctor.params %}, {{ p.name }}: {{ p.type }}{% if p.default %} = {{ p.default }}{% endif %}{% endfor %}) -> None:{% if not ctor | entity_has_doc %} ...{% endif %}
{%- if ctor | entity_has_doc %}
        """{{ ctor | docstring_body("        ") }}"""
{%- endif %}
{%- endblock %}
{%- endfor %}
{%- endif %}
{%- endblock %}
{%- block class_methods scoped %}
{%- for group in cls.method_groups %}
{%- if group.methods[0].is_operator %}
{%- elif group.is_overloaded %}
{%- block class_overloaded_method_group scoped %}
{%- for method in group.methods %}
{%- block class_overloaded_method scoped %}
{%- if group.is_static %}
    @overload
    @staticmethod
    def {{ group.name | camel_to_snake }}({% for p in method.params %}{% if not loop.first %}, {% endif %}{{ p.name }}: {{ p.type }}{% if p.default %} = {{ p.default }}{% endif %}{% endfor %}) -> {{ method.return_type }}:{% if not method | entity_has_doc %} ...{% endif %}
{%- else %}
    @overload
    def {{ group.name | camel_to_snake }}(self{% for p in method.params %}, {{ p.name }}: {{ p.type }}{% if p.default %} = {{ p.default }}{% endif %}{% endfor %}) -> {{ method.return_type }}:{% if not method | entity_has_doc %} ...{% endif %}
{%- endif %}
{%- if method | entity_has_doc %}
        """{{ method | docstring_body("        ") }}"""
{%- endif %}
{%- endblock %}
{%- endfor %}
{%- endblock %}
{%- else %}
{%- set method = group.methods[0] %}
{%- block class_method scoped %}
{%- if method.is_deprecated %}
    # deprecated{% if method.deprecation_message %}: {{ method.deprecation_message }}{% endif %}
{%- endif %}
{%- if group.is_static %}
    @staticmethod
    def {{ group.name | camel_to_snake }}({% for p in method.params %}{% if not loop.first %}, {% endif %}{{ p.name }}: {{ p.type }}{% if p.default %} = {{ p.default }}{% endif %}{% endfor %}) -> {{ method.return_type }}:{% if not method | entity_has_doc %} ...{% endif %}
{%- else %}
    def {{ group.name | camel_to_snake }}(self{% for p in method.params %}, {{ p.name }}: {{ p.type }}{% if p.default %} = {{ p.default }}{% endif %}{% endfor %}) -> {{ method.return_type }}:{% if not method | entity_has_doc %} ...{% endif %}
{%- endif %}
{%- if method | entity_has_doc %}
        """{{ method | docstring_body("        ") }}"""
{%- endif %}
{%- endblock %}
{%- endif %}
{%- endfor %}
{%- endblock %}
{%- block class_operators scoped %}
{%- for name in operators.names | unique %}
{%- if name in ("__repr__", "__bool__") and operators.names.count(name) > 1 or name == "__repr__" %}
    def {{ name }}(self) -> {{ "str" if name == "__repr__" else "bool" }}: ...
{%- else %}
{%- for group in cls.method_groups if group.methods[0].is_operator %}
{%- for method in group.methods if method.operator_name == name %}
{%- block class_operator scoped %}
{%- if operators.names.count(name) > 1 %}
    @overload
{%- endif %}
    def {{ name }}(self{% for p in method.params %}, {{ p.name }}: {{ p.type }}{% if p.default %} = {{ p.default }}{% endif %}{% endfor %}) -> {{ method.return_type }}:{% if not method | entity_has_doc %} ...{% endif %}
{%- if method | entity_has_doc %}
        """{{ method | docstring_body("        ") }}"""
{%- endif %}
{%- endblock %}
{%- endfor %}
{%- endfor %}
{%- for group in cls.free_operator_groups if group.operator_name == name %}
{%- for fn in group.functions %}
{%- block class_free_operator scoped %}
{%- if operators.names.count(name) > 1 %}
    @overload
{%- endif %}
    def {{ name }}(self{% for p in fn.params[1:] %}, {{ p.name }}: {{ p.type }}{% if p.default %} = {{ p.default }}{% endif %}{% endfor %}) -> {{ fn.return_type }}:{% if not fn | entity_has_doc %} ...{% endif %}
{%- if fn | entity_has_doc %}
        """{{ fn | docstring_body("        ") }}"""
{%- endif %}
{%- endblock %}
{%- endfor %}
{%- endfor %}
{%- endif %}
{%- endfor %}
{%- endblock %}
{{ cls.code_injections | code_at("end") }}
{%- endset %}
{%- if class_body.strip() %}{{ class_body }}{% else %}
    ...
{%- endif %}
{%- endblock %}
{%- endfor %}
{%- for enum in enums %}
{%- block enum scoped %}
{%- if enum.is_anonymous %}
{%- for value in enum.values %}

{{ value.name }}: int = {{ value.number }}
{%- endfor %}
{%- elif enum.is_scoped %}

class {{ enum.name }}(enum.IntEnum):
{%- if enum.is_deprecated %}
    # deprecated{% if enum.deprecation_message %}: {{ enum.deprecation_message }}{% endif %}
{%- endif %}
{%- if enum.doc %}
    """{{ enum.doc }}"""
{%- endif %}
{%- for value in enum.values %}
{%- block scoped_enum_value scoped %}
    {{ value.name }}: int = {{ value.number }}
{%- if value.doc %}
    """{{ value.doc }}"""
{%- endif %}
{%- endblock %}
{%- endfor %}
{%- if not enum.values and not enum.doc %}
    ...
{%- endif %}
{%- else %}

class {{ enum.name }}(int):
{%- if enum.is_deprecated %}
    # deprecated{% if enum.deprecation_message %}: {{ enum.deprecation_message }}{% endif %}
{%- endif %}
{%- if enum.doc %}
    """{{ enum.doc }}"""
{%- endif %}
{%- for value in enum.values %}
{%- block enum_value scoped %}
    {{ value.name }}: {{ enum.name }}
{%- if value.doc %}
    """{{ value.doc }}"""
{%- endif %}
{%- endblock %}
{%- endfor %}
{%- if not enum.values and not enum.doc %}
    ...
{%- endif %}
{%- endif %}
{%- endblock %}
{%- endfor %}
{%- for group in function_groups if not group.functions[0].is_operator %}
{%- block function_group scoped %}
{%- if group.is_overloaded %}
{%- block function_group_overloaded scoped %}
{%- for fn in group.functions %}
{%- block function_overloaded scoped %}
{%- if fn.is_deprecated %}

# deprecated{% if fn.deprecation_message %}: {{ fn.deprecation_message }}{% endif %}
{%- endif %}

@overload
def {{ group.name | camel_to_snake }}({% for p in fn.params %}{% if not loop.first %}, {% endif %}{{ p.name }}: {{ p.type }}{% if p.default %} = {{ p.default }}{% endif %}{% endfor %}) -> {{ fn.return_type }}:{% if not fn | entity_has_doc %} ...{% endif %}
{%- if fn | entity_has_doc %}
    """{{ fn | docstring_body("    ") }}"""
{%- endif %}
{%- endblock %}
{%- endfor %}
{%- endblock %}
{%- else %}
{%- set fn = group.functions[0] %}
{%- block function scoped %}
{%- if fn.is_deprecated %}

# deprecated{% if fn.deprecation_message %}: {{ fn.deprecation_message }}{% endif %}
{%- endif %}

def {{ group.name | camel_to_snake }}({% for p in fn.params %}{% if not loop.first %}, {% endif %}{{ p.name }}: {{ p.type }}{% if p.default %} = {{ p.default }}{% endif %}{% endfor %}) -> {{ fn.return_type }}:{% if not fn | entity_has_doc %} ...{% endif %}
{%- if fn | entity_has_doc %}
    """{{ fn | docstring_body("    ") }}"""
{%- endif %}
{%- endblock %}
{%- endif %}
{%- endblock %}
{%- endfor %}
{%- block exception_stubs %}
{%- for exc in exception_registrations %}

class {{ exc.target_name }}({{ exc.base }}): ...
{%- endfor %}
{%- endblock %}
{{ code_injections | code_at("end") }}
{%- block epilogue %}{% endblock %}
