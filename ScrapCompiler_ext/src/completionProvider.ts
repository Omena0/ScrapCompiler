import * as vscode from "vscode";
import { LogicClient, ModuleInfo } from "./logicClient";

const KEYWORDS = [
  "module",
  "inputs",
  "outputs",
  "gates",
  "dynamic",
  "buffered",
  "new",
  "as",
  "bits",
  "optional",
  "bit",
  "bool",
  "int",
  "for",
  "function",
  "in",
  "range",
  "true",
  "false",
  "#define",
];

const BUILTIN_GATES = [
  "Xor",
  "And",
  "Or",
  "Not",
  "Nand",
  "Nor",
  "Xnor",
  "Timer",
  "Lamp",
  "Switch",
  "Button",
  "ButtonInput",
  "IntInput",
  "IntDisplay",
  "Object",
];

const DECORATORS = [
  "@assert",
  "@ensure_timing",
  "@pipelined",
  "@clocked_input",
  "@clocked_output",
];

const OPERATORS = [
  "+",
  "-",
  "*",
  "/",
  "%",
  "<<",
  ">>",
  "&",
  "|",
  "^",
  "~",
  "&&",
  "||",
  "!",
  "==",
  "!=",
  "<",
  ">",
  "<=",
  ">=",
];

export class CompletionProvider implements vscode.CompletionItemProvider {
  private client: LogicClient;
  private outputChannel: vscode.OutputChannel;

  constructor(client: LogicClient, outputChannel: vscode.OutputChannel) {
    this.client = client;
    this.outputChannel = outputChannel;
  }

  public async provideCompletionItems(
    document: vscode.TextDocument,
    position: vscode.Position,
    token: vscode.CancellationToken,
    context: vscode.CompletionContext,
  ): Promise<vscode.CompletionItem[] | undefined> {
    if (document.languageId !== "logic") {
      return undefined;
    }

    this.outputChannel.appendLine(
      `[completion] providing items at line ${position.line}, col ${position.character}`,
    );

    const items: vscode.CompletionItem[] = [];
    const lineText = document.lineAt(position.line).text;
    const textBeforeCursor = lineText.substring(0, position.character);
    const prefix = this.getCurrentPrefix(textBeforeCursor);

    this.outputChannel.appendLine(
      `[completion] prefix: '${prefix}', line: '${lineText}'`,
    );

    for (const keyword of KEYWORDS) {
      const item = new vscode.CompletionItem(
        keyword,
        vscode.CompletionItemKind.Keyword,
      );
      item.detail = "Keyword";
      items.push(item);
    }
    this.outputChannel.appendLine(
      `[completion] added ${KEYWORDS.length} keywords`,
    );

    for (const gate of BUILTIN_GATES) {
      const item = new vscode.CompletionItem(
        gate,
        vscode.CompletionItemKind.Class,
      );
      item.detail = "Built-in Gate";
      items.push(item);
    }
    this.outputChannel.appendLine(
      `[completion] added ${BUILTIN_GATES.length} built-in gates`,
    );

    for (const dec of DECORATORS) {
      const item = new vscode.CompletionItem(
        dec,
        vscode.CompletionItemKind.Snippet,
      );
      item.detail = "Decorator";
      items.push(item);
    }
    this.outputChannel.appendLine(
      `[completion] added ${DECORATORS.length} decorators`,
    );

    try {
      this.outputChannel.appendLine(
        `[completion] analyzing ${document.fileName}...`,
      );
      const data = await this.client.analyze(document.fileName);
      const modules = data.modules || {};

      const moduleNames = Object.keys(modules);
      this.outputChannel.appendLine(
        `[completion] found ${moduleNames.length} modules`,
      );
      for (const moduleName of moduleNames) {
        const item = new vscode.CompletionItem(
          moduleName,
          vscode.CompletionItemKind.Module,
        );
        item.detail = "Module";
        items.push(item);
      }

      const variables = data.variables || {};
      const varNames = Object.keys(variables);
      this.outputChannel.appendLine(
        `[completion] found ${varNames.length} variables`,
      );
      for (const varName of varNames) {
        const item = new vscode.CompletionItem(
          varName,
          vscode.CompletionItemKind.Variable,
        );
        item.detail = variables[varName].type || "Variable";
        items.push(item);
      }

      if (data.functions) {
        const funcNames = Object.keys(data.functions);
        this.outputChannel.appendLine(
          `[completion] found ${funcNames.length} functions`,
        );
        for (const funcName of funcNames) {
          const item = new vscode.CompletionItem(
            funcName,
            vscode.CompletionItemKind.Function,
          );
          item.detail = "Function";
          items.push(item);
        }
      }

      const moduleInfo = this.detectModuleContext(document, position);
      if (moduleInfo) {
        const moduleData = modules[moduleInfo.name];
        if (moduleData) {
          for (const input of moduleData.inputs || []) {
            const item = new vscode.CompletionItem(
              input.name,
              vscode.CompletionItemKind.Field,
            );
            item.detail = `Input: ${input.type}`;
            items.push(item);
          }
          for (const output of moduleData.outputs || []) {
            const item = new vscode.CompletionItem(
              output.name,
              vscode.CompletionItemKind.Field,
            );
            item.detail = `Output: ${output.type}`;
            items.push(item);
          }
        }
      }
    } catch (e) {
      this.outputChannel.appendLine(`[completion] analysis error: ${e}`);
    }

    for (const op of OPERATORS) {
      if (prefix && !op.startsWith(prefix)) {
        continue;
      }
      if (!this.isExpressionContext(textBeforeCursor)) {
        continue;
      }
      const item = new vscode.CompletionItem(
        op,
        vscode.CompletionItemKind.Operator,
      );
      item.detail = "Operator";
      items.push(item);
    }

    const opCount = items.filter(
      (i) => i.kind === vscode.CompletionItemKind.Operator,
    ).length;
    this.outputChannel.appendLine(
      `[completion] added ${opCount} operators (expression context: ${this.isExpressionContext(textBeforeCursor)})`,
    );

    this.outputChannel.appendLine(
      `[completion] returning ${items.length} total items`,
    );
    return items;
  }

  private getCurrentPrefix(text: string): string {
    const match = text.match(/([a-zA-Z0-9_+\-*/%<>&|^~!]=?|>=|<=|&&|\|\|)$/);
    return match ? match[1] : "";
  }

  private isExpressionContext(textBeforeCursor: string): boolean {
    const trimmed = textBeforeCursor.trimEnd();
    if (!trimmed) {
      return false;
    }

    const lastChar = trimmed[trimmed.length - 1];
    const lastToken = trimmed.split(/\s+/).pop() || "";

    const expressionEndTokens = new Set([
      ")",
      "]",
      ".",
      ",",
      "+",
      "-",
      "*",
      "/",
      "%",
      "<<",
      ">>",
      "&",
      "|",
      "^",
      "&&",
      "||",
      "!",
      "~",
      "=",
      "==",
      "!=",
      "<",
      ">",
      "<=",
      ">=",
      "true",
      "false",
    ]);

    if (expressionEndTokens.has(lastToken)) {
      return true;
    }

    if (/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(lastToken)) {
      return true;
    }

    if (/^0x[0-9a-fA-F]+$|^0b[01]+$|^\d+$/.test(lastToken)) {
      return true;
    }

    return (
      lastChar === ")" ||
      lastChar === "]" ||
      lastChar === "." ||
      lastChar === "," ||
      lastChar === "+" ||
      lastChar === "-" ||
      lastChar === "*" ||
      lastChar === "/" ||
      lastChar === "%" ||
      lastChar === "&" ||
      lastChar === "|" ||
      lastChar === "^" ||
      lastChar === "!" ||
      lastChar === "~" ||
      lastChar === "=" ||
      lastChar === ">"
    );
  }

  private detectModuleContext(
    document: vscode.TextDocument,
    position: vscode.Position,
  ): { name: string } | undefined {
    const text = document.getText();
    const lines = text.split("\n");

    let depth = 0;
    let currentModule: string | undefined;

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();

      if (line.startsWith("module ")) {
        const match = line.match(/module\s+([a-zA-Z_][a-zA-Z0-9_]*)/);
        if (match) {
          currentModule = match[1];
        }
      }

      if (line.includes("{")) {
        depth++;
      }
      if (line.includes("}")) {
        depth--;
        if (depth === 0) {
          currentModule = undefined;
        }
      }

      if (i === position.line && currentModule && depth > 0) {
        return { name: currentModule };
      }
    }

    return undefined;
  }
}
