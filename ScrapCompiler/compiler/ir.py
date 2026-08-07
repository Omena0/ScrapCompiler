from __future__ import annotations

from .types import Gate


def gates_to_ir(gates: list[Gate]) -> str:
    """Render positioned gates using explicit IDs and inline type/variable comments."""
    in_gates = sorted(
        [gate for gate in gates if gate.prefix == "IN"], key=lambda g: (g.x, g.y, g.z)
    )
    internal_gates = sorted(
        [gate for gate in gates if gate.prefix == ""], key=lambda g: (g.x, g.y, g.z)
    )
    out_gates = sorted(
        [gate for gate in gates if gate.prefix == "OUT"], key=lambda g: (g.x, g.y, g.z)
    )

    line_ids = {}
    for line, gate in enumerate(in_gates + internal_gates + out_gates, start=1):
        line_ids[gate.key] = line

    variable_all_ids: dict[str, list[int]] = {}
    variable_in_ids: dict[str, list[int]] = {}
    for gate in in_gates + internal_gates + out_gates:
        if gate.variable and gate.prefix in ("IN", "OUT"):
            variable_all_ids.setdefault(gate.variable, []).append(gate.key)
        if gate.variable and gate.prefix == "IN":
            variable_in_ids.setdefault(gate.variable, []).append(gate.key)

    unnamed_in_ids: list[int] = []
    for gate in in_gates:
        if gate.prefix == "IN" and not gate.variable:
            unnamed_in_ids.append(gate.key)

    lines: list[str] = []
    seen_variables: set[str] = set()
    emitted_variable_types: set[str] = set()

    lines.append("\n# Input")
    for gate in in_gates:
        line_id = gate.key

        if gate.variable and gate.variable not in emitted_variable_types:
            in_ids = variable_in_ids.get(gate.variable, [])
            type_name = gate.value_type
            lines.append(f"# {_format_id_ranges(in_ids)}: {type_name}")
            emitted_variable_types.add(gate.variable)

        if gate.variable and gate.variable not in seen_variables:
            ids = variable_all_ids.get(gate.variable, [])
            if ids:
                lines.append(f"# {gate.variable}: {_format_id_ranges(ids)}")
                seen_variables.add(gate.variable)

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

    lines.append("\n# Compute")
    for gate in internal_gates:
        line_id = gate.key

        if gate.variable and gate.variable not in seen_variables:
            ids = variable_all_ids.get(gate.variable, [])
            if ids:
                lines.append(f"# {gate.variable}: {_format_id_ranges(ids)}")
                seen_variables.add(gate.variable)

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

    lines.append("\n# Output")
    for gate in out_gates:
        line_id = gate.key

        if gate.variable and gate.variable not in seen_variables:
            ids = variable_all_ids.get(gate.variable, [])
            if ids:
                lines.append(f"# {gate.variable}: {_format_id_ranges(ids)}")
                seen_variables.add(gate.variable)

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

    return "\n".join(lines)


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
