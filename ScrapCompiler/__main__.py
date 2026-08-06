from .compiler import ScrapCompiler, ir_to_blueprint
from .simulation import simulate_ir
from .parser import parser
import json
import time
import sys

def compile(source_file):
    with open(source_file) as f:
        source = f.read()

    ast = parser.parse(source)

    gates = ScrapCompiler(ast).compile()

    return ScrapCompiler.gates_to_ir(gates)

def sim(source_file, input_values):
    IR = compile(source_file)

    return simulate_ir(IR, input_values)

if __name__ == '__main__':
    option = sys.argv[1]
    match option:
        case 'compile':
            t1 = time.time()

            IR = compile(sys.argv[2])

            print(f'Took {(time.time()-t1)*1000:.4f} ms.')

            with open('out.ir', 'w') as f:
                f.write(IR)

        case 'blueprint':
            t1 = time.time()

            IR = compile(sys.argv[2])
            blueprint = ir_to_blueprint(IR)

            print(f'Took {(time.time()-t1)*1000:.4f} ms.')

            with open('out.json', 'w') as f:
                json.dump(blueprint, f, indent=2)

        case 'sim':
            print(sim(sys.argv[2], [int(i) for i in sys.argv[3:]]))

