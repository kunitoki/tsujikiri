namespace outer {
    namespace inner {
        class Deep {};
        enum class Color { Red, Green, Blue };
        void inner_func(int x);
    }
    inline namespace v2 {
        class Inlined {};
    }
    class Direct {};
}
namespace enumonly {
    enum class Status { Active, Inactive };
}
class GlobalClass {};
class ForwardDeclared;
void global_func();
