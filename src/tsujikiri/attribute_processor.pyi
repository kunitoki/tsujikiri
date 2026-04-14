from tsujikiri.configurations import AttributeHandlerConfig as AttributeHandlerConfig
from tsujikiri.ir import IRClass as IRClass, IRModule as IRModule

class AttributeProcessor:
    handlers: dict[str, str]
    def __init__(self, config: AttributeHandlerConfig) -> None: ...
    def apply(self, module: IRModule) -> None: ...
