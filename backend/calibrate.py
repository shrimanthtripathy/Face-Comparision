"""Turns benchmark results into verdict cut-offs.   python -m backend.calibrate    (run after python -m backend.benchmark; takes seconds)
Different-person scores come from ALL different-identity pairs among the cached images (tens of millions), so error rates down to
about 1 in a million can be estimated. Same-person scores come from the labelled pairs. A safety margin is added because LFW is
easier than most casework. Result: backend/calibration.json, which the app loads automatically. Also writes benchmark/top_negatives.csv (the most similar 'different' pairs, to spot labelling errors)."""
import argparse, csv, json, pickle, sys
from datetime import date
from pathlib import Path
import numpy as np
from .engine import pick_index

ROOT = Path(__file__).resolve().parent.parent
EDGES = np.linspace(-1, 1, 2001)
MIN_GAP = 0.01

def threshold_at_fmr(counts, target):
    """Smallest score threshold at which at most `target` of different-person pairs score at or above it."""
    total, cum = counts.sum(), 0
    for i in range(len(counts) - 1, -1, -1):
        cum += counts[i]
        if cum / total > target: return float(EDGES[i + 1])
    return float(EDGES[0])

def make_cuts(pos, counts, margin=0.05, fmr_same=(1e-3, 1e-5), fmr_diff=1e-2, strong_diff_pct=0.1):
    """[strong different below, moderate different below, moderate same from, strong same from].
    Same-side cut-offs come from false-match rates; moderate 'different' is the score that 99% of different-person pairs stay under
    (so only a tiny share of same-person pairs fall there); strong 'different' is the 0.1th percentile of same-person scores.
    The margin moves every cut-off toward 'inconclusive'. The band in between is the inconclusive zone."""
    cuts = [float(np.percentile(pos, strong_diff_pct)) - margin, threshold_at_fmr(counts, fmr_diff) - margin,
            threshold_at_fmr(counts, fmr_same[0]) + margin, threshold_at_fmr(counts, fmr_same[1]) + margin]
    for i in range(1, 4): cuts[i] = max(cuts[i], cuts[i - 1] + MIN_GAP)
    return [round(c, 3) for c in cuts]

def run(pairs_csv, cache_path=None, det_size=320, face_rule="central", margin=0.05, out=None):
    pairs_csv = Path(pairs_csv)
    try: cache = pickle.load(open(cache_path or pairs_csv.parent / "embeddings_cache_v2.pkl", "rb"))
    except FileNotFoundError: sys.exit("No benchmark cache found. Run: python -m backend.benchmark --update-baseline")
    embs = {}
    for k, c in cache.items():
        d, path = k.split("|", 1)
        if int(d) == det_size and c["faces"]: embs[path] = c["faces"][pick_index([b for b, _ in c["faces"]], c["w"], c["h"], face_rule)][1]
    if not embs: sys.exit("The cache is empty for this detector size.")
    paths = list(embs); X = np.stack([embs[p] for p in paths]).astype(np.float32); n = len(paths)
    ids = {}; idn = np.array([ids.setdefault(Path(p).parent.name, len(ids)) for p in paths])
    counts = np.zeros(len(EDGES) - 1, dtype=np.int64); CH = 400; top = []
    print(f"Comparing {n} images from {len(ids)} people...", flush=True)
    for i in range(0, n, CH):
        S = X[i:i + CH] @ X.T
        mask = (idn[i:i + CH, None] != idn[None, :]) & (np.arange(n)[None, :] > np.arange(i, min(i + CH, n))[:, None])
        counts += np.histogram(S[mask], bins=EDGES)[0]
        top += [(float(S[r, c]), i + int(r), int(c)) for r, c in np.argwhere(mask & (S >= 0.45))]   # suspiciously similar 'different' pairs
    resolve = lambda p: str(Path(p) if Path(p).is_absolute() else pairs_csv.parent / p)
    pos = np.array([float(np.dot(embs[resolve(r["path_a"])], embs[resolve(r["path_b"])])) for r in csv.DictReader(open(pairs_csv, newline=""))
                    if int(r["label"]) == 1 and resolve(r["path_a"]) in embs and resolve(r["path_b"]) in embs])
    if len(pos) < 1000: print(f"Warning: only {len(pos)} same-person pairs, so the 'strong different' cut-off is rough.")
    print(f"{int(counts.sum()):,} different-person pairs, {len(pos)} same-person pairs\n\n  error rate         threshold   same-person pairs missed")
    for t in (1e-2, 1e-3, 1e-4, 1e-5, 1e-6):
        th = threshold_at_fmr(counts, t); print(f"  {t:<8.0e} false match  {th:8.3f}   {100 * (pos < th).mean():6.2f} %")
    top.sort(reverse=True)
    if top:
        print(f"\n{len(top)} different-person pairs score 0.45 or more. Highest:")
        for sc, a_, b_ in top[:20]: print(f"  {sc:.3f}  {Path(paths[a_]).parent.name}  vs  {Path(paths[b_]).parent.name}")
        print("If these look like the same person filed under two names, they are labelling errors in LFW, not model failures.")
        with open(pairs_csv.parent / "top_negatives.csv", "w", newline="") as f:
            w = csv.writer(f); w.writerow(["kind", "score", "path_a", "path_b"])
            for sc, a_, b_ in top[:60]: w.writerow(["different_people_high_score", round(sc, 4), paths[a_], paths[b_]])
    cuts = make_cuts(pos, counts, margin)
    info = {"cos_cuts": cuts, "created": date.today().isoformat(), "margin": margin, "face_rule": face_rule, "det_size": det_size,
            "n_positive_pairs": int(len(pos)), "n_negative_pairs": int(counts.sum()), "source": "LFW",
            "rule": "strong same: false-match rate 1 in 100,000; moderate same: 1 in 1,000; moderate different: below the score 99% of different-person pairs stay under; strong different: below the 0.1th percentile of same-person scores; margin applied toward inconclusive"}
    out = Path(out or ROOT / "backend" / "calibration.json"); out.write_text(json.dumps(info, indent=2))
    print(f"\nCut-offs [strong different, moderate different, moderate same, strong same] = {cuts}\n(margin {margin} on the cautious side)\nSaved to {out}. Restart the app to use them.")
    return info

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--pairs", default=str(ROOT / "benchmark" / "pairs.csv"))
    ap.add_argument("--margin", type=float, default=0.05); ap.add_argument("--det-size", type=int, default=320)
    ap.add_argument("--face-rule", choices=["central", "largest"], default="central"); a = ap.parse_args()
    run(a.pairs, det_size=a.det_size, face_rule=a.face_rule, margin=a.margin)
