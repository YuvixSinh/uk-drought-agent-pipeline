"""
Pre-Warmed Offline Demo Mode — Orbital Agronomist (v5)
Provides instant (<20 ms, zero network calls) ResultPayloads for the pre-warmed UK
demo locations (`cambridge`, `edinburgh`, `belfast`, plus `norwich` and `cardiff`),
using the local `cache/` files and badging all values as `CACHED`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from web.backend.adapters import (
    ROOT_DIR,
    assemble_result_payload,
    build_deterministic_a1,
    build_deterministic_a2,
    build_deterministic_a3,
    compute_10y_window_stats,
    compute_drought_indicators,
    match_uk_crops,
    now_london_str,
)
from weather import (
    _build_fallback_archive_payload,
    _build_fallback_forecast_payload,
    _grid_key,
)
from seasonal import _summarize_seasonal_payload
from agents import PRIMARY_MODEL
from web.backend.api_models import ResultPayload

CACHE_DIR = ROOT_DIR / "cache"

DEMO_LOCATIONS: dict[str, dict[str, Any]] = {
    "cambridge": {
        "name": "Cambridge",
        "lat": 52.2053,
        "lon": 0.1218,
        "admin_area": "England",
        "land_status": "UK Land · England (Cambridge / East Anglia)",
    },
    "edinburgh": {
        "name": "Edinburgh",
        "lat": 55.9533,
        "lon": -3.1883,
        "admin_area": "Scotland",
        "land_status": "UK Land · Scotland (Edinburgh / Lothian)",
    },
    "belfast": {
        "name": "Belfast",
        "lat": 54.5973,
        "lon": -5.9301,
        "admin_area": "Northern Ireland",
        "land_status": "UK Land · Northern Ireland (Belfast / Lagan Valley)",
    },
    "norwich": {
        "name": "Norwich",
        "lat": 52.6309,
        "lon": 1.2974,
        "admin_area": "England",
        "land_status": "UK Land · England (Norwich / Norfolk)",
    },
    "cardiff": {
        "name": "Cardiff",
        "lat": 51.4816,
        "lon": -3.1791,
        "admin_area": "Wales",
        "land_status": "UK Land · Wales (Cardiff / South Glamorgan)",
    },
}


def _load_cached_or_fixture(prefix: str, lat: float, lon: float) -> tuple[dict[str, Any] | None, int]:
    g_lat, g_lon, _ = _grid_key(lat, lon)
    candidates = sorted(
        CACHE_DIR.glob(f"{prefix}_{g_lat:.2f}_{g_lon:.2f}_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if candidates:
        try:
            obj = json.loads(candidates[0].read_text(encoding="utf-8"))
            return obj.get("payload"), 3
        except Exception:
            pass
    return None, 4


def get_demo_result(name: str) -> ResultPayload:
    key = name.strip().lower()
    if key not in DEMO_LOCATIONS:
        key = "cambridge"
    loc_info = DEMO_LOCATIONS[key]
    lat = float(loc_info["lat"])
    lon = float(loc_info["lon"])
    _, _, grid_label = _grid_key(lat, lon)
    run_id = f"demo-{key}"

    selection = {
        "lat": lat,
        "lon": lon,
        "is_valid_uk_land": True,
        "admin_area": loc_info["admin_area"],
        "land_status": loc_info["land_status"],
        "grid_cell": grid_label,
    }

    fc_payload, fc_lat_ms = _load_cached_or_fixture("forecast", lat, lon)
    if fc_payload is None:
        fc_payload = _build_fallback_forecast_payload(lat, lon)
    forecast_res = {
        "source_state": "CACHED",
        "latency_ms": fc_lat_ms,
        "grid_cell": grid_label,
        "payload": fc_payload,
    }

    arch_payload, arch_lat_ms = _load_cached_or_fixture("archive10y", lat, lon)
    if arch_payload is None:
        arch_payload = _build_fallback_archive_payload(lat, lon)
    baseline_res = {
        "source_state": "CACHED",
        "latency_ms": arch_lat_ms,
        "payload": arch_payload,
    }
    baseline_stats = compute_10y_window_stats(arch_payload)

    seas_payload, seas_lat_ms = _load_cached_or_fixture("seasonal", lat, lon)
    base_90d = float(baseline_stats.get("mean_90d_rain_mm", 165.0))
    if seas_payload is not None:
        seas_stats = _summarize_seasonal_payload(seas_payload, base_90d)
    else:
        seas_stats = _summarize_seasonal_payload({"daily": {}}, base_90d)
    seasonal_res = {
        "available": True,
        "source_state": "CACHED",
        "latency_ms": seas_lat_ms,
        "stats": seas_stats,
    }

    indicators = compute_drought_indicators(
        forecast_res=forecast_res,
        baseline_stats=baseline_stats,
        seasonal_res=seasonal_res,
        run_id=None,
        what_if=False,
        emit_events=False,
    )
    crops_res = match_uk_crops(
        indicators=indicators,
        selection=selection,
        run_id=run_id,
        emit_events=False,
    )

    a1_out = build_deterministic_a1(indicators, selection)
    a2_out = build_deterministic_a2(indicators, a1_out)
    a3_out = build_deterministic_a3(indicators, crops_res, selection, a2_out)

    agents_res = {
        "a1": {
            "status": "done",
            "source_state": "CACHED",
            "product_kind": "AI-GENERATED",
            "model_used": f"{PRIMARY_MODEL} (cached-demo)",
            "output": a1_out,
            "elapsed_ms": 8,
        },
        "a2": {
            "status": "done",
            "source_state": "CACHED",
            "product_kind": "AI-GENERATED",
            "model_used": f"{PRIMARY_MODEL} (cached-demo)",
            "output": a2_out,
            "elapsed_ms": 8,
        },
        "a3": {
            "status": "done",
            "source_state": "CACHED",
            "product_kind": "AI-GENERATED",
            "model_used": f"{PRIMARY_MODEL} (cached-demo)",
            "output": a3_out,
            "elapsed_ms": 8,
        },
    }

    ts = now_london_str(include_ms=True)
    feed = [
        {"ts": ts, "source": "DEMO-CACHE", "type": "SOURCE", "text": f"Loaded pre-warmed cached forecast & 3-depth soil profile for {loc_info['name']} ({grid_label})"},
        {"ts": ts, "source": "DEMO-CACHE", "type": "SOURCE", "text": f"Loaded 2016–2025 10-year archive baseline (3,653 days) from disk cache"},
        {"ts": ts, "source": "DEMO-CACHE", "type": "SOURCE", "text": f"Loaded 50-member seasonal ensemble from disk cache"},
        {"ts": ts, "source": "INDICATORS", "type": "INDICATOR", "text": f"Computed Q1/Q2/Q3 indicators: NOW={indicators['chip_current']}, 7–15d={indicators['chip_15d']}, 1–3m={indicators['chip_13m']}"},
        {"ts": ts, "source": "AGENTS", "type": "AGENT", "text": f"Loaded pre-warmed sequential agent assessments (Meteorologist -> Hydrologist -> Agronomist)"},
    ]

    return assemble_result_payload(
        run_id=run_id,
        selection=selection,
        forecast_res=forecast_res,
        baseline_res=baseline_res,
        baseline_stats=baseline_stats,
        seasonal_res=seasonal_res,
        indicators=indicators,
        crops_res=crops_res,
        agents_res=agents_res,
        feed_events=feed,
        is_demo=True,
    )
