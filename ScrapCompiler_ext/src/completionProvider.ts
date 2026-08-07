import * as vscode from 'vscode';
import { PythonBridge } from './pythonBridge';

const KEYWORDS = [
    'module', 'inputs', 'outputs', 'gates',
    'dynamic', 'buffered', 'new', 'as',
    'bit', 'bool', 'int'
];

const BUILTIN_GATES = [
    'Xor', 'And', 'Or', 'Not', 'Nand', 'Nor', 'Xnor'
];

const OPERATORS = [
    '+', '-', '*', '/', '%',
    '<<', '>>',
    '&', '|', '^', '~',
    '&&', '||', '!',
    '==', '!=', '<', '>', '<=', '>='
];

export class CompletionProvider implements vscode.CompletionItemProvider {
    private bridge: PythonBridge;

    constructor() {
        this.bridge = new PythonBridge();
    }

    public async provideCompletionItems(
        document: vscode.TextDocument,
        position: vscode.Position,
        token: vscode.CancellationToken,
        context: vscode.CompletionContext
    ): Promise<vscode.CompletionItem[] | undefined> {
        if (document.languageId !== 'logic') {
            return undefined;
        }

        const items: vscode.CompletionItem[] = [];
        const lineText = document.lineAt(position.line).text;
        const textBeforeCursor = lineText.substring(0, position.character);
        const prefix = this.getCurrentPrefix(textBeforeCursor);

        // Always offer keywords
        for (const keyword of KEYWORDS) {
            const item = new vscode.CompletionItem(keyword, vscode.CompletionItemKind.Keyword);
            item.detail = 'Keyword';
            items.push(item);
        }

        // Try to get dynamic data from the analyzer
        try {
            const data = await this.bridge.analyze(document.fileName);
            const modules = data.modules || {};

            // Module names (for `new ModuleName(` or direct references)
            for (const moduleName of Object.keys(modules)) {
                const item = new vscode.CompletionItem(moduleName, vscode.CompletionItemKind.Module);
                item.detail = 'Module';
                items.push(item);
            }

            // Variable names (for assignments and expressions)
            const variables = data.variables || {};
            for (const varName of Object.keys(variables)) {
                const item = new vscode.CompletionItem(varName, vscode.CompletionItemKind.Variable);
                item.detail = variables[varName].type || 'Variable';
                items.push(item);
            }

            // Field names if inside a module body
            const moduleInfo = this.detectModuleContext(document, position);
            if (moduleInfo) {
                const moduleData = modules[moduleInfo.name];
                if (moduleData) {
                    for (const input of moduleData.inputs || []) {
                        const item = new vscode.CompletionItem(input.name, vscode.CompletionItemKind.Field);
                        item.detail = `Input: ${input.type}`;
                        items.push(item);
                    }
                    for (const output of moduleData.outputs || []) {
                        const item = new vscode.CompletionItem(output.name, vscode.CompletionItemKind.Field);
                        item.detail = `Output: ${output.type}`;
                        items.push(item);
                    }
                }
            }
        } catch (e) {
            // Ignore analyzer errors; still offer static completions
        }

        // Operators (filter based on prefix if applicable)
        for (const op of OPERATORS) {
            if (prefix && !op.startsWith(prefix)) {
                continue;
            }
            const item = new vscode.CompletionItem(op, vscode.CompletionItemKind.Operator);
            item.detail = 'Operator';
            items.push(item);
        }

        return items;
    }

    /**
     * Extract the current token prefix before the cursor for filtering.
     */
    private getCurrentPrefix(text: string): string {
        const match = text.match(/([a-zA-Z0-9_+\-*/%<>&|^~!]=?|>=|<=|&&|\|\|)$/);
        return match ? match[1] : '';
    }

    /**
     * Detect if the cursor is inside a specific module definition body.
     * This enables context-aware field completions.
     */
    private detectModuleContext(document: vscode.TextDocument, position: vscode.Position): { name: string } | undefined {
        const text = document.getText();
        const lines = text.split('\n');

        let depth = 0;
        let currentModule: string | undefined;

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i].trim();

            if (line.startsWith('module ') && line.includes('(')) {
                const match = line.match(/module\s+([a-zA-Z_][a-zA-Z0-9_]*)/);
                if (match) {
                    currentModule = match[1];
                }
            }

            if (line.includes('{')) {
                depth++;
            }
            if (line.includes('}')) {
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
