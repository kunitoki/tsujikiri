/// math_types.hpp — engine scenario: math namespace types (Vec3).
#pragma once
#include <cmath>

namespace math {

struct Vec3 {
    Vec3() = default;
    Vec3(double x, double y, double z) : x(x), y(y), z(z) {}

    double length() const { return std::sqrt(x * x + y * y + z * z); }

    Vec3 add(const Vec3& o) const { return Vec3(x + o.x, y + o.y, z + o.z); }
    Vec3 scale(double s) const { return Vec3(x * s, y * s, z * s); }

    static Vec3 zero()    { return Vec3(0.0, 0.0, 0.0); }
    static Vec3 up()      { return Vec3(0.0, 1.0, 0.0); }
    static Vec3 forward() { return Vec3(0.0, 0.0, -1.0); }

    double x = 0.0;
    double y = 0.0;
    double z = 0.0;
};

inline double dot(const Vec3& a, const Vec3& b)
{
    return a.x * b.x + a.y * b.y + a.z * b.z;
}

inline Vec3 cross(const Vec3& a, const Vec3& b)
{
    return Vec3(
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x);
}

} // namespace math
