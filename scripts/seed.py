"""Seeds ~40 demo reports around Ahmedabad (Chandkheda / SG Highway).

The *imagery and detections are real*: the detector is run over the images
in sample_data/ (and frames of sample_data/road_video.mp4) and each seed
report reuses one of those detections (class, confidence, box, crop). Only
the location, time, uploader and review status are synthetic, arranged into
realistic clusters so the map, de-duplication and ranking look populated on
first run.

Usage (from the project root):
    python scripts/seed.py            # seeds only if the database is empty
    python scripts/seed.py --reset    # wipes reports/uploads/feedback first
"""
from __future__ import annotations

import argparse
import random
import shutil
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

import cv2  # noqa: E402

from app.config import DATA_DIR, FEEDBACK_DIR, FRAMES_DIR, UPLOAD_DIR, settings  # noqa: E402
from app.db import Base, Frame, Report, SessionLocal, Upload, engine, init_db, utcnow  # noqa: E402
from app.detector import annotate, crop_thumb, get_detector  # noqa: E402
from app.sites import recompute_sites  # noqa: E402

SAMPLE = ROOT / "sample_data"

# (name, lat, lon, class, sightings, road, size, newest-age-days, statuses)
# size: L/M/S picks large/medium/small detections from the pool.
SITES = [
    ("Gota flyover, SG Highway",    23.09893, 72.53951, "pothole", 6, "highway",     "L", 1,  ["confirmed", "confirmed"]),
    ("Thaltej crossroads",          23.04962, 72.51172, "pothole", 5, "highway",     "L", 2,  ["confirmed"]),
    ("Visat circle",                23.09402, 72.58583, "pothole", 4, "highway",     "M", 3,  []),
    ("Chandkheda main road (IOC)",  23.11052, 72.58448, "pothole", 4, "main_road",   "L", 1,  ["confirmed"]),
    ("Sola overbridge",             23.07050, 72.51780, "alligator_crack", 3, "highway", "M", 6, []),
    ("Motera stadium road",         23.09180, 72.59660, "alligator_crack", 2, "main_road", "M", 9, []),
    ("New CG Road, Chandkheda",     23.10850, 72.59320, "pothole", 3, "main_road",   "M", 12, []),
    ("Chandkheda railway station",  23.11500, 72.59700, "pothole", 2, "main_road",   "S", 15, []),
    ("Vaishnodevi circle",          23.13330, 72.53980, "crack",   2, "highway",     "M", 5,  []),
    ("Gota housing, local lane",    23.10150, 72.53550, "pothole", 2, "local_street", "S", 20, []),
    ("ONGC colony lane",            23.10600, 72.58900, "crack",   1, "local_street", "S", 25, []),
    ("Zundal village road",         23.12200, 72.58000, "pothole", 1, "local_street", "S", 33, []),
    ("Science City road",           23.07800, 72.49500, "crack",   2, "main_road",   "S", 18, []),
    ("Sabarmati riverfront link",   23.08200, 72.58800, "pothole", 2, "main_road",   "M", 40, ["repaired", "repaired"]),
    ("Bodakdev service road",       23.04050, 72.51250, "pothole", 1, "local_street", "S", 4,  ["rejected"]),
]
UPLOADERS = ["dashcam-cab-112", "amts-bus-47", "citizen-app", "municipal-survey-van", "brts-bus-12", "citizen-app"]


def reset_all():
    Base.metadata.drop_all(engine)
    for d in (FRAMES_DIR, UPLOAD_DIR, FEEDBACK_DIR):
        shutil.rmtree(d, ignore_errors=True)
    for d in (FRAMES_DIR, UPLOAD_DIR, FEEDBACK_DIR / "images", FEEDBACK_DIR / "labels"):
        d.mkdir(parents=True, exist_ok=True)


def build_pool():
    """Runs the real detector over sample images + video frames."""
    det = get_detector()
    imgs = [(p.name, cv2.imread(str(p))) for p in sorted(SAMPLE.glob("*.jpg"))]
    video = SAMPLE / "road_video.mp4"
    if video.exists():
        cap = cv2.VideoCapture(str(video))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25
        i = 0
        while cap.grab():
            if i % int(fps) == 0:
                imgs.append((f"road_video_t{i / fps:.0f}s", cap.retrieve()[1]))
            i += 1
    pool: dict[str, list] = {}
    for name, img in imgs:
        if img is None:
            continue
        stored, _ = det.apply_blur(img)
        for d in det.detect(img, conf=0.15):
            pool.setdefault(d.cls, []).append((name, stored, d))
    for c in pool:
        pool[c].sort(key=lambda t: -t[2].area_ratio * t[2].conf)
    print("Detection pool:", {c: len(v) for c, v in pool.items()})
    return pool


def pick(pool_c, size, rng):
    n = len(pool_c)
    third = max(1, n // 3)
    band = {"L": pool_c[:third], "M": pool_c[third:2 * third] or pool_c, "S": pool_c[2 * third:] or pool_c}[size]
    return rng.choice(band)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="wipe existing data first")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    rng = random.Random(a.seed)

    if a.reset:
        reset_all()
    init_db()
    db = SessionLocal()
    if db.query(Report).count() and not a.reset:
        print("Database already has reports - skipping (use --reset to re-seed).")
        return

    pool = build_pool()
    low = settings()["review"]["low_confidence"]
    now = utcnow()
    n_reports = 0
    for si, (name, lat, lon, cls, n, road, size, age, statuses) in enumerate(SITES):
        if not pool.get(cls):
            print(f"  skip {name}: model produced no '{cls}' detections in sample_data")
            continue
        for k in range(n):
            src, img, d = pick(pool[cls], size, rng)
            uploader = rng.choice(UPLOADERS)
            when = now - timedelta(days=age + k * rng.uniform(1.5, 6), hours=rng.uniform(0, 10))
            # ~4 m GPS jitter around the site
            jlat = lat + rng.gauss(0, 4) / 111_000
            jlon = lon + rng.gauss(0, 4) / 102_000
            up = Upload(filename=f"{src} (demo seed)", kind="image", uploader=uploader,
                        road_context=road, blur=True, created_at=when)
            stem = f"seed_{si:02d}_{k}"
            img_path, ann_path, crop_path = (FRAMES_DIR / f"{stem}{s}.jpg" for s in ("", "_ann", "_d0"))
            cv2.imwrite(str(img_path), img, [cv2.IMWRITE_JPEG_QUALITY, 85])
            cv2.imwrite(str(ann_path), annotate(img, [d], low), [cv2.IMWRITE_JPEG_QUALITY, 85])
            cv2.imwrite(str(crop_path), crop_thumb(img, d.box), [cv2.IMWRITE_JPEG_QUALITY, 85])
            h, w = img.shape[:2]
            fr = Frame(upload=up, image_path=str(img_path), annotated_path=str(ann_path), width=w, height=h,
                       lat=jlat, lon=jlon, location_source="seed", timestamp=when)
            status = statuses[k] if k < len(statuses) else "pending"
            rep = Report(frame=fr, lat=jlat, lon=jlon, timestamp=when, defect_class=cls, original_class=cls,
                         confidence=d.conf, bbox=[round(v, 1) for v in d.box], bbox_area_ratio=round(d.area_ratio, 5),
                         crop_path=str(crop_path), uploader=uploader, road_context=road, status=status,
                         reviewer="demo-reviewer" if status != "pending" else None,
                         reviewed_at=now if status != "pending" else None)
            db.add_all([up, fr, rep])
            n_reports += 1
    db.commit()
    n_sites = recompute_sites(db)
    print(f"Seeded {n_reports} reports -> {n_sites} defect sites. Data dir: {DATA_DIR}")


if __name__ == "__main__":
    main()
