from __future__ import annotations

from typing import Callable

from ..types import Gate

GateValues = dict[int, int]
GateCallback = Callable[[int, int, GateValues], None]


class SimulationResult:
    """Result of a simulation run."""

    def __init__(
        self,
        values: GateValues,
        ticks: int,
        changed: list[tuple[int, int, int]] | None = None,
    ):
        self.values = values
        self.ticks = ticks
        self.changed = changed or []

    def get(self, gate_id: int) -> int | None:
        return self.values.get(gate_id)

    def to_dict(self) -> dict[int, int]:
        return dict(self.values)


class StepSimulator:
    """Step-by-step gate-level simulator for compile-time analysis.

    Supports tick-by-tick simulation, event callbacks, breakpoints, and waveform tracing.
    """

    def __init__(self, gates: list[Gate], initial_values: GateValues | None = None):
        self.gates = sorted(gates, key=lambda g: g.key)
        self.values: GateValues = dict(initial_values or {})
        self.ticks = 0
        self.history: list[GateValues] = []
        self.callbacks: list[GateCallback] = []
        self.breakpoints: set[int] = set()

    def add_callback(self, callback: GateCallback) -> StepSimulator:
        self.callbacks.append(callback)
        return self

    def add_breakpoint(self, gate_id: int) -> StepSimulator:
        self.breakpoints.add(gate_id)
        return self

    def step(self) -> SimulationResult:
        changed: list[tuple[int, int, int]] = []
        new_values = dict(self.values)

        for gate in self.gates:
            if gate.prefix == "IN":
                continue
            inputs = [self.values.get(src, 0) for src in gate.inputs]
            old_val = self.values.get(gate.key, 0)
            new_val = self._evaluate(gate.type, inputs)
            if new_val != old_val:
                changed.append((gate.key, old_val, new_val))
                new_values[gate.key] = new_val

        self.values = new_values
        self.ticks += 1
        self.history.append(dict(self.values))

        for callback in self.callbacks:
            for gate_id, old_val, new_val in changed:
                callback(gate_id, new_val, self.values)

        return SimulationResult(self.values, self.ticks, changed)

    def run(self, max_ticks: int = 1000) -> SimulationResult:
        result = self.step()
        for _ in range(max_ticks - 1):
            if not result.changed:
                break
            result = self.step()
        return result

    def _evaluate(self, gate_type: str, inputs: list[int]) -> int:
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
        elif gate_type == "SWITCH":
            return inputs[0] if inputs else 0
        elif gate_type == "LAMP":
            return inputs[0] if inputs else 0
        return 0
