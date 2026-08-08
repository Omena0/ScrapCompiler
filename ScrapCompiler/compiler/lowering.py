from __future__ import annotations

from .mixin_base import CompilerMixinBase
from .types import *


class LoweringMixin(CompilerMixinBase):
    """IR lowering helpers for the Scrap compiler."""

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
            self.error("InvalidGates", "Missing or invalid 'gates'", self.ast)

        lowered = dict(signals)
        if top_level:
            assignments: list[AstNode] = []
            arrows: list[AstNode] = []
            for statement in statements:
                if not isinstance(statement, dict):
                    self.error("InvalidGate", "Gate statement must be an object", self.ast)
                statement_type = statement.get("type")
                if statement_type == "arrow":
                    arrows.append(statement)
                else:
                    assignments.append(statement)

            for statement in assignments:
                self._lower_statement(
                    statement,
                    lowered,
                    indices,
                    z,
                    output_ports,
                    in_dynamic_loop,
                    final_iteration,
                    top_level,
                )
            for statement in arrows:
                self._lower_statement(
                    statement,
                    lowered,
                    indices,
                    z,
                    output_ports,
                    in_dynamic_loop,
                    final_iteration,
                    top_level,
                )
            return lowered

        for statement in statements:
            self._lower_statement(
                statement,
                lowered,
                indices,
                z,
                output_ports,
                in_dynamic_loop,
                final_iteration,
                top_level,
            )
        return lowered

    def _lower_statement(
        self,
        statement: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        z: int,
        output_ports: SignalTable,
        in_dynamic_loop: bool,
        final_iteration: bool,
        top_level: bool,
    ) -> None:
        """Lower one statement and mutate ``signals`` in place."""
        statement_type = statement.get("type")
        if statement_type == "gate":
            self._lower_assignment(
                statement,
                signals,
                indices,
                z,
                output_ports,
                in_dynamic_loop,
                final_iteration,
                top_level,
            )
        elif statement_type == "indexed_gate":
            self._lower_indexed_gate(
                statement,
                signals,
                indices,
                z,
                output_ports,
                in_dynamic_loop,
                final_iteration,
                top_level,
            )
        elif statement_type == "arrow":
            self._lower_arrow(statement, signals, indices, z)
        elif statement_type == "as":
            self._lower_dynamic(statement, signals, indices, z, output_ports)
        elif statement_type == "for_loop":
            self._lower_for_loop(statement, signals, indices, z, output_ports)
        elif statement_type == "function_call":
            self._lower_function_call(statement, signals, indices, z)
        else:
            self.error("InvalidGate", "Unknown gate statement type", statement)

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
        name = statement.get("name")
        value = statement.get("value")
        if not isinstance(name, str) or not isinstance(value, dict):
            self.error("InvalidGate", "Invalid gate assignment", statement)

        target = None
        if name in output_ports:
            target = (
                output_ports[name] if not in_dynamic_loop or final_iteration else None
            )
        elif name in signals:
            target = signals[name]

        if value.get("type") == "new":
            signals[name] = self._lower_new(
                value, signals, indices, z, target, statement
            )
        elif value.get("type") == "list":
            self._compile_time_values[name] = [
                self._ast_value_to_python(element) for element in value.get("value", [])
            ]
            dummy_id = self._allocator.create("LIST", [], 0, "", value_type="list")
            signals[name] = Signal((dummy_id,), value_type=ResolvedType("list"))
        else:
            signals[name] = self._lower_expression(value, signals, indices, z, None)

        for gate_id in signals[name].bits:
            self._allocator.set_variable(gate_id, name)

        if top_level and name == "out":
            for gate_id in signals[name].bits:
                self._allocator._gates[gate_id].prefix = "OUT"

    def _lower_indexed_gate(
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
        """Lower an indexed gate assignment like x[i]: expr."""
        name = statement.get("name")
        index_expr = statement.get("index")
        value = statement.get("value")
        if (
            not isinstance(name, str)
            or not isinstance(index_expr, dict)
            or not isinstance(value, dict)
        ):
            self.error("InvalidGate", "Invalid indexed gate assignment", statement)

        target = None
        if name in output_ports:
            target = (
                output_ports[name] if not in_dynamic_loop or final_iteration else None
            )
        elif name in signals:
            target = signals[name]

        position = self._evaluate_integer(index_expr, indices)
        lowered = self._lower_expression(value, signals, indices, z, None)
        if not 0 <= position < len(lowered.bits):
            self.error(
                "IndexError",
                f"Index {position} is outside a {len(lowered.bits)}-bit value",
                statement,
            )

        bit = lowered.bits[position]
        signal = Signal((bit,), value_type=lowered.value_type, is_input=lowered.is_input)
        signals[name] = signal

        for gate_id in signal.bits:
            self._allocator.set_variable(gate_id, name)

        if top_level and name == "out":
            for gate_id in signal.bits:
                self._allocator._gates[gate_id].prefix = "OUT"

    def _lower_expression(
        self,
        expression: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        z: int,
        width: int | None,
    ) -> Signal:
        """Lower an expression to a signal, optionally coercing its width."""
        expression_type = expression.get("type")
        if expression_type == "string":
            value = expression.get("value")
            if not isinstance(value, str):
                self.error(
                    "InvalidExpressionError", "Invalid string expression", expression
                )
            return self._constant_signal(0, width or 1, ResolvedType("string"))
        if expression_type == "object":
            value = expression.get("value")
            if not isinstance(value, dict):
                self.error(
                    "InvalidExpressionError", "Invalid object expression", expression
                )
            return self._constant_signal(0, width or 1, ResolvedType("object"))
        if expression_type == "list":
            return self._constant_signal(0, width or 1, ResolvedType("list"))
        if expression_type == "bool":
            value = expression.get("value")
            if not isinstance(value, bool):
                self.error(
                    "InvalidExpressionError", "Invalid boolean expression", expression
                )
            return self._constant_signal(int(value), width or 1, ResolvedType("bool"))
        if expression_type == "int":
            value = expression.get("value")
            if not isinstance(value, int):
                self.error(
                    "InvalidExpressionError", "Invalid integer expression", expression
                )
            actual_width = width or max(value.bit_length(), 1)
            return self._constant_signal(value, actual_width, ResolvedType("dynamic"))
        if expression_type == "ident":
            name = expression.get("name")
            if not isinstance(name, str):
                self.error(
                    "InvalidExpressionError", "Invalid identifier expression", expression
                )
            if name == "index" and name in indices:
                value = indices[name]
                return self._constant_signal(
                    value, max(value.bit_length(), 1), ResolvedType("int")
                )
            if name not in signals:
                self.error(
                    "UnknownIdentifierError", f"Unknown identifier: {name}", expression
                )
            return self._coerce_width(signals[name], width, expression)
        if expression_type == "index":
            return self._lower_index(expression, signals, indices, z)
        if expression_type == "field":
            return self._lower_field(expression, signals, indices, z, width)
        if expression_type == "cast":
            return self._lower_cast(expression, signals, indices, z, width)
        if expression_type == "call":
            return self._lower_call(expression, signals, indices, z, width)
        if expression_type == "new":
            return self._lower_new(expression, signals, indices, z, None, expression)
        if expression_type == "unary":
            return self._lower_unary(expression, signals, indices, z, width)
        if expression_type == "binary":
            return self._lower_binary(expression, signals, indices, z, width)
        self.error("InvalidExpressionError", "Unsupported IR expression", expression)

    def _lower_arrow(
        self,
        statement: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        z: int,
    ) -> None:
        """Append wire sources to the target, supporting concatenation and width extension."""
        target_expr = statement.get("to")
        sources = statement.get("from")
        if not isinstance(sources, list):
            self.error("InvalidGate", "Invalid wire statement", statement)

        if isinstance(target_expr, dict):
            target = self._lower_expression(target_expr, signals, indices, z, None)
        elif isinstance(target_expr, str):
            target = signals.get(target_expr)
            if target is None:
                self.error(
                    "UnknownIdentifierError",
                    f"Unknown wire target: {target_expr}",
                    statement,
                )
        else:
            self.error("InvalidGate", "Invalid wire target", statement)

        source_signals = [
            self._lower_expression(source, signals, indices, z, None)
            for source in sources
            if isinstance(source, dict)
        ]
        if len(source_signals) != len(sources):
            self.error("InvalidGate", "Wire source must be an expression", statement)

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
                "TypeMismatchError",
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
        """Unroll a bits loop once for every bit of its source signals."""
        name = statement.get("name")
        arguments = statement.get("args")
        variables = statement.get("vars")
        gates = statement.get("gates")
        if name != "bits" or not isinstance(arguments, list) or len(arguments) < 1:
            self.error("InvalidGate", "Invalid bits loop", statement)
        if not isinstance(variables, list) or not isinstance(gates, list):
            self.error("InvalidGate", "Invalid bits loop body", statement)

        lowered_args = []
        for arg in arguments:
            if not isinstance(arg, dict):
                self.error(
                    "InvalidGate", "Bits loop argument must be an expression", statement
                )
            lowered_args.append(self._lower_expression(arg, signals, indices, z, None))

        if not all(a.bits for a in lowered_args):
            self.error("InvalidGate", "Bits loop source cannot be empty", statement)

        length = len(lowered_args[0].bits)
        if not all(len(a.bits) == length for a in lowered_args):
            self.error(
                "InvalidGate", "Bits loop arguments must have the same width", statement
            )

        if not variables:
            variables = [
                arg.get("name")
                for arg in arguments
                if isinstance(arg, dict) and isinstance(arg.get("name"), str)
            ]

        for index in range(length):
            loop_indices = {**indices, "index": index}
            loop_signals = {**signals}
            for idx, var_name in enumerate(variables):
                if idx < len(lowered_args) and isinstance(var_name, str) and var_name:
                    arg_signal = lowered_args[idx]
                    bit = arg_signal.bits[index]
                    loop_signals[var_name] = Signal(
                        (bit,),
                        value_type=ResolvedType("bit"),
                    )

            start_key = self._allocator._next_key
            updated = self._lower_statements(
                gates,
                loop_signals,
                loop_indices,
                z,
                output_ports,
                True,
                index == length - 1,
                False,
            )
            for signal in updated.values():
                for bit in signal.bits:
                    if bit in self._allocator._gates and bit >= start_key:
                        self._allocator._gates[bit].y = index
            signals.update(updated)

    def _lower_for_loop(
        self,
        statement: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        z: int,
        output_ports: SignalTable,
    ) -> None:
        """Unroll a for loop for each iteration from 0 to count-1."""
        variable = statement.get("variable")
        count_expr = statement.get("count")
        body = statement.get("body")
        if (
            not isinstance(variable, str)
            or not variable
            or not isinstance(count_expr, dict)
            or not isinstance(body, list)
        ):
            self.error("InvalidGate", "Invalid for loop", statement)

        count = self._evaluate_integer(count_expr, indices)
        if count < 0:
            self.error("ValueError", "For loop count cannot be negative", statement)

        loop_signals = dict(signals)
        for iteration in range(count):
            loop_signals[variable] = Signal(
                (iteration,),
                value_type=ResolvedType("int"),
            )
            updated = self._lower_statements(
                body,
                loop_signals,
                indices,
                z,
                output_ports,
                False,
                False,
                False,
            )
            loop_signals.update(updated)

        signals.update(loop_signals)

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
        value = expression.get("value")
        if not isinstance(value, dict):
            self.error(
                "InvalidExpressionError",
                "new requires a gate or module call",
                expression,
            )

        if value.get("type") == "field":
            return self._lower_expression(value, signals, indices, z, width=None)

        if value.get("type") != "call":
            self.error(
                "InvalidExpressionError",
                "new requires a gate or module call",
                expression,
            )

        name = value.get("name")
        arguments = value.get("args")
        if not isinstance(name, str) or not isinstance(arguments, list):
            self.error(
                "InvalidExpressionError", "new requires a valid call expression", value
            )

        if name in IR_GATES:
            if name == "Timer":
                if len(arguments) != 2:
                    self.error(
                        "InvalidExpressionError",
                        "timer requires exactly two arguments: delay and signal",
                        value,
                    )
                delay_arg = arguments[0]
                signal_arg = arguments[1]
                if not isinstance(delay_arg, dict) or not isinstance(signal_arg, dict):
                    self.error(
                        "InvalidExpressionError",
                        "timer arguments must be expressions",
                        value,
                    )
                delay = self._evaluate_integer(delay_arg, indices)
                source = self._lower_expression(signal_arg, signals, indices, z, None)
                if not source.bits:
                    self.error("InvalidExpression", "timer signal cannot be empty", signal_arg)
                resolved_type = self.resolve_expression(value, signals)  # type: ignore[arg-type]
                formatted_value_type = self._format_type(resolved_type)
                prefix = "IN" if source.is_input else ""
                bits = [
                    self._allocator.create(
                        "TIMER",
                        [bit],
                        index,
                        prefix,
                        value_type=formatted_value_type,
                        delay=delay,
                    )
                    for index, bit in enumerate(source.bits)
                ]
                return Signal(tuple(bits), value_type=resolved_type)

            argument_signals = [
                self._lower_expression(argument, signals, indices, z, None)
                for argument in arguments
                if isinstance(argument, dict)
            ]
            if len(argument_signals) != len(arguments):
                self.error(
                    "InvalidExpressionError",
                    "Gate argument must be an expression",
                    value,
                )

            value_type = self.resolve_expression(value, signals)  # type: ignore[arg-type]
            inherited = self._find_inherited_output(target, argument_signals)
            if inherited is not None:
                inherited_keys = set(inherited.bits)
                argument_signals = [
                    signal
                    for signal in argument_signals
                    if set(signal.bits) != inherited_keys
                ]
                formatted_value_type = self._format_type(value_type)
                for gate in inherited.bits:
                    self._allocator.inherit(
                        gate, IR_GATES[name], value_type=formatted_value_type
                    )
                for target_index, gate in enumerate(inherited.bits):
                    inherited_inputs: list[int] = []
                    for source in argument_signals:
                        inherited_inputs.extend(
                            self._expand_for_width(
                                source, len(inherited.bits), target_index, node
                            )
                        )
                    self._allocator.append_inputs(gate, inherited_inputs)
                return inherited

            width = (
                len(target.bits)
                if target is not None
                else self._signal_width(argument_signals, 1)
            )
            gate_bits: list[int] = []
            formatted_value_type = self._format_type(value_type)
            prefix = "IN" if any(source.is_input for source in argument_signals) else ""
            for index in range(width):
                gate_inputs: list[int] = []
                for source in argument_signals:
                    gate_inputs.extend(
                        self._expand_for_width(source, width, index, node)
                    )
                gate_bits.append(
                    self._allocator.create(
                        IR_GATES[name],
                        gate_inputs,
                        index,
                        prefix,
                        value_type=formatted_value_type,
                    )
                )
            return Signal(tuple(gate_bits), value_type=value_type)

        if name in BUILTIN_MODULES:
            return self._instantiate_module(value, signals, indices, z)

        if name in self._module_asts:
            return self._instantiate_module(value, signals, indices, z)

        self.error("UnknownTypeError", f"Unknown callable type: {name}", value)

    def _lower_index(
        self,
        expression: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        z: int,
    ) -> Signal:
        """Lower an indexed expression to exactly one bit signal."""
        value = expression.get("value")
        index = expression.get("index")
        if not isinstance(value, dict) or not isinstance(index, dict):
            self.error("InvalidExpressionError", "Invalid index expression", expression)

        if value.get("type") == "ident":
            ident_name = value.get("name")
            if isinstance(ident_name, str) and ident_name in self._compile_time_values:
                position = self._evaluate_integer(index, indices)
                list_elements = self._compile_time_values[ident_name]
                if not 0 <= position < len(list_elements):
                    self.error(
                        "IndexError",
                        f"Index {position} is outside a {len(list_elements)}-element list",
                        expression,
                    )
                element = list_elements[position]
                if isinstance(element, int):
                    return self._constant_signal(
                        element, max(element.bit_length(), 1), ResolvedType("dynamic")
                    )
                if isinstance(element, dict) and isinstance(element.get("bits"), tuple):
                    return Signal(
                        element["bits"],
                        value_type=element.get("value_type", ResolvedType("bit")),
                        is_input=element.get("is_input", False),
                    )
                self.error(
                    "InvalidExpressionError",
                    f"Cannot index list element of type {type(element).__name__}",
                    expression,
                )

        signal = self._lower_expression(value, signals, indices, z, None)
        position = self._evaluate_integer(index, indices)
        if not 0 <= position < len(signal.bits):
            self.error(
                "IndexError",
                f"Index {position} is outside a {len(signal.bits)}-bit value",
                expression,
            )
        return Signal(
            (signal.bits[position],),
            value_type=ResolvedType("bit"),
            is_input=signal.is_input,
        )

    def _lower_field(
        self,
        expression: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        z: int,
        width: int | None,
    ) -> Signal:
        """Lower a module field selection to the selected output signal."""
        value = expression.get("value")
        name = expression.get("name")
        if not isinstance(value, dict):
            self.error(
                "InvalidExpressionError",
                "Invalid field selection expression",
                expression,
            )
        if not isinstance(name, str) or not name:
            self.error(
                "InvalidExpressionError",
                "Field selection is missing a name",
                expression,
            )
        if (
            value.get("type") == "call"
            and isinstance(value.get("name"), str)
            and value.get("name") in self._module_asts
        ):
            return self._instantiate_module(
                value, signals, indices, z, selected_output=name
            )

        if value.get("type") == "ident":
            ident_name = value.get("name")
            if isinstance(ident_name, str) and ident_name in signals:
                signal = signals[ident_name]
                if signal.module_outputs is not None and name in signal.module_outputs:
                    return signal.module_outputs[name]

        self.error(
            "TypeMismatchError",
            "Field selection is only supported on module call results",
            expression,
        )

    def _lower_call(
        self,
        expression: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        z: int,
        width: int | None,
    ) -> Signal:
        """Lower a direct built-in call or instantiate a module call."""
        name = expression.get("name")
        if not isinstance(name, str):
            self.error(
                "InvalidExpressionError",
                "Call expression is missing a name",
                expression,
            )
        if name in IR_GATES:
            return self._lower_builtin_call(expression, signals, indices, z, width)
        if name in self._module_asts:
            return self._instantiate_module(expression, signals, indices, z)
        self.error("UnknownTypeError", f"Unknown callable type: {name}", expression)

    def _lower_builtin_call(
        self,
        expression: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        z: int,
        width: int | None,
    ) -> Signal:
        """Lower a built-in logic call with its arguments as gate inputs."""
        name = expression.get("name")
        arguments = expression.get("args")
        if not isinstance(name, str) or not isinstance(arguments, list):
            self.error(
                "InvalidExpressionError", "Invalid built-in gate call", expression
            )

        if name == "Timer":
            if len(arguments) != 2:
                self.error(
                    "InvalidExpressionError",
                    "timer requires exactly two arguments: delay and signal",
                    expression,
                )
            delay_arg = arguments[0]
            signal_arg = arguments[1]
            if not isinstance(delay_arg, dict) or not isinstance(signal_arg, dict):
                self.error(
                    "InvalidExpressionError",
                    "timer arguments must be expressions",
                    expression,
                )
            delay = self._evaluate_integer(delay_arg, indices)
            source = self._lower_expression(signal_arg, signals, indices, z, None)
            if not source.bits:
                self.error("InvalidExpression", "timer signal cannot be empty", signal_arg)
            resolved_type = self.resolve_expression(expression, signals)  # type: ignore[arg-type]
            formatted_value_type = self._format_type(resolved_type)
            prefix = "IN" if source.is_input else ""
            bits = [
                self._allocator.create(
                    "TIMER",
                    [bit],
                    index,
                    prefix,
                    value_type=formatted_value_type,
                    delay=delay,
                )
                for index, bit in enumerate(source.bits)
            ]
            return Signal(tuple(bits), value_type=resolved_type)

        sources = [
            self._lower_expression(argument, signals, indices, z, width)
            for argument in arguments
            if isinstance(argument, dict)
        ]
        if len(sources) != len(arguments):
            self.error(
                "InvalidExpressionError",
                "Gate argument must be an expression",
                expression,
            )
        signal_width = width or self._signal_width(sources, 1)
        resolved_type = self.resolve_expression(expression, signals)  # type: ignore[arg-type]
        formatted_value_type = self._format_type(resolved_type)
        prefix = "IN" if any(source.is_input for source in sources) else ""
        bits: list[int] = []
        for index in range(signal_width):
            inputs: list[int] = []
            for source in sources:
                inputs.extend(
                    self._expand_for_width(source, signal_width, index, expression)
                )

            bits.append(
                self._allocator.create(
                    IR_GATES[name],
                    inputs,
                    index,
                    prefix,
                    value_type=formatted_value_type,
                )
            )

        return Signal(tuple(bits), value_type=resolved_type)

    def _lower_cast(
        self,
        expression: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        z: int,
        width: int | None,
    ) -> Signal:
        """Lower a type cast by re-resolving the target width and lowering the value."""
        cast_type = expression.get("cast_type")
        value = expression.get("value")
        if not isinstance(cast_type, str) or not isinstance(value, dict):
            self.error("InvalidExpressionError", "Invalid cast expression", expression)
        resolved_type = self.resolve_type(cast_type, node=expression)
        explicit_width = self._get_integer_width(cast_type)
        target_width = (
            explicit_width
            if explicit_width is not None
            else (
                resolved_type.length if isinstance(resolved_type.length, int) else width
            )
        )
        if target_width is None:
            self.error(
                "InvalidExpressionError", "Cast requires a concrete width", expression
            )
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
        operator = expression.get("op")
        value = expression.get("value")
        if not isinstance(operator, str) or not isinstance(value, dict):
            self.error("InvalidExpressionError", "Invalid unary expression", expression)
        if operator not in {"!", "~"}:
            self.error(
                "UnsupportedExpressionError",
                f"Unsupported IR unary operator: {operator}",
                expression,
            )
        source = self._lower_expression(value, signals, indices, z, width)
        resolved_type = self.resolve_expression(expression, signals)  # type: ignore[arg-type]
        formatted_value_type = self._format_type(resolved_type)
        prefix = "IN" if source.is_input else ""
        return Signal(
            tuple(
                self._allocator.create(
                    "NOT", [gate], index, prefix, value_type=formatted_value_type
                )
                for index, gate in enumerate(source.bits)
            ),
            value_type=resolved_type,
        )

    def _lower_binary(
        self,
        expression: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        z: int,
        width: int | None,
    ) -> Signal:
        """Lower bitwise logical binary expressions to one gate per bit."""
        operator = expression.get("op")
        left = expression.get("left")
        right = expression.get("right")
        if (
            not isinstance(operator, str)
            or not isinstance(left, dict)
            or not isinstance(right, dict)
        ):
            self.error(
                "InvalidExpressionError", "Invalid binary expression", expression
            )
        gate_type = BINARY_GATES.get(operator)
        if gate_type is None:
            self.error(
                "UnsupportedExpressionError",
                f"Unsupported IR binary operator: {operator}",
                expression,
            )
        left_signal = self._lower_expression(left, signals, indices, z, width)
        right_signal = self._lower_expression(right, signals, indices, z, width)
        signal_width = width or self._signal_width([left_signal, right_signal], 1)
        resolved_type = self.resolve_expression(expression, signals)  # type: ignore[arg-type]
        formatted_value_type = self._format_type(resolved_type)
        is_input = left_signal.is_input or right_signal.is_input
        prefix = "IN" if is_input else ""
        bits: list[int] = []
        for index in range(signal_width):
            inputs = [
                *self._expand_for_width(left_signal, signal_width, index, expression),
                *self._expand_for_width(right_signal, signal_width, index, expression),
            ]
            bits.append(
                self._allocator.create(
                    gate_type, inputs, index, prefix, value_type=formatted_value_type
                )
            )
        return Signal(tuple(bits), value_type=resolved_type)

    def _constant_signal(
        self, value: int, width: int, value_type: ResolvedType
    ) -> Signal:
        """Encode an integer constant as SWITCH gates per bit."""
        if width <= 0:
            self.error("ValueError", "Signal width must be positive")
        if value >= 1 << width:
            self.error("ValueError", f"Value {value} does not fit in {width} bits")
        if value_type.name == "dynamic":
            value_type = ResolvedType("dynamic", width)
        formatted_value_type = self._format_type(value_type)
        bits = [
            self._allocator.create(
                "SWITCH",
                [],
                index,
                "IN",
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
        if len(signal.bits) < width and signal.value_type.name == "dynamic":
            return self._pad_width(signal, width)
        self.error(
            "TypeMismatchError",
            f"Expected a {width}-bit value, received {len(signal.bits)} bits",
            node,
        )

    def _pad_width(self, signal: Signal, target_width: int) -> Signal:
        """Zero-pad a dynamic signal to a target width."""
        if len(signal.bits) >= target_width:
            return signal
        padding_count = target_width - len(signal.bits)
        padding = self._constant_signal(
            0, padding_count, ResolvedType("dynamic", target_width)
        )
        all_bits = tuple([*signal.bits, *padding.bits])
        for bit in all_bits:
            if bit in self._allocator._gates:
                self._allocator._gates[bit].value_type = f"u{target_width}"
        if signal.bits and padding.bits:
            first_var = self._allocator._gates[signal.bits[0]].variable
            for bit in padding.bits:
                if bit in self._allocator._gates:
                    self._allocator._gates[bit].variable = first_var
        return Signal(all_bits, value_type=ResolvedType("dynamic", target_width))

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
            "TypeMismatchError",
            f"Cannot connect {len(signal.bits)} bits to a {width}-bit value",
            node,
        )

    @staticmethod
    def _signal_width(signals: list[Signal], default: int) -> int:
        """Return the widest signal width or a fallback for empty input lists."""
        return max((len(signal.bits) for signal in signals), default=default)

    def _evaluate_integer(self, expression: AstNode, indices: dict[str, int]) -> int:
        """Evaluate compile-time integer expressions used for indexes and lengths."""
        expression_type = expression.get("type")
        if expression_type == "int" and isinstance(expression.get("value"), int):
            return expression["value"]
        if expression_type == "ident":
            name = expression.get("name")
            if isinstance(name, str) and name in indices:
                return indices[name]
        if expression_type == "unary":
            operator = expression.get("op")
            value = expression.get("value")
            if isinstance(operator, str) and isinstance(value, dict):
                operand = self._evaluate_integer(value, indices)
                if operator == "+":
                    return operand
                if operator == "-":
                    return -operand
                if operator == "~":
                    return ~operand
        if expression_type == "binary":
            operator = expression.get("op")
            left = expression.get("left")
            right = expression.get("right")
            if (
                isinstance(operator, str)
                and isinstance(left, dict)
                and isinstance(right, dict)
            ):
                first = self._evaluate_integer(left, indices)
                second = self._evaluate_integer(right, indices)
                return self._apply_integer_operator(operator, first, second, expression)
        self.error(
            "InvalidExpressionError",
            "Expected a compile-time integer expression",
            expression,
        )

    def _apply_integer_operator(
        self,
        operator: str,
        left: int,
        right: int,
        node: AstNode,
    ) -> int:
        """Apply one supported compile-time integer operator."""
        if operator == "+":
            return left + right
        if operator == "-":
            return left - right
        if operator == "*":
            return left * right
        if operator == "/":
            if right == 0:
                self.error("ValueError", "Division by zero", node)
            return left // right
        if operator == "%":
            if right == 0:
                self.error("ValueError", "Modulo by zero", node)
            return left % right
        if operator == "<<":
            return left << right
        if operator == ">>":
            return left >> right
        if operator == "&":
            return left & right
        if operator == "|":
            return left | right
        if operator == "^":
            return left ^ right
        self.error(
            "InvalidExpressionError", f"Unsupported integer operator: {operator}", node
        )


__all__ = ["LoweringMixin"]
