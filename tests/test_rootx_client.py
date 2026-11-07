"""Tests pour Mnemo rootx_client."""

from src.rootx_client import RootxClient, build_rootx_client


def test_build_rootx_client() -> None:
    instance = build_rootx_client()
    assert isinstance(instance, RootxClient)


def test_health_rootx_client() -> None:
    instance = build_rootx_client()
    health = instance.health()
    assert health["status"] == "ok"
