import csv, json, pickle
import numpy as np
from backend import calibrate as C

def _counts(scores): return np.histogram(scores, bins=C.EDGES)[0]

def test_threshold_matches_the_theoretical_tail():
    neg = np.random.default_rng(0).normal(0.0, 0.1, 2_000_000)
    assert abs(C.threshold_at_fmr(_counts(neg), 1e-3) - 0.309) < 0.012          # 3.09 standard deviations
    assert C.threshold_at_fmr(_counts(neg), 1e-2) < C.threshold_at_fmr(_counts(neg), 1e-4)

def test_cuts_are_ordered_and_margin_is_on_the_cautious_side():
    r = np.random.default_rng(1); neg = _counts(r.normal(0.0, 0.1, 1_000_000)); pos = r.normal(0.6, 0.1, 3000)
    a, b = C.make_cuts(pos, neg, margin=0.0), C.make_cuts(pos, neg, margin=0.05)
    assert a == sorted(a) and b == sorted(b) and len(set(b)) == 4 and b[2] - b[1] >= 0.05   # a real inconclusive band remains
    assert b[0] < a[0] and b[1] < a[1] and b[2] > a[2] and b[3] > a[3]            # harder to claim either verdict

def test_run_end_to_end_on_a_synthetic_cache(tmp_path):
    r = np.random.default_rng(2); rows = [["path_a", "path_b", "label"]]; cache = {}
    def emb(centre): v = centre + 0.25 * r.normal(size=64); return v / np.linalg.norm(v)
    for p in range(40):
        centre = r.normal(size=64); names = []
        for k in range(3):
            path = str(tmp_path / f"person{p}" / f"img{k}.jpg"); names.append(path)
            cache[f"320|{path}"] = {"w": 100, "h": 100, "faces": [([10.0, 10.0, 90.0, 90.0], emb(centre))]}
        rows += [[names[0], names[1], 1], [names[1], names[2], 1]]
    pickle.dump(cache, open(tmp_path / "cache.pkl", "wb")); csv.writer(open(tmp_path / "pairs.csv", "w", newline="")).writerows(rows)
    info = C.run(tmp_path / "pairs.csv", cache_path=tmp_path / "cache.pkl", out=tmp_path / "cal.json")
    assert json.load(open(tmp_path / "cal.json"))["cos_cuts"] == info["cos_cuts"] and info["cos_cuts"] == sorted(info["cos_cuts"])
    assert info["n_negative_pairs"] == (120 * 119 // 2) - 40 * 3 and info["n_positive_pairs"] == 80
