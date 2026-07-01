"""Unit tests for plans, feature gating, and the rate limiter (pure)."""

from app import access


def test_plan_config_defaults_to_free():
    assert access.plan_config(None)["max_scan_limit"] == 50
    assert access.plan_config("nonsense")["max_scan_limit"] == 50


def test_feature_gating():
    assert access.has_feature("pro", "pro_signals")
    assert not access.has_feature("free", "pro_signals")
    assert access.has_feature("free", "scan")


def test_clamp_scan_limit():
    assert access.clamp_scan_limit("free", 1000) == 50
    assert access.clamp_scan_limit("free", 10) == 10
    assert access.clamp_scan_limit("pro", 1000) == 1000


def test_rate_limiter_fixed_window():
    rl = access.RateLimiter()
    now = 1000.0
    # limit 3 within the window
    assert rl.allow("k", 3, now)
    assert rl.allow("k", 3, now + 1)
    assert rl.allow("k", 3, now + 2)
    assert not rl.allow("k", 3, now + 3)  # 4th blocked
    # next window resets
    assert rl.allow("k", 3, now + 61)


def test_rate_limiter_isolates_identities():
    rl = access.RateLimiter()
    now = 5.0
    assert rl.allow("a", 1, now)
    assert not rl.allow("a", 1, now)
    assert rl.allow("b", 1, now)  # different identity unaffected
