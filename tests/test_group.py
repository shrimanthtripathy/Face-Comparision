import numpy as np
import pytest
from backend import engine as E, report
from conftest import fake_result, sign_in

class Face:
    def __init__(self, box, emb, score=0.9, age=30): self.bbox, self.det_score, self.age = box, score, age; self.normed_embedding = np.array(emb, float)

class Det: input_size = (640, 640)
class Arc:
    det_model = Det()
    def __init__(self, faces): self.faces, self.seen = faces, []
    def get(self, img): self.seen.append(self.det_model.input_size); return list(self.faces[img.shape[0]])

def _eng(group_faces, ref_faces):
    e = E.Engine.__new__(E.Engine); import threading; e.lock = threading.Lock()
    e.arc = Arc({50: group_faces, 40: ref_faces}); e.arc_error = None; return e

def test_scan_ranks_faces_by_similarity_and_restores_detector_size():
    ref = [Face([0, 0, 30, 30], [1, 0, 0])]
    group = [Face([0, 0, 20, 20], [0.2, 0.98, 0], 0.95), Face([30, 0, 60, 30], [0.99, 0.1, 0], 0.9), Face([70, 0, 90, 20], [0, 0, 1], 0.8)]
    e = _eng(group, ref); out = e.scan(np.zeros((50, 50, 3), np.uint8), np.zeros((40, 40, 3), np.uint8))
    best = [f for f in out if f["rank"] == 1][0]
    assert len(out) == 3 and best["bbox"] == [30, 0, 60, 30] and sorted(f["rank"] for f in out) == [1, 2, 3]
    assert e.arc.det_model.input_size == (640, 640) and (1280, 1280) in e.arc.seen   # larger size used for the group, then restored

def test_scan_needs_a_reference_face_and_a_model():
    with pytest.raises(ValueError): _eng([Face([0, 0, 9, 9], [1, 0, 0])], []).scan(np.zeros((50, 50, 3), np.uint8), np.zeros((40, 40, 3), np.uint8))
    e = E.Engine.__new__(E.Engine); e.arc = None
    with pytest.raises(ValueError): e.scan(None, None)

def test_report_with_group_section_builds():
    import cv2
    res = fake_result(); q = res["quality"]["a"]
    res.update({"case_id": "abc123abc123", "created_at": "2026-10-29 10:00", "meta": {"case_ref": "", "examiner": "", "purpose": "", "operator": None},
                "inputs": {k: {"filename": k, "sha256": "a" * 64, "bytes": 1} for k in "ab"}, "method": {"version": "1.0", "versions": "t"},
                "group": {"scan_id": "x", "faces_searched": 5, "face_number": 3, "rank": 1, "scan_cosine": 0.61, "selected_by": "examiner", "bbox": [1, 2, 3, 4]}})
    im = cv2.imencode(".jpg", np.full((200, 300, 3), 120, np.uint8))[1].tobytes()
    pdf = report.build(res, {"a": im, "b": im, "overlay": im, "group": im}); assert pdf[:5] == b"%PDF-" and len(pdf) > 5000

def test_group_flow_through_the_api(client, jpeg):
    sign_in(client, "alice", "correct horse battery")
    files = {"a": ("group.jpg", jpeg, "image/jpeg"), "b": ("ref.jpg", jpeg, "image/jpeg")}
    s = client.post("/api/group/scan", files=files, data={"consent": "true"}).json()
    assert len(s["faces"]) == 2 and s["notes"]
    assert client.get(s["image"]).status_code == 200
    assert client.post(f"/api/scan/{s['scan_id']}/compare", data={"face": "9"}).status_code == 422
    r = client.post(f"/api/scan/{s['scan_id']}/compare", data={"face": "0", "case_ref": "G-1"}); assert r.status_code == 200
    j = r.json(); assert j["group"]["face_number"] == 1 and j["group"]["faces_searched"] == 2
    assert client.get(f"/api/case/{j['case_id']}/report.pdf").content[:5] == b"%PDF-"
    sign_in(client, "bob", "another long password"); assert client.get(s["image"]).status_code == 404
