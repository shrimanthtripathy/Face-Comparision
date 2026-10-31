import pytest
from backend import db as D, registration as R

GOOD = {"name": "A. Sharma", "organisation": "Cyber Lab", "designation": "Examiner", "email": "a@lab.in",
        "country": "India", "purpose": R.PURPOSES[1], "accepted_terms": True}

def _clear():
    with D.db() as c: c.execute("DELETE FROM profile")

@pytest.mark.parametrize("field", R.REQUIRED)
def test_required_fields(field):
    with pytest.raises(ValueError): R.validate({**GOOD, field: ""})

def test_terms_email_and_purpose_are_enforced():
    for bad in ({"accepted_terms": False}, {"email": "nope"}, {"purpose": "spying"}):
        with pytest.raises(ValueError): R.validate({**GOOD, **bad})

def test_save_roundtrip_and_update_keeps_first_registration_time():
    _clear(); assert R.get_profile() is None
    p1 = R.save(GOOD); p2 = R.save({**GOOD, "organisation": "New Lab"})
    assert p2["organisation"] == "New Lab" and p2["registered_at"] == p1["registered_at"] and p2["accepted_terms_at"]

def test_nothing_is_sent_without_opt_in_or_endpoint(monkeypatch):
    _clear(); p = R.save(GOOD)
    monkeypatch.setenv("NODAL_REGISTRATION_URL", "https://example.invalid/hook")
    assert R.send_async(p) is False                       # operator did not tick the box
    monkeypatch.delenv("NODAL_REGISTRATION_URL"); p["share_consent"] = 1
    assert R.send_async(p) is False                       # no endpoint configured
