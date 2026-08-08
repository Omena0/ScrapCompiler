import json
import sys
import time

from .compiler import ScrapCompiler, ir_to_blueprint
from .parser import parser
from .simulation import simulate_ir


def compile(source_file):
    with open(source_file) as f:
        source = f.read()

    ast = parser.parse(source)

    gates = ScrapCompiler(ast, "-d" in sys.argv).compile()

    return ScrapCompiler.gates_to_ir(gates)

def sim(source_file, input_values):
    IR = compile(source_file)

    return simulate_ir(IR, input_values)

def _prompt_for_int_inputs(ir: str, provided_values: list[int]) -> list[int]:
    """Prompt the user for IntInput values if not enough were provided.

    Args:
        ir: The IR text to analyze for IntInput gates.
        provided_values: Values already provided via command line.

    Returns:
        Complete list of input values including user prompts.
    """
    from .simulation import (
        _build_input_groups,
        _type_width,
        extract_type_comments,
        extract_variable_comments,
        parse_ir,
    )

    gates = parse_ir(ir)
    int_inputs = [g for g in gates if g.prefix == "IN" and g.type == "SWITCH"]

    if not int_inputs:
        return provided_values

    type_groups = extract_type_comments(ir)
    variable_groups = extract_variable_comments(ir)
    _, ordered_groups = _build_input_groups(gates, type_groups, variable_groups)

    if not ordered_groups:
        return provided_values

    values = list(provided_values)

    for group_ids, type_name in ordered_groups[len(values) :]:
        width = _type_width(type_name)
        if width == 1:
            values.append(0)
            continue

        gate = next(g for g in int_inputs if g.id == group_ids[0])
        prompt = f"Enter value for IntInput {gate.id} (default {gate.default_state}): "
        user_input = input(prompt).strip()
        if user_input:
            try:
                values.append(int(user_input))
            except ValueError:
                print(f"Invalid input, using default {gate.default_state}")
                values.append(gate.default_state)
        else:
            values.append(gate.default_state)

    return values

if __name__ == "__main__":
    option = sys.argv[1]
    match option:
        case "ast":
            with open(sys.argv[2]) as f:
                source = f.read()

            ast = parser.parse(source)

            with open("ast.json", "w") as f:
                json.dump(ast, f, indent=2)

        case "compile":
            t1 = time.time()

            IR = compile(sys.argv[2])

            print(f"Took {(time.time()-t1)*1000:.4f} ms.")

            with open("out.ir", "w") as f:
                f.write(IR)

        case "blueprint":
            t1 = time.time()

            IR = compile(sys.argv[2])
            blueprint = ir_to_blueprint(IR)

            print(f"Took {(time.time()-t1)*1000:.4f} ms.")

            with open("out.json", "w") as f:
                json.dump(blueprint, f, indent=2 if '-d' in sys.argv else None)

        case "sim":
            IR = compile(sys.argv[2])
            provided = [int(i) for i in sys.argv[3:]]
            input_values = _prompt_for_int_inputs(IR, provided)
            print(sim(sys.argv[2], input_values))

        case "vis":
            from .visualize import run

            t1 = time.time()
            IR = compile(sys.argv[2])
            print(f"Took {(time.time()-t1)*1000:.4f} ms.")

            run(IR)
