"""Turns benchmark/worst_pairs.csv into two pictures you can look at (and upload for review):
   python benchmark/make_contact_sheet.py   ->  benchmark/worst_same.jpg  and  benchmark/worst_different.jpg"""
import csv, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageOps

H, here = 200, Path(__file__).parent
name = sys.argv[1] if len(sys.argv) > 1 else "worst_pairs.csv"   # e.g. top_negatives.csv
rows = list(csv.DictReader(open(here / name, newline="")))

def load(p):
    p = Path(p); p = p if p.is_absolute() else here / p
    try: return ImageOps.exif_transpose(Image.open(p)).convert("RGB").resize((H, H))
    except Exception: return Image.new("RGB", (H, H), "gray")

def cell(r):
    c = Image.new("RGB", (2 * H + 6, H + 22), "white")
    c.paste(load(r["path_a"]), (0, 22)); c.paste(load(r["path_b"]), (H + 6, 22))
    ImageDraw.Draw(c).text((4, 4), f"similarity {r['score']}", fill="black"); return c

def sheet(kind, out, cols=3, limit=12):
    cells = [cell(r) for r in [r for r in rows if r["kind"] == kind][:limit]]
    if not cells: return
    w, h = cells[0].size; n = (len(cells) + cols - 1) // cols
    S = Image.new("RGB", (cols * (w + 10), n * (h + 10)), "white")
    for i, c in enumerate(cells): S.paste(c, ((i % cols) * (w + 10), (i // cols) * (h + 10)))
    S.save(here / out, quality=90); print("Saved", here / out)

stem = Path(name).stem
sheet("same_person_low_score", "worst_same.jpg" if stem == "worst_pairs" else f"{stem}_same.jpg")
sheet("different_people_high_score", "worst_different.jpg" if stem == "worst_pairs" else f"{stem}.jpg")
