/// anonymous_records.hpp — anonymous union / struct member flattening fixture.
#pragma once

namespace mylib {

struct AnonymousContainer {
    // Truly anonymous union holding an array plus a nested anonymous struct.
    // Both `v` and the struct's `x`/`y` are injected into AnonymousContainer's scope.
    union {
        int v[2];
        struct {
            int x;
            int y;
        };
        // A *named* record nested in an anonymous member is not itself an
        // anonymous member, so it is skipped rather than flattened.
        struct NamedInner {
            int inner_field;
        };
    };

    // Named union field: `u` is a real FIELD_DECL — must NOT be flattened
    // and must NOT produce an inner class.
    union {
        int a;
        float b;
    } u;

    // Named struct field: same rule.
    struct {
        int q;
    } named_s;

    // Anonymous struct directly at class scope.
    struct {
        int direct;
    };

    int plain = 0;

private:
    // Private anonymous union — must stay excluded entirely.
    union {
        int secret;
    };
};

struct Outer {
    int outer_field = 0;

    struct Nested {
        union {
            int nested_anon;
            double nested_anon_d;
        };
    };
};

} // namespace mylib
