# Input File Reference

[Home](index.md) > Input File Reference

An **input file** (conventionally named `*.input.yml`) is the primary configuration artefact for tsujikiri. It tells the tool which C++ headers to parse, what to include or exclude, how to transform the result, and what output to produce.

---

## Top-Level Keys

| Key | Type | Required | Default | Purpose |
|-----|------|----------|---------|---------|
| `loads` | list of strings | no | `[]` | Other input config files to merge in as defaults (resolved relative to this file) |
| `source` | mapping | one of `source`/`sources` | — | Single C++ source to parse |
| `sources` | list | one of `source`/`sources` | — | Multiple C++ sources to parse |
| `filters` | mapping | no | (all included) | Default filtering rules |
| `transforms` | list | no | `[]` | Default transform pipeline |
| `generation` | mapping | no | (empty) | Output generation settings |
| `attributes` | mapping | no | (built-ins only) | Custom C++ attribute handlers |
| `tweaks` | mapping | no | `{}` | Legacy per-class overrides |
| `format_overrides` | mapping | no | `{}` | Per-format filter/transform/generation overrides |
| `pretty` | bool | no | `false` | Run the language-appropriate pretty printer on generated output |
| `pretty_options` | list of strings | no | `[]` | Extra arguments forwarded to the pretty printer CLI |
| `typesystem` | mapping | no | (empty) | Type system declarations: primitive types, typedefs, custom types, containers, smart pointers, conversion rules, and declared functions |
| `custom_data` | mapping | no | `{}` | Arbitrary key-value data passed verbatim into the template context as `custom_data` |

The module name used in the generated output (e.g. `register_myproject`) is derived from the input file name: `myproject.input.yml` → `myproject`.

---

## `loads` — Configuration Loads

`loads` lets you split shared configuration into reusable files and compose them. Each path is resolved relative to the file declaring it.

```yaml
loads:
  - ./common/base.input.yml
  - ../shared/typesystem.input.yml
```

### Merge semantics

Loaded files are processed first and provide **defaults**. The current file's values **extend or override** them:

| Value type | Behaviour |
|------------|-----------|
| Scalar (`pretty`, `pretty_options`, `prefix`, …) | Current file wins on conflict; loaded value used when key is absent |
| List (`sources`, `transforms`, `generation.includes`, …) | Loaded entries come first, then current file's entries |
| Mapping (`filters`, `custom_data`, `format_overrides`, …) | Deep-merged; current file wins on scalar-leaf conflicts |

When multiple paths are listed under `loads`, they are merged in order — earlier entries are treated as deeper defaults, later entries extend them.

### Cycle detection

If file A loads B and B loads A (or A loads itself), the cycle is silently broken — each file is loaded at most once per resolution chain.

### Nested loads

Loaded files may themselves declare `loads`. Resolution is recursive: the full merged result of a loaded file (including its own loads) is merged into the parent before the parent's own values are applied.

### Example

```yaml
# common/filters.input.yml
filters:
  classes:
    blacklist:
      - pattern: ".*Impl$"
        is_regex: true
  constructors:
    include: true
transforms:
  - stage: add_type_mapping
    from: "engine::String"
    to: "std::string"
```

```yaml
# game_engine.input.yml
loads:
  - common/filters.input.yml

sources:
  - path: engine/physics.hpp
  - path: engine/audio.hpp

generation:
  embed_version: true
```

The resulting config has the class blacklist and `add_type_mapping` transform from `filters.input.yml`, with both sources and `embed_version: true` from `game_engine.input.yml`. Transforms from the loaded file appear before any transforms declared in `game_engine.input.yml`.

---

## `source` — Single Source Entry

Use `source` when parsing a single C++ header.

```yaml
source:
  path: "myproject.hpp"       # Path to the C++ header (relative to the input YAML)
  parse_args: ["-std=c++17"]  # Extra flags forwarded to libclang
  include_paths:              # Additional include directories
    - "/usr/local/include"
    - "third_party/include"
  defines:                    # Preprocessor definitions (equivalent to -D flags)
    - "NDEBUG"
    - "MY_FEATURE=1"
```

| Field | Type | Required | Default | Notes |
|-------|------|----------|---------|-------|
| `path` | string | yes | — | Relative to the input YAML's directory |
| `parse_args` | list of strings | no | `[]` | Any clang flag: `-std=c++17`, `-x c++` |
| `include_paths` | list of strings | no | `[]` | Equivalent to `-I` flags; added after `parse_args` |
| `system_include_paths` | list of strings | no | `[]` | Equivalent to `-isystem` flags; searched after `include_paths`, suppresses warnings from those directories |
| `defines` | list of strings | no | `[]` | Preprocessor definitions; equivalent to `-D` flags, added after `include_paths` |

---

## `sources` — Multiple Source Entries

Use `sources` when you need to parse several headers into a single binding module. Each entry may override the top-level `filters`, `transforms`, and `generation`.

```yaml
sources:
  - path: "core/types.hpp"
    parse_args: ["-std=c++17"]
    filters:
      namespaces: ["core"]
    generation:
      includes: ['"core/types.hpp"']

  - path: "ui/widgets.hpp"
    parse_args: ["-std=c++20"]
    defines: ["HAS_WIDGETS=1"]
    transforms:
      - stage: suppress_class
        pattern: ".*Internal.*"
        is_regex: true
    generation:
      includes: ['"ui/widgets.hpp"']
```

### Per-Source Override Semantics

When a source entry provides `filters`, `transforms`, or `generation`, these **replace** (not extend) the top-level defaults for that source:

- **`filters`** in a source entry: completely replaces the top-level `filters` for that source
- **`transforms`** in a source entry: completely replaces the top-level `transforms` for that source
- **`generation.includes`** in a source entry: appended to the top-level includes (not replaced)

If a source entry omits a key, the top-level value is used.

> **Tip:** Use per-source overrides when headers from different subsystems need different namespace restrictions or clang flags. Use top-level filters for policies that apply to all sources.

---

## `filters` — Filtering Rules

The `filters` section controls which classes, methods, fields, constructors, functions, and enums are included in the binding output.

```yaml
filters:
  namespaces: ["myproject"]
  sources:
    exclude_patterns: ["*.mm"]
  classes:
    whitelist: []
    blacklist: []
    internal: []
  methods:
    global_blacklist: []
    per_class: {}
  fields:
    global_blacklist: []
    per_class: {}
  constructors:
    include: true
    signatures: []
  functions:
    whitelist: []
    blacklist: []
  enums:
    whitelist: []
    blacklist: []
```

All sub-keys are optional. Omitted keys use their defaults shown above. Filter patterns are plain strings (exact match) or objects with `is_regex: true` for Python `re.fullmatch` regex.

See [Filtering](filtering.md) for complete mechanics and examples for every filter type.

---

## `transforms` — Transform Pipeline

A list of transform stages applied in order after filtering and attribute processing. Each entry is a mapping with a `stage` key identifying the operation.

```yaml
transforms:
  - stage: rename_method
    class: Vec3
    from: getLength
    to: length

  - stage: suppress_method
    class: "*"
    pattern: "operator.*"
    is_regex: true

  - stage: add_type_mapping
    from: "juce::String"
    to: "std::string"
```

Transforms mutate the Intermediate Representation in-place. The pipeline runs in list order — earlier stages affect what later stages see.

See [Transforms](transforms.md) for all 32 built-in stages with full reference and examples.

---

## `generation` — Output Generation Settings

Controls headers, prefix text, suffix text, and version embedding in the generated output.

```yaml
generation:
  includes:
    - "<myproject.hpp>"          # Angle-bracket include
    - '"relative/path.hpp"'      # Quote include (note inner quotes)
  prefix: |
    // Copyright 2024 My Company
    // SPDX-License-Identifier: MIT
  postfix: |
    // End of generated bindings
  embed_version: false
```

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `includes` | list of strings | `[]` | Each string is emitted as `#include <...>` or `#include "..."` exactly as written |
| `prefix` | string | `""` | Written verbatim before the template output |
| `postfix` | string | `""` | Written verbatim after the template output |
| `embed_version` | bool | `false` | When `true`, embeds the SHA-256 API version hash; requires template support (built-in formats support this) |

> **Note on includes format:** Write the string exactly as it should appear inside `#include`. Use `"<vector>"` for system headers and `'"myfile.hpp"'` (YAML string containing C++ quotes) for local headers.

---

## `attributes` — Custom C++ Attribute Handlers

Maps C++ attribute names to actions. tsujikiri supports several built-in attributes automatically:

- `[[tsujikiri::skip]]` — suppress a node
- `[[tsujikiri::keep]]` — force-include a node (overrides filters)
- `[[tsujikiri::rename("name")]]` — rename a node
- `[[tsujikiri::readonly]]` — mark a field read-only
- `[[tsujikiri::thread_safe]]` — mark a method/function as thread-safe
- `[[tsujikiri::doc("text")]]` — attach a documentation string
- `[[tsujikiri::rename_argument("old", "new")]]` — rename a parameter
- `[[tsujikiri::type_map("CppType", "Target")]]` — override a type for one declaration

This section registers **additional** attribute names for your project:

```yaml
attributes:
  handlers:
    "mygame::no_export": skip      # [[mygame::no_export]] → set emit=False
    "mygame::force_export": keep   # [[mygame::force_export]] → set emit=True
    "mygame::bind_as": rename      # [[mygame::bind_as("newName")]] → set rename
```

| Value | Effect |
|-------|--------|
| `skip` | Sets `emit=False` on the annotated node |
| `keep` | Sets `emit=True` on the annotated node (overrides filters) |
| `rename` | Sets `rename` to the first quoted string argument of the attribute |

See [Attributes](attributes.md) for full documentation on how attributes are detected and processed.

---

## `tweaks` — Legacy Per-Class Overrides

`tweaks` provides simple per-class overrides. It predates the transforms system and is kept for backward compatibility.

```yaml
tweaks:
  Vec3:
    rename: "Vector3"           # Rename the class in the output
    skip_methods: ["legacy"]    # Suppress specific methods by exact name
```

> **Prefer transforms for new projects.** `rename_class` and `suppress_method` transform stages are more flexible and composable. `tweaks` will remain supported but receives no new features.

---

## `format_overrides` — Per-Format Customisation

The `format_overrides` section customises behaviour for specific output formats. The key is the format name (e.g. `luabridge3`, `luals`, `pybind11`, `pyi`).

```yaml
format_overrides:
  luabridge3:
    template_extends: |
      {% extends "luabridge3.tpl" %}
      {% block prologue %}
      // Custom file header
      {{ super() }}
      {% endblock %}
    unsupported_types:
      - "MyOpaqueHandle"
    filters:
      namespaces: ["lua_api"]
      classes:
        blacklist:
          - pattern: ".*Internal"
            is_regex: true
    transforms:
      - stage: suppress_class
        pattern: "LuaUnused"
    generation:
      includes: ['"luabridge_extras.hpp"']
      prefix: "// LuaBridge3 custom header\n"
      postfix: "// LuaBridge3 custom footer\n"
    typesystem:
      primitive_types:
        - { cpp_name: "juce::String", target_name: "str" }
    pretty: true
    pretty_options:
      - "--style=LLVM"

  luals:
    generation:
      includes: []
    typesystem_file: luals_types.input.yml   # load typesystem from an external file
    pretty: false  # disable even if top-level pretty: true
```

| Field | Type | Default | Override Behaviour |
|-------|------|---------|-------------------|
| `template_extends` | string | `""` | Inline Jinja2 child template; `{% extends "luabridge3.tpl" %}` must appear first |
| `unsupported_types` | list of strings | `[]` | **Appended to** the format's built-in unsupported types list |
| `filters` | mapping | (use effective filters) | **Replaces** the effective filter set entirely for this format |
| `transforms` | list | `[]` | **Appended after** all other transforms for this format |
| `generation.includes` | list | `[]` | **Appended to** the merged includes from top-level and per-source entries |
| `generation.prefix` | string | `""` | **Replaces** the top-level prefix when non-empty |
| `generation.postfix` | string | `""` | **Replaces** the top-level postfix when non-empty |
| `generation.embed_version` | bool | `false` | OR'd with top-level `embed_version` |
| `typesystem` | mapping | (absent) | Inline typesystem declarations; entries **take priority over** the top-level `typesystem` for this format only |
| `typesystem_file` | string | `""` | Path to a YAML file whose `typesystem:` block is used as the format typesystem; **takes precedence over** inline `typesystem` when non-empty; relative paths resolved relative to the input YAML |
| `pretty` | bool or absent | (inherit) | `true` = force-enable; `false` = force-disable; absent = inherit top-level `pretty` |
| `pretty_options` | list of strings or absent | (inherit) | Override args for the pretty printer; absent = inherit top-level `pretty_options` |

---

(override-precedence)=
## Override Precedence

When a value can come from multiple places, this is the resolution order (highest priority wins):

```
format_overrides.<format>.filters   ← replaces entirely
    ↑
sources[N].filters                  ← replaces top-level for that source
    ↑
filters                             ← top-level default
```

For transforms:
```
[top-level transforms] + [per-source transforms override top-level]
    then:
+ [format_overrides.<format>.transforms]   ← appended last
```

For generation includes:
```
top-level includes
  + per-source includes (for each source entry)
  + format_overrides includes
  = final includes list (additive, no deduplication)
```

For generation prefix/postfix:
```
format_overrides prefix/postfix replaces top-level when non-empty
top-level prefix/postfix used when format_overrides omits or leaves empty
```

For pretty printing (highest priority wins):
```
CLI --pretty [FORMAT...]                    ← overrides all YAML settings
    ↑
format_overrides.<format>.pretty            ← per-format YAML override
    ↑
pretty                                      ← top-level YAML default
```

`pretty_options` follows the same priority chain; the first non-absent level wins.

### Full Example

This configuration combines multi-source, top-level filters, format-specific overrides, and generation settings:

```yaml
# game_engine.input.yml

sources:
  - path: "engine/physics.hpp"
    parse_args: ["-std=c++17"]
    defines: ["ENGINE_PHYSICS=1"]
    filters:
      namespaces: ["physics"]
    generation:
      includes: ['"engine/physics.hpp"']

  - path: "engine/audio.hpp"
    parse_args: ["-std=c++17"]
    defines: ["ENGINE_AUDIO=1"]
    filters:
      namespaces: ["audio"]
    generation:
      includes: ['"engine/audio.hpp"']

filters:
  classes:
    blacklist:
      - pattern: ".*Impl$"
        is_regex: true
      - pattern: ".*Detail$"
        is_regex: true
  methods:
    global_blacklist:
      - pattern: "operator.*"
        is_regex: true
  constructors:
    include: true

transforms:
  - stage: add_type_mapping
    from: "engine::String"
    to: "std::string"

generation:
  embed_version: true

attributes:
  handlers:
    "engine::no_script": skip
    "engine::script_name": rename

format_overrides:
  luabridge3:
    generation:
      includes: ['"engine/lua_compat.hpp"']
    transforms:
      - stage: suppress_class
        pattern: ".*LuaInternal.*"
        is_regex: true
  luals:
    generation:
      prefix: "-- LuaLS type stubs for My Game Engine\n"
```

---

## `pretty` / `pretty_options` — Post-Generation Pretty Printing

When `pretty: true`, tsujikiri pipes the generated output through the language-appropriate pretty printer before writing it. The pretty printer is determined by the output config's `language` field.

Currently registered pretty printers:

| Language | Command | Used by formats |
|----------|---------|-----------------|
| `cpp` | `clang-format` | `luabridge3`, `pybind11` |
| `python` | `ruff format` | `pyi` |

```yaml
pretty: true
pretty_options:
  - "--style=Google"
  - "--sort-includes"
```

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `pretty` | bool | `false` | Run the pretty printer on generated output |
| `pretty_options` | list of strings | `[]` | Extra CLI arguments forwarded to the pretty printer |

The pretty printer is invoked with `-` as the filename so it reads from stdin and writes to stdout — no temporary file is created. If the pretty printer binary is not on `PATH`, tsujikiri raises `FileNotFoundError`. If the pretty printer exits non-zero, `subprocess.CalledProcessError` is raised.

> **Tip:** When `language` has no registered pretty printer (e.g. `luals`), `pretty: true` is silently ignored.

### Per-Format and CLI Overrides

`pretty` can also be controlled per-format via `format_overrides` or overridden entirely from the CLI:

```yaml
# Enable globally but disable for the luals format (no registered printer)
pretty: true
pretty_options:
  - "--style=Google"

format_overrides:
  luals:
    pretty: false
  pybind11:
    pretty: true          # force-enable even if top-level were false
    pretty_options:       # use different options for this format
      - "--style=LLVM"
```

From the CLI, `--pretty` overrides the YAML setting for all targets or specific ones:

```bash
# Enable for all targets (overrides pretty: false in YAML)
tsujikiri -i project.input.yml --target luabridge3 out.cpp --pretty

# Enable only for luabridge3 (disables for all other targets even if YAML says true)
tsujikiri -i project.input.yml \
  --target luabridge3 out.cpp \
  --target luals out.lua \
  --pretty luabridge3
```

See [Override Precedence](#override-precedence) for the full resolution order.

---

## `typesystem` — Type System Declarations

The `typesystem` section provides first-class type metadata to the generator. It lets you declare how C++ types map to target-language types, define container and smart-pointer wrappers, supply conversion rules, and declare functions that the parser cannot see (e.g. templates or generated wrappers).

```yaml
typesystem:
  primitive_types:
    - { cpp_name: "int32_t",     target_name: "int" }
    - { cpp_name: "float",       target_name: "float" }
    - { cpp_name: "std::string", target_name: "str" }

  typedef_types:
    - { cpp_name: "EntityId",    target_name: "int32_t" }

  custom_types:
    - { cpp_name: "lua_State" }

  container_types:
    - { cpp_name: "std::vector",  kind: "list" }
    - { cpp_name: "std::map",     kind: "map" }
    - { cpp_name: "std::set",     kind: "set" }
    - { cpp_name: "std::pair",    kind: "pair" }

  smart_pointer_types:
    - { cpp_name: "std::shared_ptr", kind: "shared", getter: "get" }
    - { cpp_name: "std::unique_ptr", kind: "unique", getter: "get" }

  declared_functions:
    - name: makeCircle
      namespace: mylib
      return_type: "mylib::Circle*"
      parameters:
        - { name: radius, type: double }
      wrapper_code: "+[](double r) { return mylib::Circle::create(r); }"
      doc: "Factory helper for Circle objects"

  conversion_rules:
    - cpp_type: "mylib::Color"
      native_to_target: "%%in.toInt()"
      target_to_native: "mylib::Color::fromInt(%%in)"
```

### Sub-keys

| Key | Type | Purpose |
|-----|------|---------|
| `primitive_types` | list | Map a C++ type name to a target-language primitive name |
| `typedef_types` | list | Declare a C++ typedef as an alias to another known type |
| `custom_types` | list | Declare types that exist externally — no binding is generated, but the type is recognised |
| `container_types` | list | Declare C++ container templates and their sequence protocol kind |
| `smart_pointer_types` | list | Declare smart pointer templates with their kind and inner-object accessor |
| `declared_functions` | list | Manually declare functions the parser cannot see (templates, wrappers) |
| `conversion_rules` | list | Provide native ↔ target conversion code for a C++ type |

### `primitive_types`

Each entry maps one C++ type spelling to a target-language name:

| Field | Type | Notes |
|-------|------|-------|
| `cpp_name` | string | Exact C++ type spelling (e.g. `"std::string"`) |
| `target_name` | string | Target type name (e.g. `"str"`) |

### `typedef_types`

| Field | Type | Notes |
|-------|------|-------|
| `cpp_name` | string | Typedef name (e.g. `"EntityId"`) |
| `source` | string | Underlying type (e.g. `"int32_t"`) |

### `custom_types`

| Field | Type | Notes |
|-------|------|-------|
| `cpp_name` | string | The C++ type name — recognised as a known external type |

### `container_types`

| Field | Type | Notes |
|-------|------|-------|
| `cpp_name` | string | Template name (e.g. `"std::vector"`) |
| `kind` | string | `"list"` \| `"map"` \| `"set"` \| `"pair"` |

### `smart_pointer_types`

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `cpp_name` | string | — | Template name (e.g. `"std::shared_ptr"`) |
| `kind` | string | — | `"shared"` \| `"unique"` \| `"weak"` |
| `getter` | string | `"get"` | Member function returning the raw pointer |

### `declared_functions`

Allows the generator to include functions the libclang parser cannot see (template wrappers, factory helpers, etc.).

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `name` | string | — | Function name (required) |
| `namespace` | string | `""` | C++ namespace (qualified name becomes `namespace::name`) |
| `return_type` | string | `"void"` | C++ return type spelling |
| `parameters` | list | `[]` | Each item: `{ name: "...", type: "..." }` |
| `wrapper_code` | string | — | Lambda or callable to emit instead of `&qualifiedName` |
| `doc` | string | — | Documentation string attached to the function |

### `conversion_rules`

Provides native-to-target and target-to-native conversion expressions for a C++ type. Templates use these to emit appropriate conversion code.

| Field | Type | Notes |
|-------|------|-------|
| `cpp_type` | string | C++ type spelling (required) |
| `native_to_target` | string | Expression converting C++ value to target; `%%in` is the input value |
| `target_to_native` | string | Expression converting target value to C++; `%%in` is the input value |

---

## `custom_data` — User-Defined Template Variables

`custom_data` is an arbitrary YAML mapping whose contents are passed verbatim into the Jinja2 template context under the key `custom_data`. Values may be any YAML scalar (string, int, float, bool) or nested mappings and lists.

```yaml
custom_data:
  xyz: 1
  abc:
    - "a"
    - "b"
    - "c"
  something_else: true
  something_new: 42.1337
```

Inside any template, reference these values with normal Jinja2 syntax:

```jinja
// scalar
{{ custom_data.xyz }}

// list index
{{ custom_data.abc[1] }}

// list element piped through a filter
{{ custom_data.abc[1] | camel_to_snake }}

// nested mapping
{{ custom_data.nested.key }}
```

`custom_data` is available alongside all other top-level template variables (`module_name`, `classes`, `enums`, etc.). When the key is absent or set to `null`, `custom_data` is an empty dict `{}`.

---

## See Also

- [Filtering](filtering.md) — complete mechanics for every filter type
- [Transforms](transforms.md) — all 32 transform stages with examples
- [Output Formats](output-formats.md) — format files, custom formats, template_extends
- [Attributes](attributes.md) — C++ attribute system
