# API Manifest and Versioning

[Home](index.md) > Manifest and Versioning

tsujikiri can track the binding surface (API) of your C++ headers over time using a **manifest** — a JSON snapshot of what is currently exposed. Two manifests can be compared to detect breaking changes and suggest a semantic version bump.

---

## What the Manifest Captures

The manifest is computed from the **filtered and transformed IR**, after all `emit=False` nodes have been removed. It records the **binding-visible** surface — names after any renames, types before format-level remapping:

- **Classes**: their binding name, all emitted constructor signatures, all emitted methods (name, parameters, return type, is_static), all emitted fields (name, type, is_const), and nested enums
- **Free functions**: name, parameter types, return type
- **Top-level enums**: name and all value names with their integer values

The manifest does **not** capture:
- Suppressed nodes (`emit=False`)
- Template-level type remapping (from `type_mappings` in `.output.yml`)
- Code injections
- Comments or generation settings

### Deterministic UID

The `uid` field is a SHA-256 hash of the `api` section serialised with sorted keys. The same C++ surface always produces the same uid, regardless of file ordering or timestamp.

---

## Manifest JSON Structure

```json
{
  "module": "myproject",
  "version": "1.2.0",
  "uid": "3a8fe2d4c8b1f9e7d2c3a1b0f9e73a8f...64chars",
  "api": {
    "classes": [
      {
        "name": "Vec3",
        "constructors": [
          [],
          ["float", "float", "float"]
        ],
        "methods": [
          {
            "name": "length",
            "params": [],
            "return_type": "float",
            "is_static": false
          },
          {
            "name": "dot",
            "params": ["const Vec3 &"],
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
  }
}
```

> **Tip:** Commit the manifest JSON file to version control alongside the generated bindings. This gives you a complete history of API changes.

---

## Saving and Loading a Manifest

```bash
# First run — generate bindings and save the initial manifest
tsujikiri -i project.input.yml -o luabridge3 -O src/bindings.cpp \
          -M api.manifest.json

# Subsequent runs — compare with existing manifest, then save updated one
tsujikiri -i project.input.yml -o luabridge3 -O src/bindings.cpp \
          -M api.manifest.json
```

When `-M FILE` is passed:
- If `FILE` does **not** exist: generate bindings normally, then save the manifest.
- If `FILE` **does** exist and the uid differs: compare the two manifests, print a report, then save the new manifest.
- If `FILE` exists and uid is **identical**: no changes; keep the existing manifest unchanged.

---

## Comparing Manifests — Breaking vs Additive

When the manifest changes, tsujikiri classifies each difference:

### Breaking Changes (scripts that use the old surface may break)

| What changed | Example |
|-------------|---------|
| Class removed | `Vec3` was removed |
| Constructor removed | `Vec3()` was removed |
| Method signature removed or changed | `Vec3.length() → float` was removed or changed |
| Field removed | `Vec3.x_` was removed |
| Field type changed | `Vec3.x_`: `float` → `double` |
| Field const qualifier changed | `Vec3.x_` const: `false` → `true` |
| Enum removed | `Color` was removed |
| Enum value removed | `Color.Red` was removed |
| Enum value integer changed | `Color.Red`: 0 → 1 |

### Additive Changes (existing scripts continue to work)

| What changed | Example |
|-------------|---------|
| Class added | `Matrix4` was added |
| Constructor overload added | `Vec3(float, float, float)` was added |
| Method added | `Vec3.normalize() → Vec3` was added |
| Method overload added | `add(double, double) → double` overload was added |
| Field added | `Vec3.w_` was added |
| Enum added | `BlendMode` was added |
| Enum value added | `Color.Alpha` was added |

### Stderr Output

```
WARNING: Additive API changes:
  + Class 'Matrix4' was added
  + Method 'Vec3.normalize() -> Vec3' was added

ERROR: Breaking API changes detected:
  ! Method 'Vec3.dot(const Vec3 &) -> float' signature was removed or changed
  ! Field 'Vec3.z_' was removed
```

---

## `--check-compat` — Fail on Breaking Changes

```bash
tsujikiri -i project.input.yml -o luabridge3 -O src/bindings.cpp \
          -M api.manifest.json --check-compat
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
tsujikiri -i project.input.yml -o luabridge3 -O src/bindings.cpp \
          -M api.manifest.json --embed-version
```

When `--embed-version` is passed (or `embed_version: true` in `generation`), the SHA-256 uid is embedded in the generated code.

**luabridge3 output:**
```cpp
static constexpr const char* k_myproject_api_version = "3a8fe2d4c8b1f9...";

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
local expected = "3a8fe2d4c8b1f9..."
local actual = myproject.get_api_version()
if actual ~= expected then
    error("API version mismatch: expected " .. expected .. " got " .. actual)
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
tsujikiri \
  -i "$INPUT" \
  -o luabridge3 \
  -O "$OUTPUT" \
  -M "$MANIFEST" \
  --check-compat \
  --embed-version

# If we get here, either:
#   a) No manifest existed yet (first run), or
#   b) Changes were only additive (MINOR bump applied), or
#   c) No changes at all

echo "--- Generating LuaLS annotations ---"
tsujikiri \
  -i "$INPUT" \
  -o luals \
  -O "types/myproject.lua"

echo "--- Committing updated bindings ---"
git add "$OUTPUT" "$MANIFEST" "types/myproject.lua"
git diff --staged --quiet || git commit -m "chore: update generated bindings"
```

If the C++ API has breaking changes, `tsujikiri` exits with code 1 at the `--check-compat` step, the script stops (due to `set -e`), and CI marks the build as failed.

**Sample manifest after a breaking change is resolved and MAJOR bumped:**

```json
{
  "module": "myproject",
  "version": "2.0.0",
  "uid": "9f1a3d7b...newuid",
  "api": {
    "classes": [ ... ],
    "functions": [ ... ],
    "enums": [ ... ]
  }
}
```

---

## See Also

- [Getting Started](getting-started.md) — `-M`, `--check-compat`, `--embed-version` CLI flags
- [Input File Reference](input-file-reference.md) — `generation.embed_version` config key
- [Output Formats](output-formats.md) — how the API version hash appears in luabridge3 and luals templates
