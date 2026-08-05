from __future__ import annotations

from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class IrGate:
    id: int
    prefix: str
    x: int
    y: int
    z: int
    type: str
    inputs: list[int]
    value_type: str = 'bit'


def parse_ir(ir: str) -> list[IrGate]:
    """Parse IR text with explicit ids into a list of gate definitions."""
    id_to_type = _extract_type_annotations(ir)
    gates: list[IrGate] = []

    for line in ir.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue

        if ':' not in stripped:
            raise ValueError(f"Invalid IR line, missing id prefix: {line}")

        id_text, remainder = stripped.split(':', 1)
        id_text = id_text.strip()
        try:
            gate_id = int(id_text)
        except ValueError as error:
            raise ValueError(f"Invalid IR id: {id_text}") from error

        tokens = remainder.strip().split()
        if len(tokens) < 4:
            raise ValueError(f"Invalid IR gate line: {line}")

        prefix = ''
        if tokens[0] in {'IN', 'OUT'}:
            prefix = tokens[0]
            tokens = tokens[1:]

        x = int(tokens[0])
        y = int(tokens[1])
        z = int(tokens[2])
        gate_type = tokens[3]
        inputs = [int(token) for token in tokens[4:]]

        gates.append(
            IrGate(
                gate_id,
                prefix,
                x,
                y,
                z,
                gate_type,
                inputs,
                id_to_type.get(gate_id, 'bit'),
            )
        )
    return gates


def extract_type_comments(ir: str) -> dict[str, list[int]]:
    """Extract type comment groups from IR text."""
    groups: dict[str, list[int]] = {}
    for line in ir.splitlines():
        stripped = line.strip()
        if not stripped.startswith('#'):
            continue

        comment = stripped[1:].strip()
        if ':' not in comment:
            continue

        ids_text, type_name = comment.split(':', 1)
        ids = _parse_id_ranges(ids_text.strip())
        groups[type_name.strip()] = ids
    return groups

def simulate_ir(ir: str, input_values: dict[int, int] | dict[int, list[int]] | list[int] | tuple[int, ...] | None = None) -> dict[int, int]:
    """Simulate IR by evaluating every gate and returning values by id."""
    if input_values is None:
        input_values = {}

    gates = parse_ir(ir)
    _, ordered_groups = _build_input_groups(gates)
    values = _resolve_input_group_values(input_values, ordered_groups)

    for gate in gates:
        if gate.prefix == 'IN':
            continue

        inputs = [values[input_id] for input_id in gate.inputs]

        if gate.type == 'NOT':
            if len(inputs) == 0:
                values[gate.id] = 1
            elif len(inputs) == 1:
                values[gate.id] = 0 if inputs[0] else 1
            else:
                raise ValueError(f"NOT gate {gate.id} requires exactly one input")
            continue

        if gate.type == 'OR':
            values[gate.id] = 1 if any(inputs) else 0
            continue

        if gate.type == 'AND':
            values[gate.id] = 1 if all(inputs) else 0
            continue

        if gate.type == 'XOR':
            values[gate.id] = 1 if sum(inputs) % 2 else 0
            continue

        if gate.type == 'NAND':
            values[gate.id] = 0 if all(inputs) else 1
            continue

        if gate.type == 'NOR':
            values[gate.id] = 0 if any(inputs) else 1
            continue

        if gate.type == 'XNOR':
            values[gate.id] = 0 if sum(inputs) % 2 else 1
            continue

        raise ValueError(f"Unsupported gate type for simulation: {gate.type}")

    return _collect_output_values(values, gates)

def _parse_id_ranges(text: str) -> list[int]:
    ids: list[int] = []
    for part in text.split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            bounds = part.split('-', 1)
            if len(bounds) != 2:
                raise ValueError(f"Invalid id range: {part}")
            start = int(bounds[0])
            end = int(bounds[1])
            if start > end:
                raise ValueError(f"Invalid id range: {part}")
            ids.extend(range(start, end + 1))
        else:
            ids.append(int(part))
    return ids


def _extract_type_annotations(ir: str) -> dict[int, str]:
    annotations: dict[int, str] = {}
    groups = extract_type_comments(ir)
    for type_name, ids in groups.items():
        for gate_id in ids:
            annotations[gate_id] = type_name
    return annotations


def _build_input_groups(gates: list[IrGate]) -> tuple[dict[int, list[int]], list[tuple[list[int], str]]]:
    groups: dict[int, list[int]] = {}
    inputs = sorted((gate for gate in gates if gate.prefix == 'IN'), key=lambda gate: gate.id)
    ordered_groups: list[tuple[list[int], str]] = []
    current: list[IrGate] = []

    def flush_group() -> None:
        if not current:
            return
        ids = [gate.id for gate in current]
        ordered_groups.append((ids, current[0].value_type))
        for gate in current:
            groups[gate.id] = ids

    for gate in inputs:
        if not current:
            current.append(gate)
            continue
        last = current[-1]
        if (
            gate.value_type != last.value_type
            or gate.z != last.z
            or gate.id != last.id + 1
            or gate.y != last.y + 1
        ):
            flush_group()
            current = [gate]
        else:
            current.append(gate)
    flush_group()
    return groups, ordered_groups


def _cast_to_bits(raw_value: int | list[int], type_name: str, ids: list[int]) -> dict[int, int]:
    if isinstance(raw_value, list):
        if len(raw_value) != len(ids):
            raise ValueError(f"Expected {len(ids)} bits for {type_name}, got {len(raw_value)}")
        return dict(zip(ids, raw_value))

    if not isinstance(raw_value, int):
        raise ValueError(f"Unsupported raw input type for {type_name}: {type(raw_value).__name__}")

    width = len(ids)
    if type_name.startswith('u') or type_name.startswith('i'):
        mask = (1 << width) - 1
        value = raw_value & mask
    else:
        value = 1 if raw_value else 0

    bits = [(value >> index) & 1 for index in range(width)]
    return {gate_id: bit for gate_id, bit in zip(ids, bits)}


def _resolve_input_group_values(
    input_values: dict[int, int] | dict[int, list[int]] | list[int] | tuple[int, ...],
    ordered_groups: list[tuple[list[int], str]],
) -> dict[int, int]:
    values: dict[int, int] = {}
    if isinstance(input_values, (list, tuple)):
        flat_values = list(input_values)
        for idx, (group, type_name) in enumerate(ordered_groups):
            raw_value = flat_values[idx] if idx < len(flat_values) else 0
            values.update(_cast_to_bits(raw_value, type_name, group))
        return values

    if isinstance(input_values, dict):
        # Prefer group-level values keyed by the first gate id; fall back to per-bit values.
        for group, type_name in ordered_groups:
            first_id = group[0]
            if first_id in input_values:
                raw_value = input_values[first_id]
                values.update(_cast_to_bits(raw_value, type_name, group))
                continue
            for gate_id in group:
                if gate_id in input_values:
                    raw_value = input_values[gate_id]
                    if isinstance(raw_value, int):
                        values[gate_id] = raw_value & 1
                    else:
                        raise ValueError(f"Bit input values must be ints for gate {gate_id}")
                else:
                    values[gate_id] = 0
        return values

    raise ValueError('Unsupported input_values type')


def _collect_output_values(values: dict[int, int], gates: list[IrGate]) -> int | list[int] | dict[int, int]:
    output_gates = [gate for gate in gates if gate.prefix == 'OUT']
    if not output_gates:
        return values

    output_gates.sort(key=lambda gate: gate.id)
    output_ids = [gate.id for gate in output_gates]
    if len(output_ids) == 1:
        return values[output_ids[0]]

    if all(gate.value_type == 'bit' for gate in output_gates):
        return sum(values[gate_id] << index for index, gate_id in enumerate(output_ids))

    return [values[gate_id] for gate_id in output_ids]

