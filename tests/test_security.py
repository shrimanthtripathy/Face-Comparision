import time
from backend import security as S

def test_password_hash_roundtrip():
    h = S.hash_pw("a long password 123")
    assert S.check_pw("a long password 123", h) and not S.check_pw("wrong", h) and not S.check_pw("x", "garbage")

def test_password_policy():
    assert S.policy_error("short") and S.policy_error("long enough password") is None

def test_token_valid_tampered_expired():
    t = S.make_token("alice")
    assert S.read_token(t)["u"] == "alice"
    assert S.read_token(t[:-2] + "00") is None
    assert S.read_token(S.make_token("alice", ttl=-5)) is None
    assert S.read_token("not-a-token") is None

def test_rate_limiter_blocks_then_recovers():
    r = S.RateLimiter()
    assert all(r.hit("k", 3, 0.2)[0] for _ in range(3))
    ok, wait = r.hit("k", 3, 0.2); assert not ok and wait >= 1
    assert r.hit("other", 3, 0.2)[0]
    time.sleep(0.25); assert r.hit("k", 3, 0.2)[0]
