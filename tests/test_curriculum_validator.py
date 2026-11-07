"""Tests pour Mnemo curriculum_validator."""

from src.curriculum_validator import CurriculumValidator, build_curriculum_validator


def test_build_curriculum_validator() -> None:
    instance = build_curriculum_validator()
    assert isinstance(instance, CurriculumValidator)


def test_health_curriculum_validator() -> None:
    instance = build_curriculum_validator()
    health = instance.health()
    assert health["status"] == "ok"
