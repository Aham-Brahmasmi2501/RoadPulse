"""Fine-tunes YOLOv8n on a road-damage dataset with RoadPulse's 4 canonical classes:
    0 pothole, 1 crack, 2 alligator_crack, 3 patch_damage

Every source dataset is first re-written into datasets/roadpulse/ with labels
re-mapped to those indices (class names are matched by substring, e.g.
"Potholes" -> pothole, "D20"/"alligator" -> alligator_crack), so you can mix a
Roboflow export, the crack-seg set and reviewer feedback in one run.

Sources (combine freely):
  --roboflow WORKSPACE/PROJECT/VERSION   download a Roboflow Universe dataset in
                                         YOLOv8 format (needs `pip install roboflow`
                                         and ROBOFLOW_API_KEY). Good choices:
                                         a pothole or road-damage project.
  --data path/to/data.yaml               any local YOLO dataset (train/val + names)
  --crack-seg                            Ultralytics crack-seg (polygons -> boxes)
  --feedback                             add data/feedback (reviewer corrections)

Examples:
  python scripts/train.py --roboflow my-ws/pothole-detection/3 --epochs 50
  python scripts/train.py --crack-seg --feedback --epochs 10 --imgsz 416
  python scripts/train.py --data ~/datasets/rdd/data.yaml --epochs 80 --device 0

The best weights are copied to models/<name>.pt; point config.yaml
`model.weights` at them (or add them to the ensemble list).
"""
from __future__ import annotations

import argparse
import io
import os
import shutil
import urllib.request
import zipfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CANON = ["pothole", "crack", "alligator_crack", "patch_damage"]
OUT = ROOT / "datasets" / "roadpulse"
IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp"}
CRACK_SEG_URL = "https://github.com/ultralytics/assets/releases/download/v0.0.0/crack-seg.zip"


def canon_index(name: str) -> int | None:
    n = name.lower()
    rules = [("pothole", "pothole"), ("d40", "pothole"), ("alligator", "alligator_crack"),
             ("d20", "alligator_crack"), ("patch", "patch_damage"), ("crack", "crack"),
             ("longitudinal", "crack"), ("transverse", "crack"), ("d00", "crack"), ("d10", "crack")]
    for key, c in rules:
        if key in n:
            return CANON.index(c)
    return None


def to_box_line(parts: list[str], new_cls: int) -> str:
    """YOLO detect line from either a box line (5 values) or a polygon line (seg)."""
    vals = list(map(float, parts[1:]))
    if len(vals) == 4:
        cx, cy, w, h = vals
    else:
        xs, ys = vals[0::2], vals[1::2]
        x1, x2, y1, y2 = min(xs), max(xs), min(ys), max(ys)
        cx, cy, w, h = (x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1
    return f"{new_cls} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}"


def add_split(images: Path, labels: Path, names: list[str], split: str, prefix: str, limit: int | None) -> int:
    """Copies one split into datasets/roadpulse/{images,labels}/{split} with remapped classes."""
    remap = {i: canon_index(n) for i, n in enumerate(names)}
    (OUT / "images" / split).mkdir(parents=True, exist_ok=True)
    (OUT / "labels" / split).mkdir(parents=True, exist_ok=True)
    n = 0
    for img in sorted(images.glob("*")):
        if img.suffix.lower() not in IMG_EXT:
            continue
        if limit and n >= limit:
            break
        lines = []
        lbl = labels / f"{img.stem}.txt"
        if lbl.exists():
            for row in lbl.read_text().split("\n"):
                p = row.split()
                if len(p) >= 5 and remap.get(int(p[0])) is not None:
                    lines.append(to_box_line(p, remap[int(p[0])]))
        name = f"{prefix}_{img.stem}"
        shutil.copyfile(img, OUT / "images" / split / f"{name}{img.suffix}")
        (OUT / "labels" / split / f"{name}.txt").write_text("\n".join(lines) + ("\n" if lines else ""))
        n += 1
    return n


def add_yaml_dataset(data_yaml: Path, prefix: str, limit: int | None) -> None:
    cfg = yaml.safe_load(data_yaml.read_text())
    names = cfg["names"]
    names = [names[k] for k in sorted(names)] if isinstance(names, dict) else list(names)
    base = Path(cfg.get("path") or data_yaml.parent)
    if not base.is_absolute():
        base = (data_yaml.parent / base).resolve()
    for split, key in (("train", "train"), ("val", "val")):
        rel = cfg.get(key) or (cfg.get("valid") if key == "val" else None)
        if not rel:
            continue
        img_dir = (base / rel) if not Path(rel).is_absolute() else Path(rel)
        if not img_dir.exists():  # Roboflow exports use ../train/images style paths
            img_dir = (data_yaml.parent / rel).resolve()
        lbl_dir = Path(str(img_dir).replace(f"{os.sep}images", f"{os.sep}labels"))
        n = add_split(img_dir, lbl_dir, names, split, prefix, limit)
        print(f"  {prefix}/{split}: {n} images")


def add_crack_seg(limit: int | None) -> None:
    cache = ROOT / "datasets" / "crack-seg"
    if not cache.exists():
        print(f"Downloading {CRACK_SEG_URL}")
        zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(CRACK_SEG_URL, timeout=300).read())).extractall(cache)
    # The test split is held out for scripts/prepare_eval.py, so only train/val are used here
    for split in ("train", "val"):
        n = add_split(cache / "images" / split, cache / "labels" / split, ["crack"], split, "crackseg",
                      limit if split == "train" else None)
        print(f"  crack-seg/{split}: {n} images")


def add_feedback() -> None:
    fb = ROOT / "data" / "feedback"
    if (fb / "images").exists():
        n = add_split(fb / "images", fb / "labels", CANON, "train", "feedback", None)
        print(f"  feedback/train: {n} images")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--roboflow", help="WORKSPACE/PROJECT/VERSION")
    ap.add_argument("--data", type=Path, help="local YOLO data.yaml")
    ap.add_argument("--crack-seg", action="store_true")
    ap.add_argument("--feedback", action="store_true")
    ap.add_argument("--limit", type=int, default=None, help="max train images per source (quick runs)")
    ap.add_argument("--model", default=str(ROOT / "models" / "yolov8n.pt"), help="base weights")
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--device", default=None, help="'0' for GPU, 'cpu' for CPU")
    ap.add_argument("--name", default="roadpulse_yolov8n")
    a = ap.parse_args()

    shutil.rmtree(OUT, ignore_errors=True)
    print("Preparing dataset in", OUT)
    if a.roboflow:
        from roboflow import Roboflow  # pip install roboflow
        ws, proj, ver = a.roboflow.split("/")
        rf = Roboflow(api_key=os.environ["ROBOFLOW_API_KEY"])
        ds = rf.workspace(ws).project(proj).version(int(ver)).download("yolov8", location=str(ROOT / "datasets" / proj))
        add_yaml_dataset(Path(ds.location) / "data.yaml", proj, a.limit)
    if a.data:
        add_yaml_dataset(a.data, a.data.parent.name, a.limit)
    if a.crack_seg:
        add_crack_seg(a.limit)
    if a.feedback:
        add_feedback()
    if not (OUT / "images" / "train").exists():
        raise SystemExit("No training data - pass --roboflow, --data, --crack-seg and/or --feedback")
    if not (OUT / "images" / "val").exists():  # fall back to validating on train
        shutil.copytree(OUT / "images" / "train", OUT / "images" / "val")
        shutil.copytree(OUT / "labels" / "train", OUT / "labels" / "val")

    data_yaml = OUT / "data.yaml"
    data_yaml.write_text(yaml.safe_dump({"path": str(OUT), "train": "images/train", "val": "images/val",
                                         "names": {i: c for i, c in enumerate(CANON)}}))

    from ultralytics import YOLO
    model = YOLO(a.model)
    model.train(data=str(data_yaml), epochs=a.epochs, imgsz=a.imgsz, batch=a.batch, device=a.device,
                project=str(ROOT / "runs"), name=a.name, exist_ok=True, patience=20, plots=True)
    best = ROOT / "runs" / a.name / "weights" / "best.pt"
    dest = ROOT / "models" / f"{a.name}.pt"
    shutil.copyfile(best, dest)
    print(f"\nDone. Best weights -> {dest}\nAdd it to backend/config.yaml model.weights to use it.")


if __name__ == "__main__":
    main()
