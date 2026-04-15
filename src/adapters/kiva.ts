/**
 * KIVA-CLI Adapter for MNEMO
 * Enables MNEMO to work specifically with KIVA-CLI
 * 
 * KIVA-CLI is our Python CLI for multi-repo management
 * This adapter integrates memory functionality directly with KIVA
 * 
 * @author ECOS Team
 * @date 2026-04-15
 */

import { spawn, execSync } from 'child_process';
import * as path from 'path';
import * as fs from 'fs';

export interface KIVASession {
    sessionId: string;
    workingDir: string;
    timestamp: number;
    commands: string[];
    output: string[];
}

export class KIVAAdapter {
    private mnemosDir: string;
    
    constructor(kivaRoot?: string) {
        this.mnemosDir = path.join(kivaRoot || process.cwd(), '.kiva-mnemos');
        this.ensureDir();
    }
    
    private ensureDir(): void {
        if (!fs.existsSync(this.mnemosDir)) {
            fs.mkdirSync(this.mnemosDir, { recursive: true });
        }
    }
    
    /**
     * Run a KIVA-CLI command and capture output for memory
     */
    async runCommand(cmd: string, args: string[]): Promise<KIVASession> {
        const sessionId = `kiva-${Date.now()}`;
        
        return new Promise((resolve) => {
            const output: string[] = [];
            const proc = spawn(cmd, args, { shell: true });
            
            proc.stdout.on('data', (data) => {
                output.push(data.toString());
            });
            
            proc.stderr.on('data', (data) => {
                output.push(data.toString());
            });
            
            proc.on('close', () => {
                const session: KIVASession = {
                    sessionId,
                    workingDir: process.cwd(),
                    timestamp: Date.now(),
                    commands: [cmd, ...args],
                    output
                };
                
                this.saveSession(session);
                resolve(session);
            });
        });
    }
    
    /**
     * Save KIVA session to memory
     */
    private saveSession(session: KIVASession): void {
        const filePath = path.join(this.mnemosDir, `${session.sessionId}.json`);
        fs.writeFileSync(filePath, JSON.stringify(session, null, 2));
    }
    
    /**
     * Get all KIVA sessions
     */
    getSessions(): KIVASession[] {
        return fs.readdirSync(this.mnemosDir)
            .filter(f => f.endsWith('.json'))
            .map(f => {
                const data = fs.readFileSync(path.join(this.mnemosDir, f), 'utf-8');
                return JSON.parse(data);
            });
    }
    
    /**
     * Search in KIVA command history
     */
    searchHistory(query: string): KIVASession[] {
        return this.getSessions().filter(s => 
            s.commands.some(c => c.includes(query)) ||
            s.output.some(o => o.includes(query))
        );
    }
}

/**
 * Create KIVA adapter instance
 */
export function createKIVAAdapter(kivaRoot?: string): KIVAAdapter {
    return new KIVAAdapter(kivaRoot);
}
