![Backdrop](./backdrop.jpeg)

[![Tests](https://github.com/kunitoki/tsujikiri/actions/workflows/tests.yml/badge.svg)](https://github.com/kunitoki/tsujikiri/actions/workflows/tests.yml)
[![Coverage](https://codecov.io/gh/kunitoki/tsujikiri/graph/badge.svg?token=5HVQQVUNFM)](https://codecov.io/gh/kunitoki/tsujikiri)
[![PyPI version](https://img.shields.io/pypi/v/tsujikiri)](https://pypi.org/project/tsujikiri/)
[![Python](https://img.shields.io/pypi/pyversions/tsujikiri)](https://pypi.org/project/tsujikiri/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

# tsujikiri — 辻斬り

> **Cut through C++ bindings**

tsujikiri parses C++ headers via **libclang** and generates binding code through a **template-driven pipeline**. Define what to expose, plug in a target format, and get ready-to-compile bindings.

Built-in support for [LuaBridge3](https://github.com/kunitoki/LuaBridge3) (Lua bindings) and [LuaLS](https://luals.github.io/) (Lua Language Server annotations). Custom formats are first-class.

---

## How It Works

```
C++ Header (.hpp)
    │
    ▼  libclang
Intermediate Representation (IR)
    │
    ├─▶  FilterEngine        suppress classes / methods / fields by pattern
    │
    ├─▶  Transform Pipeline  rename, inject, remap types
    │
    ▼  Jinja2 templates
Target Binding Code
```

Each phase is independently configurable per input file and per output format.

---

## Installation

```bash
pip install tsujikiri
```

**Requirements:** Python ≥ 3.12, libclang 16

---

## Quick Start

### 1. Write an input config

```yaml
# myproject.input.yml
source:
  path: myproject.hpp
  parse_args: ["-std=c++17"]
  include_paths: ["/usr/local/include"]

filters:
  namespaces: ["myproject"]
  classes:
    whitelist: ["Vec3", "Matrix4", "Camera"]
  constructors:
    include: true

generation:
  includes: ["<myproject.hpp>"]
```

### 2. Generate bindings

```bash
# Print to stdout
tsujikiri -i myproject.input.yml -o luabridge3

# Write to file
tsujikiri -i myproject.input.yml -o luabridge3 -O bindings.cpp

# Dry-run: parse and filter, print summary
tsujikiri -i myproject.input.yml -o luabridge3 --dry-run

# List available formats
tsujikiri --list-formats
```

### 3. Example output (LuaBridge3)

Given a header with a `Vec3` class, tsujikiri emits:

```cpp
#include <myproject.hpp>
#include <LuaBridge/LuaBridge.h>

void register_myproject(lua_State* L)
{
    luabridge::getGlobalNamespace(L)
        .beginClass<myproject::Vec3>("Vec3")
            .addConstructor<void(*)(float, float, float)>()
            .addFunction("length", &myproject::Vec3::length)
            .addFunction("dot", &myproject::Vec3::dot)
            .addProperty("x", &myproject::Vec3::x)
            .addProperty("y", &myproject::Vec3::y)
            .addProperty("z", &myproject::Vec3::z)
        .endClass();
}
```

---

## Input Configuration Reference

```yaml
source:
  path: "myheader.hpp"            # C++ header to parse
  parse_args: ["-std=c++17"]      # Extra clang flags
  include_paths: []               # Additional include directories

filters:
  namespaces: []                  # Restrict parsing to these namespaces
  classes:
    whitelist: []                 # Include only matching class names (supports regex)
    blacklist: []                 # Exclude matching class names
  methods:
    global_blacklist: []          # Exclude methods from all classes
    per_class:                    # Per-class method exclusion
      MyClass: ["internalHelper"]
  fields:
    global_blacklist: []
  constructors:
    include: false                # Whether to emit constructors
    signatures: []                # Filter by parameter type signature
  functions:
    blacklist: []                 # Exclude free functions

transforms:
  - stage: rename_method
    class: MyClass
    from: getValueForKey
    to: get

  - stage: rename_class
    from: SomeInternal
    to: PublicName

  - stage: suppress_method
    class: "*"
    pattern: "operator.*"
    is_regex: true

  - stage: inject_method
    class: MyClass
    snippet: ".addFunction(\"create\", &MyClass::create)"

  - stage: add_type_mapping
    from: "std::string_view"
    to: "std::string"

generation:
  includes: ["<mylib.h>"]         # Extra #include lines in output
  prefix: ""                      # Literal text prepended to output
  postfix: ""                     # Literal text appended to output

format_overrides:                 # Per-format overrides (filters, transforms, generation)
  luabridge3:
    generation:
      includes: ["<LuaBridge/LuaBridge.h>"]
    transforms:
      - stage: suppress_method
        class: "*"
        pattern: "clone"
```

### Transform stages

| Stage | Effect |
|---|---|
| `rename_method` | Change the emitted name of a method |
| `rename_class` | Change the emitted name of a class |
| `suppress_method` | Remove a method from output |
| `suppress_class` | Remove a class from output |
| `inject_method` | Inject raw template snippet into a class block |
| `add_type_mapping` | Rewrite a C++ type spelling in all signatures |

All `pattern` fields accept plain strings or regex (`is_regex: true`). Use `"*"` to match all classes.

---

## Built-in Formats

### `luabridge3`

Generates C++ registration code for [LuaBridge3](https://github.com/kunitoki/LuaBridge3).

```bash
tsujikiri -i project.input.yml -o luabridge3 -O bindings/lua_bindings.cpp
```

Handles: classes, constructors, instance/static methods, overloaded methods, properties, enums, free functions, inheritance.

### `luals`

Generates [Lua Language Server](https://luals.github.io/) annotation stubs.

```bash
tsujikiri -i project.input.yml -o luals -O types/myproject.lua
```

Emits `---@class`, `---@field`, `---@param`, `---@return` annotations with C++→Lua type mappings.

---

## Custom Formats

Create a `myformat.output.yml` alongside your templates:

```yaml
format_name: "myformat"
format_version: "1.0"
description: "My custom binding format"

type_mappings:
  "std::string": "String"
  "int32_t": "int"

unsupported_types:
  - "CFStringRef"

templates:
  prologue: |
    // Generated by tsujikiri
    package {{ module_name }};
  class_begin: "register_class<{{ qualified_class_name }}>(\"{{ class_name }}\""
  # ... define all template keys
```

Point tsujikiri at your format directory:

```bash
tsujikiri -i project.input.yml -o myformat -F ./my_formats/ -O out/bindings.cpp
```

---

## CLI Reference

```
tsujikiri [OPTIONS]

Options:
  -i, --input FILE          Input config YAML (required)
  -o, --output FORMAT|FILE  Built-in format name or path to .output.yml
  -O, --output-file FILE    Write output to file instead of stdout
  -c, --classname CLASS     Generate bindings for a single class only
  -F, --formats-dir DIR     Extra directory to search for .output.yml files (repeatable)
      --list-formats        Print available formats and exit
      --dry-run             Parse and filter only; print IR summary without generating
  -h, --help                Show this message and exit
```

---

## Development

```bash
# Install task runner and sync dependencies
pip install just uv
just sync

# Run tests
just test

# Run tests with coverage
just coverage

# Build wheel
just build
```

The test suite covers parsing, filtering, transforms, generation, CLI integration, and end-to-end compilation with LuaBridge3.

---

## Coverage

[![Coverage tree](https://codecov.io/gh/kunitoki/tsujikiri/graphs/tree.svg?token=5HVQQVUNFM)](https://codecov.io/gh/kunitoki/tsujikiri)

---

## License

MIT — see [LICENSE](LICENSE).
