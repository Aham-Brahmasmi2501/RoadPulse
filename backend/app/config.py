"""Loads config.yaml and exposes project paths."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

# backend/app/config.py -> project root is two levels above backend/
BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT = BACKEND_DIR.parent
DATA_DIR = ROOT / "data"
UPLOAD_DIR = DATA_DIR / "uploads"      # raw uploaded files
FRAMES_DIR = DATA_DIR / "frames"       # saved (privacy-blurred) frames + annotated copies
FEEDBACK_DIR = DATA_DIR / "feedback"   # reviewer corrections in YOLO format
EVAL_DIR = DATA_DIR / "eval"           # labelled evaluation set
DB_PATH = Path(os.environ.get("ROADPULSE_DB", DATA_DIR / "roadpulse.db"))
CONFIG_PATH = Path(os.environ.get("ROADPULSE_CONFIG", BACKEND_DIR / "config.yaml"))

for d in (UPLOAD_DIR, FRAMES_DIR, FEEDBACK_DIR / "images", FEEDBACK_DIR / "labels", EVAL_DIR):
    d.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def settings() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    # Env var override for the weights path
    if os.environ.get("ROADPULSE_WEIGHTS"):
        cfg["model"]["weights"] = os.environ["ROADPULSE_WEIGHTS"].split(",")
    if isinstance(cfg["model"]["weights"], str):
        cfg["model"]["weights"] = [cfg["model"]["weights"]]
    return cfg


def weights_paths() -> list[Path]:
    """All configured weight files (one or more, run as an ensemble)."""
    return [p if p.is_absolute() else ROOT / p for p in map(Path, settings()["model"]["weights"])]


def weights_ok() -> bool:
    return all(p.exists() for p in weights_paths())


def model_label() -> str:
    return " + ".join(p.name for p in weights_paths())


def classes() -> list[str]:
    return list(settings()["classes"])


def media_url(path: Path | str | None) -> str | None:
    """Converts an absolute path under data/ into a URL served at /media."""
    if not path:
        return None
    rel = Path(path).resolve().relative_to(DATA_DIR.resolve())
    return "/media/" + rel.as_posix()
