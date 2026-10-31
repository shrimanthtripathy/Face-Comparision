"""Regression benchmark on a fixed list of labelled pairs.
  python -m backend.benchmark --limit 300       quick test on a fixed random sample (a few minutes)
  python -m backend.benchmark                    compare with benchmark/baseline.json (exit 1 on regression)
  python -m backend.benchmark --update-baseline  accept the current numbers as the new baseline
pairs.csv columns: path_a,path_b,label   (label 1 = same person, 0 = different people)"""
import argparse, csv, json, pickle, random, sys, time
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
TOL = {"auc": 0.005, "eer": 0.01, "fail_rate": 0.02}

def metrics(scores, labels):
    s, y = np.asarray(scores, float), np.asarray(labels, int)
    pos, neg = s[y == 1], s[y == 0]
    if len(pos) == 0 or len(neg) == 0: raise ValueError("Need both same-person and different-person pairs.")
    auc = ((pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()) / (len(pos) * len(neg))
    ts = np.unique(s)
    fmr = np.array([(neg >= t).mean() for t in ts]); fnmr = np.array([(pos < t).mean() for t in ts])
    i = int(np.argmin(np.abs(fmr - fnmr)))
    out = {"n_pos": int(len(pos)), "n_neg": int(len(neg)), "auc": round(float(auc), 4), "eer": round(float((fmr[i] + fnmr[i]) / 2), 4)}
    for tag, target in (("1e-2", 1e-2), ("1e-3", 1e-3)):
        ok = np.where(fmr <= target)[0]
        j = int(ok[0]) if len(ok) else len(ts) - 1
        out[f"threshold_fmr_{tag}"] = round(float(ts[j]), 4); out[f"fnmr_at_fmr_{tag}"] = round(float(fnmr[j]), 4)
    return out

def regressions(base, cur):
    bad = []
    if cur["auc"] < base["auc"] - TOL["auc"]: bad.append(f"AUC fell {base['auc']} -> {cur['auc']}")
    if cur["eer"] > base["eer"] + TOL["eer"]: bad.append(f"EER rose {base['eer']} -> {cur['eer']}")
    if cur["fail_rate"] > base["fail_rate"] + TOL["fail_rate"]: bad.append(f"face-detection failures rose {base['fail_rate']} -> {cur['fail_rate']}")
    return bad

def _save(cache, path):
    with open(path, "wb") as f: pickle.dump(cache, f)

def run(pairs_csv, limit=None, det_size=320, cache_path=None, worst=0):
    from .engine import Engine, load_image
    print("Loading models (the first run downloads about 280 MB, please wait)...", flush=True)
    eng = Engine(mesh=False, age=False)
    if eng.arc is None: sys.exit("InsightFace model unavailable: " + str(eng.arc_error))
    eng.arc.prepare(ctx_id=-1, det_size=(det_size, det_size))   # LFW images are small, so a smaller detector size is much faster
    pairs_csv = Path(pairs_csv); rows = list(csv.DictReader(open(pairs_csv, newline="")))
    if limit and limit < len(rows): rows = random.Random(0).sample(rows, limit)   # fixed seed = the same sample every time
    cache_path = Path(cache_path or pairs_csv.parent / "embeddings_cache.pkl")
    try: cache = pickle.load(open(cache_path, "rb"))
    except Exception: cache = {}
    resolve = lambda p: Path(p) if Path(p).is_absolute() else pairs_csv.parent / p
    def emb(p):
        k = f"{det_size}|{resolve(p)}"
        if k not in cache:
            try: cache[k] = eng._embed(load_image(resolve(p).read_bytes())[0])
            except Exception: cache[k] = None
        return cache[k]
    print(f"Comparing {len(rows)} pairs ({len(cache)} images already cached). Ctrl+C is safe: progress is saved.", flush=True)
    scores, labels, failed, t0, records = [], [], 0, time.time(), []
    try:
        for i, r in enumerate(rows, 1):
            ea, eb = emb(r["path_a"]), emb(r["path_b"])
            if ea is None or eb is None: failed += 1
            else:
                scores.append(float(np.dot(ea, eb))); labels.append(int(r["label"])); records.append((r["path_a"], r["path_b"], labels[-1], scores[-1]))
            if i % 100 == 0:
                el = time.time() - t0
                print(f"  {i}/{len(rows)} pairs, {el:.0f}s elapsed, about {el / i * (len(rows) - i):.0f}s left", flush=True)
            if i % 500 == 0: _save(cache, cache_path)
    except KeyboardInterrupt:
        _save(cache, cache_path); print("Stopped. Progress saved; run the same command again to resume.", flush=True); sys.exit(130)
    _save(cache, cache_path)
    if worst:   # the pairs the model gets most wrong: look at these images to see why
        lo = sorted((x for x in records if x[2] == 1), key=lambda x: x[3])[:worst]; hi = sorted((x for x in records if x[2] == 0), key=lambda x: -x[3])[:worst]
        out = pairs_csv.parent / "worst_pairs.csv"
        with open(out, "w", newline="") as f:
            w = csv.writer(f); w.writerow(["kind", "score", "path_a", "path_b"])
            for a, b, l, s_ in lo: w.writerow(["same_person_low_score", round(s_, 4), a, b])
            for a, b, l, s_ in hi: w.writerow(["different_people_high_score", round(s_, 4), a, b])
        print(f"Wrote the {worst} lowest-scoring same-person pairs and the {worst} highest-scoring different-person pairs to {out}", flush=True)
    m = metrics(scores, labels); m["fail_rate"] = round(failed / max(len(rows), 1), 4); m["pairs"] = len(rows); m["det_size"] = det_size
    return m

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--pairs", default=str(ROOT / "benchmark" / "pairs.csv"))
    ap.add_argument("--baseline"); ap.add_argument("--update-baseline", action="store_true")
    ap.add_argument("--limit", type=int, help="use a fixed random sample of N pairs (quick test, separate baseline file)")
    ap.add_argument("--det-size", type=int, default=320)
    ap.add_argument("--worst", type=int, default=0, help="write the N worst same-person and different-person pairs to benchmark/worst_pairs.csv")
    a = ap.parse_args(); cur = run(a.pairs, a.limit, a.det_size, worst=a.worst); print(json.dumps(cur, indent=2))
    bp = Path(a.baseline or ROOT / "benchmark" / ("baseline_quick.json" if a.limit else "baseline.json"))
    if a.update_baseline or not bp.exists():
        bp.write_text(json.dumps(cur, indent=2)); print("Baseline saved to", bp); sys.exit(0)
    base = json.loads(bp.read_text())
    if base.get("pairs") != cur["pairs"] or base.get("det_size") != cur["det_size"]:
        print(f"Warning: baseline was recorded on {base.get('pairs')} pairs (detector size {base.get('det_size')}), this run used {cur['pairs']} ({cur['det_size']}).")
    bad = regressions(base, cur)
    print("REGRESSION:\n  " + "\n  ".join(bad) if bad else "No regression against baseline."); sys.exit(1 if bad else 0)
