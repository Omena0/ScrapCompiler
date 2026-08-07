import * as vscode from 'vscode';
import { PythonBridge } from './pythonBridge';

export class HoverProvider implements vscode.HoverProvider {
    private bridge: PythonBridge;

    constructor() {
        this.bridge = new PythonBridge();
    }

    public async provideHover(
        document: vscode.TextDocument,
        position: vscode.Position,
        token: vscode.CancellationToken
    ): Promise<vscode.Hover | undefined> {
        if (document.languageId !== 'logic') {
            return undefined;
        }

        const wordRange = document.getWordRangeAtPosition(position, /[a-zA-Z_][a-zA-Z0-9_]*/);
        if (!wordRange) {
            return undefined;
        }

        const word = document.getText(wordRange);
        if (!word) {
            return undefined;
        }

        try {
            const data = await this.bridge.analyze(document.fileName);
            const info = this.lookup(data, word, document, position);
            if (!info) {
                return undefined;
            }

            const markdown = new vscode.MarkdownString();
            markdown.isTrusted = true;
            markdown.appendMarkdown(this.formatHover(word, info));
            return new vscode.Hover(markdown, wordRange);
        } catch (e) {
            // Silently ignore hover errors to avoid disrupting editing
            return undefined;
        }
    }

    private lookup(data: any, word: string, document: vscode.TextDocument, position: vscode.Position): any {
        const variables = data.variables || {};
        const modules = data.modules || {};

        if (variables[word]) {
            return { kind: 'variable', ...variables[word] };
        }

        if (modules[word]) {
            return { kind: 'module', ...modules[word] };
        }

        // Check if hovering over a module call expression
        const lineText = document.lineAt(position.line).text;
        if (lineText.includes(`new ${word}(`) || lineText.includes(`${word}(`)) {
            return { kind: 'module-call', ...modules[word] };
        }

        return undefined;
    }

    private formatHover(name: string, info: any): string {
        let md = `### ${name}\n\n`;

        if (info.kind === 'variable') {
            md += `**Type:** \`${info.type}\`\n\n`;
            md += `**Tick:** \`${info.tick}\`\n\n`;
            if (info.bits) {
                md += `**Bits:** \`${info.bits}\`\n\n`;
            }
            if (info.value !== null && info.value !== undefined) {
                md += `**Value:** \`${info.value}\`\n\n`;
            }
        } else if (info.kind === 'module' || info.kind === 'module-call') {
            md += `**Kind:** Module\n\n`;
            if (info.inputs && info.inputs.length > 0) {
                md += `**Inputs:**\n`;
                for (const input of info.inputs) {
                    md += `- \`${input.name}\`: ${input.type}`;
                    if (input.length) {
                        md += `[${input.length}]`;
                    }
                    md += `\n`;
                }
                md += `\n`;
            }
            if (info.outputs && info.outputs.length > 0) {
                md += `**Outputs:**\n`;
                for (const output of info.outputs) {
                    md += `- \`${output.name}\`: ${output.type}`;
                    if (output.length) {
                        md += `[${output.length}]`;
                    }
                    md += `\n`;
                }
                md += `\n`;
            }
        }

        return md;
    }
}
