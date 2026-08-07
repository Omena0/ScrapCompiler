import * as vscode from 'vscode';
import { HoverProvider } from './hoverProvider';
import { CompletionProvider } from './completionProvider';

export function activate(context: vscode.ExtensionContext) {
    const hoverProvider = new HoverProvider();
    const completionProvider = new CompletionProvider();

    context.subscriptions.push(
        vscode.languages.registerHoverProvider('logic', hoverProvider),
        vscode.languages.registerCompletionItemProvider('logic', completionProvider, '.', ' ')
    );

    const compileCommand = vscode.commands.registerCommand('scrapLogic.compile', () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            vscode.window.showErrorMessage('No active editor');
            return;
        }

        if (editor.document.languageId !== 'logic') {
            vscode.window.showErrorMessage('Current file is not a .logic file');
            return;
        }

        vscode.window.showInformationMessage('Scrap Logic compilation triggered (hook into your build here)');
    });

    context.subscriptions.push(compileCommand);
}

export function deactivate() {}
