import sys
import os
from collections import defaultdict
from clang import cindex
from pathlib import Path
from typing import Dict, Optional

from clang_base_enumerations import CursorKind, AccessSpecifier

from configurations import load_inspector_config, load_generator_config

#==================================================================================================

class Context(object):
    class_map = {}
    class_inheritance_map = {}
    class_inner = {}
    class_field_map = {}
    class_qualified_map = {}
    done_classes = set()

    def __init__(self, inspector_config: Path, generator_config: Path):
        self.inspector_config = load_inspector_config(inspector_config)
        self.generator_config = load_generator_config(generator_config)

#==================================================================================================

def to_camel_case(string: str) -> str:
   temp = string.split('_')
   return temp[0] + "".join(f"{x[0].title()}{x[1:]}" for x in temp[1:] if x)

#==================================================================================================

def skip_class_method(class_name: str, method_name: str) -> bool:
    skip_table = {}

    return method_name.strip() in skip_table.get(class_name.strip(), {})

#==================================================================================================

def print_class_fields(context: Context, class_context: Dict[str, str], c):
    all_fields = defaultdict(list)
    for f in filter(lambda x: x.kind == CursorKind.FIELD_DECL, c.get_children()):
        if f.access_specifier != AccessSpecifier.PUBLIC: # or m.spelling in context.inspector_config.skip_fields:
            continue
        all_fields[f.spelling].append(f)

    for fs in all_fields.values():
        for f in fs:
            print(c.spelling, "> ", f.type.spelling, " ", f.spelling)

#==================================================================================================

def print_class_methods(context: Context, class_context: Dict[str, str], c):
    all_methods = defaultdict(list)
    for m in filter(lambda x: x.kind == CursorKind.CXX_METHOD, c.get_children()):
        if m.access_specifier != AccessSpecifier.PUBLIC or m.spelling in context.inspector_config.skip_methods:
            continue
        all_methods[m.spelling].append(m)

    methods_text = []
    for _, ms in all_methods.items():
        for m in ms:
            is_overload = len(ms) > 1
            is_static_method = m.is_static_method()
            is_const_method = m.is_const_method()

            method_comment = ""
            method_spelling = m.spelling
            method_name = m.spelling
            method_args = [arg.type.spelling for arg in m.get_arguments()]
            method_return = m.result_type.spelling

            # TODO iterate types, if any unknown types, we cannot export the method
            if m.result_type.spelling in ["CFStringRef", "OSType"]:
                method_comment = f"{context.generator_config.line_comment} "

            # TODO operators needs to be handled separately, or allow separately tag methods
            if method_name.startswith("operator"):
                method_comment = f"{context.generator_config.line_comment} "

            if is_static_method:
                if is_overload:
                    method_begin = context.generator_config.class_overloaded_static_method_begin
                    method_end = context.generator_config.class_overloaded_static_method_end
                else:
                    method_begin = context.generator_config.class_static_method_begin
                    method_end = context.generator_config.class_static_method_end
            else:
                if is_overload:
                    method_begin = context.generator_config.class_overloaded_method_begin
                    method_end = context.generator_config.class_overloaded_method_end
                else:
                    method_begin = context.generator_config.class_method_begin
                    method_end = context.generator_config.class_method_end

            method_context = {
                "method_comment": method_comment,
                "method_name": method_name,
                "method_args": ", ".join(method_args),
                "method_return": method_return,
                "method_spelling": method_spelling,
                "method_is_const": context.generator_config.class_overload_const_definition if is_const_method else ""
            }

            method_context.update(class_context)

            methods_text.append(method_begin.format(**method_context) + method_end.format(**method_context))

    if methods_text:
        print(context.generator_config.class_methods_begin.format(**class_context))
        print("\n".join(methods_text))
        print(context.generator_config.class_methods_end.format(**class_context))

    return len(methods_text)

#==================================================================================================

def print_class(context: Context, module_name: str, c, parent = None, parent_variable_name = None):
    if c.spelling in context.done_classes or (c.access_specifier != AccessSpecifier.PUBLIC and c.access_specifier != AccessSpecifier.INVALID):
        return

    #if c.spelling == "Upload":
    #print(">>>>>>>>>>>>>>>>> ", c.spelling, " ", c.access_specifier == AccessSpecifier.PUBLIC)
    #print("JUCE_API" in [x.spelling for x in c.get_tokens()])

    # Check inheritance tree
    base = None
    if c.spelling in context.class_inheritance_map:
        bases = context.class_inheritance_map[c.spelling] or []
        if len(bases) > 1:
            print(f"// Multiple bases found for {c.spelling}: {''.join(bases)}")
        for ib in bases:
            base = ib
            if ib.spelling not in context.done_classes:
                print_class(context, module_name, ib)
            break

    # Start reasoning on the class
    class_name = c.spelling
    class_base_name = base.spelling if base else ""
    if parent:
        class_variable_name = to_camel_case(f"class_{parent.spelling}_{class_name}")
        qualified_class_name = f"{parent.spelling}::{c.spelling}"
    else:
        class_variable_name = to_camel_case(f"class_{class_name}")
        qualified_class_name = f"{c.spelling}"

    if not parent_variable_name:
        parent_variable_name = context.generator_config.module_name

    class_context = {
        "class_name": class_name,
        "class_base_name": class_base_name,
        "class_variable_name": class_variable_name,
        "parent_variable_name": parent_variable_name,
        "qualified_class_name": qualified_class_name,
        "module_name": module_name
    }

    if base is not None:
        print(context.generator_config.class_derived_begin.format(**class_context))
    else:
        print(context.generator_config.class_begin.format(**class_context))

    num_methods = print_class_methods(context, class_context, c)
    print_class_fields(context, class_context, c)

    print(context.generator_config.class_end.format(**class_context))

    if c.spelling in context.class_inner:
        for ic in context.class_inner[c.spelling]:
            print_class(context, module_name, ic, c, class_variable_name)

    if num_methods > 0:
        context.done_classes.add(c.spelling)

#==================================================================================================

def run_main(inspector_name: str, generator_name: str, single_classname: Optional[str]):
    # Reason about paths
    this_path = Path(__file__).parent
    base_path = this_path.parent.parent.parent

    # Load the configurations for the module
    context = Context(
        inspector_config = this_path / "configs" / "inspectors" / f"{inspector_name}.yaml",
        generator_config = this_path / "configs" / "generators" / f"{generator_name}.yaml")

    # Parse the module and return the translation unit
    source_path = base_path / context.inspector_config.source_path
    if not source_path.exists():
        raise FileNotFoundError(source_path.resolve())

    index = cindex.Index.create()
    translation_unit = index.parse(source_path.absolute(), args=context.inspector_config.parse_args)
    top_level = translation_unit.cursor.get_children()

    # Filter namespace
    namespace = []
    for entry in top_level:
        if entry.kind == CursorKind.NAMESPACE and entry.spelling == context.inspector_config.namespace:
            namespace.append(entry)

    # Extract free functions
    all_functions = []
    for entry in namespace:
        all_functions += [node for node in filter(
            lambda x: x.kind == CursorKind.FUNCTION_DECL, entry.get_children())]

    # Extract all classes
    all_classes = []
    for entry in namespace:
        all_classes += [node for node in filter(
            lambda x: x.kind == CursorKind.CLASS_DECL or x.kind == CursorKind.STRUCT_DECL, entry.get_children())]

    # Store internal mapping tables, build inheritance map
    for c in all_classes:
        bases = [node.referenced for node in filter(
            lambda x: x.kind == CursorKind.CXX_BASE_SPECIFIER, c.get_children())]

        inner_classes = [node for node in filter(
            lambda x: x.access_specifier == AccessSpecifier.PUBLIC and
                (x.kind == CursorKind.CLASS_DECL or x.kind == CursorKind.STRUCT_DECL), c.get_children())]

        context.class_map[c.spelling] = c
        context.class_inheritance_map[c.spelling] = bases
        context.class_inner[c.spelling] = inner_classes

        qualified_name = f"{context.inspector_config.namespace}::{c.spelling}"
        context.class_qualified_map[qualified_name] = c.spelling

    # Second pass: iterate classes and generate code
    print(context.generator_config.prologue.format(**{"module_name": inspector_name}))

    for c in all_classes:
        if c.spelling in context.inspector_config.skip_classes or c.spelling in context.inspector_config.internal_classes:
            continue

        if single_classname is not None and c.spelling != single_classname:
            continue

        print_class(context, inspector_name, c)

    print(context.generator_config.epilogue.format(**{"module_name": inspector_name}))
