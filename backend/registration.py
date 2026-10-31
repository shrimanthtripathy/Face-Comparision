"""Operator registration for the desktop app. Details stay on this computer; they are sent to the developer
only if the operator ticks the opt-in box AND an endpoint was configured at build time. Never images or results."""
import hmac, json, os, re, secrets, threading, urllib.request
from datetime import datetime, timezone
from . import db as D
try: from ._endpoint import URL as BAKED
except ImportError: BAKED = ""

VERSION = "1.0"
PURPOSES = ["Law enforcement investigation", "Forensic laboratory", "Legal or court proceedings",
            "Corporate or security investigation", "Academic research", "Education or training", "Other"]
FIELDS = ["name", "organisation", "designation", "email", "phone", "country", "purpose"]
REQUIRED = ["name", "organisation", "designation", "email", "country", "purpose"]
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def endpoint(): return (os.environ.get("NODAL_REGISTRATION_URL") or BAKED or "").strip()

def validate(d):
    out = {k: str(d.get(k, "") or "").strip()[:120] for k in FIELDS}
    for k in REQUIRED:
        if not out[k]: raise ValueError(f"{k.capitalize()} is required.")
    if not EMAIL.match(out["email"]): raise ValueError("Enter a valid email address.")
    if out["purpose"] not in PURPOSES: raise ValueError("Choose a purpose from the list.")
    if not d.get("accepted_terms"): raise ValueError("You must accept the terms of use.")
    out["share_consent"] = 1 if d.get("share_consent") else 0
    return out

def save(d):
    p = validate(d); now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with D.db() as c:
        old = c.execute("SELECT registered_at FROM profile WHERE id=1").fetchone()
        c.execute("INSERT OR REPLACE INTO profile(id,name,organisation,designation,email,phone,country,purpose,share_consent,accepted_terms_at,registered_at) VALUES(1,?,?,?,?,?,?,?,?,?,?)",
                  (p["name"], p["organisation"], p["designation"], p["email"], p["phone"], p["country"], p["purpose"], p["share_consent"], now, old["registered_at"] if old else now))
    return get_profile()

def get_profile():
    with D.db() as c:
        r = c.execute("SELECT * FROM profile WHERE id=1").fetchone()
        return dict(r) if r else None

def send_async(p):
    """Best effort, background, opt-in only. Sends exactly the form fields and the app version."""
    url = endpoint()
    if not (url and p.get("share_consent")): return False
    payload = {k: p[k] for k in FIELDS} | {"app_version": VERSION, "registered_at": p["registered_at"]}
    def go():
        try:
            req = urllib.request.Request(url, json.dumps(payload).encode(), {"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=8).read()
        except Exception: pass
    threading.Thread(target=go, daemon=True).start(); return True

# ---------- hosted mode (phones and browsers): one operator record per registered device ----------
def invite_required(): return bool(os.environ.get("NODAL_INVITE_CODE"))

def check_invite(code):
    need = os.environ.get("NODAL_INVITE_CODE", "")
    return (not need) or hmac.compare_digest(need, str(code or ""))

def create_operator(d, op_id=None):
    p = validate(d); now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"); op_id = op_id or secrets.token_hex(6)
    with D.db() as c:
        old = c.execute("SELECT created FROM operators WHERE id=?", (op_id,)).fetchone()
        c.execute("INSERT OR REPLACE INTO operators(id,name,organisation,designation,email,phone,country,purpose,terms_at,created) VALUES(?,?,?,?,?,?,?,?,?,?)",
                  (op_id, p["name"], p["organisation"], p["designation"], p["email"], p["phone"], p["country"], p["purpose"], now, old["created"] if old else now))
    return get_operator(op_id)

def get_operator(op_id):
    with D.db() as c:
        r = c.execute("SELECT * FROM operators WHERE id=?", (str(op_id),)).fetchone()
        return dict(r) if r else None

def list_operators():
    with D.db() as c: return [dict(r) for r in c.execute("SELECT * FROM operators ORDER BY created")]
