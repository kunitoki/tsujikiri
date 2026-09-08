{%- block prologue -%}
// DO NOT EDIT - Auto-generated LuaBridge3 bindings for {{ module_name }} by tsujikiri

{% block prologue_includes -%}
extern "C" {
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>
} // extern "C"

#include <LuaBridge/LuaBridge.h>
{%- endblock %}

#include <utility>
{% for inc in includes %}
#include {{ inc }}
{%- endfor %}

{%- block api_version %}
{%- if api_version %}
static constexpr const char* k_{{ module_name }}_api_version = "{{ api_version }}";
const char* get_{{ module_name }}_api_version() { return k_{{ module_name }}_api_version; }
{%- endif %}
{%- endblock %}

void {% block prologue_name %}register_{% endblock %}{{ module_name }}(lua_State* L{% block prologue_params %}{% endblock %})
{
  {{ code_injections | code_at("beginning") }}
  {% block prologue_entry_method %}luabridge::getGlobalNamespace{% endblock %}(L)
    .beginNamespace("{{ module_name }}")
{%- endblock %}
{%- block api_version_registration %}
{%- if api_version %}
      .addFunction("get_api_version", +[] () -> const char* { return k_{{ module_name }}_api_version; })
{%- endif %}
{%- endblock %}
{%- for enum in enums %}
{%- block enum scoped %}
      .beginNamespace("{{ enum.name }}")
{%- for value in enum.values %}
{%- block enum_value scoped %}
        .addProperty("{{ value.name }}", +[] { return static_cast<std::underlying_type_t<{{ enum.qualified_name }}>>({{ enum.qualified_name }}::{{ value.original_name }}); })
{%- endblock %}
{%- endfor %}
      .endNamespace()
{%- endblock %}
{%- endfor %}
{%- for group in function_groups %}
{%- block function_group scoped %}
{%- if group.is_overloaded %}
      .addFunction("{{ group.name | camel_to_snake }}",
{%- for fn in group.functions %}
{% block function_overloaded scoped %}        {% if fn.is_default_expansion %}[]({% for p in fn.params %}{% if not loop.first %}, {% endif %}{{ p.raw_type }} {{ p | param_name('name', loop.index0) }}{% endfor %}) -> decltype(auto) { return {{ fn.spelling }}({% for p in fn.params %}{% if not loop.first %}, {% endif %}{{ p | param_name('name', loop.index0) }}{% endfor %}); }{% else %}luabridge::overload<{{ fn.params | map(attribute='type') | join(', ') }}>(&{{ fn.spelling }}){% endif %}{{ fn.overload_separator }}
{%- endblock %}
{%- endfor %}
      )
{%- else %}
{%- set fn = group.functions[0] %}
{%- if fn.wrapper_code %}
      .addFunction("{{ group.name | camel_to_snake }}", {{ fn.wrapper_code }})
{%- else %}
      .addFunction("{{ group.name | camel_to_snake }}", {% if fn.is_operator and fn.is_cpp_overloaded %}luabridge::overload<{{ fn.params | map(attribute='type') | join(', ') }}>(&{{ fn.spelling }}){% else %}&{{ fn.spelling }}{% endif %})
{%- endif %}
{%- endif %}
{%- endblock %}
{%- endfor %}
{%- for cls in classes %}
{%- block class scoped %}
{%- if cls.public_bases %}
      .deriveClass<{{ cls.qualified_name }}, {{ cls.public_bases | map(attribute='qualified_name') | join(', ') }}>("{{ cls.name }}")
{%- else %}
      .beginClass<{{ cls.qualified_name }}>("{{ cls.name }}")
{%- endif %}
{{- cls.code_injections | code_at("beginning") }}
{%- block class_constructors scoped %}
{%- if not cls.force_abstract and cls.constructor_group.constructors %}
{%- if cls.holder_type %}
{%- set ns = namespace(ctors=[]) %}
{%- for ctor in cls.constructor_group.constructors %}
{%- set ns.ctors = ns.ctors + ["void(" + (ctor.params | map(attribute='raw_type') | join(', ')) + ")"] %}
{%- endfor %}
        .addConstructorFrom<{{ cls.holder_type }}<{{ cls.qualified_name }}>, {{ ns.ctors | join(', ') }}>()
{%- else %}
{%- set ns = namespace(ctors=[]) %}
{%- for ctor in cls.constructor_group.constructors %}
{%- set ns.ctors = ns.ctors + ["void (*)(" + (ctor.params | map(attribute='raw_type') | join(', ')) + ")"] %}
{%- endfor %}
        .addConstructor<{{ ns.ctors | join(', ') }}>()
{%- endif %}
{%- endif %}
{%- endblock %}
{%- block class_methods scoped %}
{%- for group in cls.method_groups %}
{%- if group.is_static %}
{%- block class_static_method_group scoped %}
{%- if group.is_overloaded %}
        .addStaticFunction("{{ group.name | camel_to_snake }}",
{%- for method in group.methods %}
{% block class_overloaded_static_method scoped %}          {% if method.is_default_expansion %}[]({% for p in method.params %}{% if not loop.first %}, {% endif %}{{ p.raw_type }} {{ p | param_name('name', loop.index0) }}{% endfor %}) -> decltype(auto) { return {{ cls.qualified_name }}::{{ method.spelling }}({% for p in method.params %}{% if not loop.first %}, {% endif %}{{ p | param_name('name', loop.index0) }}{% endfor %}); }{% else %}{% if method.overload_kind == "const" %}luabridge::constOverload{% elif method.overload_kind == "nonconst" %}luabridge::nonConstOverload{% else %}luabridge::overload{% endif %}<{{ method.params | map(attribute='type') | join(', ') }}>(&{{ cls.qualified_name }}::{{ method.spelling }}){% endif %}{{ method.overload_separator }}
{%- endblock %}
{%- endfor %}
        )
{%- else %}
{%- set method = group.methods[0] %}
{%- if method.wrapper_code %}
        .addStaticFunction("{{ group.name | camel_to_snake }}", {{ method.wrapper_code }})
{%- else %}
        .addStaticFunction("{{ group.name | camel_to_snake }}", &{{ cls.qualified_name }}::{{ method.spelling }})
{%- endif %}
{%- endif %}
{%- endblock %}
{%- else %}
{%- block class_method_group scoped %}
{%- if group.methods | selectattr("access", "equalto", "public_via_trampoline") | list | length == group.methods | length %}
{%- else %}
{%- if group.is_overloaded %}
{%- set method0 = group.methods[0] %}
{%- if method0.is_operator and method0.operator_name %}
{%- if method0.operator_name == "__tostring" %}
        .addFunction("__tostring", [](const {{ cls.qualified_name }}& self) -> std::string { std::ostringstream _ss; _ss << self; return _ss.str(); })
{%- else %}
        .addFunction("{{ method0.operator_name }}",
{%- for method in group.methods %}
{% block class_overloaded_metamethod scoped %}          {% if method.is_default_expansion %}[]({{ cls.qualified_name }}{% if method.is_const %} const{% endif %}* self{% if method.params %}, {% endif %}{% for p in method.params %}{% if not loop.first %}, {% endif %}{{ p.raw_type }} {{ p | param_name('name', loop.index0) }}{% endfor %}) -> decltype(auto) { return self->{{ method.spelling }}({% for p in method.params %}{% if not loop.first %}, {% endif %}{{ p | param_name('name', loop.index0) }}{% endfor %}); }{% else %}{% if method.overload_kind == "const" %}luabridge::constOverload{% elif method.overload_kind == "nonconst" %}luabridge::nonConstOverload{% else %}luabridge::overload{% endif %}<{{ method.params | map(attribute='type') | join(', ') }}>(&{{ cls.qualified_name }}::{{ method.spelling }}){% endif %}{{ method.overload_separator }}
{%- endblock %}
{%- endfor %}
        )
{%- endif %}
{%- elif method0.is_operator %}
{%- else %}
        .addFunction("{{ group.name | camel_to_snake }}",
{%- for method in group.methods %}
{% block class_overloaded_method scoped %}          {% if method.is_default_expansion %}[]({{ cls.qualified_name }}{% if method.is_const %} const{% endif %}* self{% if method.params %}, {% endif %}{% for p in method.params %}{% if not loop.first %}, {% endif %}{{ p.raw_type }} {{ p | param_name('name', loop.index0) }}{% endfor %}) -> decltype(auto) { return self->{{ method.spelling }}({% for p in method.params %}{% if not loop.first %}, {% endif %}{{ p | param_name('name', loop.index0) }}{% endfor %}); }{% else %}{% if method.overload_kind == "const" %}luabridge::constOverload{% elif method.overload_kind == "nonconst" %}luabridge::nonConstOverload{% else %}luabridge::overload{% endif %}<{{ method.params | map(attribute='type') | join(', ') }}>(&{{ cls.qualified_name }}::{{ method.spelling }}){% endif %}{{ method.overload_separator }}
{%- endblock %}
{%- endfor %}
        )
{%- endif %}
{%- else %}
{%- set method = group.methods[0] %}
{%- if method.access == "public_via_trampoline" %}
{%- elif method.is_operator and method.operator_name == "__tostring" %}
        .addFunction("__tostring", [](const {{ cls.qualified_name }}& self) -> std::string { std::ostringstream _ss; _ss << self; return _ss.str(); })
{%- elif method.is_operator and method.operator_name %}
        .addFunction("{{ method.operator_name }}", {% if method.wrapper_code %}{{ method.wrapper_code }}{% elif method.is_cpp_overloaded %}luabridge::overload<{{ method.params | map(attribute='type') | join(', ') }}>(&{{ cls.qualified_name }}::{{ method.spelling }}){% else %}&{{ cls.qualified_name }}::{{ method.spelling }}{% endif %})
{%- elif method.is_operator %}
{%- elif method.wrapper_code %}
        .addFunction("{{ group.name | camel_to_snake }}", {{ method.wrapper_code }})
{%- else %}
        .addFunction("{{ group.name | camel_to_snake }}", &{{ cls.qualified_name }}::{{ method.spelling }})
{%- endif %}
{%- endif %}
{%- endif %}
{%- endblock %}
{%- endif %}
{%- endfor %}
{%- endblock %}
{%- block class_free_operators scoped %}
{%- for group in cls.free_operator_groups %}
{%- block class_free_operator_group scoped %}
{%- if group.operator_name %}
{%- if group.is_overloaded %}
        .addFunction("{{ group.operator_name }}",
{%- for fn in group.functions %}
{% block class_free_operator_overloaded scoped %}          luabridge::overload<{{ fn.params | map(attribute='type') | join(', ') }}>(&{{ fn.spelling }}){{ fn.overload_separator }}
{%- endblock %}
{%- endfor %}
        )
{%- else %}
{%- set fn = group.functions[0] %}
        .addFunction("{{ group.operator_name }}", &{{ fn.spelling }})
{%- endif %}
{%- endif %}
{%- endblock %}
{%- endfor %}
{%- endblock %}
{%- block class_fields scoped %}
{%- for field in cls.fields %}
{%- block class_field scoped %}
{%- if field.is_static %}
{%- if field.read_only %}
        .addStaticProperty("{{ field.name | camel_to_snake }}", +[] () { return {{ cls.qualified_name }}::{{ field.original_name }}; }, nullptr)
{%- else %}
        .addStaticProperty("{{ field.name | camel_to_snake }}", +[] () { return {{ cls.qualified_name }}::{{ field.original_name }}; }, +[] (const decltype({{ cls.qualified_name }}::{{ field.original_name }})& v) { {{ cls.qualified_name }}::{{ field.original_name }} = v; })
{%- endif %}
{%- else %}
{%- if field.read_only %}
        .addProperty("{{ field.name | camel_to_snake }}", [](const {{ cls.qualified_name }}& o) { return o.{{ field.original_name }}; }, nullptr)
{%- else %}
        .addProperty("{{ field.name | camel_to_snake }}", [](const {{ cls.qualified_name }}& o) { return o.{{ field.original_name }}; }, []({{ cls.qualified_name }}& o, const {{ field.raw_type }}& v) { o.{{ field.original_name }} = v; })
{%- endif %}
{%- endif %}
{%- endblock %}
{%- endfor %}
{%- endblock %}
{%- block class_properties scoped %}
{%- for prop in cls.properties %}
{%- block class_property scoped %}
{%- if prop.setter %}
        .addProperty("{{ prop.name | camel_to_snake }}", &{{ cls.qualified_name }}::{{ prop.getter }}, &{{ cls.qualified_name }}::{{ prop.setter }})
{%- else %}
        .addProperty("{{ prop.name | camel_to_snake }}", &{{ cls.qualified_name }}::{{ prop.getter }}, nullptr)
{%- endif %}
{%- endblock %}
{%- endfor %}
{%- endblock %}
{%- block class_enums scoped %}
{%- for enum in cls.enums %}
{%- block class_enum scoped %}
        .beginNamespace("{{ enum.name }}")
{%- for value in enum.values %}
{%- block class_enum_value scoped %}
          .addProperty("{{ value.name }}", +[] { return static_cast<std::underlying_type_t<{{ enum.qualified_name }}>>({{ enum.qualified_name }}::{{ value.original_name }}); })
{%- endblock %}
{%- endfor %}
        .endNamespace()
{%- endblock %}
{%- endfor %}
{%- endblock %}
{{- cls.code_injections | code_at("end") }}
      .endClass()
{%- endblock %}
{%- endfor %}
{%- block epilogue %}
    .endNamespace();

  {{ code_injections | code_at("end") }}
}
{%- endblock %}
