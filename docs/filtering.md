# Filtering System

[Home](index.md) > Filtering

The filtering system controls which C++ declarations are included in the binding output. Filters run after parsing and before attribute processing and transforms.

---

## How Filtering Works

Filtering does **not** delete nodes from the IR. Instead, it sets `emit=False` on nodes that should be excluded. The generator skips `emit=False` nodes when building output.

This non-destructive approach has an important consequence: **transforms can re-enable suppressed nodes** by setting `emit=True`, and the [attribute system](attributes.md) can override filter decisions using `[[tsujikiri::keep]]`.

### Processing Order

For each class in the IR, the FilterEngine applies rules in this order:

1. **Source exclusion** — exclude by source file glob pattern
2. **Internal suppression** — silent suppression (no log message)
3. **Blacklist matching** — explicit exclusion
4. **Whitelist matching** — explicit inclusion (if whitelist is non-empty)
5. **Method filtering** — global blacklist + per-class blacklist
6. **Constructor filtering** — master include switch + signature filter
7. **Field filtering** — global blacklist + per-class blacklist
8. **Enum filtering** — whitelist/blacklist
9. **Inner class filtering** — recursive application of all rules

---

## Filter Patterns

Most filter fields accept either a plain string or a pattern object:

```yaml
# Plain string — exact match on the declaration name
- "MyClass"

# Pattern object — Python re.fullmatch regex
- pattern: ".*Impl$"
  is_regex: true
```

**Plain string:** matches only when the full name equals the string.

**Regex (`is_regex: true`):** uses Python `re.fullmatch`, which must match the entire name. Anchors (`^`, `$`) are implicit. Common patterns:

| Pattern | Matches |
|---------|---------|
| `".*Impl$"` | Any name ending in `Impl` |
| `".*Detail.*"` | Any name containing `Detail` |
| `"get.*"` | Any name starting with `get` |
| `"operator.*"` | Any C++ operator overload |

---

## `namespaces` — Namespace Restriction

```yaml
filters:
  namespaces: ["myproject", "myproject::utils"]
```

- **Empty list (default):** all namespaces in the header are included.
- **Non-empty list:** only classes, functions, and enums declared in the listed namespaces are included. Namespaces are matched by exact string against the fully-qualified namespace path.

**Example — restrict to a single namespace:**

```yaml
filters:
  namespaces: ["mylib"]
```

Given a header with classes in `mylib`, `mylib::internal`, and `thirdparty` namespaces, only classes in `mylib` are included (not `mylib::internal`).

---

## `sources.exclude_patterns` — Source File Exclusion

```yaml
filters:
  sources:
    exclude_patterns:
      - "*.mm"           # Exclude Objective-C++ implementation files
      - "*/platform/*"   # Exclude any file under a platform/ directory
```

Uses `fnmatch`-style glob patterns matched against the absolute source file path of each declaration. Declarations from matching files have `emit=False` set.

**Common use case:** A cross-platform header `#include`s a platform `.hpp` or `.mm` that transitively exposes declarations you do not want in the bindings. Exclude them by pattern instead of listing every class manually.

---

## `classes` — Class Filtering

The `classes` section has three independent lists: `whitelist`, `blacklist`, and `internal`.

```yaml
filters:
  classes:
    whitelist:
      - "Vec3"
      - "Matrix4"
      - pattern: "^Shape.*"
        is_regex: true
    blacklist:
      - "PrivateImpl"
      - pattern: ".*Detail$"
        is_regex: true
    internal:
      - "BaseHelper"
      - pattern: ".*Mixin$"
        is_regex: true
```

### `whitelist`

- **Empty (default):** all classes pass the whitelist check.
- **Non-empty:** only classes matching at least one entry are included.

Use the whitelist when you want to explicitly enumerate the public API surface. Any class not in the list is suppressed, even if it would otherwise pass other checks.

### `blacklist`

Classes matching any entry are suppressed, **regardless of whitelist membership**. The blacklist takes precedence over the whitelist.

```yaml
# Include all classes EXCEPT those ending in Impl or containing Detail
filters:
  classes:
    blacklist:
      - pattern: ".*Impl$"
        is_regex: true
      - pattern: ".*Detail.*"
        is_regex: true
```

### `internal`

Functionally identical to `blacklist` (sets `emit=False`), but the intent is different: `internal` is for base classes or implementation helpers that should never be exposed but are referenced by public classes. The generator does not warn about these suppressions.

```yaml
filters:
  classes:
    whitelist: ["Circle", "Rectangle"]
    internal: ["ShapeBase"]  # ShapeBase is a base class; suppress silently
```

### Interaction Between Lists

1. If `blacklist` matches → suppressed (no further checks)
2. If `internal` matches → suppressed (no further checks)
3. If `whitelist` is non-empty and the class does NOT match → suppressed
4. Otherwise → included

---

## `methods` — Method Filtering

```yaml
filters:
  methods:
    global_blacklist:
      - pattern: "operator.*"
        is_regex: true
      - "internalReset"
    per_class:
      Calculator:
        - "legacyAdd"
        - pattern: "debug.*"
          is_regex: true
      Shape:
        - "protectedHelper"
```

### `global_blacklist`

Applied to every class. Methods matching any entry have `emit=False` set across all classes. This is the right place to suppress operator overloads, deprecated APIs, or naming patterns that should never be exposed.

**Example — suppress all C++ operators:**
```yaml
filters:
  methods:
    global_blacklist:
      - pattern: "operator.*"
        is_regex: true
```

### `per_class`

A mapping from class name to a list of method patterns. The class name must match exactly (no regex support for the class key; only the method patterns support regex).

```yaml
filters:
  methods:
    per_class:
      MyClass:
        - "internalHelper"
        - pattern: "_.*"        # suppress methods starting with underscore
          is_regex: true
```

---

## `fields` — Field Filtering

```yaml
filters:
  fields:
    global_blacklist:
      - pattern: "pimpl_"
      - pattern: ".*_raw_ptr$"
        is_regex: true
    per_class:
      MyClass:
        - "privateState_"
```

Same structure as `methods`: a `global_blacklist` applied to all classes and a `per_class` mapping for targeted suppression.

**Example — hide implementation detail fields globally:**
```yaml
filters:
  fields:
    global_blacklist:
      - pattern: ".*_$"         # trailing underscore = internal convention
        is_regex: true
```

Note: `const` fields are always emitted as read-only properties; filtering still applies to them.

---

## `constructors` — Constructor Filtering

```yaml
filters:
  constructors:
    include: true
    signatures: []
```

### `include`

A master boolean switch.

- `false` (default): no constructors are emitted for any class.
- `true`: constructors are included (subject to `signatures` filtering).

### `signatures`

A list of parameter type signatures. Each signature is a comma-separated string of parameter type spellings, joined with `, `.

- **Empty list (default):** all constructors are included (when `include: true`).
- **Non-empty list:** only constructors whose parameter list exactly matches one of the listed signatures are included.

```yaml
filters:
  constructors:
    include: true
    signatures:
      - ""                  # Default constructor (no parameters)
      - "int"               # Single int parameter
      - "float, float"      # Two float parameters
```

**Signature format:** join the C++ type spellings (as libclang sees them) with `, `. For a constructor `MyClass(const char* name, int id)`, the signature is `"const char *, int"`.

---

## `functions` — Free Function Filtering

```yaml
filters:
  functions:
    whitelist:
      - "computeArea"
      - "reset"
    blacklist:
      - pattern: "detail_.*"
        is_regex: true
```

Follows the same whitelist/blacklist semantics as `classes`:
- Empty `whitelist` = include all free functions in the listed namespaces
- Non-empty `whitelist` = include only matching functions
- `blacklist` always excludes, regardless of whitelist

---

## `enums` — Enum Filtering

```yaml
filters:
  enums:
    whitelist: []
    blacklist:
      - "InternalState"
      - pattern: ".*Private.*"
        is_regex: true
```

Same whitelist/blacklist semantics. Applies to top-level enums in the namespace and to enums declared inside classes.

---

## Combined Real-World Example

The following configuration uses all filter types together against the `combined.hpp` fixture (`Shape`, `Circle`, `Calculator`, `Color` enum, `computeArea` free function):

```yaml
# combined_filtered.input.yml
source:
  path: combined.hpp
  parse_args: ["-std=c++17"]

filters:
  # Only process the mylib namespace
  namespaces: ["mylib"]

  # Exclude macOS Objective-C++ files if present
  sources:
    exclude_patterns: ["*.mm"]

  classes:
    # Only expose these three classes
    whitelist:
      - "Shape"
      - "Circle"
      - "Calculator"
    # Suppress anything that looks like a detail or helper
    blacklist:
      - pattern: ".*Detail$"
        is_regex: true
    # Silently suppress the base class if it were internal
    internal: []

  methods:
    # Remove all operator overloads from every class
    global_blacklist:
      - pattern: "operator.*"
        is_regex: true
    # Remove internal-only methods from Calculator specifically
    per_class:
      Calculator:
        - pattern: "debug.*"
          is_regex: true

  fields:
    # Hide fields that follow the trailing-underscore convention globally
    # (we'll rename them via transforms instead)
    global_blacklist: []

  constructors:
    # Include constructors (both default and parameterised)
    include: true
    signatures: []  # All constructors included

  functions:
    # Only expose computeArea, not any helpers
    whitelist:
      - "computeArea"
    blacklist:
      - pattern: ".*helper.*"
        is_regex: true

  enums:
    # Include Color enum, exclude any internal state enums
    whitelist: ["Color"]
    blacklist: []
```

---

## See Also

- [Transforms](transforms.md) — run after filtering; can re-enable suppressed nodes
- [Attributes](attributes.md) — `[[tsujikiri::skip]]` and `[[tsujikiri::keep]]` override filter decisions
- [Input File Reference](input-file-reference.md) — all YAML keys in context
