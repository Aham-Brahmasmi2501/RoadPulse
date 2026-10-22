"""RoadPulse FastAPI application.

Run from the backend/ folder:  uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

import csv
import io
import logging
import shutil
import uuid
from datetime import date, datetime, time
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import evaluate as evaluation
from .config import (DATA_DIR, ROOT, FEEDBACK_DIR, UPLOAD_DIR, classes, media_url, model_label,
                     settings, weights_ok, weights_paths)
from .db import Frame, Report, Site, Upload, get_session, init_db, utcnow
from .feedback import feedback_count, log_action, write_frame_feedback
from .geo import parse_track
from .ingest import process_file
from .sites import recompute_sites

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
app = FastAPI(title="RoadPulse API", version="1.0.0",
              description="AI-powered pothole & road distress mapper")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/media", StaticFiles(directory=DATA_DIR), name="media")

ROAD_CONTEXTS = ["highway", "main_road", "local_street"]
STATUSES = ["pending", "confirmed", "rejected", "repaired"]


@app.on_event("startup")
def _startup():
    init_db()


# --------------------------------------------------------------------------- serializers
def report_dict(r: Report, site: Site | None = None) -> dict:
    low = settings()["review"]["low_confidence"]
    return {
        "id": r.id, "lat": r.lat, "lon": r.lon,
        "timestamp": r.timestamp.isoformat() if r.timestamp else None,
        "defect_class": r.defect_class, "original_class": r.original_class,
        "confidence": r.confidence, "low_confidence": r.confidence < low,
        "bbox": r.bbox, "bbox_area_ratio": r.bbox_area_ratio,
        "image_url": media_url(r.frame.annotated_path), "thumb_url": media_url(r.crop_path),
        "frame_id": r.frame_id, "upload_id": r.frame.upload_id,
        "location_source": r.frame.location_source,
        "uploader": r.uploader, "road_context": r.road_context, "status": r.status,
        "reviewer": r.reviewer, "review_note": r.review_note,
        "site_id": r.site_id,
        "site_score": site.score if site else None,
        "severity": site.severity if site else None,
        "components": site.components if site else None,
    }


def site_dict(s: Site, best: Report | None) -> dict:
    return {
        "id": s.id, "defect_class": s.defect_class, "lat": s.lat, "lon": s.lon,
        "sightings": s.sightings,
        "first_seen": s.first_seen.isoformat() if s.first_seen else None,
        "last_seen": s.last_seen.isoformat() if s.last_seen else None,
        "best_report_id": s.best_report_id,
        "thumb_url": media_url(best.crop_path) if best else None,
        "image_url": media_url(best.frame.annotated_path) if best else None,
        "score": s.score, "severity": s.severity, "components": s.components,
        "status": s.status, "road_context": s.road_context,
        "max_confidence": best.confidence if best else None,
    }


def frame_dict(f: Frame) -> dict:
    return {
        "id": f.id, "frame_index": f.frame_index, "video_time_s": f.video_time_s,
        "image_url": media_url(f.image_path), "annotated_url": media_url(f.annotated_path),
        "width": f.width, "height": f.height, "lat": f.lat, "lon": f.lon,
        "location_source": f.location_source,
        "timestamp": f.timestamp.isoformat() if f.timestamp else None,
        "detections": [{"report_id": r.id, "class": r.defect_class, "confidence": r.confidence,
                        "bbox": r.bbox, "low_confidence": r.confidence < settings()["review"]["low_confidence"]}
                       for r in f.reports],
    }


def upload_dict(u: Upload) -> dict:
    frames = sorted(u.frames, key=lambda f: f.frame_index)
    return {
        "id": u.id, "filename": u.filename, "kind": u.kind, "uploader": u.uploader,
        "road_context": u.road_context, "blur": u.blur, "created_at": u.created_at.isoformat(),
        "frame_count": len(frames), "detection_count": sum(len(f.reports) for f in frames),
        "needs_location": any(f.lat is None for f in frames if f.reports),
        "frames": [frame_dict(f) for f in frames],
    }


def _sites_by_id(db: Session) -> dict[int, Site]:
    return {s.id: s for s in db.query(Site).all()}


def _date_bounds(date_from: Optional[date], date_to: Optional[date]):
    lo = datetime.combine(date_from, time.min) if date_from else None
    hi = datetime.combine(date_to, time.max) if date_to else None
    return lo, hi


# --------------------------------------------------------------------------- meta
@app.get("/api-info")
def api_info():
    return {"name": "RoadPulse API", "docs": "/docs"}


@app.get("/config")
def get_config():
    """Exposes the scoring config so the UI can explain the score."""
    cfg = settings()
    return {"classes": classes(), "road_contexts": ROAD_CONTEXTS, "statuses": STATUSES,
            "scoring": cfg["scoring"], "video": cfg["video"], "privacy": cfg["privacy"],
            "low_confidence": cfg["review"]["low_confidence"], "clustering": cfg["clustering"],
            "model": {"weights": model_label(), "exists": weights_ok(),
                      "conf_threshold": cfg["model"]["conf_threshold"]}}


@app.get("/stats")
def stats(db: Session = Depends(get_session)):
    reports = db.query(Report).all()
    sites = db.query(Site).all()
    reviewed = [r for r in reports if r.status in ("confirmed", "rejected", "repaired")]
    confirmed = [r for r in reports if r.status in ("confirmed", "repaired")]
    by_class, by_sev, by_status = {}, {"low": 0, "medium": 0, "high": 0}, {}
    for s in sites:
        by_class[s.defect_class] = by_class.get(s.defect_class, 0) + 1
        if s.status != "repaired":
            by_sev[s.severity] += 1
    for r in reports:
        by_status[r.status] = by_status.get(r.status, 0) + 1
    return {
        "total_reports": len(reports),
        "unique_sites": len(sites),
        "high_priority_sites": sum(1 for s in sites if s.severity == "high" and s.status != "repaired"),
        "confirmed_pct": round(100 * len(confirmed) / len(reviewed), 1) if reviewed else 0.0,
        "reviewed": len(reviewed),
        "pending_review": by_status.get("pending", 0),
        "unlocated_reports": sum(1 for r in reports if r.lat is None),
        "by_class": by_class, "by_severity": by_sev, "by_status": by_status,
        "feedback_samples": feedback_count(),
    }


# --------------------------------------------------------------------------- upload
@app.post("/upload")
def upload(
    files: list[UploadFile] = File(..., description="Images (jpg/png) or videos (mp4)"),
    gps_track: Optional[UploadFile] = File(None, description="Optional GPX or CSV (time,lat,lon)"),
    uploader: str = Form("anonymous"),
    road_context: str = Form("main_road"),
    blur: bool = Form(True),
    sample_every: Optional[float] = Form(None),
    lat: Optional[float] = Form(None),
    lon: Optional[float] = Form(None),
    video_start: Optional[str] = Form(None, description="ISO time of first video frame (defaults to track start)"),
    db: Session = Depends(get_session),
):
    """Detects road defects in uploaded media and stores each detection as a report.
    Sync def -> FastAPI runs it in a worker thread, so inference doesn't block the loop."""
    if road_context not in ROAD_CONTEXTS:
        raise HTTPException(400, f"road_context must be one of {ROAD_CONTEXTS}")
    if not weights_ok():
        raise HTTPException(503, f"Model weights missing: {[str(p) for p in weights_paths()]}")
    track = None
    if gps_track is not None and gps_track.filename:
        try:
            track = parse_track(gps_track.file.read(), gps_track.filename)
        except Exception as e:
            raise HTTPException(400, f"Could not parse GPS track: {e}")
    vstart = datetime.fromisoformat(video_start) if video_start else None

    results = []
    for f in files:
        ext = (f.filename or "file").rsplit(".", 1)[-1].lower()
        dest = UPLOAD_DIR / f"{uuid.uuid4().hex[:10]}.{ext}"
        with open(dest, "wb") as out:
            shutil.copyfileobj(f.file, out)
        try:
            up = process_file(db, dest, filename=f.filename or dest.name, uploader=uploader,
                              road_context=road_context, blur=blur, track=track, video_start=vstart,
                              manual_lat=lat, manual_lon=lon, sample_every=sample_every)
        except ValueError as e:
            db.rollback()
            raise HTTPException(400, str(e))
        results.append(up.id)
    recompute_sites(db)
    ups = db.query(Upload).filter(Upload.id.in_(results)).all()
    return {"uploads": [upload_dict(u) for u in ups]}


@app.get("/uploads")
def list_uploads(limit: int = 12, db: Session = Depends(get_session)):
    ups = db.query(Upload).order_by(Upload.id.desc()).limit(limit).all()
    return [upload_dict(u) for u in ups]


@app.get("/uploads/{upload_id}")
def get_upload(upload_id: int, db: Session = Depends(get_session)):
    u = db.get(Upload, upload_id)
    if not u:
        raise HTTPException(404, "Upload not found")
    return upload_dict(u)


class LocationIn(BaseModel):
    lat: float
    lon: float
    only_missing: bool = True  # only frames without GPS


@app.post("/uploads/{upload_id}/location")
def set_upload_location(upload_id: int, body: LocationIn, db: Session = Depends(get_session)):
    """Manual geotag: user clicked on the map to set/confirm the location."""
    u = db.get(Upload, upload_id)
    if not u:
        raise HTTPException(404, "Upload not found")
    n = 0
    for f in u.frames:
        if body.only_missing and f.lat is not None:
            continue
        f.lat, f.lon, f.location_source = body.lat, body.lon, "manual"
        for r in f.reports:
            r.lat, r.lon = body.lat, body.lon
            n += 1
    db.commit()
    recompute_sites(db)
    return {"updated_reports": n, "upload": upload_dict(u)}


@app.post("/frames/{frame_id}/location")
def set_frame_location(frame_id: int, body: LocationIn, db: Session = Depends(get_session)):
    f = db.get(Frame, frame_id)
    if not f:
        raise HTTPException(404, "Frame not found")
    f.lat, f.lon, f.location_source = body.lat, body.lon, "manual"
    for r in f.reports:
        r.lat, r.lon = body.lat, body.lon
    db.commit()
    recompute_sites(db)
    return frame_dict(f)


# --------------------------------------------------------------------------- reports & sites
@app.get("/reports")
def list_reports(
    defect_class: Optional[str] = None, severity: Optional[str] = None, status: Optional[str] = None,
    date_from: Optional[date] = None, date_to: Optional[date] = None,
    located: Optional[bool] = None, site_id: Optional[int] = None,
    low_confidence: Optional[bool] = None, limit: int = Query(1000, le=5000),
    db: Session = Depends(get_session),
):
    q = db.query(Report)
    if defect_class:
        q = q.filter(Report.defect_class.in_(defect_class.split(",")))
    if status:
        q = q.filter(Report.status.in_(status.split(",")))
    lo, hi = _date_bounds(date_from, date_to)
    if lo:
        q = q.filter(Report.timestamp >= lo)
    if hi:
        q = q.filter(Report.timestamp <= hi)
    if located is True:
        q = q.filter(Report.lat.isnot(None))
    elif located is False:
        q = q.filter(Report.lat.is_(None))
    if site_id is not None:
        q = q.filter(Report.site_id == site_id)
    if low_confidence is not None:
        thr = settings()["review"]["low_confidence"]
        q = q.filter(Report.confidence < thr if low_confidence else Report.confidence >= thr)
    sites = _sites_by_id(db)
    out = [report_dict(r, sites.get(r.site_id)) for r in q.order_by(Report.timestamp.desc()).limit(limit)]
    if severity:
        sev = severity.split(",")
        out = [r for r in out if r["severity"] in sev]
    return out


def _filtered_sites(db: Session, defect_class=None, severity=None, status=None, date_from=None, date_to=None):
    q = db.query(Site)
    if defect_class:
        q = q.filter(Site.defect_class.in_(defect_class.split(",")))
    if severity:
        q = q.filter(Site.severity.in_(severity.split(",")))
    if status:
        q = q.filter(Site.status.in_(status.split(",")))
    lo, hi = _date_bounds(date_from, date_to)
    if lo:
        q = q.filter(Site.last_seen >= lo)
    if hi:
        q = q.filter(Site.first_seen <= hi)
    sites = q.order_by(Site.score.desc(), Site.sightings.desc()).all()
    best = {r.id: r for r in db.query(Report).filter(Report.id.in_([s.best_report_id for s in sites]))}
    return [site_dict(s, best.get(s.best_report_id)) for s in sites]


@app.get("/sites")
def list_sites(defect_class: Optional[str] = None, severity: Optional[str] = None,
               status: Optional[str] = None, date_from: Optional[date] = None,
               date_to: Optional[date] = None, db: Session = Depends(get_session)):
    return _filtered_sites(db, defect_class, severity, status, date_from, date_to)


@app.get("/sites/{site_id}")
def get_site(site_id: int, db: Session = Depends(get_session)):
    s = db.get(Site, site_id)
    if not s:
        raise HTTPException(404, "Site not found (ids change only if its first report is rejected)")
    reports = db.query(Report).filter(Report.site_id == site_id).order_by(Report.timestamp).all()
    d = site_dict(s, db.get(Report, s.best_report_id))
    d["reports"] = [report_dict(r, s) for r in reports]
    return d


# --------------------------------------------------------------------------- ranking
@app.get("/ranking")
def ranking(include_repaired: bool = False, defect_class: Optional[str] = None,
            severity: Optional[str] = None, db: Session = Depends(get_session)):
    sites = _filtered_sites(db, defect_class, severity)
    if not include_repaired:
        sites = [s for s in sites if s["status"] != "repaired"]
    for i, s in enumerate(sites, 1):
        s["rank"] = i
    return sites


@app.get("/ranking.csv")
def ranking_csv(include_repaired: bool = False, db: Session = Depends(get_session)):
    rows = ranking(include_repaired=include_repaired, db=db)
    buf = io.StringIO()
    comp_keys = list(settings()["scoring"]["weights"].keys())
    w = csv.writer(buf)
    w.writerow(["rank", "site_id", "defect_class", "lat", "lon", "google_maps", "sightings", "first_seen",
                "last_seen", "score", "severity", "status", "road_context"] + [f"pts_{k}" for k in comp_keys])
    for s in rows:
        pts = {c["key"]: c["points"] for c in s["components"] or []}
        w.writerow([s["rank"], s["id"], s["defect_class"], f"{s['lat']:.6f}", f"{s['lon']:.6f}",
                    f"https://maps.google.com/?q={s['lat']:.6f},{s['lon']:.6f}", s["sightings"],
                    s["first_seen"], s["last_seen"], s["score"], s["severity"], s["status"],
                    s["road_context"]] + [pts.get(k, "") for k in comp_keys])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=roadpulse_ranking.csv"})


# --------------------------------------------------------------------------- review
class ReviewIn(BaseModel):
    action: str                       # confirm | reject | edit_class | repaired | reset
    new_class: Optional[str] = None   # required for edit_class
    reviewer: str = "reviewer"
    note: Optional[str] = None


def _in_feedback_set(frame_id: int) -> bool:
    """A frame already in the feedback set must be re-written on any later review."""
    return (FEEDBACK_DIR / "labels" / f"frame_{frame_id}.txt").exists()


def _apply_review(db: Session, r: Report, body: ReviewIn) -> Optional[str]:
    prev = r.defect_class
    exported = None
    if body.action == "confirm":
        r.status = "confirmed"
    elif body.action == "reject":
        r.status = "rejected"
    elif body.action == "repaired":
        r.status = "repaired"
    elif body.action == "reset":
        r.status = "pending"
    elif body.action == "edit_class":
        if body.new_class not in classes():
            raise HTTPException(400, f"new_class must be one of {classes()}")
        r.defect_class = body.new_class
        r.status = "confirmed"  # an edited label is a reviewer-verified label
    else:
        raise HTTPException(400, "action must be confirm | reject | edit_class | repaired | reset")
    r.reviewer, r.review_note, r.reviewed_at = body.reviewer, body.note, utcnow()
    db.flush()
    # Corrections become YOLO training data
    # Seed frames are skipped: they show other, unlabelled defects that would
    # wrongly become "background" in the training labels.
    if r.frame.location_source != "seed" and (body.action in ("reject", "edit_class") or _in_feedback_set(r.frame_id)):
        exported = write_frame_feedback(r.frame)
    log_action(r, body.action, prev)
    return exported


@app.post("/review/{report_id}")
def review_report(report_id: int, body: ReviewIn, db: Session = Depends(get_session)):
    r = db.get(Report, report_id)
    if not r:
        raise HTTPException(404, "Report not found")
    exported = _apply_review(db, r, body)
    db.commit()
    recompute_sites(db)
    db.refresh(r)
    sites = _sites_by_id(db)
    return {"report": report_dict(r, sites.get(r.site_id)), "feedback_file": exported}


@app.post("/sites/{site_id}/review")
def review_site(site_id: int, body: ReviewIn, db: Session = Depends(get_session)):
    """Applies the same review action to every report in a site."""
    reports = db.query(Report).filter(Report.site_id == site_id).all()
    if not reports:
        raise HTTPException(404, "Site not found")
    for r in reports:
        _apply_review(db, r, body)
    db.commit()
    recompute_sites(db)
    return {"updated": len(reports)}


# --------------------------------------------------------------------------- evaluation
@app.get("/evaluate")
def evaluate(refresh: bool = False):
    """Returns cached metrics; ?refresh=true re-runs the model on data/eval."""
    if not weights_ok():
        raise HTTPException(503, "Model weights missing")
    return evaluation.cached_or_run(refresh)


# --------------------------------------------------------------------------- single-site mode
# When the React app has been built (frontend/dist), this one server is the whole
# website: the dashboard at "/", the API under "/api/..." (same paths the Vite
# dev proxy uses) and media under "/media". Handy for hosting on one URL.
FRONTEND_DIST = ROOT / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")


class _StripApiPrefix:
    """ASGI wrapper: /api/stats -> /stats, so the built frontend works unchanged."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].startswith("/api/"):
            scope = dict(scope, path=scope["path"][4:], raw_path=scope["path"][4:].encode())
        await self.inner(scope, receive, send)


asgi = _StripApiPrefix(app)  # production entry point: uvicorn app.main:asgi
