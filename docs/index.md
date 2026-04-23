# tsujikiri Documentation

**tsujikiri** (辻斬り — *"cut through C++ bindings"*) parses C++ headers via **libclang-ng** and generates binding code through a **template-driven pipeline**. Define what to expose, plug in a target format, and get ready-to-compile bindings.

---

## What tsujikiri Does

tsujikiri reads a YAML configuration file (`.input.yml`) that describes which C++ headers to parse, which classes and methods to expose, and how to transform the declarations for the target binding system.

It parses each header using **libclang-ng**, building an **Intermediate Representation (IR)** — a pure Python data model of all classes, methods, fields, constructors, enums, and free functions. The IR is then processed through three configurable phases — filtering, attribute processing, and transforms — before being rendered via a **Jinja2 template** into the final output.

Built-in support for [LuaBridge3](https://github.com/kunitoki/LuaBridge3) (Lua bindings), [Lua Language Server](https://luals.github.io/) (LuaLS type stubs), [pybind11](https://pybind11.readthedocs.io/) (Python bindings), and Python type stubs (`.pyi`). Custom formats are first-class citizens — define a `.output.yml` file with your Jinja2 template and point tsujikiri at it.

---

## Pipeline

```
C++ Header (.hpp)
       │
       ▼  libclang parse
Intermediate Representation (IR)
       │
       ├──▶  FilterEngine          namespaces / classes / methods / fields
       │     ↳ filtering.md
       │
       ├──▶  AttributeProcessor    [[tsujikiri::skip]], [[tsujikiri::keep]], [[tsujikiri::rename(...)]], [[tsujikiri::doc(...)]], etc.
       │     ↳ attributes.md
       │
       ├──▶  TransformPipeline     rename, suppress, inject, remap, modify
       │     ↳ transforms.md
       │
       ▼  Jinja2 template render
Target Binding Code (.cpp / .lua)
       │
       └──▶  Manifest (optional)   API snapshot for versioning and compat checks
             ↳ manifest-and-versioning.md
```

Each phase is independently configurable per input file and per output format. All configuration lives in a single `.input.yml` file.

---

```{toctree}
:hidden:
:maxdepth: 2

getting-started
input-file-reference
filtering
transforms
output-formats
attributes
manifest-and-versioning
```

## Navigation

| Document | What it covers |
|----------|---------------|
| [Getting Started](getting-started.md) | Installation, your first binding (step-by-step), complete CLI reference |
| [Input File Reference](input-file-reference.md) | Every key in `.input.yml` — `source`, `sources`, `filters`, `transforms`, `generation`, `attributes`, `format_overrides` — with types, defaults, and examples |
| [Filtering](filtering.md) | How the filter system works; all filter types: `namespaces`, `sources`, `classes` (whitelist/blacklist/internal), `methods`, `fields`, `constructors`, `functions`, `enums` |
| [Transforms](transforms.md) | All 32 built-in transform stages with full key reference and practical examples: class/method stages (`rename_method`, `rename_class`, `suppress_method`, `suppress_class`, `inject_method`, `inject_constructor`, `inject_property`, `suppress_base`, `add_type_mapping`, `modify_method`, `modify_argument`, `modify_field`, `modify_constructor`, `remove_overload`, `inject_code`, `set_type_hint`, `mark_deprecated`, `expand_spaceship`, `expose_protected`, `resolve_using_declarations`, `overload_priority`, `exception_policy`), enum stages (`rename_enum`, `rename_enum_value`, `suppress_enum`, `suppress_enum_value`, `modify_enum`), free function stages (`rename_function`, `suppress_function`, `modify_function`, `inject_function`, `register_exception`) |
| [Output Formats](output-formats.md) | Built-in `luabridge3`, `luals`, `pybind11`, and `pyi` formats in depth; complete Jinja2 template context reference; creating custom formats; extending built-in templates |
| [Attributes](attributes.md) | C++ `[[tsujikiri::skip]]`, `[[tsujikiri::keep]]`, `[[tsujikiri::rename(...)]]`, `[[tsujikiri::doc(...)]]`, `[[tsujikiri::readonly]]`, `[[tsujikiri::thread_safe]]`, `[[tsujikiri::rename_argument(...)]]`, `[[tsujikiri::type_map(...)]]`; custom attribute handlers; when to use attributes vs YAML |
| [Manifest and Versioning](manifest-and-versioning.md) | API manifest JSON; detecting breaking vs additive changes; `--check-compat`; semantic versioning integration; `--embed-version`; CI workflow |

---

## Quick Example

**Header** (`vec3.hpp`):
```cpp
namespace myproject {
class Vec3 {
public:
    Vec3() = default;
    Vec3(float x, float y, float z) : x_(x), y_(y), z_(z) {}
    float length() const;
    float dot(const Vec3& other) const;
public:
    float x_ = 0.0f, y_ = 0.0f, z_ = 0.0f;
};
}
```

**Config** (`myproject.input.yml`):
```yaml
source:
  path: vec3.hpp
  parse_args: ["-std=c++17"]

filters:
  namespaces: ["myproject"]
  classes:
    whitelist: ["Vec3"]
  constructors:
    include: true

transforms:
  - stage: modify_field
    class: Vec3
    field: "(.+)_$"
    field_is_regex: true
    rename: "\\1"

generation:
  includes: ['"vec3.hpp"']
```

**Command:**
```bash
tsujikiri -i myproject.input.yml --target luabridge3 src/bindings.cpp
```

**Output** (excerpt):
```cpp
void register_myproject(lua_State* L)
{
  luabridge::getGlobalNamespace(L)
    .beginNamespace("myproject")
      .beginClass<myproject::Vec3>("Vec3")
        .addConstructor<void (*)(float, float, float)>()
        .addFunction("length", &myproject::Vec3::length)
        .addFunction("dot", &myproject::Vec3::dot)
        .addProperty("x", &myproject::Vec3::x_)
        .addProperty("y", &myproject::Vec3::y_)
        .addProperty("z", &myproject::Vec3::z_)
      .endClass()
    .endNamespace();
}
```

See [Getting Started](getting-started.md) for the full walkthrough.

---

## Installation

Using pip:
```bash
pip install tsujikiri
```

Using uv:
```bash
uv pip install tsujikiri
```

**Requirements:** Python ≥ 3.12, `libclang-ng` ≥ 19 (Clang 19–22 supported).

To pin a specific Clang version use an extra:

```bash
pip install "tsujikiri[clang19]"   # Clang 19
pip install "tsujikiri[clang20]"   # Clang 20
pip install "tsujikiri[clang21]"   # Clang 21
pip install "tsujikiri[clang22]"   # Clang 22
```

Only one `clangXX` extra may be active at a time. See [Getting Started](getting-started.md) for details.

---

## License

MIT — see [LICENSE](../LICENSE).
