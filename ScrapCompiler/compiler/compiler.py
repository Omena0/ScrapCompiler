from __future__ import annotations

from typing import Any, NoReturn
from .types import *
from .spatial_allocator import SpatialAllocator

class ScrapCompiler:
    """Resolve Scrap types and lower module instances to positioned gate IR."""

    def __init__(self, ast: AstNode, debug=False) -> None:
        """Initialize the compiler with a parsed AST."""
        self.ast = ast
        self.modules: dict[str, AstNode] = {}
        self.variables: SymbolTable = {}
        self.signals: SignalTable = {}
        self.module_types: dict[str, ResolvedType] = {}
        self.debug = debug

        self._module_asts: dict[str, AstNode] = {}
        self._allocator:SpatialAllocator = SpatialAllocator()
        self._literal_widths: dict[str, int] = {}

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
        expected: object = MISSING,
        node: AstNode | None = None,
    ) -> T:
        """Return a validated value or report a compiler error."""
        valid = bool(value) if expected is MISSING else value == expected
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
        if name in BUILTIN_TYPES or self._is_integer_type_name(name):
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
        if expression_type == 'cast':
            return self._resolve_cast(expression, symbols)
        if expression_type == 'int':
            return ResolvedType('dynamic')
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
        if expression_type == 'cast':
            return self._resolve_cast(expression, symbols)
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

        self._allocator = SpatialAllocator(compact=not self.debug)

        self._next_z = 0
        self.signals = self._lower_statements(
            self.ast.get('gates'),
            {},
            {},
            0,
            {},
            False,
            False,
            True,
        )
        return self._allocator.build()

    @staticmethod
    def gates_to_ir(gates: list[Gate]) -> str:
        """Render positioned gates using explicit IDs and inline type/variable comments."""
        in_gates = sorted([gate for gate in gates if gate.prefix == 'IN'], key=lambda g: (g.x, g.y, g.z))
        internal_gates = sorted([gate for gate in gates if gate.prefix == ''], key=lambda g: (g.x, g.y, g.z))
        out_gates = sorted([gate for gate in gates if gate.prefix == 'OUT'], key=lambda g: (g.x, g.y, g.z))

        ordered = ["\n# Input", *in_gates, "\n# Compute", *internal_gates, "\n# Output", *out_gates]

        line_ids = {gate if isinstance(gate,str) else gate.key: line for line, gate in enumerate(ordered, start=1)}

        variable_all_ids: dict[str, list[int]] = {}
        variable_in_ids: dict[str, list[int]] = {}
        for gate in ordered:
            if isinstance(gate, str):
                continue

            if gate.variable and gate.prefix in ('IN', 'OUT'):
                variable_all_ids.setdefault(gate.variable, []).append(gate.key)
            if gate.variable and gate.prefix == 'IN':
                variable_in_ids.setdefault(gate.variable, []).append(gate.key)

        unnamed_in_ids: list[int] = []
        for gate in ordered:
            if isinstance(gate, str):
                continue

            if gate.prefix == 'IN' and not gate.variable:
                unnamed_in_ids.append(gate.key)

        lines: list[str] = []
        seen_variables: set[str] = set()
        emitted_variable_types: set[str] = set()
        emitted_unnamed_type = False

        for gate in ordered:
            if isinstance(gate, str):
                lines.append(gate)
                continue

            line_id = gate.key

            if gate.prefix == 'IN' and gate.variable and gate.variable not in emitted_variable_types:
                in_ids = variable_in_ids.get(gate.variable, [])
                type_name = gate.value_type
                lines.append(f"# {ScrapCompiler._format_id_ranges(in_ids)}: {type_name}")
                emitted_variable_types.add(gate.variable)

            if gate.prefix == 'IN' and not gate.variable and not emitted_unnamed_type and unnamed_in_ids:
                type_name = gate.value_type
                lines.append(f"# {ScrapCompiler._format_id_ranges(unnamed_in_ids)}: {type_name}")
                emitted_unnamed_type = True

            if gate.variable and gate.variable not in seen_variables:
                ids = variable_all_ids.get(gate.variable, [])
                if ids:
                    lines.append(f"# {gate.variable}: {ScrapCompiler._format_id_ranges(ids)}")
                    seen_variables.add(gate.variable)

            inputs = [str(source) for source in gate.inputs]

            parts = ([gate.prefix] if gate.prefix else []) + [
                str(gate.x),
                str(gate.y),
                str(gate.z),
                gate.type,
                *inputs,
            ]
            if gate.type == 'SWITCH' and gate.default_state:
                parts.append(str(gate.default_state))
            lines.append(f"{line_id}: {' '.join(parts)}")

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
        if value.get('type') == 'int' and isinstance(value.get('value'), int):
            self._literal_widths[name] = max(value['value'].bit_length(), 1)

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

        if resolved is None and name in self.module_types:
            return self.module_types[name]

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

        if value.get('type') == 'ident':
            ident_name = value.get('name')
            if isinstance(ident_name, str) and ident_name in symbols:
                resolved = symbols[ident_name]
                if isinstance(resolved, ResolvedType) and resolved.name in self._module_asts:
                    module = self._module_asts[resolved.name]
                    fields = module.get('fields')
                    if isinstance(fields, dict):
                        output_defs = fields.get('outputs')
                        if isinstance(output_defs, list):
                            for definition in output_defs:
                                if isinstance(definition, dict) and self._definition_name(definition) == name:
                                    length = definition.get('len')
                                    if length is None:
                                        return ResolvedType('dynamic')
                                    if length.get('type') == 'ident':
                                        return ResolvedType('dynamic', length.get('name'))
                                    return ResolvedType('dynamic', self._evaluate_integer(length, {}))

        self.error('TypeMismatchError', 'Field selection is only supported on module call results', expression)

    def _resolve_call(self, expression: AstNode, symbols: SymbolTable) -> ResolvedType:
        """Resolve a built-in gate, dynamic helper, or module call."""
        name = expression.get('name')
        arguments = expression.get('args')
        if not isinstance(name, str) or not name:
            self.error('InvalidExpressionError', 'Call expression is missing a name', expression)
        if not isinstance(arguments, list):
            self.error('InvalidExpressionError', 'Call expression is missing arguments', expression)

        if name in BUILTIN_MODULES:
            return self._resolve_builtin_module_type(expression)

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

        if name in BUILTIN_GATES:
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

    def _resolve_builtin_module_type(self, expression: AstNode) -> ResolvedType:
        """Return the output type for a built-in module without resolving width args."""
        name = expression.get('name')
        arguments = expression.get('args')
        if name == 'IntInput' or name == 'IntDisplay':
            if isinstance(arguments, list) and len(arguments) > 0:
                width_arg = arguments[0]
                if isinstance(width_arg, dict) and width_arg.get('type') == 'int':
                    value = width_arg.get('value')
                    if isinstance(value, int):
                        return ResolvedType(f'u{value}')
                if isinstance(width_arg, dict) and width_arg.get('type') == 'ident':
                    ident_name = width_arg.get('name')
                    if isinstance(ident_name, str) and ident_name.startswith('u') and ident_name[1:].isdigit():
                        return ResolvedType(ident_name)
            return ResolvedType('bit')
        if name == 'Lamp' or name == 'Switch' or name == 'Button':
            return ResolvedType('bit')
        return ResolvedType('bit')

    def _resolve_cast(self, expression: AstNode, symbols: SymbolTable) -> ResolvedType:
        """Resolve a type cast expression."""
        cast_type = expression.get('cast_type')
        value = expression.get('value')
        if not isinstance(cast_type, str) or not isinstance(value, dict):
            self.error('InvalidExpressionError', 'Invalid cast expression', expression)
        resolved = self.resolve_type(cast_type, node=expression)
        width = self._get_integer_width(cast_type)
        if width is not None:
            return ResolvedType(resolved.name, width, resolved.arguments)
        return resolved

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
        top_level: bool = False,
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
                    top_level,
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
        top_level: bool = False,
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
        else:
            signals[name] = self._lower_expression(value, signals, indices, z, None)

        for gate_id in signals[name].bits:
            self._allocator.set_variable(gate_id, name)

        if top_level and name == 'out':
            for gate_id in signals[name].bits:
                self._allocator._gates[gate_id].prefix = 'OUT'

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
            return self._constant_signal(int(value), width or 1, ResolvedType('bool'))
        if expression_type == 'int':
            value = expression.get('value')
            if not isinstance(value, int):
                self.error('InvalidExpressionError', 'Invalid integer expression', expression)
            actual_width = width or max(value.bit_length(), 1)
            return self._constant_signal(value, actual_width, ResolvedType('dynamic'))
        if expression_type == 'ident':
            name = expression.get('name')
            if not isinstance(name, str) or name not in signals:
                self.error('UnknownIdentifierError', f"Unknown identifier: {name}", expression)
            return self._coerce_width(signals[name], width, expression)
        if expression_type == 'index':
            return self._lower_index(expression, signals, indices, z)
        if expression_type == 'field':
            return self._lower_field(expression, signals, indices, z, width)
        if expression_type == 'cast':
            return self._lower_cast(expression, signals, indices, z, width)
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
        """Append wire sources to the target, supporting concatenation and width extension."""
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

        target_width = len(target.bits)

        if target_width == 1:
            for gate in target.bits:
                inputs: list[int] = []
                for source in source_signals:
                    inputs.extend(self._expand_for_width(source, 1, 0, statement))
                self._allocator.append_inputs(gate, inputs)
            return

        concatenated_bits: list[int] = []
        for source in reversed(source_signals):
            if len(source.bits) == 1:
                concatenated_bits.append(source.bits[0])
            else:
                concatenated_bits.extend(source.bits)

        source_width = len(concatenated_bits)

        if source_width > target_width:
            self.error(
                'TypeMismatchError',
                f"Cannot connect {source_width} bits to a {target_width}-bit value",
                statement,
            )

        for target_index, gate in enumerate(target.bits):
            if source_width == 1:
                self._allocator.append_inputs(gate, [concatenated_bits[0]])
            elif target_index < source_width:
                self._allocator.append_inputs(gate, [concatenated_bits[target_index]])

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
            start_key = self._allocator._next_key
            updated = self._lower_statements(
                gates,
                loop_signals,
                loop_indices,
                z,
                output_ports,
                True,
                index == len(dynamic_signal.bits) - 1,
                False,
            )
            for signal in updated.values():
                for bit in signal.bits:
                    if bit in self._allocator._gates and bit >= start_key:
                        self._allocator._gates[bit].y = index
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

        if name in IR_GATES:
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
                    self._allocator.inherit(gate, IR_GATES[name], value_type=formatted_value_type)
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
                gate_bits.append(self._allocator.create(IR_GATES[name], inputs, index, prefix, value_type=formatted_value_type))
            return Signal(tuple(gate_bits), value_type=value_type)

        if name in BUILTIN_MODULES:
            return self._instantiate_module(value, signals, indices, z)

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

        if value.get('type') == 'ident':
            ident_name = value.get('name')
            if isinstance(ident_name, str) and ident_name in signals:
                signal = signals[ident_name]
                if signal.module_outputs is not None and name in signal.module_outputs:
                    return signal.module_outputs[name]

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
        if name in IR_GATES:
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
            bits.append(self._allocator.create(IR_GATES[name], inputs, index, prefix, value_type=formatted_value_type))
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

        if name == 'IntInput':
            return self._instantiate_int_input(expression, parent_signals, parent_indices, parent_z)
        if name == 'IntDisplay':
            return self._instantiate_int_display(expression, parent_signals, parent_indices, parent_z)
        if name == 'Lamp':
            return self._instantiate_lamp(expression, parent_signals, parent_indices, parent_z)
        if name == 'Switch':
            return self._instantiate_switch(expression, parent_signals, parent_indices, parent_z)
        if name == 'Button':
            return self._instantiate_button(expression, parent_signals, parent_indices, parent_z)

        module = self._module_asts[name]
        fields = module.get('fields')
        if not isinstance(fields, dict):
            self.error('InvalidModule', f"Invalid module {name}", module)
        input_defs = fields.get('inputs')
        output_defs = fields.get('outputs')
        gates = module.get('gates')
        if not isinstance(input_defs, list) or not isinstance(output_defs, list) or not isinstance(gates, list):
            self.error('InvalidModule', f"Invalid module {name} fields", module)

        positional, named = self._bind_call_arguments(expression, input_defs)
        generic_width = self._generic_width(expression, input_defs, output_defs, parent_signals, positional, named)
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
                source = self._constant_signal(0, field_width, input_type)
                mark_input = False
            else:
                source = self._lower_expression(
                    argument,
                    parent_signals,
                    parent_indices,
                    0,
                    field_width,
                )
                mark_input = not buffered
            signals[field_name] = self._input_ports(source, buffered, mark_input, input_type, field_name)

        for definition in output_defs:
            if not isinstance(definition, dict):
                self.error('InvalidDefinition', 'Output definition must be an object', module)
            field_name = self._definition_name(definition)
            output_type = self._resolve_definition_type(definition, signals, parent_indices, generic_width)
            field_width = self._field_width(definition, signals, parent_indices, generic_width)
            port = self._output_ports(field_width, output_type)
            signals[field_name] = port
            output_ports[field_name] = port

        lowered = self._lower_statements(
            gates,
            signals,
            {},
            0,
            output_ports,
            False,
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
            result = output_ports[selected_output]
        else:
            result = primary

        return Signal(
            bits=result.bits,
            value_type=result.value_type,
            is_input=result.is_input,
            buffered=result.buffered,
            module_outputs=dict(output_ports),
        )

    def _input_ports(self, source: Signal, buffered: bool, mark_input: bool, value_type: ResolvedType | None = None, variable: str = '') -> Signal:
        """Bind a module input to the instantiated module scope.

        Buffered inputs get an IN-prefixed OR gate buffer. Unbuffered inputs
        are carried through and tagged for the first consuming gate.
        """
        value_type = value_type or source.value_type
        if buffered:
            formatted_value_type = self._format_type(value_type)
            bits = [
                self._allocator.create('OR', [gate], index, 'IN', value_type=formatted_value_type)
                for index, gate in enumerate(source.bits)
            ]
            if variable:
                for bit in bits:
                    self._allocator.set_variable(bit, variable)
            return Signal(tuple(bits), value_type=value_type)

        if variable:
            for bit in source.bits:
                if not self._allocator._gates[bit].variable:
                    self._allocator.set_variable(bit, variable)
        if mark_input:
            return Signal(source.bits, value_type, is_input=True)
        return Signal(source.bits, value_type)

    def _output_ports(self, width: int, value_type: ResolvedType) -> Signal:
        """Create default output OR gates that can later inherit another gate type."""
        formatted_value_type = self._format_type(value_type)
        bits = [
            self._allocator.create('OR', [], index, '', value_type=formatted_value_type, is_output_port=True)
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
        parent_signals: SignalTable | None = None,
        positional: list[AstNode] | None = None,
        named: dict[str, AstNode] | None = None,
    ) -> int:
        """Resolve a module call's ``<uN>`` dynamic signal width."""
        needs_width = any(
            isinstance(definition, dict) and definition.get('type') == 'dynamic'
            for definition in [*input_defs, *output_defs]
        )
        cast_type = expression.get('cast_type')
        if cast_type is None and not needs_width:
            return 1
        if isinstance(cast_type, str):
            if cast_type == 'bit':
                return 1
            if not self._is_integer_type_name(cast_type) or cast_type[0] != 'u':
                self.error('TypeArgumentError', 'Dynamic modules require an unsigned integer type', expression)
            width = int(cast_type[1:])
            if width <= 0:
                self.error('TypeArgumentError', 'Dynamic module width must be positive', expression)
            return width
        if cast_type is not None:
            self.error('TypeArgumentError', 'Dynamic modules require a <uN> type argument', expression)

        if positional is None or named is None:
            arguments = expression.get('args')
            if not isinstance(arguments, list):
                self.error('TypeArgumentError', 'Dynamic modules require a <uN> type argument', expression)
            positional = []
            named = {}
            for argument in arguments:
                if isinstance(argument, dict):
                    if argument.get('type') == 'named_arg':
                        arg_name = argument.get('name')
                        arg_value = argument.get('value')
                        if isinstance(arg_name, str) and isinstance(arg_value, dict):
                            named[arg_name] = arg_value
                    else:
                        positional.append(argument)

        for position, definition in enumerate(input_defs):
            if not isinstance(definition, dict):
                continue
            field_name = self._definition_name(definition)
            type_name = definition.get('type')
            length = definition.get('len')
            if type_name == 'dynamic' and length is None:
                argument = named.get(field_name)
                if argument is None and position < len(positional):
                    argument = positional[position]
                if argument is not None:
                    inferred = self._infer_expression_width(argument, parent_signals)
                    if inferred is not None:
                        return inferred

        self.error('TypeArgumentError', 'Dynamic modules require a <uN> type argument', expression)

    def _infer_expression_width(self, expression: AstNode, signals: SignalTable | None) -> int | None:
        """Attempt to infer the bit width of an expression from known signals."""
        expression_type = expression.get('type')
        if expression_type == 'int':
            value = expression.get('value')
            if isinstance(value, int):
                return max(value.bit_length(), 1)
            return None
        if expression_type == 'ident':
            name = expression.get('name')
            if isinstance(name, str):
                if signals is not None and name in signals:
                    return len(signals[name].bits)
                if name in self._literal_widths:
                    return self._literal_widths[name]
            return None
        return None

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
            if candidate.bits and all(self._allocator.is_output_port(gate) for gate in candidate.bits):
                return candidate
        if target is not None and all(self._allocator.is_output_port(gate) for gate in target.bits):
            return target
        return None

    def _lower_cast(
        self,
        expression: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        z: int,
        width: int | None,
    ) -> Signal:
        """Lower a type cast by re-resolving the target width and lowering the value."""
        cast_type = expression.get('cast_type')
        value = expression.get('value')
        if not isinstance(cast_type, str) or not isinstance(value, dict):
            self.error('InvalidExpressionError', 'Invalid cast expression', expression)
        resolved_type = self.resolve_type(cast_type, node=expression)
        explicit_width = self._get_integer_width(cast_type)
        target_width = explicit_width if explicit_width is not None else (resolved_type.length if isinstance(resolved_type.length, int) else width)
        if target_width is None:
            self.error('InvalidExpressionError', 'Cast requires a concrete width', expression)
        return self._lower_expression(value, signals, indices, z, target_width)

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
            self._allocator.create('NOT', [gate], index, prefix, value_type=formatted_value_type)
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
        gate_type = BINARY_GATES.get(operator)
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
            bits.append(self._allocator.create(gate_type, inputs, index, prefix, value_type=formatted_value_type))
        return Signal(tuple(bits), value_type=resolved_type)

    def _constant_signal(self, value: int, width: int, value_type: ResolvedType) -> Signal:
        """Encode an integer constant as SWITCH gates per bit."""
        if width <= 0:
            self.error('ValueError', 'Signal width must be positive')
        if value >= 1 << width:
            self.error('ValueError', f"Value {value} does not fit in {width} bits")
        if value_type.name == 'dynamic':
            value_type = ResolvedType('dynamic', width)
        formatted_value_type = self._format_type(value_type)
        bits = [
            self._allocator.create(
                'SWITCH',
                [],
                index,
                'IN',
                value_type=formatted_value_type,
                default_state=(value >> index) & 1,
            )
            for index in range(width)
        ]
        return Signal(tuple(bits), value_type=value_type)

    def _coerce_width(self, signal: Signal, width: int | None, node: AstNode) -> Signal:
        """Require a signal to match an expected width when one is supplied."""
        if width is None or len(signal.bits) == width:
            return signal
        if len(signal.bits) < width and signal.value_type.name == 'dynamic':
            return self._pad_width(signal, width)
        self.error(
            'TypeMismatchError',
            f"Expected a {width}-bit value, received {len(signal.bits)} bits",
            node,
        )

    def _pad_width(self, signal: Signal, target_width: int) -> Signal:
        """Zero-pad a dynamic signal to a target width."""
        if len(signal.bits) >= target_width:
            return signal
        padding_count = target_width - len(signal.bits)
        padding = self._constant_signal(0, padding_count, ResolvedType('dynamic', target_width))
        all_bits = tuple([*signal.bits, *padding.bits])
        for bit in all_bits:
            if bit in self._allocator._gates:
                self._allocator._gates[bit].value_type = f'u{target_width}'
        if signal.bits and padding.bits:
            first_var = self._allocator._gates[signal.bits[0]].variable
            for bit in padding.bits:
                if bit in self._allocator._gates:
                    self._allocator._gates[bit].variable = first_var
        return Signal(all_bits, value_type=ResolvedType('dynamic', target_width))

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

    @staticmethod
    def _get_integer_width(name: str) -> int | None:
        """Return the bit width for integer type names like u8, i16, or None."""
        if len(name) > 1 and name[0] in {'i', 'u'} and name[1:].isdigit():
            return int(name[1:])
        if name in {'bit', 'bool'}:
            return 1
        return None

    def _is_integer_type(self, value_type: ResolvedType) -> bool:
        """Return whether a resolved type is an integer type."""
        return value_type.name in {'int', 'dynamic'} or self._is_integer_type_name(value_type.name)

    @staticmethod
    def _is_assignable(target: ResolvedType, source: ResolvedType) -> bool:
        """Return whether a source value can be assigned to a target type."""
        if source.name == 'dynamic' or target.name == 'dynamic':
            return True
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
        if value_type.name == 'dynamic' and isinstance(value_type.length, int):
            return f'u{value_type.length}'
        suffix = ''
        if value_type.arguments:
            suffix = '<' + ', '.join(argument.name for argument in value_type.arguments) + '>'
        if value_type.length is not None:
            suffix += f'[{value_type.length}]'
        return value_type.name + suffix

    def _resolve_builtin_width(self, expression: AstNode, parent_signals: SignalTable) -> int | None:
        """Resolve the width argument for built-in modules like IntInput. Returns None for dynamic."""
        arguments = expression.get('args')
        if not isinstance(arguments, list) or len(arguments) < 1:
            return None

        width_arg = arguments[0]
        if isinstance(width_arg, dict) and width_arg.get('type') == 'int':
            value = width_arg.get('value')
            if isinstance(value, int) and value > 0:
                return value

        if isinstance(width_arg, dict) and width_arg.get('type') == 'ident':
            name = width_arg.get('name')
            if isinstance(name, str):
                if name in parent_signals:
                    signal = parent_signals[name]
                    return len(signal.bits)
                if name.startswith('u') and name[1:].isdigit():
                    return int(name[1:])

        self.error('InvalidExpressionError', 'Built-in module width must be a positive integer, unsigned type, or signal', expression)

    def _instantiate_int_input(self, expression: AstNode, parent_signals: SignalTable, parent_indices: dict[str, int], parent_z: int) -> Signal:
        """Create a block of SWITCH gates representing an integer input."""
        width = self._resolve_builtin_width(expression, parent_signals)
        bits = []
        for index in range(width):
            gate_id = self._allocator.create('SWITCH', [], index, 'IN', value_type=f'u{width}')
            self._allocator.mark_input(gate_id)
            bits.append(gate_id)
        signal = Signal(tuple(bits), value_type=ResolvedType(f'u{width}'))
        return Signal(bits=signal.bits, value_type=signal.value_type, module_outputs={'bits': signal})

    def _instantiate_int_display(self, expression: AstNode, parent_signals: SignalTable, parent_indices: dict[str, int], parent_z: int) -> Signal:
        """Create a block of LAMP gates representing an integer display."""
        width = self._resolve_builtin_width(expression, parent_signals)
        input_signal = None
        arguments = expression.get('args')
        if isinstance(arguments, list) and len(arguments) > 1:
            input_signal = self._lower_expression(arguments[1], parent_signals, parent_indices, parent_z, width)

        bits = []
        for index in range(width):
            inputs = []
            if input_signal is not None:
                inputs.append(input_signal.bits[index] if index < len(input_signal.bits) else input_signal.bits[0])
            gate_id = self._allocator.create('LAMP', inputs, index, 'OUT', value_type=f'u{width}')
            bits.append(gate_id)
        signal = Signal(tuple(bits), value_type=ResolvedType(f'u{width}'))
        return Signal(bits=signal.bits, value_type=signal.value_type, module_outputs={})

    def _instantiate_lamp(self, expression: AstNode, parent_signals: SignalTable, parent_indices: dict[str, int], parent_z: int) -> Signal:
        """Create a single LAMP gate."""
        arguments = expression.get('args')
        input_signal = None
        if isinstance(arguments, list) and len(arguments) > 0:
            input_signal = self._lower_expression(arguments[0], parent_signals, parent_indices, parent_z, 1)
        bit = input_signal.bits[0] if input_signal else 0
        gate_id = self._allocator.create('LAMP', [bit], 0, 'OUT', value_type='bit')
        signal = Signal((gate_id,), value_type=ResolvedType('bit'))
        return Signal(bits=signal.bits, value_type=signal.value_type, module_outputs={})

    def _instantiate_switch(self, expression: AstNode, parent_signals: SignalTable, parent_indices: dict[str, int], parent_z: int) -> Signal:
        """Create a single SWITCH gate with a default state."""
        arguments = expression.get('args')
        default_state = 0
        if isinstance(arguments, list) and len(arguments) > 0:
            default_state = self._evaluate_integer(arguments[0], parent_indices)
            if default_state not in (0, 1):
                default_state = 1 if default_state else 0
        gate_id = self._allocator.create('SWITCH', [], 0, 'IN', value_type='bit', default_state=default_state)
        self._allocator.mark_input(gate_id)
        signal = Signal((gate_id,), value_type=ResolvedType('bit'))
        return Signal(bits=signal.bits, value_type=signal.value_type, module_outputs={'bit': signal})

    def _instantiate_button(self, expression: AstNode, parent_signals: SignalTable, parent_indices: dict[str, int], parent_z: int) -> Signal:
        """Create a single BUTTON gate."""
        gate_id = self._allocator.create('BUTTON', [], 0, 'IN', value_type='bit')
        self._allocator.mark_input(gate_id)
        signal = Signal((gate_id,), value_type=ResolvedType('bit'))
        return Signal(bits=signal.bits, value_type=signal.value_type, module_outputs={'bit': signal})

