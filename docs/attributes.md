# C++ Attribute System

[Home](index.md) > Attributes

tsujikiri can read C++17 `[[namespace::name]]` attributes directly from C++ source files and use them to control binding generation — skipping declarations, keeping them, or renaming them.

---

## How Attributes Are Detected

libclang does not expose custom-namespace attributes as cursor children (only standard C++ attributes like `[[nodiscard]]` are cursor-accessible). tsujikiri works around this by scanning the **source text** of each declaration.

For each cursor, tsujikiri looks in three locations:

1. **Trailing same-line:** the rest of the line after the cursor's spelling location
2. **Leading same-line:** the portion of the line before the cursor that ends with `[[...]]`
3. **Preceding line:** the full text of the line immediately above the cursor (skipping lines that end with `;`, `{`, or `}`)

Source files are read once per parse and cached. The scanner extracts all `[[...]]` blocks it finds and parses their contents.

**Multi-attribute blocks:** `[[a::x, b::y]]` yields two entries: `a::x` and `b::y`.

**Attribute arguments:** `[[tsujikiri::rename("newName")]]` — the argument `"newName"` is extracted from the first quoted string.

### What the Scanner Looks For

Attributes must use the `[[double-bracket]]` C++17 syntax. GNU-style `__attribute__((x))` annotations are not detected.

---

## Built-in Attributes

The following attributes are always active — no configuration required.

### `[[tsujikiri::skip]]`

Sets `emit=False` on the annotated node. Applies to:
- Classes
- Methods
- Fields
- Constructors
- Enums and enum values
- Free functions

The attribute is processed **after** the FilterEngine runs, so it can suppress a node that the filter config would include.

```cpp
namespace mylib {

[[tsujikiri::skip]]
class InternalHelper { ... };   // suppressed, never appears in bindings

class Shape {
public:
    // This method is always hidden, regardless of filter config
    [[tsujikiri::skip]]
    void internalOptimize();

    // Normal methods appear in the binding
    double area() const;
};

}
```

### `[[tsujikiri::keep]]`

Sets `emit=True` on the annotated node. This is most useful for re-enabling a node that the filter config suppressed.

```cpp
namespace mylib {

class Shape {
public:
    // Globally suppressed by filter: methods.global_blacklist with pattern "operator.*"
    // But we explicitly want this one exposed:
    [[tsujikiri::keep]]
    bool operator==(const Shape& other) const;

    // This operator stays suppressed (no [[keep]])
    bool operator<(const Shape& other) const;
};

}
```

When `[[tsujikiri::skip]]` and `[[tsujikiri::keep]]` both appear on the same line (e.g. `[[tsujikiri::skip, tsujikiri::keep]]`), the **last one processed wins** — they are applied in attribute list order.

### `[[tsujikiri::rename("newName")]]`

Sets the `rename` field on the annotated node to the first quoted string argument. Works on:
- Classes → changes the binding name
- Methods → changes the binding name
- Fields → changes the binding name

```cpp
namespace mylib {

[[tsujikiri::rename("Vector3")]]
class Vec3 {
public:
    [[tsujikiri::rename("length_sq")]]
    float getLengthSquared() const;

    [[tsujikiri::rename("x")]]
    float x_ = 0.0f;
};

}
```

With the config:
```yaml
filters:
  namespaces: ["mylib"]
  constructors:
    include: false
```

The generated binding will use `Vector3`, `length_sq`, and `x` as the names — even though no transforms are configured. The attribute-based rename is applied in the same pass as `[[skip]]` and `[[keep]]`.

### `[[tsujikiri::readonly]]`

Forces a field to be exposed as read-only, even if the C++ field is not `const`.

Applies to: **Fields**.

```cpp
class Circle {
public:
    // Exposed as read-only even though the field is mutable in C++:
    [[tsujikiri::readonly]]
    double radius_ = 1.0;
};
```

In `luabridge3`, read-only fields are emitted with a `nullptr` setter:
```cpp
.addProperty("radius_", &mylib::Circle::radius_, nullptr)
```

In `pybind11`, they use `.def_readonly(...)` instead of `.def_readwrite(...)`.

### `[[tsujikiri::thread_safe]]`

Marks a method or free function as thread-safe, setting `allow_thread=True` on the IR node. This is a template hint — the built-in formats do not use it directly, but custom formats can use it to emit GIL-release annotations or other thread safety wrappers.

Applies to: **Methods**, **Free functions**.

```cpp
class Processor {
public:
    [[tsujikiri::thread_safe]]
    void process(const float* data, int count);
};
```

### `[[tsujikiri::doc("text")]]`

Attaches a documentation string to a node. The text is available as `node.doc` in Jinja2 templates. Both `pybind11` and `pyi` built-in formats use this to emit Python docstrings.

Applies to: **Classes**, **Methods**, **Constructors**, **Fields**, **Enums**, **Enum values**, **Free functions**.

```cpp
/// [[tsujikiri::doc("A 2D geometric shape.")]]
class Shape {
public:
    /// [[tsujikiri::doc("Compute the area of the shape.")]]
    virtual double area() const = 0;

    /// [[tsujikiri::doc("The shape's scale factor.")]]
    [[tsujikiri::readonly]]
    double scale_ = 1.0;
};
```

Generated pybind11 output:
```cpp
py::class_<mylib::Shape>(m, "Shape", "A 2D geometric shape.")
    .def("area", &mylib::Shape::area, "Compute the area of the shape.")
    .def_readonly("scale_", &mylib::Shape::scale_, "The shape's scale factor.");
```

### `[[tsujikiri::rename_argument("old", "new")]]`

Renames a parameter by name on the annotated method or function. Equivalent to a `modify_argument` transform but expressed in the C++ source.

Applies to: **Methods**, **Free functions**.

```cpp
class Circle {
public:
    // Expose the parameter as "radius" instead of the C++ name "r"
    [[tsujikiri::rename_argument("r", "radius")]]
    void setRadius(double r);
};
```

### `[[tsujikiri::type_map("CppType", "TargetType")]]`

Overrides the type of a matching parameter or return value on the annotated method or function. Also applies to fields when the field's type matches. Equivalent to a targeted `add_type_mapping` but scoped to a single declaration.

Applies to: **Methods**, **Free functions**, **Fields**.

```cpp
class Processor {
public:
    // Map juce::String to std::string only for this method's signature:
    [[tsujikiri::type_map("juce::String", "std::string")]]
    void setName(juce::String name);
};
```

---

## Custom Attribute Handlers

Register custom attribute names by adding `attributes.handlers` to your `.input.yml`. This maps an attribute name (including namespace) to one of three actions.

```yaml
attributes:
  handlers:
    "mygame::no_export": skip     # [[mygame::no_export]] → suppress
    "mygame::export": keep        # [[mygame::export]] → include (overrides filters)
    "mygame::bind_as": rename     # [[mygame::bind_as("newName")]] → rename
    "api::internal": skip         # supports any namespace
```

### Available Actions

| Action | Effect |
|--------|--------|
| `skip` | Sets `emit=False` on the annotated node |
| `keep` | Sets `emit=True` on the annotated node |
| `rename` | Sets `rename` to the first quoted string argument |

Custom handlers work identically to built-in ones. They extend the built-in set — registering `"tsujikiri::skip"` would be redundant, but registering `"mygame::skip"` adds a project-specific alias.

### Real-World Example

Given this C++ header:

```cpp
// game_api.hpp
#pragma once
#include <string>

namespace game {

// Attribute namespaces must be declared with [[using]] in the compiler
// but tsujikiri's scanner doesn't require this
class [[mygame::export]] AudioEngine {
public:
    [[mygame::export]]
    AudioEngine() = default;

    [[mygame::export]]
    void play(const std::string& soundName);

    [[mygame::no_export]]
    void internalUpdate(float dt);   // only called from the engine loop

    [[mygame::bind_as("volume")]]
    float masterVolume = 1.0f;

    float internalBuffer[256];       // no attribute = excluded by field filter
};

[[mygame::no_export]]
class AudioDriverImpl { ... };       // implementation detail

} // namespace game
```

And this config:

```yaml
# game.input.yml
source:
  path: game_api.hpp
  parse_args: ["-std=c++17"]

filters:
  namespaces: ["game"]
  constructors:
    include: true
  fields:
    global_blacklist:
      - "internalBuffer"

attributes:
  handlers:
    "mygame::no_export": skip
    "mygame::export": keep
    "mygame::bind_as": rename
```

Result:
- `AudioEngine` is included (`[[mygame::export]]` → `emit=True`)
- `AudioDriverImpl` is excluded (`[[mygame::no_export]]` → `emit=False`)
- `play` is included (attribute `keep`)
- `internalUpdate` is excluded (attribute `skip`)
- `masterVolume` field is renamed to `volume` (attribute `rename`)
- `internalBuffer` is excluded by the field filter

---

## Attributes vs YAML Filters and Transforms

Both the attribute system and YAML config can control which declarations are included and how they're named. Choosing between them is a matter of **where the decision belongs**:

| Use attributes when… | Use YAML filters/transforms when… |
|----------------------|-----------------------------------|
| The decision is made by the C++ author | The decision is made by the binding author |
| You control the header and can annotate it | You do not modify the header (third-party library) |
| The policy applies to every project that uses the header | The policy is specific to this binding configuration |
| You want the binding intent visible in the C++ source | You want binding config separate from C++ code |

**Practical guideline:** For your own library headers, annotate with `[[tsujikiri::skip]]` and `[[tsujikiri::rename(...)]]` to express the binding intent alongside the C++ API. For third-party headers you cannot modify, use YAML `filters` and `transforms` exclusively.

---

## Attribute Placement Rules and Gotchas

### Scanning Scope

The scanner checks three locations (in order) and stops when it finds attributes:

1. **Trailing same-line text** — any `[[...]]` after the identifier on the same line
2. **Leading same-line text** — any `[[...]]` at the start of the same line, before the identifier
3. **Preceding line text** — the full previous line if it doesn't end with `;`, `{`, or `}`

### What Is Skipped

The preceding-line scan skips lines that end with:
- `;` — statement separator (previous statement, not an attribute)
- `{` — opening brace (start of a block)
- `}` — closing brace (end of a block)

This prevents accidentally picking up attributes from sibling declarations.

### Line Comments

Content inside `//` line comments is not filtered out by the scanner (the raw line text is searched). Avoid placing `[[...]]` attribute-like strings inside line comments if you don't want them detected.

### Only Double-Bracket Style

Only `[[namespace::name]]` and `[[namespace::name("arg")]]` syntax is detected. GNU `__attribute__((x))`, MSVC `__declspec(x)`, and pragma annotations are not supported.

### Inner Classes

Attributes on inner class declarations are detected. The scanner looks at the cursor's location in the source, so inner classes at any nesting depth are handled correctly.

---

## See Also

- [Filtering](filtering.md) — attributes are processed after FilterEngine; `[[keep]]` can override filter suppressions
- [Transforms](transforms.md) — transforms run after attributes; can further modify `emit` and `rename` fields
- [Input File Reference](input-file-reference.md) — `attributes.handlers` configuration key
