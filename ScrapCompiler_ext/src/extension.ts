import * as vscode from "vscode";
import { LogicClient } from "./logicClient";
import { HoverProvider } from "./hoverProvider";
import { CompletionProvider } from "./completionProvider";
import { DiagnosticsProvider } from "./diagnosticsProvider";

export function activate(context: vscode.ExtensionContext) {
  const client = new LogicClient();
  const outputChannel = vscode.window.createOutputChannel("Scrap Logic");

  context.subscriptions.push(outputChannel);

  const hoverProvider = new HoverProvider(client);
  const completionProvider = new CompletionProvider(client);
  const diagnosticsProvider = new DiagnosticsProvider(client);

  context.subscriptions.push(
    vscode.languages.registerHoverProvider("logic", hoverProvider),
    vscode.languages.registerCompletionItemProvider(
      "logic",
      completionProvider,
      ".",
      " ",
    ),
  );

  diagnosticsProvider.activate();
  context.subscriptions.push({
    dispose: () => diagnosticsProvider.dispose(),
  });

  const compileCommand = vscode.commands.registerCommand(
    "scrapLogic.compile",
    async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor) {
        vscode.window.showErrorMessage("No active editor");
        return;
      }

      if (editor.document.languageId !== "logic") {
        vscode.window.showErrorMessage("Current file is not a .logic file");
        return;
      }

      outputChannel.clear();
      outputChannel.show(true);

      try {
        const ir = await client.compile(editor.document.fileName);
        outputChannel.appendLine("Compilation successful");
        const outputUri = editor.document.uri.with({
          path: editor.document.uri.path + ".ir",
        });
        const encoder = new TextEncoder();
        const edit = new vscode.WorkspaceEdit();
        edit.createFile(outputUri, { overwrite: true });
        edit.insert(outputUri, new vscode.Position(0, 0), ir);
        await vscode.workspace.applyEdit(edit);
        await vscode.window.showTextDocument(outputUri);
        vscode.window.showInformationMessage("Compilation successful");
      } catch (e: any) {
        const message = e.message || "Compilation failed";
        outputChannel.appendLine(`Error: ${message}`);
        vscode.window.showErrorMessage(`Compilation failed: ${message}`);
      }
    },
  );

  const visualizeCommand = vscode.commands.registerCommand(
    "scrapLogic.visualize",
    async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor) {
        vscode.window.showErrorMessage("No active editor");
        return;
      }

      if (editor.document.languageId !== "logic") {
        vscode.window.showErrorMessage("Current file is not a .logic file");
        return;
      }

      try {
        await vscode.window.withProgress(
          {
            location: vscode.ProgressLocation.Notification,
            title: "Opening visualizer...",
            cancellable: false,
          },
          async () => {
            await client.visualize(editor.document.fileName);
          },
        );
      } catch (e: any) {
        vscode.window.showErrorMessage(
          `Failed to open visualizer: ${e.message}`,
        );
      }
    },
  );

  context.subscriptions.push(compileCommand, visualizeCommand);
}

export function deactivate() {}
