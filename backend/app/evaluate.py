"""Evaluates the detector on data/eval (images/ + YOLO labels/).

Labels use the canonical class indices from config.yaml `classes`.
Outputs precision / recall (at the configured confidence threshold),
AP@0.5 per class, mAP@0.5 (over classes present in the ground truth),
a confusion matrix with a background row/column, and sample TP/FP images.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import cv2
import numpy as np

from .config import EVAL_DIR, classes, model_label, settings
from .detector import CLASS_COLORS, get_detector

RESULTS = EVAL_DIR / "results.json"
SAMPLES = EVAL_DIR / "samples"
IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp"}


def _iou(a, b) -> float:
    ix1, iy1, ix2, iy2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def _load_gt(label: Path, w: int, h: int, names: list[str]):
    gt = []
    if label.exists():
        for line in label.read_text().split("\n"):
            p = line.split()
            if len(p) >= 5:
                c, cx, cy, bw, bh = int(p[0]), *map(float, p[1:5])
                gt.append((names[c], [(cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h]))
    return gt


def _ap(scores: list[float], tps: list[int], n_gt: int) -> float:
    """All-point interpolated average precision (VOC 2010+ / COCO style)."""
    if n_gt == 0 or not scores:
        return 0.0
    order = np.argsort(-np.array(scores))
    tp = np.array(tps)[order]
    ctp, cfp = np.cumsum(tp), np.cumsum(1 - tp)
    rec = ctp / n_gt
    prec = ctp / np.maximum(ctp + cfp, 1e-9)
    mrec = np.concatenate(([0.0], rec, [1.0]))
    mpre = np.concatenate(([1.0], prec, [0.0]))
    mpre = np.flip(np.maximum.accumulate(np.flip(mpre)))
    idx = np.where(mrec[1:] != mrec[:-1])[0]
    return float(np.sum((mrec[idx + 1] - mrec[idx]) * mpre[idx + 1]))


def _draw_sample(img, gts, preds, path: Path):
    out = img.copy()
    for _, b in gts:  # ground truth: white dashed-ish thin box
        cv2.rectangle(out, (int(b[0]), int(b[1])), (int(b[2]), int(b[3])), (255, 255, 255), 2)
    for c, conf, b, ok in preds:
        col = CLASS_COLORS.get(c, (0, 255, 0)) if ok else (60, 60, 230)
        cv2.rectangle(out, (int(b[0]), int(b[1])), (int(b[2]), int(b[3])), col, 2)
        cv2.putText(out, f"{'TP' if ok else 'FP'} {c} {conf:.2f}", (int(b[0]) + 2, max(14, int(b[1]) - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, col, 1, cv2.LINE_AA)
    s = 480 / max(out.shape[:2])
    cv2.imwrite(str(path), cv2.resize(out, (int(out.shape[1] * s), int(out.shape[0] * s))))


def run_evaluation() -> dict:
    names = classes()
    img_dir, lbl_dir = EVAL_DIR / "images", EVAL_DIR / "labels"
    images = sorted(p for p in img_dir.glob("*") if p.suffix.lower() in IMG_EXT) if img_dir.exists() else []
    if not images:
        return {"available": False, "message": "No images in data/eval/images. Run scripts/prepare_eval.py."}

    det = get_detector()
    conf_thr = settings()["model"]["conf_threshold"]
    iou_thr = 0.5
    SAMPLES.mkdir(exist_ok=True)
    for old in SAMPLES.glob("*.jpg"):
        old.unlink()

    # Collect predictions at a low threshold so the PR curve / AP is meaningful
    per_class = {c: {"scores": [], "tp": [], "n_gt": 0} for c in names}
    labels_cm = names + ["background"]
    cm = np.zeros((len(labels_cm), len(labels_cm)), dtype=int)  # rows = predicted, cols = true
    tp_samples, fp_samples = [], []
    t0 = time.time()

    for p in images:
        img = cv2.imread(str(p))
        if img is None:
            continue
        h, w = img.shape[:2]
        gts = _load_gt(lbl_dir / f"{p.stem}.txt", w, h, names)
        for c, _ in gts:
            per_class[c]["n_gt"] += 1
        preds = sorted(det.detect(img, conf=0.01), key=lambda d: -d.conf)

        # --- AP matching (class-aware, greedy by confidence)
        used = set()
        for d in preds:
            best, bi = 0.0, -1
            for i, (c, b) in enumerate(gts):
                if c == d.cls and i not in used:
                    v = _iou(d.box, b)
                    if v > best:
                        best, bi = v, i
            hit = best >= iou_thr
            if hit:
                used.add(bi)
            per_class[d.cls]["scores"].append(d.conf)
            per_class[d.cls]["tp"].append(int(hit))

        # --- confusion matrix + samples at the operating threshold (class-agnostic IoU match)
        op = [d for d in preds if d.conf >= conf_thr]
        matched_gt, drawn = set(), []
        for d in op:
            best, bi = 0.0, -1
            for i, (_, b) in enumerate(gts):
                if i not in matched_gt:
                    v = _iou(d.box, b)
                    if v > best:
                        best, bi = v, i
            if best >= iou_thr:
                matched_gt.add(bi)
                cm[names.index(d.cls), names.index(gts[bi][0])] += 1
                drawn.append((d.cls, d.conf, d.box, d.cls == gts[bi][0]))
            else:
                cm[names.index(d.cls), -1] += 1
                drawn.append((d.cls, d.conf, d.box, False))
        for i, (c, _) in enumerate(gts):
            if i not in matched_gt:
                cm[-1, names.index(c)] += 1  # missed = predicted background
        if any(ok for *_, ok in drawn) and len(tp_samples) < 6:
            out = SAMPLES / f"tp_{p.stem}.jpg"
            _draw_sample(img, gts, drawn, out)
            tp_samples.append({"image": f"/media/eval/samples/{out.name}", "name": p.name})
        elif any(not ok for *_, ok in drawn) and len(fp_samples) < 6:
            out = SAMPLES / f"fp_{p.stem}.jpg"
            _draw_sample(img, gts, drawn, out)
            fp_samples.append({"image": f"/media/eval/samples/{out.name}", "name": p.name})

    # --- metrics
    rows = []
    ap_vals = []
    total_tp = total_fp = total_gt = 0
    for c in names:
        pc = per_class[c]
        sc, tp = np.array(pc["scores"]), np.array(pc["tp"])
        sel = sc >= conf_thr if len(sc) else np.array([], dtype=bool)
        ctp, cfp = int(tp[sel].sum()) if len(sc) else 0, int((1 - tp[sel]).sum()) if len(sc) else 0
        ap = _ap(pc["scores"], pc["tp"], pc["n_gt"])
        if pc["n_gt"] > 0:
            ap_vals.append(ap)
        total_tp, total_fp, total_gt = total_tp + ctp, total_fp + cfp, total_gt + pc["n_gt"]
        rows.append({"class": c, "gt": pc["n_gt"], "tp": ctp, "fp": cfp,
                     "precision": round(ctp / (ctp + cfp), 3) if ctp + cfp else None,
                     "recall": round(ctp / pc["n_gt"], 3) if pc["n_gt"] else None,
                     "ap50": round(ap, 3) if pc["n_gt"] else None})

    result = {
        "available": True,
        "model": model_label(),
        "images": len(images),
        "conf_threshold": conf_thr,
        "iou_threshold": iou_thr,
        "precision": round(total_tp / (total_tp + total_fp), 3) if total_tp + total_fp else 0.0,
        "recall": round(total_tp / total_gt, 3) if total_gt else 0.0,
        "map50": round(float(np.mean(ap_vals)), 3) if ap_vals else 0.0,
        "per_class": rows,
        "confusion": {"labels": labels_cm, "matrix": cm.tolist(),
                      "note": "rows = predicted class, columns = true class"},
        "samples": {"true_positives": tp_samples, "false_positives": fp_samples},
        "seconds": round(time.time() - t0, 1),
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    readme = EVAL_DIR / "SOURCE.md"
    if readme.exists():
        result["source"] = readme.read_text()
    RESULTS.write_text(json.dumps(result, indent=2))
    return result


def cached_or_run(refresh: bool = False) -> dict:
    if RESULTS.exists() and not refresh:
        return json.loads(RESULTS.read_text())
    return run_evaluation()
