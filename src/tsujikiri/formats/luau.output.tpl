{%- block prologue -%}
--!strict
-- DO NOT EDIT - Auto-generated Luau type definitions for {{ module_name }} by tsujikiri
{{ code_injections | code_at("beginning") }}
{%- endblock %}
{%- block api_version %}
{%- if api_version %}

declare function get_api_version(): string
{%- endif %}
{%- endblock %}
{%- for cls in classes %}
{%- block class scoped %}
{%- if cls.doc %}

--- {{ cls.doc }}
{%- endif %}
{%- if cls.is_deprecated %}
{%- if not cls.doc %}
{{ '' }}
{%- endif %}
--- @deprecated{% if cls.deprecation_message %} {{ cls.deprecation_message }}{% endif %}
{%- endif %}
{%- if not cls.doc and not cls.is_deprecated %}
{{ '' }}
{%- endif %}
declare extern type {{ cls.name }}{% if cls.base_name %} extends {{ cls.base_short_name }}{% endif %} with
{%- block class_fields scoped %}
{%- for field in cls.fields if not field.is_static %}
{%- if field.doc %}
    --- {{ field.doc }}
{%- endif %}
    {{ field.name }}: {{ field.type }}
{%- endfor %}
{%- endblock %}
{%- block class_methods scoped %}
{%- for group in cls.method_groups if not group.is_static %}
{%- for method in group.methods %}
{%- if method.is_operator and method.operator_name %}
    function {{ method.operator_name }}(self{% if method.params %}, {{ method.params | param_pairs('name', ': ', 'type', ', ') }}{% endif %}): {{ method.return_type }}
{%- elif not method.is_operator %}
{%- if method.doc %}
    --- {{ method.doc }}
{%- endif %}
    function {{ group.name }}(self{% if method.params %}, {{ method.params | param_pairs('name', ': ', 'type', ', ') }}{% endif %}): {{ method.return_type }}
{%- endif %}
{%- endfor %}
{%- endfor %}
{%- endblock %}
{%- block class_free_operators scoped %}
{%- for group in cls.free_operator_groups if group.operator_name %}
{%- for fn in group.functions %}
    function {{ group.operator_name }}(self{% if fn.params[1:] %}, {{ fn.params[1:] | param_pairs('name', ': ', 'type', ', ') }}{% endif %}): {{ fn.return_type }}
{%- endfor %}
{%- endfor %}
{%- endblock %}
end
{%- block class_statics scoped %}
{%- set static_fields = cls.fields | selectattr('is_static') | list %}
{%- set static_groups = cls.method_groups | selectattr('is_static') | list %}
{%- set has_ctor = cls.constructor_group.constructors and not cls.force_abstract %}
{%- if has_ctor or static_fields or static_groups %}
declare {{ cls.name }}: {
{%- if has_ctor %}
{%- if cls.constructor_group.is_overloaded %}
    new: {% for ov in cls.constructor_group.constructors %}(({% if ov.params %}{{ ov.params | param_pairs('name', ': ', 'type', ', ') }}{% endif %}) -> {{ cls.name }}){% if not loop.last %} & {% endif %}{% endfor %},
{%- else %}
{%- set ctor = cls.constructor_group.constructors[0] %}
    new: (({% if ctor.params %}{{ ctor.params | param_pairs('name', ': ', 'type', ', ') }}{% endif %}) -> {{ cls.name }}),
{%- endif %}
{%- endif %}
{%- for field in static_fields %}
    {{ field.name }}: {{ field.type }},
{%- endfor %}
{%- for group in static_groups %}
{%- if group.is_overloaded %}
    {{ group.name }}: {% for method in group.methods %}(({% if method.params %}{{ method.params | param_pairs('name', ': ', 'type', ', ') }}{% endif %}) -> {{ method.return_type }}){% if not loop.last %} & {% endif %}{% endfor %},
{%- else %}
{%- set method = group.methods[0] %}
    {{ group.name }}: (({% if method.params %}{{ method.params | param_pairs('name', ': ', 'type', ', ') }}{% endif %}) -> {{ method.return_type }}),
{%- endif %}
{%- endfor %}
}
{%- endif %}
{%- endblock %}
{{ cls.code_injections | code_at("end") }}
{%- endblock %}
{%- endfor %}
{%- for enum in enums %}
{%- block enum scoped %}
{%- if enum.is_anonymous %}
{%- for value in enum.values %}
declare {{ value.name }}: number
{%- endfor %}
{%- else %}
{%- if enum.doc %}

--- {{ enum.doc }}
{%- else %}
{{ '' }}
{%- endif %}
export type {{ enum.name }} = number
declare {{ enum.name }}: {
{%- for value in enum.values %}
{%- block enum_value scoped %}
    {{ value.name }}: number,
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

{%- if first.doc %}
--- {{ first.doc }}
{%- endif %}
{%- if first.is_deprecated %}
--- @deprecated{% if first.deprecation_message %} {{ first.deprecation_message }}{% endif %}
{%- endif %}
declare {{ group.name }}: {% for fn in group.functions %}(({% if fn.params %}{{ fn.params | param_pairs('name', ': ', 'type', ', ') }}{% endif %}) -> {{ fn.return_type }}){% if not loop.last %} & {% endif %}{% endfor %}
{%- else %}
{%- set fn = group.functions[0] %}

{%- if fn.doc %}
--- {{ fn.doc }}
{%- endif %}
{%- if fn.is_deprecated %}
--- @deprecated{% if fn.deprecation_message %} {{ fn.deprecation_message }}{% endif %}
{%- endif %}
declare function {{ group.name }}({% if fn.params %}{{ fn.params | param_pairs('name', ': ', 'type', ', ') }}{% endif %}): {{ fn.return_type }}
{%- endif %}
{%- endblock %}
{%- endfor %}
{{ code_injections | code_at("end") }}
{%- block epilogue %}{% endblock %}
