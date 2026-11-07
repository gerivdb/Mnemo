"""Tests pour Mnemo causal_validator."""

from src.causal_validator import CausalValidator, build_causal_validator


def test_build_causal_validator() -> None:
    instance = build_causal_validator()
    assert isinstance(instance, CausalValidator)


def test_health_causal_validator() -> None:
    instance = build_causal_validator()
    health = instance.health()
    assert health["status"] == "ok"
