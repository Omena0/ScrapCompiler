# todo

Add timer block support. In the IR just call it TIMER.
First arg is the delay and the second is the input.
A timer is equivalent to n-1 OR gates in a chain.
n-1 because the timer itself has a 1 tick delay.
A timer block delays the signal sent to it by n+1 ticks, where n is the delay arg.
timer block blueprint json syntax. Only use ticks and leave seconds at 0.

```json
{
  // SHAPE 1 ID:12472
  "color": "DF7F01",
  "controller": {
    "active": false,
    "id": 10442,
    "seconds": 0,
    "ticks": 0
  },
  "pos": {
    "x": -1,
    "y": -13,
    "z": 0
  },
  "shapeId": "8f7fd0e7-c46e-4944-a414-7ce2437bb30f", // Timer
  "xaxis": 1,
  "zaxis": -2
}
```

Also make sure blueprint generation works.

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
