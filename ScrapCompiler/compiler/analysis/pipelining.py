from __future__ import annotations

from typing import Any

from ..types import Gate
from .timing import TimingAnalyzer


class PipelineAnalyzer:
    """Analyze and suggest pipeline stages for modules."""

    def __init__(self, gates: list[Gate]):
        self.gates = gates
        self.timing = TimingAnalyzer(gates)

    def analyze(self) -> dict[str, Any]:
        timing_info = self.timing.analyze()
        max_depth = timing_info["max_depth"]
        stages = self._suggest_stages(max_depth)
        return {
            "max_depth": max_depth,
            "suggested_stages": stages,
            "stage_count": len(stages),
            "min_ticks": max_depth + 1,
            "timing": timing_info,
        }

    def _suggest_stages(self, max_depth: int) -> list[list[int]]:
        if max_depth <= 1:
            return [[]]
        stage_size = max(1, max_depth // 2)
        stages: list[list[int]] = []
        for i in range(0, max_depth + 1, stage_size):
            stage_gates = [
                g.key for g in self.gates if self.timing.depth.get(g.key, 0) == i
            ]
            stages.append(stage_gates)
        return stages
