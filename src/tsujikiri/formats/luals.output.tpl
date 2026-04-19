{%- block prologue -%}
-- DO NOT EDIT - Auto-generated LuaLS annotations for {{ module_name }} by tsujikiri
{{ code_injections | code_at("beginning") }}
{%- endblock %}
{%- block api_version %}
{%- if api_version %}

---@return string
function {{ module_name }}.get_api_version() end
{%- endif %}
{%- endblock %}
{%- for cls in classes %}
{%- block class scoped %}
{%- if cls.doc %}

---{{ cls.doc }}
{%- endif %}
{%- if cls.is_deprecated %}

---@deprecated {% if cls.deprecation_message %}{{ cls.deprecation_message }}{% endif %}
{%- endif %}

---@class {{ cls.name }} {% if cls.base_name %}: {{ cls.base_short_name }}{% endif %}
{%- block class_fields scoped %}
{%- for field in cls.fields %}
{%- block class_field_annotation scoped %}
{%- if field.doc %}
---{{ field.doc }}
{%- endif %}
---@field {{ field.name }} {{ field.type }}{% if field.read_only %} (readonly){% endif %}{% if field.is_static %} (static){% endif %}
{%- endblock %}
{%- endfor %}
{%- endblock %}
{{ cls.code_injections | code_at("beginning") }}
local {{ cls.name }} = {}

{% block class_constructors scoped %}
{%- if not cls.force_abstract %}
{%- if cls.constructor_group.is_overloaded %}
{%- set first = cls.constructor_group.constructors[0] %}
{%- block class_constructor_group scoped %}
{% for p in first.params %}---@param {{ p.name }} {{ p.type }}
{% endfor -%}---@return {{ cls.name }}
{%- for ov in cls.constructor_group.constructors[1:] %}
---@overload fun({% if ov.params %}{{ ov.params | param_pairs('name', ': ', 'type', ', ') }}{% endif %}): {{ cls.name }}
{%- endfor %}
function {{ cls.name }}.new({% if first.params %}{{ first.params | map(attribute='name') | join(', ') }}{% endif %}) end
{%- endblock %}
{%- elif cls.constructor_group.constructors %}
{%- set ctor = cls.constructor_group.constructors[0] %}
{%- block class_constructor scoped %}
{% for p in ctor.params %}---@param {{ p.name }} {{ p.type }}
{% endfor -%}---@return {{ cls.name }}
function {{ cls.name }}.new({% if ctor.params %}{{ ctor.params | map(attribute='name') | join(', ') }}{% endif %}) end
{%- endblock %}
{%- endif %}
{%- endif %}
{%- endblock %}

{% block class_methods scoped %}
{%- for group in cls.method_groups %}
{%- if group.is_static %}
{%- block class_static_method_group scoped %}
{%- if group.is_overloaded %}
{%- set first = group.methods[0] %}
{% for p in first.params %}---@param {{ p.name }} {{ p.type }}
{% endfor -%}---@return {{ first.return_type }}
{%- for ov in group.methods[1:] %}
---@overload fun({% if ov.params %}{{ ov.params | param_pairs('name', ': ', 'type', ', ') }}{% endif %}): {{ ov.return_type }}
{%- endfor %}
function {{ cls.name }}.{{ group.name }}({% if first.params %}{{ first.params | map(attribute='name') | join(', ') }}{% endif %}) end
{% else %}
{%- set method = group.methods[0] %}
{% for p in method.params %}---@param {{ p.name }} {{ p.type }}
{% endfor -%}---@return {{ method.return_type }}
function {{ cls.name }}.{{ group.name }}({% if method.params %}{{ method.params | map(attribute='name') | join(', ') }}{% endif %}) end
{% endif %}
{%- endblock %}
{%- else %}
{%- block class_method_group scoped %}
{%- if group.is_overloaded %}
{%- set first = group.methods[0] %}
{%- if first.is_operator and first.operator_name == "__tostring" %}
---@return string
function {{ cls.name }}:__tostring() end
{%- elif first.is_operator and first.operator_name %}
{% for p in first.params %}---@param {{ p.name }} {{ p.type }}
{% endfor -%}---@return {{ first.return_type }}
{%- for ov in group.methods[1:] %}
---@overload fun(self: {{ cls.name }}{% if ov.params %}, {{ ov.params | param_pairs('name', ': ', 'type', ', ') }}{% endif %}): {{ ov.return_type }}
{%- endfor %}
function {{ cls.name }}:{{ first.operator_name }}({% if first.params %}{{ first.params | param_pairs('name', '', '', ', ') }}{% endif %}) end
{%- elif not first.is_operator %}
{% for p in first.params %}---@param {{ p.name }} {{ p.type }}
{% endfor -%}---@return {{ first.return_type }}
{%- for ov in group.methods[1:] %}
---@overload fun(self: {{ cls.name }}{% if ov.params %}, {{ ov.params | param_pairs('name', ': ', 'type', ', ') }}{% endif %}): {{ ov.return_type }}
{%- endfor %}
function {{ cls.name }}:{{ group.name }}({% if first.params %}{{ first.params | param_pairs('name', '', '', ', ') }}{% endif %}) end
{%- endif %}
{% else %}
{%- set method = group.methods[0] %}
{%- if method.is_operator and method.operator_name == "__tostring" %}
---@return string
function {{ cls.name }}:__tostring() end
{%- elif method.is_operator and method.operator_name %}
{% for p in method.params %}---@param {{ p.name }} {{ p.type }}
{% endfor -%}---@return {{ method.return_type }}
function {{ cls.name }}:{{ method.operator_name }}({% if method.params %}{{ method.params | param_pairs('name', '', '', ', ') }}{% endif %}) end
{%- elif not method.is_operator %}
{% for p in method.params %}---@param {{ p.name }} {{ p.type }}
{% endfor -%}---@return {{ method.return_type }}
function {{ cls.name }}:{{ group.name }}({% if method.params %}{{ method.params | param_pairs('name', '', '', ', ') }}{% endif %}) end
{%- endif %}
{% endif %}
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

{{ value.name }} = {{ value.number }}
{%- endfor %}
{%- else %}
{%- if enum.doc %}

---{{ enum.doc }}
{%- endif %}
{%- if enum.is_deprecated %}
---@deprecated {% if enum.deprecation_message %}{{ enum.deprecation_message }}{% endif %}
{%- endif %}

---@enum {{ enum.name }}
local {{ enum.name }} = {
{%- for value in enum.values %}
{%- block enum_value scoped %}
  {{ value.name }} = {{ value.number }},
{%- endblock %}
{%- endfor %}
}
{%- endif %}

{%- endblock %}
{%- endfor %}
{%- for group in function_groups %}
{%- block function_group scoped %}
{%- if group.is_overloaded %}
{%- set first = group.functions[0] %}

{%- if first.is_deprecated %}
---@deprecated {% if first.deprecation_message %}{{ first.deprecation_message }}{% endif %}
{%- endif %}
{% for p in first.params %}---@param {{ p | param_name('name', loop.index0) }} {{ p.type }}
{% endfor -%}---@return {{ first.return_type }}
{%- for ov in group.functions[1:] %}
---@overload fun({% if ov.params %}{{ ov.params | param_pairs('name', ': ', 'type', ', ') }}{% endif %}): {{ ov.return_type }}
{%- endfor %}
function {{ group.name }}({% if first.params %}{{ first.params | param_pairs('name', '', '', ', ') }}{% endif %}) end
{% else %}
{%- set fn = group.functions[0] %}

{%- if fn.is_deprecated %}
---@deprecated {% if fn.deprecation_message %}{{ fn.deprecation_message }}{% endif %}
{%- endif %}
{% for p in fn.params %}---@param {{ p | param_name('name', loop.index0) }} {{ p.type }}
{% endfor -%}---@return {{ fn.return_type }}
function {{ group.name }}({% if fn.params %}{{ fn.params | param_pairs('name', '', '', ', ') }}{% endif %}) end
{% endif %}
{%- endblock %}
{%- endfor %}
{{ code_injections | code_at("end") }}
{%- block epilogue %}{% endblock %}
