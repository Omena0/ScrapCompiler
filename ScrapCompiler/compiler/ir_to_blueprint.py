from __future__ import annotations

import json

from ..simulation import IrGate, parse_ir

GATE_COLORS: dict[str, str] = {
    "XOR": "0A3EE2",
    "AND": "D02525",
    "OR": "CF11D2",
    "NOT": "D02525",
    "NAND": "D02525",
    "NOR": "673B00",
    "XNOR": "35086C",
    "TIMER": "DF7F01",
}

BODY_COLOR = "8D8F89"
BLOCK_COLOR = "9B683A"
INPUT_COLOR = "222222"
OUTPUT_COLOR = "222222"
SWITCH_COLOR = "DF7F01"

BODY_SHAPE_ID = "a6c6ce30-dd47-4587-b475-085d55c6a3b4"
BLOCK_SHAPE_ID = "df953d9c-234f-4ac2-af5e-f0490b223e71"
GATE_SHAPE_ID = "9f0f56e8-2c31-4d83-996c-d00a9b296c3f"
SWITCH_SHAPE_ID = "7cf717d7-d167-4f2d-a6e7-6b2c70aa3986"
LAMP_SHAPE_ID = "ed27f5e2-cac5-4a32-a5d9-49f116acc6af"
BUTTON_SHAPE_ID = "1e8d93a4-506b-470d-9ada-9c0a321e2db5"
TIMER_SHAPE_ID = "8f7fd0e7-c46e-4944-a414-7ce2437bb30f"

GATE_MODES: dict[str, int] = {
    "AND": 0,
    "OR": 1,
    "XOR": 2,
    "NAND": 3,
    "NOR": 4,
    "XNOR": 5,
    "NOT": 4,
}


def ir_to_blueprint(ir_text: str) -> dict:
    """Convert IR text to a Scrap Mechanic blueprint dictionary."""
    gates = parse_ir(ir_text)
    return _build_blueprint(gates)

def _gate_pos(gate: IrGate) -> tuple[float, float, float]:
    return (gate.x, gate.y, gate.z)

def _build_blueprint(gates: list[IrGate]) -> dict:
    """Build a Scrap Mechanic blueprint from a list of IR gates."""
    if not gates:
        return {"bodies": [{"childs": []}], "version": 4}

    input_ids: set[int] = {gate.id for gate in gates if gate.prefix == "IN"}
    input_targets: dict[int, list[int]] = {}

    for gate in gates:
        if gate.prefix != "IN":
            for source in gate.inputs:
                if source in input_ids:
                    input_targets.setdefault(source, []).append(gate.id)

    output_targets: dict[int, list[int]] = {}
    for gate in gates:
        for source in gate.inputs:
            output_targets.setdefault(source, []).append(gate.id)

    positions: list[tuple[float, float, float]] = []

    for gate in gates:
        positions.append(_gate_pos(gate))
        if gate.type in ["SWITCH", "BUTTON"]:
            positions.append((gate.x - 1, gate.y, gate.z))
        if gate.type == "TIMER":
            positions.append((gate.x + 1, gate.y, gate.z))

    min_x = min(p[0] for p in positions)
    max_x = max(p[0] for p in positions)
    min_y = min(p[1] for p in positions)
    max_y = max(p[1] for p in positions)
    min_z = min(p[2] for p in positions)

    body = {
        "bounds": {
            "x": max_x - min_x + 1,
            "y": max_y - min_y + 1,
            "z": 1,
        },
        "color": BODY_COLOR,
        "pos": {"x": min_x, "y": min_y, "z": min_z},
        "shapeId": BODY_SHAPE_ID,
        "xaxis": 1,
        "zaxis": 3,
    }

    childs = [body]

    for gate in gates:
        x, y, z = _gate_pos(gate)
        z += 1

        if gate.type in ["SWITCH", "BUTTON"]:
            base_block: dict[str, object] = {
                "bounds": {"x": 1, "y": 1, "z": 1},
                "color": BLOCK_COLOR,
                "pos": {"x": x - 1, "y": y, "z": z},
                "shapeId": BLOCK_SHAPE_ID,
                "xaxis": 1,
                "zaxis": 3,
            }
            childs.append(base_block)

            targets = input_targets.get(gate.id, [])
            shape_id = SWITCH_SHAPE_ID if gate.type == "SWITCH" else BUTTON_SHAPE_ID
            switch_block: dict[str, object] = {
                "color": SWITCH_COLOR,
                "pos": {"x": x - 1, "y": y + 1, "z": z},
                "shapeId": shape_id,
                "xaxis": 3,
                "zaxis": -2,
                "controller": {
                    "id": gate.id,
                    "state": gate.default_state if gate.type == "SWITCH" else 0,
                    "controllers": [{"id": t} for t in targets],
                },
            }

            childs.append(switch_block)
            continue

        color = _get_gate_color(gate)
        shape_id = _get_gate_shape_id(gate)
        block = {
            "color": color,
            "pos": {"x": x, "y": y+1, "z": z},
            "shapeId": shape_id,
            "xaxis": 1,
            "zaxis": -2,
        }

        if gate.type == "TIMER":
            block["xaxis"] = 3
            block["zaxis"] = 1
            block["controller"] = {
                "id": gate.id,
                "ticks": gate.delay,
                "seconds": 0,
                "controllers": [
                    *[{"id": inp} for inp in gate.inputs],
                    *[{"id": t} for t in output_targets.get(gate.id, [])],
                ],
            }
            childs.append(block)

            extension = {
                "color": color,
                "pos": {"x": x + 1, "y": y, "z": z},
                "shapeId": shape_id,
                "xaxis": 3,
                "zaxis": 1,
            }
            childs.append(extension)
            continue

        elif gate.type == "LAMP":
            block["xaxis"] = 2
            block["zaxis"] = 1
            block["controller"] = {
                "id": gate.id,
                "luminance": 100,
            }
            block["pos"] = {"x": x, "y": y, "z": z}
            block["color"] = 'FFFFFF'

        else:
            mode = GATE_MODES.get(gate.type, 1)
            block["controller"] = {
                "id": gate.id,
                "mode": mode,
                "controllers": [
                    *[{"id": t} for t in output_targets.get(gate.id, [])],
                ],
            }
        childs.append(block)

    return {"bodies": [{"childs": childs}], "version": 4}

def _get_gate_color(gate: IrGate) -> str:
    """Get the color for a gate based on its type and prefix."""
    if gate.prefix == "IN":
        return INPUT_COLOR
    if gate.prefix == "OUT":
        return OUTPUT_COLOR
    return GATE_COLORS.get(gate.type, "222222")


def _get_gate_shape_id(gate: IrGate) -> str:
    """Get the Scrap Mechanic shape ID for the gate based on its type."""
    if gate.type == "SWITCH":
        return SWITCH_SHAPE_ID
    elif gate.type == "BUTTON":
        return BUTTON_SHAPE_ID
    elif gate.type == "LAMP":
        return LAMP_SHAPE_ID
    elif gate.type == "TIMER":
        return TIMER_SHAPE_ID
    return GATE_SHAPE_ID


def write_blueprint(ir_text: str, path: str) -> None:
    """Write a Scrap Mechanic blueprint to a file."""
    blueprint = ir_to_blueprint(ir_text)
    with open(path, "w") as f:
        json.dump(blueprint, f, indent=2)
