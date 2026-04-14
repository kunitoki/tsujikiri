from _typeshed import Incomplete
from tsujikiri.configurations import FilterConfig as FilterConfig, FilterPattern as FilterPattern
from tsujikiri.ir import IRClass as IRClass, IRModule as IRModule

class FilterEngine:
    cfg: Incomplete
    def __init__(self, filter_config: FilterConfig) -> None: ...
    def apply(self, module: IRModule) -> None: ...
