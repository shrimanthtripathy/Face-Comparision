import hashlib, sqlite3, threading, time
from contextlib import contextmanager
from datetime import datetime, timezone
from . import security as S

_lock = threading.Lock()
SCHEMA = """CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY, pw_hash TEXT NOT NULL, role TEXT NOT NULL,
  failed INTEGER DEFAULT 0, locked_until REAL DEFAULT 0, created REAL);
CREATE TABLE IF NOT EXISTS profile(id INTEGER PRIMARY KEY CHECK(id=1), name TEXT, organisation TEXT, designation TEXT, email TEXT, phone TEXT,
  country TEXT, purpose TEXT, share_consent INTEGER, accepted_terms_at TEXT, registered_at TEXT);
CREATE TABLE IF NOT EXISTS operators(id TEXT PRIMARY KEY, name TEXT, organisation TEXT, designation TEXT, email TEXT, phone TEXT,
  country TEXT, purpose TEXT, terms_at TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, user TEXT, ip TEXT, action TEXT,
  case_id TEXT, detail TEXT, prev TEXT, hash TEXT);"""

@contextmanager
def db():
    c = sqlite3.connect(str(S.datadir() / "nodal.db"), timeout=10); c.row_factory = sqlite3.Row
    try:
        c.executescript(SCHEMA); yield c; c.commit()
    finally:
        c.close()

def create_user(username, password, role="examiner"):
    err = S.policy_error(password)
    if err: raise ValueError(err)
    if role not in ("admin", "examiner"): raise ValueError("Role must be admin or examiner.")
    with db() as c:
        c.execute("INSERT INTO users(username,pw_hash,role,created) VALUES(?,?,?,?)", (username.strip().lower(), S.hash_pw(password), role, time.time()))

def set_password(username, password):
    err = S.policy_error(password)
    if err: raise ValueError(err)
    with db() as c: c.execute("UPDATE users SET pw_hash=?, failed=0, locked_until=0 WHERE username=?", (S.hash_pw(password), username.lower()))

def delete_user(username):
    with db() as c: c.execute("DELETE FROM users WHERE username=?", (username.lower(),))

def get_user(username):
    with db() as c:
        r = c.execute("SELECT * FROM users WHERE username=?", (username.strip().lower(),)).fetchone()
        return dict(r) if r else None

def list_users():
    with db() as c: return [dict(r) for r in c.execute("SELECT username, role, created FROM users ORDER BY username")]

def record_fail(username, max_fails, lock_secs):
    with db() as c:
        c.execute("UPDATE users SET failed=failed+1 WHERE username=?", (username,))
        c.execute("UPDATE users SET locked_until=?, failed=0 WHERE username=? AND failed>=?", (time.time() + lock_secs, username, max_fails))

def clear_fail(username):
    with db() as c: c.execute("UPDATE users SET failed=0, locked_until=0 WHERE username=?", (username,))

# --- tamper-evident audit log: every row hashes the previous row ---
def _digest(prev, ts, user, ip, action, case, detail):
    return hashlib.sha256("|".join([prev, ts, user, ip, action, case, detail]).encode()).hexdigest()

def audit_log(user, ip, action, case_id="", detail=""):
    with _lock, db() as c:
        row = c.execute("SELECT hash FROM audit ORDER BY id DESC LIMIT 1").fetchone()
        prev = row["hash"] if row else "0" * 64
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        user, ip, detail = user or "-", ip or "-", str(detail)[:300]
        c.execute("INSERT INTO audit(ts,user,ip,action,case_id,detail,prev,hash) VALUES(?,?,?,?,?,?,?,?)",
                  (ts, user, ip, action, case_id, detail, prev, _digest(prev, ts, user, ip, action, case_id, detail)))

def audit_verify():
    """Returns (ok, first_bad_id)."""
    with db() as c:
        prev = "0" * 64
        for r in c.execute("SELECT * FROM audit ORDER BY id"):
            if r["prev"] != prev or r["hash"] != _digest(prev, r["ts"], r["user"], r["ip"], r["action"], r["case_id"], r["detail"]):
                return False, r["id"]
            prev = r["hash"]
    return True, None

def audit_tail(limit=100):
    with db() as c: return [dict(r) for r in c.execute("SELECT id,ts,user,ip,action,case_id,detail FROM audit ORDER BY id DESC LIMIT ?", (limit,))]
