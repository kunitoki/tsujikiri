#pragma once

namespace mylib {

/// A documented container.
///
/// More detail about the container.
class Container {
public:
    /// Constructs a container.
    /// @param size The initial size.
    Container(int size);

    /**
     * Sets the volume.
     *
     * @param volume Volume in decibels.
     * @param fadeTime Fade time in seconds.
     */
    void setVolume(float volume, float fadeTime);

    /// Gets the current volume.
    /// @return The volume in decibels.
    float getVolume() const;

    //! A field holding the gain.
    float gain;
};

/// A documented enum.
enum class Mode {
    /// The first mode.
    First,
    Second,
};

/// A free function.
/// @param x The input value.
/// @returns The computed result.
double compute(double x);

} // namespace mylib
