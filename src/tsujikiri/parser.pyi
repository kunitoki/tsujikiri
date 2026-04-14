from tsujikiri.clang_base_enumerations import AccessSpecifier as AccessSpecifier, AvailabilityKind as AvailabilityKind, CursorKind as CursorKind
from tsujikiri.configurations import SourceConfig as SourceConfig
from tsujikiri.ir import IRBase as IRBase, IRClass as IRClass, IRConstructor as IRConstructor, IREnum as IREnum, IREnumValue as IREnumValue, IRField as IRField, IRFunction as IRFunction, IRMethod as IRMethod, IRModule as IRModule, IRParameter as IRParameter, IRUsingDeclaration as IRUsingDeclaration

def parse_translation_unit(source: SourceConfig, namespaces: list[str], module_name: str) -> IRModule: ...
