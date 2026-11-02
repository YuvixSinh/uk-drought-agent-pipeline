"""
Open-Meteo Weather, Soil-Moisture & 10-Year Baseline Client (F3) — Orbital Agronomist (v2)
Fetches:
1. Recent 30-day + 15-day forecast daily rain/ET0/temps + hourly 3-depth soil moisture & 0-7cm soil temp.
2. 10-year daily archive baseline (2016-01-01 to 2025-12-31) for the matching 30-day & 90-day calendar windows.
Includes disk caching in `cache/`, fallback fixtures in `fixtures/`, outbound call logging, and live FeedEvent emission.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from events import append_feed_event, log_outbound_call

CACHE_DIR = Path(__file__).parent / "cache"
FIXTURES_DIR = Path(__file__).parent / "fixtures"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


def _grid_key(lat: float, lon: float) -> tuple[float, float, str]:
    g_lat = round(round(float(lat) / 0.1) * 0.1, 2)
    g_lon = round(round(float(lon) / 0.1) * 0.1, 2)
    ns = "N" if g_lat >= 0 else "S"
    ew = "E" if g_lon >= 0 else "W"
    label = f"{abs(g_lat):.2f}°{ns}, {abs(g_lon):.2f}°{ew}"
    return g_lat, g_lon, label


def _cache_file(prefix: str, g_lat: float, g_lon: float, extra: str = "") -> Path:
    raw = f"{prefix}_{g_lat:.2f}_{g_lon:.2f}_{extra}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return CACHE_DIR / f"{prefix}_{g_lat:.2f}_{g_lon:.2f}_{digest}.json"


def _percentile_rank(values: list[float], target: float) -> int:
    if not values:
        return 50
    clean = sorted(float(v) for v in values if v is not None and not math.isnan(float(v)))
    if not clean:
        return 50
    below = sum(1 for v in clean if v <= target)
    return max(1, min(99, int(round(100.0 * below / len(clean)))))


def fetch_forecast_and_recent(
    lat: float,
    lon: float,
    run_id: str,
    on_event: Callable[[str, str, str], None] | None = None,
    timeout_s: float = 10.0,
) -> dict[str, Any]:
    """
    Fetch past 30 days + next 15 days from Open-Meteo /v1/forecast.
    Falls back to disk cache or deterministic fixture if offline.
    """
    g_lat, g_lon, grid_label = _grid_key(lat, lon)
    today_str = date.today().isoformat()
    cpath = _cache_file("forecast", g_lat, g_lon, today_str)

    params = {
        "latitude": f"{lat:.4f}",
        "longitude": f"{lon:.4f}",
        "daily": "precipitation_sum,et0_fao_evapotranspiration,temperature_2m_max,temperature_2m_min",
        "hourly": "soil_moisture_0_to_7cm,soil_moisture_7_to_28cm,soil_moisture_28_to_100cm,soil_temperature_0_to_7cm",
        "past_days": "30",
        "forecast_days": "15",
        "timezone": "Europe/London",
    }
    url = f"{FORECAST_URL}?{urllib.parse.urlencode(params)}"

    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "OrbitalAgronomist/2.0"})
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw_bytes = resp.read()
            payload = json.loads(raw_bytes.decode("utf-8"))
        latency_ms = int((time.perf_counter() - t0) * 1000)

        actual_lat = payload.get("latitude", g_lat)
        actual_lon = payload.get("longitude", g_lon)
        actual_grid = f"{actual_lat:.2f}°N, {actual_lon:.2f}°E"

        # Save to disk cache
        cpath.write_text(json.dumps({"fetched_at": time.time(), "payload": payload}), encoding="utf-8")

        log_outbound_call(
            endpoint="Open-Meteo /v1/forecast",
            grid_cell=actual_grid,
            run_id=run_id,
            status="200 OK (LIVE)",
            latency_ms=latency_ms,
        )
        msg = f"GET /v1/forecast (past_days=30, forecast_days=15, soil 3 depths) -> 200 OK in {latency_ms} ms"
        append_feed_event(run_id, "OPEN-METEO", msg, "ok")
        if on_event:
            on_event("OPEN-METEO", msg, "ok")

        return {
            "source_state": "LIVE",
            "latency_ms": latency_ms,
            "grid_cell": actual_grid,
            "payload": payload,
        }
    except Exception as exc:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        # Try any existing forecast cache for this grid cell
        candidates = sorted(CACHE_DIR.glob(f"forecast_{g_lat:.2f}_{g_lon:.2f}_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if candidates:
            cached_obj = json.loads(candidates[0].read_text(encoding="utf-8"))
            payload = cached_obj["payload"]
            log_outbound_call(
                endpoint="Open-Meteo /v1/forecast",
                grid_cell=grid_label,
                run_id=run_id,
                status="CACHE_FALLBACK",
                latency_ms=latency_ms,
            )
            msg = f"GET /v1/forecast failed ({type(exc).__name__}); loaded disk cache for {grid_label}"
            append_feed_event(run_id, "OPEN-METEO", msg, "warn")
            if on_event:
                on_event("OPEN-METEO", msg, "warn")
            return {
                "source_state": "CACHED",
                "latency_ms": latency_ms,
                "grid_cell": grid_label,
                "payload": payload,
            }

        # Synthesize deterministic offline fixture so app never crashes
        payload = _build_fallback_forecast_payload(lat, lon)
        log_outbound_call(
            endpoint="Open-Meteo /v1/forecast",
            grid_cell=grid_label,
            run_id=run_id,
            status="FIXTURE_FALLBACK",
            latency_ms=latency_ms,
        )
        msg = f"GET /v1/forecast unreachable; using deterministic offline fixture for {grid_label}"
        append_feed_event(run_id, "OPEN-METEO", msg, "warn")
        if on_event:
            on_event("OPEN-METEO", msg, "warn")
        return {
            "source_state": "DEMO FIXTURE",
            "latency_ms": latency_ms,
            "grid_cell": grid_label,
            "payload": payload,
        }


def fetch_10y_baseline(
    lat: float,
    lon: float,
    run_id: str,
    on_event: Callable[[str, str, str], None] | None = None,
    timeout_s: float = 12.0,
) -> dict[str, Any]:
    """
    Fetch 10-year historical daily baseline (2016-01-01 to 2025-12-31) from Open-Meteo /v1/archive.
    Uses persistent disk cache keyed by 0.1-deg grid cell so repeat runs take <15 ms.
    """
    g_lat, g_lon, grid_label = _grid_key(lat, lon)
    cpath = _cache_file("archive10y", g_lat, g_lon, "2016_2025")

    if cpath.exists():
        t0 = time.perf_counter()
        try:
            cached_obj = json.loads(cpath.read_text(encoding="utf-8"))
            latency_ms = max(1, int((time.perf_counter() - t0) * 1000))
            msg = f"Loaded 10-year daily baseline (2016–2025, 3,653 days) from disk cache in {latency_ms} ms"
            append_feed_event(run_id, "BASELINE", msg, "ok")
            if on_event:
                on_event("BASELINE", msg, "ok")
            return {
                "source_state": "CACHED",
                "latency_ms": latency_ms,
                "payload": cached_obj["payload"],
            }
        except Exception:
            pass

    params = {
        "latitude": f"{lat:.4f}",
        "longitude": f"{lon:.4f}",
        "start_date": "2016-01-01",
        "end_date": "2025-12-31",
        "daily": "precipitation_sum,et0_fao_evapotranspiration",
        "timezone": "Europe/London",
    }
    url = f"{ARCHIVE_URL}?{urllib.parse.urlencode(params)}"
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "OrbitalAgronomist/2.0"})
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw_bytes = resp.read()
            payload = json.loads(raw_bytes.decode("utf-8"))
        latency_ms = int((time.perf_counter() - t0) * 1000)

        cpath.write_text(json.dumps({"fetched_at": time.time(), "payload": payload}), encoding="utf-8")
        log_outbound_call(
            endpoint="Open-Meteo /v1/archive (2016-2025)",
            grid_cell=grid_label,
            run_id=run_id,
            status="200 OK (LIVE)",
            latency_ms=latency_ms,
        )
        days_cnt = len(payload.get("daily", {}).get("time", []))
        msg = f"GET /v1/archive (2016–2025, {days_cnt:,} days) -> 200 OK in {latency_ms} ms (saved to disk cache)"
        append_feed_event(run_id, "OPEN-METEO", msg, "ok")
        if on_event:
            on_event("OPEN-METEO", msg, "ok")
        return {
            "source_state": "LIVE",
            "latency_ms": latency_ms,
            "payload": payload,
        }
    except Exception as exc:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        payload = _build_fallback_archive_payload(lat, lon)
        log_outbound_call(
            endpoint="Open-Meteo /v1/archive (2016-2025)",
            grid_cell=grid_label,
            run_id=run_id,
            status="FIXTURE_FALLBACK",
            latency_ms=latency_ms,
        )
        msg = f"GET /v1/archive failed ({type(exc).__name__}); using deterministic 10y baseline fixture"
        append_feed_event(run_id, "OPEN-METEO", msg, "warn")
        if on_event:
            on_event("OPEN-METEO", msg, "warn")
        return {
            "source_state": "DEMO FIXTURE",
            "latency_ms": latency_ms,
            "payload": payload,
        }


def compute_10y_window_stats(archive_payload: dict[str, Any], ref_date: date | None = None) -> dict[str, Any]:
    """
    Compute 10-year (2016-2025) baseline statistics for:
    1) The 30-day calendar window ending on ref_date's month/day across each year 2016..2025.
    2) The 90-day forward calendar window starting on ref_date's month/day across each year 2016..2024.
    """
    ref = ref_date or date.today()
    daily = archive_payload.get("daily", {})
    times = daily.get("time", [])
    rains = daily.get("precipitation_sum", [])
    et0s = daily.get("et0_fao_evapotranspiration", [])

    by_date: dict[str, tuple[float, float]] = {}
    for t_str, r_val, e_val in zip(times, rains, et0s):
        r_clean = float(r_val) if r_val is not None else 0.0
        e_clean = float(e_val) if e_val is not None else 1.2
        by_date[t_str] = (r_clean, e_clean)

    yearly_30d_rain: dict[int, float] = {}
    yearly_30d_et0: dict[int, float] = {}
    yearly_90d_rain: list[float] = []

    for yr in range(2016, 2026):
        try:
            anchor = date(yr, ref.month, min(ref.day, 28 if ref.month == 2 else ref.day))
        except ValueError:
            anchor = date(yr, ref.month, 28)

        # Past 30-day window in year `yr`
        r_sum, e_sum, count = 0.0, 0.0, 0
        for d_back in range(30):
            d_str = (anchor - timedelta(days=d_back)).isoformat()
            if d_str in by_date:
                r_sum += by_date[d_str][0]
                e_sum += by_date[d_str][1]
                count += 1
        if count >= 20:
            yearly_30d_rain[yr] = round(r_sum, 1)
            yearly_30d_et0[yr] = round(e_sum, 1)

        # Forward 90-day window in year `yr`
        r90_sum, c90 = 0.0, 0
        for d_fwd in range(1, 91):
            d_str = (anchor + timedelta(days=d_fwd)).isoformat()
            if d_str in by_date:
                r90_sum += by_date[d_str][0]
                c90 += 1
        if c90 >= 60:
            yearly_90d_rain.append(round(r90_sum, 1))

    rain_vals = list(yearly_30d_rain.values()) or [62.0] * 10
    et0_vals = list(yearly_30d_et0.values()) or [36.0] * 10
    mean_30d_rain = round(sum(rain_vals) / len(rain_vals), 1)
    mean_30d_et0 = round(sum(et0_vals) / len(et0_vals), 1)
    mean_90d_rain = round(sum(yearly_90d_rain) / len(yearly_90d_rain), 1) if yearly_90d_rain else round(mean_30d_rain * 3.0, 1)

    return {
        "yearly_30d_rain": yearly_30d_rain,
        "yearly_30d_et0": yearly_30d_et0,
        "mean_30d_rain_mm": mean_30d_rain,
        "mean_30d_et0_mm": mean_30d_et0,
        "mean_90d_rain_mm": mean_90d_rain,
        "rain_30d_series": rain_vals,
    }


def _build_fallback_forecast_payload(lat: float, lon: float) -> dict[str, Any]:
    """Deterministic fallback forecast payload (30 past days + 15 forecast days) if completely offline."""
    today = date.today()
    start = today - timedelta(days=30)
    days = [(start + timedelta(days=i)).isoformat() for i in range(45)]
    # Slightly wetter in western/northern UK, drier in East Anglia
    wet_factor = 1.35 if lon < -2.5 or lat > 55.0 else 0.9
    precip = [round(((i * 7 + 3) % 11) * 0.45 * wet_factor if (i % 3 == 0) else 0.0, 1) for i in range(45)]
    et0 = [round(1.25 - 0.01 * i, 2) for i in range(45)]
    tmax = [round(13.5 - 0.05 * i, 1) for i in range(45)]
    tmin = [round(6.8 - 0.04 * i, 1) for i in range(45)]

    hours = []
    sm0, sm7, sm28, st0 = [], [], [], []
    base_sm = 0.28 if wet_factor > 1.0 else 0.23
    for d_idx in range(45):
        for h in range(24):
            hours.append(f"{days[d_idx]}T{h:02d}:00")
            sm0.append(round(base_sm + 0.01 * math.sin(d_idx / 4.0), 3))
            sm7.append(round(base_sm + 0.02 + 0.008 * math.cos(d_idx / 5.0), 3))
            sm28.append(round(base_sm + 0.05, 3))
            st0.append(round(9.8 - 0.03 * d_idx, 1))

    return {
        "latitude": round(lat, 2),
        "longitude": round(lon, 2),
        "daily": {
            "time": days,
            "precipitation_sum": precip,
            "et0_fao_evapotranspiration": et0,
            "temperature_2m_max": tmax,
            "temperature_2m_min": tmin,
        },
        "hourly": {
            "time": hours,
            "soil_moisture_0_to_7cm": sm0,
            "soil_moisture_7_to_28cm": sm7,
            "soil_moisture_28_to_100cm": sm28,
            "soil_temperature_0_to_7cm": st0,
        },
    }


def _build_fallback_archive_payload(lat: float, lon: float) -> dict[str, Any]:
    """Deterministic fallback 10-year archive payload if offline and uncached."""
    wet_factor = 1.35 if lon < -2.5 or lat > 55.0 else 0.95
    d0 = date(2016, 1, 1)
    d_end = date(2025, 12, 31)
    total_days = (d_end - d0).days + 1
    times, rains, et0s = [], [], []
    for i in range(total_days):
        cur = d0 + timedelta(days=i)
        times.append(cur.isoformat())
        rains.append(round((1.9 * wet_factor) if (i % 2 == 0) else 0.3, 1))
        et0s.append(1.3)
    return {
        "latitude": round(lat, 2),
        "longitude": round(lon, 2),
        "daily": {
            "time": times,
            "precipitation_sum": rains,
            "et0_fao_evapotranspiration": et0s,
        },
    }
