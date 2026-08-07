
# todo

Split compiler.py into multiple files and even subfolders if apropriate.

Clean up the code while you move parts into other files.

fix the blueprint generation. its completely fucked.
logic gates cant have a "bounds": {}. bounds is the width/height/depth of it
If you arent sure about the blueprint syntax then look it up.

create launch.json for extension debug and fix the extension rn it crashes with Activating extension 'undefined_publisher.scrap-logic' failed: Cannot find module '/home/omena0/Github/ScrapCompiler/ScrapCompiler_ext/out/extension.js' Require stack: - /usr/share/code-insiders/resources/app/out/vs/workbench/api/node/extensionHostProcess.js.

Also in the simulation for each IntInput in the thing, either prompt the user when they run it or take from sys argv if available.
And in the visualizer add support for buttons lamps and switches. also draw them as half height blocks.

Also implement functions. Functions are like modules but they just contain gates, functions cant be used with the new keyword. When calling a function it will just emit whatever gates are inside it. its kinda like a macro.

Also here are the shape IDs for the blueprint generation again:
logic gate: 9f0f56e8-2c31-4d83-996c-d00a9b296c3f
switch: 7cf717d7-d167-4f2d-a6e7-6b2c70aa3986
shack light: ebefa387-fe4a-4839-bdd9-b6b4da39368f
timer: 8f7fd0e7-c46e-4944-a414-7ce2437bb30f
button: 1e8d93a4-506b-470d-9ada-9c0a321e2db5

Timer will come next so you might as well add the uuid constant to the ir_to_blueprint.py file.

Also make error handling better by adding range support not just an exact column.
Add with stream.range() which automatically adds range info to stream.emit()

Fix the spatial allocator, its not working at all. Make a bunch of tests for the spatial allocator (e.g. making sure bits of the same value are on the same xz pos etc. etc.)

Remove 'buffered' value support entirely.

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
