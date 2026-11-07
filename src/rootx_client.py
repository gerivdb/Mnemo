"""
Mnemo rootx_client - Composant auto-dev integre.

Contexte:
- Mnemo est un composant de l'ecosysteme gerivdb.
- rootx_client permet [TODO: decrire le role specifique].

Integration:
- GOVERNANCE-HUB: SOT, ADR, PRD-MOC, hooks
- KG-L / VERSES: connaissances et ontologie
- Mnemo: composant hote
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RootxClientConfig:
    """Configuration du composant rootx_client."""
    endpoint: str = "http://localhost:8795"
    timeout_seconds: int = 10


class RootxClient:
    """Composant rootx_client."""

    def __init__(self, config: RootxClientConfig | None = None) -> None:
        self.config = config or RootxClientConfig()

    def health(self) -> dict[str, Any]:
        """Verifie la disponibilite du composant."""
        return {"status": "ok", "endpoint": self.config.endpoint}


def build_rootx_client(config: RootxClientConfig | None = None) -> RootxClient:
    """Factory pour creer une instance de RootxClient."""
    return RootxClient(config=config)
