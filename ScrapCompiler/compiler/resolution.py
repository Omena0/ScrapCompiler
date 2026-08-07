from __future__ import annotations

from .mixin_base import CompilerMixinBase
from .types import *


class ResolutionMixin(CompilerMixinBase):
    """Type resolution helpers for the Scrap compiler."""

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
            self.error("UnknownTypeError", f"Unknown type: {name}", node)

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
        expression_type = expression.get("type")
        if expression_type == "int" and isinstance(expression.get("value"), int):
            return expression["value"]
        if expression_type == "ident" and resolved.name in {"int", "dynamic"}:
            identifier = expression.get("name")
            if isinstance(identifier, str):
                return identifier

        self.error(
            "InvalidLengthError",
            "Lengths must be integer expressions or dynamic signal references",
            node or expression,
        )

    def resolve_expression(
        self, expression: AstNode, symbols: SymbolTable
    ) -> ResolvedType:
        """Resolve the type of an expression within a symbol scope."""
        expression_type = expression.get("type")
        if expression_type == "cast":
            return self._resolve_cast(expression, symbols)
        if expression_type == "int":
            return ResolvedType("dynamic")
        if expression_type == "bool":
            return ResolvedType("bool")
        if expression_type == "ident":
            return self._resolve_identifier(expression, symbols)
        if expression_type == "index":
            return self._resolve_index(expression, symbols)
        if expression_type == "field":
            return self._resolve_field(expression, symbols)
        if expression_type == "call":
            return self._resolve_call(expression, symbols)
        if expression_type == "new":
            return self._resolve_new(expression, symbols)
        if expression_type == "unary":
            return self._resolve_unary(expression, symbols)
        if expression_type == "binary":
            return self._resolve_binary(expression, symbols)
        self.error("InvalidExpressionError", "Unknown expression type", expression)

    def _resolve_identifier(
        self, expression: AstNode, symbols: SymbolTable | dict[str, Any]
    ) -> ResolvedType:
        """Resolve an identifier expression from the active symbol table."""
        name = expression.get("name")

        if not isinstance(name, str) or not name:
            self.error(
                "InvalidExpressionError",
                "Identifier expression is missing a name",
                expression,
            )

        resolved = symbols.get(name)

        if resolved is None and name in self.module_types:
            return self.module_types[name]

        if resolved is None:
            self.error(
                "UnknownIdentifierError", f"Unknown identifier: {name}", expression
            )

        if isinstance(resolved, Signal):
            return resolved.value_type

        if isinstance(resolved, ResolvedType):
            return resolved

        self.error(
            "InvalidExpressionError",
            f"Invalid symbol table entry for {name}",
            expression,
        )

    def _resolve_index(self, expression: AstNode, symbols: SymbolTable) -> ResolvedType:
        """Resolve an indexed signal or typed module result to its element type."""
        value = expression.get("value")
        index = expression.get("index")
        if not isinstance(value, dict) or not isinstance(index, dict):
            self.error("InvalidExpressionError", "Invalid index expression", expression)
        index_type = self.resolve_expression(index, symbols)
        if not self._is_integer_type(index_type):
            self.error("TypeMismatchError", "Indexes must be integers", index)

        value_type = self.resolve_expression(value, symbols)
        if value_type.name == "dynamic":
            return ResolvedType("bit")
        if self._is_integer_type(value_type):
            return ResolvedType("bit")
        if value_type.arguments:
            return value_type.arguments[0]
        self.error(
            "TypeMismatchError",
            f"Cannot index {self._format_type(value_type)}",
            expression,
        )

    def _resolve_field(self, expression: AstNode, symbols: SymbolTable) -> ResolvedType:
        """Resolve a field selection on a module call result."""
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
            module = self._module_asts[value["name"]]
            fields = module.get("fields")
            if not isinstance(fields, dict):
                self.error("InvalidModule", f"Invalid module {value['name']}", module)
            output_defs = fields.get("outputs")
            if not isinstance(output_defs, list):
                self.error(
                    "InvalidModule", f"Invalid module {value['name']} outputs", module
                )

            for definition in output_defs:
                if (
                    isinstance(definition, dict)
                    and self._definition_name(definition) == name
                ):
                    generic_width = self._generic_width(
                        value, fields.get("inputs", []), output_defs
                    )
                    signals: SignalTable = {}
                    for definition_input in fields.get("inputs", []):
                        if not isinstance(definition_input, dict):
                            continue
                        input_name = self._definition_name(definition_input)
                        input_type = self._resolve_definition_type(
                            definition_input, signals, {}, generic_width
                        )
                        input_width = self._field_width(
                            definition_input, signals, {}, generic_width
                        )
                        signals[input_name] = Signal(
                            tuple(range(input_width)), value_type=input_type
                        )
                    return self._resolve_definition_type(
                        definition, signals, {}, generic_width
                    )

            self.error(
                "UnknownIdentifierError", f"Unknown module output: {name}", expression
            )

        if value.get("type") == "ident":
            ident_name = value.get("name")
            if isinstance(ident_name, str) and ident_name in symbols:
                resolved = symbols[ident_name]
                if (
                    isinstance(resolved, ResolvedType)
                    and resolved.name in self._module_asts
                ):
                    module = self._module_asts[resolved.name]
                    fields = module.get("fields")
                    if isinstance(fields, dict):
                        output_defs = fields.get("outputs")
                        if isinstance(output_defs, list):
                            for definition in output_defs:
                                if (
                                    isinstance(definition, dict)
                                    and self._definition_name(definition) == name
                                ):
                                    length = definition.get("len")
                                    if length is None:
                                        return ResolvedType("dynamic")
                                    if length.get("type") == "ident":
                                        return ResolvedType(
                                            "dynamic", length.get("name")
                                        )
                                    return ResolvedType(
                                        "dynamic", self._evaluate_integer(length, {})
                                    )

        self.error(
            "TypeMismatchError",
            "Field selection is only supported on module call results",
            expression,
        )

    def _resolve_call(self, expression: AstNode, symbols: SymbolTable) -> ResolvedType:
        """Resolve a built-in gate, dynamic helper, or module call."""
        name = expression.get("name")
        arguments = expression.get("args")
        if not isinstance(name, str) or not name:
            self.error(
                "InvalidExpressionError",
                "Call expression is missing a name",
                expression,
            )
        if not isinstance(arguments, list):
            self.error(
                "InvalidExpressionError",
                "Call expression is missing arguments",
                expression,
            )

        if name in BUILTIN_MODULES:
            return self._resolve_builtin_module_type(expression)

        argument_types: list[ResolvedType] = []
        for argument in arguments:
            if not isinstance(argument, dict):
                self.error(
                    "InvalidExpressionError",
                    "Call argument must be an expression",
                    expression,
                )
            argument_value = argument
            if argument.get("type") == "named_arg":
                named_value = argument.get("value")
                if not isinstance(named_value, dict):
                    self.error(
                        "InvalidExpressionError",
                        "Named argument is missing a value",
                        argument,
                    )
                argument_value = named_value
            argument_types.append(self.resolve_expression(argument_value, symbols))

        cast_type = expression.get("cast_type")
        if cast_type is not None and not isinstance(cast_type, str):
            self.error(
                "InvalidExpressionError",
                "Call type argument must be a name",
                expression,
            )

        if name in BUILTIN_GATES:
            for argument_type in argument_types:
                if argument_type.name != "bit":
                    self.error(
                        "TypeMismatchError",
                        f"{name} accepts only bit inputs",
                        expression,
                    )
            return ResolvedType("bit")

        if name == "dynamic":
            if len(argument_types) != 1 or argument_types[0].name != "dynamic":
                self.error(
                    "TypeMismatchError",
                    "dynamic requires one dynamic signal",
                    expression,
                )
            return argument_types[0]

        if name not in self.module_types:
            self.error("UnknownTypeError", f"Unknown callable type: {name}", expression)

        type_arguments: tuple[ResolvedType, ...] = ()
        if cast_type is not None:
            type_arguments = (self.resolve_type(cast_type, node=expression),)
        return ResolvedType(name, arguments=type_arguments)

    def _resolve_builtin_module_type(self, expression: AstNode) -> ResolvedType:
        """Return the output type for a built-in module without resolving width args."""
        name = expression.get("name")
        arguments = expression.get("args")
        if name == "IntInput" or name == "IntDisplay":
            if isinstance(arguments, list) and len(arguments) > 0:
                width_arg = arguments[0]
                if isinstance(width_arg, dict) and width_arg.get("type") == "int":
                    value = width_arg.get("value")
                    if isinstance(value, int):
                        return ResolvedType(f"u{value}")
                if isinstance(width_arg, dict) and width_arg.get("type") == "ident":
                    ident_name = width_arg.get("name")
                    if (
                        isinstance(ident_name, str)
                        and ident_name.startswith("u")
                        and ident_name[1:].isdigit()
                    ):
                        return ResolvedType(ident_name)
            return ResolvedType("bit")
        if name == "Lamp" or name == "Switch" or name == "Button":
            return ResolvedType("bit")
        return ResolvedType("bit")

    def _resolve_cast(self, expression: AstNode, symbols: SymbolTable) -> ResolvedType:
        """Resolve a type cast expression."""
        cast_type = expression.get("cast_type")
        value = expression.get("value")
        if not isinstance(cast_type, str) or not isinstance(value, dict):
            self.error("InvalidExpressionError", "Invalid cast expression", expression)
        resolved = self.resolve_type(cast_type, node=expression)
        width = self._get_integer_width(cast_type)
        if width is not None:
            return ResolvedType(resolved.name, width, resolved.arguments)
        return resolved

    def _resolve_new(self, expression: AstNode, symbols: SymbolTable) -> ResolvedType:
        """Resolve an allocation expression to its constructed value type."""
        value = expression.get("value")
        if not isinstance(value, dict):
            self.error(
                "InvalidExpressionError",
                "new expression is missing a value",
                expression,
            )
        return self.resolve_expression(value, symbols)

    def _resolve_unary(self, expression: AstNode, symbols: SymbolTable) -> ResolvedType:
        """Resolve a unary operator and validate its operand type."""
        operator = expression.get("op")
        value = expression.get("value")
        if not isinstance(operator, str) or not isinstance(value, dict):
            self.error("InvalidExpressionError", "Invalid unary expression", expression)
        value_type = self.resolve_expression(value, symbols)
        if operator in {"+", "-"} and not self._is_integer_type(value_type):
            self.error(
                "TypeMismatchError", f"{operator} requires an integer", expression
            )
        if (
            operator == "~"
            and value_type.name not in {"bit", "int"}
            and not self._is_integer_type(value_type)
        ):
            self.error("TypeMismatchError", "~ requires a bit or integer", expression)
        if operator == "!" and value_type.name not in {"bit", "bool"}:
            self.error("TypeMismatchError", "! requires a bit or boolean", expression)
        return value_type

    def _resolve_binary(
        self, expression: AstNode, symbols: SymbolTable
    ) -> ResolvedType:
        """Resolve a binary operator and validate its operand types."""
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
        left_type = self.resolve_expression(left, symbols)
        right_type = self.resolve_expression(right, symbols)
        if operator in {"==", "!=", "<", "<=", ">", ">="}:
            if not self._is_assignable(left_type, right_type):
                self.error(
                    "TypeMismatchError",
                    "Comparison operands must have matching types",
                    expression,
                )
            return ResolvedType("bool")
        if operator in {"&&", "||"}:
            if left_type.name not in {"bit", "bool"} or right_type.name not in {
                "bit",
                "bool",
            }:
                self.error(
                    "TypeMismatchError",
                    f"{operator} requires bit or boolean operands",
                    expression,
                )
            return ResolvedType(
                "bit" if "bit" in {left_type.name, right_type.name} else "bool"
            )
        if operator in {"&", "|", "^"}:
            if left_type.name == right_type.name == "bit":
                return ResolvedType("bit")
            if self._is_integer_type(left_type) and self._is_integer_type(right_type):
                return self._common_integer_type(left_type, right_type)
            self.error(
                "TypeMismatchError",
                f"{operator} requires matching bit or integer operands",
                expression,
            )
        if operator in {"+", "-", "*", "/", "%", "<<", ">>"}:
            if not self._is_integer_type(left_type) or not self._is_integer_type(
                right_type
            ):
                self.error(
                    "TypeMismatchError",
                    f"{operator} requires integer operands",
                    expression,
                )
            return self._common_integer_type(left_type, right_type)
        self.error(
            "InvalidExpressionError", f"Unknown binary operator: {operator}", expression
        )

    def _resolve_definition_type(
        self,
        definition: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        generic_width: int,
    ) -> ResolvedType:
        """Resolve a field definition to its actual value type."""
        type_name = definition.get("type")
        if type_name == "bit" or type_name == "bool":
            return ResolvedType(type_name)
        if isinstance(type_name, str) and self._is_integer_type_name(type_name):
            return ResolvedType(type_name)
        if type_name != "dynamic":
            self.error(
                "UnknownTypeError",
                f"Unsupported IR field type: {type_name}",
                definition,
            )

        length = definition.get("len")
        if length is None:
            return ResolvedType("dynamic", generic_width)
        if not isinstance(length, dict):
            self.error(
                "InvalidDefinition",
                "Dynamic field length must be an expression",
                definition,
            )
        if length.get("type") == "ident":
            name = length.get("name")
            if isinstance(name, str) and name in signals:
                return ResolvedType("dynamic", len(signals[name].bits))
        return ResolvedType("dynamic", self._evaluate_integer(length, indices))

    @staticmethod
    def _definition_name(definition: AstNode) -> str:
        """Return a validated declaration name."""
        name = definition.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("Definition is missing a name")
        return name

    @staticmethod
    def _is_integer_type_name(name: str) -> bool:
        """Return whether a type name denotes a signed or unsigned integer."""
        return len(name) > 1 and name[0] in {"i", "u"} and name[1:].isdigit()

    @staticmethod
    def _get_integer_width(name: str) -> int | None:
        """Return the bit width for integer type names like u8, i16, or None."""
        if len(name) > 1 and name[0] in {"i", "u"} and name[1:].isdigit():
            return int(name[1:])
        if name in {"bit", "bool"}:
            return 1
        return None

    def _is_integer_type(self, value_type: ResolvedType) -> bool:
        """Return whether a resolved type is an integer type."""
        return value_type.name in {"int", "dynamic"} or self._is_integer_type_name(
            value_type.name
        )

    @staticmethod
    def _is_assignable(target: ResolvedType, source: ResolvedType) -> bool:
        """Return whether a source value can be assigned to a target type."""
        if source.name == "dynamic" or target.name == "dynamic":
            return True
        if target.name != source.name or target.arguments != source.arguments:
            return False
        return (
            target.length is None
            or source.length is None
            or target.length == source.length
        )

    def _common_integer_type(
        self, left: ResolvedType, right: ResolvedType
    ) -> ResolvedType:
        """Return the shared integer type or the generic integer fallback."""
        if left == right:
            return left
        if left.name == "int":
            return right
        if right.name == "int":
            return left
        return ResolvedType("int")

    @staticmethod
    def _format_type(value_type: ResolvedType) -> str:
        """Format a resolved type for compiler diagnostics."""
        if value_type.name == "dynamic" and isinstance(value_type.length, int):
            return f"u{value_type.length}"
        suffix = ""
        if value_type.arguments:
            suffix = (
                "<"
                + ", ".join(argument.name for argument in value_type.arguments)
                + ">"
            )
        if value_type.length is not None:
            suffix += f"[{value_type.length}]"
        return value_type.name + suffix

    def _resolve_builtin_width(
        self, expression: AstNode, parent_signals: SignalTable
    ) -> int | None:
        """Resolve the width argument for built-in modules like IntInput. Returns None for dynamic."""
        arguments = expression.get("args")
        if not isinstance(arguments, list) or len(arguments) < 1:
            return None

        width_arg = arguments[0]
        if isinstance(width_arg, dict) and width_arg.get("type") == "int":
            value = width_arg.get("value")
            if isinstance(value, int) and value > 0:
                return value

        if isinstance(width_arg, dict) and width_arg.get("type") == "ident":
            name = width_arg.get("name")
            if isinstance(name, str):
                if name in parent_signals:
                    signal = parent_signals[name]
                    return len(signal.bits)
                if name.startswith("u") and name[1:].isdigit():
                    return int(name[1:])

        self.error(
            "InvalidExpressionError",
            "Built-in module width must be a positive integer, unsigned type, or signal",
            expression,
        )

    def _field_width(
        self,
        definition: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        generic_width: int,
    ) -> int:
        """Resolve a field declaration to a concrete number of signal bits."""
        type_name = definition.get("type")
        if type_name == "bit" or type_name == "bool":
            return 1
        if isinstance(type_name, str) and self._is_integer_type_name(type_name):
            return int(type_name[1:])
        if type_name != "dynamic":
            self.error(
                "UnknownTypeError",
                f"Unsupported IR field type: {type_name}",
                definition,
            )

        length = definition.get("len")
        if length is None:
            return generic_width
        if not isinstance(length, dict):
            self.error(
                "InvalidDefinition",
                "Dynamic field length must be an expression",
                definition,
            )
        if length.get("type") == "ident":
            name = length.get("name")
            if isinstance(name, str) and name in signals:
                return len(signals[name].bits)
        return self._evaluate_integer(length, indices)

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
            isinstance(definition, dict) and definition.get("type") == "dynamic"
            for definition in [*input_defs, *output_defs]
        )
        cast_type = expression.get("cast_type")
        if cast_type is None and not needs_width:
            return 1
        if isinstance(cast_type, str):
            if cast_type == "bit":
                return 1
            if not self._is_integer_type_name(cast_type) or cast_type[0] != "u":
                self.error(
                    "TypeArgumentError",
                    "Dynamic modules require an unsigned integer type",
                    expression,
                )
            width = int(cast_type[1:])
            if width <= 0:
                self.error(
                    "TypeArgumentError",
                    "Dynamic module width must be positive",
                    expression,
                )
            return width
        if cast_type is not None:
            self.error(
                "TypeArgumentError",
                "Dynamic modules require a <uN> type argument",
                expression,
            )

        if positional is None or named is None:
            arguments = expression.get("args")
            if not isinstance(arguments, list):
                self.error(
                    "TypeArgumentError",
                    "Dynamic modules require a <uN> type argument",
                    expression,
                )
            positional = []
            named = {}
            for argument in arguments:
                if isinstance(argument, dict):
                    if argument.get("type") == "named_arg":
                        arg_name = argument.get("name")
                        arg_value = argument.get("value")
                        if isinstance(arg_name, str) and isinstance(arg_value, dict):
                            named[arg_name] = arg_value
                    else:
                        positional.append(argument)

        for position, definition in enumerate(input_defs):
            if not isinstance(definition, dict):
                continue
            field_name = self._definition_name(definition)
            type_name = definition.get("type")
            length = definition.get("len")
            if type_name == "dynamic" and length is None:
                argument = named.get(field_name)
                if argument is None and position < len(positional):
                    argument = positional[position]
                if argument is not None:
                    inferred = self._infer_expression_width(argument, parent_signals)
                    if inferred is not None:
                        return inferred

        self.error(
            "TypeArgumentError",
            "Dynamic modules require a <uN> type argument",
            expression,
        )

    def _infer_expression_width(
        self, expression: AstNode, signals: SignalTable | None
    ) -> int | None:
        """Attempt to infer the bit width of an expression from known signals."""
        expression_type = expression.get("type")
        if expression_type == "int":
            value = expression.get("value")
            if isinstance(value, int):
                return max(value.bit_length(), 1)
            return None
        if expression_type == "ident":
            name = expression.get("name")
            if isinstance(name, str):
                if signals is not None and name in signals:
                    return len(signals[name].bits)
                if name in self._literal_widths:
                    return self._literal_widths[name]
            return None
        return None


__all__ = ["ResolutionMixin"]
