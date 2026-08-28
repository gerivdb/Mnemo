---
id: ATOM-065
name: RLM-243 – Recursive Ternary Memory
type: ARCHITECTURE
strate: L2 (Cognition & Logique Ternaire)
substrate: Compréhension contextuelle
status: ACTIV
version: v1.0.0
intent_hash: 0xRLM243_CANON_20260724
conforms_to: NEXUS, BRAIN, CTULU
---

# RLM-243 – Spécification Canonique

## Définition
Moteur d'inférence récurrente ternaire (Trit-based RNN Engine).
Compresse séquentiellement des flux de tokens (jusqu'à 1M) en un état latent de 81 trits (`{-1,0,+1}`³), déroulé sur 3 pas temporels (`h0 → h1 → h2`).
Pas de stockage vectoriel, pas de similarité, pas d'embedding flottant.

## Nature
State-Space Model ternaire (SSM-like), proche de Mamba/RWKV pour la récurrence, mais :
- **Sans multiplication** (uniquement `_mm_sign_epi8` + additions SSE4.2),
- **Poids partagés** (W, U, b) → complexité O(N) stricte,
- **État discret** : 81 trits → 3⁸¹ états théoriques.

## Invariants
- 243 neurones = 3 × 81 (déroulé temporel).
- Pas d'attention, pas de matrice de similarité.

## Intégration dans le DAG
Tokens (1M) → RLM-243 (h₂) → HOLMES (validation causale) → HERMES (vectorisation + persistance)
                                                         ↓
                                                    PLIX / NEXUS (WAL + IntentHash)

## Rôle
Compresseur sémantique amont. Alimente HERMES (moteur vectoriel) et HOLMES (moteur causal) en états sémantiques validés.

## Références
- ADR-003 (Inférence Ternaire)
- ADR-007 (Intégration DAG-3)
- Dépôt KEEL, Mnemo, HERMES, HOLMES, FLUENCE, CTULU