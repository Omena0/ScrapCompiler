# Scrap Logic

Language support for Scrap Logic (`.logic`) files in Visual Studio Code.

## Features

- **Syntax Highlighting** for `.logic` files
- **Hover Support** for modules, variables, and gates
- **Autocompletion** for keywords, built-in gates, modules, and variables
- **Diagnostics** for parse and compilation errors
- **Compile Command** (`Ctrl+Shift+P` → `Scrap Logic: Compile Current File`)
- **Visualize Command** (`Ctrl+Shift+V`) to open the gate visualizer
- **Output Channel** for compilation logs and errors

## Requirements

- Python 3.8+
- VS Code 1.80.0+

## Extension Settings

This extension contributes the following commands:

- `scrapLogic.compile`: Compile the current `.logic` file to IR
- `scrapLogic.visualize`: Open the compiled IR in the visualizer

## Known Issues

- Hover and completion may not work if the Python bridge cannot find the ScrapCompiler binary.
- Some advanced language features (e.g., `@pipelined`, `@clocked_input`) are parsed but not yet fully implemented in the compiler.

## Release Notes

### 0.0.1

Initial release with syntax highlighting, hover, completion, diagnostics, compile, and visualize commands.
