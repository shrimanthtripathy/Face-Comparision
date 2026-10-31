import io, json, os, threading
from pathlib import Path
import cv2, numpy as np
from PIL import Image, ImageOps
from . import integrity

MAX_SIDE = 1024
COS_CUTS = [0.15, 0.25, 0.40, 0.55]   # provisional defaults; python -m backend.calibrate writes backend/calibration.json, which replaces them
CALIBRATION = None
_cal = Path(__file__).with_name("calibration.json")
if _cal.exists():
    try: CALIBRATION = json.loads(_cal.read_text()); COS_CUTS = CALIBRATION["cos_cuts"]
    except Exception: CALIBRATION = None
LABELS = ["Strong support for different identities", "Moderate support for different identities",
          "Inconclusive", "Moderate support for the same identity", "Strong support for the same identity"]

REGIONS = {
 "eye_right": [33,7,163,144,145,153,154,155,133,173,157,158,159,160,161,246],
 "eye_left": [362,382,381,380,374,373,390,249,263,466,388,387,386,385,384,398],
 "brow_right": [70,63,105,66,107,55,65,52,53,46],
 "brow_left": [300,293,334,296,336,285,295,282,283,276],
 "nose": [1,2,4,5,6,19,94,97,98,168,195,197,129,358,327,326,49,279,64,294,48,278,102,331,219,439,45,275,440,344,115,220],
 "lips": [61,146,91,181,84,17,314,405,321,375,291,409,270,269,267,0,37,39,40,185,78,95,88,178,87,14,317,402,318,324,308,415,310,311,312,13,82,81,80,191],
 "contour": [10,338,297,332,284,251,389,356,454,323,361,288,397,365,379,378,400,377,152,148,176,149,150,136,172,58,132,93,234,127,162,21,54,103,67,109],
 "iris": list(range(468, 478)),
}
_used = {i for v in REGIONS.values() for i in v}
REGIONS["cheeks_forehead"] = [i for i in range(478) if i not in _used]

RATIOS = {  # name: (landmark pair); normalised by outer inter-ocular distance (33-263)
 "Eye width (subject right)": (33,133), "Eye width (subject left)": (263,362),
 "Inner eye gap": (133,362), "Nose width": (129,358), "Nose length": (168,2),
 "Mouth width": (61,291), "Face width": (234,454), "Face height": (10,152),
 "Jaw width": (172,397), "Subnasale to chin": (2,152)}

# Age safeguard (provisional, uncalibrated): large age gaps lower similarity even for the same person.
AGE_SOFT, AGE_CAP, AGE_BLOCK, CHILD_AGE = 5, 10, 20, 14

def age_assess(est_a, est_b, declared=None):
    """Decide how much an age gap should limit the verdict. rule: none | soft | cap | block."""
    gap, src = None, None
    if declared is not None: gap, src = float(declared), "declared by the examiner"
    elif est_a is not None and est_b is not None: gap, src = float(abs(est_a - est_b)), "estimated from the faces"
    child = any(a is not None and a < CHILD_AGE for a in (est_a, est_b))
    rule, msg = "none", None
    if child:
        rule, msg = "block", f"A face appears to be a child's (estimated age under {CHILD_AGE}). Models trained mostly on adults are unreliable here, so no identity conclusion is given."
    elif gap is None:
        msg = "The age difference could not be estimated. If the photos were taken years apart, treat the result with great care."
    elif gap >= AGE_BLOCK:
        rule, msg = "block", f"About {gap:.0f} years between the photos ({src}). Faces change too much over this span for a reliable conclusion."
    elif gap >= AGE_CAP:
        rule, msg = "cap", f"About {gap:.0f} years between the photos ({src}). A low score cannot support 'different identities' and 'strong' support is not allowed."
    elif gap >= AGE_SOFT:
        rule, msg = "soft", f"About {gap:.0f} years between the photos ({src}). The verdict was moved one step toward inconclusive."
    return {"estimated_a": est_a, "estimated_b": est_b, "declared_gap": declared, "gap": gap, "source": src, "child": child, "rule": rule, "message": msg}

class AmbiguousFaces(ValueError):
    """An image holds several faces of similar size, so we cannot silently guess which person to compare."""

def pick_index(boxes, w, h, how="largest"):
    """Index of the chosen face. 'central' = nearest the image centre (the LFW convention); 'largest' = biggest box."""
    if how == "central": return int(np.argmin([np.hypot((b[0] + b[2]) / 2 - w / 2, (b[1] + b[3]) / 2 - h / 2) for b in boxes]))
    return int(np.argmax([(b[2] - b[0]) * (b[3] - b[1]) for b in boxes]))

def substantial(faces):
    """Faces comparable in size to the biggest one (small background faces do not count)."""
    sizes = [min(f.bbox[2] - f.bbox[0], f.bbox[3] - f.bbox[1]) for f in faces]
    if not sizes: return []
    return [f for f, s in zip(faces, sizes) if s >= 0.6 * max(sizes) and float(f.det_score) >= 0.6]

MODEL3D = np.array([(0,0,0),(0,63.6,12.5),(-43.3,-32.7,26),(43.3,-32.7,26),(28.9,28.9,24.1),(-28.9,28.9,24.1)], float)
POSE_IDX = [1, 152, 33, 263, 291, 61]

def load_image(data, max_side=MAX_SIDE):
    im = Image.open(io.BytesIO(data)); exif = im.getexif()
    meta = {"exif": len(exif) > 0, "software": str(exif.get(0x0131, ""))[:60]}
    im = ImageOps.exif_transpose(im).convert("RGB"); im.thumbnail((max_side, max_side))
    return cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR), meta

def _wrap(a):
    a = (a + 180) % 360 - 180
    return a - 180 if a > 90 else a + 180 if a < -90 else a

def pose(pts, w, h):
    cam = np.array([[w, 0, w / 2], [0, w, h / 2], [0, 0, 1]], float)
    ok, rv, _ = cv2.solvePnP(MODEL3D, pts[POSE_IDX], cam, np.zeros(4))
    if not ok: return 0., 0., 0.
    p, y, r = cv2.RQDecomp3x3(cv2.Rodrigues(rv)[0])[0]
    return _wrap(p), _wrap(y), _wrap(r)

def procrustes(A, B):
    ma, mb = A.mean(0), B.mean(0); Ac, Bc = A - ma, B - mb
    U, S, Vt = np.linalg.svd(Bc.T @ Ac)
    d = np.sign(np.linalg.det(U @ Vt)) or 1.0
    R = U @ np.diag([1, d]) @ Vt
    s = (S * np.array([1, d])).sum() / (Bc ** 2).sum()
    return s, R, mb, ma

def agree(d):  # provisional mapping of normalised shape distance to a 0-100 index
    return round(100 * min(1, max(0, 1 - (d - 0.015) / 0.06)), 1)

class Engine:
    def __init__(self, mesh=True, age=True):
        self.lock = threading.Lock(); self.mesh = None
        if mesh:
            import mediapipe as mp
            if not hasattr(mp, "solutions"):
                raise RuntimeError("This mediapipe version has no 'solutions' API. Run: pip install mediapipe==0.10.14 (needs Python 3.9 to 3.11)")
            self.mesh = mp.solutions.face_mesh.FaceMesh(static_image_mode=True, max_num_faces=3,
                                                        refine_landmarks=True, min_detection_confidence=0.5)
        self.arc, self.arc_error = None, None
        try:
            from insightface.app import FaceAnalysis
            self.arc = FaceAnalysis(name="buffalo_l", root=os.environ.get("NODAL_MODEL_DIR") or "~/.insightface", providers=["CPUExecutionProvider"],
                                    allowed_modules=["detection", "recognition"] + (["genderage"] if age else []))
            self.arc.prepare(ctx_id=-1, det_size=(640, 640))
        except Exception as e:
            self.arc_error = str(e)

    def _landmarks(self, img, near=None):
        h, w = img.shape[:2]
        res = self.mesh.process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        if not res.multi_face_landmarks: return None, 0
        fs = res.multi_face_landmarks
        area = lambda f: np.ptp([p.x for p in f.landmark]) * np.ptp([p.y for p in f.landmark])
        if near is not None:   # use the same person the recognition model chose
            cx, cy = (near[0] + near[2]) / 2, (near[1] + near[3]) / 2
            f = min(fs, key=lambda f: np.hypot(np.mean([p.x for p in f.landmark]) * w - cx, np.mean([p.y for p in f.landmark]) * h - cy))
        else:
            f = max(fs, key=area)
        return np.array([[p.x * w, p.y * h] for p in f.landmark]), len(fs)

    def _faces(self, img):
        return list(self.arc.get(img)) if self.arc else []

    @staticmethod
    def _pick(fs, img, how="largest"):
        if not fs: return None
        return fs[pick_index([f.bbox for f in fs], img.shape[1], img.shape[0], how)]

    @staticmethod
    def _check_ambiguous(fs, label, advice):
        n = len(substantial(fs))
        if n > 1: raise AmbiguousFaces(f"Image {label} contains {n} faces of similar size, so Nodal cannot tell which person to compare. {advice}")

    def _face(self, img):
        return self._pick(self._faces(img), img)

    def _embed(self, img):
        f = self._face(img)
        return None if f is None else f.normed_embedding

    def scan(self, group, ref, det_size=1280):
        """Find every face in a group photo and rank them by similarity to the reference face."""
        if not self.arc: raise ValueError("The face-recognition model is not available, so a group photo cannot be searched.")
        with self.lock:
            fbs = self._faces(ref); self._check_ambiguous(fbs, "B", "Crop the reference photo to the person you want to find.")
            rf = self._pick(fbs, ref)
            if rf is None: raise ValueError("No face found in the reference image (B).")
            det = self.arc.det_model; prev = getattr(det, "input_size", None)
            try:
                if prev is not None: det.input_size = (det_size, det_size)   # larger detector size so small faces are found
                fs = self.arc.get(group)
            finally:
                if prev is not None: det.input_size = prev
        fs = sorted(fs, key=lambda f: -float(f.det_score))[:80]
        out = []
        for i, f in enumerate(fs):
            x0, y0, x1, y1 = [float(v) for v in f.bbox]
            out.append({"index": i, "bbox": [round(x0), round(y0), round(x1), round(y1)], "size_px": int(min(x1 - x0, y1 - y0)),
                        "det_score": round(float(f.det_score), 3), "cosine": round(float(np.dot(f.normed_embedding, rf.normed_embedding)), 4), "age": self._age(f)})
        for r, i in enumerate(sorted(range(len(out)), key=lambda i: -out[i]["cosine"]), 1): out[i]["rank"] = r
        return out

    @staticmethod
    def _age(f):
        a = getattr(f, "age", None) if f is not None else None
        return int(round(float(a))) if a is not None else None

    def _quality(self, img, pts, nfaces):
        h, w = img.shape[:2]
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        x0, y0 = np.clip(pts.min(0), 0, [w - 1, h - 1]).astype(int); x1, y1 = np.clip(pts.max(0), 0, [w - 1, h - 1]).astype(int)
        crop = g[y0:y1 + 1, x0:x1 + 1]
        sharp = float(cv2.Laplacian(crop, cv2.CV_64F).var()); bright = float(crop.mean())
        iod = float(np.linalg.norm(pts[33] - pts[263])); pitch, yaw, roll = pose(pts, w, h)
        hard, soft = [], []
        if iod < 40: hard.append("Face too small (inter-ocular distance under 40 px)")
        if sharp < 30: hard.append("Face region is too blurred")
        if abs(yaw) > 45 or abs(pitch) > 40: hard.append("Head pose too extreme for comparison")
        elif abs(yaw) > 25 or abs(pitch) > 25: soft.append("Head turned noticeably away from frontal")
        if bright < 60 or bright > 200: soft.append("Poor exposure on the face")
        if nfaces > 1: soft.append("More than one face found; the largest was used")
        return {"sharpness": round(sharp, 1), "brightness": round(bright, 1), "inter_ocular_px": round(iod, 1),
                "pitch": round(pitch, 1), "yaw": round(yaw, 1), "roll": round(roll, 1),
                "width": w, "height": h, "hard_issues": hard, "soft_issues": soft}

    def compare(self, ia, ib, ma, mb, age_gap=None, a_chosen=False):
        with self.lock:
            fas, fbs = self._faces(ia), self._faces(ib)
            if not a_chosen: self._check_ambiguous(fas, "A", "Crop the photo to the person, or tick 'Image A is a group photo' to choose the face.")
            self._check_ambiguous(fbs, "B", "Crop the reference photo to the person you want to compare.")
            fa, fb = self._pick(fas, ia, "central" if a_chosen else "largest"), self._pick(fbs, ib)
            pa, na = self._landmarks(ia, None if fa is None else fa.bbox); pb, nb = self._landmarks(ib, None if fb is None else fb.bbox)
            if pa is None or pb is None:
                raise ValueError("No face found in " + ("image A" if pa is None else "image B") + ".")
        ea = None if fa is None else fa.normed_embedding
        eb = None if fb is None else fb.normed_embedding
        age = age_assess(self._age(fa), self._age(fb), age_gap)
        qa, qb = self._quality(ia, pa, na), self._quality(ib, pb, nb)
        iod = np.linalg.norm(pa[33] - pa[263])
        s, R, mu_b, mu_a = procrustes(pa, pb)
        pb_al = s * ((pb - mu_b) @ R) + mu_a
        M = np.hstack([s * R.T, (mu_a - s * R.T @ mu_b)[:, None]])
        b_al = cv2.warpAffine(ib, M, (ia.shape[1], ia.shape[0]), borderMode=cv2.BORDER_REPLICATE)
        resid = np.linalg.norm(pb_al - pa, axis=1) / iod
        shape_d = float(np.sqrt((resid ** 2).mean()))
        regions = [{"name": k, "points": len(v), "distance": round(float(np.sqrt((resid[v] ** 2).mean())), 4),
                    "agreement": agree(float(np.sqrt((resid[v] ** 2).mean())))} for k, v in REGIONS.items()]
        ratios = []
        for k, (i, j) in RATIOS.items():
            norm = lambda p: np.linalg.norm(p[234] - p[454]) if k == "Face width" else np.linalg.norm(p[33] - p[263])
            ra, rb = np.linalg.norm(pa[i] - pa[j]) / norm(pa), np.linalg.norm(pb[i] - pb[j]) / norm(pb)
            ratios.append({"name": k, "a": round(float(ra), 3), "b": round(float(rb), 3),
                           "diff_pct": round(float(abs(ra - rb) / ((ra + rb) / 2) * 100), 1)})
        mean_diff = round(float(np.mean([r["diff_pct"] for r in ratios])), 1)
        geo = {"shape_distance": round(shape_d, 4), "agreement_index": agree(shape_d),
               "mean_ratio_diff_pct": mean_diff, "regions": regions, "ratios": ratios}
        cos = float(np.dot(ea, eb)) if ea is not None and eb is not None else None
        concl = self._conclude(cos, geo, qa, qb, age)
        return {
            "landmarks": {"count": len(pa), "regions": REGIONS, "a": pa.round(1).tolist(), "b": pb.round(1).tolist(),
                          "b_aligned": pb_al.round(1).tolist()},
            "quality": {"a": qa, "b": qb}, "geometry": geo,
            "embedding": {"available": cos is not None, "model": "InsightFace buffalo_l (ArcFace)" if self.arc else None,
                          "cosine": None if cos is None else round(cos, 4), "error": self.arc_error},
            "integrity": {"a": integrity.screen(ia, ma), "b": integrity.screen(ib, mb)},
            "age": age, "conclusion": concl}, b_al, pb_al

    def _conclude(self, cos, geo, qa, qb, age=None):
        flags = []
        hard = qa["hard_issues"] + qb["hard_issues"]; soft = qa["soft_issues"] + qb["soft_issues"]
        if cos is None:
            return {"level": 2, "label": LABELS[2], "flags": ["Face-recognition model unavailable; geometry alone cannot support an identity conclusion."],
                    "rationale": []}
        level = sum(cos >= c for c in COS_CUTS)
        rationale = [f"Embedding cosine similarity {cos:.3f} maps to: {LABELS[level]}."]
        aged = bool(age) and age["rule"] != "none"
        if hard:
            level = 2; flags += hard; rationale.append("Image quality is below the minimum for a conclusion.")
        else:
            flags += soft
            if soft and level != 2: level += 1 if level < 2 else -1
            frontal = max(abs(qa["yaw"]), abs(qb["yaw"])) < 25
            ai = geo["agreement_index"]
            if frontal and not aged and ((level >= 3 and ai < 55) or (level <= 1 and ai > 85)):
                level += 1 if level < 2 else -1
                flags.append("Landmark geometry disagrees with the embedding result; conclusion moved toward inconclusive.")
        if age and age.get("message"):
            flags.append(age["message"])
            if age["rule"] == "block": level = 2
            elif age["rule"] == "cap": level = 2 if level < 2 else 3 if level == 4 else level
            elif age["rule"] == "soft" and level != 2: level += 1 if level < 2 else -1
            if aged: rationale.append("Age safeguard applied to the verdict.")
        rationale.append(f"Landmark agreement index {geo['agreement_index']}/100 across {len(REGIONS['cheeks_forehead']) + sum(len(v) for k, v in REGIONS.items() if k != 'cheeks_forehead')} points.")
        return {"level": level, "label": LABELS[level], "flags": flags, "rationale": rationale}

def annotate(img, pts, color, extra=None, extra_color=(31, 160, 245)):
    out = img.copy()
    for p in pts: cv2.circle(out, (int(p[0]), int(p[1])), 2, color, -1, cv2.LINE_AA)
    if extra is not None:
        for p in extra: cv2.circle(out, (int(p[0]), int(p[1])), 2, extra_color, -1, cv2.LINE_AA)
    return out
