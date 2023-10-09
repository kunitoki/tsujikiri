import yaml
from copy import deepcopy
from pathlib import Path
from typing import Any, List

def list_union(lhs: List[Any], rhs: List[Any]) -> List[Any]:
    result = deepcopy(lhs)
    for x in rhs:
        if x not in result:
            result.append(x)
    return result

class InspectorConfig(yaml.YAMLObject):
    yaml_tag = u'!InspectorConfig'

    def __init__(self, **kwargs):
        #import pprint
        #pprint.pprint(kwargs)
        self.source_path = kwargs.get("source_path", None)
        self.parse_args = list_union(kwargs.get("parse_args", []), ["-x", "c++", "-DNDEBUG=1"])
        self.namespace = kwargs.get("namespace", "std")
        self.skip_classes = kwargs.get("skip_classes", [])
        self.skip_methods = kwargs.get("skip_methods", [])
        self.internal_classes = kwargs.get("internal_classes", [])
        self.class_tweaks = kwargs.get("class_tweaks", {})

    @staticmethod
    def constructor(loader, node):
        return InspectorConfig(**loader.construct_mapping(node, deep=True))

class GeneratorConfig(yaml.YAMLObject):
    yaml_tag = u'!GeneratorConfig'

    def __init__(self, **kwargs):
        self.line_comment = kwargs.get("line_comment", "")
        self.prologue = kwargs.get("prologue", "")
        self.epilogue = kwargs.get("epilogue", "")
        self.module_name = kwargs.get("module_name", "")
        self.class_begin = kwargs.get("class_begin", "")
        self.class_end = kwargs.get("class_end", "")
        self.class_derived_begin = kwargs.get("class_derived_begin", "")
        self.class_methods_begin = kwargs.get("class_methods_begin", "")
        self.class_methods_end = kwargs.get("class_methods_end", "")
        self.class_method_begin = kwargs.get("class_method_begin", "")
        self.class_method_end = kwargs.get("class_method_end", "")
        self.class_static_method_begin = kwargs.get("class_static_method_begin", "")
        self.class_static_method_end = kwargs.get("class_static_method_end", "")
        self.class_overloaded_method_begin = kwargs.get("class_overloaded_method_begin", "")
        self.class_overloaded_method_end = kwargs.get("class_overloaded_method_end", "")
        self.class_overloaded_static_method_begin = kwargs.get("class_overloaded_static_method_begin", "")
        self.class_overloaded_static_method_end = kwargs.get("class_overloaded_static_method_end", "")
        self.class_overload_const_definition = kwargs.get("class_overload_const_definition", "")

    @staticmethod
    def constructor(loader, node):
        return GeneratorConfig(**loader.construct_mapping(node, deep=True))

yaml.add_constructor(InspectorConfig.yaml_tag, InspectorConfig.constructor)
yaml.add_constructor(GeneratorConfig.yaml_tag, GeneratorConfig.constructor)

def load_inspector_config(config_file: Path) -> InspectorConfig:
    with open(config_file, 'r') as f:
        return yaml.load(f.read(), Loader=yaml.Loader)

def load_generator_config(config_file: Path) -> GeneratorConfig:
    with open(config_file, 'r') as f:
        return yaml.load(f.read(), Loader=yaml.Loader)
