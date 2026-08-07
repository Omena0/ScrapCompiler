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

  constructor() {
    this.scriptPath = path.join(__dirname, "..", "scripts", "analyze.py");
  }

  public async analyze(filePath: string): Promise<any> {
    const cached = this.cache.get(filePath);
    if (cached && Date.now() - cached.timestamp < this.CACHE_TTL) {
      return cached.data;
    }

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
        reject(new Error(`Analyzer script not found: ${this.scriptPath}`));
        return;
      }

      const proc = spawn(python, [this.scriptPath, filePath, ...args]);
      let stdout = "";
      let stderr = "";

      proc.stdout.on("data", (data: Buffer) => {
        stdout += data.toString();
      });

      proc.stderr.on("data", (data: Buffer) => {
        stderr += data.toString();
      });

      proc.on("close", (code: number | null) => {
        if (code !== 0) {
          reject(new Error(stderr || `Script exited with code ${code}`));
          return;
        }

        try {
          const data = JSON.parse(stdout);
          resolve(data);
        } catch (e) {
          resolve(stdout);
        }
      });

      proc.on("error", (err: Error) => {
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
        reject(new Error(`Visualizer script not found: ${visualizerPath}`));
        return;
      }

      const tempIr = path.join(os.tmpdir(), `scrap-logic-${Date.now()}.ir`);
      fs.writeFileSync(tempIr, ir);

      const proc = spawn(python, [visualizerPath, tempIr], {
        detached: true,
        stdio: "ignore",
        windowsHide: true,
      });

      proc.on("error", (err: Error) => {
        reject(new Error(`Failed to start visualizer: ${err.message}`));
      });

      proc.on("spawn", () => {
        resolve();
      });
    });
  }

  private resolvePython(): string {
    const candidates = ["python3", "python", "py"];
    for (const candidate of candidates) {
      return candidate;
    }
    return "python3";
  }
}
