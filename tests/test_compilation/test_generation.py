"""Generation tests — parse input YAMLs and verify generated binding code.

All tests here are fast: they generate binding source code in-memory and check
for expected strings.  No compiler or cmake invocation is required.
"""

from __future__ import annotations

import copy
import io
from pathlib import Path

from tsujikiri.configurations import CustomTypeEntry, PrimitiveTypeEntry, TransformSpec, TypesystemConfig
from tsujikiri.generator import Generator
from tsujikiri.transforms import build_pipeline_from_config

HERE = Path(__file__).parent


def _generate(module, output_config, generation=None) -> str:
    buf = io.StringIO()
    Generator(output_config, generation=generation).generate(module, buf)
    return buf.getvalue()


def _generate_with_options(module, output_config, generation=None, api_version: str = "", typesystem=None) -> str:
    buf = io.StringIO()
    Generator(output_config, generation=generation, typesystem=typesystem).generate(module, buf, api_version=api_version)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# combined — original single-namespace, single-header (LuaBridge3)
# ---------------------------------------------------------------------------

class TestCombinedLuaBridge3Generation:
    """Fast generation tests for the original combined scenario."""

    def test_all(self, compiled_module, luabridge3_output_config):
        out = _generate(compiled_module, luabridge3_output_config)
        assert '.beginNamespace("Color")' in out
        assert '.beginClass<mylib::Shape>("Shape")' in out
        assert '.deriveClass<mylib::Circle, mylib::Shape>("Circle")' in out
        assert 'addConstructor<void (*)()>' in out
        assert 'luabridge::overload<int, int>(&mylib::Calculator::add)' in out
        assert '.endNamespace()' in out


# ---------------------------------------------------------------------------
# geo — multi-header, single namespace, Circle/Rectangle : Shape
# ---------------------------------------------------------------------------

class TestGeoLuaBridge3Generation:
    """Fast generation tests for the geo multi-header scenario."""

    def test_begin_class_shape(self, geo_module, luabridge3_output_config):
        assert '.beginClass<geo::Shape>("Shape")' in _generate(geo_module, luabridge3_output_config)

    def test_derive_class_circle(self, geo_module, luabridge3_output_config):
        assert '.deriveClass<geo::Circle, geo::Shape>("Circle")' in _generate(geo_module, luabridge3_output_config)

    def test_derive_class_rectangle(self, geo_module, luabridge3_output_config):
        assert '.deriveClass<geo::Rectangle, geo::Shape>("Rectangle")' in _generate(geo_module, luabridge3_output_config)

    def test_color_enum_registered(self, geo_module, luabridge3_output_config):
        out = _generate(geo_module, luabridge3_output_config)
        assert '.beginNamespace("Color")' in out
        assert "geo::Color::Red" in out
        assert "geo::Color::Green" in out
        assert "geo::Color::Blue" in out

    def test_overloaded_resize(self, geo_module, luabridge3_output_config):
        out = _generate(geo_module, luabridge3_output_config)
        assert "luabridge::overload<double>(&geo::Circle::resize)" in out
        assert "luabridge::overload<double, double>(&geo::Circle::resize)" in out

    def test_static_factory_circle(self, geo_module, luabridge3_output_config):
        assert "&geo::Circle::unit" in _generate(geo_module, luabridge3_output_config)

    def test_static_factory_rectangle(self, geo_module, luabridge3_output_config):
        assert "&geo::Rectangle::square" in _generate(geo_module, luabridge3_output_config)

    def test_free_function_overloads(self, geo_module, luabridge3_output_config):
        out = _generate(geo_module, luabridge3_output_config)
        assert "luabridge::overload<double>(&geo::computeArea)" in out
        assert "luabridge::overload<double, double>(&geo::computeArea)" in out

    def test_no_duplicate_shape_class(self, geo_module, luabridge3_output_config):
        # Multi-source dedup: Shape must appear exactly once in the output
        out = _generate(geo_module, luabridge3_output_config)
        assert out.count('beginClass<geo::Shape>') + out.count('deriveClass<geo::Shape') == 1


class TestGeoPybind11Generation:
    """Fast generation tests for the geo scenario with pybind11."""

    def test_circle_class_with_base(self, geo_module, pybind11_output_config):
        assert "py::class_<geo::Circle, PyCircle, geo::Shape>" in _generate(geo_module, pybind11_output_config)

    def test_rectangle_class_with_base(self, geo_module, pybind11_output_config):
        assert "py::class_<geo::Rectangle, PyRectangle, geo::Shape>" in _generate(geo_module, pybind11_output_config)

    def test_color_enum(self, geo_module, pybind11_output_config):
        out = _generate(geo_module, pybind11_output_config)
        assert 'py::enum_<geo::Color>(m, "Color")' in out
        # geo::Color is "enum class" (scoped), so .export_values() must NOT appear
        assert ".export_values();" not in out

    def test_overloaded_resize_fixed(self, geo_module, pybind11_output_config):
        # Verify the fixed template: no spurious py::overload_cast<...> as 2nd arg
        out = _generate(geo_module, pybind11_output_config)
        assert "py::overload_cast<double>(&geo::Circle::resize)" in out
        assert "py::overload_cast<double, double>(&geo::Circle::resize)" in out

    def test_static_factory(self, geo_module, pybind11_output_config):
        assert '.def_static("unit"' in _generate(geo_module, pybind11_output_config)

    def test_no_duplicate_shape(self, geo_module, pybind11_output_config):
        out = _generate(geo_module, pybind11_output_config)
        assert out.count('py::class_<geo::Shape, PyShape>') == 1


# ---------------------------------------------------------------------------
# engine — multi-header, two namespaces (math + engine), cross-references
# ---------------------------------------------------------------------------

class TestEngineLuaBridge3Generation:
    """Fast generation tests for the engine multi-namespace scenario."""

    def test_vec3_registered(self, engine_module, luabridge3_output_config):
        assert '.beginClass<math::Vec3>("Vec3")' in _generate(engine_module, luabridge3_output_config)

    def test_entity_registered(self, engine_module, luabridge3_output_config):
        assert '.beginClass<engine::Entity>("Entity")' in _generate(engine_module, luabridge3_output_config)

    def test_player_derives_entity(self, engine_module, luabridge3_output_config):
        assert '.deriveClass<engine::Player, engine::Entity>("Player")' in _generate(engine_module, luabridge3_output_config)

    def test_entity_type_enum(self, engine_module, luabridge3_output_config):
        out = _generate(engine_module, luabridge3_output_config)
        assert '.beginNamespace("EntityType")' in out
        assert "engine::EntityType::Static" in out
        assert "engine::EntityType::Dynamic" in out

    def test_cross_namespace_method(self, engine_module, luabridge3_output_config):
        # setPosition takes math::Vec3 — verify it appears in binding code
        assert "&engine::Entity::setPosition" in _generate(engine_module, luabridge3_output_config)

    def test_free_functions_dot_cross(self, engine_module, luabridge3_output_config):
        out = _generate(engine_module, luabridge3_output_config)
        assert "&math::dot" in out
        assert "&math::cross" in out

    def test_no_duplicate_vec3(self, engine_module, luabridge3_output_config):
        out = _generate(engine_module, luabridge3_output_config)
        assert out.count('beginClass<math::Vec3>') == 1


class TestEnginePybind11Generation:
    """Fast generation tests for the engine scenario with pybind11."""

    def test_vec3_class(self, engine_module, pybind11_output_config):
        assert 'py::class_<math::Vec3>(m, "Vec3")' in _generate(engine_module, pybind11_output_config)

    def test_player_derives_entity(self, engine_module, pybind11_output_config):
        assert "py::class_<engine::Player, PyPlayer, engine::Entity>" in _generate(engine_module, pybind11_output_config)

    def test_cross_namespace_binding(self, engine_module, pybind11_output_config):
        assert "&engine::Entity::setPosition" in _generate(engine_module, pybind11_output_config)

    def test_no_duplicate_vec3(self, engine_module, pybind11_output_config):
        out = _generate(engine_module, pybind11_output_config)
        assert out.count('py::class_<math::Vec3>') == 1


# ---------------------------------------------------------------------------
# audio — single header, 3-level deep inheritance chain
# ---------------------------------------------------------------------------

class TestAudioLuaBridge3Generation:
    """Fast generation tests for the audio 3-level hierarchy."""

    def test_audio_node_base_class(self, audio_module, luabridge3_output_config):
        assert '.beginClass<audio::AudioNode>("AudioNode")' in _generate(audio_module, luabridge3_output_config)

    def test_audio_source_derives_node(self, audio_module, luabridge3_output_config):
        assert '.deriveClass<audio::AudioSource, audio::AudioNode>("AudioSource")' in _generate(audio_module, luabridge3_output_config)

    def test_audio_effect_derives_node(self, audio_module, luabridge3_output_config):
        assert '.deriveClass<audio::AudioEffect, audio::AudioNode>("AudioEffect")' in _generate(audio_module, luabridge3_output_config)

    def test_reverb_derives_effect(self, audio_module, luabridge3_output_config):
        assert '.deriveClass<audio::Reverb, audio::AudioEffect>("Reverb")' in _generate(audio_module, luabridge3_output_config)

    def test_delay_derives_effect(self, audio_module, luabridge3_output_config):
        assert '.deriveClass<audio::Delay, audio::AudioEffect>("Delay")' in _generate(audio_module, luabridge3_output_config)

    def test_reverb_static_factories(self, audio_module, luabridge3_output_config):
        out = _generate(audio_module, luabridge3_output_config)
        assert "&audio::Reverb::room" in out
        assert "&audio::Reverb::chamber" in out

    def test_delay_static_factories(self, audio_module, luabridge3_output_config):
        out = _generate(audio_module, luabridge3_output_config)
        assert "&audio::Delay::echo" in out
        assert "&audio::Delay::slap" in out

    def test_node_type_enum(self, audio_module, luabridge3_output_config):
        out = _generate(audio_module, luabridge3_output_config)
        assert '.beginNamespace("NodeType")' in out
        assert "audio::NodeType::Source" in out


class TestAudioPybind11Generation:
    """Fast generation tests for the audio scenario with pybind11."""

    def test_audio_node_class(self, audio_module, pybind11_output_config):
        assert 'py::class_<audio::AudioNode, PyAudioNode>' in _generate(audio_module, pybind11_output_config)

    def test_reverb_deep_inheritance(self, audio_module, pybind11_output_config):
        assert "py::class_<audio::Reverb, PyReverb, audio::AudioEffect>" in _generate(audio_module, pybind11_output_config)

    def test_delay_deep_inheritance(self, audio_module, pybind11_output_config):
        assert "py::class_<audio::Delay, PyDelay, audio::AudioEffect>" in _generate(audio_module, pybind11_output_config)

    def test_reverb_static_factories_pybind11(self, audio_module, pybind11_output_config):
        out = _generate(audio_module, pybind11_output_config)
        assert '.def_static("room"' in out
        assert '.def_static("chamber"' in out

    def test_node_type_enum_pybind11(self, audio_module, pybind11_output_config):
        out = _generate(audio_module, pybind11_output_config)
        assert 'py::enum_<audio::NodeType>' in out


# ---------------------------------------------------------------------------
# samplebinding — virtual methods, trampolines, shared_ptr holder
# ---------------------------------------------------------------------------

class TestSamplebindingPybind11Generation:
    """Fast generation tests for the samplebinding scenario with pybind11."""

    def test_trampoline_class_generated(self, samplebinding_module, pybind11_output_config):
        out = _generate(samplebinding_module, pybind11_output_config)
        assert "class PyIcecream : public sample::Icecream" in out

    def test_trampoline_using_constructor(self, samplebinding_module, pybind11_output_config):
        out = _generate(samplebinding_module, pybind11_output_config)
        assert "using sample::Icecream::Icecream" in out

    def test_trampoline_override_get_flavor(self, samplebinding_module, pybind11_output_config):
        out = _generate(samplebinding_module, pybind11_output_config)
        assert 'PYBIND11_OVERRIDE_NAME(std::string, sample::Icecream, "get_flavor", getFlavor)' in out

    def test_trampoline_override_clone(self, samplebinding_module, pybind11_output_config):
        out = _generate(samplebinding_module, pybind11_output_config)
        assert 'PYBIND11_OVERRIDE_NAME(' in out
        assert 'sample::Icecream, "clone", clone' in out

    def test_icecream_class_with_trampoline_and_holder(self, samplebinding_module, pybind11_output_config):
        out = _generate(samplebinding_module, pybind11_output_config)
        assert "py::class_<sample::Icecream, PyIcecream, std::shared_ptr<sample::Icecream>>" in out

    def test_truck_class_no_trampoline(self, samplebinding_module, pybind11_output_config):
        out = _generate(samplebinding_module, pybind11_output_config)
        assert 'py::class_<sample::Truck>(m, "Truck")' in out

    def test_add_flavor_bound(self, samplebinding_module, pybind11_output_config):
        out = _generate(samplebinding_module, pybind11_output_config)
        assert '"add_flavor"' in out
        assert "&sample::Truck::addFlavor" in out


# ---------------------------------------------------------------------------
# api_version — version gating and constant emission
# ---------------------------------------------------------------------------

class TestApiVersionGeneration:
    """Generator api_version parameter: constant emission and entity gating."""

    def test_luabridge3_emits_api_version_constant(self, geo_module, luabridge3_output_config):
        out = _generate_with_options(geo_module, luabridge3_output_config, api_version="1.0.0")
        assert 'k_geo_api_version = "1.0.0"' in out
        assert "get_geo_api_version" in out

    def test_pybind11_emits_api_version_constant_and_attr(self, geo_module, pybind11_output_config):
        out = _generate_with_options(geo_module, pybind11_output_config, api_version="2.3.0")
        assert 'k_geo_api_version = "2.3.0"' in out
        assert 'm.attr("__api_version__")' in out

    def test_no_api_version_no_constant(self, geo_module, luabridge3_output_config):
        out = _generate(geo_module, luabridge3_output_config)
        assert "k_geo_api_version" not in out

    def test_class_filtered_below_api_since(self, geo_module, luabridge3_output_config):
        module = copy.deepcopy(geo_module)
        circle = next(c for c in module.classes if c.name == "Circle")
        circle.api_since = "2.0.0"
        out = _generate_with_options(module, luabridge3_output_config, api_version="1.0.0")
        assert "beginClass<geo::Circle>" not in out
        assert "deriveClass<geo::Circle" not in out

    def test_class_visible_from_api_since(self, geo_module, luabridge3_output_config):
        module = copy.deepcopy(geo_module)
        circle = next(c for c in module.classes if c.name == "Circle")
        circle.api_since = "2.0.0"
        out = _generate_with_options(module, luabridge3_output_config, api_version="2.0.0")
        assert "deriveClass<geo::Circle" in out

    def test_class_excluded_at_api_until(self, geo_module, pybind11_output_config):
        module = copy.deepcopy(geo_module)
        circle = next(c for c in module.classes if c.name == "Circle")
        circle.api_until = "3.0.0"
        out_before = _generate_with_options(module, pybind11_output_config, api_version="2.9.0")
        out_at = _generate_with_options(module, pybind11_output_config, api_version="3.0.0")
        assert "geo::Circle" in out_before
        assert "geo::Circle" not in out_at

    def test_method_filtered_below_api_since(self, geo_module, luabridge3_output_config):
        module = copy.deepcopy(geo_module)
        circle = next(c for c in module.classes if c.name == "Circle")
        for m in circle.methods:
            if m.name == "setRadius":
                m.api_since = "5.0.0"
        out = _generate_with_options(module, luabridge3_output_config, api_version="1.0.0")
        assert "&geo::Circle::setRadius" not in out

    def test_method_visible_from_api_since(self, geo_module, luabridge3_output_config):
        module = copy.deepcopy(geo_module)
        circle = next(c for c in module.classes if c.name == "Circle")
        for m in circle.methods:
            if m.name == "setRadius":
                m.api_since = "5.0.0"
        out = _generate_with_options(module, luabridge3_output_config, api_version="5.0.0")
        assert "&geo::Circle::setRadius" in out

    def test_method_excluded_at_api_until(self, geo_module, luabridge3_output_config):
        module = copy.deepcopy(geo_module)
        circle = next(c for c in module.classes if c.name == "Circle")
        for m in circle.methods:
            if m.name == "getRadius":
                m.api_until = "2.0.0"
        out_before = _generate_with_options(module, luabridge3_output_config, api_version="1.9.0")
        out_at = _generate_with_options(module, luabridge3_output_config, api_version="2.0.0")
        assert "&geo::Circle::getRadius" in out_before
        assert "&geo::Circle::getRadius" not in out_at

    def test_enum_filtered_below_api_since(self, engine_module, luabridge3_output_config):
        module = copy.deepcopy(engine_module)
        for e in module.enums:
            if e.name == "EntityType":
                e.api_since = "10.0.0"
        out = _generate_with_options(module, luabridge3_output_config, api_version="1.0.0")
        assert 'beginNamespace("EntityType")' not in out

    def test_enum_visible_from_api_since(self, engine_module, luabridge3_output_config):
        module = copy.deepcopy(engine_module)
        for e in module.enums:
            if e.name == "EntityType":
                e.api_since = "10.0.0"
        out = _generate_with_options(module, luabridge3_output_config, api_version="10.0.0")
        assert 'beginNamespace("EntityType")' in out

    def test_free_function_filtered_by_api_since(self, engine_module, luabridge3_output_config):
        module = copy.deepcopy(engine_module)
        for fn in module.functions:
            if fn.name == "dot":
                fn.api_since = "99.0.0"
        out = _generate_with_options(module, luabridge3_output_config, api_version="1.0.0")
        assert "&math::dot" not in out

    def test_free_function_visible_from_api_since(self, engine_module, luabridge3_output_config):
        module = copy.deepcopy(engine_module)
        for fn in module.functions:
            if fn.name == "dot":
                fn.api_since = "99.0.0"
        out = _generate_with_options(module, luabridge3_output_config, api_version="99.0.0")
        assert "&math::dot" in out

    def test_api_version_engine_pybind11_constant(self, engine_module, pybind11_output_config):
        out = _generate_with_options(engine_module, pybind11_output_config, api_version="3.1.4")
        assert 'k_engine_api_version = "3.1.4"' in out


# ---------------------------------------------------------------------------
# typesystem — primitive_types and custom_types
# ---------------------------------------------------------------------------

class TestTypesystemScenarioLuaBridge3Generation:
    """Typesystem config integration with luabridge3 generation."""

    def test_typed_class_registered(self, typesystem_module, luabridge3_output_config):
        assert '.beginClass<types::TypedClass>("TypedClass")' in _generate(typesystem_module, luabridge3_output_config)

    def test_int_method_always_visible(self, typesystem_module, luabridge3_output_config):
        assert "&types::TypedClass::getValue" in _generate(typesystem_module, luabridge3_output_config)

    def test_getter_with_ostype_return_absent_by_default(self, typesystem_module, luabridge3_output_config):
        # getTag returns OSType which is in unsupported_types → filtered
        out = _generate(typesystem_module, luabridge3_output_config)
        assert "&types::TypedClass::getTag" not in out

    def test_setter_with_ostype_param_present_by_default(self, typesystem_module, luabridge3_output_config):
        # setTag returns void (not OSType) → NOT filtered; unsupported check is return-type only
        out = _generate(typesystem_module, luabridge3_output_config)
        assert "&types::TypedClass::setTag" in out

    def test_custom_type_unlocks_ostype_getter(self, typesystem_module, luabridge3_output_config):
        ts = TypesystemConfig(custom_types=[CustomTypeEntry(cpp_name="OSType")])
        out = _generate_with_options(typesystem_module, luabridge3_output_config, typesystem=ts)
        assert "&types::TypedClass::getTag" in out

    def test_ostype_free_function_absent_by_default(self, typesystem_module, luabridge3_output_config):
        # Free function overloads using int64_t are present; OSType-param methods are not
        out = _generate(typesystem_module, luabridge3_output_config)
        assert "computeId" in out  # int64_t overloads are fine by default

    def test_primitive_type_mapping_in_overload_template(self, typesystem_module, luabridge3_output_config):
        # luabridge3 overload<type> uses mapped type — verify int64_t → I64 via typesystem
        ts = TypesystemConfig(primitive_types=[PrimitiveTypeEntry(cpp_name="int64_t", python_name="I64")])
        out = _generate_with_options(typesystem_module, luabridge3_output_config, typesystem=ts)
        assert "luabridge::overload<I64>" in out

    def test_no_typesystem_raw_int64_in_overload(self, typesystem_module, luabridge3_output_config):
        out = _generate(typesystem_module, luabridge3_output_config)
        assert "luabridge::overload<int64_t>" in out

    def test_int64_method_visible_without_typesystem(self, typesystem_module, luabridge3_output_config):
        assert "&types::TypedClass::getId" in _generate(typesystem_module, luabridge3_output_config)


class TestTypesystemScenarioPybind11Generation:
    """Typesystem config integration with pybind11 generation."""

    def test_typed_class_registered(self, typesystem_module, pybind11_output_config):
        assert 'py::class_<types::TypedClass' in _generate(typesystem_module, pybind11_output_config)

    def test_getter_with_ostype_return_absent_by_default(self, typesystem_module, pybind11_output_config):
        # getTag returns OSType → filtered; pybind11 also uses unsupported_types
        out = _generate(typesystem_module, pybind11_output_config)
        assert "&types::TypedClass::getTag" not in out

    def test_setter_with_ostype_param_present_by_default(self, typesystem_module, pybind11_output_config):
        # setTag returns void → not filtered
        out = _generate(typesystem_module, pybind11_output_config)
        assert "&types::TypedClass::setTag" in out

    def test_custom_type_unlocks_ostype_getter(self, typesystem_module, pybind11_output_config):
        ts = TypesystemConfig(custom_types=[CustomTypeEntry(cpp_name="OSType")])
        out = _generate_with_options(typesystem_module, pybind11_output_config, typesystem=ts)
        assert "&types::TypedClass::getTag" in out

    def test_int_method_always_visible(self, typesystem_module, pybind11_output_config):
        assert "&types::TypedClass::getValue" in _generate(typesystem_module, pybind11_output_config)

    def test_int64_method_visible_by_default(self, typesystem_module, pybind11_output_config):
        # int64_t is not in unsupported_types, so getId/setId are always present
        out = _generate(typesystem_module, pybind11_output_config)
        assert "&types::TypedClass::getId" in out
        assert "&types::TypedClass::setId" in out

    def test_api_version_with_typesystem(self, typesystem_module, pybind11_output_config):
        ts = TypesystemConfig(custom_types=[CustomTypeEntry(cpp_name="OSType")])
        out = _generate_with_options(typesystem_module, pybind11_output_config, api_version="1.0.0", typesystem=ts)
        assert 'k_typesystem_api_version = "1.0.0"' in out
        assert "&types::TypedClass::getTag" in out


# ---------------------------------------------------------------------------
# Transform pipeline integration — OverloadPriority + ExceptionPolicy
# ---------------------------------------------------------------------------

class TestTransformPipelineIntegration:
    """OverloadPriority and ExceptionPolicy transforms via full parse → transform pipeline."""

    def test_overload_priority_sets_ir_field_on_parsed_overload(self, geo_module):
        module = copy.deepcopy(geo_module)
        specs = [TransformSpec(stage="OverloadPriority", kwargs={
            "class": "Circle",
            "method": "resize",
            "signature": "void resize(double, double)",
            "priority": 0,
        })]
        build_pipeline_from_config(specs).run(module)
        circle = next(c for c in module.classes if c.name == "Circle")
        matched = [m for m in circle.methods if m.name == "resize" and m.overload_priority == 0]
        assert len(matched) == 1
        assert matched[0].parameters[1].type_spelling == "double"

    def test_overload_priority_leaves_other_overload_unchanged(self, geo_module):
        module = copy.deepcopy(geo_module)
        specs = [TransformSpec(stage="OverloadPriority", kwargs={
            "class": "Circle",
            "method": "resize",
            "signature": "void resize(double, double)",
            "priority": 0,
        })]
        build_pipeline_from_config(specs).run(module)
        circle = next(c for c in module.classes if c.name == "Circle")
        single_param = [m for m in circle.methods if m.name == "resize" and len(m.parameters) == 1]
        assert single_param[0].overload_priority is None

    def test_exception_policy_on_parsed_method(self, audio_module):
        module = copy.deepcopy(audio_module)
        specs = [TransformSpec(stage="ExceptionPolicy", kwargs={
            "class": "Reverb",
            "method": "process",
            "policy": "pass_through",
        })]
        build_pipeline_from_config(specs).run(module)
        reverb = next(c for c in module.classes if c.name == "Reverb")
        for m in reverb.methods:
            if m.name == "process":
                assert m.exception_policy == "pass_through"

    def test_exception_policy_wildcard_applies_to_all_classes(self, geo_module):
        module = copy.deepcopy(geo_module)
        specs = [TransformSpec(stage="ExceptionPolicy", kwargs={
            "policy": "abort",
        })]
        build_pipeline_from_config(specs).run(module)
        for cls in module.classes:
            for m in cls.methods:
                assert m.exception_policy == "abort"

    def test_exception_policy_on_free_function(self, engine_module):
        module = copy.deepcopy(engine_module)
        specs = [TransformSpec(stage="ExceptionPolicy", kwargs={
            "function": "dot",
            "policy": "none",
        })]
        build_pipeline_from_config(specs).run(module)
        dot_fn = next(fn for fn in module.functions if fn.name == "dot")
        assert dot_fn.exception_policy == "none"

    def test_unmatched_stages_detected_after_transform(self, geo_module):
        module = copy.deepcopy(geo_module)
        specs = [TransformSpec(stage="suppress_method", kwargs={
            "class": "NonExistentClass",
            "pattern": "nonExistentMethod",
        })]
        pipeline = build_pipeline_from_config(specs)
        pipeline.run(module)
        unmatched = pipeline.unmatched_stages()
        assert len(unmatched) == 1
        assert "suppress_method" in unmatched[0]

    def test_matched_stage_not_in_unmatched(self, geo_module):
        module = copy.deepcopy(geo_module)
        specs = [TransformSpec(stage="suppress_method", kwargs={
            "class": "Circle",
            "pattern": "getRadius",
        })]
        pipeline = build_pipeline_from_config(specs)
        pipeline.run(module)
        assert pipeline.unmatched_stages() == []
