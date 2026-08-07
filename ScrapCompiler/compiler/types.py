from __future__ import annotations

from typing import Any, Final, Literal, TypeAlias
from dataclasses import dataclass

AstNode: TypeAlias = dict[str, Any]
SymbolTable: TypeAlias = dict[str, 'ResolvedType']
SignalTable: TypeAlias = dict[str, 'Signal']
TypeLength: TypeAlias = int | str | None
GatePrefix: TypeAlias = Literal['', 'IN', 'OUT']

MISSING: Final = object()
BUILTIN_GATES: Final = frozenset({'Xor', 'And', 'Or', 'Nor', 'XNor', 'Nand'})
BUILTIN_TYPES: Final = frozenset({'bit', 'bool', 'dynamic'})
IR_GATES: Final = {
    'And': 'AND',
    'Nand': 'NAND',
    'Nor': 'NOR',
    'Or': 'OR',
    'XNor': 'XNOR',
    'Xor': 'XOR',
}
BINARY_GATES: Final = {
    '&': 'AND',
    '&&': 'AND',
    '|': 'OR',
    '||': 'OR',
    '^': 'XOR',
}

BUILTIN_MODULES: Final = {
    'IntInput': {
        'inputs': [],
        'outputs': [{'name': 'bits', 'type': 'dynamic', 'len': None}],
        'has_width': True,
    },
    'IntDisplay': {
        'inputs': [{'name': 'bits', 'type': 'dynamic', 'len': None}],
        'outputs': [],
        'has_width': True,
    },
    'Lamp': {
        'inputs': [{'name': 'bit', 'type': 'bit'}],
        'outputs': [],
    },
    'Switch': {
        'inputs': [{'name': 'default', 'type': 'bit'}],
        'outputs': [{'name': 'bit', 'type': 'bit'}],
    },
    'Button': {
        'inputs': [],
        'outputs': [{'name': 'bit', 'type': 'bit'}],
    },
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
    module_outputs: dict[str, 'Signal'] | None = None

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
    variable: str = ''
    default_state: int = 0
    is_output_port: bool = False

