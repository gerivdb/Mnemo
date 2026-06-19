/**
 * Memory Routes
 *
 * Handles manual memory/observation saving.
 * POST /api/memory/save - Save a manual memory observation
 * GET /api/memory/jsonld - List observations in JSON-LD format (ADR-v3-001)
 */

import express, { Request, Response } from 'express';
import { BaseRouteHandler } from '../BaseRouteHandler.js';
import { logger } from '../../../../utils/logger.js';
import { memoryRowToJsonLd, observationRowToJsonLd } from '../../../../sqlite/types.js';
import type { DatabaseManager } from '../../DatabaseManager.js';

export class MemoryRoutes extends BaseRouteHandler {
  constructor(
    private dbManager: DatabaseManager,
    private defaultProject: string
  ) {
    super();
  }

  setupRoutes(app: express.Application): void {
    app.post('/api/memory/save', this.handleSaveMemory.bind(this));
    app.get('/api/memory/jsonld', this.handleGetJsonLd.bind(this));
  }

  /**
   * GET /api/memory/jsonld — List observations in JSON-LD format (ADR-v3-001)
   * Query: ?project=&limit=50&offset=0&query=
   */
  private handleGetJsonLd = this.wrapHandler(async (req: Request, res: Response): Promise<void> => {
    const project = (req.query.project as string) || this.defaultProject;
    const limit = Math.min(parseInt(req.query.limit as string) || 50, 200);
    const offset = parseInt(req.query.offset as string) || 0;
    const query = (req.query.query as string) || undefined;

    const searchResults = this.dbManager.getSessionSearch().searchObservations(query, {
      project,
      limit,
      offset,
      orderBy: "date_desc",
    });

    const jsonLdEntries = searchResults.map((row) =>
      observationRowToJsonLd(row as unknown as Parameters<typeof observationRowToJsonLd>[0])
    );

    res.json({
      "@context": "https://github.com/gerivdb/Mnemo#",
      "@type": "Collection",
      "total": jsonLdEntries.length,
      "project": project,
      ...(query && { "query": query }),
      "members": jsonLdEntries,
    });
  });

  /**
   * POST /api/memory/save - Save a manual memory/observation
   * Body: { text: string, title?: string, project?: string }
   */
  private handleSaveMemory = this.wrapHandler(async (req: Request, res: Response): Promise<void> => {
    const { text, title, project } = req.body;
    const targetProject = project || this.defaultProject;

    if (!text || typeof text !== 'string' || text.trim().length === 0) {
      this.badRequest(res, 'text is required and must be non-empty');
      return;
    }

    const sessionStore = this.dbManager.getSessionStore();
    const chromaSync = this.dbManager.getChromaSync();

    // 1. Get or create manual session for project
    const memorySessionId = sessionStore.getOrCreateManualSession(targetProject);

    // 2. Build observation
    const observation = {
      type: 'discovery',  // Use existing valid type
      title: title || text.substring(0, 60).trim() + (text.length > 60 ? '...' : ''),
      subtitle: 'Manual memory',
      facts: [] as string[],
      narrative: text,
      concepts: [] as string[],
      files_read: [] as string[],
      files_modified: [] as string[]
    };

    // 3. Store to SQLite
    const result = sessionStore.storeObservation(
      memorySessionId,
      targetProject,
      observation,
      0,  // promptNumber
      0   // discoveryTokens
    );

    logger.info('HTTP', 'Manual observation saved', {
      id: result.id,
      project: targetProject,
      title: observation.title
    });

    // 4. Sync to ChromaDB (async, fire-and-forget)
    chromaSync.syncObservation(
      result.id,
      memorySessionId,
      targetProject,
      observation,
      0,
      result.createdAtEpoch,
      0
    ).catch(err => {
      logger.error('CHROMA', 'ChromaDB sync failed', { id: result.id }, err as Error);
    });

    // 5. Return success
    res.json({
      success: true,
      id: result.id,
      title: observation.title,
      project: targetProject,
      message: `Memory saved as observation #${result.id}`
    });
  });
}
