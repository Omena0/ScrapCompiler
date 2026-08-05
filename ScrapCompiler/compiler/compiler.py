from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Literal, NoReturn, TypeAlias

AstNode: TypeAlias = dict[str, Any]
SymbolTable: TypeAlias = dict[str, 'ResolvedType']
SignalTable: TypeAlias = dict[str, 'Signal']
TypeLength: TypeAlias = int | str | None
GatePrefix: TypeAlias = Literal['', 'IN', 'OUT']

_MISSING: Final = object()
_BUILTIN_GATES: Final = frozenset({'Xor', 'And', 'Or', 'Nor', 'XNor', 'Nand'})
_BUILTIN_TYPES: Final = frozenset({'bit', 'bool', 'dynamic'})
_IR_GATES: Final = {
    'And': 'AND',
    'Nand': 'NAND',
    'Nor': 'NOR',
    'Or': 'OR',
    'XNor': 'XNOR',
    'Xor': 'XOR',
}
_BINARY_GATES: Final = {
    '&': 'AND',
    '&&': 'AND',
    '|': 'OR',
    '||': 'OR',
    '^': 'XOR',
}

@dataclass(frozen=True, slots=True)
class ResolvedType:
    """A compiler-resolved type, optionally carrying a length or type argument."""

    name: str
    length: TypeLength = None
    arguments: tuple['ResolvedType', ...] = ()

@dataclass(frozen=True, slots=True)
class Signal:
    """A scalar or vector signal represented by logical gate handles."""

    bits: tuple[int, ...]
    value_type: ResolvedType = ResolvedType('bit')
    is_input: bool = False
    is_input: bool = False
    buffered: bool = False

@dataclass(slots=True)
class Gate:
    """One positioned IR gate whose final ID is its rendered line number."""

    type: str
    inputs: list[int]
    x: int
    y: int
    z: int
    prefix: GatePrefix = ''
    key: int = -1
    value_type: str = 'bit'

class SpatialAllocator:
    """Own gate handles and calculate deterministic spatial IR positions."""

    def __init__(self) -> None:
        """Create an empty gate collection."""
        self._gates: dict[int, Gate] = {}
        self._next_key = 0

    def create(
        self,
        gate_type: str,
        inputs: list[int],
        y: int,
        z: int,
        prefix: GatePrefix = '',
        value_type: str = 'bit',
    ) -> int:
        """Allocate a gate and return its internal handle."""
        key = self._next_key
        self._next_key += 1
        self._gates[key] = Gate(gate_type, list(inputs), 0, y, z, prefix, key, value_type)
        return key

    def inherit(self, key: int, gate_type: str, value_type: str | None = None) -> None:
        """Retag an existing output gate and clear its inherited inputs."""
        gate = self._get(key)
        gate.type = gate_type
        gate.inputs.clear()
        if value_type is not None:
            gate.value_type = value_type

    def append_inputs(self, key: int, inputs: list[int]) -> None:
        """Connect additional source gates to an existing gate."""
        self._get(key).inputs.extend(inputs)

    def mark_input(self, key: int) -> None:
        """Mark an existing gate handle as an input boundary."""
        self._get(key).prefix = 'IN'

    def is_output(self, key: int) -> bool:
        """Return whether a handle belongs to an output-prefixed gate."""
        return self._get(key).prefix == 'OUT'

    def build(self) -> list[Gate]:
        """Calculate gate times and return gates in allocation order."""
        times: dict[int, int] = {}
        for key in self._gates:
            self._time_for(key, times, set())

        for key, gate in self._gates.items():
            gate.x = times[key]

        collision_z: dict[tuple[int, int], set[int]] = {}
        for gate in self._gates.values():
            key = (gate.x, gate.y)
            used = collision_z.setdefault(key, set())
            if gate.z in used:
                new_z = 0
                while new_z in used:
                    new_z += 1
                gate.z = new_z
            used.add(gate.z)

        return list(self._gates.values())

    def _get(self, key: int) -> Gate:
        """Return one allocated gate or raise for an invalid handle."""
        try:
            return self._gates[key]
        except KeyError as error:
            raise ValueError(f'Unknown gate handle: {key}') from error

    def _time_for(
        self,
        key: int,
        times: dict[int, int],
        visiting: set[int],
    ) -> int:
        """Recursively calculate a gate's activation tick."""
        if key in times:
            return times[key]
        if key in visiting:
            raise ValueError('IR gates cannot contain a dependency cycle')

        visiting.add(key)
        gate = self._get(key)
        if not gate.inputs:
            time = 0
        else:
            source_time = max(self._time_for(source, times, visiting) for source in gate.inputs)
            time = source_time if gate.prefix == 'IN' else source_time + 1
        visiting.remove(key)
        times[key] = time
        return time

class ScrapCompiler:
    """Resolve Scrap types and lower module instances to positioned gate IR."""

    def __init__(self, ast: AstNode) -> None:
        """Initialize the compiler with a parsed AST."""
        self.ast = ast
        self.modules: dict[str, AstNode] = {}
        self.variables: SymbolTable = {}
        self.signals: SignalTable = {}
        self.module_types: dict[str, ResolvedType] = {}
        self._module_asts: dict[str, AstNode] = {}
        self._allocator = SpatialAllocator()
        self._next_z = 0

    def error(self, name: str, text: str, node: AstNode | None = None) -> NoReturn:
        """Print a compiler error with optional parser-provided source context."""
        if node is not None:
            source = node.get('error')
            line = node.get('line')
            column = node.get('column')
            if isinstance(source, str) and isinstance(line, int) and isinstance(column, int):
                print(source)
                print(' ' * max(column - 1, 0) + '^')
                print(f'At line {line}, col {column}')

        print(f'{name}: {text}')
        raise SystemExit(-1)

    def expect[T](
        self,
        value: T,
        name: str,
        message: str,
        expected: object = _MISSING,
        node: AstNode | None = None,
    ) -> T:
        """Return a validated value or report a compiler error."""
        valid = bool(value) if expected is _MISSING else value == expected
        if not valid:
            self.error(name, message, node)
        return value

    def resolve_type(
        self,
        name: str,
        length: AstNode | None = None,
        symbols: SymbolTable | None = None,
        node: AstNode | None = None,
    ) -> ResolvedType:
        """Resolve a declared type name and optional length expression."""
        if name in _BUILTIN_TYPES or self._is_integer_type_name(name):
            resolved = ResolvedType(name)

        elif name in self.module_types:
            resolved = self.module_types[name]
        else:
            self.error('UnknownTypeError', f"Unknown type: {name}", node)

        if length is None:
            return resolved

        return ResolvedType(
            resolved.name,
            self.resolve_length(length, symbols or {}, node),
            resolved.arguments,
        )

    def resolve_length(
        self,
        expression: AstNode,
        symbols: SymbolTable,
        node: AstNode | None = None,
    ) -> int | str:
        """Resolve an integer or dynamic-signal length expression."""
        resolved = self.resolve_expression(expression, symbols)
        expression_type = expression.get('type')
        if expression_type == 'int' and isinstance(expression.get('value'), int):
            return expression['value']
        if expression_type == 'ident' and resolved.name in {'int', 'dynamic'}:
            identifier = expression.get('name')
            if isinstance(identifier, str):
                return identifier

        self.error(
            'InvalidLengthError',
            'Lengths must be integer expressions or dynamic signal references',
            node or expression,
        )

    def resolve_expression(self, expression: AstNode, symbols: SymbolTable) -> ResolvedType:
        """Resolve the type of an expression within a symbol scope."""
        expression_type = expression.get('type')
        if expression_type == 'int':
            return ResolvedType('int')
        if expression_type == 'bool':
            return ResolvedType('bool')
        if expression_type == 'ident':
            return self._resolve_identifier(expression, symbols)
        if expression_type == 'index':
            return self._resolve_index(expression, symbols)
        if expression_type == 'field':
            return self._resolve_field(expression, symbols)
        if expression_type == 'call':
            return self._resolve_call(expression, symbols)
        if expression_type == 'new':
            return self._resolve_new(expression, symbols)
        if expression_type == 'unary':
            return self._resolve_unary(expression, symbols)
        if expression_type == 'binary':
            return self._resolve_binary(expression, symbols)
        self.error('InvalidExpressionError', 'Unknown expression type', expression)

    def compile_module(self, name: str, module: AstNode) -> AstNode:
        """Resolve all declarations and gate statements in one module."""
        fields = module.get('fields')
        if not isinstance(fields, dict):
            self.error('InvalidModule', f"Invalid module {name}, missing 'fields'", module)

        inputs = self._resolve_definitions(fields.get('inputs'), {}, module)
        outputs = self._resolve_definitions(fields.get('outputs'), inputs, module)
        symbols = {**inputs, **outputs}
        resolved_gates = self._resolve_statements(module.get('gates'), symbols, module)
        inherit = module.get('inherit', [])
        if not isinstance(inherit, list):
            self.error('InvalidModule', f"Invalid module {name}, invalid 'inherit'", module)

        return {
            'inherit': [self.resolve_expression(value, symbols) for value in inherit],
            'fields': {'inputs': inputs, 'outputs': outputs},
            'gates': resolved_gates,
        }

    def compile_modules(self, modules: dict[str, AstNode]) -> dict[str, AstNode]:
        """Predeclare and resolve every module in the AST."""
        self.module_types = {name: ResolvedType(name) for name in modules}
        self.modules = {
            name: self.compile_module(name, module)
            for name, module in modules.items()
        }
        return self.modules

    def compile(self) -> list[Gate]:
        """Resolve the AST and lower all top-level statements into IR gates."""
        modules = self.ast.get('modules')
        if not isinstance(modules, dict):
            self.error('InvalidAst', "Missing or invalid 'modules'", self.ast)
        self._module_asts = modules
        self.compile_modules(modules)
        self.variables = self._resolve_statements(self.ast.get('gates'), {}, self.ast)

        self._allocator = SpatialAllocator()
        self._next_z = 0
        self.signals = self._lower_statements(
            self.ast.get('gates'),
            {},
            {},
            0,
            {},
            False,
            False,
        )
        return self._allocator.build()

    @staticmethod
    def gates_to_ir(gates: list[Gate]) -> str:
        """Render positioned gates using explicit IDs and trailing type comments."""
        ordered = [
            *[gate for gate in gates if gate.prefix == 'IN'],
            *[gate for gate in gates if gate.prefix == ''],
            *[gate for gate in gates if gate.prefix == 'OUT'],
        ]
        line_ids = {gate.key: line for line, gate in enumerate(ordered, start=1)}
        lines: list[str] = []
        type_groups: dict[str, list[int]] = {}

        for gate in ordered:
            try:
                inputs = [str(line_ids[source]) for source in gate.inputs]
            except KeyError as error:
                raise ValueError(f'Unknown source gate handle: {error.args[0]}') from error

            line_id = line_ids[gate.key]
            parts = ([gate.prefix] if gate.prefix else []) + [
                str(gate.x),
                str(gate.y),
                str(gate.z),
                gate.type,
                *inputs,
            ]
            lines.append(f"{line_id}: {' '.join(parts)}")
            type_groups.setdefault(gate.value_type, []).append(line_id)

        for value_type, ids in sorted(type_groups.items()):
            lines.append(f"# {ScrapCompiler._format_id_ranges(ids)}: {value_type}")

        return '\n'.join(lines)

    @staticmethod
    def _format_id_ranges(ids: list[int]) -> str:
        """Format a sorted list of ids as a compact comma/range string."""
        if not ids:
            return ''

        ids = sorted(ids)
        ranges: list[str] = []
        start = prev = ids[0]

        for current in ids[1:]:
            if current == prev + 1:
                prev = current
                continue
            ranges.append(str(start) if start == prev else f'{start}-{prev}')
            start = prev = current

        ranges.append(str(start) if start == prev else f'{start}-{prev}')
        return ','.join(ranges)

    def _resolve_definitions(
        self,
        definitions: object,
        symbols: SymbolTable,
        node: AstNode,
    ) -> SymbolTable:
        """Resolve field definitions while making earlier names available."""
        if not isinstance(definitions, list):
            self.error('InvalidFields', 'Missing or invalid field definitions', node)

        resolved = dict(symbols)
        declared: SymbolTable = {}
        for definition in definitions:
            if not isinstance(definition, dict):
                self.error('InvalidDefinition', 'Field definition must be an object', node)
            name = definition.get('name')
            type_name = definition.get('type')
            if not isinstance(name, str) or not name:
                self.error('InvalidDefinition', 'Field definition is missing a name', definition)
            if not isinstance(type_name, str) or not type_name:
                self.error('InvalidDefinition', 'Field definition is missing a type', definition)
            if name in resolved:
                self.error('DuplicateNameError', f"Duplicate definition: {name}", definition)

            length = definition.get('len')
            if length is not None and not isinstance(length, dict):
                self.error('InvalidDefinition', 'Field length must be an expression', definition)
            declared[name] = self.resolve_type(type_name, length, resolved, definition)
            resolved[name] = declared[name]
        return declared

    def _resolve_statements(
        self,
        statements: object,
        symbols: SymbolTable,
        node: AstNode,
    ) -> SymbolTable:
        """Resolve gate statements and enforce type-safe assignments and wires."""
        if not isinstance(statements, list):
            self.error('InvalidGates', "Missing or invalid 'gates'", node)

        resolved = dict(symbols)
        for statement in statements:
            if not isinstance(statement, dict):
                self.error('InvalidGate', 'Gate statement must be an object', node)
            statement_type = statement.get('type')
            if statement_type == 'gate':
                self._resolve_assignment(statement, resolved)
            elif statement_type == 'arrow':
                self._resolve_arrow(statement, resolved)
            elif statement_type == 'as':
                self._resolve_loop(statement, resolved)
            else:
                self.error('InvalidGate', 'Unknown gate statement type', statement)
        return resolved

    def _resolve_assignment(self, statement: AstNode, symbols: SymbolTable) -> None:
        """Resolve a gate assignment and bind or validate its target type."""
        name = statement.get('name')
        value = statement.get('value')
        if not isinstance(name, str) or not name:
            self.error('InvalidGate', 'Gate assignment is missing a name', statement)
        if not isinstance(value, dict):
            self.error('InvalidGate', 'Gate assignment is missing a value', statement)

        value_type = self.resolve_expression(value, symbols)
        current_type = symbols.get(name)
        if current_type is not None and not self._is_assignable(current_type, value_type):
            self.error(
                'TypeMismatchError',
                f"Cannot assign {self._format_type(value_type)} to {self._format_type(current_type)}",
                statement,
            )
        symbols[name] = current_type or value_type

    def _resolve_arrow(self, statement: AstNode, symbols: SymbolTable) -> None:
        """Resolve a wire statement and validate every source against its target."""
        target = statement.get('to')
        sources = statement.get('from')
        if not isinstance(target, str) or not target:
            self.error('InvalidGate', 'Wire statement is missing a target', statement)
        if not isinstance(sources, list):
            self.error('InvalidGate', 'Wire statement is missing sources', statement)
        target_type = symbols.get(target)
        if target_type is None:
            self.error('UnknownIdentifierError', f"Unknown wire target: {target}", statement)

        for source in sources:
            if not isinstance(source, dict):
                self.error('InvalidGate', 'Wire source must be an expression', statement)
            source_type = self.resolve_expression(source, symbols)
            if not self._is_assignable(target_type, source_type):
                self.error(
                    'TypeMismatchError',
                    f"Cannot wire {self._format_type(source_type)} to {self._format_type(target_type)}",
                    source,
                )

    def _resolve_loop(self, statement: AstNode, symbols: SymbolTable) -> None:
        """Resolve a dynamic loop with an integer index variable."""
        name = statement.get('name')
        arguments = statement.get('args')
        variable = statement.get('var')
        gates = statement.get('gates')
        if name != 'dynamic' or not isinstance(arguments, list) or len(arguments) != 1:
            self.error('InvalidGate', 'Invalid dynamic loop', statement)
        if not isinstance(variable, str) or not variable:
            self.error('InvalidGate', 'Dynamic loop is missing its index variable', statement)
        if not isinstance(gates, list):
            self.error('InvalidGate', 'Dynamic loop is missing its body', statement)

        source = arguments[0]
        if not isinstance(source, dict):
            self.error('InvalidGate', 'Dynamic loop argument must be an expression', statement)
        source_type = self.resolve_expression(source, symbols)
        if source_type.name != 'dynamic':
            self.error('TypeMismatchError', 'Dynamic loops require a dynamic signal', source)
        self._resolve_statements(gates, {**symbols, variable: ResolvedType('int')}, statement)

    def _resolve_identifier(self, expression: AstNode, symbols: SymbolTable | dict[str, Any]) -> ResolvedType:
        """Resolve an identifier expression from the active symbol table."""
        name = expression.get('name')
        if not isinstance(name, str) or not name:
            self.error('InvalidExpressionError', 'Identifier expression is missing a name', expression)
        resolved = symbols.get(name)
        if resolved is None:
            self.error('UnknownIdentifierError', f"Unknown identifier: {name}", expression)
        if isinstance(resolved, Signal):
            return resolved.value_type
        if isinstance(resolved, ResolvedType):
            return resolved
        self.error('InvalidExpressionError', f"Invalid symbol table entry for {name}", expression)

    def _resolve_index(self, expression: AstNode, symbols: SymbolTable) -> ResolvedType:
        """Resolve an indexed signal or typed module result to its element type."""
        value = expression.get('value')
        index = expression.get('index')
        if not isinstance(value, dict) or not isinstance(index, dict):
            self.error('InvalidExpressionError', 'Invalid index expression', expression)
        index_type = self.resolve_expression(index, symbols)
        if not self._is_integer_type(index_type):
            self.error('TypeMismatchError', 'Indexes must be integers', index)

        value_type = self.resolve_expression(value, symbols)
        if value_type.name == 'dynamic':
            return ResolvedType('bit')
        if self._is_integer_type(value_type):
            return ResolvedType('bit')
        if value_type.arguments:
            return value_type.arguments[0]
        self.error('TypeMismatchError', f"Cannot index {self._format_type(value_type)}", expression)

    def _resolve_field(self, expression: AstNode, symbols: SymbolTable) -> ResolvedType:
        """Resolve a field selection on a module call result."""
        value = expression.get('value')
        name = expression.get('name')
        if not isinstance(value, dict):
            self.error('InvalidExpressionError', 'Invalid field selection expression', expression)
        if not isinstance(name, str) or not name:
            self.error('InvalidExpressionError', 'Field selection is missing a name', expression)

        if value.get('type') == 'call' and isinstance(value.get('name'), str) and value.get('name') in self._module_asts:
            module = self._module_asts[value['name']]
            fields = module.get('fields')
            if not isinstance(fields, dict):
                self.error('InvalidModule', f"Invalid module {value['name']}", module)
            output_defs = fields.get('outputs')
            if not isinstance(output_defs, list):
                self.error('InvalidModule', f"Invalid module {value['name']} outputs", module)

            for definition in output_defs:
                if isinstance(definition, dict) and self._definition_name(definition) == name:
                    generic_width = self._generic_width(value, fields.get('inputs', []), output_defs)
                    signals: SignalTable = {}
                    for definition_input in fields.get('inputs', []):
                        if not isinstance(definition_input, dict):
                            continue
                        input_name = self._definition_name(definition_input)
                        input_type = self._resolve_definition_type(definition_input, signals, {}, generic_width)
                        input_width = self._field_width(definition_input, signals, {}, generic_width)
                        signals[input_name] = Signal(tuple(range(input_width)), value_type=input_type)
                    return self._resolve_definition_type(definition, signals, {}, generic_width)

            self.error('UnknownIdentifierError', f"Unknown module output: {name}", expression)

        self.error('TypeMismatchError', 'Field selection is only supported on module call results', expression)

    def _resolve_call(self, expression: AstNode, symbols: SymbolTable) -> ResolvedType:
        """Resolve a built-in gate, dynamic helper, or module call."""
        name = expression.get('name')
        arguments = expression.get('args')
        if not isinstance(name, str) or not name:
            self.error('InvalidExpressionError', 'Call expression is missing a name', expression)
        if not isinstance(arguments, list):
            self.error('InvalidExpressionError', 'Call expression is missing arguments', expression)

        argument_types: list[ResolvedType] = []
        for argument in arguments:
            if not isinstance(argument, dict):
                self.error('InvalidExpressionError', 'Call argument must be an expression', expression)
            argument_value = argument
            if argument.get('type') == 'named_arg':
                argument_value = argument.get('value')
                if not isinstance(argument_value, dict):
                    self.error('InvalidExpressionError', 'Named argument is missing a value', argument)
            argument_types.append(self.resolve_expression(argument_value, symbols))

        cast_type = expression.get('cast_type')
        if cast_type is not None and not isinstance(cast_type, str):
            self.error('InvalidExpressionError', 'Call type argument must be a name', expression)
        if name in _BUILTIN_GATES:
            for argument_type in argument_types:
                if argument_type.name != 'bit':
                    self.error('TypeMismatchError', f"{name} accepts only bit inputs", expression)
            return ResolvedType('bit')
        if name == 'dynamic':
            if len(argument_types) != 1 or argument_types[0].name != 'dynamic':
                self.error('TypeMismatchError', 'dynamic requires one dynamic signal', expression)
            return argument_types[0]
        if name not in self.module_types:
            self.error('UnknownTypeError', f"Unknown callable type: {name}", expression)

        type_arguments: tuple[ResolvedType, ...] = ()
        if cast_type is not None:
            type_arguments = (self.resolve_type(cast_type, node=expression),)
        return ResolvedType(name, arguments=type_arguments)

    def _resolve_new(self, expression: AstNode, symbols: SymbolTable) -> ResolvedType:
        """Resolve an allocation expression to its constructed value type."""
        value = expression.get('value')
        if not isinstance(value, dict):
            self.error('InvalidExpressionError', 'new expression is missing a value', expression)
        return self.resolve_expression(value, symbols)

    def _resolve_unary(self, expression: AstNode, symbols: SymbolTable) -> ResolvedType:
        """Resolve a unary operator and validate its operand type."""
        operator = expression.get('op')
        value = expression.get('value')
        if not isinstance(operator, str) or not isinstance(value, dict):
            self.error('InvalidExpressionError', 'Invalid unary expression', expression)
        value_type = self.resolve_expression(value, symbols)
        if operator in {'+', '-'} and not self._is_integer_type(value_type):
            self.error('TypeMismatchError', f"{operator} requires an integer", expression)
        if operator == '~' and value_type.name not in {'bit', 'int'} and not self._is_integer_type(value_type):
            self.error('TypeMismatchError', '~ requires a bit or integer', expression)
        if operator == '!' and value_type.name not in {'bit', 'bool'}:
            self.error('TypeMismatchError', '! requires a bit or boolean', expression)
        return value_type

    def _resolve_binary(self, expression: AstNode, symbols: SymbolTable) -> ResolvedType:
        """Resolve a binary operator and validate its operand types."""
        operator = expression.get('op')
        left = expression.get('left')
        right = expression.get('right')
        if not isinstance(operator, str) or not isinstance(left, dict) or not isinstance(right, dict):
            self.error('InvalidExpressionError', 'Invalid binary expression', expression)
        left_type = self.resolve_expression(left, symbols)
        right_type = self.resolve_expression(right, symbols)
        if operator in {'==', '!=', '<', '<=', '>', '>='}:
            if not self._is_assignable(left_type, right_type):
                self.error('TypeMismatchError', 'Comparison operands must have matching types', expression)
            return ResolvedType('bool')
        if operator in {'&&', '||'}:
            if left_type.name not in {'bit', 'bool'} or right_type.name not in {'bit', 'bool'}:
                self.error('TypeMismatchError', f"{operator} requires bit or boolean operands", expression)
            return ResolvedType('bit' if 'bit' in {left_type.name, right_type.name} else 'bool')
        if operator in {'&', '|', '^'}:
            if left_type.name == right_type.name == 'bit':
                return ResolvedType('bit')
            if self._is_integer_type(left_type) and self._is_integer_type(right_type):
                return self._common_integer_type(left_type, right_type)
            self.error('TypeMismatchError', f"{operator} requires matching bit or integer operands", expression)
        if operator in {'+', '-', '*', '/', '%', '<<', '>>'}:
            if not self._is_integer_type(left_type) or not self._is_integer_type(right_type):
                self.error('TypeMismatchError', f"{operator} requires integer operands", expression)
            return self._common_integer_type(left_type, right_type)
        self.error('InvalidExpressionError', f"Unknown binary operator: {operator}", expression)

    def _lower_statements(
        self,
        statements: object,
        signals: SignalTable,
        indices: dict[str, int],
        z: int,
        output_ports: SignalTable,
        in_dynamic_loop: bool,
        final_iteration: bool,
    ) -> SignalTable:
        """Lower statement AST nodes and return their resulting signal bindings."""
        if not isinstance(statements, list):
            self.error('InvalidGates', "Missing or invalid 'gates'", self.ast)

        lowered = dict(signals)
        for statement in statements:
            if not isinstance(statement, dict):
                self.error('InvalidGate', 'Gate statement must be an object', self.ast)
            statement_type = statement.get('type')
            if statement_type == 'gate':
                self._lower_assignment(
                    statement,
                    lowered,
                    indices,
                    z,
                    output_ports,
                    in_dynamic_loop,
                    final_iteration,
                )
            elif statement_type == 'arrow':
                self._lower_arrow(statement, lowered, indices, z)
            elif statement_type == 'as':
                self._lower_dynamic(statement, lowered, indices, z, output_ports)
            else:
                self.error('InvalidGate', 'Unknown gate statement type', statement)
        return lowered

    def _mark_output_signal(self, signal: Signal) -> None:
        """Mark every gate in a signal as an output boundary."""
        for gate in signal.bits:
            self._allocator.mark_output(gate)

    def _lower_assignment(
        self,
        statement: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        z: int,
        output_ports: SignalTable,
        in_dynamic_loop: bool,
        final_iteration: bool,
    ) -> None:
        """Lower a gate declaration or rebind an alias signal."""
        name = statement.get('name')
        value = statement.get('value')
        if not isinstance(name, str) or not isinstance(value, dict):
            self.error('InvalidGate', 'Invalid gate assignment', statement)

        target = None
        if name in output_ports:
            target = output_ports[name] if not in_dynamic_loop or final_iteration else None
        elif name in signals:
            target = signals[name]

        if value.get('type') == 'new':
            signals[name] = self._lower_new(value, signals, indices, z, target, statement)
            return
        signals[name] = self._lower_expression(value, signals, indices, z, None)

    def _lower_expression(
        self,
        expression: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        z: int,
        width: int | None,
    ) -> Signal:
        """Lower an expression to a signal, optionally coercing its width."""
        expression_type = expression.get('type')
        if expression_type == 'bool':
            value = expression.get('value')
            if not isinstance(value, bool):
                self.error('InvalidExpressionError', 'Invalid boolean expression', expression)
            return self._constant_signal(int(value), width or 1, z, ResolvedType('bool'))
        if expression_type == 'int':
            value = expression.get('value')
            if not isinstance(value, int):
                self.error('InvalidExpressionError', 'Invalid integer expression', expression)
            actual_width = width or max(value.bit_length(), 1)
            return self._constant_signal(value, actual_width, z, ResolvedType(f'u{actual_width}'))
        if expression_type == 'ident':
            name = expression.get('name')
            if not isinstance(name, str) or name not in signals:
                self.error('UnknownIdentifierError', f"Unknown identifier: {name}", expression)
            return self._coerce_width(signals[name], width, expression)
        if expression_type == 'index':
            return self._lower_index(expression, signals, indices, z)
        if expression_type == 'field':
            return self._lower_field(expression, signals, indices, z, width)
        if expression_type == 'call':
            return self._lower_call(expression, signals, indices, z, width)
        if expression_type == 'new':
            return self._lower_new(expression, signals, indices, z, None, expression)
        if expression_type == 'unary':
            return self._lower_unary(expression, signals, indices, z, width)
        if expression_type == 'binary':
            return self._lower_binary(expression, signals, indices, z, width)
        self.error('InvalidExpressionError', 'Unsupported IR expression', expression)

    def _lower_arrow(
        self,
        statement: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        z: int,
    ) -> None:
        """Append all wire sources to the gate or gates bound by a target name."""
        target_name = statement.get('to')
        sources = statement.get('from')
        if not isinstance(target_name, str) or not isinstance(sources, list):
            self.error('InvalidGate', 'Invalid wire statement', statement)
        target = signals.get(target_name)
        if target is None:
            self.error('UnknownIdentifierError', f"Unknown wire target: {target_name}", statement)

        source_signals = [
            self._lower_expression(source, signals, indices, z, None)
            for source in sources
            if isinstance(source, dict)
        ]
        if len(source_signals) != len(sources):
            self.error('InvalidGate', 'Wire source must be an expression', statement)

        for target_index, gate in enumerate(target.bits):
            inputs: list[int] = []
            for source in source_signals:
                inputs.extend(self._expand_for_width(source, len(target.bits), target_index, statement))
            self._allocator.append_inputs(gate, inputs)

    def _lower_dynamic(
        self,
        statement: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        z: int,
        output_ports: SignalTable,
    ) -> None:
        """Unroll a dynamic block once for every bit of its source signal."""
        name = statement.get('name')
        arguments = statement.get('args')
        variable = statement.get('var')
        gates = statement.get('gates')
        if name != 'dynamic' or not isinstance(arguments, list) or len(arguments) != 1:
            self.error('InvalidGate', 'Invalid dynamic loop', statement)
        if not isinstance(variable, str) or not isinstance(gates, list):
            self.error('InvalidGate', 'Invalid dynamic loop body', statement)
        source = arguments[0]
        if not isinstance(source, dict):
            self.error('InvalidGate', 'Dynamic loop source must be an expression', statement)
        dynamic_signal = self._lower_expression(source, signals, indices, z, None)
        if not dynamic_signal.bits:
            self.error('InvalidGate', 'Dynamic loop source cannot be empty', source)

        for index in range(len(dynamic_signal.bits)):
            loop_indices = {**indices, variable: index}
            loop_signals = {
                **signals,
                variable: Signal((0,), value_type=ResolvedType('int')),
            }
            updated = self._lower_statements(
                gates,
                loop_signals,
                loop_indices,
                z,
                output_ports,
                True,
                index == len(dynamic_signal.bits) - 1,
            )
            signals.update(updated)

    def _lower_new(
        self,
        expression: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        z: int,
        target: Signal | None,
        node: AstNode,
    ) -> Signal:
        """Create a built-in gate, module instance, or retag an inherited output gate in place."""
        value = expression.get('value')
        if not isinstance(value, dict):
            self.error('InvalidExpressionError', 'new requires a gate or module call', expression)

        if value.get('type') == 'field':
            return self._lower_expression(value, signals, indices, z, width=None)

        if value.get('type') != 'call':
            self.error('InvalidExpressionError', 'new requires a gate or module call', expression)

        name = value.get('name')
        arguments = value.get('args')
        if not isinstance(name, str) or not isinstance(arguments, list):
            self.error('InvalidExpressionError', 'new requires a valid call expression', value)

        if name in _IR_GATES:
            argument_signals = [
                self._lower_expression(argument, signals, indices, z, None)
                for argument in arguments
                if isinstance(argument, dict)
            ]
            if len(argument_signals) != len(arguments):
                self.error('InvalidExpressionError', 'Gate argument must be an expression', value)

            value_type = self.resolve_expression(value, signals)
            inherited = self._find_inherited_output(target, argument_signals)
            if inherited is not None:
                inherited_keys = set(inherited.bits)
                argument_signals = [
                    signal for signal in argument_signals
                    if set(signal.bits) != inherited_keys
                ]
                formatted_value_type = self._format_type(value_type)
                for gate in inherited.bits:
                    self._allocator.inherit(gate, _IR_GATES[name], value_type=formatted_value_type)
                for target_index, gate in enumerate(inherited.bits):
                    inputs: list[int] = []
                    for source in argument_signals:
                        inputs.extend(self._expand_for_width(source, len(inherited.bits), target_index, node))
                    self._allocator.append_inputs(gate, inputs)
                return inherited

            width = len(target.bits) if target is not None else self._signal_width(argument_signals, 1)
            gate_bits: list[int] = []
            formatted_value_type = self._format_type(value_type)
            prefix = 'IN' if any(source.is_input for source in argument_signals) else ''
            for index in range(width):
                inputs: list[int] = []
                for source in argument_signals:
                    inputs.extend(self._expand_for_width(source, width, index, node))
                gate_bits.append(self._allocator.create(_IR_GATES[name], inputs, index, z, prefix, value_type=formatted_value_type))
            return Signal(tuple(gate_bits), value_type=value_type)

        if name in self._module_asts:
            return self._instantiate_module(value, signals, indices, z)

        self.error('UnknownTypeError', f"Unknown callable type: {name}", value)

    def _lower_index(
        self,
        expression: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        z: int,
    ) -> Signal:
        """Lower an indexed expression to exactly one bit signal."""
        value = expression.get('value')
        index = expression.get('index')
        if not isinstance(value, dict) or not isinstance(index, dict):
            self.error('InvalidExpressionError', 'Invalid index expression', expression)
        signal = self._lower_expression(value, signals, indices, z, None)
        position = self._evaluate_integer(index, indices)
        if not 0 <= position < len(signal.bits):
            self.error('IndexError', f'Index {position} is outside a {len(signal.bits)}-bit value', expression)
        return Signal((signal.bits[position],), value_type=ResolvedType('bit'), is_input=signal.is_input)

    def _lower_field(
        self,
        expression: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        z: int,
        width: int | None,
    ) -> Signal:
        """Lower a module field selection to the selected output signal."""
        value = expression.get('value')
        name = expression.get('name')
        if not isinstance(value, dict):
            self.error('InvalidExpressionError', 'Invalid field selection expression', expression)
        if not isinstance(name, str) or not name:
            self.error('InvalidExpressionError', 'Field selection is missing a name', expression)
        if value.get('type') == 'call' and isinstance(value.get('name'), str) and value.get('name') in self._module_asts:
            return self._instantiate_module(value, signals, indices, z, selected_output=name)
        self.error('TypeMismatchError', 'Field selection is only supported on module call results', expression)

    def _lower_call(
        self,
        expression: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        z: int,
        width: int | None,
    ) -> Signal:
        """Lower a direct built-in call or instantiate a module call."""
        name = expression.get('name')
        if not isinstance(name, str):
            self.error('InvalidExpressionError', 'Call expression is missing a name', expression)
        if name in _IR_GATES:
            return self._lower_builtin_call(expression, signals, indices, z, width)
        if name in self._module_asts:
            return self._instantiate_module(expression, signals, indices, z)
        self.error('UnknownTypeError', f"Unknown callable type: {name}", expression)

    def _lower_builtin_call(
        self,
        expression: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        z: int,
        width: int | None,
    ) -> Signal:
        """Lower a built-in logic call with its arguments as gate inputs."""
        name = expression.get('name')
        arguments = expression.get('args')
        if not isinstance(name, str) or not isinstance(arguments, list):
            self.error('InvalidExpressionError', 'Invalid built-in gate call', expression)
        sources = [
            self._lower_expression(argument, signals, indices, z, width)
            for argument in arguments
            if isinstance(argument, dict)
        ]
        if len(sources) != len(arguments):
            self.error('InvalidExpressionError', 'Gate argument must be an expression', expression)
        signal_width = width or self._signal_width(sources, 1)
        resolved_type = self.resolve_expression(expression, signals)
        formatted_value_type = self._format_type(resolved_type)
        prefix = 'IN' if any(source.is_input for source in sources) else ''
        bits: list[int] = []
        for index in range(signal_width):
            inputs: list[int] = []
            for source in sources:
                inputs.extend(self._expand_for_width(source, signal_width, index, expression))
            bits.append(self._allocator.create(_IR_GATES[name], inputs, index, z, prefix, value_type=formatted_value_type))
        return Signal(tuple(bits), value_type=resolved_type)

    def _instantiate_module(
        self,
        expression: AstNode,
        parent_signals: SignalTable,
        parent_indices: dict[str, int],
        parent_z: int,
        selected_output: str | None = None,
    ) -> Signal:
        """Instantiate a module, bind its inputs, and return its primary output or a selected output."""
        name = expression.get('name')
        if not isinstance(name, str):
            self.error('InvalidExpressionError', 'Module call is missing a name', expression)
        module = self._module_asts[name]
        fields = module.get('fields')
        if not isinstance(fields, dict):
            self.error('InvalidModule', f"Invalid module {name}", module)
        input_defs = fields.get('inputs')
        output_defs = fields.get('outputs')
        gates = module.get('gates')
        if not isinstance(input_defs, list) or not isinstance(output_defs, list) or not isinstance(gates, list):
            self.error('InvalidModule', f"Invalid module {name} fields", module)

        instance_z = self._next_z
        self._next_z += 1
        generic_width = self._generic_width(expression, input_defs, output_defs)
        positional, named = self._bind_call_arguments(expression, input_defs)
        signals: SignalTable = {}
        output_ports: SignalTable = {}

        for position, definition in enumerate(input_defs):
            if not isinstance(definition, dict):
                self.error('InvalidDefinition', 'Input definition must be an object', module)
            field_name = self._definition_name(definition)
            input_type = self._resolve_definition_type(definition, signals, parent_indices, generic_width)
            field_width = self._field_width(definition, signals, parent_indices, generic_width)
            buffered = self._definition_buffered(definition)
            argument = named.get(field_name)
            if argument is None and position < len(positional):
                argument = positional[position]
            if argument is None:
                if not definition.get('optional', False):
                    self.error('MissingArgumentError', f"Missing module input: {field_name}", expression)
                source = self._constant_signal(0, field_width, instance_z, input_type)
                mark_input = False
            else:
                source = self._lower_expression(
                    argument,
                    parent_signals,
                    parent_indices,
                    parent_z,
                    field_width,
                )
                mark_input = not buffered
            signals[field_name] = self._input_ports(source, instance_z, buffered, mark_input)

        for definition in output_defs:
            if not isinstance(definition, dict):
                self.error('InvalidDefinition', 'Output definition must be an object', module)
            field_name = self._definition_name(definition)
            output_type = self._resolve_definition_type(definition, signals, parent_indices, generic_width)
            field_width = self._field_width(definition, signals, parent_indices, generic_width)
            port = self._output_ports(field_width, instance_z, output_type)
            signals[field_name] = port
            output_ports[field_name] = port

        lowered = self._lower_statements(
            gates,
            signals,
            {},
            instance_z,
            output_ports,
            False,
            False,
        )
        primary = self._primary_output(output_defs, output_ports, generic_width, module)
        for field_name, port in output_ports.items():
            if field_name in lowered and len(port.bits) == len(lowered[field_name].bits):
                output_ports[field_name] = lowered[field_name]
        if selected_output is not None:
            if selected_output not in output_ports:
                self.error('UnknownIdentifierError', f"Unknown module output: {selected_output}", expression)
            return output_ports[selected_output]
        return primary

    def _input_ports(self, source: Signal, z: int, buffered: bool, mark_input: bool) -> Signal:
        """Bind a module input to the instantiated module scope.

        Buffered inputs get an IN-prefixed OR gate buffer. Unbuffered inputs
        are carried through and tagged for the first consuming gate.
        """
        if buffered:
            formatted_value_type = self._format_type(source.value_type)
            bits = [
                self._allocator.create('OR', [gate], index, z, 'IN', value_type=formatted_value_type)
                for index, gate in enumerate(source.bits)
            ]
            return Signal(tuple(bits), value_type=source.value_type)

        if mark_input:
            return Signal(source.bits, source.value_type, is_input=True)
        return source

    def _output_ports(self, width: int, z: int, value_type: ResolvedType) -> Signal:
        """Create default OUT OR gates that can later inherit another gate type."""
        formatted_value_type = self._format_type(value_type)
        bits = [
            self._allocator.create('OR', [], index, z, 'OUT', value_type=formatted_value_type)
            for index in range(width)
        ]
        return Signal(tuple(bits), value_type=value_type)

    def _primary_output(
        self,
        definitions: list[object],
        output_ports: SignalTable,
        generic_width: int,
        node: AstNode,
    ) -> Signal:
        """Select the dynamic output matching the module call's generic width."""
        for definition in definitions:
            if isinstance(definition, dict) and definition.get('type') == 'dynamic':
                name = self._definition_name(definition)
                output = output_ports[name]
                if len(output.bits) == generic_width:
                    return output
        for definition in definitions:
            if isinstance(definition, dict):
                return output_ports[self._definition_name(definition)]
        self.error('InvalidModule', 'Module has no outputs', node)

    def _bind_call_arguments(
        self,
        expression: AstNode,
        definitions: list[object],
    ) -> tuple[list[AstNode], dict[str, AstNode]]:
        """Split positional and named call arguments and validate their names."""
        arguments = expression.get('args')
        if not isinstance(arguments, list):
            self.error('InvalidExpressionError', 'Call expression is missing arguments', expression)
        known_names = {
            self._definition_name(definition)
            for definition in definitions
            if isinstance(definition, dict)
        }
        positional: list[AstNode] = []
        named: dict[str, AstNode] = {}
        for argument in arguments:
            if not isinstance(argument, dict):
                self.error('InvalidExpressionError', 'Call argument must be an expression', expression)
            if argument.get('type') != 'named_arg':
                positional.append(argument)
                continue
            argument_name = argument.get('name')
            value = argument.get('value')
            if not isinstance(argument_name, str) or argument_name not in known_names:
                self.error('UnknownArgumentError', f"Unknown module input: {argument_name}", argument)
            if not isinstance(value, dict):
                self.error('InvalidExpressionError', 'Named argument is missing a value', argument)
            if argument_name in named:
                self.error('DuplicateArgumentError', f"Repeated module input: {argument_name}", argument)
            named[argument_name] = value
        if len(positional) > len(definitions):
            self.error('ArgumentError', 'Too many positional module inputs', expression)
        return positional, named

    def _generic_width(
        self,
        expression: AstNode,
        input_defs: list[object],
        output_defs: list[object],
    ) -> int:
        """Resolve a module call's ``<uN>`` dynamic signal width."""
        needs_width = any(
            isinstance(definition, dict) and definition.get('type') == 'dynamic'
            for definition in [*input_defs, *output_defs]
        )
        cast_type = expression.get('cast_type')
        if cast_type is None and not needs_width:
            return 1
        if not isinstance(cast_type, str):
            self.error('TypeArgumentError', 'Dynamic modules require a <uN> type argument', expression)
        if cast_type == 'bit':
            return 1
        if not self._is_integer_type_name(cast_type) or cast_type[0] != 'u':
            self.error('TypeArgumentError', 'Dynamic modules require an unsigned integer type', expression)
        width = int(cast_type[1:])
        if width <= 0:
            self.error('TypeArgumentError', 'Dynamic module width must be positive', expression)
        return width

    def _field_width(
        self,
        definition: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        generic_width: int,
    ) -> int:
        """Resolve a field declaration to a concrete number of signal bits."""
        type_name = definition.get('type')
        if type_name == 'bit' or type_name == 'bool':
            return 1
        if isinstance(type_name, str) and self._is_integer_type_name(type_name):
            return int(type_name[1:])
        if type_name != 'dynamic':
            self.error('UnknownTypeError', f"Unsupported IR field type: {type_name}", definition)

        length = definition.get('len')
        if length is None:
            return generic_width
        if not isinstance(length, dict):
            self.error('InvalidDefinition', 'Dynamic field length must be an expression', definition)
        if length.get('type') == 'ident':
            name = length.get('name')
            if isinstance(name, str) and name in signals:
                return len(signals[name].bits)
        return self._evaluate_integer(length, indices)

    def _resolve_definition_type(
        self,
        definition: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        generic_width: int,
    ) -> ResolvedType:
        """Resolve a field definition to its actual value type."""
        type_name = definition.get('type')
        if type_name == 'bit' or type_name == 'bool':
            return ResolvedType(type_name)
        if isinstance(type_name, str) and self._is_integer_type_name(type_name):
            return ResolvedType(type_name)
        if type_name != 'dynamic':
            self.error('UnknownTypeError', f"Unsupported IR field type: {type_name}", definition)

        length = definition.get('len')
        if length is None:
            return ResolvedType('dynamic', generic_width)
        if not isinstance(length, dict):
            self.error('InvalidDefinition', 'Dynamic field length must be an expression', definition)
        if length.get('type') == 'ident':
            name = length.get('name')
            if isinstance(name, str) and name in signals:
                return ResolvedType('dynamic', len(signals[name].bits))
        return ResolvedType('dynamic', self._evaluate_integer(length, indices))

    def _definition_buffered(self, definition: AstNode) -> bool:
        """Return whether an input definition was declared buffered."""
        buffered = definition.get('buffered')
        return bool(buffered)

    def _find_inherited_output(
        self,
        target: Signal | None,
        arguments: list[Signal],
    ) -> Signal | None:
        """Find an output signal that a ``new`` expression can retag in place."""
        if len(arguments) == 1:
            candidate = arguments[0]
            if candidate.bits and all(self._allocator.is_output(gate) for gate in candidate.bits):
                return candidate
        if target is not None and all(self._allocator.is_output(gate) for gate in target.bits):
            return target
        return None

    def _lower_unary(
        self,
        expression: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        z: int,
        width: int | None,
    ) -> Signal:
        """Lower bitwise negation; reject integer-only unary IR operations."""
        operator = expression.get('op')
        value = expression.get('value')
        if not isinstance(operator, str) or not isinstance(value, dict):
            self.error('InvalidExpressionError', 'Invalid unary expression', expression)
        if operator not in {'!', '~'}:
            self.error('UnsupportedExpressionError', f"Unsupported IR unary operator: {operator}", expression)
        source = self._lower_expression(value, signals, indices, z, width)
        resolved_type = self.resolve_expression(expression, signals)
        formatted_value_type = self._format_type(resolved_type)
        prefix = 'IN' if source.is_input else ''
        return Signal(tuple(
            self._allocator.create('NOT', [gate], index, z, prefix, value_type=formatted_value_type)
            for index, gate in enumerate(source.bits)
        ), value_type=resolved_type)

    def _lower_binary(
        self,
        expression: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        z: int,
        width: int | None,
    ) -> Signal:
        """Lower bitwise logical binary expressions to one gate per bit."""
        operator = expression.get('op')
        left = expression.get('left')
        right = expression.get('right')
        if not isinstance(operator, str) or not isinstance(left, dict) or not isinstance(right, dict):
            self.error('InvalidExpressionError', 'Invalid binary expression', expression)
        gate_type = _BINARY_GATES.get(operator)
        if gate_type is None:
            self.error('UnsupportedExpressionError', f"Unsupported IR binary operator: {operator}", expression)
        left_signal = self._lower_expression(left, signals, indices, z, width)
        right_signal = self._lower_expression(right, signals, indices, z, width)
        signal_width = width or self._signal_width([left_signal, right_signal], 1)
        resolved_type = self.resolve_expression(expression, signals)
        formatted_value_type = self._format_type(resolved_type)
        is_input = left_signal.is_input or right_signal.is_input
        prefix = 'IN' if is_input else ''
        bits: list[int] = []
        for index in range(signal_width):
            inputs = [
                *self._expand_for_width(left_signal, signal_width, index, expression),
                *self._expand_for_width(right_signal, signal_width, index, expression),
            ]
            bits.append(self._allocator.create(gate_type, inputs, index, z, prefix, value_type=formatted_value_type))
        return Signal(tuple(bits), value_type=resolved_type)

    def _constant_signal(self, value: int, width: int, z: int, value_type: ResolvedType) -> Signal:
        """Encode an integer constant as zero-input OR and NOT gates per bit."""
        if width <= 0:
            self.error('ValueError', 'Signal width must be positive')
        if value >= 1 << width:
            self.error('ValueError', f"Value {value} does not fit in {width} bits")
        formatted_value_type = self._format_type(value_type)
        bits = [
            self._allocator.create(
                'NOT' if value & (1 << index) else 'OR',
                [],
                index,
                z,
                value_type=formatted_value_type,
            )
            for index in range(width)
        ]
        return Signal(tuple(bits), value_type=value_type)

    def _coerce_width(self, signal: Signal, width: int | None, node: AstNode) -> Signal:
        """Require a signal to match an expected width when one is supplied."""
        if width is None or len(signal.bits) == width:
            return signal
        self.error(
            'TypeMismatchError',
            f"Expected a {width}-bit value, received {len(signal.bits)} bits",
            node,
        )

    def _expand_for_width(
        self,
        signal: Signal,
        width: int,
        index: int,
        node: AstNode,
    ) -> list[int]:
        """Select a matching vector bit or broadcast one scalar input bit."""
        if len(signal.bits) == width:
            return [signal.bits[index]]
        if len(signal.bits) == 1:
            return [signal.bits[0]]
        self.error(
            'TypeMismatchError',
            f"Cannot connect {len(signal.bits)} bits to a {width}-bit value",
            node,
        )

    @staticmethod
    def _signal_width(signals: list[Signal], default: int) -> int:
        """Return the widest signal width or a fallback for empty input lists."""
        return max((len(signal.bits) for signal in signals), default=default)

    def _evaluate_integer(self, expression: AstNode, indices: dict[str, int]) -> int:
        """Evaluate compile-time integer expressions used for indexes and lengths."""
        expression_type = expression.get('type')
        if expression_type == 'int' and isinstance(expression.get('value'), int):
            return expression['value']
        if expression_type == 'ident':
            name = expression.get('name')
            if isinstance(name, str) and name in indices:
                return indices[name]
        if expression_type == 'unary':
            operator = expression.get('op')
            value = expression.get('value')
            if isinstance(operator, str) and isinstance(value, dict):
                operand = self._evaluate_integer(value, indices)
                if operator == '+':
                    return operand
                if operator == '-':
                    return -operand
                if operator == '~':
                    return ~operand
        if expression_type == 'binary':
            operator = expression.get('op')
            left = expression.get('left')
            right = expression.get('right')
            if isinstance(operator, str) and isinstance(left, dict) and isinstance(right, dict):
                first = self._evaluate_integer(left, indices)
                second = self._evaluate_integer(right, indices)
                return self._apply_integer_operator(operator, first, second, expression)
        self.error('InvalidExpressionError', 'Expected a compile-time integer expression', expression)

    def _apply_integer_operator(
        self,
        operator: str,
        left: int,
        right: int,
        node: AstNode,
    ) -> int:
        """Apply one supported compile-time integer operator."""
        if operator == '+':
            return left + right
        if operator == '-':
            return left - right
        if operator == '*':
            return left * right
        if operator == '/':
            if right == 0:
                self.error('ValueError', 'Division by zero', node)
            return left // right
        if operator == '%':
            if right == 0:
                self.error('ValueError', 'Modulo by zero', node)
            return left % right
        if operator == '<<':
            return left << right
        if operator == '>>':
            return left >> right
        if operator == '&':
            return left & right
        if operator == '|':
            return left | right
        if operator == '^':
            return left ^ right
        self.error('InvalidExpressionError', f"Unsupported integer operator: {operator}", node)

    @staticmethod
    def _definition_name(definition: AstNode) -> str:
        """Return a validated declaration name."""
        name = definition.get('name')
        if not isinstance(name, str) or not name:
            raise ValueError('Definition is missing a name')
        return name

    @staticmethod
    def _is_integer_type_name(name: str) -> bool:
        """Return whether a type name denotes a signed or unsigned integer."""
        return len(name) > 1 and name[0] in {'i', 'u'} and name[1:].isdigit()

    def _is_integer_type(self, value_type: ResolvedType) -> bool:
        """Return whether a resolved type is an integer type."""
        return value_type.name == 'int' or self._is_integer_type_name(value_type.name)

    @staticmethod
    def _is_assignable(target: ResolvedType, source: ResolvedType) -> bool:
        """Return whether a source value can be assigned to a target type."""
        if target.name != source.name or target.arguments != source.arguments:
            return False
        return target.length is None or source.length is None or target.length == source.length

    def _common_integer_type(self, left: ResolvedType, right: ResolvedType) -> ResolvedType:
        """Return the shared integer type or the generic integer fallback."""
        if left == right:
            return left
        if left.name == 'int':
            return right
        if right.name == 'int':
            return left
        return ResolvedType('int')

    @staticmethod
    def _format_type(value_type: ResolvedType) -> str:
        """Format a resolved type for compiler diagnostics."""
        suffix = ''
        if value_type.arguments:
            suffix = '<' + ', '.join(argument.name for argument in value_type.arguments) + '>'
        if value_type.length is not None:
            suffix += f'[{value_type.length}]'
        return value_type.name + suffix

