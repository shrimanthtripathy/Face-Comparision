import asyncio, hashlib, json, os, re, shutil, sys, time, uuid
from importlib import metadata
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
import cv2
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from . import db as D, engine as E, registration as R, report, security as S

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
DATA = S.datadir() / "cases"; DATA.mkdir(parents=True, exist_ok=True)
TTL_MIN, MAX_BYTES = 60, 25 * 1024 * 1024   # phone cameras produce large photos
ID = re.compile(r"^[a-f0-9]{12}$")
TEAL, AMBER = (114, 122, 11), (31, 160, 245)  # BGR
state = {}
SECURE = os.environ.get("NODAL_HTTPS") == "1"
DESKTOP = os.environ.get("NODAL_MODE") == "desktop"   # single-user local app: operator details instead of login
LOCAL_TOKEN = os.environ.get("NODAL_LOCAL_TOKEN", "")
HOSTED = os.environ.get("NODAL_MODE") == "hosted"   # web/phone version: operator details per device, no passwords
MAX_FAILS, LOCK_SECS = 5, 900
limiter = S.RateLimiter()
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src https://fonts.gstatic.com; img-src 'self' blob: data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")

def ip_of(r): return r.client.host if r.client else "-"

def throttle(key, limit, window):
    ok, wait = limiter.hit(key, limit, window)
    if not ok: raise HTTPException(429, f"Too many requests. Try again in {wait} s.", headers={"Retry-After": str(wait)})

def who(user): return (user.get("profile") or {}).get("name") or user["username"]

def current_user(request: Request):
    if DESKTOP:
        p = R.get_profile()
        if not p: raise HTTPException(401, "Operator details required.")
        return {"username": "local", "role": "admin", "profile": p}
    if HOSTED:
        d = S.read_token(request.cookies.get("nodal_op", ""))
        op = R.get_operator(d["u"]) if d else None
        if not op: raise HTTPException(401, "Operator details required.")
        throttle("user:op-" + op["id"], 240, 60)
        return {"username": "op-" + op["id"], "role": "operator", "profile": op}
    d = S.read_token(request.cookies.get("nodal_session", ""))
    u = D.get_user(d["u"]) if d else None
    if not u: raise HTTPException(401, "Sign in required.")
    throttle("user:" + u["username"], 240, 60)
    return u

def versions():
    out = []
    for n in ("opencv-python-headless", "numpy", "mediapipe", "insightface"):
        try: out.append(f"{n} {metadata.version(n)}")
        except metadata.PackageNotFoundError: out.append(f"{n} n/a")
    return ", ".join(out)

async def janitor():
    while True:
        for d in DATA.iterdir():
            if d.is_dir() and time.time() - d.stat().st_mtime > TTL_MIN * 60: shutil.rmtree(d, ignore_errors=True)
        await asyncio.sleep(60)

@asynccontextmanager
async def lifespan(app):
    state["engine"] = E.Engine(); task = asyncio.create_task(janitor()); yield; task.cancel()

app = FastAPI(title="Nodal", lifespan=lifespan)

@app.middleware("http")
async def guard(request: Request, call_next):
    if DESKTOP:   # only this computer's launcher may talk to the local server
        if request.headers.get("host", "").split(":")[0] not in ("127.0.0.1", "localhost"):
            return JSONResponse({"detail": "Forbidden host."}, 403)
        if LOCAL_TOKEN and request.url.path.startswith("/api/") and request.cookies.get("nodal_local") != LOCAL_TOKEN:
            return JSONResponse({"detail": "Open Nodal from its launcher."}, 403)
    ok, wait = limiter.hit("ip:" + ip_of(request), 600, 60)
    resp = await call_next(request) if ok else JSONResponse({"detail": "Too many requests."}, 429, headers={"Retry-After": str(wait)})
    if DESKTOP and LOCAL_TOKEN and request.query_params.get("t") == LOCAL_TOKEN:
        resp.set_cookie("nodal_local", LOCAL_TOKEN, httponly=True, samesite="strict", path="/")
    resp.headers.update({"Content-Security-Policy": CSP, "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
                         "Referrer-Policy": "no-referrer", "Permissions-Policy": "camera=(), microphone=(), geolocation=()"})
    if request.url.path.startswith("/api/"): resp.headers["Cache-Control"] = "no-store"
    if SECURE: resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return resp

class Login(BaseModel):
    username: str
    password: str

@app.post("/api/login")
def login(body: Login, request: Request, response: Response):
    ip = ip_of(request); throttle("login:" + ip, 10, 60)
    u = D.get_user(body.username)
    locked = bool(u) and u["locked_until"] > time.time()
    ok = S.check_pw(body.password, u["pw_hash"] if u else S.DUMMY)
    if not (u and ok) or locked:
        if u and not locked: D.record_fail(u["username"], MAX_FAILS, LOCK_SECS)
        D.audit_log(body.username[:40], ip, "login_locked" if locked else "login_fail")
        raise HTTPException(401, "Wrong username or password, or the account is temporarily locked.")
    D.clear_fail(u["username"]); D.audit_log(u["username"], ip, "login_ok")
    response.set_cookie("nodal_session", S.make_token(u["username"]), httponly=True, samesite="strict", secure=SECURE, max_age=8 * 3600, path="/")
    return {"username": u["username"], "role": u["role"]}

@app.post("/api/logout")
def logout(request: Request, response: Response):
    d = S.read_token(request.cookies.get("nodal_session", ""))
    if d: D.audit_log(d["u"], ip_of(request), "logout")
    response.delete_cookie("nodal_session", path="/"); return {"ok": True}

@app.get("/api/me")
def me(user=Depends(current_user)): return {"username": user["username"], "role": user["role"], **(user.get("profile") or {})}

@app.get("/api/config")
def config(): return {"mode": "desktop" if DESKTOP else "hosted" if HOSTED else "server", "version": R.VERSION, "purposes": R.PURPOSES,
                      "share_enabled": bool(R.endpoint()) and DESKTOP, "invite_required": HOSTED and R.invite_required()}

class Register(BaseModel):
    name: str = ""
    organisation: str = ""
    designation: str = ""
    email: str = ""
    phone: str = ""
    country: str = ""
    purpose: str = ""
    accepted_terms: bool = False
    share_consent: bool = False
    invite: str = ""

@app.post("/api/register")
def register(body: Register, request: Request, response: Response):
    if not (DESKTOP or HOSTED): raise HTTPException(404, "Not available.")
    ip = ip_of(request)
    if HOSTED:
        throttle("register:" + ip, 5, 60)
        if not R.check_invite(body.invite): raise HTTPException(403, "Invalid invitation code.")
        d = S.read_token(request.cookies.get("nodal_op", ""))
        try: op = R.create_operator(dict(body), d["u"] if d and R.get_operator(d["u"]) else None)
        except ValueError as e: raise HTTPException(422, str(e))
        response.set_cookie("nodal_op", S.make_token(op["id"], ttl=30 * 86400), httponly=True, samesite="strict", secure=SECURE, max_age=30 * 86400, path="/")
        D.audit_log(op["name"], ip, "operator_registered", "", f"id={op['id']} org={op['organisation']} purpose={op['purpose']}")
        return {"ok": True}
    try: p = R.save(dict(body))
    except ValueError as e: raise HTTPException(422, str(e))
    sent = R.send_async(p)
    D.audit_log(p["name"], ip, "operator_details_saved", "", f"org={p['organisation']} purpose={p['purpose']} shared_with_developer={sent}")
    return {"ok": True}

@app.get("/api/audit")
def audit(limit: int = 100, user=Depends(current_user)):
    if user["role"] != "admin": raise HTTPException(403, "Administrators only.")
    ok, bad = D.audit_verify(); return {"chain_intact": ok, "first_bad_entry": bad, "entries": D.audit_tail(min(max(limit, 1), 500))}

def _case(cid, user):
    if not ID.match(cid) or not (DATA / cid / "result.json").is_file(): raise HTTPException(404, "Case not found or expired.")
    res = json.loads((DATA / cid / "result.json").read_text())
    if res.get("owner") != user["username"] and user["role"] != "admin": raise HTTPException(404, "Case not found or expired.")
    return DATA / cid, res

@app.get("/api/health")
def health(): return {"ok": True}

@app.get("/api/status")
def status(user=Depends(current_user)):
    if user["role"] != "admin": raise HTTPException(403, "Administrators only.")
    en = state["engine"]; return {"embedding_model": bool(en.arc), "embedding_error": en.arc_error, "ttl_minutes": TTL_MIN}

def _gap(age_gap):
    if not age_gap.strip(): return None
    if not age_gap.strip().isdigit() or int(age_gap) > 90: raise HTTPException(422, "Years between the photos must be a whole number from 0 to 90.")
    return int(age_gap)

def _read(*files):
    out = []
    for f in files:
        data = f.file.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES: raise HTTPException(413, f"{f.filename} is larger than {MAX_BYTES // 1048576} MB.")
        out.append(data)
    return out

def _inputs(*items):
    return {k: {"filename": n[:80], "sha256": hashlib.sha256(r).hexdigest(), "bytes": len(r)} for k, n, r in items}

def _build_case(request, user, ia, ib, ma, mb, gap, form, inputs, group=None, marked=None, a_chosen=False):
    try:
        res, b_al, pb_al = state["engine"].compare(ia, ib, ma, mb, gap, a_chosen)
    except E.AmbiguousFaces as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))
    cid = uuid.uuid4().hex[:12]; d = DATA / cid; d.mkdir()
    pa, pb = res["landmarks"]["a"], res["landmarks"]["b"]
    imgs = {"a": ia, "b": ib, "b_aligned": b_al, "a_ann": E.annotate(ia, pa, TEAL), "b_ann": E.annotate(ib, pb, AMBER),
            "overlay": E.annotate(cv2.addWeighted(ia, 0.5, b_al, 0.5, 0), pa, TEAL, res["landmarks"]["b_aligned"], AMBER)}
    if marked is not None: imgs["group_marked"] = marked
    for k, v in imgs.items(): cv2.imwrite(str(d / f"{k}.jpg"), v, [cv2.IMWRITE_JPEG_QUALITY, 92])
    res.update({"case_id": cid, "created_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
                "expires_at": (datetime.utcnow() + timedelta(minutes=TTL_MIN)).strftime("%H:%M UTC"),
                "meta": {"case_ref": form["case_ref"][:80], "examiner": form["examiner"][:80] or (user.get("profile") or {}).get("name", ""), "purpose": form["purpose"][:200],
                         "operator": {k: user["profile"][k] for k in ("name", "organisation", "designation")} if user.get("profile") else None},
                "inputs": inputs, "method": {"version": "1.0", "versions": versions(), "calibration": E.CALIBRATION}, "owner": user["username"],
                "images": {k: f"/api/case/{cid}/image/{k}.jpg" for k in ("a", "b", "b_aligned")}})
    if group: res["group"] = group
    (d / "result.json").write_text(json.dumps(res))
    D.audit_log(who(user), ip_of(request), "compare", cid, f"a={inputs['a']['sha256'][:16]} b={inputs['b']['sha256'][:16]} result={res['conclusion']['label']}"
                + (f" group_face={group['face_number']}/{group['faces_searched']}" if group else ""))
    return res

@app.post("/api/compare")
def compare(request: Request, a: UploadFile = File(...), b: UploadFile = File(...), consent: str = Form(...),
            case_ref: str = Form(""), examiner: str = Form(""), purpose: str = Form(""), age_gap: str = Form(""), user=Depends(current_user)):
    throttle("compare:" + user["username"], 10, 60)
    if consent != "true": raise HTTPException(400, "Confirm you have the right to process these images.")
    gap = _gap(age_gap); raw = _read(a, b)
    try:
        (ia, ma), (ib, mb) = E.load_image(raw[0]), E.load_image(raw[1])
    except Exception:
        raise HTTPException(400, "One of the files is not a readable image (use JPEG, PNG or WebP).")
    return _build_case(request, user, ia, ib, ma, mb, gap, {"case_ref": case_ref, "examiner": examiner, "purpose": purpose},
                       _inputs(("a", a.filename, raw[0]), ("b", b.filename, raw[1])))

# ---------------- group photo: find the person, let the examiner choose the face ----------------
def _scan_dir(sid, user):
    if not ID.match(sid) or not (DATA / sid / "scan.json").is_file(): raise HTTPException(404, "Scan not found or expired.")
    sc = json.loads((DATA / sid / "scan.json").read_text())
    if sc.get("owner") != user["username"] and user["role"] != "admin": raise HTTPException(404, "Scan not found or expired.")
    return DATA / sid, sc

@app.post("/api/group/scan")
def group_scan(request: Request, a: UploadFile = File(...), b: UploadFile = File(...), consent: str = Form(...), user=Depends(current_user)):
    throttle("scan:" + user["username"], 10, 60)
    if consent != "true": raise HTTPException(400, "Confirm you have the right to process these images.")
    raw = _read(a, b)
    try:
        (ig, mg), (ir, mr) = E.load_image(raw[0], 3000), E.load_image(raw[1])   # keep more resolution so small faces survive
    except Exception:
        raise HTTPException(400, "One of the files is not a readable image (use JPEG, PNG or WebP).")
    try:
        faces = state["engine"].scan(ig, ir)
    except E.AmbiguousFaces as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))
    if not faces: raise HTTPException(422, "No faces were found in the group photo.")
    ranked = sorted((f["cosine"] for f in faces), reverse=True); notes = []
    if len(faces) > 1: notes.append(f"Searching {len(faces)} faces raises the chance that one looks like the reference by chance. Treat the top-ranked face as a lead and confirm it by eye.")
    if ranked[0] < 0.25: notes.append("No face in the group photo resembles the reference strongly.")
    elif len(ranked) > 1 and ranked[0] - ranked[1] < 0.08: notes.append("The top two faces score similarly, so the ranking is not decisive.")
    small = sum(f["size_px"] < 40 for f in faces)
    if small: notes.append(f"{small} face(s) are very small (under 40 px); small faces may be missed or unreliable.")
    sid = uuid.uuid4().hex[:12]; d = DATA / sid; d.mkdir()
    cv2.imwrite(str(d / "group.jpg"), ig, [cv2.IMWRITE_JPEG_QUALITY, 92]); cv2.imwrite(str(d / "ref.jpg"), ir, [cv2.IMWRITE_JPEG_QUALITY, 92])
    inputs = _inputs(("a", a.filename, raw[0]), ("b", b.filename, raw[1]))
    (d / "scan.json").write_text(json.dumps({"owner": user["username"], "faces": faces, "inputs": inputs, "meta_a": mg, "meta_b": mr}))
    D.audit_log(who(user), ip_of(request), "group_scan", sid, f"a={inputs['a']['sha256'][:16]} b={inputs['b']['sha256'][:16]} faces={len(faces)}")
    return {"scan_id": sid, "image": f"/api/scan/{sid}/image.jpg", "width": ig.shape[1], "height": ig.shape[0], "faces": faces, "notes": notes}

@app.get("/api/scan/{sid}/image.jpg")
def scan_image(sid: str, user=Depends(current_user)):
    return FileResponse(_scan_dir(sid, user)[0] / "group.jpg", media_type="image/jpeg")

@app.post("/api/scan/{sid}/compare")
def scan_compare(sid: str, request: Request, face: int = Form(...), case_ref: str = Form(""), examiner: str = Form(""),
                 purpose: str = Form(""), age_gap: str = Form(""), user=Depends(current_user)):
    throttle("compare:" + user["username"], 10, 60)
    d, sc = _scan_dir(sid, user); faces = sc["faces"]
    if not 0 <= face < len(faces): raise HTTPException(422, "Choose one of the detected faces.")
    ig, ir = cv2.imread(str(d / "group.jpg")), cv2.imread(str(d / "ref.jpg"))
    x0, y0, x1, y1 = faces[face]["bbox"]; w, h = x1 - x0, y1 - y0
    crop = ig[max(0, int(y0 - .35 * h)):min(ig.shape[0], int(y1 + .35 * h)), max(0, int(x0 - .35 * w)):min(ig.shape[1], int(x1 + .35 * w))]
    marked, t = ig.copy(), max(2, ig.shape[1] // 500)
    for i, f in enumerate(faces):
        a_, b_, c_, d_ = f["bbox"]; chosen = i == face; col = AMBER if chosen else (150, 150, 150)
        cv2.rectangle(marked, (a_, b_), (c_, d_), col, t * 2 if chosen else t)
        cv2.putText(marked, str(i + 1), (a_, max(18, b_ - 6)), cv2.FONT_HERSHEY_SIMPLEX, max(0.6, ig.shape[1] / 1800), col, t, cv2.LINE_AA)
    group = {"scan_id": sid, "faces_searched": len(faces), "face_number": face + 1, "rank": faces[face]["rank"],
             "scan_cosine": faces[face]["cosine"], "selected_by": "examiner", "bbox": faces[face]["bbox"]}
    return _build_case(request, user, crop, ir, sc["meta_a"], sc["meta_b"], _gap(age_gap),
                       {"case_ref": case_ref, "examiner": examiner, "purpose": purpose}, sc["inputs"], group, marked, a_chosen=True)

@app.get("/api/case/{cid}/image/{name}.jpg")
def image(cid: str, name: str, user=Depends(current_user)):
    if name not in {"a", "b", "b_aligned", "a_ann", "b_ann", "overlay"}: raise HTTPException(404)
    return FileResponse(_case(cid, user)[0] / f"{name}.jpg", media_type="image/jpeg")

@app.get("/api/case/{cid}/report.json")
def report_json(cid: str, request: Request, user=Depends(current_user)):
    d, _ = _case(cid, user); D.audit_log(who(user), ip_of(request), "download_json", cid)
    return Response((d / "result.json").read_bytes(), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="nodal-{cid}.json"'})

@app.get("/api/case/{cid}/report.pdf")
def report_pdf(cid: str, request: Request, user=Depends(current_user)):
    d, res = _case(cid, user); D.audit_log(who(user), ip_of(request), "download_pdf", cid)
    imgs = {k: (d / f"{k}.jpg").read_bytes() for k in ("a_ann", "b_ann", "overlay")}
    pics = {"a": imgs["a_ann"], "b": imgs["b_ann"], "overlay": imgs["overlay"]}
    if (d / "group_marked.jpg").exists(): pics["group"] = (d / "group_marked.jpg").read_bytes()
    pdf = report.build(res, pics)
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="nodal-report-{cid}.pdf"'})

@app.delete("/api/case/{cid}")
def delete(cid: str, request: Request, user=Depends(current_user)):
    d, res = _case(cid, user); shutil.rmtree(d, ignore_errors=True)
    if res.get("group") and ID.match(res["group"]["scan_id"]): shutil.rmtree(DATA / res["group"]["scan_id"], ignore_errors=True)
    D.audit_log(who(user), ip_of(request), "delete_case", cid); return {"deleted": True}

app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="ui")
