"""
Tests pour mnemo_core.py et mnemo_kg_sync.py

IntentHash: 0xMNEMO_TESTS_20260828
"""
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.mnemo.mnemo_core import (
    MnemoCore, MemoryEntry, MemoryTier, Provenance, Operation,
    MemoryWrite, MemoryRead, MemoryTier, create_mnemo_core,
)


def test_basic_set_get():
    """Test set/get basique."""
    mnemo = MnemoCore()
    result = mnemo.set("test:key", "test_value", provenance="HUMAN")
    assert result["success"] is True
    
    value = mnemo.get("test:key")
    assert value == "test_value"
    print("✓ test_basic_set_get passed")


def test_tier_management():
    """Test promotion hot → warm → cold."""
    mnemo = MnemoCore()
    mnemo.set("tier:test", "value", tier="hot")
    
    # Vérifier HOT
    assert "tier:test" in mnemo._hot_cache
    assert mnemo._hot_cache["tier:test"].tier == MemoryTier.HOT
    
    # Promote to warm
    mnemo.promote_to_warm("tier:test")
    assert "tier:test" not in mnemo._hot_cache
    assert "tier:test" in mnemo._warm_cache
    assert mnemo._warm_cache["tier:test"].tier == MemoryTier.WARM
    
    # Promote to cold
    mnemo.promote_to_cold("tier:test")
    assert "tier:test" not in mnemo._warm_cache
    # Note: cold tier is virtual (KG-L), pas de storage local
    
    print("✓ test_tier_management passed")


def test_ttl_expiration():
    """Test expiration TTL."""
    mnemo = MnemoCore(hot_ttl=1)  # 1 seconde
    mnemo.set("ttl:test", "value", tier="hot")
    
    # Immédiat: présent
    assert mnemo.get("ttl:test") == "value"
    
    # Attendre expiration
    time.sleep(1.5)
    
    # Après expiration: absent
    assert mnemo.get("ttl:test") is None
    print("✓ test_ttl_expiration passed")


def test_lru_eviction():
    """Test éviction LRU quand max_entries atteint."""
    mnemo = MnemoCore(max_entries=3)
    
    mnemo.set("key1", "v1")
    mnemo.set("key2", "v2")
    mnemo.set("key3", "v3")
    assert len(mnemo._hot_cache) == 3
    
    # Ajouter 4ème → éviction key1 (LRU)
    mnemo.set("key4", "v4")
    assert len(mnemo._hot_cache) == 3
    assert "key1" not in mnemo._hot_cache
    assert "key4" in mnemo._hot_cache
    print("✓ test_lru_eviction passed")


def test_provenance_tracking():
    """Test tracking provenance."""
    mnemo = MnemoCore()
    mnemo.set("prov:human", "v1", provenance="HUMAN")
    mnemo.set("prov:brain", "v2", provenance="BRAIN")
    mnemo.set("prov:mnemo", "v3", provenance="MNEMO")
    
    # Query by provenance
    human_entries = mnemo.query({"provenance": "HUMAN"})
    brain_entries = mnemo.query({"provenance": "BRAIN"})
    mnemo_entries = mnemo.query({"provenance": "MNEMO"})
    
    assert len(human_entries) == 1
    assert len(brain_entries) == 1
    assert len(mnemo_entries) == 1
    print("✓ test_provenance_tracking passed")


def test_tag_query():
    """Test query par tags."""
    mnemo = MnemoCore()
    mnemo.set("tag:a", "v1", tags=["fact", "identity"])
    mnemo.set("tag:b", "v2", tags=["fact"])
    mnemo.set("tag:c", "v3", tags=["skill"])
    
    fact_entries = mnemo.query({"tags": ["fact"]})
    identity_entries = mnemo.query({"tags": ["identity"]})
    skill_entries = mnemo.query({"tags": ["skill"]})
    
    assert len(fact_entries) == 2
    assert len(identity_entries) == 1
    assert len(skill_entries) == 1
    print("✓ test_tag_query passed")


def test_link_relations():
    """Test création de liens entre entrées."""
    mnemo = MnemoCore()
    mnemo.set("rel:a", "value_a")
    mnemo.set("rel:b", "value_b")
    
    # Create link
    from src.mnemo.mnemo_core import MemoryWrite, Operation, Provenance
    mw = MemoryWrite(
        operation=Operation.LINK,
        domain="test",
        payload={"source": "rel:a", "target": "rel:b", "relation": "causes"},
        provenance=Provenance.HUMAN,
    )
    result = mnemo.write(mw)
    assert result["success"] is True
    
    # Vérifier relation dans metadata
    entry_a = mnemo._hot_cache["rel:a"]
    assert "relations" in entry_a.metadata
    assert any(r["target"] == "rel:b" and r["relation"] == "causes" 
               for r in entry_a.metadata["relations"])
    print("✓ test_link_relations passed")


def test_persistence():
    """Test sauvegarde/chargement persistance."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        persist_path = f.name
    
    try:
        mnemo = MnemoCore(persistence_path=persist_path)
        mnemo.set("persist:key", "persist_value", provenance="HUMAN")
        mnemo.save_persistence()
        
        # Nouveau instance charge depuis disque
        mnemo2 = MnemoCore(persistence_path=persist_path)
        value = mnemo2.get("persist:key")
        assert value == "persist_value"
        print("✓ test_persistence passed")
    finally:
        Path(persist_path).unlink(missing_ok=True)


def test_concurrent_access():
    """Test accès concurrent (thread safety)."""
    mnemo = MnemoCore()
    errors = []
    
    def writer(thread_id):
        try:
            for i in range(100):
                key = f"thread:{thread_id}:item:{i}"
                mnemo.set(key, f"value_{i}", provenance="BRAIN")
        except Exception as e:
            errors.append(e)
    
    threads = [threading.Thread(target=writer, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    assert len(errors) == 0
    assert len(mnemo._hot_cache) == 500
    print("✓ test_concurrent_access passed")


def test_health_check():
    """Test health check."""
    mnemo = MnemoCore()
    mnemo.set("health:test", "ok")
    
    health = mnemo.health_check()
    assert health["status"] == "healthy"
    assert health["hot_entries"] >= 1
    assert "stats" in health
    print("✓ test_health_check passed")


def test_stats():
    """Test statistiques."""
    mnemo = MnemoCore()
    mnemo.set("stat:1", "v1")
    mnemo.set("stat:2", "v2")
    _ = mnemo.get("stat:1")  # hit
    _ = mnemo.get("stat:1")  # hit
    _ = mnemo.get("nonexistent")  # miss
    
    stats = mnemo.stats()
    assert stats["sets"] == 2
    assert stats["hits"] == 2
    assert stats["misses"] == 1
    assert stats["hot_entries"] == 2
    assert 0 <= stats["hit_rate"] <= 1
    print("✓ test_stats passed")


def run_all_tests():
    """Lance tous les tests."""
    tests = [
        test_basic_set_get,
        test_tier_management,
        test_ttl_expiration,
        test_lru_eviction,
        test_provenance_tracking,
        test_tag_query,
        test_link_relations,
        test_persistence,
        test_concurrent_access,
        test_health_check,
        test_stats,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__} FAILED: {e}")
            failed += 1
    
    print(f"\n=== Results: {passed} passed, {failed} failed ===")
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)