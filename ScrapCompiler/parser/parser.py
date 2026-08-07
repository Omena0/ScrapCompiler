from __future__ import annotations

import sys
from typing import Any, TypeAlias

from .stream import TextStream

AstNode: TypeAlias = dict[str, Any]
ModuleNodes: TypeAlias = dict[str, AstNode]

keywords: set[str] = {"module"}
fields: dict[str, list[str]] = {
    'module': ['inputs', 'outputs', 'gates']
}
complex_fields: list[str] = ['gates']

builtins: list[str] = ['Xor', 'And', 'Or', 'Nor', 'XNor', 'Nand']


def consume_call(stream: TextStream) -> list[AstNode]:
    """Parse a parenthesized, comma-separated expression list."""
    stream.expect('(')
    stream.consume_whitespace()

    args = []
    while not stream.consume_text(')'):
        args.append(_parse_call_argument(stream))
        if not stream.match(')'):
            stream.expect(',')
            stream.consume_whitespace()

    stream.consume_whitespace()

    return args

def _parse_call_argument(stream: TextStream) -> AstNode:
    """Parse a positional expression or a named ``name = value`` argument."""
    start = stream.pos
    name = stream.consume_word()
    if name:
        _consume_trivia(stream)
        if stream.consume_text('='):
            if not stream.match('='):
                return stream.emit({
                    'type': 'named_arg',
                    'name': name,
                    'value': parse_expr(stream),
                })

    stream.pos = start
    return parse_expr(stream)

def consume_classdef(stream: TextStream) -> list[AstNode]:
    """Parse module inheritance arguments followed by an opening brace."""

    inherits = consume_call(stream)

    stream.expect('{')

    stream.consume_whitespace()

    return inherits

def consume_def(stream: TextStream) -> AstNode:
    """Parse a named input or output definition."""
    definition_type = stream.consume_word()
    type_len = None
    if stream.consume_text('['):
        type_len = parse_expr(stream)
        stream.expect(']')

    stream.consume_whitespace()

    buffered = stream.consume_text('buffered')
    stream.consume_whitespace()

    optional = stream.consume_text('?')
    name = stream.consume_word()

    return stream.emit({
        "name": name,
        "type": definition_type,
        "len": type_len,
        "optional": optional,
        "buffered": buffered,
    })

def consume_defs(stream: TextStream) -> list[AstNode]:
    """Parse definitions until the enclosing field closes."""
    defs = []
    while True:
        stream.consume_whitespace()
        if stream.match('}'):
            break

        if stream.eof:
            stream.error('SyntaxError', "Unclosed '}'")

        defs.append(consume_def(stream))
        stream.consume_whitespace()

    stream.expect('}')

    return defs

def consume_comment(stream: TextStream) -> None:
    """Consume one optional line comment and its leading whitespace."""
    stream.consume_whitespace()
    if stream.consume_text('//'):
        stream.consume_until('\n')

_binary_precedence = {
    '||': 1,
    '&&': 2,
    '|': 3,
    '^': 4,
    '&': 5,
    '==': 6,
    '!=': 6,
    '<': 7,
    '<=': 7,
    '>': 7,
    '>=': 7,
    '<<': 8,
    '>>': 8,
    '+': 9,
    '-': 9,
    '*': 10,
    '/': 10,
    '%': 10,
}
_binary_operators = tuple(sorted(_binary_precedence, key=len, reverse=True))

def _consume_trivia(stream: TextStream) -> None:
    """Consume whitespace and consecutive line comments."""
    while True:
        stream.consume_whitespace()
        if not stream.consume_text('//'):
            return
        stream.consume_until('\n')

def _is_generic_call(stream: TextStream) -> bool:
    """Return whether the remaining text begins a typed function call."""
    source = stream.remaining
    if not source.startswith('<'):
        return False

    position = 1
    while position < len(source) and source[position].isspace():
        position += 1

    start = position
    while position < len(source) and (source[position].isalnum() or source[position] == '_'):
        position += 1

    if position == start:
        return False

    while position < len(source) and source[position].isspace():
        position += 1

    if position == len(source) or source[position] != '>':
        return False

    position += 1
    while position < len(source) and source[position].isspace():
        position += 1

    return position < len(source) and source[position] == '('

def _parse_postfix(stream: TextStream, value: AstNode) -> AstNode:
    """Extend a primary expression with calls, type arguments, and indexes."""
    while True:
        _consume_trivia(stream)

        if stream.consume_text('['):
            index = parse_expr(stream)
            stream.expect(']')
            value = stream.emit({
                'type': 'index',
                'value': value,
                'index': index,
            })
            continue

        if stream.consume_text('.'):
            name = stream.consume_word()
            if not name:
                stream.error('SyntaxError', 'Field selection requires a name')
            value = stream.emit({
                'type': 'field',
                'value': value,
                'name': name,
            })
            continue

        if _is_generic_call(stream):
            if value['type'] != 'ident':
                stream.error('SyntaxError', 'Generic calls require an identifier')

            stream.expect('<')
            _consume_trivia(stream)
            cast_type = stream.consume_word()
            if not cast_type:
                stream.error('SyntaxError', 'Expected cast type')
            _consume_trivia(stream)
            stream.expect('>')
            _consume_trivia(stream)
            value = stream.emit({
                'type': 'call',
                'name': value['name'],
                'cast_type': cast_type,
                'args': consume_call(stream),
            })
            continue

        if stream.match('('):
            if value['type'] != 'ident':
                stream.error('SyntaxError', 'Calls require an identifier')

            value = stream.emit({
                'type': 'call',
                'name': value['name'],
                'args': consume_call(stream),
            })
            continue

        return value

def _parse_primary(stream: TextStream) -> AstNode:
    """Parse an expression that does not begin with a unary operator."""
    _consume_trivia(stream)

    if stream.peek().isdigit():
        value = stream.consume_while(lambda char: char.isdigit())
        return stream.emit({'type': 'int', 'value': int(value)})

    if stream.consume_text('('):
        value = parse_expr(stream)
        stream.expect(')')
        return value

    word = stream.consume_word()
    if not word:
        stream.error('SyntaxError', 'Expected expression')

    if word == 'true':
        return stream.emit({'type': 'bool', 'value': True})

    if word == 'false':
        return stream.emit({'type': 'bool', 'value': False})

    if word == 'new':
        return stream.emit({'type': 'new', 'value': _parse_unary(stream)})

    if word in keywords:
        return parse_keyword(word, stream)

    return stream.emit({'type': 'ident', 'name': word})

def _parse_unary(stream: TextStream) -> AstNode:
    """Parse a prefix unary expression or postfix primary expression."""
    _consume_trivia(stream)
    for operator in ('+', '-', '!', '~'):
        if stream.consume_text(operator):
            return stream.emit({
                'type': 'unary',
                'op': operator,
                'value': _parse_unary(stream),
            })

    cast = _try_parse_cast(stream)
    if cast is not None:
        return cast

    return _parse_postfix(stream, _parse_primary(stream))

def _try_parse_cast(stream: TextStream) -> AstNode | None:
    """Parse a type cast expression like <u8>10 if present."""
    if not stream.match('<'):
        return None
    start = stream.pos
    stream.consume_text('<')
    _consume_trivia(stream)
    cast_type = stream.consume_word()
    if not cast_type:
        stream.pos = start
        return None
    _consume_trivia(stream)
    if not stream.consume_text('>'):
        stream.pos = start
        return None
    _consume_trivia(stream)
    value = _parse_primary(stream)
    if not isinstance(value, dict):
        stream.pos = start
        return None
    return stream.emit({
        'type': 'cast',
        'cast_type': cast_type,
        'value': value,
    })

def parse_expr(stream: TextStream, min_precedence: int = 1) -> AstNode:
    """Parse a precedence-aware expression from ``stream``."""
    value = _parse_unary(stream)

    while True:
        _consume_trivia(stream)
        if stream.match('->'):
            return value

        operator = next(
            (candidate for candidate in _binary_operators if stream.match(candidate)),
            None,
        )
        if operator is None or _binary_precedence[operator] < min_precedence:
            return value

        stream.consume_text(operator)
        precedence = _binary_precedence[operator]
        value = stream.emit({
            'type': 'binary',
            'op': operator,
            'left': value,
            'right': parse_expr(stream, precedence + 1),
        })

def parse_statement(stream: TextStream) -> list[AstNode]:
    """Parse one statement from a module gate block."""
    # We have something like
    # dynamic(a) as n {
    # x: new Xor()
    # a, b -> x
    # a[n], b[n] -> x

    consume_comment(stream)

    stream.consume_whitespace()

    word = stream.consume_word()

    # Is identifier
    if stream.match(':'):
        return [parse_ident(word, stream)]

    elif stream.match('('):
        args = consume_call(stream)

        stream.consume_whitespace()

        if stream.consume_text('as'):
            stream.consume_whitespace()
            name = stream.consume_word()

            stream.consume_whitespace(False)

            stream.expect('{')

            stream.consume_whitespace()

            gates = parse_complex_field(stream)
            stream.expect('}')
            stream.consume_whitespace()

            return [stream.emit({
                "type": "as",
                "name": word,
                "args": args,
                "var": name,
                "gates": gates
            })]

        else:
            stream.error('SyntaxError', 'Unexpected call')

    # Wire
    # a[n], b[n] -> x
    elif '->' in stream.current_line:
        # Get back the dropped off first part
        stream.pos -= len(word)

        args = []
        while not stream.consume_text('->'):
            stream.consume_whitespace()
            args.append(parse_expr(stream))

            stream.consume_whitespace()
            if stream.consume_text('->'):
                break

            stream.expect(',')


        stream.consume_whitespace()
        to = stream.consume_word()
        stream.consume_whitespace()

        return [stream.emit({
            "type": "arrow",
            "from": args,
            "to": to
        })]


    else:
        stream.error('SyntaxError', 'Invalid syntax while parsing statement. Expected ident, call, or wire statement.')

def parse_complex_field(stream: TextStream) -> list[AstNode]:
    """Parse statements until a complex field's closing brace."""
    statements = []
    while not stream.match('}'):
        statements.extend(parse_statement(stream))
        stream.consume_whitespace()

    return statements

def parse_field(stream: TextStream) -> tuple[str, list[AstNode]]:
    """Parse a named module field and its contents."""
    # field {

    field = stream.consume_word()
    if not field in fields['module']:
        stream.error('UnknownFieldError', f'Unknown field: {field}', field)

    stream.consume_whitespace(False)

    stream.expect('{')

    stream.consume_whitespace()

    # Complex field like 'gates'
    if field in complex_fields:
        defs = parse_complex_field(stream)
        stream.expect('}')
        stream.consume_whitespace()
        return field, defs

    # Simple definitions
    defs = consume_defs(stream)

    stream.consume_whitespace()

    return field, defs

def parse_keyword(keyword: str, stream: TextStream) -> AstNode:
    """Parse a keyword-led module declaration or allocation expression."""
    stream.consume_whitespace()

    if keyword == 'module':
        # module Name(..) {
        #        ^^^^
        name = stream.consume_word()

        stream.consume_whitespace()

        # module Name(..) {
        #            ^^^^^^
        inherit = consume_classdef(stream)

        module_fields: AstNode = {}
        while not stream.match('}'):
            field, defs = parse_field(stream)
            if field not in complex_fields:
                module_fields[field] = defs

        stream.consume_whitespace()
        stream.expect('}')

        return {
            name: stream.emit({
                "inherit": inherit,
                "fields": stream.emit(module_fields),
                "gates": defs
            })
        }

    else:
        stream.error('SyntaxError', f"Invalid keyword: '{keyword}'", keyword)

def parse_ident(name: str, stream: TextStream) -> AstNode:
    """Parse a named gate assignment after its identifier."""
    stream.consume_whitespace()

    stream.expect(':')

    expr = parse_expr(stream)

    gate = stream.emit({
        "type": "gate",
        "name": name,
        "value": expr
    })

    return gate

def parse_toplevel(stream: TextStream) -> tuple[ModuleNodes, list[AstNode]]:
    """Parse one top-level module declaration or gate assignment."""
    consume_comment(stream)
    stream.consume_whitespace()
    word = stream.consume_word()

    if word in keywords:
        return parse_keyword(word, stream), []

    # Word is an identifier
    if stream.match(':'):
        return {}, [parse_ident(word, stream)]

    # Arrow statement at top level: expr, expr -> target
    if '->' in stream.current_line:
        stream.pos -= len(word)
        args = []
        while not stream.consume_text('->'):
            stream.consume_whitespace()
            args.append(parse_expr(stream))
            stream.consume_whitespace()
            if stream.consume_text('->'):
                break
            stream.expect(',')
        stream.consume_whitespace()
        to = stream.consume_word()
        return {}, [stream.emit({
            "type": "arrow",
            "from": args,
            "to": to
        })]

    stream.error('SyntaxError', f'invalid syntax while parsing toplevel: {word}', word)

def parse(source: str, debug=True) -> AstNode:
    """Parse source text into the compiler AST."""
    stream = TextStream(source, debug)

    ast = stream.emit({
        "modules": {},
        "gates": []
    })

    while stream:
        stream.consume_whitespace()

        m, g = parse_toplevel(stream)
        stream.consume_whitespace()

        ast['modules'].update(m)
        ast['gates'].extend(g)

    return ast
