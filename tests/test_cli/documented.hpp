/// documented.hpp — fixture for CLI comment-extraction tests.
#pragma once

namespace documented {

/// A documented widget class.
class Widget {
public:
    Widget();

    /// Returns the identifier.
    /// @return The widget id.
    int getId() const;
};

} // namespace documented
