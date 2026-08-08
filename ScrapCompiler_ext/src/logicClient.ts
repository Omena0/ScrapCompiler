import * as vscode from "vscode";
import { PythonBridge } from "./pythonBridge";

export interface VariableInfo {
  type: string;
  tick: number;
  bits: string;
  value: number | null;
}

export interface ModuleField {
  name: string;
  type: string;
  length: number | string | null;
}

export interface ModuleInfo {
  inputs: ModuleField[];
  outputs: ModuleField[];
}

export interface AnalysisResult {
  variables: Record<string, VariableInfo>;
  modules: Record<string, ModuleInfo>;
  functions: Record<string, any>;
  errors: string[];
}

export class LogicClient {
  private bridge: PythonBridge;
  private cache: Map<string, { data: AnalysisResult; timestamp: number }> =
    new Map();
  private readonly CACHE_TTL = 5000;

  constructor(outputChannel: vscode.OutputChannel) {
    this.bridge = new PythonBridge(outputChannel);
  }

  public async analyze(filePath: string): Promise<AnalysisResult> {
    const cached = this.cache.get(filePath);
    if (cached && Date.now() - cached.timestamp < this.CACHE_TTL) {
      return cached.data;
    }

    const data = await this.bridge.analyze(filePath);
    const result: AnalysisResult = {
      variables: data.variables || {},
      modules: data.modules || {},
      functions: data.functions || {},
      errors: data.errors
        ? Array.isArray(data.errors)
          ? data.errors
          : [data.errors]
        : [],
    };

    this.cache.set(filePath, { data: result, timestamp: Date.now() });
    return result;
  }

  public async compile(filePath: string): Promise<string> {
    return this.bridge.compile(filePath);
  }

  public async visualize(filePath: string): Promise<void> {
    return this.bridge.visualize(filePath);
  }
}
