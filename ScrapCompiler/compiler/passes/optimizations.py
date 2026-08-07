from __future__ import annotations

from typing import Any

from ..types import Gate
from .base import CompilerPass, PassResult


class ConstantPropagationPass(CompilerPass):
    """Propagate constant values through combinational logic.

    Replaces gates with constant inputs with their computed values,
    enabling further optimizations like dead code elimination.

    This pass identifies SWITCH gates with no inputs (constant sources)
    and propagates their values through the gate network, replacing
    downstream gates whose all inputs are known constants.
    """

    name = "constant_propagation"
    description = "Propagate constant values through combinational logic"

    def run(
        self, gates: list[Gate], context: dict[str, Any] | None = None
    ) -> PassResult:
        """Execute constant propagation on the gate list.

        Args:
            gates: The list of gates to process.
            context: Optional context dictionary (unused).

        Returns:
            PassResult with propagated constants and statistics.
        """
        constants: dict[int, int] = {}
        changed = False
        new_gates: list[Gate] = []

        for gate in gates:
            if gate.prefix == "IN" or gate.type == "SWITCH":
                new_gates.append(gate)
                if gate.type == "SWITCH" and not gate.inputs:
                    constants[gate.key] = gate.default_state
                continue

            input_vals: list[int] = []
            all_constant = True
            for src in gate.inputs:
                if src in constants:
                    input_vals.append(constants[src])
                else:
                    all_constant = False
                    break

            if all_constant and input_vals:
                result = self._evaluate(gate.type, input_vals)
                constants[gate.key] = result
                changed = True
            else:
                new_gates.append(gate)

        return PassResult(
            new_gates,
            modified=changed,
            stats={"constants_propagated": len(constants)},
        )

    def _evaluate(self, gate_type: str, inputs: list[int]) -> int:
        """Evaluate a gate type with given input values.

        Args:
            gate_type: The type of gate (XOR, AND, OR, etc.).
            inputs: List of input values (0 or 1).

        Returns:
            The output value of the gate.
        """
        if gate_type == "XOR":
            return sum(inputs) % 2
        elif gate_type == "AND":
            return 1 if all(inputs) else 0
        elif gate_type == "OR":
            return 1 if any(inputs) else 0
        elif gate_type == "NOT":
            return 1 - inputs[0] if inputs else 0
        elif gate_type == "NAND":
            return 0 if all(inputs) else 1
        elif gate_type == "NOR":
            return 0 if any(inputs) else 1
        elif gate_type == "XNOR":
            return 1 if sum(inputs) % 2 == 0 else 0
        return 0


class DeadCodeEliminationPass(CompilerPass):
    """Remove gates whose outputs are never used.

    Identifies and removes gates that do not contribute to any
    output or observable behavior, reducing circuit size.

    Requires a dependency map from the timing analyzer to identify
    which gates are actually used.
    """

    name = "dead_code_elimination"
    description = "Remove unused gates"

    def run(
        self, gates: list[Gate], context: dict[str, Any] | None = None
    ) -> PassResult:
        """Execute dead code elimination on the gate list.

        Args:
            gates: The list of gates to process.
            context: Optional context with dependency information.

        Returns:
            PassResult with unused gates removed and statistics.
        """
        used: set[int] = set()

        for gate in gates:
            if gate.prefix == "OUT":
                used.add(gate.key)
            for src in gate.inputs:
                used.add(src)

        new_gates = [g for g in gates if g.key in used]
        removed = len(gates) - len(new_gates)

        return PassResult(
            new_gates,
            modified=removed > 0,
            stats={"gates_removed": removed},
        )


class CommonSubexpressionEliminationPass(CompilerPass):
    """Identify and merge common subexpressions.

    When two or more gates compute the same function on the same
    inputs, this pass replaces duplicates with references to a
    single shared gate, reducing redundancy.
    """

    name = "cse"
    description = "Common subexpression elimination"

    def run(
        self, gates: list[Gate], context: dict[str, Any] | None = None
    ) -> PassResult:
        """Execute common subexpression elimination on the gate list.

        Args:
            gates: The list of gates to process.
            context: Optional context dictionary (unused).

        Returns:
            PassResult with merged subexpressions and statistics.
        """
        signatures: dict[tuple[str, tuple[int, ...], bool], int] = {}
        replacements: dict[int, int] = {}
        new_gates: list[Gate] = []

        for gate in gates:
            if not gate.inputs or gate.prefix == "IN":
                new_gates.append(gate)
                continue

            sig = (gate.type, tuple(sorted(gate.inputs)), gate.prefix != "")
            if sig in signatures:
                replacements[gate.key] = signatures[sig]
            else:
                signatures[sig] = gate.key
                new_gates.append(gate)

        for gate in new_gates:
            gate.inputs = [replacements.get(src, src) for src in gate.inputs]

        return PassResult(
            new_gates,
            modified=bool(replacements),
            stats={"common_subexpressions": len(replacements)},
        )
