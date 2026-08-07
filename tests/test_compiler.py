import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ScrapCompiler.compiler.compiler import ScrapCompiler
from ScrapCompiler.parser import parser
from ScrapCompiler.simulation import simulate_ir


def compile(source: str) -> str:
    ast = parser.parse(source)
    gates = ScrapCompiler(ast).compile()
    return ScrapCompiler.gates_to_ir(gates)


def test_basic_module_with_bit_outputs():
    source = """
module HalfAdder() {
    inputs {
        bit a
        bit b
    }

    outputs {
        bit sum
        bit carry
    }

    gates {
        sum: new Xor(a, b)
        carry: new And(a, b)
    }
}

out: new HalfAdder(1, 0)
"""
    ir = compile(source)
    assert "XOR" in ir
    assert "AND" in ir


def test_dynamic_type_inference_from_ident():
    source = """
module Adder() {
    inputs {
        dynamic a
        dynamic[a] b
        bit ?carry_in
    }

    outputs {
        dynamic[a] sum
        bit carry_out
    }

    gates {
        bits(a, b, sum) as (a, b, sum) {
            x: new Xor()
            a, b -> x

            out: new Xor(sum)
            x, carry_in -> out

            y: new And()
            a, b -> y

            z: new And()
            x, carry_in -> z

            carry_out: new Or()
            y, z -> carry_out

            carry_in: carry_out
        }
    }
}

x: 5
y: 5

out: new Adder(x, y)
"""
    ir = compile(source)
    assert "u3" in ir


def test_dynamic_type_inference_from_int_literal():
    source = """
module Adder() {
    inputs {
        dynamic a
        dynamic[a] b
        bit ?carry_in
    }

    outputs {
        dynamic[a] sum
        bit carry_out
    }

    gates {
        bits(a, b, sum) as (a, b, sum) {
            x: new Xor()
            a, b -> x

            out: new Xor(sum)
            x, carry_in -> out

            y: new And()
            a, b -> y

            z: new And()
            x, carry_in -> z

            carry_out: new Or()
            y, z -> carry_out

            carry_in: carry_out
        }
    }
}

out: new Adder(5, 3)
"""
    ir = compile(source)
    assert "u3" in ir


def test_explicit_generic_type_argument():
    source = """
module Adder() {
    inputs {
        dynamic a
        dynamic[a] b
        bit ?carry_in
    }

    outputs {
        dynamic[a] sum
        bit carry_out
    }

    gates {
        dynamic(a) as n {
            x: new Xor()
            a[n], b[n] -> x

            out: new Xor(sum[n])
            x, carry_in -> out

            y: new And()
            a[n], b[n] -> y

            z: new And()
            x, carry_in -> z

            carry_out: new Or()
            y, z -> carry_out

            carry_in: carry_out
        }
    }
}

out: new Adder<u8>(0, 0)
"""
    ir = compile(source)
    assert "u8" in ir


def test_dynamic_width_one_from_literal_one():
    source = """
module Adder() {
    inputs {
        dynamic a
        dynamic[a] b
        bit ?carry_in
    }

    outputs {
        dynamic[a] sum
        bit carry_out
    }

    gates {
        dynamic(a) as n {
            x: new Xor()
            a[n], b[n] -> x

            out: new Xor(sum[n])
            x, carry_in -> out

            y: new And()
            a[n], b[n] -> y

            z: new And()
            x, carry_in -> z

            carry_out: new Or()
            y, z -> carry_out

            carry_in: carry_out
        }
    }
}

out: new Adder(1, 1)
"""
    ir = compile(source)
    assert "u1" in ir


def test_all_builtin_gates():
    source = """
module GateTest() {
    inputs {
        bit a
        bit b
    }

    outputs {
        bit xor_out
        bit and_out
        bit or_out
        bit nor_out
        bit xnorr_out
        bit nand_out
    }

    gates {
        xor_out: new Xor(a, b)
        and_out: new And(a, b)
        or_out: new Or(a, b)
        nor_out: new Nor(a, b)
        xnorr_out: new XNor(a, b)
        nand_out: new Nand(a, b)
    }
}

out: new GateTest(1, 0)
"""
    ir = compile(source)
    assert "XOR" in ir
    assert "AND" in ir
    assert "OR" in ir
    assert "NAND" in ir
    assert "NOR" in ir
    assert "XNOR" in ir


def test_dynamic_loop_iteration():
    source = """
module Counter() {
    inputs {
        dynamic count
    }

    outputs {
        dynamic[count] bits
    }

    gates {
        dynamic(count) as i {
            out: new Or()
        }
    }
}

x: 4

out: new Counter(x)
"""
    ir = compile(source)
    assert "u3" in ir


def test_wire_arrows():
    source = """
module WireTest() {
    inputs {
        bit a
        bit b
    }

    outputs {
        bit out
    }

    gates {
        mid: new Xor(a, b)
        a, b -> mid
        out: new Or(mid, mid)
    }
}

out: new WireTest(1, 0)
"""
    ir = compile(source)
    assert "XOR" in ir
    assert "OR" in ir


def test_indexing_dynamic_signal():
    source = """
module IndexTest() {
    inputs {
        dynamic width
    }

    outputs {
        bit bit0
    }

    gates {
        temp: new Or()
        width[0] -> temp
        bit0: new Xor(temp, temp)
    }
}

x: 4

out: new IndexTest(x)
"""
    ir = compile(source)
    assert "XOR" in ir


def test_field_selection_on_module():
    source = """
module Pair() {
    inputs {
        bit a
        bit b
    }

    outputs {
        bit first
        bit second
    }

    gates {
        first: new Xor(a, a)
        second: new And(b, b)
    }
}

out: new Pair(1, 0).first
"""
    ir = compile(source)
    assert "XOR" in ir


def test_named_arguments():
    source = """
module NamedArgs() {
    inputs {
        bit a
        bit b
    }

    outputs {
        bit out
    }

    gates {
        out: new Xor(a, b)
    }
}

out: new NamedArgs(b=1, a=0)
"""
    ir = compile(source)
    assert "XOR" in ir


def test_optional_input_defaults_to_zero():
    source = """
module OptionalInput() {
    inputs {
        bit ?a
        bit b
    }

    outputs {
        bit out
    }

    gates {
        out: new Xor(a, b)
    }
}

out: new OptionalInput(b=1)
"""
    ir = compile(source)
    assert "XOR" in ir


def test_module_inheritance():
    source = """
module Base() {
    inputs {
        bit a
    }

    outputs {
        bit out
    }

    gates {
        out: new Xor(a, a)
    }
}

module Child(Base) {
    inputs {
        bit b
    }

    outputs {
        bit final
    }

    gates {
        final: new And(b, b)
    }
}

out: new Child(0)
"""
    ir = compile(source)
    assert "AND" in ir


def test_binary_operators_in_lengths():
    source = """
module WidthTest() {
    inputs {
        dynamic width
    }

    outputs {
        dynamic[width] bits
    }

    gates {
        dynamic(width) as i {
            out: new Or()
        }
    }
}

x: 4

out: new WidthTest(x)
"""
    ir = compile(source)
    assert "u3" in ir


def test_unary_operators():
    source = """
module UnaryTest() {
    inputs {
        bit a
    }

    outputs {
        bit not_out
    }

    gates {
        not_out: new And(~a, a)
    }
}

out: new UnaryTest(1)
"""
    ir = compile(source)
    assert "NOT" in ir


def test_boolean_literals():
    source = """
module BoolTest() {
    inputs {
        bit a
        bit b
    }

    outputs {
        bit out
    }

    gates {
        out: new And(a, b)
    }
}

out: new BoolTest(1, 0)
"""
    ir = compile(source)
    assert "AND" in ir


def test_comments():
    source = """
module CommentTest() {
    inputs {
        bit a
    }

    outputs {
        bit out
    }

    gates {
        out: new Xor(a, a)
    }
}

out: new CommentTest(1)
"""
    ir = compile(source)
    assert "XOR" in ir


def test_simulation_of_adder():
    source = """
module Adder() {
    inputs {
        dynamic a
        dynamic[a] b
        bit ?carry_in
    }

    outputs {
        dynamic[a] sum
        bit carry_out
    }

    gates {
        dynamic(a) as n {
            x: new Xor()
            a[n], b[n] -> x

            out: new Xor(sum[n])
            x, carry_in -> out

            y: new And()
            a[n], b[n] -> y

            z: new And()
            x, carry_in -> z

            carry_out: new Or()
            y, z -> carry_out

            carry_in: carry_out
        }
    }
}

x: 5
y: 5

out: new Adder<u4>(x, y)
"""
    ir = compile(source)
    result = simulate_ir(ir, [5, 5, 0])
    assert result == 10


def test_simulation_of_half_adder():
    source = """
module HalfAdder() {
    inputs {
        bit a
        bit b
    }

    outputs {
        bit sum
        bit carry
    }

    gates {
        sum: new Xor(a, b)
        carry: new And(a, b)
    }
}

out: new HalfAdder(1, 1)
"""
    ir = compile(source)
    result = simulate_ir(ir, [1, 1])
    assert result == 0


def test_module_with_multiple_instances():
    source = """
module Gate() {
    inputs {
        bit a
        bit b
    }

    outputs {
        bit out
    }

    gates {
        out: new And(a, b)
    }
}

x: new Gate(1, 1)
y: new Gate(0, 1)
"""
    ir = compile(source)
    assert ir.count("AND") == 2


def test_assert_decorator_passes():
    source = """
@assert(a=1, b=1, out=1)
module AssertGate() {
    inputs {
        bit a
        bit b
    }

    outputs {
        bit out
    }

    gates {
        out: new And(a, b)
    }
}

x: new AssertGate(1, 1)
"""
    ir = compile(source)
    assert "AND" in ir


def test_assert_decorator_fails():
    source = """
@assert(a=1, b=1, out=0)
module AssertGate() {
    inputs {
        bit a
        bit b
    }

    outputs {
        bit out
    }

    gates {
        out: new And(a, b)
    }
}

x: new AssertGate(1, 1)
"""
    with pytest.raises(SystemExit):
        compile(source)
