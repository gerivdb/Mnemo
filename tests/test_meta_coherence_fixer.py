"""Tests pour Mnemo meta_coherence_fixer."""

from src.meta_coherence_fixer import MetaCoherenceFixer, build_meta_coherence_fixer


def test_build_meta_coherence_fixer() -> None:
    instance = build_meta_coherence_fixer()
    assert isinstance(instance, MetaCoherenceFixer)


def test_health_meta_coherence_fixer() -> None:
    instance = build_meta_coherence_fixer()
    health = instance.health()
    assert health["status"] == "ok"
