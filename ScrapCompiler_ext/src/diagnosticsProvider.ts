import * as vscode from "vscode";
import { LogicClient, AnalysisResult } from "./logicClient";

export class DiagnosticsProvider {
  private client: LogicClient;
  private diagnosticCollection: vscode.DiagnosticCollection;

  constructor(client: LogicClient) {
    this.client = client;
    this.diagnosticCollection =
      vscode.languages.createDiagnosticCollection("logic");
  }

  public activate(): void {
    vscode.workspace.onDidChangeTextDocument((event) => {
      if (event.document.languageId === "logic") {
        this.updateDiagnostics(event.document);
      }
    });

    vscode.workspace.onDidOpenTextDocument((document) => {
      if (document.languageId === "logic") {
        this.updateDiagnostics(document);
      }
    });
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
    } catch (e) {
      // Ignore analysis errors
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
