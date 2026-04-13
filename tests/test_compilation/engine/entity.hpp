/// entity.hpp — engine scenario: engine namespace with cross-namespace Vec3 usage.
#pragma once

#include "math_types.hpp"

#include <string>
#include <string_view>

namespace engine {

enum class EntityType { Static = 0, Dynamic = 1, Kinematic = 2 };

class Entity {
public:
    Entity() = default;
    explicit Entity(std::string_view name) : name_(name) {}
    Entity(std::string name, math::Vec3 pos) : name_(name), position_(pos) {}

    std::string_view getName() const { return name_; }
    void        setName(const char* n) { name_ = n; }

    math::Vec3 getPosition() const { return position_; }
    void       setPosition(math::Vec3 pos) { position_ = pos; }

    EntityType getType() const { return type_; }
    void       setType(EntityType t) { type_ = t; }

    bool isActive() const { return active_; }
    void setActive(bool a) { active_ = a; }

    virtual void      update(double dt) {}
    virtual const char* className() const { return "Entity"; }

    static Entity create(const char* name) { return Entity(name); }

private:
    std::string name_     = "entity";
    math::Vec3  position_ = {};
    EntityType  type_     = EntityType::Static;
    bool        active_   = true;
};

class Player : public Entity {
public:
    Player() = default;
    explicit Player(const char* name) : Entity(name) {}

    double getHealth() const { return health_; }
    void   setHealth(double h) { health_ = h; }

    double getSpeed() const { return speed_; }
    void   setSpeed(double s) { speed_ = s; }

    void move(math::Vec3 direction) {
        math::Vec3 pos = getPosition();
        setPosition(math::Vec3(pos.x + direction.x, pos.y + direction.y, pos.z + direction.z));
    }

    void takeDamage(double amount) {
        health_ -= amount;
        if (health_ < 0.0)
            health_ = 0.0;
    }

    bool        isAlive() const { return health_ > 0.0; }
    const char* className() const override { return "Player"; }

    static Player spawn(const char* name, math::Vec3 pos) {
        Player p(name);
        p.setPosition(pos);
        return p;
    }

private:
    double health_ = 100.0;
    double speed_  = 5.0;
};

} // namespace engine
