from __future__ import annotations

from typing import Any

from ..passes.base import PassContext, PassResult
from ..types import Gate


class OptimizationPass(PassContext):
    """Base class for optimization passes that can modify gates."""

    def run(
        self, gates: list[Gate], context: dict[str, Any] | None = None
    ) -> PassResult:
        raise NotImplementedError
