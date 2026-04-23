from tsujikiri.configurations import SourceConfig as SourceConfig
from tsujikiri.ir import IRBase as IRBase, IRClass as IRClass, IRConstructor as IRConstructor, IREnum as IREnum, IREnumValue as IREnumValue, IRField as IRField, IRFunction as IRFunction, IRMethod as IRMethod, IRModule as IRModule, IRParameter as IRParameter, IRUsingDeclaration as IRUsingDeclaration
from tsujikiri.tir import TIRModule as TIRModule, upgrade_module as upgrade_module

def parse_translation_unit(source: SourceConfig, namespaces: list[str], module_name: str, *, verbose: bool = False) -> TIRModule: ...
