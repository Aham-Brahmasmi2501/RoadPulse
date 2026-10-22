"""Exports reviewer corrections as a YOLO-format dataset for retraining.

For every frame touched by a reject / class edit we write
    data/feedback/images/frame_<id>.jpg
    data/feedback/labels/frame_<id>.txt   (one "cls cx cy w h" line per kept box)
The label file contains every detection in that frame that the reviewer did
NOT reject, using the corrected class. A frame whose only box was rejected
gets an empty label file = a hard-negative background image.
"""
from __future__ import annotations

import json
import shutil

from .config import FEEDBACK_DIR, classes
from .db import Frame, Report, utcnow


def _ensure_yaml() -> None:
    y = FEEDBACK_DIR / "data.yaml"
    if not y.exists():
        names = "\n".join(f"  {i}: {c}" for i, c in enumerate(classes()))
        y.write_text(f"# Reviewer feedback dataset (YOLO format)\npath: {FEEDBACK_DIR}\n"
                     f"train: images\nval: images\nnames:\n{names}\n")


def write_frame_feedback(frame: Frame) -> str:
    _ensure_yaml()
    cls_idx = {c: i for i, c in enumerate(classes())}
    lines = []
    for r in frame.reports:
        if r.status == "rejected" or r.defect_class not in cls_idx:
            continue
        x1, y1, x2, y2 = r.bbox
        cx, cy = (x1 + x2) / 2 / frame.width, (y1 + y2) / 2 / frame.height
        bw, bh = (x2 - x1) / frame.width, (y2 - y1) / frame.height
        lines.append(f"{cls_idx[r.defect_class]} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
    name = f"frame_{frame.id}"
    shutil.copyfile(frame.image_path, FEEDBACK_DIR / "images" / f"{name}.jpg")
    (FEEDBACK_DIR / "labels" / f"{name}.txt").write_text("\n".join(lines) + ("\n" if lines else ""))
    return name


def log_action(report: Report, action: str, prev_class: str) -> None:
    with open(FEEDBACK_DIR / "log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "time": utcnow().isoformat(timespec="seconds"), "report_id": report.id,
            "frame_id": report.frame_id, "action": action, "previous_class": prev_class,
            "new_class": report.defect_class, "model_class": report.original_class,
            "confidence": report.confidence, "reviewer": report.reviewer, "note": report.review_note,
        }) + "\n")


def feedback_count() -> int:
    return len(list((FEEDBACK_DIR / "labels").glob("*.txt")))
