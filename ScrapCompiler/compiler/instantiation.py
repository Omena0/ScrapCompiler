from __future__ import annotations

from .mixin_base import CompilerMixinBase
from .types import *


class InstantiationMixin(CompilerMixinBase):
    """Module and built-in gate instantiation helpers for the Scrap compiler."""

    def _instantiate_module(
        self,
        expression: AstNode,
        parent_signals: SignalTable,
        parent_indices: dict[str, int],
        parent_z: int,
        selected_output: str | None = None,
    ) -> Signal:
        """Instantiate a module, bind its inputs, and return its primary output or a selected output."""
        name = expression.get("name")
        if not isinstance(name, str):
            self.error(
                "InvalidExpressionError", "Module call is missing a name", expression
            )

        if name == "IntInput":
            return self._instantiate_int_input(
                expression, parent_signals, parent_indices, parent_z
            )
        if name == "IntDisplay":
            return self._instantiate_int_display(
                expression, parent_signals, parent_indices, parent_z
            )
        if name == "Lamp":
            return self._instantiate_lamp(
                expression, parent_signals, parent_indices, parent_z
            )
        if name == "Switch":
            return self._instantiate_switch(
                expression, parent_signals, parent_indices, parent_z
            )
        if name in ("Button", "ButtonInput"):
            return self._instantiate_button(
                expression, parent_signals, parent_indices, parent_z
            )
        if name == "Object":
            return self._instantiate_object(
                expression, parent_signals, parent_indices, parent_z
            )

        module = self._module_asts[name]
        fields = module.get("fields")
        if not isinstance(fields, dict):
            self.error("InvalidModule", f"Invalid module {name}", module)
        input_defs = fields.get("inputs")
        output_defs = fields.get("outputs")
        gates = module.get("gates")
        if (
            not isinstance(input_defs, list)
            or not isinstance(output_defs, list)
            or not isinstance(gates, list)
        ):
            self.error("InvalidModule", f"Invalid module {name} fields", module)

        decorators = module.get("decorators", [])
        has_clocked_input = any(
            isinstance(d, dict) and d.get("name") == "clocked_input"
            for d in decorators
        )
        has_clocked_output = any(
            isinstance(d, dict) and d.get("name") == "clocked_output"
            for d in decorators
        )

        positional, named = self._bind_call_arguments(expression, input_defs)
        generic_width = self._generic_width(
            expression, input_defs, output_defs, parent_signals, positional, named
        )
        signals: SignalTable = {}
        output_ports: SignalTable = {}

        input_names: set[str] = set()
        for position, definition in enumerate(input_defs):
            if not isinstance(definition, dict):
                self.error(
                    "InvalidDefinition", "Input definition must be an object", module
                )
            field_name = self._definition_name(definition)
            input_names.add(field_name)
            input_type = self._resolve_definition_type(
                definition, signals, parent_indices, generic_width
            )
            field_width = self._field_width(
                definition, signals, parent_indices, generic_width
            )
            argument = named.get(field_name)
            if argument is None and position < len(positional):
                argument = positional[position]
            if argument is None:
                if not definition.get("optional", False):
                    self.error(
                        "MissingArgumentError",
                        f"Missing module input: {field_name}",
                        expression,
                    )
                source = self._constant_signal(0, field_width, input_type)
            else:
                source = self._lower_expression(
                    argument,
                    parent_signals,
                    parent_indices,
                    0,
                    field_width,
                )
            signals[field_name] = self._input_ports(source, input_type, field_name)

        if has_clocked_input:
            clock_signal = signals.get("clock")
            if clock_signal and clock_signal.bits:
                clock_bit = clock_signal.bits[0]
                and_outputs = []
                bit_index = 0
                for field_name in input_names:
                    if field_name == "clock":
                        continue
                    signal = signals[field_name]
                    gated_bits = []
                    for bit in signal.bits:
                        and_id = self._allocator.create(
                            "AND", [bit, clock_bit], bit_index, "", value_type="bit"
                        )
                        gated_bits.append(and_id)
                        bit_index += 1
                    signals[field_name] = Signal(tuple(gated_bits), signal.value_type)
                    and_outputs.extend(gated_bits)

                if and_outputs:
                    or_id = self._allocator.create(
                        "OR", and_outputs, 0, "", value_type="bit"
                    )
                    signals["clock_gate"] = Signal((or_id,), value_type=ResolvedType("bit"))

        for definition in output_defs:
            if not isinstance(definition, dict):
                self.error(
                    "InvalidDefinition", "Output definition must be an object", module
                )
            field_name = self._definition_name(definition)
            output_type = self._resolve_definition_type(
                definition, signals, parent_indices, generic_width
            )
            field_width = self._field_width(
                definition, signals, parent_indices, generic_width
            )
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
            if field_name in lowered and len(port.bits) == len(
                lowered[field_name].bits
            ):
                output_ports[field_name] = lowered[field_name]

        if has_clocked_output:
            clock_signal = signals.get("clock")
            if clock_signal and clock_signal.bits:
                clock_bit = clock_signal.bits[0]
                for field_name, port in list(output_ports.items()):
                    gated_bits = []
                    for bit in port.bits:
                        switch_id = self._allocator.create(
                            "SWITCH", [bit], 0, "", value_type="bit"
                        )
                        self._allocator.append_inputs(switch_id, [clock_bit])
                        gated_bits.append(switch_id)
                    gated_port = Signal(tuple(gated_bits), port.value_type)
                    output_ports[field_name] = gated_port
                    signals[field_name] = gated_port
                primary = self._primary_output(output_defs, output_ports, generic_width, module)

        if selected_output is not None:
            if selected_output not in output_ports:
                self.error(
                    "UnknownIdentifierError",
                    f"Unknown module output: {selected_output}",
                    expression,
                )
            result = output_ports[selected_output]
        else:
            result = primary

        module_ports = dict(output_ports)
        for field_name in input_names:
            if field_name in signals:
                module_ports[field_name] = signals[field_name]

        return Signal(
            bits=result.bits,
            value_type=result.value_type,
            is_input=result.is_input,
            module_outputs=module_ports,
        )

    def _input_ports(
        self, source: Signal, value_type: ResolvedType | None = None, variable: str = ""
    ) -> Signal:
        """Bind a module input to the instantiated module scope."""
        value_type = value_type or source.value_type
        if variable:
            for bit in source.bits:
                if not self._allocator._gates[bit].variable:
                    self._allocator.set_variable(bit, variable)
        return Signal(source.bits, value_type)

    def _output_ports(self, width: int, value_type: ResolvedType) -> Signal:
        """Create default output OR gates that can later inherit another gate type."""
        formatted_value_type = self._format_type(value_type)
        bits = [
            self._allocator.create(
                "OR",
                [],
                index,
                "",
                value_type=formatted_value_type,
                is_output_port=True,
            )
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
            if isinstance(definition, dict) and definition.get("type") == "dynamic":
                name = self._definition_name(definition)
                output = output_ports[name]

                if len(output.bits) == generic_width:
                    return output

        for definition in definitions:
            if isinstance(definition, dict):
                return output_ports[self._definition_name(definition)]

        self.error("InvalidModule", "Module has no outputs", node)

    def _bind_call_arguments(
        self,
        expression: AstNode,
        definitions: list[object],
    ) -> tuple[list[AstNode], dict[str, AstNode]]:
        """Split positional and named call arguments and validate their names."""
        arguments = expression.get("args")
        if not isinstance(arguments, list):
            self.error(
                "InvalidExpressionError",
                "Call expression is missing arguments",
                expression,
            )
        known_names = {
            self._definition_name(definition)
            for definition in definitions
            if isinstance(definition, dict)
        }
        positional: list[AstNode] = []
        named: dict[str, AstNode] = {}
        for argument in arguments:
            if not isinstance(argument, dict):
                self.error(
                    "InvalidExpressionError",
                    "Call argument must be an expression",
                    expression,
                )
            if argument.get("type") != "named_arg":
                positional.append(argument)
                continue
            argument_name = argument.get("name")
            value = argument.get("value")
            if not isinstance(argument_name, str) or argument_name not in known_names:
                self.error(
                    "UnknownArgumentError",
                    f"Unknown module input: {argument_name}",
                    argument,
                )
            if not isinstance(value, dict):
                self.error(
                    "InvalidExpressionError",
                    "Named argument is missing a value",
                    argument,
                )
            if argument_name in named:
                self.error(
                    "DuplicateArgumentError",
                    f"Repeated module input: {argument_name}",
                    argument,
                )
            named[argument_name] = value
        if len(positional) > len(definitions):
            self.error("ArgumentError", "Too many positional module inputs", expression)
        return positional, named

    def _find_inherited_output(
        self,
        target: Signal | None,
        arguments: list[Signal],
    ) -> Signal | None:
        """Find an output signal that a ``new`` expression can retag in place."""
        if len(arguments) == 1:
            candidate = arguments[0]
            if candidate.bits and all(
                self._allocator.is_output_port(gate) for gate in candidate.bits
            ):
                return candidate
        if target is not None and all(
            self._allocator.is_output_port(gate) for gate in target.bits
        ):
            return target
        return None

    def _instantiate_int_input(
        self,
        expression: AstNode,
        parent_signals: SignalTable,
        parent_indices: dict[str, int],
        parent_z: int,
    ) -> Signal:
        """Create a block of SWITCH gates representing an integer input."""
        width = self._resolve_builtin_width(expression, parent_signals)
        if width is None:
            self.error(
                "InvalidExpressionError",
                "IntInput requires a concrete width",
                expression,
            )
        bits = []
        for index in range(width):
            gate_id = self._allocator.create(
                "SWITCH", [], index, "IN", value_type=f"u{width}"
            )
            self._allocator.mark_input(gate_id)
            bits.append(gate_id)
        signal = Signal(tuple(bits), value_type=ResolvedType(f"u{width}"))
        return Signal(
            bits=signal.bits,
            value_type=signal.value_type,
            module_outputs={"bits": signal},
        )

    def _instantiate_int_display(
        self,
        expression: AstNode,
        parent_signals: SignalTable,
        parent_indices: dict[str, int],
        parent_z: int,
    ) -> Signal:
        """Create a block of LAMP gates representing an integer display."""
        width = self._resolve_builtin_width(expression, parent_signals)
        if width is None:
            self.error(
                "InvalidExpressionError",
                "IntDisplay requires a concrete width",
                expression,
            )
        input_signal = None
        arguments = expression.get("args")
        if isinstance(arguments, list) and len(arguments) > 1:
            input_signal = self._lower_expression(
                arguments[1], parent_signals, parent_indices, parent_z, width
            )

        bits = []
        for index in range(width):
            gate_inputs: list[int] = []
            if input_signal is not None:
                gate_inputs.append(
                    input_signal.bits[index]
                    if index < len(input_signal.bits)
                    else input_signal.bits[0]
                )
            gate_id = self._allocator.create(
                "LAMP", gate_inputs, index, "OUT", value_type=f"u{width}"
            )
            bits.append(gate_id)
        signal = Signal(tuple(bits), value_type=ResolvedType(f"u{width}"))
        return Signal(bits=signal.bits, value_type=signal.value_type, module_outputs={})

    def _instantiate_lamp(
        self,
        expression: AstNode,
        parent_signals: SignalTable,
        parent_indices: dict[str, int],
        parent_z: int,
    ) -> Signal:
        """Create a single LAMP gate."""
        arguments = expression.get("args")
        input_signal = None
        if isinstance(arguments, list) and len(arguments) > 0:
            input_signal = self._lower_expression(
                arguments[0], parent_signals, parent_indices, parent_z, 1
            )
        bit = input_signal.bits[0] if input_signal else 0
        gate_id = self._allocator.create("LAMP", [bit], 0, "OUT", value_type="bit")
        signal = Signal((gate_id,), value_type=ResolvedType("bit"))
        return Signal(bits=signal.bits, value_type=signal.value_type, module_outputs={})

    def _instantiate_switch(
        self,
        expression: AstNode,
        parent_signals: SignalTable,
        parent_indices: dict[str, int],
        parent_z: int,
    ) -> Signal:
        """Create a single SWITCH gate with a default state."""
        arguments = expression.get("args")
        default_state = 0
        if isinstance(arguments, list) and len(arguments) > 0:
            default_state = self._evaluate_integer(arguments[0], parent_indices)
            if default_state not in (0, 1):
                default_state = 1 if default_state else 0
        gate_id = self._allocator.create(
            "SWITCH", [], 0, "IN", value_type="bit", default_state=default_state
        )
        self._allocator.mark_input(gate_id)
        signal = Signal((gate_id,), value_type=ResolvedType("bit"))
        return Signal(
            bits=signal.bits,
            value_type=signal.value_type,
            module_outputs={"bit": signal},
        )

    def _instantiate_button(
        self,
        expression: AstNode,
        parent_signals: SignalTable,
        parent_indices: dict[str, int],
        parent_z: int,
    ) -> Signal:
        """Create a single BUTTON gate."""
        gate_id = self._allocator.create("BUTTON", [], 0, "IN", value_type="bit")
        self._allocator.mark_input(gate_id)
        signal = Signal((gate_id,), value_type=ResolvedType("bit"))
        return Signal(
            bits=signal.bits,
            value_type=signal.value_type,
            module_outputs={"bit": signal},
        )

    def _instantiate_object(
        self,
        expression: AstNode,
        parent_signals: SignalTable,
        parent_indices: dict[str, int],
        parent_z: int,
    ) -> Signal:
        """Create a dummy gate representing an object literal annotation."""
        arguments = expression.get("args")
        object_value = None
        if isinstance(arguments, list) and len(arguments) > 0:
            arg = arguments[0]
            if isinstance(arg, dict) and arg.get("type") == "object":
                object_value = arg.get("value")

        gate_id = self._allocator.create("OBJECT", [], 0, "", value_type="object")
        if object_value is not None:
            self._allocator._gates[gate_id].annotation = object_value

        signal = Signal((gate_id,), value_type=ResolvedType("object"))
        return Signal(bits=signal.bits, value_type=signal.value_type, module_outputs={})


__all__ = ["InstantiationMixin"]
