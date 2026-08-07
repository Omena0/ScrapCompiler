from __future__ import annotations

from typing import Any

from ..types import Gate


class TimingAnalyzer:
    """Analyze gate timing and critical paths.

    Computes tick depths, fan-in/fan-out counts, and critical paths.
    """

    def __init__(self, gates: list[Gate]):
        self.gates = gates
        self.depth: dict[int, int] = {}
        self.fan_in: dict[int, int] = {}
        self.fan_out: dict[int, int] = {}
        self.critical_path: list[int] = []

    def analyze(self) -> dict[str, Any]:
        self._compute_depths()
        self._compute_fan_counts()
        self._find_critical_path()
        return {
            "depths": dict(self.depth),
            "fan_in": dict(self.fan_in),
            "fan_out": dict(self.fan_out),
            "critical_path": self.critical_path,
            "max_depth": max(self.depth.values()) if self.depth else 0,
            "total_gates": len(self.gates),
        }

    def _compute_depths(self) -> None:
        memo: dict[int, int] = {}
        for gate in self.gates:
            self._depth(gate.key, memo, set())
        self.depth = memo

    def _depth(self, gate_id: int, memo: dict[int, int], visiting: set[int]) -> int:
        if gate_id in memo:
            return memo[gate_id]
        if gate_id in visiting:
            raise ValueError("IR gates cannot contain a dependency cycle")
        visiting.add(gate_id)
        gate = self._find_gate(gate_id)
        if not gate or not gate.inputs:
            result = 0
        else:
            result = max(self._depth(src, memo, visiting) for src in gate.inputs) + 1
        visiting.discard(gate_id)
        memo[gate_id] = result
        return result

    def _compute_fan_counts(self) -> None:
        for gate in self.gates:
            self.fan_in[gate.key] = len(gate.inputs)
        for gate in self.gates:
            for src in gate.inputs:
                self.fan_out[src] = self.fan_out.get(src, 0) + 1

    def _find_critical_path(self) -> None:
        if not self.depth:
            return
        max_depth = max(self.depth.values())
        end_gates = [g for g in self.gates if self.depth.get(g.key) == max_depth]
        if not end_gates:
            return
        path: list[int] = []
        current = end_gates[0]
        while current:
            path.append(current.key)
            if not current.inputs:
                break
            next_gate = max(
                (self._find_gate(src) for src in current.inputs),
                key=lambda g: self.depth.get(g.key, 0) if g else -1,
                default=None,
            )
            if not next_gate or self.depth.get(next_gate.key, -1) >= self.depth.get(
                current.key, -1
            ):
                break
            current = next_gate
        self.critical_path = path

    def _find_gate(self, gate_id: int) -> Gate | None:
        for gate in self.gates:
            if gate.key == gate_id:
                return gate
        return None
