# todo

Add decorator support (no user defined decorators)
Support multiple decorators on a single module.

Add @ensure_timing decorator:
Ensures that all inputs are passed in at latest when the value is used.
(delays other inputs if one input arrives later)

Add @pipelined decorator:
Allows the module to be pipelined.
Ensures that all values reach their first place of use EXACTLY when needed. (within n-ticks)
@pipelined(n_ticks) for target speed ((n_ticks) is optional)
Input to pipelined functions should change exactly every n_ticks,
and the module output should be read on the last tick.
Default n_ticks is the fastest the compiler can pipeline it. (simulate it)

Add @clocked_input and @clocked_output decorators.
Hold in/output in a buffer untill clock signal fires to prevent garbage outputs / side effects (+1 input)
Should support other decorators being applied along with it.
If @pipelined, both buffers should share the same release signal.

Add @assert decorator:
Specify value for each input and expected output for any no. of outputs.
for example @assert(a=3, b=2, sum=5, carry_out=0)
Automatically raises on compile time if they fail.

Change dynamic(a) as n { syntax to bits(a) as bit { where 'bit' is a[idx] instead of idx.
Also support doing that with multiple values, like
bits(a, b, sum) as (a, b, sum) {}
Also make sure the variables the 'as' syntax defines are ALL LOCAL.
dont overwrite the actual values passed into bits()
Also support for not having an 'as' at all, in that case implicitly assume that the user
wants to define them with the same names.

Also add 'index' keyword, which is literally just the loop index.
This will support any other loop types in the future too.

Update VSCode Extension to match features.

Implement VSCode Extension README.md

Fix:
ScrapCompiler/simulation.py:180: error: Incompatible return value type (got "int | list[int] | dict[int,int]", expected "dict[int, int]") [return-value]
ScrapCompiler/simulation.py:373: error: Incompatible types in assignment (expression has type "int | list[int]", variable has type "int") [assignment]
ScrapCompiler/simulation.py:378: error: Incompatible types in assignment (expression has type "int | list[int]", variable has type "int") [assignment]
ScrapCompiler/compiler/spatial_allocator.py:84: error: Incompatible types in assignment (expression has type "tuple[int, int]", variable has type "int") [assignment]
ScrapCompiler/compiler/spatial_allocator.py:85: error: Argument 1 to "setdefault" of "MutableMapping" has incompatible type "int"; expected "tuple[int, int]" [arg-type]
ScrapCompiler/parser/parser.py:240: error: Incompatible types in assignment (expression has type "dict[str, Any]", variable has type "str") [assignment]
ScrapCompiler/parser/parser.py:242: error: Incompatible return value type (got "str", expected "dict[str, Any]") [return-value]
Found 7 errors in 3 files (checked 26 source files)
