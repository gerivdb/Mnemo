"""Tests pour Mnemo narrative_generator."""

from src.narrative_generator import NarrativeGenerator, build_narrative_generator


def test_build_narrative_generator() -> None:
    instance = build_narrative_generator()
    assert isinstance(instance, NarrativeGenerator)


def test_health_narrative_generator() -> None:
    instance = build_narrative_generator()
    health = instance.health()
    assert health["status"] == "ok"
