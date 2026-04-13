/// samplebinding.hpp — mirrors the shiboken samplebinding scenario.
///
/// Demonstrates:
///   - virtual methods that Python can override (trampoline classes)
///   - shared_ptr holder type (enable_shared_from_this)
///   - ownership transfer: addFlavor(Icecream*) keeps the icecream alive
///   - value-type Truck that stores a collection of shared_ptr<Icecream>
///   - operator<< bound as __repr__
#pragma once

#include <memory>
#include <sstream>
#include <string>
#include <vector>

namespace sample {

class Icecream : public std::enable_shared_from_this<Icecream> {
public:
    explicit Icecream(const std::string& flavor) : flavor_(flavor) {}
    virtual ~Icecream() = default;

    virtual std::string getFlavor() const { return flavor_; }
    virtual std::shared_ptr<Icecream> clone() const {
        return std::make_shared<Icecream>(flavor_);
    }

    std::string toString() const {
        std::ostringstream ss;
        ss << "Icecream(" << flavor_ << ")";
        return ss.str();
    }

private:
    std::string flavor_;
};

class Truck {
public:
    explicit Truck(bool leaveOnDestruction = false)
        : leaveOnDestruction_(leaveOnDestruction) {}

    void addFlavor(std::shared_ptr<Icecream> ice) {
        flavors_.push_back(std::move(ice));
    }

    int flavorCount() const { return static_cast<int>(flavors_.size()); }

    std::string flavorAt(int index) const {
        if (index < 0 || index >= static_cast<int>(flavors_.size())) {
            return "";
        }
        return flavors_[index]->getFlavor();
    }

    bool isLeaving() const { return leaveOnDestruction_; }

private:
    bool leaveOnDestruction_;
    std::vector<std::shared_ptr<Icecream>> flavors_;
};

} // namespace sample
