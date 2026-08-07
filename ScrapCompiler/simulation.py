from __future__ import annotations

from dataclasses import dataclass
from typing import cast

_dict_int_int = dict[int, int]
_dict_int_list = dict[int, list[int]]


@dataclass(frozen=True)
class IrGate:
    id: int
    prefix: str
    x: int
    y: int
    z: int
    type: str
    inputs: list[int]
    value_type: str = "bit"
    default_state: int = 0
    delay: int = 0


def parse_ir(ir: str) -> list[IrGate]:
    """Parse IR text with explicit ids into a list of gate definitions."""
    id_to_type = _extract_type_annotations(ir)
    gates: list[IrGate] = []

    for line in ir.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if ":" not in stripped:
            raise ValueError(f"Invalid IR line, missing id prefix: {line}")

        id_text, remainder = stripped.split(":", 1)
        id_text = id_text.strip()
        try:
            gate_id = int(id_text)
        except ValueError as error:
            raise ValueError(f"Invalid IR id: {id_text}") from error

        tokens = remainder.strip().split()
        if len(tokens) < 4:
            raise ValueError(f"Invalid IR gate line: {line}")

        prefix = ""
        if tokens[0] in {"IN", "OUT"}:
            prefix = tokens[0]
            tokens = tokens[1:]

        x = int(tokens[0])
        y = int(tokens[1])
        z = int(tokens[2])
        gate_type = tokens[3]
        default_state = 0
        delay = 0
        if gate_type == "SWITCH" and len(tokens) > 4:
            try:
                default_state = int(tokens[-1])
                inputs = [int(token) for token in tokens[4:-1]]
            except ValueError:
                inputs = [int(token) for token in tokens[4:]]
        elif gate_type == "TIMER" and len(tokens) > 5:
            try:
                delay = int(tokens[-1])
                inputs = [int(token) for token in tokens[4:-1]]
            except ValueError:
                inputs = [int(token) for token in tokens[4:]]
        else:
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
                id_to_type.get(gate_id, "bit"),
                default_state,
                delay,
            )
        )
    return gates


def extract_type_comments(ir: str) -> dict[str, list[int]]:
    """Extract type comment groups from IR text."""
    groups: dict[str, list[int]] = {}
    for line in ir.splitlines():
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue

        comment = stripped[1:].strip()
        if ":" not in comment:
            continue

        ids_text, type_name = comment.split(":", 1)
        ids_text = ids_text.strip()
        if not ids_text or not ids_text[0].isdigit():
            continue
        ids = _parse_id_ranges(ids_text)
        groups.setdefault(type_name.strip(), []).extend(ids)
    return groups


def extract_variable_comments(ir: str) -> dict[str, list[int]]:
    """Extract variable comment groups from IR text."""
    groups: dict[str, list[int]] = {}
    for line in ir.splitlines():
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue

        comment = stripped[1:].strip()
        if ":" not in comment:
            continue

        var_name, ids_text = comment.split(":", 1)
        var_name = var_name.strip()
        ids_text = ids_text.strip()
        if not var_name or not var_name[0].isalpha():
            continue
        ids = _parse_id_ranges(ids_text)
        groups[var_name] = ids
    return groups


def simulate_ir(
    ir: str,
    input_values: (
        dict[int, int] | dict[int, list[int]] | list[int] | tuple[int, ...] | None
    ) = None,
) -> int | list[int] | dict[int, int]:
    """Simulate IR by evaluating every gate and returning values by id."""
    if input_values is None:
        input_values = {}

    gates = parse_ir(ir)
    type_groups = extract_type_comments(ir)
    variable_groups = extract_variable_comments(ir)
    _, ordered_groups = _build_input_groups(gates, type_groups, variable_groups)
    values = _resolve_input_group_values(input_values, ordered_groups)

    for gate in gates:
            if gate.prefix == "IN":
                continue

            inputs = [values[input_id] for input_id in gate.inputs]

            if gate.type == "NOT":
                if not inputs:
                    values[gate.id] = 1
                elif len(inputs) == 1:
                    values[gate.id] = 0 if inputs[0] else 1
                else:
                    raise ValueError(f"NOT gate {gate.id} requires exactly one input")
                continue

            if gate.type == "OR":
                values[gate.id] = 1 if any(inputs) else 0
                continue

            if gate.type == "AND":
                values[gate.id] = 1 if all(inputs) else 0
                continue

            if gate.type == "XOR":
                values[gate.id] = 1 if sum(inputs) % 2 else 0
                continue

            if gate.type == "NAND":
                values[gate.id] = 0 if all(inputs) else 1
                continue

            if gate.type == "NOR":
                values[gate.id] = 0 if any(inputs) else 1
                continue

            if gate.type == "XNOR":
                values[gate.id] = 0 if sum(inputs) % 2 else 1
                continue

            if gate.type == "LAMP":
                values[gate.id] = inputs[0] if inputs else 0
                continue

            if gate.type == "SWITCH":
                values[gate.id] = inputs[0] if inputs else gate.default_state
                continue

            if gate.type == "TIMER":
                values[gate.id] = 0
                continue

            raise ValueError(f"Unsupported gate type for simulation: {gate.type}")

    return _collect_output_values(values, gates)


def _parse_id_ranges(text: str) -> list[int]:
    ids: list[int] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            bounds = part.split("-", 1)
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


def _build_input_groups(
    gates: list[IrGate],
    type_groups: dict[str, list[int]] | None = None,
    variable_groups: dict[str, list[int]] | None = None,
) -> tuple[dict[int, list[int]], list[tuple[list[int], str]]]:
    groups: dict[int, list[int]] = {}
    inputs = sorted(
        (gate for gate in gates if gate.prefix == "IN"), key=lambda gate: gate.id
    )
    ordered_groups: list[tuple[list[int], str]] = []

    if type_groups and variable_groups:
        input_ids = {gate.id for gate in gates if gate.prefix == "IN"}
        variable_input_groups: dict[str, list[int]] = {}
        for var_name, ids in variable_groups.items():
            var_in_ids = [gate_id for gate_id in ids if gate_id in input_ids]
            if var_in_ids:
                variable_input_groups[var_name] = var_in_ids

        used_ids: set[int] = set()
        variable_groups_list: list[tuple[list[int], str]] = []

        for var_name, var_ids in variable_input_groups.items():
            if not var_ids:
                continue
            type_name = gates[var_ids[0] - 1].value_type
            width = _type_width(type_name)
            if len(var_ids) == width:
                variable_groups_list.append((var_ids, type_name))
                used_ids.update(var_ids)

        if variable_groups_list:
            remaining_type_groups: dict[str, list[int]] = {}
            for type_name, ids in type_groups.items():
                remaining = [
                    gate_id
                    for gate_id in ids
                    if gate_id in input_ids and gate_id not in used_ids
                ]
                if remaining:
                    remaining_type_groups[type_name] = remaining

            for type_name, ids in remaining_type_groups.items():
                width = _type_width(type_name)
                for group_ids in _chunk(ids, width):
                    variable_groups_list.append((group_ids, type_name))

            variable_groups_list.sort(key=lambda item: item[0][0])
            for group_ids, type_name in variable_groups_list:
                ordered_groups.append((group_ids, type_name))
                for gate_id in group_ids:
                    groups[gate_id] = group_ids
            return groups, ordered_groups

    if type_groups:
        groups_list: list[tuple[list[int], str]] = []
        input_ids = {gate.id for gate in gates if gate.prefix == "IN"}
        for type_name, ids in type_groups.items():
            width = _type_width(type_name)
            input_ids_for_type = sorted(
                [gate_id for gate_id in ids if gate_id in input_ids]
            )
            for group_ids in _chunk(input_ids_for_type, width):
                groups_list.append((group_ids, type_name))
        groups_list.sort(key=lambda item: item[0][0])
        for group_ids, type_name in groups_list:
            ordered_groups.append((group_ids, type_name))
            for gate_id in group_ids:
                groups[gate_id] = group_ids
        return groups, ordered_groups

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


def _split_consecutive(ids: list[int], width: int = 1) -> list[list[int]]:
    """Split a sorted list of ids into consecutive runs of at most `width` ids."""
    if not ids:
        return []
    result: list[list[int]] = []
    run: list[int] = [ids[0]]
    for gate_id in ids[1:]:
        if gate_id == run[-1] + 1 and len(run) < width:
            run.append(gate_id)
        else:
            result.append(run)
            run = [gate_id]
    result.append(run)
    return result


def _chunk(ids: list[int], size: int) -> list[list[int]]:
    """Split a list into fixed-size chunks."""
    return [ids[i : i + size] for i in range(0, len(ids), size)]


def _type_width(type_name: str) -> int:
    """Return the bit width for a type name like u8, i16, bit, or dynamic."""
    if type_name.startswith("u") or type_name.startswith("i"):
        try:
            return int(type_name[1:])
        except ValueError:
            return 1
    return 1


def _cast_to_bits(
    raw_value: int | list[int], type_name: str, ids: list[int]
) -> dict[int, int]:
    if isinstance(raw_value, list):
        if len(raw_value) != len(ids):
            raise ValueError(
                f"Expected {len(ids)} bits for {type_name}, got {len(raw_value)}"
            )
        return dict(zip(ids, raw_value, strict=False))

    if not isinstance(raw_value, int):
        raise ValueError(
            f"Unsupported raw input type for {type_name}: {type(raw_value).__name__}"
        )

    width = len(ids)
    if type_name.startswith("u") or type_name.startswith("i"):
        mask = (1 << width) - 1
        value = raw_value & mask
    else:
        value = 1 if raw_value else 0

    bits = [(value >> index) & 1 for index in range(width)]
    return dict(zip(ids, bits, strict=False))


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
        dict_inputs = cast("_dict_int_int | _dict_int_list", input_values)
        for group, type_name in ordered_groups:
            first_id = group[0]
            if first_id in dict_inputs:
                group_value = dict_inputs[first_id]
                if isinstance(group_value, (int, list)):
                    values.update(_cast_to_bits(group_value, type_name, group))
                continue
            for gate_id in group:
                if gate_id in dict_inputs:
                    bit_value = dict_inputs[gate_id]
                    if isinstance(bit_value, int):
                        values[gate_id] = bit_value & 1
                    else:
                        raise ValueError(
                            f"Bit input values must be ints for gate {gate_id}"
                        )
                else:
                    values[gate_id] = 0
        return values

    raise ValueError("Unsupported input_values type")


def _collect_output_values(
    values: dict[int, int], gates: list[IrGate]
) -> int | list[int] | dict[int, int]:
    output_gates = [gate for gate in gates if gate.prefix == "OUT"]
    if not output_gates:
        return values

    output_gates.sort(key=lambda gate: gate.id)
    output_ids = [gate.id for gate in output_gates]
    if len(output_ids) == 1:
        return values[output_ids[0]]

    if all(gate.value_type == "bit" for gate in output_gates):
        return sum(values[gate_id] << index for index, gate_id in enumerate(output_ids))

    return [values[gate_id] for gate_id in output_ids]
