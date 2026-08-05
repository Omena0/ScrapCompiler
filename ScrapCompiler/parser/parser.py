from .stream import TextStream

keywords = {"module", "new"}
fields = {
    'module': ['inputs', 'outputs', 'gates']
}
complex_fields = ['gates']

builtins = ['Xor', 'And', 'Or', 'Nor', 'XNor', 'Nand']

def consume_call(stream:TextStream):
    """Consumes (..)"""
    stream.expect('(')

    args = []
    while not stream.consume_text(')'):
        args.append(parse_expr(stream))
        if not stream.match(')'):
            stream.expect(',')

    stream.consume_whitespace()

    return args

def consume_classdef(stream:TextStream) -> list | None:
    """Consumes `(..) {`, returning `..`"""

    inherits = consume_call(stream)

    stream.expect('{')

    stream.consume_whitespace()

    return inherits

def consume_def(stream:TextStream):
    type = stream.consume_word()
    type_len = None
    if stream.consume_text('['):
        type_len = parse_expr(stream)
        stream.expect(']')

    stream.consume_whitespace()

    name = stream.consume_word()

    return {"name": name, "type": type, "len": type_len}

def consume_defs(stream:TextStream):
    defs = []
    while not stream.consume_text('}'):
        if stream.eof:
            stream.error('SyntaxError', "Unclosed '}'")

        defs.append(consume_def(stream))
        stream.consume_whitespace()

    return defs

def consume_comment(stream:TextStream):
    stream.consume_whitespace()
    if stream.consume_text('//'):
        stream.consume_until('\n')

# TODO
def parse_expr(stream: TextStream) -> dict:
    stream.consume_whitespace()

    # Integer literal
    if stream.peek().isdigit():
        value = stream.consume_while(lambda c: c.isdigit())
        return {
            "type": "int",
            "value": int(value)
        }

    # Boolean literals
    if stream.match("true"):
        stream.consume_text("true")
        return {
            "type": "bool",
            "value": True
        }

    if stream.match("false"):
        stream.consume_text("false")
        return {
            "type": "bool",
            "value": False
        }

    word = stream.consume_word()

    stream.consume_whitespace()

    consume_comment(stream)
    stream.consume_whitespace()

    if stream.peek() in "])}," or stream.match("->"):
        return {
            "type": "ident",
            "name": word
        }

    if stream.consume_text('['):
        idx = parse_expr(stream)
        stream.expect(']')
        return {
            "type": "index",
            "value": parse_expr(TextStream(word)),
            "index": idx
        }

    if word in keywords:
        return parse_keyword(word, stream)

    if stream.match('('):
        args = consume_call(stream)

        if stream.consume_text('['):
            idx = parse_expr(stream)
            stream.expect(']')
            return {
                "type": "index",
                "value": {
                    "type": "call",
                    "name": word,
                    "args": args
                },
                "index": idx
            }

        return {
            "type": "call",
            "name": word,
            "args": args
        }

    if stream.consume_text('<'):
        cast = stream.consume_word()
        stream.expect('>')

        args = consume_call(stream)

        if stream.consume_text('['):
            idx = parse_expr(stream)
            stream.expect(']')
            return {
                "type": "index",
                "value": {
                    "type": "call",
                    "name": word,
                    "cast_type": cast,
                    "args": args
                },
                "index": idx
            }

        return {
            "type": "call",
            "name": word,
            "cast_type": cast,
            "args": args
        }

    stream.error("SyntaxError", "Invalid expression")

def parse_statement(stream:TextStream) -> list:
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

            return [{
                "type": "as",
                "name": word,
                "args": args,
                "var": name,
                "gates": parse_complex_field(stream)
            }]

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

        return [{
            "type": "arrow",
            "from": args,
            "to": to
        }]


    else:
        stream.error('SyntaxError', 'Invalid syntax')

def parse_complex_field(stream:TextStream):
    statements = []
    while not stream.match('}'):
        statements.extend(parse_statement(stream))
        stream.consume_whitespace()

    return statements

def parse_field(stream:TextStream):
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

def parse_keyword(keyword:str, stream: TextStream) -> dict:
    stream.consume_whitespace()

    if keyword == 'module':
        # module Name(..) {
        #        ^^^^
        name = stream.consume_word()

        stream.consume_whitespace()

        # module Name(..) {
        #            ^^^^^^
        inherit = consume_classdef(stream)

        fields = {}
        while not stream.consume_text('}'):
            field, defs = parse_field(stream)
            if field not in complex_fields:
                fields[field] = defs

        stream.consume_whitespace()

        stream.expect('}')

        return {
            name: {
                "inherit": inherit,
                "fields": fields,
                "gates": defs
            }
        }

    elif keyword == 'new':
        stream.consume_whitespace()
        value = parse_expr(stream)
        return {
            "type": "new",
            "value": value
        }

    else:
        stream.error('SyntaxError', f"Invalid keyword: '{keyword}'", keyword)

def parse_ident(name:str, stream:TextStream) -> dict:
    stream.consume_whitespace()

    stream.expect(':')

    expr = parse_expr(stream)

    gate = {
        "type": "gate",
        "name": name,
        "value": expr
    }

    return gate

def parse_toplevel(stream: TextStream) -> tuple[dict, list]:
    stream.consume_whitespace()
    word = stream.consume_word()

    if word in keywords:
        return parse_keyword(word, stream), []

    # Word is an identifier
    if stream.match(':'):
        return {}, [parse_ident(word, stream)]

    stream.error('SyntaxError', f'invalid syntax: {word}', word)

def parse(source:str):
    stream = TextStream(source)

    ast = {
        "modules": {},
        "gates": []
    }

    while stream:
        stream.consume_whitespace()

        m, g = parse_toplevel(stream)
        stream.consume_whitespace()

        ast['modules'].update(m)
        ast['gates'].extend(g)

    return ast

