"""Screening indicators for image manipulation. Not a deepfake verdict.
Plug in your own detector: set DEEPFAKE_DETECTOR="your_module:predict" where
predict(bgr_image: np.ndarray) -> float (probability the image is manipulated)."""
import importlib, os
import cv2, numpy as np

_ext = None
def _external():
    global _ext
    spec = os.environ.get("DEEPFAKE_DETECTOR")
    if _ext is None and spec:
        mod, fn = spec.split(":")
        _ext = getattr(importlib.import_module(mod), fn)
    return _ext

def screen(img, meta):
    ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    diff = cv2.absdiff(img, cv2.imdecode(enc, 1)).astype(np.float32).mean(2)
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    f = np.abs(np.fft.fftshift(np.fft.fft2(g - g.mean())))
    h, w = g.shape
    yy, xx = np.ogrid[:h, :w]
    r = np.hypot((yy - h / 2) / (h / 2), (xx - w / 2) / (w / 2))
    hf = float(f[r > 0.5].sum() / (f.sum() + 1e-9))
    out = {"ela_mean": round(float(diff.mean()), 3), "ela_p99": round(float(np.percentile(diff, 99)), 3),
           "hf_ratio": round(hf, 4), "has_exif": meta["exif"], "software_tag": meta["software"] or None,
           "model_probability": None, "flag": "no indicators"}
    notes = []
    if out["ela_p99"] > 6: notes.append("uneven recompression response (ELA)")
    if out["hf_ratio"] < 0.02: notes.append("unusually low high-frequency energy (smoothing/upscaling)")
    if meta["software"]: notes.append("software tag present: " + meta["software"])
    fn = _external()
    if fn:
        out["model_probability"] = round(float(fn(img)), 4)
        if out["model_probability"] > 0.5: notes.append("external detector score above 0.5")
    if notes: out["flag"] = "review"
    out["notes"] = notes
    return out
