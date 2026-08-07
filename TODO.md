# todo

Add VSCode extension output log, and a ton of logging to it.
Since rn hovers and some other things dont work i think something is crashing or it cant find a binary or smth.

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

Also add 'index' keyword, which is literally just the loop index.
This will support any other loop types in the future too.

Update VSCode Extension to match features.

Implement VSCode Extension README.md
