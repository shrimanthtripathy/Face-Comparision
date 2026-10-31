import os, tempfile
os.environ["NODAL_DATA_DIR"] = tempfile.mkdtemp(prefix="nodal-test-")  # must be set before backend is imported
os.environ["NODAL_SECRET"] = "test-secret"
import cv2, numpy as np, pytest

def fake_result():
    pts = [[20 + (i % 20) * 8, 20 + (i // 20) * 6] for i in range(478)]
    q = {"sharpness": 120, "brightness": 110, "inter_ocular_px": 90, "pitch": 1, "yaw": 2, "roll": 0, "width": 200, "height": 200, "hard_issues": [], "soft_issues": []}
    ig = {"flag": "no indicators", "ela_mean": 1.0, "ela_p99": 3.0, "hf_ratio": 0.08, "model_probability": None, "notes": []}
    return {"landmarks": {"count": 478, "regions": {"nose": [1, 2]}, "a": pts, "b": pts, "b_aligned": pts}, "quality": {"a": q, "b": q},
            "geometry": {"agreement_index": 70.0, "shape_distance": 0.03, "mean_ratio_diff_pct": 4.0,
                         "regions": [{"name": "nose", "points": 2, "distance": 0.02, "agreement": 90}],
                         "ratios": [{"name": "Nose width", "a": 0.5, "b": 0.5, "diff_pct": 0.0}]},
            "embedding": {"available": True, "model": "fake", "cosine": 0.6, "error": None}, "integrity": {"a": ig, "b": ig},
            "conclusion": {"level": 4, "label": "Strong support for the same identity", "flags": [], "rationale": ["fake"]}}

class FakeEngine:
    arc, arc_error = None, None
    def scan(self, group, ref, det_size=1280):
        return [{"index": 0, "bbox": [10, 10, 60, 60], "size_px": 50, "det_score": 0.9, "cosine": 0.62, "age": 30, "rank": 1},
                {"index": 1, "bbox": [100, 20, 150, 70], "size_px": 50, "det_score": 0.8, "cosine": 0.10, "age": 25, "rank": 2}]
    def compare(self, ia, ib, ma, mb, age_gap=None, a_chosen=False):
        return fake_result(), cv2.resize(ib, (ia.shape[1], ia.shape[0])), np.zeros((478, 2))

@pytest.fixture(autouse=True)
def default_cuts(monkeypatch):   # tests must not depend on a calibration.json produced on your machine
    from backend import engine as E
    monkeypatch.setattr(E, "COS_CUTS", [0.15, 0.25, 0.40, 0.55])

@pytest.fixture
def jpeg():
    return cv2.imencode(".jpg", np.random.default_rng(1).integers(0, 255, (200, 200, 3), dtype=np.uint8))[1].tobytes()

@pytest.fixture
def app_env(monkeypatch):
    from backend import db as D, main
    monkeypatch.setattr(main.E, "Engine", FakeEngine)
    with D.db() as c: c.execute("DELETE FROM users"); c.execute("DELETE FROM audit")
    main.limiter.reset()
    D.create_user("alice", "correct horse battery", "examiner"); D.create_user("bob", "another long password", "examiner")
    D.create_user("root", "administrator password", "admin")
    return main

@pytest.fixture
def client(app_env):
    from fastapi.testclient import TestClient
    with TestClient(app_env.app) as c: yield c

def sign_in(client, user, pw):
    client.cookies.clear()
    return client.post("/api/login", json={"username": user, "password": pw})
