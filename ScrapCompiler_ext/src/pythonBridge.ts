import * as vscode from "vscode";
import { spawn } from "child_process";
import * as path from "path";
import * as fs from "fs";
import * as os from "os";

/**
 * Bridge to the ScrapCompiler Python runtime.
 *
 * All compiler-specific knowledge lives in `analyze.py`. To add new
 * language features or hover data, update that script and the grammar;
 * this file only handles process communication.
 */
export class PythonBridge {
  private scriptPath: string;
  private cache: Map<string, { data: any; timestamp: number }> = new Map();
  private readonly CACHE_TTL = 5000;
  private outputChannel: vscode.OutputChannel;

  constructor(outputChannel: vscode.OutputChannel) {
    this.scriptPath = path.join(__dirname, "..", "scripts", "analyze.py");
    this.outputChannel = outputChannel;
  }

  public async analyze(filePath: string): Promise<any> {
    const cached = this.cache.get(filePath);
    if (cached && Date.now() - cached.timestamp < this.CACHE_TTL) {
      this.outputChannel.appendLine(`[bridge] cache hit for ${filePath}`);
      return cached.data;
    }

    this.outputChannel.appendLine(`[bridge] analyzing ${filePath}...`);
    const result = await this.runAnalyzer(filePath);
    this.cache.set(filePath, { data: result, timestamp: Date.now() });
    return result;
  }

  public async compile(filePath: string): Promise<string> {
    return this.runScript(filePath, ["compile"]);
  }

  public async visualize(filePath: string): Promise<void> {
    const ir = await this.compile(filePath);
    await this.launchVisualizer(ir);
  }

  private async runAnalyzer(filePath: string): Promise<any> {
    return this.runScript(filePath, ["analyze"]);
  }

  private runScript(filePath: string, args: string[]): Promise<any> {
    return new Promise((resolve, reject) => {
      const python = this.resolvePython();
      if (!fs.existsSync(this.scriptPath)) {
        const err = new Error(`Analyzer script not found: ${this.scriptPath}`);
        this.outputChannel.appendLine(`[bridge] ${err.message}`);
        reject(err);
        return;
      }

      this.outputChannel.appendLine(
        `[bridge] running: ${python} ${this.scriptPath} ${filePath} ${args.join(" ")}`,
      );
      const proc = spawn(python, [this.scriptPath, filePath, ...args]);
      let stdout = "";
      let stderr = "";

      proc.stdout.on("data", (data: Buffer) => {
        stdout += data.toString();
      });

      proc.stderr.on("data", (data: Buffer) => {
        stderr += data.toString();
        this.outputChannel.appendLine(`[bridge] stderr: ${data.toString()}`);
      });

      proc.on("close", (code: number | null) => {
        if (code !== 0) {
          const err = new Error(stderr || `Script exited with code ${code}`);
          this.outputChannel.appendLine(
            `[bridge] script failed: ${err.message}`,
          );
          reject(err);
          return;
        }

        this.outputChannel.appendLine(
          `[bridge] script succeeded, stdout length: ${stdout.length}`,
        );
        try {
          const data = JSON.parse(stdout);
          resolve(data);
        } catch (e) {
          this.outputChannel.appendLine(
            `[bridge] stdout was not JSON, returning raw text`,
          );
          resolve(stdout);
        }
      });

      proc.on("error", (err: Error) => {
        this.outputChannel.appendLine(
          `[bridge] failed to start Python: ${err.message}`,
        );
        reject(new Error(`Failed to start Python: ${err.message}`));
      });
    });
  }

  private async launchVisualizer(ir: string): Promise<void> {
    return new Promise((resolve, reject) => {
      const python = this.resolvePython();
      const visualizerPath = path.join(
        __dirname,
        "..",
        "..",
        "..",
        "..",
        "ScrapCompiler",
        "visualize.py",
      );

      if (!fs.existsSync(visualizerPath)) {
        const err = new Error(`Visualizer script not found: ${visualizerPath}`);
        this.outputChannel.appendLine(`[bridge] ${err.message}`);
        reject(err);
        return;
      }

      const tempIr = path.join(os.tmpdir(), `scrap-logic-${Date.now()}.ir`);
      fs.writeFileSync(tempIr, ir);

      this.outputChannel.appendLine(
        `[bridge] launching visualizer with ${tempIr}`,
      );
      const proc = spawn(python, [visualizerPath, tempIr], {
        detached: true,
        stdio: "ignore",
        windowsHide: true,
      });

      proc.on("error", (err: Error) => {
        this.outputChannel.appendLine(
          `[bridge] failed to start visualizer: ${err.message}`,
        );
        reject(new Error(`Failed to start visualizer: ${err.message}`));
      });

      proc.on("spawn", () => {
        this.outputChannel.appendLine(
          "[bridge] visualizer launched successfully",
        );
        resolve();
      });
    });
  }

  private resolvePython(): string {
    const candidates = ["python3", "python", "py"];
    const found = candidates.find((candidate) => {
      try {
        const { execSync } = require("child_process");
        execSync(`${candidate} --version`, { stdio: "ignore" });
        return true;
      } catch {
        return false;
      }
    });
    const python = found || "python3";
    this.outputChannel.appendLine(`[bridge] resolved Python: ${python}`);
    return python;
  }
}
