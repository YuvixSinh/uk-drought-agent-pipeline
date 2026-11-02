"""
UK Land Validation (F2) — Orbital Agronomist (v2)
Validates any (lat, lon) coordinate locally against Natural Earth 1:10m admin-0 map units
for the United Kingdom (England, Scotland, Wales, Northern Ireland, including Shetland,
Orkney, the Hebrides, Anglesey, and the Isle of Wight).
Republic of Ireland, Isle of Man, and Channel Islands are excluded per specification.
"""

from __future__ import annotations

import json
import math
import os
from functools import lru_cache
from typing import Any

# Demo heuristic coastal tolerance in km for near-coast clicks
COASTAL_TOLERANCE_KM = 3.5

_UK_GEOJSON_PATH = os.path.join(os.path.dirname(__file__), "uk_10m.geojson")


@lru_cache(maxsize=1)
def _load_uk_features() -> list[dict[str, Any]]:
    with open(_UK_GEOJSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("features", [])


def _point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi
        ):
            inside = not inside
        j = i
    return inside


def _point_in_polygon(lon: float, lat: float, rings: list[list[list[float]]]) -> bool:
    if not rings or not _point_in_ring(lon, lat, rings[0]):
        return False
    for hole in rings[1:]:
        if _point_in_ring(lon, lat, hole):
            return False
    return True


def _min_distance_km_to_ring(lon: float, lat: float, ring: list[list[float]]) -> float:
    cos_lat = math.cos(math.radians(lat))
    min_d2 = float("inf")
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        dx = (x2 - x1) * cos_lat * 111.32
        dy = (y2 - y1) * 111.32
        px = (lon - x1) * cos_lat * 111.32
        py = (lat - y1) * 111.32
        seg_len2 = dx * dx + dy * dy
        if seg_len2 > 1e-12:
            t = max(0.0, min(1.0, (px * dx + py * dy) / seg_len2))
            proj_x = t * dx
            proj_y = t * dy
            d2 = (px - proj_x) ** 2 + (py - proj_y) ** 2
        else:
            d2 = px * px + py * py
        if d2 < min_d2:
            min_d2 = d2
    return math.sqrt(min_d2)


def _broad_geographic_context(lat: float, lon: float, unit: str | None) -> str:
    if not unit:
        return "Outside UK land boundary"
    if unit == "Scotland":
        if lat >= 59.8:
            return "Shetland Isles · Northern Scotland"
        if lat >= 58.7 and lon > -3.6:
            return "Orkney Isles · Northern Scotland"
        if lon < -5.8 and lat >= 56.5:
            return "Hebrides / Western Isles · Scotland"
        if lat >= 56.8:
            return "Scottish Highlands / North"
        return "Central & Southern Scotland"
    if unit == "Northern Ireland":
        return "Northern Ireland"
    if unit == "Wales":
        if lat >= 53.15 and lon < -4.1:
            return "Isle of Anglesey / North West Wales"
        if lat >= 52.6:
            return "North Wales"
        if lat <= 51.75:
            return "South Wales"
        return "Mid & West Wales"
    # England
    if lat <= 50.78 and -1.6 <= lon <= -1.05:
        return "Isle of Wight · Southern England"
    if lat >= 54.0:
        return "Northern England"
    if lon >= 0.0 and 51.8 <= lat <= 53.0:
        return "East Anglia · Eastern England"
    if lat <= 51.6 and lon < -2.2:
        return "South West England"
    if lat <= 51.7 and lon >= -2.2:
        return "Southern England / Thames Valley"
    return "Midlands & Central England"


def estimate_grid_cell(lat: float, lon: float) -> str:
    """Approximate 0.1 deg (~9-11 km) model grid cell representation prior to live API fetch."""
    g_lat = round(round(lat / 0.1) * 0.1, 2)
    g_lon = round(round(lon / 0.1) * 0.1, 2)
    return f"{g_lat:.2f}°, {g_lon:.2f}°"


def validate_uk_coordinate(
    lat: float,
    lon: float,
    coastal_tolerance_km: float = COASTAL_TOLERANCE_KM,
) -> dict[str, Any]:
    """
    Validate whether (lat, lon) is inside UK land or within the coastal tolerance heuristic.
    Returns dict with keys:
      valid (bool), status ('uk_land' | 'near_coast' | 'non_uk'),
      unit (str | None), land_status (str), context (str),
      grid_cell (str), dist_km (float)
    """
    # Quick bounding check before polygon test (Shetland to Scilly, Rockall/NI to Lowestoft)
    if not (49.7 <= lat <= 61.2 and -8.8 <= lon <= 2.1):
        return {
            "valid": False,
            "status": "non_uk",
            "unit": None,
            "land_status": "Not UK land. No data requested.",
            "context": "Outside UK land boundary",
            "grid_cell": estimate_grid_cell(lat, lon),
            "dist_km": 999.0,
        }

    features = _load_uk_features()
    best_unit = None
    min_dist = float("inf")

    for feat in features:
        unit = feat.get("properties", {}).get("unit", "UK")
        geom = feat.get("geometry", {})
        gtype = geom.get("type")
        polys = [geom["coordinates"]] if gtype == "Polygon" else geom.get("coordinates", [])
        for poly in polys:
            if _point_in_polygon(lon, lat, poly):
                ctx = _broad_geographic_context(lat, lon, unit)
                return {
                    "valid": True,
                    "status": "uk_land",
                    "unit": unit,
                    "admin_area": unit,
                    "land_status": f"UK land · {unit}",
                    "context": ctx,
                    "geographic_context": ctx,
                    "grid_cell": estimate_grid_cell(lat, lon),
                    "dist_km": 0.0,
                }
            d = _min_distance_km_to_ring(lon, lat, poly[0])
            if d < min_dist:
                min_dist = d
                best_unit = unit

    if min_dist <= coastal_tolerance_km and best_unit is not None:
        ctx = f"{_broad_geographic_context(lat, lon, best_unit)} (coastal margin)"
        return {
            "valid": True,
            "status": "near_coast",
            "unit": best_unit,
            "admin_area": best_unit,
            "land_status": f"Near coast · classification uncertain ({best_unit}, ~{min_dist:.1f} km demo heuristic)",
            "context": ctx,
            "geographic_context": ctx,
            "grid_cell": estimate_grid_cell(lat, lon),
            "dist_km": round(min_dist, 2),
        }

    return {
        "valid": False,
        "status": "non_uk",
        "unit": None,
        "admin_area": None,
        "land_status": "Not UK land. No data requested.",
        "context": "Sea or non-UK territory",
        "geographic_context": "Sea or non-UK territory",
        "grid_cell": estimate_grid_cell(lat, lon),
        "dist_km": round(min_dist, 2),
    }
