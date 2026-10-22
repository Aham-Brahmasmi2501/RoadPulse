"""Geotagging helpers: EXIF GPS, GPX/CSV tracks with interpolation, haversine."""
from __future__ import annotations

import csv
import io
import math
from bisect import bisect_left
from datetime import datetime, timezone

from PIL import Image

EARTH_R_M = 6_371_000.0


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R_M * math.asin(math.sqrt(a))


# ----------------------------------------------------------------------------- EXIF
def _dms_to_deg(dms, ref) -> float:
    d, m, s = (float(x) for x in dms)
    deg = d + m / 60 + s / 3600
    return -deg if ref in ("S", "W") else deg


def read_exif(path) -> tuple[float | None, float | None, datetime | None]:
    """Returns (lat, lon, timestamp) from image EXIF; any value may be None."""
    lat = lon = ts = None
    try:
        img = Image.open(path)
        exif = img.getexif()
        gps = exif.get_ifd(0x8825)  # GPSInfo IFD
        if gps and 2 in gps and 4 in gps:
            lat = _dms_to_deg(gps[2], gps.get(1, "N"))
            lon = _dms_to_deg(gps[4], gps.get(3, "E"))
        # DateTimeOriginal lives in the Exif sub-IFD; fall back to DateTime
        raw = exif.get_ifd(0x8769).get(36867) or exif.get(306)
        if raw:
            ts = datetime.strptime(str(raw).strip("\x00"), "%Y:%m:%d %H:%M:%S")
    except Exception:  # unreadable / no EXIF -> just return what we have
        pass
    return lat, lon, ts


# ----------------------------------------------------------------------------- tracks
class Track:
    """A time-ordered GPS track; locate() linearly interpolates lat/lon."""

    def __init__(self, points: list[tuple[datetime, float, float]]):
        self.points = sorted(points, key=lambda p: p[0])
        self.times = [p[0].timestamp() for p in self.points]

    @property
    def start(self) -> datetime | None:
        return self.points[0][0] if self.points else None

    def locate(self, when: datetime) -> tuple[float, float] | None:
        if not self.points:
            return None
        t = when.timestamp()
        if t <= self.times[0]:
            return self.points[0][1:]
        if t >= self.times[-1]:
            return self.points[-1][1:]
        i = bisect_left(self.times, t)
        t0, t1 = self.times[i - 1], self.times[i]
        f = (t - t0) / (t1 - t0) if t1 > t0 else 0
        (_, la0, lo0), (_, la1, lo1) = self.points[i - 1], self.points[i]
        return la0 + f * (la1 - la0), lo0 + f * (lo1 - lo0)


def _parse_time(v: str, base: datetime | None) -> datetime:
    """Accepts ISO-8601 timestamps or plain seconds-from-start numbers."""
    v = v.strip()
    try:
        secs = float(v)
        base = base or datetime(2026, 1, 1)
        return datetime.fromtimestamp(base.timestamp() + secs)
    except ValueError:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def parse_track(data: bytes, filename: str) -> Track:
    """Parses a GPX file or a CSV with columns time,lat,lon (header required)."""
    text = data.decode("utf-8", errors="ignore")
    points: list[tuple[datetime, float, float]] = []
    if filename.lower().endswith(".gpx") or text.lstrip().startswith("<"):
        import gpxpy
        gpx = gpxpy.parse(text)
        for trk in gpx.tracks:
            for seg in trk.segments:
                for p in seg.points:
                    if p.time is not None:
                        t = p.time.astimezone(timezone.utc).replace(tzinfo=None) if p.time.tzinfo else p.time
                        points.append((t, p.latitude, p.longitude))
    else:
        reader = csv.DictReader(io.StringIO(text))
        cols = {c.lower().strip(): c for c in reader.fieldnames or []}
        tcol = cols.get("time") or cols.get("timestamp") or cols.get("t")
        latcol = cols.get("lat") or cols.get("latitude")
        loncol = cols.get("lon") or cols.get("lng") or cols.get("longitude")
        if not (tcol and latcol and loncol):
            raise ValueError("CSV track needs columns: time, lat, lon")
        for row in reader:
            points.append((_parse_time(row[tcol], None), float(row[latcol]), float(row[loncol])))
    if len(points) < 1:
        raise ValueError("GPS track contains no timed points")
    return Track(points)
