# Transform Stages

[Home](index.md) > Transforms

Transforms run **after** filtering and attribute processing, and **before** code generation. They mutate the Intermediate Representation (IR) in-place: renaming declarations, suppressing nodes, injecting synthetic methods, remapping types, and more.

---

## How the Pipeline Works

The `transforms` list in your input file is a sequence of stages. Each stage is applied to the full IR in order. Later stages see the IR as modified by all earlier stages.

```yaml
transforms:
  - stage: suppress_method      # ← runs first
    class: "*"
    pattern: "operator.*"
    is_regex: true

  - stage: rename_method        # ← runs second, sees suppressed methods still in IR
    class: "*"
    from: "getValue"
    to: "get"
```

Key properties:
- Transforms **can re-enable nodes suppressed by filters** (set `emit=True` explicitly).
- Transforms **see all IR nodes** regardless of `emit` flag — they decide whether to act on them.
- Stages run on the merged module (all sources combined).

---

## Pattern Matching in Transforms

Many stages accept pattern fields for class and method names:

| Field | Type | Matches |
|-------|------|---------|
| Plain string | `"MyClass"` | Exact name match only |
| `"*"` wildcard | `"*"` | All declarations of that type |
| Regex | `is_regex: true` | Python `re.fullmatch` against the name |

Class-level stages use `class_is_regex: true` for the class pattern and `is_regex: true` (or `method_is_regex: true`) for method patterns:

```yaml
- stage: rename_method
  class: ".*Service$"    # match all classes ending in Service
  class_is_regex: true
  from: "get.*"          # match methods starting with get
  is_regex: true
  to: "fetch"            # rename all of them to "fetch"
```

---

## Stage Reference

### Class and Method Stages

| Stage | Purpose | Required Keys |
|-------|---------|---------------|
| `rename_method` | Change the binding name of a method | `class`, `from`, `to` |
| `rename_class` | Change the binding name of a class | `from`, `to` |
| `suppress_method` | Set `emit=False` on matching methods | `class`, `pattern` |
| `suppress_class` | Set `emit=False` on matching classes | `pattern` |
| `inject_method` | Append a synthetic method to a class | `class`, `name` |
| `inject_constructor` | Append a synthetic constructor to a class | `class` |
| `suppress_base` | Hide a base class from the binding output | `class`, `base` |
| `add_type_mapping` | Rewrite a C++ type spelling globally | `from`, `to` |
| `modify_method` | Multi-field edit on matching methods | `class`, `method` |
| `modify_argument` | Edit a single parameter of a method | `class`, `method`, `argument` |
| `modify_field` | Edit a class field | `class`, `field` |
| `modify_constructor` | Remove a constructor by signature | `class`, `signature` |
| `remove_overload` | Remove one overload of a method | `class`, `method`, `signature` |
| `inject_code` | Insert raw code at a position in output | `target`, `position`, `code` |
| `set_type_hint` | Override class-level type trait metadata | `class` |

### Enum Stages

| Stage | Purpose | Required Keys |
|-------|---------|---------------|
| `rename_enum` | Change the binding name of an enum | `from`, `to` |
| `rename_enum_value` | Change the binding name of an enum value | `enum`, `from`, `to` |
| `suppress_enum` | Set `emit=False` on matching enums | `pattern` |
| `suppress_enum_value` | Set `emit=False` on matching enum values | `enum`, `pattern` |
| `modify_enum` | Rename or suppress an enum | `enum` |

### Free Function Stages

| Stage | Purpose | Required Keys |
|-------|---------|---------------|
| `rename_function` | Change the binding name of a free function | `from`, `to` |
| `suppress_function` | Set `emit=False` on matching free functions | `pattern` |
| `modify_function` | Multi-field edit on matching free functions | `function` |
| `inject_function` | Append a synthetic free function to the module | `name` |

---

## `rename_method`

Changes the binding-visible name of a method. The original C++ method name (`spelling`) is preserved so the template can still emit `&Class::spelling`. Only the name shown in the output changes.

```yaml
- stage: rename_method
  class: MyClass          # plain name, '*', or regex with class_is_regex: true
  from: getValueForKey    # plain name or regex with is_regex: true
  to: get
  is_regex: false         # optional, default false
  class_is_regex: false   # optional, default false
```

**All keys:**

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `class` | string | `"*"` | Class name to target |
| `class_is_regex` | bool | `false` | Treat `class` as regex |
| `from` | string | — | Method name to match (required) |
| `to` | string | — | New binding name (required) |
| `is_regex` | bool | `false` | Treat `from` as regex |

**Example — rename a specific getter to a shorter name:**
```yaml
transforms:
  - stage: rename_method
    class: Calculator
    from: getValue
    to: get
```

Before: Lua sees `calc:get_value()` (after camelToSnake). After: Lua sees `calc:get()`.

**Example — rename all `get*` prefixed methods on all classes using regex:**
```yaml
transforms:
  - stage: rename_method
    class: "*"
    from: "get(.*)"
    to: "\\1"           # strips the "get" prefix
    is_regex: true
```

This strips `get` from any method whose name starts with it: `getRadius` → `Radius` (then camelToSnake in output: `radius`).

---

## `rename_class`

Changes the binding-visible name of a class. The qualified C++ name is preserved for template use (e.g. `beginClass<mylib::Vec3>`). Only the string registered in the binding changes.

```yaml
- stage: rename_class
  from: InternalVec3
  to: Vec3
  is_regex: false       # optional
```

**All keys:**

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `from` | string | — | Class name to match (required) |
| `to` | string | — | New binding name (required) |
| `is_regex` | bool | `false` | Treat `from` as regex |

**Example — expose an internal helper class under a public name:**
```yaml
transforms:
  - stage: rename_class
    from: ShapeImpl
    to: Shape
```

**Example — strip a common prefix from all classes using regex:**
```yaml
transforms:
  - stage: rename_class
    from: "My(.*)"
    to: "\\1"
    is_regex: true
```

`MyVec3` → `Vec3`, `MyMatrix4` → `Matrix4`, etc.

---

## `suppress_method`

Sets `emit=False` on matching methods. The method stays in the IR (transforms can still see it) but the generator will skip it.

```yaml
- stage: suppress_method
  class: "*"              # all classes
  pattern: "operator.*"   # match any operator overload
  is_regex: true
  class_is_regex: false   # optional
```

**All keys:**

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `class` | string | `"*"` | Class name to target |
| `class_is_regex` | bool | `false` | Treat `class` as regex |
| `pattern` | string | — | Method pattern to match (required) |
| `is_regex` | bool | `false` | Treat `pattern` as regex |

**Example — globally suppress all operator overloads:**
```yaml
transforms:
  - stage: suppress_method
    class: "*"
    pattern: "operator.*"
    is_regex: true
```

**Example — suppress debug methods on one class:**
```yaml
transforms:
  - stage: suppress_method
    class: Calculator
    pattern: "debugDump"
```

---

## `suppress_class`

Sets `emit=False` on matching classes. Applies to top-level classes and nested inner classes.

```yaml
- stage: suppress_class
  pattern: ".*Detail$"
  is_regex: true
```

**All keys:**

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `pattern` | string | — | Class name pattern (required) |
| `is_regex` | bool | `false` | Treat `pattern` as regex |

**Example — suppress implementation detail classes:**
```yaml
transforms:
  - stage: suppress_class
    pattern: ".*Detail$"
    is_regex: true
```

**Example — suppress a specific class by name:**
```yaml
transforms:
  - stage: suppress_class
    pattern: "Unused"
```

---

## `inject_method`

Appends a synthetic `IRMethod` to a class. The method appears in the output exactly as specified. The caller is responsible for ensuring the corresponding C++ symbol exists (or providing a `wrapper_code` via a subsequent `modify_method` stage).

```yaml
- stage: inject_method
  class: MyClass
  name: create
  return_type: "MyClass*"
  parameters:
    - name: value
      type: int
    - name: label
      type: "const char *"
  is_static: true
```

**All keys:**

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `class` | string | — | Target class name (required; no regex, no wildcard) |
| `name` | string | — | Name of the injected method (required) |
| `return_type` | string | `"void"` | C++ return type spelling |
| `parameters` | list | `[]` | Each item has `name` (string) and `type` (string) |
| `is_static` | bool | `false` | Whether to register as a static method |

**Example — inject a static factory method not present in the original C++ API:**
```yaml
transforms:
  - stage: inject_method
    class: Circle
    name: unit
    return_type: "Circle"
    parameters: []
    is_static: true
```

This injects a method named `unit` into `Circle`. The generated binding will call `&Circle::unit`, so this function must exist in your C++ code (or be provided via `wrapper_code`).

> **Tip:** Combine `inject_method` with `modify_method` to provide a `wrapper_code` for the injected method when no real C++ function exists.

---

## `add_type_mapping`

Rewrites a C++ type spelling across the entire module: in method return types, parameter types, field types, and free function signatures. This affects the IR, so all subsequent stages and the generator see the remapped type.

```yaml
- stage: add_type_mapping
  from: "juce::String"
  to: "std::string"
```

**All keys:**

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `from` | string | — | C++ type spelling to match (exact; required) |
| `to` | string | — | Replacement type spelling (required) |

**Example — map a library-specific string type to `std::string`:**
```yaml
transforms:
  - stage: add_type_mapping
    from: "juce::String"
    to: "std::string"
```

Every method returning `juce::String` and every parameter of type `juce::String` will now appear as `std::string` in the IR and generated output.

**Difference from `OutputConfig.type_mappings`:**

The `type_mappings` field in a `.output.yml` format file applies only in the Jinja2 template rendering phase (the `map_type` filter). `add_type_mapping` changes the IR itself, before rendering. Use `add_type_mapping` when you want the IR (and manifest) to reflect the remapped types. Use format-level `type_mappings` for cosmetic remapping that only affects the template output (e.g. C++ `int` → Lua `integer`).

---

## `modify_method`

A comprehensive editor for one or more matching methods. Can rename, remove, override return type, set ownership semantics, allow threading hints, and provide a wrapper lambda.

```yaml
- stage: modify_method
  class: MyClass
  method: getData
  class_is_regex: false   # optional
  method_is_regex: false  # optional
  rename: data            # optional: new binding name
  remove: false           # optional: set emit=False
  return_type: "std::string"           # optional: override return type in output
  return_ownership: "cpp"              # optional: "none" | "cpp" | "script"
  allow_thread: true                   # optional: hint for GIL release
  wrapper_code: "+[](MyClass& self) { return self.getData().str(); }"
```

**All keys:**

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `class` | string | `"*"` | Class name pattern |
| `class_is_regex` | bool | `false` | Treat `class` as regex |
| `method` | string | `"*"` | Method name pattern |
| `method_is_regex` | bool | `false` | Treat `method` as regex |
| `rename` | string | — | New binding name |
| `remove` | bool | `false` | Set `emit=False` |
| `return_type` | string | — | Overrides return type in output (IR `return_type_override`) |
| `return_ownership` | string | — | `"none"` \| `"cpp"` \| `"script"` — memory ownership hint |
| `allow_thread` | bool | — | Template hint to release interpreter lock around call |
| `wrapper_code` | string | — | Replace `&Class::method` with this lambda/callable in the output |

**`return_ownership` values:**
- `"none"` — no ownership transfer (default; most C++ getters)
- `"cpp"` — C++ retains ownership; caller should not delete
- `"script"` — caller (script side) takes ownership; C++ will not delete

**`wrapper_code` — emitting a lambda instead of a method pointer:**

When `wrapper_code` is set, the template emits its value verbatim in place of `&Class::method`. This is useful when you need to adapt the C++ signature for the binding without modifying C++.

```yaml
transforms:
  - stage: modify_method
    class: Shape
    method: getName
    wrapper_code: "+[](Shape& self) { return std::string(self.getName()); }"
```

Generated output (luabridge3):
```cpp
.addFunction("get_name", +[](Shape& self) { return std::string(self.getName()); })
```

**Example — override return type for a method that returns an opaque internal type:**
```yaml
transforms:
  - stage: modify_method
    class: Calculator
    method: getValue
    return_type: "int"    # IR sees "InternalInt" but output shows "int"
```

---

## `modify_argument`

Edits a single parameter of one or more matching methods. Can rename the parameter, remove it from the binding signature, override its type or default value, and set ownership semantics.

```yaml
- stage: modify_argument
  class: MyClass
  method: setData
  argument: data          # by parameter name, OR 0-based integer index
  class_is_regex: false
  method_is_regex: false
  rename: value           # optional: new parameter name in binding
  remove: false           # optional: hide parameter from binding signature
  type: "std::string"     # optional: override type in output
  default: "std::string{}"  # optional: override default expression
  ownership: "cpp"        # optional: "none" | "cpp" | "script"
```

**All keys:**

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `class` | string | `"*"` | Class name pattern |
| `class_is_regex` | bool | `false` | Treat `class` as regex |
| `method` | string | `"*"` | Method name pattern |
| `method_is_regex` | bool | `false` | Treat `method` as regex |
| `argument` | string or int | — | Parameter name or 0-based index (required) |
| `rename` | string | — | New parameter name |
| `remove` | bool | `false` | Set `emit=False` — hides from signature |
| `type` | string | — | Override type spelling in output |
| `default` | string | — | Override default expression |
| `ownership` | string | — | `"none"` \| `"cpp"` \| `"script"` |

**Selecting by index:** If `argument` is a string of digits (e.g. `"0"`, `"1"`), it selects by zero-based position. Otherwise it selects by name.

**Example — rename a parameter with a trailing underscore convention:**
```yaml
transforms:
  - stage: modify_argument
    class: Circle
    method: setRadius
    argument: r           # parameter named "r" in C++
    rename: radius        # exposed as "radius" in the binding
```

**Example — remove an internal context pointer from the binding signature:**
```yaml
transforms:
  - stage: modify_argument
    class: Processor
    method: process
    argument: 0           # first parameter (by index)
    remove: true          # hidden from callers; must have a default or wrapper
```

**Example — add a default value for an optional parameter:**
```yaml
transforms:
  - stage: modify_argument
    class: Shape
    method: setName
    argument: name
    default: '""'         # caller can omit this argument
```

---

## `modify_field`

Edits a class field: rename it, hide it from the binding, or force it to be read-only.

```yaml
- stage: modify_field
  class: MyClass
  field: data_            # plain name or '*'
  class_is_regex: false
  field_is_regex: false
  rename: data            # optional: new binding name
  remove: false           # optional: set emit=False
  read_only: true         # optional: force read-only even if not const in C++
```

**All keys:**

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `class` | string | `"*"` | Class name pattern |
| `class_is_regex` | bool | `false` | Treat `class` as regex |
| `field` | string | `"*"` | Field name pattern |
| `field_is_regex` | bool | `false` | Treat `field` as regex |
| `rename` | string | — | New field name in binding |
| `remove` | bool | `false` | Set `emit=False` |
| `read_only` | bool | — | Force read-only; emits `nullptr` setter in luabridge3 |

**Example — rename fields to strip trailing underscore convention:**
```yaml
transforms:
  - stage: modify_field
    class: "*"
    field: "(.+)_$"
    field_is_regex: true
    rename: "\\1"         # strip trailing underscore from all fields
```

**Example — hide an internal mutable field and force-readonly another:**
```yaml
transforms:
  - stage: modify_field
    class: Shape
    field: scale_
    rename: scale

  - stage: modify_field
    class: Circle
    field: radius_
    rename: radius
    read_only: true       # expose radius_ but disallow writes from Lua
```

---

## `modify_constructor`

Removes a specific constructor from the binding by matching its parameter type signature.

```yaml
- stage: modify_constructor
  class: MyClass
  signature: "int, float"   # comma+space joined param types
  remove: true              # currently only remove is supported
```

**All keys:**

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `class` | string | `"*"` | Class name pattern |
| `class_is_regex` | bool | `false` | Treat `class` as regex |
| `signature` | string | `""` | Comma+space joined parameter type spellings; `""` = default constructor |
| `remove` | bool | `false` | Set `emit=False` on the matched constructor |

**Signature format:** join the parameter type spellings exactly as libclang reports them, separated by `, `. For `Circle(double radius)`, the signature is `"double"`. For `Shape(const char* name, int id)`, the signature is `"const char *, int"`.

**Example — suppress the copy constructor:**
```yaml
transforms:
  - stage: modify_constructor
    class: Shape
    signature: "const Shape &"
    remove: true
```

**Example — suppress the default constructor (no parameters):**
```yaml
transforms:
  - stage: modify_constructor
    class: Calculator
    signature: ""     # empty string = default constructor
    remove: true
```

---

## `remove_overload`

Removes one specific overload from an overloaded method by matching the full parameter type signature. Other overloads of the same method name remain unaffected.

```yaml
- stage: remove_overload
  class: Calculator
  method: add
  signature: "double, double"   # remove the double overload, keep int
```

**All keys:**

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `class` | string | `"*"` | Class name pattern |
| `class_is_regex` | bool | `false` | Treat `class` as regex |
| `method` | string | — | Method name (exact; required) |
| `signature` | string | — | Comma+space joined parameter types (required) |

**Example — expose only the `int` overload of `Calculator::add`:**
```yaml
transforms:
  - stage: remove_overload
    class: Calculator
    method: add
    signature: "double, double"
```

**Example — from `combined.hpp`, keep only one `computeArea` overload:**
```yaml
transforms:
  # computeArea has two overloads: (double radius) and (double width, double height)
  # Keep only the single-argument version
  - stage: remove_overload
    class: "*"     # it's a free function, not a class method
    method: computeArea
    signature: "double, double"
```

> **Note:** `remove_overload` for free functions currently requires specifying the class as `"*"` but the stage searches class methods. For free function overloads, use the `functions.blacklist` filter instead.

---

## `inject_code`

Inserts arbitrary raw code at a specific position in the generated output. The code is stored in `IRCodeInjection` objects that the Jinja2 template retrieves using the `code_at` filter.

```yaml
- stage: inject_code
  target: class           # "module" | "class" | "method" | "constructor"
  class: Shape            # required when target != "module"
  method: getValue        # required when target == "method"
  signature: "int"        # optional; for target == "constructor" to select one
  position: beginning     # "beginning" | "end"
  code: |
    // This code is injected at the beginning of the Shape class block
    .addFunction("__tostring", +[](Shape& s) { return s.getName(); })
```

**All keys:**

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `target` | string | — | Where to attach the injection (required) |
| `class` | string | `"*"` | Class pattern; required for all targets except `"module"` |
| `class_is_regex` | bool | `false` | Treat `class` as regex |
| `method` | string | `"*"` | Method pattern; relevant for `target: method` |
| `method_is_regex` | bool | `false` | Treat `method` as regex |
| `signature` | string | — | Constructor signature; selects specific constructor when `target: constructor` |
| `position` | string | `"end"` | `"beginning"` or `"end"` |
| `code` | string | — | Literal text to inject (required) |

**Target values:**

| Target | Injection point in IR | Template variable |
|--------|----------------------|-------------------|
| `module` | `IRModule.code_injections` | `{{ code_injections \| code_at("...") }}` |
| `class` | `IRClass.code_injections` | `{{ cls.code_injections \| code_at("...") }}` |
| `method` | `IRMethod.code_injections` | `{{ method.code_injections \| code_at("...") }}` |
| `constructor` | `IRConstructor.code_injections` | `{{ ctor.code_injections \| code_at("...") }}` |

**Template requirement:** The Jinja2 template must use `{{ code_injections | code_at("beginning") }}` and `{{ code_injections | code_at("end") }}` at appropriate positions. Both built-in formats (luabridge3 and luals) support module-level and class-level injections.

**Example — inject a custom method into the luabridge3 class block:**
```yaml
transforms:
  - stage: inject_code
    target: class
    class: Calculator
    position: end
    code: |
      .addFunction("add_three", +[](Calculator& c, int a, int b, int z) {
        return c.add(a, b) + z;
      })
```

**Example — inject a comment at the beginning of the module registration:**
```yaml
transforms:
  - stage: inject_code
    target: module
    position: beginning
    code: |
      // Bindings generated for mylib v2.1 — DO NOT EDIT
```

**Example — inject code at the beginning of every Shape constructor:**
```yaml
transforms:
  - stage: inject_code
    target: constructor
    class: Shape
    position: beginning
    code: |
      // Shape constructor wrapper start
```

---

## `set_type_hint`

Overrides class-level type trait metadata that the generator uses to decide how to register a class (copyable, movable, or abstract-only).

```yaml
- stage: set_type_hint
  class: MyClass
  copyable: false       # optional: override copy-constructibility
  movable: true         # optional: override move-constructibility
  force_abstract: true  # optional: suppress constructor binding entirely
```

**All keys:**

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `class` | string | `"*"` | Class name pattern |
| `class_is_regex` | bool | `false` | Treat `class` as regex |
| `copyable` | bool | — | `None` = infer from C++; `true`/`false` = forced |
| `movable` | bool | — | `None` = infer from C++; `true`/`false` = forced |
| `force_abstract` | bool | — | When `true`, suppresses constructor binding even if C++ class is not abstract |

**`copyable` / `movable`:** tsujikiri infers these from the C++ class definition. Override when libclang's inference is wrong (e.g. deleted copy constructor not detected).

**`force_abstract`:** Use when a class should be exposed in the binding (so derived classes can use `deriveClass`) but should never be instantiated from Lua. Common for singleton managers, resource handles with private constructors, or factory-only APIs.

**Example — mark a resource handle as non-copyable:**
```yaml
transforms:
  - stage: set_type_hint
    class: AudioBuffer
    copyable: false
```

In luabridge3, non-copyable classes are registered differently (the binding won't offer a copy constructor path).

**Example — expose a singleton manager but suppress its constructor:**
```yaml
transforms:
  - stage: set_type_hint
    class: AudioEngine
    force_abstract: true    # no .addConstructor() emitted; still bindable as base for deriveClass
```

---

## `inject_constructor`

Appends a synthetic `IRConstructor` to a class. Useful when you want to expose a construction path that doesn't correspond directly to an existing C++ constructor (combined with `modify_method` or a wrapper).

```yaml
- stage: inject_constructor
  class: MyClass
  parameters:
    - name: value
      type: int
    - name: label
      type: "const char *"
```

**All keys:**

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `class` | string | — | Target class name (required; plain name or regex) |
| `class_is_regex` | bool | `false` | Treat `class` as regex |
| `parameters` | list | `[]` | Each item has `name` (string) and `type` (string) |

When the class already has constructors, all existing constructors are marked as overloads too (so the binding system generates appropriate overload sets).

**Example — inject a default constructor not present in the original C++:**
```yaml
transforms:
  - stage: inject_constructor
    class: Circle
    parameters: []    # default constructor (no parameters)
```

---

## `suppress_base`

Removes a specific base class from a class's binding output. The base still exists in the C++ type system; it is simply not listed in the generated binding. This is useful when a base class is an implementation detail or provides non-scriptable functionality.

```yaml
- stage: suppress_base
  class: Circle
  base: ".*Protected"
  is_regex: true
```

**All keys:**

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `class` | string | `"*"` | Class name pattern |
| `class_is_regex` | bool | `false` | Treat `class` as regex |
| `base` | string | — | Base class pattern matched against its `qualified_name` (required) |
| `is_regex` | bool | `false` | Treat `base` as regex |

The `base` pattern is matched against the base class's **qualified name** (e.g. `mylib::ShapeBase`), not its short name.

**Example — suppress an internal non-scriptable base:**
```yaml
transforms:
  - stage: suppress_base
    class: "*"
    base: ".*::detail::.*"
    is_regex: true
```

**Example — suppress a specific named base on one class:**
```yaml
transforms:
  - stage: suppress_base
    class: AudioEngine
    base: "mylib::RefCounted"
```

---

## `rename_enum`

Changes the binding-visible name of an enum. The qualified C++ name is preserved for template use. Only the string registered in the binding changes.

```yaml
- stage: rename_enum
  from: Color
  to: Colour
  is_regex: false
```

**All keys:**

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `from` | string | — | Enum name to match (required) |
| `to` | string | — | New binding name (required) |
| `is_regex` | bool | `false` | Treat `from` as regex |

**Example — rename all enums to remove a common prefix:**
```yaml
transforms:
  - stage: rename_enum
    from: "Juce(.*)"
    to: "\\1"
    is_regex: true
```

---

## `rename_enum_value`

Changes the binding-visible name of one or more enum values. The original C++ enumerator name is preserved in `original_name` so templates that reference the C++ symbol still work correctly.

```yaml
- stage: rename_enum_value
  enum: Color
  from: Red
  to: red
```

**All keys:**

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `enum` | string | `"*"` | Enum name to target (plain, `"*"`, or regex) |
| `enum_is_regex` | bool | `false` | Treat `enum` as regex |
| `from` | string | — | Enum value name to match (required) |
| `to` | string | — | New binding name (required) |
| `is_regex` | bool | `false` | Treat `from` as regex |

**Example — lowercase all values of the Color enum:**
```yaml
transforms:
  - stage: rename_enum_value
    enum: Color
    from: "(.*)"
    to: "\\L\\1"    # note: Jinja2 doesn't expand \\L; this is an example of intent
    is_regex: true
```

**Example — rename a specific value:**
```yaml
transforms:
  - stage: rename_enum_value
    enum: Status
    from: StatusOK
    to: ok
```

---

## `suppress_enum`

Sets `emit=False` on matching enums. The enum stays in the IR (transforms can still see it) but the generator will skip it.

```yaml
- stage: suppress_enum
  pattern: ".*Detail$"
  is_regex: true
```

**All keys:**

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `pattern` | string | — | Enum name pattern (required) |
| `is_regex` | bool | `false` | Treat `pattern` as regex |

**Example — suppress all internal enums:**
```yaml
transforms:
  - stage: suppress_enum
    pattern: ".*Internal.*"
    is_regex: true
```

---

## `suppress_enum_value`

Sets `emit=False` on matching values within an enum. The value stays in the IR but is excluded from the generated output.

```yaml
- stage: suppress_enum_value
  enum: Color
  pattern: "Reserved.*"
  is_regex: true
```

**All keys:**

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `enum` | string | `"*"` | Enum name to target (plain, `"*"`, or regex) |
| `enum_is_regex` | bool | `false` | Treat `enum` as regex |
| `pattern` | string | — | Enum value name pattern (required) |
| `is_regex` | bool | `false` | Treat `pattern` as regex |

**Example — suppress all `COUNT` sentinel values across all enums:**
```yaml
transforms:
  - stage: suppress_enum_value
    enum: "*"
    pattern: ".*_COUNT"
    is_regex: true
```

---

## `modify_enum`

A combined editor for an enum: rename it or suppress it in one stage. For more targeted operations, prefer `rename_enum` and `suppress_enum`.

```yaml
- stage: modify_enum
  enum: Color
  rename: Colour       # optional: new binding name
  remove: false        # optional: set emit=False
```

**All keys:**

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `enum` | string | `"*"` | Enum name to target |
| `enum_is_regex` | bool | `false` | Treat `enum` as regex |
| `rename` | string | — | New binding name |
| `remove` | bool | `false` | Set `emit=False` |

---

## `rename_function`

Changes the binding-visible name of a free function. The qualified C++ name is preserved for template use.

```yaml
- stage: rename_function
  from: computeArea
  to: compute_area
  is_regex: false
```

**All keys:**

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `from` | string | — | Function name to match (required) |
| `to` | string | — | New binding name (required) |
| `is_regex` | bool | `false` | Treat `from` as regex |

**Example — strip a common verb prefix from all free functions:**
```yaml
transforms:
  - stage: rename_function
    from: "do(.*)"
    to: "\\1"
    is_regex: true
```

---

## `suppress_function`

Sets `emit=False` on matching free functions.

```yaml
- stage: suppress_function
  pattern: "internal_.*"
  is_regex: true
```

**All keys:**

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `pattern` | string | — | Function name pattern (required) |
| `is_regex` | bool | `false` | Treat `pattern` as regex |

**Example — suppress all debug functions:**
```yaml
transforms:
  - stage: suppress_function
    pattern: "debug.*"
    is_regex: true
```

---

## `modify_function`

A comprehensive editor for one or more free functions. Mirrors `modify_method` but operates on module-level functions.

```yaml
- stage: modify_function
  function: computeArea
  function_is_regex: false
  rename: compute_area         # optional: new binding name
  remove: false                # optional: set emit=False
  return_type: "float"         # optional: override return type in output
  return_ownership: "cpp"      # optional: "none" | "cpp" | "script"
  allow_thread: true           # optional: GIL-release hint
  wrapper_code: "+[]() { return 0.0f; }"  # optional: lambda instead of &qualifiedName
```

**All keys:**

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `function` | string | `"*"` | Function name pattern |
| `function_is_regex` | bool | `false` | Treat `function` as regex |
| `rename` | string | — | New binding name |
| `remove` | bool | `false` | Set `emit=False` |
| `return_type` | string | — | Override return type in output |
| `return_ownership` | string | — | `"none"` \| `"cpp"` \| `"script"` |
| `allow_thread` | bool | — | Template hint to release interpreter lock |
| `wrapper_code` | string | — | Replace function pointer with this lambda/callable |

**Example — wrap a C-style function that returns a raw pointer:**
```yaml
transforms:
  - stage: modify_function
    function: getEngine
    return_type: "AudioEngine&"
    wrapper_code: "[]() -> AudioEngine& { return *getEngine(); }"
```

---

## `inject_function`

Appends a synthetic `IRFunction` to the module. The caller is responsible for ensuring the corresponding C++ symbol exists.

```yaml
- stage: inject_function
  name: create_circle
  namespace: mylib
  return_type: "mylib::Circle*"
  parameters:
    - name: radius
      type: double
```

**All keys:**

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `name` | string | — | Function name (required) |
| `namespace` | string | `""` | Namespace for the qualified name (`namespace::name`) |
| `return_type` | string | `"void"` | C++ return type spelling |
| `parameters` | list | `[]` | Each item has `name` (string) and `type` (string) |

**Example — inject a factory function not present in the original API:**
```yaml
transforms:
  - stage: inject_function
    name: create_default_engine
    namespace: audio
    return_type: "audio::AudioEngine*"
    parameters: []
```

---

## Combining Stages: A Real-World Recipe

The following configuration applies several stages to the `combined.hpp` fixture to produce a clean Lua API from the raw C++ headers:

```yaml
# combined_transforms.input.yml
source:
  path: combined.hpp
  parse_args: ["-std=c++17"]

filters:
  namespaces: ["mylib"]
  constructors:
    include: true
  methods:
    global_blacklist:
      - pattern: "operator.*"
        is_regex: true

transforms:
  # 1. Rename fields to remove trailing underscores
  - stage: modify_field
    class: "*"
    field: "(.+)_$"
    field_is_regex: true
    rename: "\\1"

  # 2. Map the Calculator's int return to a more descriptive name in context
  - stage: rename_method
    class: Calculator
    from: getValue
    to: get

  # 3. Keep only the int overload of add (remove the double one)
  - stage: remove_overload
    class: Calculator
    method: add
    signature: "double, double"

  # 4. Make the radius field of Circle read-only (it should only change via setRadius)
  - stage: modify_field
    class: Circle
    field: radius
    read_only: true

  # 5. Suppress the virtual base class methods on Shape that subclasses handle
  - stage: suppress_method
    class: Shape
    pattern: "area"

  # 6. Inject a helper into the module-level registration
  - stage: inject_code
    target: module
    position: end
    code: |
      // Helper registered separately

generation:
  includes: ['"combined.hpp"']
```

---

## See Also

- [Filtering](filtering.md) — runs before transforms; transforms can re-enable suppressed nodes
- [Output Formats](output-formats.md) — how the IR context variables from transforms appear in templates
- [Input File Reference](input-file-reference.md) — where to put `transforms` in the YAML
