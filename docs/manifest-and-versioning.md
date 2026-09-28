# API Manifest and Versioning

[Home](index.md) > Manifest and Versioning

tsujikiri can track the binding surface (API) of your C++ headers over time using a **manifest** — a JSON snapshot of what is currently exposed. Two manifests can be compared to detect breaking changes and suggest a semantic version bump.

---

## What the Manifest Captures

The manifest is computed from the **filtered and transformed IR**, after `emit=False` nodes have been removed. It records the **binding-visible** surface — names after renames and types after transform overrides, but before format-level remapping:

- **Classes**: their binding name, all emitted constructor signatures, all emitted methods (name, parameters, minimum arity, return type, is_static), all emitted fields (name, type, is_const/read_only), injected properties, and nested enums
- **Free functions**: name, parameter types, minimum arity, return type
- **Top-level enums**: name and all value names with their integer values
- **Transform metadata**: code injections, wrapper code, ownership/keep-alive/thread hints, exception policy, type hints, injected properties, API gates, and other transform-controlled binding metadata

The manifest does **not** capture:
- Suppressed nodes (`emit=False`)
- Template-level type remapping (from `type_mappings` in `.output.yml`)
- Comments or generation settings
- The *expressions* of parameter defaults — only how many arguments may be omitted (see `min_arity` below)

### `min_arity` — defaulted arguments

Every constructor, method and free function records `min_arity`: the smallest
number of arguments a caller may supply, i.e. the parameter count minus the
trailing run of parameters that carry a C++ default.

This is tracked separately from `params` because **removing a default does not
change any parameter type**. `f(int a, float b = 1.0f)` and `f(int a, float b)`
have an identical type list, so without `min_arity` the two produce byte-identical
manifests — while every generated binding silently loses the one-argument call.
Trailing defaults are omittable in each target language (pybind11 and pyi emit
them natively as `py::arg("b") = 1.0f` / `b: float = 1.0f`; luabridge3 and luals
emit one callable per arity, see
`expand_default_arguments` in [Output Formats](output-formats.md)), so
`min_arity` is a format-agnostic property of the binding surface.

`min_arity` is derived from the same rule the generator uses to decide which
arities to emit, so the manifest can never claim an arity that is not generated.
It is computed over the **emitted** parameters, so a parameter suppressed by a
transform is not counted.

Changing a default's *value* (`= 1.0f` → `= 2.0f`) leaves `min_arity` untouched
and is reported as no change: the callable surface is identical and only runtime
behaviour differs. There is no "changed" classification, and recording a value
that is never compared would put churn in the file that drives no version bump.

Manifests written before `min_arity` existed simply omit it. For a signature
that is still present, the comparison then **skips the arity check** rather than
assuming a value, so upgrading tsujikiri never reports a spurious change on the
first run. A signature from such a manifest that is no longer present is assumed
to accept only its full parameter list (see the next section). Constructors
in those older manifests are stored as bare lists of parameter types instead of
objects; both shapes are accepted.

### Overloads and defaulted parameters

Signatures are compared by **the calls they accept**, not by exact parameter
list. An old signature accepts every argument count from its `min_arity` up to
its parameter count. A given count `k` is still served when some new overload
with the same name, the same `is_static`, and the same return type (constructors
have no return type):

- has the same first `k` parameter types,
- has at least `k` parameters, and
- has a `min_arity` of at most `k`.

The old signature only breaks callers if some count it accepted is served by no
new overload. So these changes are **additive**, because every existing call
still resolves:

| Change | Example |
|--------|---------|
| Defaulted parameter(s) appended | `refresh()` → `refresh(bool force = false)` |
| Overloads merged into one defaulted signature | `resize()` + `resize(int)` → `resize(int n = 0)` |
| A default split into explicit overloads | `scale(float, bool = false)` → `scale(float)` + `scale(float, bool)` |

A new overload whose `min_arity` is unknown (the entry has no `min_arity`) is
assumed to need every parameter. Parameters that are prepended, retyped, or
appended without a default still break callers, and so does a changed return
type.

### Transform metadata

Transform metadata is compared per entry:

- **Class-level metadata** (holder type, copyability, API gates, class code
  injections, …): any difference is breaking.
- **Member transforms** (constructors, methods, nested enums):
  - a transform on a new member is additive;
  - a changed or removed transform is breaking.
- **Signatures kept callable by another overload** (see above): the transform
  follows the signature. It is compared with the transform of the overload that
  now serves its full argument list. Parameter transforms on the appended
  parameters are ignored.
- **Field transforms** only carry `read_only`, which the field diff already
  classifies.
- **Module code injections and exception registrations** are compared as
  before.

So changes to injected code or other transform-controlled binding behaviour
still suggest a major version bump.

---

## Manifest JSON Structure

```json
{
  "module": "myproject",
  "version": "1.2.0",
  "api": {
    "classes": [
      {
        "name": "Vec3",
        "constructors": [
          { "params": [], "min_arity": 0 },
          { "params": ["float", "float", "float"], "min_arity": 1 }
        ],
        "methods": [
          {
            "name": "length",
            "params": [],
            "min_arity": 0,
            "return_type": "float",
            "is_static": false
          },
          {
            "name": "dot",
            "params": ["const Vec3 &"],
            "min_arity": 1,
            "return_type": "float",
            "is_static": false
          }
        ],
        "fields": [
          { "name": "x_", "type": "float", "is_const": false },
          { "name": "y_", "type": "float", "is_const": false },
          { "name": "z_", "type": "float", "is_const": false }
        ],
        "enums": []
      }
    ],
    "functions": [
      {
        "name": "computeArea",
        "params": ["double"],
        "min_arity": 1,
        "return_type": "double"
      }
    ],
    "enums": [
      {
        "name": "Color",
        "values": [
          { "name": "Blue", "value": 2 },
          { "name": "Green", "value": 1 },
          { "name": "Red", "value": 0 }
        ]
      }
    ]
  },
  "transformations": {
    "code_injections": [
      { "position": "beginning", "code": "// generated prologue" }
    ]
  }
}
```

> **Tip:** Commit the manifest JSON file to version control alongside the generated bindings. This gives you a complete history of API changes.

---

## Saving and Loading a Manifest

```bash
# First run — generate bindings and save the initial manifest
tsujikiri -i project.input.yml --target luabridge3 src/bindings.cpp \
          -m api.manifest.json

# Subsequent runs — compare with existing manifest, then save updated one
tsujikiri -i project.input.yml --target luabridge3 src/bindings.cpp \
          -m api.manifest.json
```

When `-m FILE` is passed:
- If `FILE` does **not** exist: generate bindings normally, then save the manifest.
- If `FILE` **does** exist: compare the old and new manifests, print any detected changes, then save the new manifest unless `--check-compat` blocks a breaking change.

---

## Comparing Manifests — Breaking vs Additive

When the manifest changes, tsujikiri classifies each difference:

### Breaking Changes (scripts that use the old surface may break)

| What changed | Example |
|-------------|---------|
| Class removed | `Vec3` was removed |
| Constructor removed | `Vec3()` was removed |
| Method removed | `Vec3.length` was removed |
| Method signature changed so an existing call no longer resolves | `Vec3.dot(const Vec3 &) → float` signature was removed or changed (a parameter retyped or prepended, a parameter appended without a default, or the return type changed) |
| Parameter default removed | `Vec3.scale(float, float)` no longer accepts 1 argument(s) |
| Field removed | `Vec3.x_` was removed |
| Field type changed | `Vec3.x_`: `float` → `double` |
| Field const qualifier changed | `Vec3.x_` const: `false` → `true` |
| Field or property made read-only | `Vec3.x_` read-only: `False` → `True` |
| Property setter removed or replaced | `Vec3.length` setter: `setLength` → `None` |
| Enum removed | `Color` was removed |
| Enum value removed | `Color.Red` was removed |
| Enum value integer changed | `Color.Red`: 0 → 1 |
| Transform metadata changed or removed | injected code, wrapper code, or type hints changed |

### Additive Changes (existing scripts continue to work)

| What changed | Example |
|-------------|---------|
| Class added | `Matrix4` was added |
| Constructor overload added | `Vec3(float, float, float)` was added |
| Method added | `Vec3.normalize() → Vec3` was added |
| Method overload added | `add(double, double) → double` overload was added |
| Parameter default added | `Vec3.scale(float, float)` now accepts 1 argument(s) |
| Defaulted parameter(s) appended | `Vec3.length() → float` is still callable via `Vec3.length(bool) → float` |
| Overloads merged into a defaulted signature | `Vec3.scale() → void` is still callable via `Vec3.scale(float) → void` |
| Field added | `Vec3.w_` was added |
| Setter added / read-only relaxed | `Vec3.x_` read-only: `True` → `False` |
| Enum added | `BlendMode` was added |
| Enum value added | `Color.Alpha` was added |
| Transform on a new member added | `Vec3.normalize()` method transform was added |

### Stderr Output

```
WARNING: Additive API changes:
  + Class 'Matrix4' was added
  + Method 'Vec3.normalize() -> Vec3' was added
  + Method 'Vec3.length() -> float' is still callable via 'Vec3.length(bool) -> float' (defaulted parameter(s) added)

ERROR: Breaking API changes detected:
  ! Method 'Vec3.dot(const Vec3 &) -> float' signature was removed or changed
  ! Field 'Vec3.z_' was removed
```

---

## `--check-compat` — Fail on Breaking Changes

```bash
tsujikiri -i project.input.yml --target luabridge3 src/bindings.cpp \
          -m api.manifest.json --check-compat
```

When `--check-compat` is passed:
- If breaking changes are detected: exit with code `1`; the manifest is **not** saved (the old manifest is preserved)
- If only additive changes: exit `0`; manifest is saved normally
- If no changes: exit `0`; manifest is unchanged

Use `--check-compat` in CI to block merges that would break existing Lua scripts.

---

## Semantic Versioning Integration

If the existing manifest has a `"version"` field that is a valid `MAJOR.MINOR.PATCH` semver string, tsujikiri suggests a bumped version:

| Change type | Bump |
|------------|------|
| Breaking changes present | Bump `MAJOR`, reset `MINOR` and `PATCH` to 0 |
| Only additive changes | Bump `MINOR`, reset `PATCH` to 0 |
| No changes | Version unchanged |

```
INFO: Suggested semver bump: 1.2.0 -> 2.0.0
```

The suggestion is printed to stderr. The manifest is saved with the suggested version automatically.

To seed the initial version, manually edit the saved manifest JSON and set `"version": "1.0.0"`. On the next run, tsujikiri will pick it up and suggest bumps from there.

---

## `--embed-version` — Version Hash in Generated Code

```bash
tsujikiri -i project.input.yml --target luabridge3 src/bindings.cpp \
          -m api.manifest.json --embed-version
```

When `--embed-version` is passed (or `embed_version: true` in `generation`), the api version number is embedded in the generated code.

**luabridge3 output:**
```cpp
static constexpr const char* k_myproject_api_version = "1.7.3";

const char* get_myproject_api_version()
{
    return k_myproject_api_version;
}

// Inside register_myproject():
.addFunction("get_api_version", +[] () -> const char* { return k_myproject_api_version; })
```

**luals output:**
```lua
---@return string
function myproject.get_api_version() end
```

**Runtime version check (Lua side):**
```lua
local function parse(v)
    local a, b, c = v:match("(%d+)%.(%d+)%.(%d+)")
    return a*1e6 + b*1e3 + c
end

local expected = "1.7.3"
local actual = myproject.get_api_version()
if parse(actual) ~= parse(expected) then
    error(("API version mismatch: expected %s got %s"):format(expected, actual))
end
```

This lets you detect at runtime when a Lua script was compiled against a different API version than the loaded library provides.

---

## Complete CI Workflow Example

The following shell script demonstrates a full versioning workflow in a CI pipeline:

```bash
#!/bin/bash
set -euo pipefail

INPUT="project.input.yml"
MANIFEST="api.manifest.json"
OUTPUT="src/lua_bindings.cpp"

echo "--- Generating bindings ---"
tsujikiri -i "$INPUT" --target luabridge3 "$OUTPUT" -m "$MANIFEST" \
  --check-compat \
  --embed-version

# If we get here, either:
#   a) No manifest existed yet (first run), or
#   b) Changes were only additive (MINOR bump applied), or
#   c) No changes at all

echo "--- Generating LuaLS annotations ---"
tsujikiri -i "$INPUT" --target luals "types/myproject.lua"

echo "--- Committing updated bindings ---"
git add "$OUTPUT" "$MANIFEST" "types/myproject.lua"
git diff --staged --quiet || git commit -m "chore: update generated bindings"
```

If the C++ API has breaking changes, `tsujikiri` exits with code 1 at the `--check-compat` step, the script stops (due to `set -e`), and CI marks the build as failed.

**Sample manifest after a breaking change is resolved and MAJOR bumped:**

```text
{
  "module": "myproject",
  "version": "2.0.0",
  "api": {
    "classes": [ ... ],
    "functions": [ ... ],
    "enums": [ ... ]
  }
}
```

---

## See Also

- [Getting Started](getting-started.md) — `--manifest-file`, `--check-compat`, `--embed-version` CLI flags
- [Input File Reference](input-file-reference.md) — `generation.embed_version` config key
- [Output Formats](output-formats.md) — how the API version hash appears in luabridge3 and luals templates
