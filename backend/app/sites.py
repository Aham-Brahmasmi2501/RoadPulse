"""Duplicate grouping (DBSCAN) and the transparent priority score."""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import datetime

import numpy as np
from sklearn.cluster import DBSCAN, AgglomerativeClustering
from sklearn.metrics.pairwise import haversine_distances
from sqlalchemy.orm import Session

from .config import settings
from .db import Report, Site, utcnow
from .geo import EARTH_R_M

COMPONENT_LABELS = {
    "size": "Size",
    "confidence": "Confidence",
    "sightings": "Sightings",
    "defect_type": "Defect type",
    "road_context": "Road context",
    "recency": "Recency",
}


def severity_for(score: float) -> str:
    bands = settings()["scoring"]["bands"]
    if score > bands["high"]:
        return "high"
    if score >= bands["medium"]:
        return "medium"
    return "low"


def compute_score(reports: list[Report], road_context: str, now: datetime | None = None) -> tuple[float, list[dict]]:
    """Score (0-100) for a group of reports of the same defect.

    Each component is normalised to 0..1 then multiplied by its configured
    weight; the score is the plain sum, so the breakdown always adds up.
    """
    sc = settings()["scoring"]
    w = sc["weights"]
    now = now or utcnow()
    cls = reports[0].defect_class
    last_seen = max(r.timestamp for r in reports)
    age_days = max(0.0, (now - last_seen).total_seconds() / 86400)

    norm = {
        # Largest visible extent among sightings; area ratio saturates at size_full_at
        "size": min(1.0, max(r.bbox_area_ratio for r in reports) / sc["size_full_at"]),
        "confidence": float(np.mean([r.confidence for r in reports])),
        # log scale: 1 sighting ~ 0.32, 3 ~ 0.63, 8+ = 1.0 (with full_at=8)
        "sightings": min(1.0, math.log1p(len(reports)) / math.log1p(sc["sightings_full_at"])),
        "defect_type": sc["type_weights"].get(cls, 0.3),
        "road_context": sc["road_weights"].get(road_context, 0.5),
        "recency": 0.5 ** (age_days / sc["recency_half_life_days"]),
    }
    raw = {
        "size": f"{max(r.bbox_area_ratio for r in reports) * 100:.1f}% of frame",
        "confidence": f"{norm['confidence']:.2f} avg",
        "sightings": f"{len(reports)} report(s)",
        "defect_type": cls.replace("_", " "),
        "road_context": road_context.replace("_", " "),
        "recency": f"{age_days:.0f} day(s) ago",
    }
    components = [
        {"key": k, "label": COMPONENT_LABELS[k], "weight": w[k], "normalized": round(norm[k], 3),
         "points": round(norm[k] * w[k], 1), "detail": raw[k]}
        for k in w
    ]
    return round(sum(c["points"] for c in components), 1), components


def _site_status(reports: list[Report]) -> str:
    st = {r.status for r in reports}
    if st == {"repaired"}:
        return "repaired"
    if "confirmed" in st:
        return "confirmed"
    if "repaired" in st and "pending" not in st:
        return "repaired"
    return "pending"


def _split_wide(groups: dict, max_span_m: float) -> list[list[Report]]:
    """Splits DBSCAN clusters whose diameter exceeds max_span_m (anti-chaining)."""
    out = []
    for grp in groups.values():
        if len(grp) < 2:
            out.append(grp)
            continue
        d = haversine_distances(np.radians([[r.lat, r.lon] for r in grp])) * EARTH_R_M
        if d.max() <= max_span_m:
            out.append(grp)
            continue
        labels = AgglomerativeClustering(n_clusters=None, metric="precomputed", linkage="complete",
                                         distance_threshold=max_span_m).fit(d).labels_
        sub: dict[int, list[Report]] = defaultdict(list)
        for r, lab in zip(grp, labels):
            sub[lab].append(r)
        out.extend(sub.values())
    return out


def recompute_sites(db: Session) -> int:
    """Re-clusters all located, non-rejected reports into Defect Sites.

    DBSCAN runs per defect class with the haversine metric, eps = eps_m metres;
    over-wide clusters are then split so a site never exceeds max_span_m.
    """
    cfg = settings()["clustering"]
    eps_rad = cfg["eps_m"] / EARTH_R_M
    reports = (db.query(Report)
               .filter(Report.lat.isnot(None), Report.lon.isnot(None), Report.status != "rejected")
               .all())
    # Rejected / unlocated reports never belong to a site
    db.query(Report).filter((Report.status == "rejected") | Report.lat.is_(None)).update({Report.site_id: None})

    by_class: dict[str, list[Report]] = defaultdict(list)
    for r in reports:
        by_class[r.defect_class].append(r)

    new_sites: list[Site] = []
    for cls, items in by_class.items():
        coords = np.radians([[r.lat, r.lon] for r in items])
        labels = DBSCAN(eps=eps_rad, min_samples=cfg["min_samples"], metric="haversine",
                        algorithm="ball_tree").fit(coords).labels_
        groups: dict[int, list[Report]] = defaultdict(list)
        for r, lab in zip(items, labels):
            # min_samples=1 means no noise; guard anyway by giving noise its own site
            groups[lab if lab >= 0 else -r.id].append(r)
        for grp in _split_wide(groups, cfg.get("max_span_m", 1e9)):
            site_id = min(r.id for r in grp)
            road = Counter(r.road_context for r in grp).most_common(1)[0][0]
            # Score only counts reports that are still open (not repaired) when any are open
            open_reports = [r for r in grp if r.status != "repaired"] or grp
            score, comps = compute_score(open_reports, road)
            best = max(grp, key=lambda r: (r.status == "confirmed", r.confidence * (0.5 + r.bbox_area_ratio)))
            status = _site_status(grp)
            for r in grp:
                r.site_id = site_id
            new_sites.append(Site(
                id=site_id, defect_class=cls,
                lat=float(np.mean([r.lat for r in grp])), lon=float(np.mean([r.lon for r in grp])),
                sightings=len(grp), first_seen=min(r.timestamp for r in grp),
                last_seen=max(r.timestamp for r in grp), best_report_id=best.id,
                score=0.0 if status == "repaired" else score,
                severity="low" if status == "repaired" else severity_for(score),
                components=comps, status=status, road_context=road,
            ))
    db.query(Site).delete()
    db.add_all(new_sites)
    db.commit()
    return len(new_sites)
