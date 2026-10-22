"""YOLOv8 road-damage detection, annotation, privacy blur and video sampling."""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .config import ROOT, settings, weights_paths

log = logging.getLogger("roadpulse.detector")

# BGR colours for each canonical class (used when drawing boxes)
CLASS_COLORS = {
    "pothole": (22, 115, 249),          # orange
    "crack": (248, 189, 56),            # sky blue
    "alligator_crack": (250, 139, 167), # violet
    "patch_damage": (21, 204, 250),     # yellow
}
COCO_PRIVACY = {"person": 0, "car": 2, "motorcycle": 3, "bus": 5, "truck": 7}


@dataclass
class Detection:
    cls: str            # canonical class
    raw_cls: str        # model's own class name
    conf: float
    box: list[float]    # x1, y1, x2, y2 (pixels)
    area_ratio: float   # box area / image area


class Detector:
    """Lazily-loaded singleton around the Ultralytics model."""

    _lock = threading.Lock()

    def __init__(self):
        from ultralytics import YOLO  # imported here so the API can boot fast

        cfg = settings()["model"]
        self.models = []  # list of (YOLO model, {class_id: canonical class})
        for path in weights_paths():
            if not path.exists():
                raise FileNotFoundError(f"Model weights not found: {path}. See README > Model weights.")
            model = YOLO(str(path))
            # Resolve each model class id -> canonical class via substring rules
            id_map: dict[int, str] = {}
            for idx, name in model.names.items():
                for key, canon in cfg["class_map"].items():
                    if key in name.lower():
                        id_map[idx] = canon
                        break
            self.models.append((model, id_map))
            log.info("Loaded %s; class map %s", path.name, {model.names[k]: v for k, v in id_map.items()})
        self.conf = cfg["conf_threshold"]
        self.iou = cfg["iou_threshold"]
        self.imgsz = cfg["imgsz"]
        self.ensemble_iou = cfg.get("ensemble_iou", 0.5)

        # Optional COCO model used only to localise people/vehicles for blurring
        coco = ROOT / "models" / "yolov8n.pt"
        self.coco = YOLO(str(coco)) if coco.exists() else None
        base = Path(cv2.data.haarcascades)
        self.face_cascade = cv2.CascadeClassifier(str(base / "haarcascade_frontalface_default.xml"))
        self.plate_cascade = cv2.CascadeClassifier(str(base / "haarcascade_russian_plate_number.xml"))

    # ------------------------------------------------------------------ inference
    def detect(self, img: np.ndarray, conf: float | None = None) -> list[Detection]:
        h, w = img.shape[:2]
        dets: list[Detection] = []
        for model, id_map in self.models:
            with self._lock:  # ultralytics models are not thread-safe
                res = model.predict(img, conf=conf or self.conf, iou=self.iou, imgsz=self.imgsz, verbose=False)[0]
            for b in res.boxes:
                cid = int(b.cls)
                if cid not in id_map:
                    continue
                x1, y1, x2, y2 = (float(v) for v in b.xyxy[0].tolist())
                dets.append(Detection(id_map[cid], model.names[cid], round(float(b.conf), 4),
                                      [x1, y1, x2, y2], ((x2 - x1) * (y2 - y1)) / (w * h)))
        return _merge(dets, self.ensemble_iou) if len(self.models) > 1 else dets

    # ------------------------------------------------------------------ privacy
    def privacy_regions(self, img: np.ndarray) -> list[tuple[int, int, int, int]]:
        """Finds faces and number plates. If the COCO model is available, faces
        are searched inside people and plates inside vehicles, which avoids
        Haar false positives on road texture."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        regions: list[tuple[int, int, int, int]] = []

        def search(cascade, x0, y0, x1, y1, min_size):
            roi = gray[y0:y1, x0:x1]
            if roi.size == 0:
                return
            for (x, y, rw, rh) in cascade.detectMultiScale(roi, 1.1, 4, minSize=min_size):
                regions.append((x0 + x, y0 + y, x0 + x + rw, y0 + y + rh))

        if self.coco is not None:
            with self._lock:
                res = self.coco.predict(img, conf=0.35, classes=list(COCO_PRIVACY.values()), verbose=False)[0]
            for b in res.boxes:
                x0, y0, x1, y1 = (int(v) for v in b.xyxy[0].tolist())
                if int(b.cls) == 0:
                    # Blur the head area of each person (top ~22% of the box)
                    # plus any Haar face found inside the person.
                    regions.append((x0, y0, x1, y0 + max(8, int((y1 - y0) * 0.22))))
                    search(self.face_cascade, x0, y0, x1, y1, (16, 16))
                else:
                    search(self.plate_cascade, x0, y0, x1, y1, (20, 8))
        else:
            search(self.face_cascade, 0, 0, w, h, (24, 24))
            search(self.plate_cascade, 0, int(h * 0.3), w, h, (30, 10))
        return regions

    def apply_blur(self, img: np.ndarray) -> tuple[np.ndarray, int]:
        out = img.copy()
        regions = self.privacy_regions(img)
        for (x0, y0, x1, y1) in regions:
            x0, y0 = max(0, x0), max(0, y0)
            roi = out[y0:y1, x0:x1]
            if roi.size:
                k = max(15, (min(roi.shape[:2]) // 2) | 1)
                out[y0:y1, x0:x1] = cv2.GaussianBlur(roi, (k, k), 0)
        return out, len(regions)


def _box_iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def _merge(dets: list[Detection], iou: float) -> list[Detection]:
    """Class-wise NMS across ensemble members: keep the most confident box,
    drop same-class boxes that overlap it by more than `iou`."""
    kept: list[Detection] = []
    for d in sorted(dets, key=lambda d: -d.conf):
        if all(k.cls != d.cls or _box_iou(k.box, d.box) <= iou for k in kept):
            kept.append(d)
    return kept


_detector: Detector | None = None
_init_lock = threading.Lock()


def get_detector() -> Detector:
    global _detector
    with _init_lock:
        if _detector is None:
            _detector = Detector()
    return _detector


# ---------------------------------------------------------------------- drawing
def annotate(img: np.ndarray, dets: list[Detection], low_conf: float = 0.5) -> np.ndarray:
    """Draws labelled boxes. Low-confidence boxes are dashed-looking (thinner)."""
    out = img.copy()
    h, w = out.shape[:2]
    thick = max(2, int(round(min(h, w) / 300)))
    scale = max(0.5, min(h, w) / 900)
    for d in dets:
        color = CLASS_COLORS.get(d.cls, (255, 255, 255))
        x1, y1, x2, y2 = (int(v) for v in d.box)
        cv2.rectangle(out, (x1, y1), (x2, y2), color, thick if d.conf >= low_conf else max(1, thick - 1))
        label = f"{d.cls.replace('_', ' ')} {d.conf:.2f}" + (" ?" if d.conf < low_conf else "")
        (tw, th), base = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, scale, max(1, thick - 1))
        ty = y1 - 4 if y1 - th - 8 > 0 else y1 + th + 8
        cv2.rectangle(out, (x1, ty - th - 4), (x1 + tw + 8, ty + base - 2), color, -1)
        cv2.putText(out, label, (x1 + 4, ty - 2), cv2.FONT_HERSHEY_SIMPLEX, scale, (20, 20, 20),
                    max(1, thick - 1), cv2.LINE_AA)
    return out


def crop_thumb(img: np.ndarray, box: list[float], size: int = 320) -> np.ndarray:
    """Crop around a detection with context padding, resized for thumbnails."""
    h, w = img.shape[:2]
    x1, y1, x2, y2 = box
    pad = 0.6 * max(x2 - x1, y2 - y1)
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    half = max(x2 - x1, y2 - y1) / 2 + pad
    a, b = int(max(0, cx - half)), int(max(0, cy - half))
    c, d = int(min(w, cx + half)), int(min(h, cy + half))
    crop = img[b:d, a:c]
    if crop.size == 0:
        crop = img
    s = size / max(crop.shape[:2])
    return cv2.resize(crop, (max(1, int(crop.shape[1] * s)), max(1, int(crop.shape[0] * s))))


# ---------------------------------------------------------------------- video
def sample_video(path: Path, every_sec: float, dedupe_threshold: float, max_frames: int):
    """Yields (frame_index, time_seconds, frame) every `every_sec` seconds,
    skipping frames nearly identical to the previous kept one (e.g. the car
    stopped at a signal)."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError("Could not open video")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    step = max(1, int(round(fps * every_sec)))
    prev_small = None
    idx = kept = 0
    while kept < max_frames:
        ok = cap.grab()
        if not ok:
            break
        if idx % step == 0:
            ok, frame = cap.retrieve()
            if not ok:
                break
            small = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (64, 64)).astype(np.float32)
            if prev_small is None or float(np.mean(np.abs(small - prev_small))) >= dedupe_threshold:
                prev_small = small
                yield kept, idx / fps, frame
                kept += 1
        idx += 1
    cap.release()
