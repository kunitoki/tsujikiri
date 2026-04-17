![Backdrop](https://raw.githubusercontent.com/kunitoki/tsujikiri/main/backdrop.jpeg?x=9)

[![Tests](https://github.com/kunitoki/tsujikiri/actions/workflows/tests.yml/badge.svg?x=9)](https://github.com/kunitoki/tsujikiri/actions/workflows/tests.yml)
[![Type Check](https://github.com/kunitoki/tsujikiri/actions/workflows/typecheck.yml/badge.svg?x=9)](https://github.com/kunitoki/tsujikiri/actions/workflows/typecheck.yml)
[![Coverage](https://codecov.io/gh/kunitoki/tsujikiri/graph/badge.svg?token=5HVQQVUNFM&x=9)](https://codecov.io/gh/kunitoki/tsujikiri)
[![Documentation](https://app.readthedocs.org/projects/tsujikiri/badge/?version=latest&x=9)](https://tsujikiri.readthedocs.io/en/latest/)
[![PyPI version](https://img.shields.io/pypi/v/tsujikiri?x=9)](https://pypi.org/project/tsujikiri/)
[![Python](https://img.shields.io/pypi/pyversions/tsujikiri?x=9)](https://pypi.org/project/tsujikiri/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

# tsujikiri — 辻斬り

> **Cut through C++ bindings**

tsujikiri parses C++ headers via **libclang**, **filters** by namespace and pattern, **transforms** symbols — rename, remap types, inject code — then **renders** ready-to-compile bindings through a Jinja2 template. Precise control, zero boilerplate.

Built-in support for [LuaBridge3](https://github.com/kunitoki/LuaBridge3) (Lua bindings), [LuaLS](https://luals.github.io/) (Lua Language Server annotations), [pybind11](https://pybind11.readthedocs.io/) (Python bindings), and Python type stubs (`.pyi`). Custom formats are first-class.

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

## Documentation

Full documentation is available at [tsujikiri.readthedocs.io](https://tsujikiri.readthedocs.io/en/latest/).

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

**Requirements:** Python ≥ 3.12

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
tsujikiri -i myproject.input.yml --target luabridge3 -

# Write to file
tsujikiri -i myproject.input.yml --target luabridge3 bindings.cpp

# Generate multiple outputs in one pass
tsujikiri -i myproject.input.yml \
  --target luabridge3 bindings.cpp \
  --target pybind11 py_bindings.cpp \
  --target pyi mymodule.pyi

# Dry-run: parse and filter, print summary
tsujikiri -i myproject.input.yml --target luabridge3 - --dry-run

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

## Built-in Formats

### `luabridge3`

Generates C++ registration code for [LuaBridge3](https://github.com/kunitoki/LuaBridge3).

```bash
tsujikiri -i project.input.yml --target luabridge3 bindings/lua_bindings.cpp
```

Handles: classes, constructors, instance/static methods, overloaded methods, properties, enums, free functions, inheritance.

### `luals`

Generates [Lua Language Server](https://luals.github.io/) annotation stubs.

```bash
tsujikiri -i project.input.yml --target luals types/myproject.lua
```

Emits `---@class`, `---@field`, `---@param`, `---@return` annotations with C++→Lua type mappings.

### `pybind11`

Generates C++ registration code for [pybind11](https://pybind11.readthedocs.io/).

```bash
tsujikiri -i project.input.yml --target pybind11 src/py_bindings.cpp
```

Handles: classes with multiple inheritance, constructors, instance/static methods, overloaded methods (via `py::overload_cast`), read-write/read-only properties, enums (via `py::enum_`), free functions, doc strings.

### `pyi`

Generates Python type stub files (`.pyi`) for use alongside `pybind11` bindings.

```bash
tsujikiri -i project.input.yml --target pyi mymodule.pyi
```

Emits Python-typed stubs with `@overload`, `@staticmethod`, class inheritance, enum stubs as `class Foo(int)`, and C++→Python type mappings.

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

template:
  {%- block prologue -%}
  # DO NOT EDIT - Auto-generated Python stubs for {{ module_name }} by tsujikiri
  from __future__ import annotations
  from typing import overload
  {{ code_injections | code_at("beginning") }}
  {%- endblock %}
  # ... finish the template
```

Point tsujikiri at your format directory:

```bash
tsujikiri -i project.input.yml --target myformat out/bindings.cpp -f ./my_formats/
```

---

## CLI Reference

```
tsujikiri [OPTIONS]

Options:
  -i, --input FILE            Input config YAML (required)
  -t, --target FORMAT FILE    Output target: FORMAT is a built-in name or path to
                              .output.yml; FILE is the output path ('-' for stdout).
                              Repeatable for multiple simultaneous outputs.
  -c, --classname CLASS       Generate bindings for a single class only
  -f, --formats-dir DIR       Extra directory to search for .output.yml files (repeatable)
      --list-formats          Print available formats and exit
      --dry-run               Parse and filter only; print IR summary without generating
  -m, --manifest-file FILE    Write API manifest JSON to FILE; compare if FILE exists
      --check-compat          Exit 1 if manifest shows breaking API changes
      --embed-version         Embed the API version hash in the generated code
      --trace-transforms      Print transform stages and their targets to stderr
      --dump-ir [FILE]        Dump the post-transform IR as JSON (default: stdout)
      --validate-config       Validate input config (regex patterns, stage names) and exit
  -h, --help                  Show this message and exit
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

[![Coverage tree](https://codecov.io/gh/kunitoki/tsujikiri/graphs/tree.svg?x=9&token=5HVQQVUNFM)](https://codecov.io/gh/kunitoki/tsujikiri)

---

## License

MIT — see [LICENSE](LICENSE).
