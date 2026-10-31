"""Re-scores the worst same-person pairs with different face-selection rules and detector sizes, to find out why they score so low.
   python benchmark/recheck_worst.py      (takes a minute or two; needs benchmark/worst_pairs.csv)"""
import csv, os, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.engine import Engine, load_image

here = Path(__file__).parent
rows = [r for r in csv.DictReader(open(here / "worst_pairs.csv", newline="")) if r["kind"] == "same_person_low_score"]
eng = Engine(mesh=False, age=False)
cache = {}

def detect(path, size):
    if (path, size) not in cache:
        img = load_image(Path(path).read_bytes())[0]
        eng.arc.prepare(ctx_id=-1, det_size=(size, size)); cache[(path, size)] = (img, eng.arc.get(img))
    return cache[(path, size)]

def pick(fs, img, how):
    if not fs: return None
    h, w = img.shape[:2]
    if how == "largest": return max(fs, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
    return min(fs, key=lambda f: np.hypot((f.bbox[0] + f.bbox[2]) / 2 - w / 2, (f.bbox[1] + f.bbox[3]) / 2 - h / 2))   # face nearest the image centre

cols = ["old", "320 largest", "320 central", "640 largest", "640 central"]
print(f"{'person':28}" + "".join(f"{c:>13}" for c in cols) + "   faces found (A,B) at 320 / 640")
table = []
for r in rows:
    name = Path(r["path_a"]).parent.name[:27]; line = [float(r["score"])]; counts = []
    for size in (320, 640):
        (ia, fa), (ib, fb) = detect(r["path_a"], size), detect(r["path_b"], size)
        counts.append(f"({len(fa)},{len(fb)})")
        for how in ("largest", "central"):
            A, B = pick(fa, ia, how), pick(fb, ib, how)
            line.append(np.nan if A is None or B is None else float(np.dot(A.normed_embedding, B.normed_embedding)))
    table.append(line)
    print(f"{name:28}" + "".join(f"{v:13.3f}" for v in line) + "   " + " / ".join(counts))
t = np.array(table)
print("\nMean score :" + "".join(f"{np.nanmean(t[:, i]):13.3f}" for i in range(5)))
print("Pairs above 0.25 (a normal same-person score): " + ", ".join(f"{c}: {int((t[:, i] > 0.25).sum())}/{len(t)}" for i, c in enumerate(cols)))
