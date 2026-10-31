import pytest
from backend import db as D, registration as R
from test_profile import GOOD

def test_operator_roundtrip_update_and_listing():
    with D.db() as c: c.execute("DELETE FROM operators")
    op = R.create_operator(GOOD); same = R.create_operator({**GOOD, "organisation": "Lab 2"}, op["id"])
    assert same["id"] == op["id"] and same["organisation"] == "Lab 2" and same["created"] == op["created"]
    assert len(R.list_operators()) == 1 and R.get_operator("missing") is None

def test_operator_needs_terms_and_valid_details():
    with pytest.raises(ValueError): R.create_operator({**GOOD, "accepted_terms": False})
    with pytest.raises(ValueError): R.create_operator({**GOOD, "email": "bad"})

def test_invite_code(monkeypatch):
    monkeypatch.delenv("NODAL_INVITE_CODE", raising=False); assert R.check_invite("") and not R.invite_required()
    monkeypatch.setenv("NODAL_INVITE_CODE", "s3cret"); assert R.invite_required() and R.check_invite("s3cret") and not R.check_invite("wrong") and not R.check_invite(None)
