from tsujikiri.configurations import AttributeHandlerConfig as AttributeHandlerConfig
from tsujikiri.tir import TIRClass as TIRClass, TIRModule as TIRModule

class AttributeProcessor:
    handlers: dict[str, str]
    def __init__(self, config: AttributeHandlerConfig) -> None: ...
    def apply(self, module: TIRModule) -> None: ...
