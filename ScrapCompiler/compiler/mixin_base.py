from __future__ import annotations

from typing import Any, NoReturn

from .types import *


class CompilerMixinBase:
    """Base class that declares the shared compiler interface for type checkers."""

    def error(self, name: str, text: str, node: AstNode | None = None) -> NoReturn:
        raise NotImplementedError()

    def expect[T](
        self,
        value: T,
        name: str,
        message: str,
        expected: object = object(),
        node: AstNode | None = None,
    ) -> T:
        raise NotImplementedError()

    def resolve_type(
        self,
        name: str,
        length: AstNode | None = None,
        symbols: SymbolTable | None = None,
        node: AstNode | None = None,
    ) -> ResolvedType:
        raise NotImplementedError()

    def resolve_expression(
        self,
        expression: AstNode,
        symbols: SymbolTable,
    ) -> ResolvedType:
        raise NotImplementedError()

    def resolve_length(
        self,
        expression: AstNode,
        symbols: SymbolTable,
    ) -> int | str:
        raise NotImplementedError()

    def _resolve_identifier(
        self,
        expression: AstNode,
        symbols: SymbolTable,
    ) -> ResolvedType:
        raise NotImplementedError()

    def _resolve_index(
        self,
        expression: AstNode,
        symbols: SymbolTable,
    ) -> ResolvedType:
        raise NotImplementedError()

    def _resolve_field(
        self,
        expression: AstNode,
        symbols: SymbolTable,
    ) -> ResolvedType:
        raise NotImplementedError()

    def _resolve_call(
        self,
        expression: AstNode,
        symbols: SymbolTable,
    ) -> ResolvedType:
        raise NotImplementedError()

    def _resolve_cast(
        self,
        expression: AstNode,
        symbols: SymbolTable,
    ) -> ResolvedType:
        raise NotImplementedError()

    def _resolve_new(
        self,
        expression: AstNode,
        symbols: SymbolTable,
    ) -> ResolvedType:
        raise NotImplementedError()

    def _resolve_unary(
        self,
        expression: AstNode,
        symbols: SymbolTable,
    ) -> ResolvedType:
        raise NotImplementedError()

    def _resolve_binary(
        self,
        expression: AstNode,
        symbols: SymbolTable,
    ) -> ResolvedType:
        raise NotImplementedError()

    def _resolve_definition_type(
        self,
        definition: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        generic_width: int,
    ) -> ResolvedType:
        raise NotImplementedError()

    @staticmethod
    def _definition_name(definition: AstNode) -> str:
        raise NotImplementedError()

    @staticmethod
    def _is_integer_type_name(name: str) -> bool:
        raise NotImplementedError()

    @staticmethod
    def _get_integer_width(name: str) -> int | None:
        raise NotImplementedError()

    def _is_integer_type(self, value_type: ResolvedType) -> bool:
        raise NotImplementedError()

    @staticmethod
    def _is_assignable(target: ResolvedType, source: ResolvedType) -> bool:
        raise NotImplementedError()

    def _common_integer_type(
        self,
        left: ResolvedType,
        right: ResolvedType,
    ) -> ResolvedType:
        raise NotImplementedError()

    @staticmethod
    def _format_type(value_type: ResolvedType) -> str:
        raise NotImplementedError()

    def _resolve_builtin_width(
        self,
        expression: AstNode,
        parent_signals: SignalTable,
    ) -> int | None:
        raise NotImplementedError()

    def _field_width(
        self,
        definition: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        generic_width: int,
    ) -> int:
        raise NotImplementedError()

    def _generic_width(
        self,
        expression: AstNode,
        input_defs: list[object],
        output_defs: list[object],
        parent_signals: SignalTable | None = None,
        positional: list[AstNode] | None = None,
        named: dict[str, AstNode] | None = None,
    ) -> int:
        raise NotImplementedError()

    def _infer_expression_width(
        self,
        expression: AstNode,
        signals: SignalTable,
    ) -> int | None:
        raise NotImplementedError()

    def _constant_signal(
        self,
        value: int,
        width: int,
        value_type: ResolvedType,
    ) -> Signal:
        raise NotImplementedError()

    def _coerce_width(
        self,
        signal: Signal,
        width: int | None,
        node: AstNode,
    ) -> Signal:
        raise NotImplementedError()

    def _pad_width(
        self,
        signal: Signal,
        target_width: int,
    ) -> Signal:
        raise NotImplementedError()

    def _expand_for_width(
        self,
        signal: Signal,
        width: int,
        index: int,
        node: AstNode,
    ) -> list[int]:
        raise NotImplementedError()

    @staticmethod
    def _signal_width(signals: list[Signal], default: int) -> int:
        raise NotImplementedError()

    def _evaluate_integer(
        self,
        expression: AstNode,
        indices: dict[str, int],
    ) -> int:
        raise NotImplementedError()

    def _apply_integer_operator(
        self,
        operator: str,
        left: int,
        right: int,
        node: AstNode,
    ) -> int:
        raise NotImplementedError()

    def _lower_expression(
        self,
        expression: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        z: int,
        width: int | None,
    ) -> Signal:
        raise NotImplementedError()

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
        raise NotImplementedError()

    def _lower_arrow(
        self,
        statement: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        z: int,
    ) -> None:
        raise NotImplementedError()

    def _lower_dynamic(
        self,
        statement: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        z: int,
        output_ports: SignalTable,
    ) -> None:
        raise NotImplementedError()

    def _lower_builtin_call(
        self,
        expression: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        z: int,
        width: int | None,
    ) -> Signal:
        raise NotImplementedError()

    def _lower_cast(
        self,
        expression: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        z: int,
        width: int | None,
    ) -> Signal:
        raise NotImplementedError()

    def _lower_unary(
        self,
        expression: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        z: int,
        width: int | None,
    ) -> Signal:
        raise NotImplementedError()

    def _lower_binary(
        self,
        expression: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        z: int,
        width: int | None,
    ) -> Signal:
        raise NotImplementedError()

    def _lower_index(
        self,
        expression: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        z: int,
    ) -> Signal:
        raise NotImplementedError()

    def _lower_field(
        self,
        expression: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        z: int,
        width: int | None,
    ) -> Signal:
        raise NotImplementedError()

    def _lower_call(
        self,
        expression: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        z: int,
        width: int | None,
    ) -> Signal:
        raise NotImplementedError()

    def _lower_new(
        self,
        expression: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        z: int,
        target: Signal | None,
        node: AstNode,
    ) -> Signal:
        raise NotImplementedError()

    def _instantiate_module(
        self,
        expression: AstNode,
        parent_signals: SignalTable,
        parent_indices: dict[str, int],
        parent_z: int,
        selected_output: str | None = None,
    ) -> Signal:
        raise NotImplementedError()

    def _input_ports(
        self,
        source: Signal,
        value_type: ResolvedType | None = None,
        variable: str = "",
    ) -> Signal:
        raise NotImplementedError()

    def _output_ports(
        self,
        width: int,
        value_type: ResolvedType,
    ) -> Signal:
        raise NotImplementedError()

    def _primary_output(
        self,
        definitions: list[object],
        output_ports: SignalTable,
        generic_width: int,
        node: AstNode,
    ) -> Signal:
        raise NotImplementedError()

    def _bind_call_arguments(
        self,
        expression: AstNode,
        definitions: list[object],
    ) -> tuple[list[AstNode], dict[str, AstNode]]:
        raise NotImplementedError()

    def _find_inherited_output(
        self,
        target: Signal | None,
        arguments: list[Signal],
    ) -> Signal | None:
        raise NotImplementedError()

    def _instantiate_int_input(
        self,
        expression: AstNode,
        parent_signals: SignalTable,
        parent_indices: dict[str, int],
        parent_z: int,
    ) -> Signal:
        raise NotImplementedError()

    def _instantiate_int_display(
        self,
        expression: AstNode,
        parent_signals: SignalTable,
        parent_indices: dict[str, int],
        parent_z: int,
    ) -> Signal:
        raise NotImplementedError()

    def _instantiate_lamp(
        self,
        expression: AstNode,
        parent_signals: SignalTable,
        parent_indices: dict[str, int],
        parent_z: int,
    ) -> Signal:
        raise NotImplementedError()

    def _instantiate_switch(
        self,
        expression: AstNode,
        parent_signals: SignalTable,
        parent_indices: dict[str, int],
        parent_z: int,
    ) -> Signal:
        raise NotImplementedError()

    def _instantiate_button(
        self,
        expression: AstNode,
        parent_signals: SignalTable,
        parent_indices: dict[str, int],
        parent_z: int,
    ) -> Signal:
        raise NotImplementedError()

    def _resolve_function_call(
        self,
        statement: AstNode,
        symbols: SymbolTable,
    ) -> None:
        raise NotImplementedError()

    def _lower_function_call(
        self,
        statement: AstNode,
        signals: SignalTable,
        indices: dict[str, int],
        z: int,
    ) -> Signal:
        raise NotImplementedError()

    _allocator: Any
    _module_asts: Any
    _functions: Any
    _literal_widths: Any
    module_types: Any
    ast: Any
    _lower_statements: Any
