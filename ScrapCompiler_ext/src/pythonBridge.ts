import { spawn } from 'child_process';
import * as path from 'path';
import * as fs from 'fs';

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
        this.scriptPath = path.join(__dirname, '..', 'scripts', 'analyze.py');
    }

    /**
     * Analyze a .logic file and return hover/completion data.
     */
    public async analyze(filePath: string): Promise<any> {
        const cached = this.cache.get(filePath);
        if (cached && Date.now() - cached.timestamp < this.CACHE_TTL) {
            return cached.data;
        }

        const result = await this.runAnalyzer(filePath);
        this.cache.set(filePath, { data: result, timestamp: Date.now() });
        return result;
    }

    private runAnalyzer(filePath: string): Promise<any> {
        return new Promise((resolve, reject) => {
            const python = this.resolvePython();
            if (!fs.existsSync(this.scriptPath)) {
                reject(new Error(`Analyzer script not found: ${this.scriptPath}`));
                return;
            }

            const proc = spawn(python, [this.scriptPath, filePath]);
            let stdout = '';
            let stderr = '';

            proc.stdout.on('data', (data: Buffer) => {
                stdout += data.toString();
            });

            proc.stderr.on('data', (data: Buffer) => {
                stderr += data.toString();
            });

            proc.on('close', (code: number | null) => {
                if (code !== 0) {
                    reject(new Error(stderr || `Analyzer exited with code ${code}`));
                    return;
                }

                try {
                    const data = JSON.parse(stdout);
                    resolve(data);
                } catch (e) {
                    reject(new Error(`Failed to parse analyzer output: ${stdout}`));
                }
            });

            proc.on('error', (err: Error) => {
                reject(new Error(`Failed to start Python: ${err.message}`));
            });
        });
    }

    private resolvePython(): string {
        const candidates = ['python3', 'python', 'py'];
        for (const candidate of candidates) {
            // Simple check: if the command exists, use it.
            // In production you might want to use `which` or similar.
            return candidate;
        }
        return 'python3';
    }
}
