#!/usr/bin/env python3
"""
Scrap Logic Analyzer

This script is the single source of truth for all language intelligence.
To add new syntax or hover data, update the grammar JSON and this script.
The TypeScript extension only handles display; all logic lives here.
"""

import json
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def _setup_sys_path(filepath: str) -> None:
    script_dir = os.path.dirname(os.path.abspath(__file__))

    candidates = []

    repo_root = os.path.abspath(os.path.join(script_dir, "..", ".."))
    candidates.append(repo_root)

    file_dir = os.path.dirname(os.path.abspath(filepath))
    current = file_dir
    for _ in range(8):
        if os.path.isdir(os.path.join(current, "ScrapCompiler")):
            candidates.append(current)
            break
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent

    seen = set()
    for candidate in candidates:
        abs_candidate = os.path.abspath(candidate)
        if abs_candidate not in seen and os.path.isdir(abs_candidate):
            sys.path.insert(0, abs_candidate)
            seen.add(abs_candidate)


def analyze(filepath: str) -> dict:
    """Parse, compile, and analyze a .logic file for IDE support."""
    _setup_sys_path(filepath)
    from ScrapCompiler.compiler.compiler import ScrapCompiler
    from ScrapCompiler.parser import parser
    with open(filepath, "r") as f:
        source = f.read()

    ast = None
    modules = {}
    functions = {}
    errors = []
    defines = {}
    try:
        ast = parser.parse(source)
        modules = ast.get("modules", {}) if isinstance(ast, dict) else {}
        functions = ast.get("functions", {}) if isinstance(ast, dict) else {}
        defines = _extract_defines(source)
    except SystemExit as e:
        errors.append(str(e))
        modules = _extract_module_defs(source)
        defines = _extract_defines(source)
    except Exception as e:
        errors.append(str(e))
        modules = _extract_module_defs(source)
        defines = _extract_defines(source)

    compiler = ScrapCompiler(ast) if ast else None
    variables = {}
    gates = []

    if compiler:
        try:
            compiler.compile_modules(modules, functions)
            gates = compiler.compile()
            variables = _build_variable_info(gates)
        except SystemExit as e:
            errors.append(str(e))
        except Exception as e:
            errors.append(str(e))

    module_info = _build_module_info(modules, compiler)

    return {
        "variables": variables,
        "modules": module_info,
        "functions": _build_function_info(functions),
        "defines": defines,
        "errors": errors,
    }


def compile(filepath: str) -> str:
    """Compile a .logic file to IR."""
    _setup_sys_path(filepath)
    from ScrapCompiler.compiler.compiler import ScrapCompiler
    from ScrapCompiler.parser import parser

    with open(filepath, "r") as f:
        source = f.read()

    ast = parser.parse(source)
    compiler = ScrapCompiler(ast)
    compiler.compile_modules(ast.get("modules", {}), ast.get("functions", {}))
    gates = compiler.compile()
    return ScrapCompiler.gates_to_ir(gates)


def visualize(filepath: str) -> None:
    """Compile a .logic file and launch the visualizer."""
    ir = compile(filepath)

    visualizer_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "ScrapCompiler", "visualize.py"
    )

    with tempfile.NamedTemporaryFile(mode="w", suffix=".ir", delete=False) as f:
        f.write(ir)
        temp_path = f.name

    try:
        subprocess.Popen(
            [sys.executable, visualizer_path, temp_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)


def _extract_defines(source: str) -> dict:
    """Extract #define macros from source."""
    defines = {}
    for match in re.finditer(r"#\s*define\s+(\w+)\s*=\s*(.+)", source):
        name = match.group(1)
        value = match.group(2).strip()
        if value.startswith("{") and value.endswith("}"):
            value = value[1:-1].strip()
        defines[name] = value
    return defines


def _extract_module_defs(source: str) -> dict:
    """Best-effort module name and field extraction when the parser fails."""
    modules = {}
    lines = source.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("module "):
            paren_idx = line.find("(")
            if paren_idx != -1:
                name = line[7:paren_idx].strip()
            else:
                name = line[7:].strip().rstrip("{")

            inputs = []
            outputs = []
            decorators = []

            j = i + 1
            while j < len(lines):
                block_line = lines[j].strip()

                if block_line.startswith("@"):
                    decorators.append(block_line)
                    j += 1
                    continue

                if block_line == "inputs" or block_line.startswith("inputs {"):
                    fields, j = _parse_block(lines, j, "inputs")
                    inputs.extend(fields)
                    continue

                if block_line == "outputs" or block_line.startswith("outputs {"):
                    fields, j = _parse_block(lines, j, "outputs")
                    outputs.extend(fields)
                    continue

                if block_line == "}":
                    break

                j += 1

            modules[name] = {
                "inputs": inputs,
                "outputs": outputs,
                "decorators": decorators,
            }
            i = j
        i += 1
    return modules


def _parse_block(lines: list, start: int, block_name: str):
    """Parse an inputs or outputs block starting at `start`."""
    fields = []
    j = start

    block_line = lines[j].strip()
    if block_line == block_name:
        j += 1
        if j < len(lines) and lines[j].strip() == "{":
            j += 1
    elif block_line.startswith(block_name + " {"):
        j += 1

    while j < len(lines):
        inner = lines[j].strip()
        if inner == "}":
            j += 1
            break
        if inner and not inner.startswith("@"):
            fields.append(_parse_field(inner))
        j += 1

    return fields, j


def _parse_field(line: str) -> dict:
    """Parse a simple field line like 'dynamic a' or 'bit ?carry_in'."""
    parts = line.split()
    result = {"name": "", "type": "", "length": None, "optional": False, "buffered": False}

    if "[" in line:
        bracket_start = line.find("[")
        bracket_end = line.find("]")
        if bracket_start != -1 and bracket_end != -1:
            length_expr = line[bracket_start + 1 : bracket_end]
            result["length"] = length_expr

    if "buffered" in parts:
        result["buffered"] = True

    name_parts = []
    type_parts = []
    for part in parts:
        if part in ("dynamic", "buffered", "bit", "bool", "int"):
            if part != "buffered":
                type_parts.append(part)
        elif part == "?":
            result["optional"] = True
        elif part.startswith("[") or part.endswith("]"):
            continue
        else:
            name_parts.append(part)

    result["type"] = " ".join(type_parts) if type_parts else "bit"
    result["name"] = name_parts[-1] if name_parts else ""

    return result


def _build_variable_info(gates) -> dict:
    """Map top-level variables to their tick, type, and bit representation."""
    variable_gates = {}
    for gate in gates:
        if hasattr(gate, "variable") and gate.variable:
            variable_gates.setdefault(gate.variable, []).append(gate)

    result = {}
    for var, var_gates in variable_gates.items():
        max_tick = max(g.x for g in var_gates)
        bits = sorted(var_gates, key=lambda g: g.y)
        bit_str = "".join(
            (
                "1"
                if g.type == "OR" and not g.inputs
                else "0" if g.type == "NOT" and not g.inputs else "?"
            )
            for g in bits
        )
        value = None
        if bit_str and all(c in "01" for c in bit_str):
            value = int(bit_str, 2)

        result[var] = {
            "type": var_gates[0].value_type,
            "tick": max_tick,
            "bits": bit_str,
            "value": value,
        }

    return result


def _build_module_info(modules: dict, compiler) -> dict:
    """Extract module definitions for hover and completion."""
    result = {}

    builtin_inputs = {
        "IntInput": [],
        "IntDisplay": [{"name": "bits", "type": "dynamic", "length": None}],
        "Lamp": [{"name": "bit", "type": "bit", "length": None}],
        "Switch": [{"name": "default", "type": "bit", "length": None}],
        "Button": [],
        "ButtonInput": [],
        "Object": [{"name": "value", "type": "object", "length": None}],
    }
    builtin_outputs = {
        "IntInput": [{"name": "bits", "type": "dynamic", "length": None}],
        "IntDisplay": [],
        "Lamp": [],
        "Switch": [{"name": "bit", "type": "bit", "length": None}],
        "Button": [{"name": "bit", "type": "bit", "length": None}],
        "ButtonInput": [{"name": "bit", "type": "bit", "length": None}],
        "Object": [],
    }

    for name in list(modules.keys()) + list(builtin_inputs.keys()):
        if name in result:
            continue
        if name in builtin_inputs:
            result[name] = {
                "inputs": builtin_inputs[name],
                "outputs": builtin_outputs[name],
                "decorators": [],
            }
        elif name in modules:
            mod = modules[name]
            fields = mod.get("fields", {}) if isinstance(mod, dict) else {}
            inputs = []
            for f in fields.get("inputs", []):
                if isinstance(f, dict):
                    inputs.append(
                        {
                            "name": f.get("name", ""),
                            "type": f.get("type", ""),
                            "length": f.get("len") or f.get("length"),
                            "optional": f.get("optional", False),
                            "buffered": f.get("buffered", False),
                        }
                    )
            outputs = []
            for f in fields.get("outputs", []):
                if isinstance(f, dict):
                    outputs.append(
                        {
                            "name": f.get("name", ""),
                            "type": f.get("type", ""),
                            "length": f.get("len") or f.get("length"),
                            "optional": f.get("optional", False),
                            "buffered": f.get("buffered", False),
                        }
                    )
            decorators = []
            if isinstance(mod, dict) and "decorators" in mod:
                raw_decs = mod.get("decorators", [])
                if isinstance(raw_decs, list):
                    for d in raw_decs:
                        if isinstance(d, dict):
                            decorators.append(d.get("name", ""))
                        elif isinstance(d, str):
                            decorators.append(d)

            result[name] = {
                "inputs": inputs,
                "outputs": outputs,
                "decorators": decorators,
            }
    return result


def _build_function_info(functions: dict) -> dict:
    """Extract function definitions for hover and completion."""
    result = {}

    for name, func in functions.items():
        if not isinstance(func, dict):
            continue

        fields = func.get("fields", {})
        inputs = []
        outputs = []

        if isinstance(fields, dict):
            for f in fields.get("inputs", []):
                if isinstance(f, dict):
                    inputs.append(
                        {
                            "name": f.get("name", ""),
                            "type": f.get("type", ""),
                            "length": f.get("len") or f.get("length"),
                            "optional": f.get("optional", False),
                        }
                    )
            for f in fields.get("outputs", []):
                if isinstance(f, dict):
                    outputs.append(
                        {
                            "name": f.get("name", ""),
                            "type": f.get("type", ""),
                            "length": f.get("len") or f.get("length"),
                            "optional": f.get("optional", False),
                        }
                    )

        decorators = []
        if "decorators" in func:
            raw_decs = func.get("decorators", [])
            if isinstance(raw_decs, list):
                for d in raw_decs:
                    if isinstance(d, dict):
                        decorators.append(d.get("name", ""))
                    elif isinstance(d, str):
                        decorators.append(d)

        result[name] = {
            "params": inputs,
            "outputs": outputs,
            "decorators": decorators,
        }

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: analyze.py <file.logic> [command]"}))
        sys.exit(0)

    filepath = sys.argv[1]
    command = sys.argv[2] if len(sys.argv) > 2 else "analyze"

    try:
        if command == "compile":
            ir = compile(filepath)
            print(ir)
        elif command == "visualize":
            visualize(filepath)
        else:
            result = analyze(filepath)
            print(json.dumps(result))
    except Exception as e:
        print(
            json.dumps(
                {"error": str(e), "variables": {}, "modules": {}, "functions": {}, "defines": {}, "errors": [str(e)]}
            )
        )
    sys.exit(0)
