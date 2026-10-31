"""Build benchmark/pairs.csv from the official LFW pairs.txt (a fixed, public pair list).
  python benchmark/make_lfw_pairs.py --lfw-dir path/to/lfw --pairs-txt path/to/pairs.txt"""
import argparse, csv
from pathlib import Path
ap = argparse.ArgumentParser(); ap.add_argument("--lfw-dir", required=True); ap.add_argument("--pairs-txt", required=True)
ap.add_argument("--out", default=str(Path(__file__).parent / "pairs.csv")); a = ap.parse_args()
img = lambda n, i: str(Path(a.lfw_dir).resolve() / n / f"{n}_{int(i):04d}.jpg")
rows = []
for line in open(a.pairs_txt).read().split("\n")[1:]:
    t = line.split()
    if len(t) == 3: rows.append((img(t[0], t[1]), img(t[0], t[2]), 1))
    elif len(t) == 4: rows.append((img(t[0], t[1]), img(t[2], t[3]), 0))
with open(a.out, "w", newline="") as f:
    w = csv.writer(f); w.writerow(["path_a", "path_b", "label"]); w.writerows(rows)
print(len(rows), "pairs written to", a.out)
