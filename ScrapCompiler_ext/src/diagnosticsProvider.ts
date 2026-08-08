import * as vscode from "vscode";
import { LogicClient, AnalysisResult } from "./logicClient";

export class DiagnosticsProvider {
  private client: LogicClient;
  private diagnosticCollection: vscode.DiagnosticCollection;
  private outputChannel: vscode.OutputChannel;

  constructor(client: LogicClient, outputChannel: vscode.OutputChannel) {
    this.client = client;
    this.outputChannel = outputChannel;
    this.diagnosticCollection =
      vscode.languages.createDiagnosticCollection("logic");
  }

  public activate(): void {
    vscode.workspace.onDidChangeTextDocument((event) => {
      if (event.document.languageId === "logic") {
        this.outputChannel.appendLine(
          `[diagnostics] document changed: ${event.document.fileName}`,
        );
        this.updateDiagnostics(event.document);
      }
    });

    vscode.workspace.onDidOpenTextDocument((document) => {
      if (document.languageId === "logic") {
        this.outputChannel.appendLine(
          `[diagnostics] document opened: ${document.fileName}`,
        );
        this.updateDiagnostics(document);
      }
    });
  }

  public getDiagnosticCollection(): vscode.DiagnosticCollection {
    return this.diagnosticCollection;
  }

  private async updateDiagnostics(
    document: vscode.TextDocument,
  ): Promise<void> {
    try {
      const result = await this.client.analyze(document.fileName);
      const diagnostics: vscode.Diagnostic[] = [];

      for (const error of result.errors) {
        const diagnostic = this.createDiagnostic(error, document);
        if (diagnostic) {
          diagnostics.push(diagnostic);
        }
      }

      this.diagnosticCollection.set(document.uri, diagnostics);
      this.outputChannel.appendLine(
        `[diagnostics] set ${diagnostics.length} diagnostics for ${document.fileName}`,
      );
    } catch (e) {
      this.outputChannel.appendLine(`[diagnostics] error: ${e}`);
    }
  }

  private createDiagnostic(
    error: string,
    document: vscode.TextDocument,
  ): vscode.Diagnostic | undefined {
    const match = error.match(/At line (\d+), col (\d+)/);
    if (!match) {
      const range = new vscode.Range(0, 0, document.lineCount, 0);
      return new vscode.Diagnostic(
        range,
        error,
        vscode.DiagnosticSeverity.Error,
      );
    }

    const line = parseInt(match[1]) - 1;
    const col = parseInt(match[2]) - 1;
    const range = new vscode.Range(line, col, line, col + 1);

    return new vscode.Diagnostic(range, error, vscode.DiagnosticSeverity.Error);
  }

  public dispose(): void {
    this.diagnosticCollection.dispose();
  }
}
