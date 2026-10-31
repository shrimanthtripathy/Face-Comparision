import io
from datetime import datetime
from xml.sax.saxutils import escape as esc
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether

INK, LINE, TEAL = colors.HexColor("#1B2A35"), colors.HexColor("#C9D3D9"), colors.HexColor("#0B7285")
ss = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=ss["Title"], fontName="Times-Bold", fontSize=20, textColor=INK, alignment=0)
H2 = ParagraphStyle("h2", parent=ss["Heading2"], fontName="Times-Bold", fontSize=13, textColor=INK, spaceBefore=12, spaceAfter=4)
P = ParagraphStyle("p", parent=ss["BodyText"], fontName="Helvetica", fontSize=9, leading=12.5, textColor=INK)
SM = ParagraphStyle("sm", parent=P, fontSize=7.5, leading=10, textColor=colors.HexColor("#5B6B76"))

def _table(rows, widths, head=True):
    t = Table(rows, colWidths=widths, repeatRows=1 if head else 0)
    st = [("FONT", (0, 0), (-1, -1), "Helvetica", 8), ("TEXTCOLOR", (0, 0), (-1, -1), INK),
          ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    if head: st += [("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E6EBEE"))]
    t.setStyle(TableStyle(st)); return t

def _img(data, w):
    iw, ih = PILImage.open(io.BytesIO(data)).size
    return Image(io.BytesIO(data), width=w, height=w * ih / iw)

def build(res, imgs):
    buf = io.BytesIO()
    def footer(c, d):
        c.setFont("Helvetica", 7); c.setFillColor(colors.HexColor("#5B6B76"))
        c.drawString(18 * mm, 10 * mm, f"Case {res['case_id']} | Nodal {res['method']['version']} | decision-support output, requires examiner review")
        c.drawRightString(192 * mm, 10 * mm, f"Page {d.page}")
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=18 * mm,
                            title="Facial comparison report " + res["case_id"])
    c, g, e, m = res["conclusion"], res["geometry"], res["embedding"], res["meta"]
    S = [Paragraph("Facial comparison report", H1),
         Paragraph(f"Case {res['case_id']} &nbsp;|&nbsp; generated {res['created_at']} UTC", P), Spacer(1, 6),
         _table([["Case reference", esc(m["case_ref"] or "-")], ["Examiner", esc(m["examiner"] or "-")],
                 ["Operator", esc(", ".join(m["operator"][k] for k in ("name", "designation", "organisation")) if m.get("operator") else "-")], ["Purpose", esc(m["purpose"] or "-")], ["Consent recorded", "Yes (uploader confirmed lawful basis)"]], [40 * mm, 134 * mm], head=False),
         Paragraph("Conclusion", H2), Paragraph(f"<b>{c['label']}</b>", ParagraphStyle("c", parent=P, fontSize=12, textColor=TEAL))]
    for t in c["rationale"] + c["flags"]: S.append(Paragraph("- " + esc(t), P))
    S += [Paragraph("Input images", H2), _table(
        [["", "Image A (questioned)", "Image B (reference)"],
         ["File", esc(res["inputs"]["a"]["filename"]), esc(res["inputs"]["b"]["filename"])],
         ["SHA-256 (original upload)", res["inputs"]["a"]["sha256"][:32] + "...", res["inputs"]["b"]["sha256"][:32] + "..."],
         ["Working size (px)", f"{res['quality']['a']['width']} x {res['quality']['a']['height']}", f"{res['quality']['b']['width']} x {res['quality']['b']['height']}"]],
        [42 * mm, 66 * mm, 66 * mm]), Spacer(1, 4),
        Paragraph(f"Full hashes: A {res['inputs']['a']['sha256']}<br/>B {res['inputs']['b']['sha256']}", SM), Spacer(1, 6),
        Table([[_img(imgs["a"], 56 * mm), _img(imgs["b"], 56 * mm), _img(imgs["overlay"], 56 * mm)],
               [Paragraph("A with landmarks", SM), Paragraph("B with landmarks", SM), Paragraph("B aligned to A (A teal, B amber)", SM)]])]
    gp = res.get("group")
    if gp:
        S.append(Paragraph("Group photo search", H2))
        S.append(_table([["Item", "Value"], ["Faces found in the group photo", gp["faces_searched"]], ["Face selected (numbered in the image below)", gp["face_number"]],
                         ["Rank of that face by similarity to the reference", f"{gp['rank']} of {gp['faces_searched']}"], ["Similarity at scan", gp["scan_cosine"]], ["Selected by", gp["selected_by"]]], [80 * mm, 94 * mm]))
        S.append(Paragraph("Image A in this report is a crop of the selected face. Searching many faces raises the chance that one resembles the reference by chance, so the ranking is a lead only, and the selection was confirmed visually by the examiner.", P))
        if "group" in imgs: S.append(Spacer(1, 4)); S.append(_img(imgs["group"], 120 * mm))
    S += [Paragraph("Scores", H2), _table([["Measure", "Value", "Note"],
        ["Embedding cosine", "n/a" if e["cosine"] is None else f"{e['cosine']:.3f}", esc(e["model"] or "model unavailable")],
        ["Landmark agreement index", f"{g['agreement_index']} / 100", f"{res['landmarks']['count']} landmarks, Procrustes aligned, shape distance {g['shape_distance']}"],
        ["Mean proportion difference", f"{g['mean_ratio_diff_pct']} %", "10 facial proportions, normalised by inter-ocular distance"]], [48 * mm, 30 * mm, 96 * mm])]
    ag = res.get("age")
    if ag:
        S.append(Paragraph("Age considerations", H2))
        S.append(_table([["Item", "Value"], ["Estimated age A / B (approximate)", f"{ag['estimated_a'] if ag['estimated_a'] is not None else 'n/a'} / {ag['estimated_b'] if ag['estimated_b'] is not None else 'n/a'}"],
            ["Gap declared by examiner", "not given" if ag["declared_gap"] is None else f"{ag['declared_gap']} years"],
            ["Gap used", "unknown" if ag["gap"] is None else f"{ag['gap']:.0f} years ({ag['source']})"], ["Safeguard applied", ag["rule"]]], [70 * mm, 104 * mm]))
    S.append(Paragraph("Region-by-region agreement", H2))
    S.append(_table([["Region", "Points", "Residual / IOD", "Agreement"]] + [[r["name"].replace("_", " "), r["points"], r["distance"], r["agreement"]] for r in g["regions"]], [60 * mm, 30 * mm, 42 * mm, 42 * mm]))
    S.append(Paragraph("Facial proportions", H2))
    S.append(_table([["Proportion", "A", "B", "Difference %"]] + [[r["name"], r["a"], r["b"], r["diff_pct"]] for r in g["ratios"]], [70 * mm, 34 * mm, 34 * mm, 36 * mm]))
    qa, qb = res["quality"]["a"], res["quality"]["b"]
    S.append(Paragraph("Image quality and pose", H2))
    S.append(_table([["Measure", "A", "B"]] + [[k, qa[k], qb[k]] for k in ["sharpness", "brightness", "inter_ocular_px", "yaw", "pitch", "roll"]]
        + [["Issues", esc("; ".join(qa["hard_issues"] + qa["soft_issues"]) or "none"), esc("; ".join(qb["hard_issues"] + qb["soft_issues"]) or "none")]], [50 * mm, 62 * mm, 62 * mm]))
    ia, ib = res["integrity"]["a"], res["integrity"]["b"]
    S.append(Paragraph("Manipulation screening", H2))
    S.append(_table([["Indicator", "A", "B"], ["Result", ia["flag"], ib["flag"]], ["ELA mean / p99", f"{ia['ela_mean']} / {ia['ela_p99']}", f"{ib['ela_mean']} / {ib['ela_p99']}"],
        ["High-frequency ratio", ia["hf_ratio"], ib["hf_ratio"]], ["Detector probability", ia["model_probability"] or "not configured", ib["model_probability"] or "not configured"],
        ["Notes", esc("; ".join(ia["notes"]) or "none"), esc("; ".join(ib["notes"]) or "none")]], [50 * mm, 62 * mm, 62 * mm]))
    cal = res["method"].get("calibration")
    cal_txt = (f"Verdict cut-offs were derived on {cal['created']} from {cal['n_positive_pairs']} same-person and {cal['n_negative_pairs']:,} different-person LFW comparisons, with a safety margin of {cal['margin']} on the cautious side. LFW images are easier than much casework, so real error rates may be higher; validate on material like yours." if cal
               else "Thresholds mapping scores to the verbal scale are provisional and uncalibrated. Report false-match and false-non-match rates measured on your own validation set before relying on this output.")
    S.append(Paragraph("Method, standards and limitations", H2))
    for t in [f"Landmarks: MediaPipe Face Mesh ({res['landmarks']['count']} points incl. irises). Identity embeddings: {e['model'] or 'unavailable'}. Software versions: " + esc(res["method"]["versions"]) + ".",
              "Procedure follows the morphological-analysis structure recommended by FISWG facial comparison guidance; image suitability is screened against ISO/IEC 19794-5 style criteria (pose, size, sharpness, exposure). This is not a certified implementation of either.",
              cal_txt,
              "Age estimates are approximate (often several years off, and less reliable for children and older adults). A large age gap lowers similarity even for the same person, so a low score across a large gap is not evidence of different identities; the software limits its verdict accordingly.",
              "Landmark geometry is sensitive to pose, expression and lens distortion. Manipulation screening uses simple indicators and is not proof of authenticity or forgery.",
              "This report is decision support. A qualified examiner must review the evidence and take responsibility for any conclusion."]:
        S.append(Paragraph("- " + t, P))
    S.append(Spacer(1, 18)); S.append(Table([["Examiner signature: ____________________", "Date: ______________"]], colWidths=[100 * mm, 74 * mm]))
    doc.build(S, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
