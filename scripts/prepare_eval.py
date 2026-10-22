"""Builds the labelled evaluation set in data/eval/{images,labels}.

Labels are written with RoadPulse's canonical class indices
(0 pothole, 1 crack, 2 alligator_crack, 3 patch_damage).

Sources (pick one):
  --crack-seg            Ultralytics "crack-seg" (Roboflow, CC BY 4.0) test split,
                         downloaded from GitHub releases; polygons -> boxes, class crack.
                         This is the default because it's reachable almost everywhere.
  --rdd PATH             An extracted RDD2022 country folder (e.g. RDD2022/India/train)
                         with images/ and annotations/xmls/ (Pascal VOC). D00/D10 -> crack,
                         D20 -> alligator_crack, D40 -> pothole. Best match for Indian roads.
  --yolo PATH --names a,b,c
                         Any YOLO dataset split (images/ + labels/), e.g. a Roboflow
                         pothole export. --names lists its class names in index order;
                         names are mapped to canonical classes by substring.

Usage:
  python scripts/prepare_eval.py --crack-seg --limit 40
  python scripts/prepare_eval.py --rdd ~/RDD2022/India/train --limit 80 --append
"""
from __future__ import annotations

import argparse
import io
import random
import shutil
import sys
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "data" / "eval"
CANON = ["pothole", "crack", "alligator_crack", "patch_damage"]
CRACK_SEG_URL = "https://github.com/ultralytics/assets/releases/download/v0.0.0/crack-seg.zip"
RDD_MAP = {"D00": "crack", "D10": "crack", "D20": "alligator_crack", "D40": "pothole"}


def canon(name: str) -> str | None:
    n = name.lower()
    for key, c in [("pothole", "pothole"), ("alligator", "alligator_crack"), ("patch", "patch_damage"),
                   ("crack", "crack"), ("longitudinal", "crack"), ("transverse", "crack")]:
        if key in n:
            return c
    return None


def reset(append: bool):
    if not append:
        for sub in ("images", "labels", "samples"):
            shutil.rmtree(EVAL / sub, ignore_errors=True)
        (EVAL / "results.json").unlink(missing_ok=True)
    (EVAL / "images").mkdir(parents=True, exist_ok=True)
    (EVAL / "labels").mkdir(parents=True, exist_ok=True)


def from_crack_seg(limit: int, seed: int) -> int:
    print(f"Downloading {CRACK_SEG_URL} ...")
    data = urllib.request.urlopen(CRACK_SEG_URL, timeout=120).read()
    zf = zipfile.ZipFile(io.BytesIO(data))
    imgs = sorted(n for n in zf.namelist() if "images/test/" in n and n.lower().endswith(".jpg"))
    random.Random(seed).shuffle(imgs)
    n = 0
    for name in imgs[:limit]:
        stem = Path(name).stem
        lbl = name.replace("images/", "labels/", 1).rsplit(".", 1)[0] + ".txt"
        lines = []
        for row in zf.read(lbl).decode().split("\n"):
            p = row.split()
            if len(p) < 7:
                continue
            xs, ys = list(map(float, p[1::2])), list(map(float, p[2::2]))
            x1, x2, y1, y2 = min(xs), max(xs), min(ys), max(ys)
            lines.append(f"{CANON.index('crack')} {(x1+x2)/2:.6f} {(y1+y2)/2:.6f} {x2-x1:.6f} {y2-y1:.6f}")
        out = f"crackseg_{stem[:24]}"
        (EVAL / "images" / f"{out}.jpg").write_bytes(zf.read(name))
        (EVAL / "labels" / f"{out}.txt").write_text("\n".join(lines) + "\n")
        n += 1
    (EVAL / "SOURCE.md").write_text(
        "Ultralytics crack-seg test split (Roboflow Universe, CC BY 4.0): held-out close-up crack photos, "
        "polygons converted to boxes, class = crack only. It measures crack detection; it does NOT measure "
        "pothole accuracy. Pothole/alligator false positives come from the dashcam-trained road models firing "
        "on concrete texture. For a road-view benchmark run: "
        "python scripts/prepare_eval.py --rdd <RDD2022/India/train>")
    return n


def from_rdd(path: Path, limit: int, seed: int) -> int:
    xmls = sorted((path / "annotations" / "xmls").glob("*.xml"))
    random.Random(seed).shuffle(xmls)
    n = 0
    for x in xmls:
        if n >= limit:
            break
        root = ET.parse(x).getroot()
        w, h = int(root.find("size/width").text), int(root.find("size/height").text)
        lines = []
        for obj in root.findall("object"):
            c = RDD_MAP.get(obj.find("name").text.strip())
            if not c:
                continue
            bb = obj.find("bndbox")
            x1, y1, x2, y2 = (float(bb.find(k).text) for k in ("xmin", "ymin", "xmax", "ymax"))
            lines.append(f"{CANON.index(c)} {(x1+x2)/2/w:.6f} {(y1+y2)/2/h:.6f} {(x2-x1)/w:.6f} {(y2-y1)/h:.6f}")
        if not lines:
            continue  # keep images that contain at least one mapped defect
        img = path / "images" / (x.stem + ".jpg")
        if not img.exists():
            continue
        shutil.copyfile(img, EVAL / "images" / f"rdd_{x.stem}.jpg")
        (EVAL / "labels" / f"rdd_{x.stem}.txt").write_text("\n".join(lines) + "\n")
        n += 1
    (EVAL / "SOURCE.md").write_text(f"Evaluation images: RDD2022 ({path}), Pascal VOC converted to YOLO. "
                                    "D00/D10 -> crack, D20 -> alligator_crack, D40 -> pothole.")
    return n


def from_yolo(path: Path, names: list[str], limit: int, seed: int) -> int:
    imgs = sorted(p for p in (path / "images").glob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    random.Random(seed).shuffle(imgs)
    mapping = {i: canon(nm) for i, nm in enumerate(names)}
    n = 0
    for img in imgs[:limit]:
        lbl = path / "labels" / f"{img.stem}.txt"
        lines = []
        if lbl.exists():
            for row in lbl.read_text().split("\n"):
                p = row.split()
                if len(p) == 5 and mapping.get(int(p[0])):
                    lines.append(" ".join([str(CANON.index(mapping[int(p[0])]))] + p[1:]))
        shutil.copyfile(img, EVAL / "images" / f"yolo_{img.stem}{img.suffix}")
        (EVAL / "labels" / f"yolo_{img.stem}.txt").write_text("\n".join(lines) + ("\n" if lines else ""))
        n += 1
    (EVAL / "SOURCE.md").write_text(f"Evaluation images: YOLO dataset at {path} (classes {names}).")
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--crack-seg", action="store_true")
    ap.add_argument("--rdd", type=Path)
    ap.add_argument("--yolo", type=Path)
    ap.add_argument("--names", type=str, help="comma-separated class names for --yolo")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--append", action="store_true", help="add to the existing eval set")
    a = ap.parse_args()
    reset(a.append)
    if a.rdd:
        n = from_rdd(a.rdd, a.limit, a.seed)
    elif a.yolo:
        if not a.names:
            sys.exit("--yolo needs --names")
        n = from_yolo(a.yolo, a.names.split(","), a.limit, a.seed)
    else:
        n = from_crack_seg(a.limit, a.seed)
    print(f"Wrote {n} labelled images to {EVAL}")


if __name__ == "__main__":
    main()
