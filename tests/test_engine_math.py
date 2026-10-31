import cv2, numpy as np
from backend import engine as E

def test_procrustes_recovers_similarity_transform():
    A = np.random.default_rng(0).normal(size=(478, 2)) * 100 + 300
    th = 0.3; R0 = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    B = 1.4 * (A @ R0) + [40, -25]
    s, R, mb, ma = E.procrustes(A, B)
    assert np.abs(s * ((B - mb) @ R) + ma - A).max() < 1e-6

def test_pose_estimate_matches_synthetic_rotation():
    cam = np.array([[800, 0, 400], [0, 800, 400], [0, 0, 1.]])
    for yaw in (0, 30):
        proj, _ = cv2.projectPoints(E.MODEL3D, np.array([0, np.radians(yaw), 0.]), np.array([0, 0, 600.]), cam, np.zeros(4))
        pts = np.zeros((478, 2)); pts[E.POSE_IDX] = proj.reshape(-1, 2)
        assert abs(E.pose(pts, 800, 800)[1] - yaw) < 1.0

def test_landmark_regions_cover_every_point_once():
    allp = [i for v in E.REGIONS.values() for i in v]
    assert len(set(range(478)) - set(allp)) == 0 and len(allp) >= 478

def test_agreement_index_is_monotonic_and_bounded():
    v = [E.agree(d) for d in (0.0, 0.02, 0.04, 0.1)]
    assert v == sorted(v, reverse=True) and v[0] == 100 and v[-1] == 0

def _eng():
    e = E.Engine.__new__(E.Engine); e.arc = None; return e
Q = {"hard_issues": [], "soft_issues": [], "yaw": 5, "pitch": 0}

def test_verdict_scale_follows_cosine():
    labels = [_eng()._conclude(c, {"agreement_index": 80}, Q, Q)["label"] for c in (0.7, 0.45, 0.3, 0.2, 0.05)]
    assert labels == E.LABELS[::-1]

def test_poor_quality_forces_inconclusive():
    bad = {**Q, "hard_issues": ["blurred"]}
    assert _eng()._conclude(0.9, {"agreement_index": 90}, bad, Q)["level"] == 2

def test_geometry_conflict_downgrades_one_step():
    assert _eng()._conclude(0.7, {"agreement_index": 30}, Q, Q)["level"] == 3

def test_missing_model_never_gives_identity_conclusion():
    assert _eng()._conclude(None, {"agreement_index": 99}, Q, Q)["level"] == 2
