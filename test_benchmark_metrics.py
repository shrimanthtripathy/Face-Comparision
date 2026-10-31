import json, os, sys
from pathlib import Path
import numpy as np, pytest
from backend import benchmark as B

def test_perfect_separation():
    m = B.metrics([0.9, 0.8, 0.1, 0.0], [1, 1, 0, 0]); assert m["auc"] == 1.0 and m["eer"] == 0.0

def test_random_scores_are_near_chance():
    r = np.random.default_rng(0); m = B.metrics(r.random(2000), r.integers(0, 2, 2000)); assert abs(m["auc"] - 0.5) < 0.05

def test_threshold_at_fmr_gives_zero_false_matches_when_strict():
    m = B.metrics([0.9, 0.7, 0.6, 0.3, 0.2, 0.1], [1, 1, 1, 0, 0, 0]); assert m["fnmr_at_fmr_1e-3"] == 0.0 and m["threshold_fmr_1e-3"] > 0.3

def test_regression_gate():
    base = {"auc": 0.99, "eer": 0.02, "fail_rate": 0.0}
    assert not B.regressions(base, {"auc": 0.99, "eer": 0.02, "fail_rate": 0.0})
    assert B.regressions(base, {"auc": 0.97, "eer": 0.02, "fail_rate": 0.0})
    assert B.regressions(base, {"auc": 0.99, "eer": 0.05, "fail_rate": 0.0})
    assert B.regressions(base, {"auc": 0.99, "eer": 0.02, "fail_rate": 0.1})

def test_real_benchmark_has_not_regressed():
    """Runs only when benchmark/pairs.csv, baseline.json and the InsightFace model exist."""
    pairs, base = B.ROOT / "benchmark" / "pairs.csv", B.ROOT / "benchmark" / "baseline.json"
    pytest.importorskip("insightface")
    if not (pairs.exists() and base.exists()): pytest.skip("Create pairs.csv and run: python -m backend.benchmark --update-baseline")
    assert not B.regressions(json.loads(base.read_text()), B.run(pairs))

def test_metrics_need_both_kinds_of_pairs():
    with pytest.raises(ValueError): B.metrics([0.9, 0.8], [1, 1])

def test_run_samples_caches_and_resumes(tmp_path, monkeypatch):
    import csv, cv2
    from backend import engine as E
    calls = []
    class Fake:
        arc = type("A", (), {"prepare": lambda self, **k: None})()
        arc_error = None
        def __init__(self, mesh=True, age=True): pass
        def _embed(self, img):
            calls.append(1); v = img.reshape(-1, 3).mean(0).astype(float) + 1.0; return v / np.linalg.norm(v)
    monkeypatch.setattr(E, "Engine", Fake)
    rng = np.random.default_rng(0); files = []
    for i in range(6):
        p = tmp_path / f"{i}.png"; cv2.imwrite(str(p), np.full((20, 20, 3), (40 * i + 10, 255 - 30 * i, 20 * i + 5), np.uint8)); files.append(p.name)
    with open(tmp_path / "pairs.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["path_a", "path_b", "label"])
        for i in range(6): w.writerow([files[i], files[i], 1]); w.writerow([files[i], files[(i + 3) % 6], 0])
    m = B.run(tmp_path / "pairs.csv", limit=8)
    assert m["pairs"] == 8 and m["fail_rate"] == 0 and (tmp_path / "embeddings_cache.pkl").exists()
    first = len(calls); m2 = B.run(tmp_path / "pairs.csv", limit=8)
    assert len(calls) == first and m2["auc"] == m["auc"]          # second run reuses the cache
    B.run(tmp_path / "pairs.csv", limit=8, worst=2); assert len(list(csv.reader(open(tmp_path / "worst_pairs.csv")))) == 5   # header + 2 + 2
