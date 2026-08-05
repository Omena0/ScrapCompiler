from .compiler import ScrapCompiler
import json

with open('ast.json') as f:
    ast = json.load(f)

compiler = ScrapCompiler(ast)
gates = compiler.compile()

IR = ScrapCompiler.gates_to_ir(gates)

print(IR)
