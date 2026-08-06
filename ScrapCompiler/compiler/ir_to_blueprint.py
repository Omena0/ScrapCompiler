from __future__ import annotations

import json
from ..simulation import parse_ir, IrGate

GATE_COLORS: dict[str, str] = {
    "XOR": "0A3EE2",
    "AND": "D02525",
    "OR": "CF11D2",
    "NOT": "D02525",
    "NAND": "D02525",
    "NOR": "673B00",
    "XNOR": "35086C",
}

INPUT_COLOR = "222222"
OUTPUT_COLOR = "222222"
BODY_COLOR = "9B683A"

BODY_SHAPE_ID = "df953d9c-234f-4ac2-af5e-f0490b223e71"
GATE_SHAPE_ID = "9f0f56e8-2c31-4d83-996c-d00a9b296c3f"


def ir_to_blueprint(ir_text: str) -> dict:
    gates = parse_ir(ir_text)
    return _build_blueprint(gates)


def _build_blueprint(gates: list[IrGate]) -> dict:
    if not gates:
        return {"bodies": [{"childs": []}], "version": 4}

    max_x = max(g.x for g in gates)
    max_y = max(g.y for g in gates)
    max_z = max(g.z for g in gates)

    body = {
        "bounds": {"x": max_y + 1, "y": max_x + 1, "z": max_z + 1},
        "color": BODY_COLOR,
        "pos": {"x": 0, "y": 0, "z": 0},
        "shapeId": BODY_SHAPE_ID,
        "xaxis": 1,
        "zaxis": 1,
    }

    childs = [body]

    for gate in gates:
        color = _get_gate_color(gate)
        block: dict[str, object] = {
            "bounds": {"x": 1, "y": 1, "z": 1},
            "color": color,
            "pos": {"x": gate.y, "y": -gate.x, "z": gate.z + 1},
            "shapeId": GATE_SHAPE_ID,
            "xaxis": 1,
            "zaxis": 1,
        }
        if gate.prefix == "IN":
            block["controller"] = {
                "active": False,
                "controllers": [{"id": gate.id}],
                "id": gate.id,
                "joints": None,
                "mode": 1,
            }
        elif gate.prefix == "OUT":
            block["controller"] = {
                "active": False,
                "controllers": [{"id": gate.id}],
                "id": gate.id,
                "joints": None,
                "mode": 0,
            }
        else:
            block["controller"] = {
                "active": False,
                "controllers": None,
                "id": gate.id,
                "joints": None,
                "mode": 1,
            }
        childs.append(block)

    return {"bodies": [{"childs": childs}], "version": 4}


def _get_gate_color(gate: IrGate) -> str:
    if gate.prefix == "IN":
        return INPUT_COLOR
    if gate.prefix == "OUT":
        return OUTPUT_COLOR
    return GATE_COLORS.get(gate.type, "222222")


def write_blueprint(ir_text: str, path: str) -> None:
    blueprint = ir_to_blueprint(ir_text)
    with open(path, "w") as f:
        json.dump(blueprint, f, indent=2)
