# Getting Started

[Home](index.md) > Getting Started

---

## Requirements

- Python 3.12 or later
- libclang 16 (the Python `libclang` package wraps the system libclang)

On macOS, libclang ships with Xcode Command Line Tools. On Linux, install `libclang-16-dev` from your package manager.

---

## Installation

```bash
# From PyPI
pip install tsujikiri

# With uv
uv add tsujikiri
```

Verify the installation:

```bash
tsujikiri --list-formats
```

Expected output:

```
luabridge3
luals
pybind11
pyi
```

---

## Your First Binding

This walkthrough takes you from a C++ header to working LuaBridge3 registration code in three steps.

### Step 1 — Write your C++ header

```cpp
// vec3.hpp
#pragma once
#include <cmath>

namespace myproject {

class Vec3 {
public:
    Vec3() = default;
    Vec3(float x, float y, float z) : x_(x), y_(y), z_(z) {}

    float length() const { return std::sqrt(x_*x_ + y_*y_ + z_*z_); }
    float dot(const Vec3& other) const { return x_*other.x_ + y_*other.y_ + z_*other.z_; }
    Vec3  normalized() const { float l = length(); return {x_/l, y_/l, z_/l}; }

    void setX(float v) { x_ = v; }
    void setY(float v) { y_ = v; }
    void setZ(float v) { z_ = v; }

public:
    float x_ = 0.0f;
    float y_ = 0.0f;
    float z_ = 0.0f;
};

} // namespace myproject
```

### Step 2 — Write the input config

```yaml
# myproject.input.yml
source:
  path: vec3.hpp
  parse_args: ["-std=c++17"]

filters:
  namespaces: ["myproject"]
  classes:
    whitelist: ["Vec3"]
  constructors:
    include: true
  methods:
    global_blacklist:
      - pattern: "operator.*"
        is_regex: true

transforms:
  - stage: modify_field
    class: Vec3
    field: x_
    rename: x
  - stage: modify_field
    class: Vec3
    field: y_
    rename: y
  - stage: modify_field
    class: Vec3
    field: z_
    rename: z

generation:
  includes: ['"vec3.hpp"']
```

### Step 3 — Generate the bindings

```bash
tsujikiri -i myproject.input.yml --target luabridge3 bindings.cpp
```

**Output** (`bindings.cpp`):

```cpp
// DO NOT EDIT - Auto-generated LuaBridge3 bindings for myproject by tsujikiri
extern "C" {
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>
} // extern "C"

#include <LuaBridge/LuaBridge.h>

#include <utility>
#include "vec3.hpp"

void register_myproject(lua_State* L)
{
  luabridge::getGlobalNamespace(L)
    .beginNamespace("myproject")
      .beginClass<myproject::Vec3>("Vec3")
        .addConstructor<void (*)(float, float, float)>()
        .addFunction("length", &myproject::Vec3::length)
        .addFunction("dot", &myproject::Vec3::dot)
        .addFunction("normalized", &myproject::Vec3::normalized)
        .addFunction("set_x", &myproject::Vec3::setX)
        .addFunction("set_y", &myproject::Vec3::setY)
        .addFunction("set_z", &myproject::Vec3::setZ)
        .addProperty("x", &myproject::Vec3::x_)
        .addProperty("y", &myproject::Vec3::y_)
        .addProperty("z", &myproject::Vec3::z_)
      .endClass()
    .endNamespace();
}
```

Notice that `setX`, `setY`, `setZ` are rendered as `set_x`, `set_y`, `set_z` — tsujikiri automatically converts `camelCase` method names to `snake_case` in the output.

---

## Pipeline Overview

```
C++ Header (.hpp)
       │
       ▼  libclang parse
Intermediate Representation (IR)
       │
       ├──▶  FilterEngine          suppress by namespace / class / method / field
       │     (see Filtering)
       │
       ├──▶  AttributeProcessor    read [[tsujikiri::skip]] etc. from C++ source
       │     (see Attributes)
       │
       ├──▶  TransformPipeline     rename, suppress, inject, remap types
       │     (see Transforms)
       │
       ▼  Jinja2 template render
Target Binding Code (.cpp / .lua)
```

Each phase is independently configurable per input file and per output format. The [Input File Reference](input-file-reference.md) documents every key. Detailed pages cover [Filtering](filtering.md), [Transforms](transforms.md), [Output Formats](output-formats.md), and [Attributes](attributes.md).

---

## Dry-Run Workflow

Before generating code, use `--dry-run` to inspect what will be emitted:

```bash
tsujikiri -i myproject.input.yml --target luabridge3 - --dry-run
```

```
Format  : luabridge3 1.0
Sources : 1
Classes : 1 — Vec3
Functions: 0 — (none)
Enums   : 0 — (none)
Version : 3a8f...e291
```

This parses and filters the header without rendering any output. Use it to iterate on your filter and transform config before writing files.

---

## CLI Reference

```
tsujikiri [OPTIONS]
```

| Flag | Short | Argument | Description |
|------|-------|----------|-------------|
| `--input` | `-i` | `FILE` | Input config YAML (required) |
| `--target` | `-t` | `FORMAT FILE` | Built-in format name or path to `.output.yml`, plus output file path (`-` for stdout). Repeatable. |
| `--classname` | `-c` | `CLASS` | Generate bindings for a single class only (additive to config filters) |
| `--formats-dir` | `-F` | `DIR` | Additional directory to search for `.output.yml` files (repeatable) |
| `--list-formats` | | | Print available formats and exit |
| `--dry-run` | | | Parse and filter only; print IR summary without generating code |
| `--manifest-file` | `-M` | `FILE` | Write API manifest JSON to FILE; compare if FILE already exists |
| `--check-compat` | | | Exit 1 if manifest shows breaking API changes |
| `--embed-version` | | | Embed the API version hash string in the generated code |
| `--trace-transforms` | | | Print which transform stages ran and on what entities to stderr |
| `--dump-ir` | | `[FILE]` | Dump the post-transform IR as JSON to FILE (default: stdout) |
| `--validate-config` | | | Validate input config (regex patterns, stage names) and exit |
| `--help` | `-h` | | Show help and exit |

### Common Patterns

**Print to stdout (quick inspection):**
```bash
tsujikiri -i project.input.yml --target luabridge3 -
```

**Write to file:**
```bash
tsujikiri -i project.input.yml --target luabridge3 src/bindings.cpp
```

**Generate multiple outputs in one pass:**
```bash
tsujikiri -i project.input.yml \
  --target luabridge3 src/bindings.cpp \
  --target luals      types/myproject.lua
```

**Single class (useful during development):**
```bash
tsujikiri -i project.input.yml --target luabridge3 - -c Vec3
```

**Custom format from a local directory:**
```bash
tsujikiri -i project.input.yml --target myfmt out/bindings.cpp -F ./my_formats/
```

**API versioning — save manifest and fail on breaking changes:**
```bash
tsujikiri -i project.input.yml --target luabridge3 src/bindings.cpp \
          -M api.manifest.json --check-compat
```

**Debug transforms — see which stages apply to what:**
```bash
tsujikiri -i project.input.yml --target luabridge3 - --trace-transforms 2>transforms.log
```

**Dump IR as JSON for inspection:**
```bash
tsujikiri -i project.input.yml --target luabridge3 - --dump-ir ir.json
```

**Validate config without generating:**
```bash
tsujikiri -i project.input.yml --validate-config
```

**List all known formats (including custom directories):**
```bash
tsujikiri --list-formats -F ./my_formats/
```

---

## See Also

- [Input File Reference](input-file-reference.md) — every YAML key explained
- [Filtering](filtering.md) — control which classes and methods are exposed
- [Transforms](transforms.md) — rename, suppress, inject, and remap types
