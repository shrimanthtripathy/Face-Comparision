from backend import db as D

def _clear():
    with D.db() as c: c.execute("DELETE FROM audit")

def test_chain_is_intact_then_detects_tampering():
    _clear()
    for i in range(5): D.audit_log("alice", "1.2.3.4", "compare", f"case{i}", "x")
    assert D.audit_verify() == (True, None)
    with D.db() as c: c.execute("UPDATE audit SET detail='edited' WHERE id=(SELECT id FROM audit ORDER BY id LIMIT 1 OFFSET 2)")
    ok, bad = D.audit_verify(); assert not ok and bad is not None

def test_deleting_an_entry_is_detected():
    _clear()
    for i in range(4): D.audit_log("a", "ip", "x")
    with D.db() as c: c.execute("DELETE FROM audit WHERE id=(SELECT id FROM audit ORDER BY id LIMIT 1 OFFSET 1)")
    assert D.audit_verify()[0] is False
