import base64, hashlib, hmac, json, os, secrets, threading, time
from collections import defaultdict, deque
from pathlib import Path

def datadir():
    p = Path(os.environ.get("NODAL_DATA_DIR") or Path(__file__).resolve().parent.parent / "data")
    p.mkdir(parents=True, exist_ok=True); return p

def hash_pw(pw):
    salt = os.urandom(16)
    return f"scrypt${salt.hex()}${hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32).hex()}"

def check_pw(pw, stored):
    try:
        _, s, h = stored.split("$")
        calc = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(s), n=2**14, r=8, p=1, dklen=32).hex()
    except Exception:
        return False
    return hmac.compare_digest(calc, h)

DUMMY = hash_pw("dummy-password-for-constant-timing")  # used when the username does not exist

def policy_error(pw):
    return None if len(pw) >= 12 else "Password must be at least 12 characters."

def _secret():
    if os.environ.get("NODAL_SECRET"): return os.environ["NODAL_SECRET"].encode()
    f = datadir() / "secret.key"
    if not f.exists():
        f.write_text(secrets.token_hex(32))
        try: os.chmod(f, 0o600)
        except OSError: pass
    return f.read_text().strip().encode()

def _sig(body): return hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()

def make_token(user, ttl=8 * 3600):
    body = base64.urlsafe_b64encode(json.dumps({"u": user, "exp": int(time.time()) + ttl}).encode()).decode()
    return f"{body}.{_sig(body)}"

def read_token(tok):
    try:
        body, sig = tok.rsplit(".", 1)
        if not hmac.compare_digest(_sig(body), sig): return None
        d = json.loads(base64.urlsafe_b64decode(body))
        return d if d["exp"] > time.time() else None
    except Exception:
        return None

class RateLimiter:
    """Sliding window, in memory. Use Redis instead if you run more than one worker process."""
    def __init__(self): self.h, self.lock = defaultdict(deque), threading.Lock()
    def reset(self):
        with self.lock: self.h.clear()
    def hit(self, key, limit, window):
        now = time.monotonic()
        with self.lock:
            q = self.h[key]
            while q and now - q[0] > window: q.popleft()
            if len(q) >= limit: return False, int(window - (now - q[0])) + 1
            q.append(now); return True, 0
