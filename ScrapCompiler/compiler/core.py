from __future__ import annotations

import json
from typing import Any, NoReturn

from .analysis import *
from .instantiation import InstantiationMixin
from .lowering import LoweringMixin
from .modules import ModulesMixin
from .passes import *
from .resolution import ResolutionMixin
from .spatial_allocator import SpatialAllocator
from .types import *


class ScrapCompiler(ResolutionMixin, LoweringMixin, InstantiationMixin, ModulesMixin):
    """Resolve Scrap types and lower module instances to positioned gate IR."""

    def __init__(self, ast: AstNode, debug: bool = False) -> None:
        """Initialize the compiler with a parsed AST."""
        self.ast = ast
        self.modules: dict[str, AstNode] = {}
        self.variables: SymbolTable = {}
        self.signals: SignalTable = {}
        self.module_types: dict[str, ResolvedType] = {}
        self.debug = debug

        self._module_asts: dict[str, AstNode] = {}
        self._functions: dict[str, AstNode] = {}
        self._allocator: SpatialAllocator = SpatialAllocator()
        self._literal_widths: dict[str, int] = {}
        self._skip_assertions = False

    def error(self, name: str, text: str, node: AstNode | None = None) -> NoReturn:
        """Print a compiler error with optional parser-provided source context."""
        if node is not None:
            source = node.get("error")
            line = node.get("line")
            column = node.get("column")
            if (
                isinstance(source, str)
                and isinstance(line, int)
                and isinstance(column, int)
            ):
                print(source)
                print(" " * max(column - 1, 0) + "^")
                print(f"At line {line}, col {column}")

        print(f"{name}: {text}")
        raise SystemExit(-1)

    def expect[T](
        self,
        value: T,
        name: str,
        message: str,
        expected: object = MISSING,
        node: AstNode | None = None,
    ) -> T:
        """Return a validated value or report a compiler error."""
        valid = bool(value) if expected is MISSING else value == expected
        if not valid:
            self.error(name, message, node)
        return value

    def compile(self) -> list[Gate]:
        """Resolve the AST and lower all top-level statements into IR gates."""
        modules = self.ast.get("modules")

        if not isinstance(modules, dict):
            self.error("InvalidAst", "Missing or invalid 'modules'", self.ast)

        functions = self.ast.get("functions")
        if not isinstance(functions, dict):
            functions = {}

        self._module_asts = modules
        self.compile_modules(modules, functions)
        self.variables = self._resolve_statements(self.ast.get("gates"), {}, self.ast)

        self._allocator = SpatialAllocator(compact=not self.debug)

        self._next_z = 0
        self.signals = self._lower_statements(
            self.ast.get("gates"),
            {},
            {},
            0,
            {},
            False,
            False,
            True,
        )
        gates = self._allocator.build()
        self._validate_assertions(gates)
        return gates

    @staticmethod
    def gates_to_ir(gates: list[Gate]) -> str:
        """Render positioned gates using explicit IDs and inline type/variable comments."""
        in_gates = sorted(
            [gate for gate in gates if gate.prefix == "IN" and gate.type != "OBJECT"],
            key=lambda g: (g.x, g.y, g.z),
        )
        internal_gates = sorted(
            [gate for gate in gates if gate.prefix == "" and gate.type != "OBJECT"],
            key=lambda g: (g.x, g.y, g.z),
        )
        out_gates = sorted(
            [gate for gate in gates if gate.prefix == "OUT" and gate.type != "OBJECT"],
            key=lambda g: (g.x, g.y, g.z),
        )

        {
            gate.key: line
            for line, gate in enumerate(in_gates + internal_gates + out_gates, start=1)
        }
        variable_all_ids: dict[str, list[int]] = {}
        variable_in_ids: dict[str, list[int]] = {}
        for gate in in_gates + internal_gates + out_gates:
            if gate.variable and gate.prefix in ("IN", "OUT"):
                variable_all_ids.setdefault(gate.variable, []).append(gate.key)
            if gate.variable and gate.prefix == "IN":
                variable_in_ids.setdefault(gate.variable, []).append(gate.key)

        unnamed_in_ids: list[int] = []
        unnamed_in_ids.extend(
            gate.key for gate in in_gates if gate.prefix == "IN" and not gate.variable
        )
        seen_variables: set[str] = set()
        emitted_variable_types: set[str] = set()

        lines: list[str] = ["\n# Input"]
        for gate in in_gates:
            line_id = gate.key

            if gate.variable and gate.variable not in emitted_variable_types:
                in_ids = variable_in_ids.get(gate.variable, [])
                type_name = gate.value_type
                lines.append(
                    f"# {ScrapCompiler._format_id_ranges(in_ids)}: {type_name}"
                )
                emitted_variable_types.add(gate.variable)

            if gate.variable and gate.variable not in seen_variables:
                if ids := variable_all_ids.get(gate.variable, []):
                    lines.append(
                        f"# {gate.variable}: {ScrapCompiler._format_id_ranges(ids)}"
                    )
                    seen_variables.add(gate.variable)

            inputs = [str(source) for source in gate.inputs]

            parts = ([gate.prefix] if gate.prefix else []) + [
                str(gate.x),
                str(gate.y),
                str(gate.z),
                gate.type,
                *inputs,
            ]
            if gate.type == "SWITCH" and gate.prefix == "IN" and gate.default_state:
                parts.append(str(gate.default_state))
            if gate.type == "TIMER" and gate.delay:
                parts.append(str(gate.delay))
            lines.append(f"{line_id}: {' '.join(parts)}")

        lines.append("\n# Compute")
        for gate in internal_gates:
            line_id = gate.key

            if gate.variable and gate.variable not in seen_variables:
                if ids := variable_all_ids.get(gate.variable, []):
                    lines.append(
                        f"# {gate.variable}: {ScrapCompiler._format_id_ranges(ids)}"
                    )
                    seen_variables.add(gate.variable)

            inputs = [str(source) for source in gate.inputs]

            parts = ([gate.prefix] if gate.prefix else []) + [
                str(gate.x),
                str(gate.y),
                str(gate.z),
                gate.type,
                *inputs,
            ]
            if gate.type == "SWITCH" and gate.prefix == "IN" and gate.default_state:
                parts.append(str(gate.default_state))
            if gate.type == "TIMER" and gate.delay:
                parts.append(str(gate.delay))
            lines.append(f"{line_id}: {' '.join(parts)}")

        lines.append("\n# Output")
        for gate in out_gates:
            line_id = gate.key

            if gate.variable and gate.variable not in seen_variables:
                if ids := variable_all_ids.get(gate.variable, []):
                    lines.append(
                        f"# {gate.variable}: {ScrapCompiler._format_id_ranges(ids)}"
                    )
                    seen_variables.add(gate.variable)

            if gate.type == "OBJECT" and gate.annotation is not None:
                lines.append(f"# {json.dumps(gate.annotation)}")
                continue

            inputs = [str(source) for source in gate.inputs]

            parts = ([gate.prefix] if gate.prefix else []) + [
                str(gate.x),
                str(gate.y),
                str(gate.z),
                gate.type,
                *inputs,
            ]
            if gate.type == "SWITCH" and gate.default_state:
                parts.append(str(gate.default_state))
            lines.append(f"{line_id}: {' '.join(parts)}")

        object_gates = [
            gate for gate in in_gates + internal_gates + out_gates if gate.type == "OBJECT"
        ]
        for gate in object_gates:
            if gate.annotation is not None:
                lines.append(f"# {json.dumps(gate.annotation)}")

        return "\n".join(lines)

    @staticmethod
    def _format_id_ranges(ids: list[int]) -> str:
        """Format a sorted list of ids as a compact comma/range string."""
        if not ids:
            return ""

        ids = sorted(ids)
        ranges: list[str] = []
        start = prev = ids[0]

        for current in ids[1:]:
            if current == prev + 1:
                prev = current
                continue
            ranges.append(str(start) if start == prev else f"{start}-{prev}")
            start = prev = current

        ranges.append(str(start) if start == prev else f"{start}-{prev}")
        return ",".join(ranges)

    def analyze(self) -> dict[str, Any]:
        """Run full analysis on compiled gates."""
        gates = self._allocator.build()
        timing = TimingAnalyzer(gates)
        timing_info = timing.analyze()
        pipeline = PipelineAnalyzer(gates)
        pipeline_info = pipeline.analyze()
        return {
            "timing": timing_info,
            "pipeline": pipeline_info,
            "gate_count": len(gates),
        }

    def simulate(
        self, inputs: dict[int, int] | None = None, max_ticks: int = 1000
    ) -> SimulationResult:
        """Run step-by-step simulation on compiled gates."""
        gates = self._allocator.build()
        simulator = StepSimulator(gates, inputs)
        return simulator.run(max_ticks)

    def optimize(self, passes: list[str] | None = None) -> PassResult:
        """Run optimization passes on compiled gates."""
        gates = self._allocator.build()
        manager = PassManager()

        if passes is None or "constant_prop" in passes:
            manager.add_pass(ConstantPropagationPass())
        if passes is None or "dead_code" in passes:
            manager.add_pass(DeadCodeEliminationPass())
        if passes is None or "cse" in passes:
            manager.add_pass(CommonSubexpressionEliminationPass())

        return manager.run(gates)

    def _validate_assertions(self, gates: list[Gate]) -> None:
        """Simulate each @assert-decorated module and raise on mismatch."""
        if self._skip_assertions:
            return

        from ..simulation import simulate_ir

        for name, module in self.modules.items():
            decorators = module.get("decorators", [])
            if not isinstance(decorators, list):
                continue

            asserts = [
                d for d in decorators
                if isinstance(d, dict) and d.get("name") == "assert"
            ]
            if not asserts:
                continue

            original_ast = self._module_asts.get(name)
            if not isinstance(original_ast, dict):
                continue

            for decorator in asserts:
                args = decorator.get("args", [])
                if not isinstance(args, list):
                    continue

                input_values: dict[int, int] = {}
                expected_outputs: dict[str, int] = {}
                input_defs = original_ast.get("fields", {}).get("inputs", [])
                output_defs = original_ast.get("fields", {}).get("outputs", [])
                input_names = {
                    d.get("name")
                    for d in input_defs
                    if isinstance(d, dict) and isinstance(d.get("name"), str)
                }
                output_names = {
                    d.get("name")
                    for d in output_defs
                    if isinstance(d, dict) and isinstance(d.get("name"), str)
                }

                for arg in args:
                    if not isinstance(arg, dict) or arg.get("type") != "named_arg":
                        continue
                    field_name = arg.get("name")
                    value_node = arg.get("value")
                    if not isinstance(field_name, str) or not isinstance(value_node, dict):
                        continue
                    if field_name in input_names:
                        value = value_node.get("value")
                        if isinstance(value, int):
                            input_values[field_name] = value
                    elif field_name in output_names:
                        value = value_node.get("value")
                        if isinstance(value, int):
                            expected_outputs[field_name] = value

                if not input_values or not expected_outputs:
                    continue

                call_args = self._build_assert_call_args(original_ast, input_values)
                if call_args is None:
                    continue

                temp_ast: AstNode = {
                    "modules": {
                        name: {
                            k: v
                            for k, v in original_ast.items()
                            if k != "decorators"
                        }
                    },
                    "functions": self.ast.get("functions", {}),
                    "gates": [
                        {
                            "type": "gate",
                            "name": "out",
                            "value": {
                                "type": "new",
                                "value": {
                                    "type": "call",
                                    "name": name,
                                    "args": call_args,
                                },
                            },
                        }
                    ],
                }

                temp_ast["modules"][name]["decorators"] = []

                compiler = ScrapCompiler(temp_ast)
                compiler._skip_assertions = True
                try:
                    compiled = compiler.compile()
                except SystemExit:
                    self.error(
                        "AssertError",
                        f"Failed to compile assertion for module '{name}'",
                        decorator,
                    )

                ir = ScrapCompiler.gates_to_ir(compiled)
                sim_inputs = list(input_values.values())
                result = simulate_ir(ir, sim_inputs)

                if isinstance(result, dict):
                    actual_outputs = result
                elif isinstance(result, int):
                    output_list = list(expected_outputs.keys())
                    actual_outputs = (
                        {output_list[0]: result} if output_list else {}
                    )
                else:
                    actual_outputs = {}

                for output_name, expected in expected_outputs.items():
                    actual = actual_outputs.get(output_name)
                    if actual != expected:
                        self.error(
                            "AssertError",
                            f"Module '{name}' assertion failed: {output_name} expected {expected}, got {actual}",
                            decorator,
                        )

    def _build_assert_call_args(
        self, module: AstNode, input_values: dict[str, int]
    ) -> list[AstNode] | None:
        """Build positional call args for an assertion instantiation."""
        fields = module.get("fields")
        if not isinstance(fields, dict):
            return None
        input_defs = fields.get("inputs", [])
        if not isinstance(input_defs, list):
            return None

        args: list[AstNode] = []
        for definition in input_defs:
            if not isinstance(definition, dict):
                continue
            field_name = definition.get("name")
            if not isinstance(field_name, str):
                continue
            value = input_values.get(field_name)
            if value is None:
                continue
            args.append({"type": "int", "value": value})

        return args or None


__all__ = ["ScrapCompiler"]
