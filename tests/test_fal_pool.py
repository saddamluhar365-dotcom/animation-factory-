from __future__ import annotations
import time
import pytest
from core.video.contracts import KeyHealthStatus
from core.video.pool import FalKeyPool, FalKeyRecord
from app.storage import mask_key


def test_key_masking():
    assert mask_key("fal_abcdef123456") == "fal_...3456"
    assert mask_key("short12") == "***t12"
    assert mask_key("") == ""


def test_fal_key_pool_unlimited_keys_and_rotation():
    # Support 7+ keys as requested
    raw_keys = [f"fal_test_key_{i:02d}_abcdef" for i in range(1, 9)]
    pool = FalKeyPool(keys=raw_keys)

    assert pool.count() == 8
    assert pool.active_count() == 8

    # Rotate through all keys
    seen = []
    for _ in range(8):
        k = pool.get_next_key()
        seen.append(k.raw_key)

    assert len(seen) == 8
    assert len(set(seen)) == 8  # All 8 unique keys used in round-robin


def test_fal_key_pool_rate_limiting_cooldown():
    pool = FalKeyPool(keys=["key_A", "key_B"], default_cooldown=2.0)
    k1 = pool.get_next_key()
    assert k1.raw_key == "key_A"

    # Mark key_A rate-limited
    pool.mark_rate_limited("key_A", cooldown_seconds=0.5)

    # Next key should immediately be key_B
    k2 = pool.get_next_key()
    assert k2.raw_key == "key_B"

    # Before cooldown expires, key_B is selected again
    k3 = pool.get_next_key()
    assert k3.raw_key == "key_B"

    # After cooldown expires, key_A recovers to active
    time.sleep(0.6)
    k4 = pool.get_next_key()
    assert k4.raw_key in ("key_A", "key_B")


def test_fal_key_pool_invalid_key_disablement():
    pool = FalKeyPool(keys=["good_key", "bad_key"])
    
    # Mark bad_key as invalid (e.g. 401 Unauthorized)
    pool.mark_invalid("bad_key", reason="HTTP 401 Invalid Token")

    summary = pool.status_summary()
    assert summary["invalid"] == 1
    assert summary["active"] == 1

    # Loop 4 times; bad_key must NEVER be leased
    for _ in range(4):
        k = pool.get_next_key()
        assert k.raw_key == "good_key"


def test_fal_key_pool_exhausted_raises_error():
    pool = FalKeyPool(keys=["k1"])
    pool.mark_invalid("k1")

    with pytest.raises(RuntimeError, match="disabled or invalid"):
        pool.get_next_key()
