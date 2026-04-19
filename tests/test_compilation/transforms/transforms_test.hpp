#pragma once
// transforms_test.hpp — single header that exercises every tsujikiri transform stage.
#include <compare>
#include <memory>
#include <stdexcept>
#include <string>

namespace trf {

// add_type_mapping: WidgetTag -> "unsigned char"
using WidgetTag = unsigned char;

// suppress_enum: WidgetState is entirely hidden from bindings
enum class WidgetState { Initial = 0, Active = 1, Paused = 2 };

// rename_enum (OldColor -> Color), rename_enum_value (Red -> Crimson),
// suppress_enum_value (Alpha), modify_enum (arithmetic: true)
enum OldColor { Red = 0, Green = 1, Blue = 2, Alpha = 3 };

// register_exception: registered as Python exception class in pybind11
class TransformError : public std::runtime_error {
public:
    explicit TransformError(const std::string& msg) : std::runtime_error(msg) {}
};

// suppress_base: used as a suppressed base in DerivedWidget
class BaseHelper {
public:
    BaseHelper() = default;
    void helperMethod() {}
    int helperValue() const { return 99; }
};

// Main test class — exercises the majority of class/method/field/constructor transforms.
class Widget {
public:
    Widget() = default;
    explicit Widget(int id) : id_(id), cache_name_("default") {}
    // modify_constructor removes this overload; inject_constructor re-adds it
    Widget(int id, int extra) : id_(id + extra), cache_name_("default") {}
    virtual ~Widget() = default;

    // rename_method: getIdInternal -> get_id
    int getIdInternal() const { return id_; }

    // add_type_mapping: WidgetTag remapped to "unsigned char" in binding type spellings.
    // Overloads force luabridge::overload<unsigned char> disambiguation in generated code.
    WidgetTag getTag() const { return static_cast<WidgetTag>(id_); }
    void setTag(int tag) { id_ = tag; }
    void setTag(WidgetTag tag) { id_ = static_cast<int>(tag); }

    // suppress_method
    void legacyReset() { id_ = 0; cache_name_ = ""; }

    // modify_method: rename -> process_data
    void processData(int value) { id_ += value; }

    // modify_argument: rawOption -> option, rawName -> name
    // exception_policy: pass_through
    void configure(int rawOption, const std::string& rawName) {
        id_ = rawOption;
        cache_name_ = rawName;
    }

    // update(int) and update(double) are kept; update(float) is removed via remove_overload
    void update(int value) { id_ = value; }
    void update(double value) { id_ = static_cast<int>(value); }
    void update(float value) { id_ = static_cast<int>(value); }

    // overload_priority: compute(double) gets priority 0 (tried first in binding)
    double compute(int n) const { return static_cast<double>(n * n); }
    double compute(double x) const { return x * x; }

    // inject_property targets (getter / setter)
    int getRawValue() const { return id_; }
    void setRawValue(int v) { id_ = v; }

    // suppress_method then inject_method: the original binding is suppressed and re-injected
    std::string describe() const { return "Widget(" + std::to_string(id_) + ")"; }

    // modify_field: id_  renamed to "id" in the binding
    int id_ = 0;
    // modify_field: cache_name_ removed from the binding
    std::string cache_name_ = "default";

protected:
    // expose_protected: exposed via pybind11 trampoline so Python can override it
    virtual void onRender() {}
};

// suppress_class: WidgetInternal is entirely absent from binding output
class WidgetInternal {
public:
    WidgetInternal() = default;
    void internalOp() {}
};

// rename_class: WidgetManager -> Manager
// mark_deprecated applied to increment()
class WidgetManager {
public:
    WidgetManager() = default;
    int getCount() const { return count_; }
    void increment() { ++count_; }
private:
    int count_ = 0;
};

// suppress_base: DerivedWidget's BaseHelper base is suppressed in the binding
class DerivedWidget : public Widget, public BaseHelper {
public:
    DerivedWidget() = default;
    explicit DerivedWidget(int id) : Widget(id) {}
};

// set_type_hint: holder_type = std::shared_ptr
// expose_protected applied to computeValue() for pybind11 trampoline
class SharedNode {
public:
    SharedNode() = default;
    explicit SharedNode(int value) : value_(value) {}
    virtual ~SharedNode() = default;
    int getValue() const { return value_; }
    std::shared_ptr<SharedNode> clone() const {
        return std::make_shared<SharedNode>(value_);
    }
protected:
    virtual int computeValue() const { return value_; }
private:
    int value_ = 0;
};

// resolve_using_declarations: ExtendedWidget's using declarations are resolved into methods
class WidgetBase {
public:
    WidgetBase() = default;
    void extendedMethod(int x) { ext_val_ += x; }
    int extendedValue() const { return ext_val_; }
private:
    int ext_val_ = 0;
};

class ExtendedWidget : public Widget, public WidgetBase {
public:
    ExtendedWidget() = default;
    using WidgetBase::extendedMethod;
    using WidgetBase::extendedValue;
};

// expand_spaceship: Score::operator<=> is expanded to 6 comparison operators
struct Score {
    int value = 0;
    Score() = default;
    explicit Score(int v) : value(v) {}
    auto operator<=> (const Score&) const = default;
};

// rename_function: computeWidgetScore -> compute_score
inline int computeWidgetScore(int n) { return n * n; }
// suppress_function
inline void internalUtility() {}
// modify_function: rename -> process_widget
inline double processWidget(double x) { return x * 2.0; }
// suppress_function + inject_function: suppressed then synthetically re-injected
inline Widget* makeWidget(int id) { return new Widget(id); }
// exception_policy: pass_through; pybind11 maps thrown TransformError to Python exception
inline void throwTransformError(const std::string& msg) { throw TransformError(msg); }

} // namespace trf
