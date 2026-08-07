from pyray import *  # type: ignore

VARIABLE_COLORS = [
    (230, 25, 75),
    (60, 180, 75),
    (255, 225, 25),
    (0, 130, 200),
    (245, 130, 48),
    (145, 30, 180),
    (70, 240, 240),
    (240, 50, 230),
    (210, 245, 60),
    (250, 190, 190),
    (0, 128, 128),
    (230, 190, 255),
    (170, 110, 40),
    (255, 250, 200),
    (128, 0, 0),
    (170, 255, 195),
    (128, 128, 0),
    (255, 215, 180),
]

GATE_COLORS = {
    "OR": (0, 200, 0),
    "NOT": (255, 80, 80),
    "XOR": (255, 180, 0),
    "AND": (0, 120, 255),
    "NAND": (0, 220, 220),
    "NOR": (180, 0, 255),
    "XNOR": (220, 220, 220),
    "SWITCH": (128, 128, 128),
    "BUTTON": (255, 140, 0),
    "LAMP": (255, 255, 0),
}

HALF_HEIGHT_GATES = {"SWITCH", "BUTTON", "LAMP"}


def draw_cube_wires_thick(pos, size, thickness, color):
    x, y, z = pos
    width, height, length = size
    t = thickness

    hx = width / 2
    hy = height / 2
    hz = length / 2

    draw_cube_v(Vector3(x, y - hy, z - hz), Vector3(width, t, t), color)
    draw_cube_v(Vector3(x, y + hy, z - hz), Vector3(width, t, t), color)
    draw_cube_v(Vector3(x, y - hy, z + hz), Vector3(width, t, t), color)
    draw_cube_v(Vector3(x, y + hy, z + hz), Vector3(width, t, t), color)

    draw_cube_v(Vector3(x - hx, y, z - hz), Vector3(t, height, t), color)
    draw_cube_v(Vector3(x + hx, y, z - hz), Vector3(t, height, t), color)
    draw_cube_v(Vector3(x - hx, y, z + hz), Vector3(t, height, t), color)
    draw_cube_v(Vector3(x + hx, y, z + hz), Vector3(t, height, t), color)

    draw_cube_v(Vector3(x - hx, y - hy, z), Vector3(t, t, length), color)
    draw_cube_v(Vector3(x + hx, y - hy, z), Vector3(t, t, length), color)
    draw_cube_v(Vector3(x - hx, y + hy, z), Vector3(t, t, length), color)
    draw_cube_v(Vector3(x + hx, y + hy, z), Vector3(t, t, length), color)


def load_ir(ir):
    gates = []
    variables = {}
    maxX = 0
    maxZ = 0

    for line in ir.splitlines():
        stripped = line.strip()

        if stripped.startswith("#"):
            if ":" in stripped:
                ids_text, rest = stripped[1:].split(":", 1)
                ids_text = ids_text.strip()
                rest = rest.strip()

                if ids_text and rest and not any(c in rest for c in ["u", "i", "bit"]):
                    variable = ids_text
                    ids = []
                    for part in rest.split(","):
                        part = part.strip()

                        if "-" in part:
                            start, end = part.split("-", 1)
                            ids.extend(range(int(start), int(end) + 1))

                        else:
                            ids.append(int(part))

                    variables.update({gate_id: variable for gate_id in ids})
            continue

        parts = stripped.split(":", 1)
        if len(parts) != 2:
            continue

        id_text, remainder = parts
        remainder = remainder.strip()
        tokens = remainder.split()

        if not tokens:
            continue

        prefix = ""
        if tokens[0] in {"IN", "OUT"}:
            prefix = tokens[0]
            tokens = tokens[1:]

        try:
            gate_id = int(id_text.strip())
            x = int(tokens[0])
            y = int(tokens[1])
            z = int(tokens[2])
            gate_type = tokens[3]
            inputs = [int(token) for token in tokens[4:]]
        except ValueError:
            print(f"Invalid gate: {line}. Skipping.")
            continue

        if x > maxX:
            maxX = x
        if z > maxZ:
            maxZ = z

        gates.append((gate_id, prefix, x, y, z, gate_type, inputs))

    return gates, variables, maxX, maxZ


def get_variable_color(variable, color_map):
    if not variable:
        return None
    if variable not in color_map:
        color_map[variable] = VARIABLE_COLORS[len(color_map) % len(VARIABLE_COLORS)]
    return color_map[variable]


def run(ir: str):
    gates, variables, maxX, maxZ = load_ir(ir)
    color_map: dict[str, tuple[int, int, int]] = {}

    init_window(1000, 700, "Visualization")

    camera = Camera3D(
        Vector3(100, 50, 150),
        Vector3(0, 2, 0),
        Vector3(0, 1, 0),
        30,
    )
    camera.projection = 1

    while not window_should_close():
        begin_drawing()
        clear_background(WHITE)
        begin_mode_3d(camera)

        draw_grid(max(maxX, maxZ, 1) * 2, 1)

        for gate_id, prefix, x, y, z, gate_type, inputs in gates:
            x -= maxX // 2
            z -= maxZ // 2

            variable = variables.get(gate_id, "")
            var_color = get_variable_color(variable, color_map)

            size = (1, 0.5, 1) if gate_type in HALF_HEIGHT_GATES else (1, 1, 1)
            pos = (x, y + 0.25, z) if gate_type in HALF_HEIGHT_GATES else (x, y, z)

            if var_color:
                draw_cube_v(Vector3(*pos), Vector3(*size), Color(*var_color, 50))  # type: ignore

            r, g, b = GATE_COLORS.get(gate_type, (150, 150, 150))
            draw_cube_wires_thick(pos, size, 0.05, Color(r, g, b, 255))

        end_mode_3d()
        end_drawing()

    close_window()


if __name__ == "__main__":
    with open("out.ir") as f:
        ir = f.read()

    run(ir)
