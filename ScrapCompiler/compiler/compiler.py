from typing import NoReturn, TypeVar, overload, TypeGuard
from dataclasses import dataclass

@dataclass(slots=True)
class Gate:
    type: str
    inputs: list
    outputs: list

class ScrapCompiler:
    def __init__(self, ast: dict):
        self.ast = ast
        self.modules = {}
        self.variables = {}

    def error(self, name, text) -> NoReturn:
        print(f'{name}: {text}')
        exit(-1)

    @overload
    def expect(self, obj, name, msg): ...
    @overload
    def expect(self, obj, name, msg, value): ...
    def expect[T](self, obj:T, name:str, msg:str, value=None) -> T:
        if not obj if value is None else obj != value:
            self.error(name, msg)

        return obj

    def compile_module(self, name:str, module:dict) -> dict:
        inherit = module.get('inherit', [])

        # Fields
        fields = module.get('fields')
        print(fields)
        fields = self.expect(fields, 'InvalidModule', f"Invalid module {name}, Missing 'fields'")

        # Inputs
        inputs  = fields.get('inputs')
        inputs = self.expect(inputs, 'InvalidFields', f"Invalid module fields: {name}. Missing 'inputs'")

        # Outputs
        outputs = fields.get('outputs')
        outputs = self.expect(outputs, 'InvalidFields', f"Invalid module fields: {name}. Missing 'outputs'")

        # Gates
        gates = module.get('gates')
        gates = self.expect(gates, 'InvalidModule', f"Invalid module {name}, Missing 'gates'")

        print(inputs)
        print(outputs)
        print(gates)

        return {}

    def compile_modules(self, modules:dict) -> dict:
        for name, module in modules.items():
            self.modules[name] = self.compile_module(name, module)

        return self.modules

    def compile(self) -> list[Gate]:
        self.modules = self.compile_modules(self.ast['modules'])

        return []

    @staticmethod
    def gates_to_ir(gates: list[Gate]) -> str:

        return ''

