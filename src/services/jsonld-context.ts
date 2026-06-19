/**
 * JSON-LD Context for Mnemo — ADR-v3-001 Neurosymbolic Protocol
 *
 * Aligné sur ADR-v3-001 : format d'échange canonique JSON-LD
 * pour les échanges neurosymboliques BRAIN ↔ NEXUS via Mnemo.
 *
 * Vocabulaire :
 * - nexus: https://github.com/gerivdb/NEXUS#
 * - ontology: https://github.com/gerivdb/ONTOLOGY#
 * - mnemo: https://github.com/gerivdb/Mnemo#
 * - schema: https://schema.org/
 */

export const MNEMO_JSONLD_CONTEXT = {
  "@vocab": "https://github.com/gerivdb/Mnemo#",
  "nexus": "https://github.com/gerivdb/NEXUS#",
  "ontology": "https://github.com/gerivdb/ONTOLOGY#",
  "schema": "https://schema.org/",
  "mnemo": "https://github.com/gerivdb/Mnemo#",

  // Entity types
  "MnemoSession": { "@id": "mnemo:Session", "@type": "@id" },
  "MnemoMemory": { "@id": "mnemo:Memory", "@type": "@id" },
  "MnemoObservation": { "@id": "mnemo:Observation", "@type": "@id" },
  "MnemoDiagnostic": { "@id": "mnemo:Diagnostic", "@type": "@id" },
  "MnemoTranscriptEvent": { "@id": "mnemo:TranscriptEvent", "@type": "@id" },

  // Common fields
  "intentHash": { "@id": "ontology:intentHash" },
  "nexusStatus": { "@id": "nexus:status" },
  "nexusVerdict": { "@id": "nexus:verdict" },

  // Session fields
  "sessionId": { "@id": "mnemo:sessionId" },
  "project": { "@id": "mnemo:project" },
  "source": { "@id": "mnemo:source" },
  "createdAt": { "@id": "schema:dateCreated", "@type": "schema:DateTime" },
  "archivedAt": { "@id": "mnemo:archivedAt", "@type": "schema:DateTime" },

  // Memory/Observation fields
  "text": { "@id": "mnemo:text" },
  "title": { "@id": "schema:headline" },
  "subtitle": { "@id": "mnemo:subtitle" },
  "type": { "@id": "mnemo:observationType" },
  "facts": { "@id": "mnemo:facts", "@container": "@list" },
  "concepts": { "@id": "mnemo:concepts", "@container": "@list" },
  "filesTouched": { "@id": "mnemo:filesTouched", "@container": "@list" },
  "narrative": { "@id": "mnemo:narrative" },
  "keywords": { "@id": "mnemo:keywords", "@container": "@list" },
  "discoveryTokens": { "@id": "mnemo:discoveryTokens", "@type": "schema:Integer" },

  // Diagnostic fields
  "severity": { "@id": "mnemo:severity" },
  "message": { "@id": "schema:description" },

  // Transcript fields
  "eventIndex": { "@id": "mnemo:eventIndex", "@type": "schema:Integer" },
  "eventType": { "@id": "mnemo:eventType" },

  // Pagination
  "limit": { "@id": "mnemo:limit", "@type": "schema:Integer" },
  "offset": { "@id": "mnemo:offset", "@type": "schema:Integer" },
  "orderBy": { "@id": "mnemo:orderBy" },
} as const;

/**
 * Base JSON-LD envelope for Mnemo responses
 */
export function createJsonLdEnvelope(data: Record<string, unknown>) {
  return {
    "@context": MNEMO_JSONLD_CONTEXT,
    ...data,
  };
}
