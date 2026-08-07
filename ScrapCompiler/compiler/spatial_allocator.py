from .types import *


class SpatialAllocator:
    """Own gate handles and calculate deterministic spatial IR positions."""

    def __init__(self, compact=True) -> None:
        """Create an empty gate collection."""
        self._gates: dict[int, Gate] = {}
        self._next_key = 0
        self._compact = compact

    def create(
        self,
        gate_type: str,
        inputs: list[int],
        y: int,
        prefix: GatePrefix = "",
        value_type: str = "bit",
        variable: str = "",
        default_state: int = 0,
        is_output_port: bool = False,
        delay: int = 0,
        x: int | None = None,
    ) -> int:
        """Allocate a gate and return its internal handle."""
        key = self._next_key
        self._next_key += 1

        if x is None:
            max_input_x = 0
            for input_key in inputs:
                if input_key in self._gates:
                    max_input_x = max(max_input_x, self._gates[input_key].x)
            x = max_input_x + 1 if inputs else 0

        z = 0
        for gate in self._gates.values():
            if gate.x == x and gate.y == y:
                z += 1

        self._gates[key] = Gate(
            gate_type,
            list(inputs),
            x,
            y,
            z,
            prefix,
            key,
            value_type,
            variable,
            default_state,
            is_output_port,
            delay,
        )
        return key

    def inherit(self, key: int, gate_type: str, value_type: str | None = None) -> None:
        """Retag an existing output gate and clear its inherited inputs."""
        gate = self._get(key)
        gate.type = gate_type
        gate.inputs.clear()
        if value_type is not None:
            gate.value_type = value_type

    def append_inputs(self, key: int, inputs: list[int]) -> None:
        """Connect additional source gates to an existing gate."""
        self._get(key).inputs.extend(inputs)

    def mark_input(self, key: int) -> None:
        """Mark an existing gate handle as an input boundary."""
        self._get(key).prefix = "IN"

    def mark_output(self, key: int) -> None:
        """Mark an existing gate handle as an input boundary."""
        self._get(key).prefix = "OUT"

    def is_output(self, key: int) -> bool:
        """Return whether a handle belongs to an output-prefixed gate."""
        return self._get(key).prefix == "OUT"

    def is_output_port(self, key: int) -> bool:
        """Return whether a handle belongs to a module output port."""
        return self._get(key).is_output_port

    def set_variable(self, key: int, variable: str) -> None:
        """Tag a gate handle with the variable that owns it."""
        self._get(key).variable = variable

    def build(self) -> list[Gate]:
        """Calculate gate depths, resolve stacking, and return gates in allocation order."""
        times: dict[int, int] = {}
        for key in self._gates:
            self._time_for(key, times, set())

        for key, gate in self._gates.items():
            gate.x = times[key]

        xy_groups: dict[tuple[int, int], list[Gate]] = {}
        for gate in self._gates.values():
            pos = (gate.x, gate.y)
            xy_groups.setdefault(pos, []).append(gate)

        for group in xy_groups.values():
            group.sort(key=lambda g: g.key)
            for index, gate in enumerate(group):
                gate.z = index

        return list(self._gates.values())

    def _time_for(self, key: int, times: dict[int, int], visiting: set[int]) -> int:
        """Calculate the depth of a gate in the dependency graph."""
        if key in times:
            return times[key]
        if key in visiting:
            raise ValueError("IR gates cannot contain a dependency cycle")

        visiting.add(key)
        gate = self._get(key)
        if not gate.inputs:
            time = 0

        else:
            if self._compact:
                source_time = min(
                    self._time_for(source, times, visiting) for source in gate.inputs
                )
            else:
                source_time = max(
                    self._time_for(source, times, visiting) for source in gate.inputs
                )
            time = source_time + 1

        visiting.remove(key)
        times[key] = time
        return time

    def _get(self, key: int) -> Gate:
        """Return one allocated gate or raise for an invalid handle."""
        try:
            return self._gates[key]
        except KeyError as error:
            raise ValueError(f"Unknown gate handle: {key}") from error
