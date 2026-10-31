from conftest import sign_in
from backend import db as D

def post_compare(client, jpeg, consent="true"):
    return client.post("/api/compare", files={"a": ("a.jpg", jpeg, "image/jpeg"), "b": ("b.jpg", jpeg, "image/jpeg")}, data={"consent": consent, "case_ref": "T-1"})

def test_everything_requires_login(client, jpeg):
    assert post_compare(client, jpeg).status_code == 401
    assert client.get("/api/me").status_code == 401 and client.get("/api/audit").status_code == 401

def test_login_wrong_password_and_lockout(client):
    assert sign_in(client, "alice", "wrong password!!").status_code == 401
    for _ in range(5): sign_in(client, "alice", "wrong password!!")
    assert sign_in(client, "alice", "correct horse battery").status_code == 401   # locked even with the right password

def test_login_is_rate_limited(client):
    codes = [sign_in(client, "nobody", "x" * 12).status_code for _ in range(12)]
    assert 429 in codes

def test_full_flow_report_and_audit(client, jpeg):
    assert sign_in(client, "alice", "correct horse battery").status_code == 200
    assert post_compare(client, jpeg, consent="false").status_code == 400
    r = post_compare(client, jpeg); assert r.status_code == 200
    cid = r.json()["case_id"]
    pdf = client.get(f"/api/case/{cid}/report.pdf"); assert pdf.status_code == 200 and pdf.content[:5] == b"%PDF-"
    assert client.get(f"/api/case/{cid}/image/a.jpg").status_code == 200
    actions = [e["action"] for e in D.audit_tail(50)]
    assert {"login_ok", "compare", "download_pdf"} <= set(actions) and D.audit_verify()[0]

def test_cases_are_private_to_their_owner_but_admin_can_see(client, jpeg):
    sign_in(client, "alice", "correct horse battery"); cid = post_compare(client, jpeg).json()["case_id"]
    sign_in(client, "bob", "another long password"); assert client.get(f"/api/case/{cid}/report.pdf").status_code == 404
    assert client.delete(f"/api/case/{cid}").status_code == 404
    sign_in(client, "root", "administrator password"); assert client.get(f"/api/case/{cid}/report.pdf").status_code == 200
    assert client.delete(f"/api/case/{cid}").status_code == 200 and client.get(f"/api/case/{cid}/report.pdf").status_code == 404

def test_audit_endpoint_is_admin_only(client):
    sign_in(client, "alice", "correct horse battery"); assert client.get("/api/audit").status_code == 403
    sign_in(client, "root", "administrator password"); j = client.get("/api/audit").json(); assert j["chain_intact"] is True

def test_compare_is_rate_limited(client, jpeg):
    sign_in(client, "alice", "correct horse battery")
    codes = [post_compare(client, jpeg).status_code for _ in range(12)]
    assert codes.count(200) == 10 and 429 in codes

def test_age_gap_field_is_validated(client, jpeg):
    sign_in(client, "alice", "correct horse battery")
    files = {"a": ("a.jpg", jpeg, "image/jpeg"), "b": ("b.jpg", jpeg, "image/jpeg")}
    assert client.post("/api/compare", files=files, data={"consent": "true", "age_gap": "abc"}).status_code == 422
    assert client.post("/api/compare", files=files, data={"consent": "true", "age_gap": "120"}).status_code == 422
    assert client.post("/api/compare", files=files, data={"consent": "true", "age_gap": "15"}).status_code == 200

def test_security_headers_present(client):
    h = client.get("/api/health").headers
    assert "default-src 'self'" in h["content-security-policy"] and h["x-frame-options"] == "DENY" and h["cache-control"] == "no-store"
