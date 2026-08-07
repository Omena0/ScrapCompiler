from __future__ import annotations

from typing import Any, TypeAlias

from .stream import TextStream

AstNode: TypeAlias = dict[str, Any]
ModuleNodes: TypeAlias = dict[str, AstNode]

keywords: set[str] = {"module", "function"}
fields: dict[str, list[str]] = {
    "module": ["inputs", "outputs", "gates"],
    "function": ["gates"],
}
complex_fields: list[str] = ["gates"]

builtins: list[str] = ["Xor", "And", "Or", "Nor", "XNor", "Nand"]

valid_decorators: set[str] = {
    "assert",
    "ensure_timing",
    "pipelined",
    "clocked_input",
    "clocked_output",
}


def parse_decorators(stream: TextStream) -> list[AstNode]:
    """Consume any leading decorators and return them as AST nodes."""
    decorators: list[AstNode] = []
    while stream and stream.consume_text("@"):
        name = stream.consume_word()
        if name not in valid_decorators:
            stream.error("UnknownDecoratorError", f"Unknown decorator: @{name}", name)

        args: list[AstNode] = []
        if stream.consume_text("("):
            while stream and not stream.consume_text(")"):
                _consume_trivia(stream)
                arg_name = stream.consume_word()
                if arg_name and stream.consume_text("="):
                    value = parse_expr(stream)
                    args.append(
                        stream.emit(
                            {
                                "type": "named_arg",
                                "name": arg_name,
                                "value": value,
                            }
                        )
                    )
                else:
                    stream.pos -= len(arg_name)
                    args.append(parse_expr(stream))

                _consume_trivia(stream)
                if not stream.consume_text(","):
                    stream.expect(")")
                    break
            stream.consume_whitespace()

        decorators.append(
            stream.emit(
                {
                    "type": "decorator",
                    "name": name,
                    "args": args,
                }
            )
        )
    return decorators


def consume_call(stream: TextStream) -> list[AstNode]:
    """Parse a parenthesized, comma-separated expression list."""
    stream.expect("(")
    stream.consume_whitespace()

    args = []
    while stream and not stream.consume_text(")"):
        args.append(_parse_call_argument(stream))
        if not stream.match(")"):
            stream.expect(",")
            stream.consume_whitespace()

    stream.consume_whitespace()

    return args


def _parse_call_argument(stream: TextStream) -> AstNode:
    """Parse a positional expression or a named ``name = value`` argument."""
    start = stream.pos
    if name := stream.consume_word():
        _consume_trivia(stream)
        if stream.consume_text("="):
            if not stream.match("="):
                return stream.emit(
                    {
                        "type": "named_arg",
                        "name": name,
                        "value": parse_expr(stream),
                    }
                )

    stream.pos = start
    return parse_expr(stream)


def consume_classdef(stream: TextStream) -> list[AstNode]:
    """Parse module inheritance arguments followed by an opening brace."""

    inherits = consume_call(stream)

    stream.expect("{")

    stream.consume_whitespace()

    return inherits


def consume_def(stream: TextStream) -> AstNode:
    """Parse a named input or output definition."""
    definition_type = stream.consume_word()
    type_len = None
    if stream.consume_text("["):
        type_len = parse_expr(stream)
        stream.expect("]")

    stream.consume_whitespace()

    optional = stream.consume_text("?")
    name = stream.consume_word()

    return stream.emit(
        {
            "name": name,
            "type": definition_type,
            "len": type_len,
            "optional": optional,
        }
    )


def consume_defs(stream: TextStream) -> list[AstNode]:
    """Parse definitions until the enclosing field closes."""
    defs = []
    while True:
        stream.consume_whitespace()
        if stream.match("}"):
            break

        if stream.eof:
            stream.error("SyntaxError", "Unclosed '}'")

        defs.append(consume_def(stream))
        stream.consume_whitespace()

    stream.expect("}")

    return defs


def consume_comment(stream: TextStream) -> None:
    """Consume one optional line comment and its leading whitespace."""
    stream.consume_whitespace()
    if stream.consume_text("//"):
        stream.consume_until("\n")


_binary_precedence = {
    "||": 1,
    "&&": 2,
    "|": 3,
    "^": 4,
    "&": 5,
    "==": 6,
    "!=": 6,
    "<": 7,
    "<=": 7,
    ">": 7,
    ">=": 7,
    "<<": 8,
    ">>": 8,
    "+": 9,
    "-": 9,
    "*": 10,
    "/": 10,
    "%": 10,
}
_binary_operators = tuple(sorted(_binary_precedence, key=len, reverse=True))


def _consume_trivia(stream: TextStream) -> None:
    """Consume whitespace and consecutive line comments."""
    while True:
        stream.consume_whitespace()
        if not stream.consume_text("//"):
            return
        stream.consume_until("\n")


def _is_generic_call(stream: TextStream) -> bool:
    """Return whether the remaining text begins a typed function call."""
    source = stream.remaining
    if not source.startswith("<"):
        return False

    position = 1
    while position < len(source) and source[position].isspace():
        position += 1

    start = position
    while position < len(source) and (
        source[position].isalnum() or source[position] == "_"
    ):
        position += 1

    if position == start:
        return False

    while position < len(source) and source[position].isspace():
        position += 1

    if position == len(source) or source[position] != ">":
        return False

    position += 1
    while position < len(source) and source[position].isspace():
        position += 1

    return position < len(source) and source[position] == "("


def _parse_postfix(stream: TextStream, value: AstNode) -> AstNode:
    """Extend a primary expression with calls, type arguments, and indexes."""
    while True:
        _consume_trivia(stream)

        if stream.consume_text("["):
            index = parse_expr(stream)
            stream.expect("]")
            value = stream.emit(
                {
                    "type": "index",
                    "value": value,
                    "index": index,
                }
            )
            continue

        if stream.consume_text("."):
            name = stream.consume_word()
            if not name:
                stream.error("SyntaxError", "Field selection requires a name")
            value = stream.emit(
                {
                    "type": "field",
                    "value": value,
                    "name": name,
                }
            )
            continue

        if _is_generic_call(stream):
            if value["type"] != "ident":
                stream.error("SyntaxError", "Generic calls require an identifier")

            stream.expect("<")
            _consume_trivia(stream)
            cast_type = stream.consume_word()
            if not cast_type:
                stream.error("SyntaxError", "Expected cast type")
            _consume_trivia(stream)
            stream.expect(">")
            _consume_trivia(stream)
            value = stream.emit(
                {
                    "type": "call",
                    "name": value["name"],
                    "cast_type": cast_type,
                    "args": consume_call(stream),
                }
            )
            continue

        if stream.match("("):
            if value["type"] != "ident":
                stream.error("SyntaxError", "Calls require an identifier")

            value = stream.emit(
                {
                    "type": "call",
                    "name": value["name"],
                    "args": consume_call(stream),
                }
            )
            continue

        return value


def _parse_primary(stream: TextStream) -> AstNode:
    """Parse an expression that does not begin with a unary operator."""
    _consume_trivia(stream)

    if stream.peek().isdigit():
        value = stream.consume_while(lambda char: char.isdigit())
        return stream.emit({"type": "int", "value": int(value)})

    if stream.consume_text("("):
        expr = parse_expr(stream)
        stream.expect(")")
        return expr

    word = stream.consume_word()
    if not word:
        stream.error("SyntaxError", "Expected expression")

    if word == "true":
        return stream.emit({"type": "bool", "value": True})

    if word == "false":
        return stream.emit({"type": "bool", "value": False})

    if word == "new":
        return stream.emit({"type": "new", "value": _parse_unary(stream)})

    return stream.emit({"type": "ident", "name": word})


def _parse_unary(stream: TextStream) -> AstNode:
    """Parse a prefix unary expression or postfix primary expression."""
    _consume_trivia(stream)
    for operator in ("+", "-", "!", "~"):
        if stream.consume_text(operator):
            return stream.emit(
                {
                    "type": "unary",
                    "op": operator,
                    "value": _parse_unary(stream),
                }
            )

    cast = _try_parse_cast(stream)
    return _parse_postfix(stream, _parse_primary(stream)) if cast is None else cast


def _try_parse_cast(stream: TextStream) -> AstNode | None:
    """Parse a type cast expression like <u8>10 if present."""
    if not stream.match("<"):
        return None
    start = stream.pos
    stream.consume_text("<")
    _consume_trivia(stream)
    cast_type = stream.consume_word()
    if not cast_type:
        stream.pos = start
        return None
    _consume_trivia(stream)
    if not stream.consume_text(">"):
        stream.pos = start
        return None
    _consume_trivia(stream)
    value = _parse_primary(stream)
    if not isinstance(value, dict):
        stream.pos = start
        return None
    return stream.emit(
        {
            "type": "cast",
            "cast_type": cast_type,
            "value": value,
        }
    )


def parse_expr(stream: TextStream, min_precedence: int = 1) -> AstNode:
    """Parse a precedence-aware expression from ``stream``."""
    value = _parse_unary(stream)

    while True:
        _consume_trivia(stream)
        if stream.match("->"):
            return value

        operator = next(
            (candidate for candidate in _binary_operators if stream.match(candidate)),
            None,
        )
        if operator is None or _binary_precedence[operator] < min_precedence:
            return value

        stream.consume_text(operator)
        precedence = _binary_precedence[operator]
        value = stream.emit(
            {
                "type": "binary",
                "op": operator,
                "left": value,
                "right": parse_expr(stream, precedence + 1),
            }
        )


def consume_as_names(stream: TextStream) -> list[str]:
    """Parse the variable names after ``as``, reusing consume_call when parenthesized."""
    stream.consume_whitespace()
    if stream.match("("):
        names: list[str] = []
        args = consume_call(stream)
        for arg in args:
            if isinstance(arg, dict) and arg.get("type") == "ident":
                name = arg.get("name")
                if isinstance(name, str):
                    names.append(name)
        return names

    name = stream.consume_word()
    return [name] if name else []


def parse_statement(stream: TextStream) -> list[AstNode]:
    """Parse one statement from a module gate block."""
    # We have something like
    # bits(a) {
    # x: new Xor()
    # a, b -> x
    # a[n], b[n] -> x

    consume_comment(stream)

    stream.consume_whitespace()

    word = stream.consume_word()

    # Is identifier
    if stream.match(":"):
        return [parse_ident(word, stream)]

    elif stream.match("("):
        args = consume_call(stream)

        stream.consume_whitespace()

        as_names = (consume_as_names(stream) if stream.consume_text("as") else []) or [
            name
            for arg in args
            if isinstance(arg, dict) and isinstance(name := arg.get("name"), str)
        ]

        stream.consume_whitespace(False)

        stream.expect("{")

        stream.consume_whitespace()

        gates = parse_complex_field(stream)
        stream.expect("}")
        stream.consume_whitespace()

        return [
            stream.emit(
                {
                    "type": "as",
                    "name": word,
                    "args": args,
                    "vars": as_names,
                    "gates": gates,
                }
            )
        ]

    elif "->" in stream.current_line:
        # Get back the dropped off first part
        stream.pos -= len(word)

        args = []
        while stream and not stream.consume_text("->"):
            stream.consume_whitespace()
            args.append(parse_expr(stream))

            stream.consume_whitespace()
            if stream.consume_text("->"):
                break

            stream.expect(",")

        stream.consume_whitespace()
        to = stream.consume_word()
        stream.consume_whitespace()

        return [stream.emit({"type": "arrow", "from": args, "to": to})]

    else:
        stream.error(
            "SyntaxError",
            "Invalid syntax while parsing statement. Expected ident, call, or wire statement.",
        )


def parse_complex_field(stream: TextStream) -> list[AstNode]:
    """Parse statements until a complex field's closing brace."""
    statements = []
    while stream and not stream.match("}"):
        statements.extend(parse_statement(stream))
        stream.consume_whitespace()

    return statements


def parse_field(stream: TextStream) -> tuple[str, list[AstNode]]:
    """Parse a named module field and its contents."""
    # field {

    field = stream.consume_word()
    if field not in fields["module"]:
        stream.error("UnknownFieldError", f"Unknown field: {field}", field)

    stream.consume_whitespace(False)

    stream.expect("{")

    stream.consume_whitespace()

    # Complex field like 'gates'
    if field in complex_fields:
        defs = parse_complex_field(stream)
        stream.expect("}")
        stream.consume_whitespace()
        return field, defs

    # Simple definitions
    defs = consume_defs(stream)

    stream.consume_whitespace()

    return field, defs


def parse_keyword(
    keyword: str, stream: TextStream, decorators: list[AstNode] | None = None
) -> tuple[ModuleNodes, ModuleNodes, list[AstNode]]:
    """Parse a keyword-led module or function declaration."""
    stream.consume_whitespace()
    decorators = decorators or []

    if keyword == "module":
        with stream.range():
            name = stream.consume_word()

        stream.consume_whitespace()

        inherit = consume_classdef(stream)

        module_fields: AstNode = {}
        with stream.range():
            while stream and not stream.match("}"):
                field, defs = parse_field(stream)
                if field not in complex_fields:
                    module_fields[field] = defs

            stream.consume_whitespace()
            stream.expect("}")

        return (
            {
                name: stream.emit(
                    {
                        "decorators": decorators,
                        "inherit": inherit,
                        "fields": stream.emit(module_fields),
                        "gates": defs,
                    }
                )
            },
            {},
            [],
        )

    if keyword == "function":
        with stream.range():
            name = stream.consume_word()

        stream.consume_whitespace()

        stream.expect("(")
        stream.consume_whitespace()
        stream.expect(")")
        stream.consume_whitespace()

        stream.expect("{")

        function_fields: AstNode = {}
        function_defs: list[AstNode] = []
        with stream.range():
            while stream and not stream.match("}"):
                field, function_defs = parse_field(stream)
                if field not in complex_fields:
                    function_fields[field] = function_defs

            stream.consume_whitespace()
            stream.expect("}")

        return (
            {},
            {
                name: stream.emit(
                    {
                        "type": "function",
                        "decorators": decorators,
                        "fields": stream.emit(function_fields),
                        "gates": function_defs,
                    }
                )
            },
            [],
        )

    stream.error("SyntaxError", f"Invalid keyword: '{keyword}'", keyword)


def parse_ident(name: str, stream: TextStream) -> AstNode:
    """Parse a named gate assignment after its identifier."""
    stream.consume_whitespace()

    stream.expect(":")

    expr = parse_expr(stream)

    return stream.emit({"type": "gate", "name": name, "value": expr})


def parse_toplevel(
    stream: TextStream,
) -> tuple[ModuleNodes, ModuleNodes, list[AstNode]]:
    """Parse one top-level module declaration, function declaration, or gate assignment."""
    consume_comment(stream)
    stream.consume_whitespace()

    with stream.range():
        decorators = parse_decorators(stream)

    word = stream.consume_word()

    if word in keywords:
        m, f, g = parse_keyword(word, stream, decorators)
        return m, f, g

    # Word is an identifier
    if stream.match(":"):
        return {}, {}, [parse_ident(word, stream)]

    # Arrow statement at top level: expr, expr -> target
    if "->" in stream.current_line:
        stream.pos -= len(word)
        args = []
        while stream and not stream.consume_text("->"):
            stream.consume_whitespace()
            args.append(parse_expr(stream))
            stream.consume_whitespace()
            if stream.consume_text("->"):
                break
            stream.expect(",")

        stream.consume_whitespace()
        to = stream.consume_word()
        stream.consume_whitespace()

        return {}, {}, [stream.emit({"type": "arrow", "from": args, "to": to})]

    stream.error("SyntaxError", f"invalid syntax while parsing toplevel: {word}", word)


def parse(source: str, debug=True) -> AstNode:
    """Parse source text into the compiler AST."""
    stream = TextStream(source, debug)

    ast = stream.emit({"modules": {}, "functions": {}, "gates": []})

    while stream:
        stream.consume_whitespace()

        m, f, g = parse_toplevel(stream)
        stream.consume_whitespace()

        ast["modules"].update(m)
        ast["functions"].update(f)
        ast["gates"].extend(g)

    return ast
