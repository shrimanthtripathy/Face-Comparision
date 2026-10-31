from backend import engine as E

Q = {"hard_issues": [], "soft_issues": [], "yaw": 5, "pitch": 0}
def _eng():
    e = E.Engine.__new__(E.Engine); e.arc = None; return e
def level(cos, age, ai=80): return _eng()._conclude(cos, {"agreement_index": ai}, Q, Q, age)["level"]

def test_child_versus_adult_is_blocked():
    a = E.age_assess(6, 35); assert a["child"] and a["rule"] == "block" and a["gap"] == 29

def test_gap_bands():
    assert E.age_assess(30, 33)["rule"] == "none"
    assert E.age_assess(25, 32)["rule"] == "soft"
    assert E.age_assess(25, 37)["rule"] == "cap"
    assert E.age_assess(20, 45)["rule"] == "block" and not E.age_assess(20, 45)["child"]

def test_declared_gap_overrides_estimate_and_unknown_is_flagged():
    assert E.age_assess(30, 31, declared=22)["rule"] == "block"
    assert E.age_assess(None, None, declared=15)["rule"] == "cap"
    u = E.age_assess(None, None); assert u["rule"] == "none" and u["message"]

def test_block_forces_inconclusive_for_any_score():
    b = E.age_assess(6, 35)
    assert level(0.9, b) == 2 and level(0.05, b) == 2

def test_cap_never_supports_different_and_never_strong_same():
    c = E.age_assess(25, 37)
    assert level(0.05, c) == 2 and level(0.2, c) == 2 and level(0.9, c) == 3 and level(0.45, c) == 3

def test_soft_moves_one_step_and_skips_geometry_check():
    s = E.age_assess(25, 32)
    assert level(0.9, s) == 3 and level(0.9, s, ai=20) == 3      # geometry is unreliable across an age gap

def test_no_age_info_leaves_verdict_unchanged():
    assert level(0.9, None) == 4 and level(0.9, E.age_assess(30, 31)) == 4
