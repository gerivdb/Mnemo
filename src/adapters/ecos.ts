/**
 * ECOS Adapter for MNEMO
 * Enables MNEMO to work with KIVA-CLI, ECOS CLI, and KILO agent
 * 
 * This adapter allows MNEMO to:
 * - Save/load context from KIVA-CLI sessions
 * - Work with ECOS CLI (PowerShell)
 * - Integrate with KILO agent
 * 
 * @author ECOS Team
 * @date 2026-04-15
 */

import { EventEmitter } from 'events';
import * as fs from 'fs';
import * as path from 'path';

export interface ECOSSession {
    sessionId: string;
    repoPath: string;
    timestamp: number;
    context: string;
    observations: Observation[];
}

export interface Observation {
    id: string;
    type: 'tool-use' | 'user-message' | 'assistant-message';
    content: string;
    timestamp: number;
}

export class ECOSAdapter extends EventEmitter {
    private storagePath: string;
    
    constructor(ecosRoot: string = process.cwd()) {
        super();
        this.storagePath = path.join(ecosRoot, '.mnemos');
        this.ensureStorage();
    }
    
    private ensureStorage(): void {
        if (!fs.existsSync(this.storagePath)) {
            fs.mkdirSync(this.storagePath, { recursive: true });
        }
    }
    
    /**
     * Save current session context
     */
    async saveContext(sessionId: string, context: string, observations: Observation[]): Promise<void> {
        const session: ECOSSession = {
            sessionId,
            repoPath: process.cwd(),
            timestamp: Date.now(),
            context,
            observations
        };
        
        const filePath = path.join(this.storagePath, `${sessionId}.json`);
        fs.writeFileSync(filePath, JSON.stringify(session, null, 2));
    }
    
    /**
     * Load session context
     */
    async loadContext(sessionId: string): Promise<ECOSSession | null> {
        const filePath = path.join(this.storagePath, `${sessionId}.json`);
        
        if (!fs.existsSync(filePath)) {
            return null;
        }
        
        const data = fs.readFileSync(filePath, 'utf-8');
        return JSON.parse(data);
    }
    
    /**
     * Search in all stored sessions
     */
    async search(query: string): Promise<ECOSSession[]> {
        const sessions: ECOSSession[] = [];
        const files = fs.readdirSync(this.storagePath);
        
        for (const file of files) {
            if (!file.endsWith('.json')) continue;
            
            const data = fs.readFileSync(path.join(this.storagePath, file), 'utf-8');
            const session: ECOSSession = JSON.parse(data);
            
            if (session.context.includes(query) || 
                session.observations.some(o => o.content.includes(query))) {
                sessions.push(session);
            }
        }
        
        return sessions;
    }
    
    /**
     * List all sessions
     */
    async listSessions(): Promise<string[]> {
        return fs.readdirSync(this.storagePath)
            .filter(f => f.endsWith('.json'))
            .map(f => f.replace('.json', ''));
    }
}

/**
 * Create ECOS adapter instance
 */
export function createECOSAdapter(ecosRoot?: string): ECOSAdapter {
    return new ECOSAdapter(ecosRoot);
}
