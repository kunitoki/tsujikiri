{%- block prologue -%}
# DO NOT EDIT - Auto-generated Python stubs for {{ module_name }} by tsujikiri
from __future__ import annotations
import enum
from typing import overload
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
    def __init__(self{% for p in ctor.params %}, {{ p | param_name('name', loop.index0) }}: {{ p.type }}{% if p.default %} = {{ p.default }}{% endif %}{% endfor %}) -> None: ...
{%- if ctor.doc %}
        """{{ ctor.doc }}"""
{%- endif %}
{%- endblock %}
{%- endfor %}
{%- endif %}
{%- endblock %}
{%- block class_methods scoped %}
{%- for group in cls.method_groups %}
{%- if group.is_overloaded %}
{%- block class_overloaded_method_group scoped %}
{%- for method in group.methods %}
{%- block class_overloaded_method scoped %}
{%- if group.is_static %}
    @overload
    @staticmethod
    def {{ group.name | camel_to_snake }}({% for p in method.params %}{% if not loop.first %}, {% endif %}{{ p | param_name('name', loop.index0) }}: {{ p.type }}{% if p.default %} = {{ p.default }}{% endif %}{% endfor %}) -> {{ method.return_type }}: ...
{%- else %}
    @overload
    def {{ group.name | camel_to_snake }}(self{% for p in method.params %}, {{ p | param_name('name', loop.index0) }}: {{ p.type }}{% if p.default %} = {{ p.default }}{% endif %}{% endfor %}) -> {{ method.return_type }}: ...
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
    def {{ group.name | camel_to_snake }}({% for p in method.params %}{% if not loop.first %}, {% endif %}{{ p | param_name('name', loop.index0) }}: {{ p.type }}{% if p.default %} = {{ p.default }}{% endif %}{% endfor %}) -> {{ method.return_type }}: ...
{%- else %}
    def {{ group.name | camel_to_snake }}(self{% for p in method.params %}, {{ p | param_name('name', loop.index0) }}: {{ p.type }}{% if p.default %} = {{ p.default }}{% endif %}{% endfor %}) -> {{ method.return_type }}: ...
{%- endif %}
{%- if method.doc %}
        """{{ method.doc }}"""
{%- endif %}
{%- endblock %}
{%- endif %}
{%- endfor %}
{%- endblock %}
{{ cls.code_injections | code_at("end") }}
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
{%- endif %}
{%- endblock %}
{%- endfor %}
{%- for group in function_groups %}
{%- block function_group scoped %}
{%- if group.is_overloaded %}
{%- block function_group_overloaded scoped %}
{%- for fn in group.functions %}
{%- block function_overloaded scoped %}
{%- if fn.is_deprecated %}

# deprecated{% if fn.deprecation_message %}: {{ fn.deprecation_message }}{% endif %}
{%- endif %}

@overload
def {{ group.name | camel_to_snake }}({% for p in fn.params %}{% if not loop.first %}, {% endif %}{{ p | param_name('name', loop.index0) }}: {{ p.type }}{% if p.default %} = {{ p.default }}{% endif %}{% endfor %}) -> {{ fn.return_type }}: ...
{%- endblock %}
{%- endfor %}
{%- endblock %}
{%- else %}
{%- set fn = group.functions[0] %}
{%- block function scoped %}
{%- if fn.is_deprecated %}

# deprecated{% if fn.deprecation_message %}: {{ fn.deprecation_message }}{% endif %}
{%- endif %}

def {{ group.name | camel_to_snake }}({% for p in fn.params %}{% if not loop.first %}, {% endif %}{{ p | param_name('name', loop.index0) }}: {{ p.type }}{% if p.default %} = {{ p.default }}{% endif %}{% endfor %}) -> {{ fn.return_type }}: ...
{%- if fn.doc %}
    """{{ fn.doc }}"""
{%- endif %}
{%- endblock %}
{%- endif %}
{%- endblock %}
{%- endfor %}
{%- block exception_stubs %}
{%- for exc in exception_registrations %}

class {{ exc.python_name }}({{ exc.base }}): ...
{%- endfor %}
{%- endblock %}
{{ code_injections | code_at("end") }}
{%- block epilogue %}{% endblock %}
