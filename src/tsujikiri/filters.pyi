from _typeshed import Incomplete
from tsujikiri.configurations import FilterConfig as FilterConfig, FilterPattern as FilterPattern
from tsujikiri.tir import TIRClass as TIRClass, TIRModule as TIRModule

class FilterEngine:
    cfg: Incomplete
    def __init__(self, filter_config: FilterConfig) -> None: ...
    def apply(self, module: TIRModule) -> None: ...
