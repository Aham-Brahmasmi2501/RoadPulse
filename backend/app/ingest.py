"""Turns an uploaded image/video into frames + reports (detections)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from pathlib import Path

import cv2
import numpy as np
from sqlalchemy.orm import Session

from .config import FRAMES_DIR, settings
from .db import Frame, Report, Upload, utcnow
from .detector import annotate, crop_thumb, get_detector, sample_video
from .geo import Track, read_exif

VIDEO_EXT = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


def _save_frame(db: Session, upload: Upload, img: np.ndarray, *, frame_index: int = 0,
                video_time_s: float | None = None, lat=None, lon=None, loc_source="none",
                timestamp: datetime | None = None, conf: float | None = None) -> Frame:
    """Detects defects in one frame, saves blurred + annotated copies, creates reports."""
    det = get_detector()
    low = settings()["review"]["low_confidence"]
    # Detect on the original frame (blur must never hide road damage), then blur for storage
    dets = det.detect(img, conf=conf)
    stored, _ = det.apply_blur(img) if upload.blur else (img, 0)

    stem = f"u{upload.id}_f{frame_index:04d}_{uuid.uuid4().hex[:6]}"
    img_path = FRAMES_DIR / f"{stem}.jpg"
    ann_path = FRAMES_DIR / f"{stem}_ann.jpg"
    cv2.imwrite(str(img_path), stored, [cv2.IMWRITE_JPEG_QUALITY, 88])
    cv2.imwrite(str(ann_path), annotate(stored, dets, low), [cv2.IMWRITE_JPEG_QUALITY, 88])

    h, w = img.shape[:2]
    frame = Frame(upload=upload, frame_index=frame_index, video_time_s=video_time_s,
                  image_path=str(img_path), annotated_path=str(ann_path), width=w, height=h,
                  lat=lat, lon=lon, location_source=loc_source if lat is not None else "none",
                  timestamp=timestamp or upload.created_at)
    db.add(frame)
    for i, d in enumerate(dets):
        crop_path = FRAMES_DIR / f"{stem}_d{i}.jpg"
        cv2.imwrite(str(crop_path), crop_thumb(stored, d.box), [cv2.IMWRITE_JPEG_QUALITY, 85])
        db.add(Report(frame=frame, lat=lat, lon=lon, timestamp=frame.timestamp,
                      defect_class=d.cls, original_class=d.cls, confidence=d.conf,
                      bbox=[round(v, 1) for v in d.box], bbox_area_ratio=round(d.area_ratio, 5),
                      crop_path=str(crop_path), uploader=upload.uploader,
                      road_context=upload.road_context))
    return frame


def process_file(db: Session, path: Path, *, filename: str, uploader: str, road_context: str,
                 blur: bool, track: Track | None = None, video_start: datetime | None = None,
                 manual_lat: float | None = None, manual_lon: float | None = None,
                 sample_every: float | None = None, conf: float | None = None,
                 when: datetime | None = None) -> Upload:
    """Main entry point. Location priority: EXIF > GPS track > manual pin."""
    vcfg = settings()["video"]
    kind = "video" if path.suffix.lower() in VIDEO_EXT else "image"
    upload = Upload(filename=filename, kind=kind, uploader=uploader or "anonymous",
                    road_context=road_context, blur=blur, created_at=when or utcnow())
    db.add(upload)
    db.flush()

    if kind == "image":
        img = cv2.imread(str(path))
        if img is None:
            raise ValueError(f"{filename}: not a readable image")
        lat, lon, ts = read_exif(path)
        src = "exif" if lat is not None else "none"
        if lat is None and track is not None and ts is not None:
            loc = track.locate(ts)
            if loc:
                (lat, lon), src = loc, "gpx"
        if lat is None and manual_lat is not None:
            lat, lon, src = manual_lat, manual_lon, "manual"
        _save_frame(db, upload, img, lat=lat, lon=lon, loc_source=src,
                    timestamp=ts or upload.created_at, conf=conf)
    else:
        start = video_start or (track.start if track else None) or upload.created_at
        for idx, t, frame in sample_video(path, sample_every or vcfg["sample_every_sec"],
                                          vcfg["dedupe_threshold"], vcfg["max_frames"]):
            ts = start + timedelta(seconds=t)
            lat = lon = None
            src = "none"
            if track is not None:
                loc = track.locate(ts)
                if loc:
                    (lat, lon), src = loc, "gpx"
            if lat is None and manual_lat is not None:
                lat, lon, src = manual_lat, manual_lon, "manual"
            _save_frame(db, upload, frame, frame_index=idx, video_time_s=round(t, 2), lat=lat,
                        lon=lon, loc_source=src, timestamp=ts, conf=conf)
    db.commit()
    return upload
