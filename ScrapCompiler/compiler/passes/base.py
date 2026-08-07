from __future__ import annotations

from typing import Any

from ..types import Gate


class CompilerPass:
    """Base class for compiler analysis and optimization passes.

    All compiler passes should inherit from this class and implement
    the `run` method. Passes can either analyze (read-only) or modify
    the gate list.
    """

    name: str = "base"
    """Unique identifier for this pass."""

    description: str = "Base compiler pass"
    """Human-readable description of what this pass does."""

    def run(
        self, gates: list[Gate], context: dict[str, Any] | None = None
    ) -> PassResult:
        """Execute the pass on the gate list.

        Args:
            gates: The list of gates to process.
            context: Optional context dictionary with pass-specific data.

        Returns:
            PassResult containing the processed gates and metadata.

        Raises:
            NotImplementedError: Must be implemented by subclasses.
        """
        raise NotImplementedError

    def analyze(
        self, gates: list[Gate], context: dict[str, Any] | None = None
    ) -> PassResult:
        """Analyze the gate list without modifying it.

        The default implementation calls `run`, but analysis-only passes
        should override this to avoid side effects.

        Args:
            gates: The list of gates to analyze.
            context: Optional context dictionary with pass-specific data.

        Returns:
            PassResult containing analysis results.
        """
        return self.run(gates, context)


class PassResult:
    """Result of a compiler pass execution.

    Encapsulates the output of a compiler pass, including any modified
    gates, statistics, and errors encountered during execution.
    """

    def __init__(
        self,
        gates: list[Gate],
        modified: bool = False,
        stats: dict[str, Any] | None = None,
        errors: list[str] | None = None,
    ) -> None:
        """Initialize a pass result.

        Args:
            gates: The resulting gate list after the pass.
            modified: Whether the pass modified the gate list.
            stats: Optional statistics collected during the pass.
            errors: Optional list of errors encountered during the pass.
        """
        self.gates: list[Gate] = gates
        self.modified: bool = modified
        self.stats: dict[str, Any] = stats or {}
        self.errors: list[str] = errors or []

    @property
    def success(self) -> bool:
        """Whether the pass completed without errors."""
        return len(self.errors) == 0


class PassContext:
    """Shared context for compiler passes.

    Provides common data structures that passes can use to share
    information, such as type information, timing data, and dependencies.
    """

    def __init__(self) -> None:
        """Initialize an empty pass context."""
        self.variables: dict[str, Any] = {}
        self.types: dict[int, str] = {}
        self.timing: dict[int, int] = {}
        self.dependencies: dict[int, set[int]] = {}
        self.metadata: dict[str, Any] = {}

    def get_gate(self, gate_id: int, gates: list[Gate]) -> Gate | None:
        """Find a gate by its ID in the given gate list.

        Args:
            gate_id: The ID of the gate to find.
            gates: The list of gates to search.

        Returns:
            The gate with the matching ID, or None if not found.
        """
        for gate in gates:
            if gate.key == gate_id:
                return gate
        return None

    def get_dependents(self, gate_id: int, gates: list[Gate]) -> set[int]:
        """Get the set of gates that depend on the given gate.

        Args:
            gate_id: The ID of the gate to query.
            gates: The list of all gates.

        Returns:
            Set of gate IDs that have the given gate as an input.
        """
        if gate_id not in self.dependencies:
            return set()
        return self.dependencies[gate_id]


class PassManager:
    """Manages execution of multiple compiler passes.

    Allows chaining multiple compiler passes together and running
    them in sequence on a gate list.
    """

    def __init__(self) -> None:
        """Initialize an empty pass manager."""
        self.passes: list[CompilerPass] = []
        self.context: PassContext = PassContext()

    def add_pass(self, pass_inst: CompilerPass) -> PassManager:
        """Add a compiler pass to the pipeline.

        Args:
            pass_inst: The compiler pass to add.

        Returns:
            Self for method chaining.
        """
        self.passes.append(pass_inst)
        return self

    def run(self, gates: list[Gate]) -> PassResult:
        """Run all registered passes on the gate list.

        Args:
            gates: The initial list of gates to process.

        Returns:
            PassResult containing the final gates and aggregated statistics.
        """
        current_gates: list[Gate] = gates
        total_stats: dict[str, Any] = {}

        for pass_inst in self.passes:
            result = pass_inst.run(current_gates, self.context.metadata)
            current_gates = result.gates
            total_stats.update(result.stats)

            if not result.success:
                return PassResult(
                    current_gates,
                    modified=result.modified,
                    stats=total_stats,
                    errors=result.errors,
                )

        return PassResult(current_gates, modified=True, stats=total_stats)

    def analyze(self, gates: list[Gate]) -> dict[str, PassResult]:
        """Run all registered passes in analysis mode.

        Args:
            gates: The list of gates to analyze.

        Returns:
            Dictionary mapping pass names to their PassResult.
        """
        results: dict[str, PassResult] = {}
        for pass_inst in self.passes:
            result = pass_inst.analyze(gates, self.context.metadata)
            results[pass_inst.name] = result
        return results
