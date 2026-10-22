"""SQLite storage via SQLAlchemy.

Tables
------
uploads  : one row per uploaded file (image or video)
frames   : sampled frames (image = 1 frame, video = N frames) with location
reports  : one row per detection = one crowdsourced "report" of a defect
sites    : de-duplicated defect sites (DBSCAN clusters of reports), recomputed
           whenever reports change. Site id = smallest report id in the cluster
           so ids stay stable as new sightings arrive.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (JSON, Boolean, Column, DateTime, Float, ForeignKey,
                        Integer, String, Text, create_engine)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from .config import DB_PATH

def utcnow() -> datetime:
    """Naive UTC timestamp (SQLite stores naive datetimes)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
Base = declarative_base()


class Upload(Base):
    __tablename__ = "uploads"
    id = Column(Integer, primary_key=True)
    filename = Column(String, nullable=False)
    kind = Column(String, nullable=False)            # "image" | "video"
    uploader = Column(String, default="anonymous")
    road_context = Column(String, default="main_road")
    blur = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)
    frames = relationship("Frame", back_populates="upload", cascade="all, delete-orphan")


class Frame(Base):
    __tablename__ = "frames"
    id = Column(Integer, primary_key=True)
    upload_id = Column(Integer, ForeignKey("uploads.id"), nullable=False)
    frame_index = Column(Integer, default=0)          # index of the sampled frame
    video_time_s = Column(Float, nullable=True)       # offset in the video, seconds
    image_path = Column(String, nullable=False)       # privacy-blurred frame (no boxes)
    annotated_path = Column(String, nullable=False)   # same frame with boxes drawn
    width = Column(Integer)
    height = Column(Integer)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    location_source = Column(String, default="none")  # exif | gpx | manual | seed | none
    timestamp = Column(DateTime, nullable=True)
    upload = relationship("Upload", back_populates="frames")
    reports = relationship("Report", back_populates="frame", cascade="all, delete-orphan")


class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True)
    frame_id = Column(Integer, ForeignKey("frames.id"), nullable=False)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    timestamp = Column(DateTime, default=utcnow)
    defect_class = Column(String, nullable=False)
    original_class = Column(String, nullable=False)   # what the model said (before edits)
    confidence = Column(Float, nullable=False)
    bbox = Column(JSON, nullable=False)               # [x1, y1, x2, y2] in pixels
    bbox_area_ratio = Column(Float, nullable=False)   # bbox area / frame area
    crop_path = Column(String, nullable=True)         # thumbnail of the defect
    uploader = Column(String, default="anonymous")
    road_context = Column(String, default="main_road")
    status = Column(String, default="pending")        # pending | confirmed | rejected | repaired
    reviewer = Column(String, nullable=True)
    review_note = Column(Text, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    site_id = Column(Integer, nullable=True, index=True)
    frame = relationship("Frame", back_populates="reports")


class Site(Base):
    __tablename__ = "sites"
    id = Column(Integer, primary_key=True)            # = min report id in cluster
    defect_class = Column(String, nullable=False)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    sightings = Column(Integer, default=1)
    first_seen = Column(DateTime)
    last_seen = Column(DateTime)
    best_report_id = Column(Integer)
    score = Column(Float, default=0)
    severity = Column(String, default="low")
    components = Column(JSON)                         # per-component breakdown
    status = Column(String, default="pending")
    road_context = Column(String, default="main_road")


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_session():
    """FastAPI dependency."""
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()
