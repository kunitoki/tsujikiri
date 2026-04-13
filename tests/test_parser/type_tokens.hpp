/// type_tokens.hpp — fixture for TestTypeFromTokens: exercises _type_from_tokens
/// across the full spectrum of C++ parameter type shapes.
///
/// Many std:: types are affected by a libclang bug that reports the wrong type
/// (typically 'int') via cursor.type.spelling. _type_from_tokens works around
/// this by reconstructing the type from the source token stream instead.
/// Functions are grouped below by whether they trigger the bug.
#pragma once
#include <cstddef>
#include <functional>
#include <map>
#include <memory>
#include <optional>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "type_namespaces.hpp"

namespace types {

struct Obj {};

// ---------------------------------------------------------------------------
// Primitive / built-in types — not affected by the libclang bug
// ---------------------------------------------------------------------------
void f_int(int x);
void f_double(double x);
void f_bool(bool x);
void f_unsigned_int(unsigned int x);
void f_long_long(long long x);
void f_size_t(std::size_t x);

// ---------------------------------------------------------------------------
// Pointer and reference qualifications — not affected
// ---------------------------------------------------------------------------
void f_int_ptr(int* x);
void f_const_char_ptr(const char* x);
void f_int_ref(int& x);
void f_const_int_ref(const int& x);

// ---------------------------------------------------------------------------
// std::string — all variants affected by the libclang bug
// ---------------------------------------------------------------------------
void f_string(std::string x);
void f_string_ref(std::string& x);
void f_string_cref(const std::string& x);
void f_string_rref(std::string&& x);

// ---------------------------------------------------------------------------
// std::string_view — NOT affected by the bug
// ---------------------------------------------------------------------------
void f_sv(std::string_view x);
void f_sv_cref(const std::string_view& x);

// ---------------------------------------------------------------------------
// std::vector — affected by the libclang bug
// ---------------------------------------------------------------------------
void f_vec_int(std::vector<int> x);
void f_vec_string(std::vector<std::string> x);
void f_vec_int_cref(const std::vector<int>& x);

// ---------------------------------------------------------------------------
// std::map — affected by the libclang bug
// ---------------------------------------------------------------------------
void f_map_string_int(std::map<std::string, int> x);

// ---------------------------------------------------------------------------
// std::optional — affected by the libclang bug
// ---------------------------------------------------------------------------
void f_opt_string(std::optional<std::string> x);

// ---------------------------------------------------------------------------
// Nested templates — affected by the libclang bug
// ---------------------------------------------------------------------------
void f_nested(std::vector<std::pair<int, std::string>> x);

// ---------------------------------------------------------------------------
// std::function — NOT affected by the bug
// ---------------------------------------------------------------------------
void f_fn_void_int(std::function<void(int)> x);
void f_fn_int_two_doubles(std::function<int(double, double)> x);

// ---------------------------------------------------------------------------
// std::shared_ptr — NOT affected by the bug
// ---------------------------------------------------------------------------
void f_shared_obj(std::shared_ptr<Obj> x);

// ---------------------------------------------------------------------------
// Multi-parameter function: verifies each position is correctly resolved
// ---------------------------------------------------------------------------
void f_multi(std::string name, int count, const std::vector<double>& values);

// ---------------------------------------------------------------------------
// Global-namespace-qualified std:: types  (::std::...)
// All are affected by the libclang bug (reported as 'int').
// The :: prefix causes a leading '::' token in the PARM_DECL stream.
// ---------------------------------------------------------------------------
void g_string(::std::string x);
void g_string_cref(const ::std::string& x);
void g_string_rref(::std::string&& x);
void g_vec_int(::std::vector<int> x);
void g_optional_string(::std::optional<::std::string> x);
void g_map_string_int(::std::map<::std::string, int> x);
void g_function_void_string(::std::function<void(::std::string)> x);

// ---------------------------------------------------------------------------
// Nested-namespace user types  (outer::inner::Type)
// libclang reports these CORRECTLY, but the token path must still work.
// ---------------------------------------------------------------------------
void n_nested_value(outer::inner::Nested x);
void n_nested_cref(const outer::inner::Nested& x);
void n_nested_ptr(outer::inner::Nested* x);
void n_mid_value(outer::Mid = outer::Mid{});
void n_global_nested(::outer::inner::Nested x);
void n_global_deep_ptr(::outer::inner::Deep* x);

// ---------------------------------------------------------------------------
// Cross-namespace: std containers / wrappers holding user types,
// and user types alongside global-qualified std types in the same parameter.
// ---------------------------------------------------------------------------
void m_multi(outer::inner::Nested a, ::std::string b);
void m_vec_nested(::std::vector<outer::inner::Nested> x);
void m_map_nested_string(::std::map<outer::inner::Nested, ::std::string> x);
void m_function_nested(::std::function<outer::inner::Nested(::std::string, outer::Mid)>);

// ---------------------------------------------------------------------------
// Class with a constructor that uses std::move in its initialiser list.
// This is the original bug trigger: libclang reports wrong types for such
// constructors without the _type_from_tokens workaround.
// ---------------------------------------------------------------------------
class Widget {
public:
    Widget() = default;
    Widget(std::string name, std::vector<int> ids)
        : name_(std::move(name)), ids_(std::move(ids)) {}
    Widget(const std::string& label, std::map<std::string, int> attrs, std::optional<double> weight)
        : name_(label), ids_(), weight_(weight) { (void)attrs; }
private:
    std::string name_;
    std::vector<int> ids_;
    std::optional<double> weight_;
};

} // namespace types


