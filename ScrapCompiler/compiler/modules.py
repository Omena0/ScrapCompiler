from __future__ import annotations

from .mixin_base import CompilerMixinBase
from .types import *


class ModulesMixin(CompilerMixinBase):
    """Module compilation helpers for the Scrap compiler."""

    def compile_module(self, name: str, module: AstNode) -> AstNode:
        """Resolve all declarations and gate statements in one module."""
        fields = module.get("fields")
        if not isinstance(fields, dict):
            self.error(
                "InvalidModule", f"Invalid module {name}, missing 'fields'", module
            )

        decorators = module.get("decorators", [])
        if not isinstance(decorators, list):
            decorators = []

        for decorator in decorators:
            if not isinstance(decorator, dict):
                continue
            dec_name = decorator.get("name")
            if dec_name == "assert":
                self._validate_assert_decorator(name, decorator, fields)
            elif dec_name == "pipelined":
                self._validate_timing_decorator(name, decorator)

        has_clocked_input = any(
            isinstance(d, dict) and d.get("name") == "clocked_input"
            for d in decorators
        )
        has_clocked_output = any(
            isinstance(d, dict) and d.get("name") == "clocked_output"
            for d in decorators
        )

        if has_clocked_input or has_clocked_output:
            fields.setdefault("inputs", []).append(
                {"name": "clock", "type": "bit", "optional": True}
            )

        inputs = self._resolve_definitions(fields.get("inputs"), {}, module)
        outputs = self._resolve_definitions(fields.get("outputs"), inputs, module)
        symbols = {**inputs, **outputs}
        resolved_gates = self._resolve_statements(module.get("gates"), symbols, module)
        inherit = module.get("inherit", [])
        if not isinstance(inherit, list):
            self.error(
                "InvalidModule", f"Invalid module {name}, invalid 'inherit'", module
            )

        return {
            "decorators": decorators,
            "inherit": [self.resolve_expression(value, symbols) for value in inherit],
            "fields": {"inputs": inputs, "outputs": outputs},
            "gates": resolved_gates,
        }

    def compile_modules(
        self, modules: dict[str, AstNode], functions: dict[str, AstNode]
    ) -> dict[str, AstNode]:
        """Predeclare and resolve every module in the AST."""
        self.module_types = {name: ResolvedType(name) for name in modules}
        self._functions = functions
        self.modules = {
            name: self.compile_module(name, module) for name, module in modules.items()
        }
        return self.modules

    def _resolve_definitions(
        self,
        definitions: object,
        symbols: SymbolTable,
        node: AstNode,
    ) -> SymbolTable:
        """Resolve field definitions while making earlier names available."""
        if not isinstance(definitions, list):
            self.error("InvalidFields", "Missing or invalid field definitions", node)

        resolved = dict(symbols)
        declared: SymbolTable = {}
        for definition in definitions:
            if not isinstance(definition, dict):
                self.error(
                    "InvalidDefinition", "Field definition must be an object", node
                )
            name = definition.get("name")
            type_name = definition.get("type")
            if not isinstance(name, str) or not name:
                self.error(
                    "InvalidDefinition",
                    "Field definition is missing a name",
                    definition,
                )
            if not isinstance(type_name, str) or not type_name:
                self.error(
                    "InvalidDefinition",
                    "Field definition is missing a type",
                    definition,
                )
            if name in resolved:
                self.error(
                    "DuplicateNameError", f"Duplicate definition: {name}", definition
                )

            length = definition.get("len")
            if length is not None and not isinstance(length, dict):
                self.error(
                    "InvalidDefinition",
                    "Field length must be an expression",
                    definition,
                )
            declared[name] = self.resolve_type(type_name, length, resolved, definition)
            resolved[name] = declared[name]
        return declared

    def _resolve_statements(
        self,
        statements: object,
        symbols: SymbolTable,
        node: AstNode,
        top_level: bool = False,
    ) -> SymbolTable:
        """Resolve gate statements and enforce type-safe assignments and wires."""
        if not isinstance(statements, list):
            self.error("InvalidGates", "Missing or invalid 'gates'", node)

        resolved = dict(symbols)
        if top_level:
            assignments: list[AstNode] = []
            arrows: list[AstNode] = []
            for statement in statements:
                if not isinstance(statement, dict):
                    self.error("InvalidGate", "Gate statement must be an object", node)
                statement_type = statement.get("type")
                if statement_type == "arrow":
                    arrows.append(statement)
                else:
                    assignments.append(statement)

            for statement in assignments:
                self._resolve_statement(statement, resolved, node)
            for statement in arrows:
                self._resolve_statement(statement, resolved, node)
            return resolved

        for statement in statements:
            self._resolve_statement(statement, resolved, node)
        return resolved

    def _resolve_statement(
        self,
        statement: AstNode,
        symbols: SymbolTable,
        node: AstNode,
    ) -> None:
        """Resolve one gate statement and mutate ``symbols`` in place."""
        statement_type = statement.get("type")
        if statement_type == "gate":
            self._resolve_assignment(statement, symbols)
        elif statement_type == "indexed_gate":
            self._resolve_indexed_gate(statement, symbols)
        elif statement_type == "arrow":
            self._resolve_arrow(statement, symbols)
        elif statement_type == "as":
            self._resolve_loop(statement, symbols)
        elif statement_type == "for_loop":
            self._resolve_for_loop(statement, symbols)
        elif statement_type == "function_call":
            self._resolve_function_call(statement, symbols)
        else:
            self.error("InvalidGate", "Unknown gate statement type", statement)

    def _resolve_indexed_gate(
        self,
        statement: AstNode,
        symbols: SymbolTable,
    ) -> None:
        """Resolve an indexed gate assignment."""
        name = statement.get("name")
        index = statement.get("index")
        value = statement.get("value")
        if not isinstance(name, str) or not name:
            self.error("InvalidGate", "Indexed gate assignment is missing a name", statement)
        if not isinstance(index, dict) or not isinstance(value, dict):
            self.error("InvalidGate", "Invalid indexed gate assignment", statement)

        index_type = self.resolve_expression(index, symbols)
        if not self._is_integer_type(index_type):
            self.error(
                "TypeMismatchError",
                f"Index must be an integer, got {self._format_type(index_type)}",
                statement,
            )

        value_type = self.resolve_expression(value, symbols)
        current_type = symbols.get(name)
        if current_type is not None and not self._is_assignable(
            current_type, value_type
        ):
            self.error(
                "TypeMismatchError",
                f"Cannot assign {self._format_type(value_type)} to {self._format_type(current_type)}",
                statement,
            )
        symbols[name] = current_type or value_type

    def _resolve_for_loop(
        self,
        statement: AstNode,
        symbols: SymbolTable,
    ) -> None:
        """Resolve a for loop by adding the loop variable and resolving the body."""
        variable = statement.get("variable")
        count = statement.get("count")
        body = statement.get("gates") or statement.get("body")

        if not isinstance(variable, str) or not variable:
            self.error("InvalidGate", "For loop requires a variable name", statement)
        if not isinstance(count, dict):
            self.error("InvalidGate", "For loop requires a count expression", statement)
        if not isinstance(body, list):
            self.error("InvalidGate", "For loop requires a body", statement)

        resolved_count = self.resolve_expression(count, symbols)
        if not self._is_integer_type(resolved_count):
            self.error(
                "TypeMismatchError",
                f"For loop count must be an integer, got {self._format_type(resolved_count)}",
                statement,
            )

        loop_symbols = dict(symbols)
        loop_symbols[variable] = ResolvedType("int")
        self._resolve_statements(body, loop_symbols, statement)

    def _resolve_assignment(self, statement: AstNode, symbols: SymbolTable) -> None:
        """Resolve a gate assignment and bind or validate its target type."""
        name = statement.get("name")
        value = statement.get("value")
        if not isinstance(name, str) or not name:
            self.error("InvalidGate", "Gate assignment is missing a name", statement)
        if not isinstance(value, dict):
            self.error("InvalidGate", "Gate assignment is missing a value", statement)

        value_type = self.resolve_expression(value, symbols)
        current_type = symbols.get(name)
        if current_type is not None and not self._is_assignable(
            current_type, value_type
        ):
            self.error(
                "TypeMismatchError",
                f"Cannot assign {self._format_type(value_type)} to {self._format_type(current_type)}",
                statement,
            )
        symbols[name] = current_type or value_type
        if value.get("type") == "int" and isinstance(value.get("value"), int):
            self._literal_widths[name] = max(value["value"].bit_length(), 1)

    def _resolve_arrow(self, statement: AstNode, symbols: SymbolTable) -> None:
        """Resolve a wire statement and validate every source against its target."""
        target = statement.get("to")
        sources = statement.get("from")

        if not target:
            self.error("InvalidGate", "Wire statement is missing a target", statement)

        if not isinstance(sources, list):
            self.error("InvalidGate", "Wire statement is missing sources", statement)

        if isinstance(target, dict):
            target_type = self.resolve_expression(target, symbols)
        elif isinstance(target, str):
            target_type = symbols.get(target)
            if target_type is None:
                self.error(
                    "UnknownIdentifierError", f"Unknown wire target: {target}", statement
                )
        else:
            self.error("InvalidGate", "Invalid wire target", statement)

        for source in sources:
            if not isinstance(source, dict):
                self.error(
                    "InvalidGate", "Wire source must be an expression", statement
                )

            source_type = self.resolve_expression(source, symbols)

            if not self._is_assignable(target_type, source_type):
                self.error(
                    "TypeMismatchError",
                    f"Cannot wire {self._format_type(source_type)} to {self._format_type(target_type)}",
                    source,
                )

    def _resolve_loop(self, statement: AstNode, symbols: SymbolTable) -> None:
        """Resolve a bits loop with local indexed variables."""
        name = statement.get("name")
        arguments = statement.get("args")
        variables = statement.get("vars")
        gates = statement.get("gates")

        if name != "bits" or not isinstance(arguments, list) or len(arguments) < 1:
            self.error("InvalidGate", "Invalid bits loop", statement)

        if not isinstance(variables, list):
            variables = []

        if not isinstance(gates, list):
            self.error("InvalidGate", "Invalid bits loop body", statement)

        if not variables:
            variables = [
                arg.get("name")
                for arg in arguments
                if isinstance(arg, dict) and isinstance(arg.get("name"), str)
            ]

        loop_symbols = {**symbols}
        for var_name in variables:
            if isinstance(var_name, str) and var_name:
                loop_symbols[var_name] = ResolvedType("bit")
        loop_symbols.setdefault("index", ResolvedType("int"))

        self._resolve_statements(gates, loop_symbols, statement)

    def _validate_timing_decorator(
        self, name: str, decorator: AstNode
    ) -> None:
        """Validate timing-related decorators."""
        dec_name = decorator.get("name")
        if dec_name == "pipelined":
            args = decorator.get("args", [])
            if isinstance(args, list) and args:
                arg = args[0]
                if isinstance(arg, dict) and arg.get("type") == "int":
                    value = arg.get("value")
                    if isinstance(value, int) and value <= 0:
                        self.error(
                            "InvalidDecoratorError",
                            "@pipelined requires a positive integer argument",
                            decorator,
                        )

    def _validate_assert_decorator(
        self, name: str, decorator: AstNode, fields: AstNode
    ) -> None:
        """Validate that @assert decorator references valid module fields."""
        args = decorator.get("args", [])
        if not isinstance(args, list):
            return

        input_names = {
            d.get("name")
            for d in fields.get("inputs", [])
            if isinstance(d, dict) and isinstance(d.get("name"), str)
        }
        output_names = {
            d.get("name")
            for d in fields.get("outputs", [])
            if isinstance(d, dict) and isinstance(d.get("name"), str)
        }

        for arg in args:
            if not isinstance(arg, dict):
                continue
            if arg.get("type") == "named_arg":
                field_name = arg.get("name")
                if field_name not in input_names and field_name not in output_names:
                    self.error(
                        "AssertError",
                        f"@assert references unknown field '{field_name}' in module '{name}'",
                        decorator,
                    )


__all__ = ["ModulesMixin"]
