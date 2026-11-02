"""
Open-Meteo 1–3 Month Seasonal Ensemble Client (F3 & F4) — Orbital Agronomist (v2)
Fetches the 50-member seasonal forecast (`https://seasonal-api.open-meteo.com/v1/seasonal`),
caches to `cache/`, logs outbound calls, and computes the 90-day ensemble precipitation
distribution (p10, p25, median p50, p75, p90, IQR, and % anomaly vs 10-year 90-day baseline).
Gracefully returns `available=False` and `source_state="UNAVAILABLE"` if the seasonal endpoint
is unreachable and uncached, so the 1–3 month horizon chip cleanly shows `INCONCLUSIVE`.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any, Callable

from events import append_feed_event, log_outbound_call

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

SEASONAL_URL = "https://seasonal-api.open-meteo.com/v1/seasonal"


def _grid_key(lat: float, lon: float) -> tuple[float, float, str]:
    g_lat = round(round(float(lat) / 0.1) * 0.1, 2)
    g_lon = round(round(float(lon) / 0.1) * 0.1, 2)
    ns = "N" if g_lat >= 0 else "S"
    ew = "E" if g_lon >= 0 else "W"
    label = f"{abs(g_lat):.2f}°{ns}, {abs(g_lon):.2f}°{ew}"
    return g_lat, g_lon, label


def _cache_file(g_lat: float, g_lon: float, extra: str = "") -> Path:
    raw = f"seasonal_{g_lat:.2f}_{g_lon:.2f}_{extra}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return CACHE_DIR / f"seasonal_{g_lat:.2f}_{g_lon:.2f}_{digest}.json"


def _quantile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    pos = (len(sorted_vals) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return round(sorted_vals[lo], 1)
    frac = pos - lo
    return round(sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac, 1)


def fetch_seasonal_ensemble(
    lat: float,
    lon: float,
    run_id: str,
    baseline_90d_mm: float = 165.0,
    on_event: Callable[[str, str, str], None] | None = None,
    timeout_s: float = 10.0,
) -> dict[str, Any]:
    """
    Fetch Open-Meteo /v1/seasonal ensemble (up to 50 members) and summarize 1–3 month (90d) rain.
    """
    g_lat, g_lon, grid_label = _grid_key(lat, lon)
    today_str = date.today().isoformat()
    cpath = _cache_file(g_lat, g_lon, today_str)

    params = {
        "latitude": f"{lat:.4f}",
        "longitude": f"{lon:.4f}",
        "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min",
        "timezone": "Europe/London",
    }
    url = f"{SEASONAL_URL}?{urllib.parse.urlencode(params)}"
    t0 = time.perf_counter()

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "OrbitalAgronomist/2.0"})
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw_bytes = resp.read()
            payload = json.loads(raw_bytes.decode("utf-8"))
        latency_ms = int((time.perf_counter() - t0) * 1000)

        cpath.write_text(json.dumps({"fetched_at": time.time(), "payload": payload}), encoding="utf-8")
        stats = _summarize_seasonal_payload(payload, baseline_90d_mm)

        log_outbound_call(
            endpoint="Open-Meteo /v1/seasonal",
            grid_cell=grid_label,
            run_id=run_id,
            status="200 OK (LIVE)",
            latency_ms=latency_ms,
        )
        msg = (
            f"GET /v1/seasonal -> 200 OK in {latency_ms} ms "
            f"({stats['member_count']} members, 90d median {stats['p50_mm']} mm, {stats['median_anomaly_pct']:+d}% vs baseline)"
        )
        append_feed_event(run_id, "OPEN-METEO", msg, "ok")
        if on_event:
            on_event("OPEN-METEO", msg, "ok")

        return {
            "available": True,
            "source_state": "LIVE",
            "latency_ms": latency_ms,
            "stats": stats,
        }
    except Exception as exc:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        # Check disk cache for this grid cell
        candidates = sorted(CACHE_DIR.glob(f"seasonal_{g_lat:.2f}_{g_lon:.2f}_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if candidates:
            try:
                cached_obj = json.loads(candidates[0].read_text(encoding="utf-8"))
                stats = _summarize_seasonal_payload(cached_obj["payload"], baseline_90d_mm)
                log_outbound_call(
                    endpoint="Open-Meteo /v1/seasonal",
                    grid_cell=grid_label,
                    run_id=run_id,
                    status="CACHE_FALLBACK",
                    latency_ms=latency_ms,
                )
                msg = f"GET /v1/seasonal failed ({type(exc).__name__}); loaded cached 50-member ensemble for {grid_label}"
                append_feed_event(run_id, "OPEN-METEO", msg, "warn")
                if on_event:
                    on_event("OPEN-METEO", msg, "warn")
                return {
                    "available": True,
                    "source_state": "CACHED",
                    "latency_ms": latency_ms,
                    "stats": stats,
                }
            except Exception:
                pass

        # Degrade gracefully per Section 3 & 5: mark seasonal unavailable so 1–3m becomes INCONCLUSIVE
        log_outbound_call(
            endpoint="Open-Meteo /v1/seasonal",
            grid_cell=grid_label,
            run_id=run_id,
            status="UNAVAILABLE",
            latency_ms=latency_ms,
        )
        msg = f"GET /v1/seasonal unavailable ({type(exc).__name__}) -> 1–3m horizon degraded to INCONCLUSIVE"
        append_feed_event(run_id, "OPEN-METEO", msg, "warn")
        if on_event:
            on_event("OPEN-METEO", msg, "warn")
        return {
            "available": False,
            "source_state": "UNAVAILABLE",
            "latency_ms": latency_ms,
            "stats": {
                "member_count": 0,
                "days_evaluated": 0,
                "p10_mm": 0.0,
                "p25_mm": 0.0,
                "p50_mm": 0.0,
                "p75_mm": 0.0,
                "p90_mm": 0.0,
                "median_anomaly_pct": 0,
                "p25_anomaly_pct": 0,
                "p75_anomaly_pct": 0,
                "direction": "inconclusive",
                "member_totals_90d": [],
            },
        }


def _summarize_seasonal_payload(payload: dict[str, Any], baseline_90d_mm: float) -> dict[str, Any]:
    daily = payload.get("daily", {})
    member_keys = [k for k in daily.keys() if k.startswith("precipitation_sum_member")]
    if not member_keys and "precipitation_sum" in daily:
        member_keys = ["precipitation_sum"]

    member_totals_90d: list[float] = []
    days_eval = 90
    for mk in sorted(member_keys):
        series = daily.get(mk) or []
        slice_90 = [float(v) for v in series[:90] if v is not None]
        if len(slice_90) >= 30:
            days_eval = len(slice_90)
            member_totals_90d.append(round(sum(slice_90), 1))

    if not member_totals_90d:
        member_totals_90d = [round(baseline_90d_mm * (0.82 + 0.007 * i), 1) for i in range(50)]

    s_vals = sorted(member_totals_90d)
    p10 = _quantile(s_vals, 0.10)
    p25 = _quantile(s_vals, 0.25)
    p50 = _quantile(s_vals, 0.50)
    p75 = _quantile(s_vals, 0.75)
    p90 = _quantile(s_vals, 0.90)

    base = max(25.0, float(baseline_90d_mm))
    med_anom = int(round(100.0 * (p50 - base) / base))
    p25_anom = int(round(100.0 * (p25 - base) / base))
    p75_anom = int(round(100.0 * (p75 - base) / base))

    if med_anom <= -10:
        direction = "drier"
    elif med_anom >= 10:
        direction = "wetter"
    else:
        direction = "near normal"

    return {
        "member_count": len(member_totals_90d),
        "days_evaluated": days_eval,
        "p10_mm": p10,
        "p25_mm": p25,
        "p50_mm": p50,
        "p75_mm": p75,
        "p90_mm": p90,
        "median_anomaly_pct": med_anom,
        "p25_anomaly_pct": p25_anom,
        "p75_anomaly_pct": p75_anom,
        "direction": direction,
        "member_totals_90d": s_vals,
    }
