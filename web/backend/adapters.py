"""
Adapters & Result Assembler — Orbital Agronomist (v5)
Wraps the untouched root-level Streamlit prototype modules (`globe_component/uk_land.py`,
`weather.py`, `seasonal.py`, `indicators.py`, `crop_rules.py`, `agents.py`, `events.py`)
into clean Pydantic v2 responses (`ResultPayload`, `ValidateResponse`, plain-text dossier).
"""

from __future__ import annotations

import importlib.util
import sys
import types
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

# Ensure project root is importable without loading Streamlit anywhere
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

LONDON_TZ = ZoneInfo("Europe/London")
_OUTBOUND_LOG: list[dict[str, Any]] = []
_FEED_EVENTS: dict[str, list[dict[str, Any]]] = {}


def now_london_str(include_ms: bool = False) -> str:
    dt = datetime.now(LONDON_TZ)
    if include_ms:
        return dt.strftime("%H:%M:%S.") + f"{int(dt.microsecond / 1000):03d}"
    return dt.strftime("%H:%M:%S %Z")


def now_london_iso() -> str:
    return datetime.now(LONDON_TZ).isoformat(timespec="seconds")


def _pure_log_outbound_call(
    endpoint: str,
    grid_cell: str,
    run_id: str,
    status: str = "OK",
    latency_ms: float | None = None,
) -> dict[str, Any]:
    ts_str = now_london_str(include_ms=True)
    entry = {
        "ts": ts_str,
        "timestamp": ts_str,
        "phase": "analyse",
        "run_id": run_id,
        "endpoint": endpoint,
        "grid_cell": grid_cell,
        "status": status,
        "latency_ms": round(latency_ms, 1) if latency_ms is not None else 0,
    }
    _OUTBOUND_LOG.append(entry)
    return entry


def _pure_append_feed_event(
    run_id: str,
    source_or_type: str = "SOURCE",
    text: str = "",
    level: str = "info",
    *,
    event_type: str | None = None,
    source: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    actual_source = source or source_or_type
    ev = {
        "run_id": run_id,
        "ts": now_london_str(include_ms=True),
        "type": event_type or "SOURCE",
        "source": actual_source,
        "text": text,
        "payload": payload or {"level": level},
    }
    _FEED_EVENTS.setdefault(run_id, []).append(ev)
    return ev


# Register pure-Python events module so root modules never import streamlit
_events_mod = types.ModuleType("events")
_events_mod.now_london_str = now_london_str  # type: ignore[attr-defined]
_events_mod.now_london_iso = now_london_iso  # type: ignore[attr-defined]
_events_mod.log_outbound_call = _pure_log_outbound_call  # type: ignore[attr-defined]
_events_mod.append_feed_event = _pure_append_feed_event  # type: ignore[attr-defined]
sys.modules["events"] = _events_mod

# Load uk_land.py directly without executing globe_component/__init__.py (which imports streamlit)
_uk_land_spec = importlib.util.spec_from_file_location(
    "uk_land_standalone", ROOT_DIR / "globe_component" / "uk_land.py"
)
assert _uk_land_spec and _uk_land_spec.loader
_uk_land_mod = importlib.util.module_from_spec(_uk_land_spec)
_uk_land_spec.loader.exec_module(_uk_land_mod)
validate_uk_coordinate = _uk_land_mod.validate_uk_coordinate

from weather import (  # noqa: E402
    compute_10y_window_stats,
    fetch_10y_baseline,
    fetch_forecast_and_recent,
)
from seasonal import fetch_seasonal_ensemble  # noqa: E402
from indicators import compute_drought_indicators  # noqa: E402
from crop_rules import match_uk_crops  # noqa: E402
from agents import (  # noqa: E402
    FALLBACK_MODEL,
    PRIMARY_MODEL,
    build_deterministic_a1,
    build_deterministic_a2,
    build_deterministic_a3,
    run_sequential_agents,
)

from web.backend.api_models import (  # noqa: E402
    AgentDetailModel,
    BaselineYearBar,
    CropConstraintIcon,
    CropTileModel,
    DailySeriesPoint,
    GlyphKind,
    KpiItem,
    ProtectPipModel,
    Q1Payload,
    Q2Payload,
    Q3Payload,
    ResultPayload,
    RiskWord,
    SeasonalSummary,
    SoilLayerBar,
    SourceDiagnosticItem,
    ValidateResponse,
)

LONDON_TZ = ZoneInfo("Europe/London")


def _clamp_14_words(text: str) -> str:
    words = text.strip().split()
    if len(words) <= 14:
        return " ".join(words)
    return " ".join(words[:14]).rstrip(",;:") + "."


def validate_point(lat: float, lon: float) -> ValidateResponse:
    res = validate_uk_coordinate(lat, lon)
    is_valid = bool(res.get("valid", res.get("is_valid_uk_land", False)))
    nation = (res.get("unit") or res.get("admin_area")) if is_valid else None
    grid_cell = res.get("grid_cell", f"{abs(lat):.2f}°N, {abs(lon):.2f}°E")
    label = res.get("land_status", "UK Land" if is_valid else "Not UK land. No data requested.")
    context = res.get(
        "context",
        "~1–25 km model grid · Regional weather context" if is_valid else "Not UK land. No data requested.",
    )
    return ValidateResponse(
        valid=is_valid,
        nation=nation,
        grid_cell=grid_cell,
        status="UK_LAND" if is_valid else "OUTSIDE_UK",
        label=label,
        context=context,
        reason=None if is_valid else "Not UK land. No data requested.",
        lat=round(float(lat), 4),
        lon=round(float(lon), 4),
    )


def _source_glyph_and_prov(
    source_state: str,
    product_suffix: str,
    is_demo: bool = False,
    what_if: bool = False,
) -> tuple[GlyphKind, str]:
    if what_if:
        return "SIMULATED", "SIMULATED"
    if is_demo or source_state in ("CACHED", "DEMO FIXTURE"):
        return "CACHED", f"CACHED · {product_suffix}"
    if source_state == "UNAVAILABLE":
        return "FALLBACK", "UNAVAILABLE"
    return "LIVE", f"LIVE · {product_suffix}"


def _build_crop_tiles(
    crops_res: dict[str, Any],
    indicators: dict[str, Any],
    what_if: bool = False,
) -> list[CropTileModel]:
    ui_list = crops_res.get("candidates_ui", [])
    schema_list = crops_res.get("candidates_schema", [])
    sm_top = float(indicators.get("sm_0_7_now", 0.24))
    sm_deep = float(indicators.get("sm_28_100_now", 0.29))
    stemp = float(indicators.get("soil_temp_0_7_c", 9.8))

    tiles: list[CropTileModel] = []
    for idx, c_ui in enumerate(ui_list[:3]):
        c_sch = schema_list[idx] if idx < len(schema_list) else None
        raw_name = c_ui.get("name", "UK Crop")
        short_name = raw_name.split(" (")[0]
        win_full = c_ui.get("window", "Oct–Nov · Window OPEN")
        win_short = win_full.split(" · ")[0].strip()

        # Map window onto 0..6 (Oct..Apr)
        low_w = win_short.lower()
        if "feb" in low_w or "apr" in low_w or "spring" in low_w:
            s_idx, e_idx = 4, 6  # Feb..Apr
        elif "oct" in low_w and "nov" in low_w:
            s_idx, e_idx = 0, 1  # Oct..Nov
        elif "sep" in low_w and "oct" in low_w:
            s_idx, e_idx = 0, 0  # Oct
        else:
            s_idx, e_idx = 0, 1  # Oct..Nov

        conf_str = getattr(c_sch, "confidence", "MODERATE") if c_sch else "MODERATE"
        if conf_str == "MODERATE" and not what_if:
            dots = 3
            conf_word = "Good regional fit"
        elif conf_str == "CONDITIONAL" or (what_if and idx < 2):
            dots = 2
            conf_word = "Conditional · watch moisture"
        else:
            dots = 1
            conf_word = "Wait / monitor moisture"

        constraints = [
            CropConstraintIcon(
                kind="water",
                label="Topsoil moisture",
                tooltip=f"0–7 cm at {sm_top:.2f} m³/m³; 28–100 cm subsoil at {sm_deep:.2f} m³/m³. {c_ui.get('watch', '')}",
            ),
            CropConstraintIcon(
                kind="temp",
                label="Soil temperature",
                tooltip=f"Modelled 0–7 cm soil temperature is {stemp:.1f} °C ({win_full}).",
            ),
            CropConstraintIcon(
                kind="drainage",
                label="Ground verification",
                tooltip=c_ui.get("verify", "Verify field drainage, soil texture, and pH on ground."),
            ),
        ]

        tiles.append(
            CropTileModel(
                id=f"crop_{idx+1}",
                name=short_name,
                window_label=win_short,
                start_month_idx=s_idx,
                end_month_idx=e_idx,
                confidence_dots=dots,
                confidence_word=conf_word,
                why=c_ui.get("why", ""),
                watch=c_ui.get("watch", ""),
                verify=c_ui.get("verify", ""),
                constraints=constraints,
                glyph="SIMULATED" if what_if else "FALLBACK",
                provenance="SIMULATED" if what_if else "FALLBACK · HEURISTIC",
            )
        )
    return tiles


def build_q1_q2_q3_models(
    forecast_res: dict[str, Any],
    baseline_res: dict[str, Any],
    baseline_stats: dict[str, Any],
    seasonal_res: dict[str, Any],
    indicators: dict[str, Any],
    crops_res: dict[str, Any],
    selection: dict[str, Any],
    fetched_time: str,
    is_demo: bool = False,
    what_if: bool = False,
    baseline_indicators: dict[str, Any] | None = None,
) -> tuple[Q1Payload, Q2Payload, Q3Payload]:
    """
    Construct the structured Q1, Q2, and Q3 payloads for the 3-column Outlook view.
    """
    fc_state = forecast_res.get("source_state", "LIVE")
    base_state = baseline_res.get("source_state", "CACHED")
    seas_state = seasonal_res.get("source_state", "LIVE")
    grid_cell = indicators.get("grid_cell", selection.get("grid_cell", "52.20°N, 0.10°E"))
    admin = crops_res.get("admin", selection.get("admin_area", "England"))

    g_mod, p_mod = _source_glyph_and_prov(fc_state, "MODELLED", is_demo=is_demo, what_if=what_if)
    g_der, p_der = _source_glyph_and_prov(fc_state, "DERIVED", is_demo=is_demo, what_if=what_if)
    g_sea, p_sea = _source_glyph_and_prov(seas_state, "SEASONAL ENSEMBLE", is_demo=is_demo, what_if=what_if)

    # -------------------------------------------------------------------------
    # Q1: How dry is it now?
    # -------------------------------------------------------------------------
    chip_cur: RiskWord = indicators["chip_current"]
    r30 = float(indicators["rain_30d_mm"])
    m30 = float(indicators["mean_10y_30d_mm"])
    anom30 = int(indicators["rain_30d_anom_pct"])
    pet30 = float(indicators["p_minus_et0_30d_mm"])
    dry14 = int(indicators["dry_days_14d"])
    sm0 = float(indicators["sm_0_7_now"])
    sm7 = float(indicators["sm_7_28_now"])
    sm28 = float(indicators["sm_28_100_now"])
    rz_pct = int(indicators["root_zone_pct"])

    if what_if:
        q1_head = _clamp_14_words(
            f"Simulated 30 dry days: {chip_cur} dryness with {r30:.1f} mm rain ({anom30:+d}% vs mean)."
        )
    else:
        q1_head = _clamp_14_words(
            f"Current dryness is {chip_cur}: 30-day rain {r30:.1f} mm ({anom30:+d}% vs 10-year mean)."
        )

    base_q1_head = None
    if baseline_indicators is not None:
        base_q1_head = _clamp_14_words(
            f"Current dryness is {baseline_indicators['chip_current']}: 30-day rain {baseline_indicators['rain_30d_mm']:.1f} mm ({baseline_indicators['rain_30d_anom_pct']:+d}% vs 10-year mean)."
        )

    q1_kpis = [
        KpiItem(
            id="rain_anom_30d",
            label="30-day rain vs 10y mean",
            value=float(anom30),
            display_value=f"{anom30:+d}%",
            unit=f"({r30:.1f} vs {m30:.1f} mm)",
            glyph=g_der,
            provenance=p_der,
            source="Open-Meteo /v1/forecast + /v1/archive (2016–2025)",
            valid_time="Past 30 days",
            fetched_time=fetched_time,
            tooltip=f"{p_der} · 30d rainfall {r30:.1f} mm vs 2016–2025 calendar-window mean {m30:.1f} mm at grid {grid_cell}.",
        ),
        KpiItem(
            id="root_zone_sm",
            label="Root-zone soil moisture (7–28 cm)",
            value=sm7,
            display_value=f"{sm7:.2f}",
            unit=f"m³/m³ · {rz_pct}th pct",
            glyph=g_mod,
            provenance=p_mod,
            source="Open-Meteo /v1/forecast hourly soil_moisture_7_to_28cm",
            valid_time="Current day mean",
            fetched_time=fetched_time,
            tooltip=f"{p_mod} · Modelled volumetric soil moisture at 7–28 cm depth ({rz_pct}th percentile vs 10y window).",
        ),
        KpiItem(
            id="dry_days_14d",
            label="Dry days in last 14 days",
            value=float(dry14),
            display_value=f"{dry14}/14",
            unit=f"days <1 mm · P−ET₀ {pet30:+.1f} mm",
            glyph=g_der,
            provenance=p_der,
            source="Open-Meteo /v1/forecast daily precipitation_sum",
            valid_time="Last 14 days",
            fetched_time=fetched_time,
            tooltip=f"{p_der} · {dry14} of last 14 days had <1.0 mm rainfall; 30-day net P−ET₀ is {pet30:+.1f} mm.",
        ),
    ]

    # 10-year baseline bars (2016..2025 + Now)
    yearly_dict: dict[int, float] = baseline_stats.get("yearly_30d_rain", {})
    baseline_bars: list[BaselineYearBar] = []
    for yr in range(2016, 2026):
        val = float(yearly_dict.get(yr, m30))
        baseline_bars.append(BaselineYearBar(year=str(yr), rain_mm=round(val, 1), is_current=False))
    baseline_bars.append(BaselineYearBar(year="Now", rain_mm=round(r30, 1), is_current=True))

    base_sm0 = float(baseline_indicators["sm_0_7_now"]) if baseline_indicators else sm0
    base_sm7 = float(baseline_indicators["sm_7_28_now"]) if baseline_indicators else sm7
    base_sm28 = float(baseline_indicators["sm_28_100_now"]) if baseline_indicators else sm28

    soil_layers = [
        SoilLayerBar(
            depth_label="0–7 cm",
            moisture_m3m3=sm0,
            baseline_m3m3=base_sm0,
            glyph=g_mod,
            provenance=p_mod,
            tooltip=f"{p_mod} · Surface topsoil (0–7 cm): {sm0:.2f} m³/m³",
        ),
        SoilLayerBar(
            depth_label="7–28 cm",
            moisture_m3m3=sm7,
            baseline_m3m3=base_sm7,
            glyph=g_mod,
            provenance=p_mod,
            tooltip=f"{p_mod} · Root zone (7–28 cm): {sm7:.2f} m³/m³ ({rz_pct}th pct)",
        ),
        SoilLayerBar(
            depth_label="28–100 cm",
            moisture_m3m3=sm28,
            baseline_m3m3=base_sm28,
            glyph=g_mod,
            provenance=p_mod,
            tooltip=f"{p_mod} · Deep subsoil (28–100 cm): {sm28:.2f} m³/m³",
        ),
    ]

    past_dates = indicators.get("past_dates", [])
    past_rain = indicators.get("past_rain", [])
    past_et0 = indicators.get("past_et0", [])
    series_past30: list[DailySeriesPoint] = []
    cum_p = 0.0
    for d_str, r_v, e_v in zip(past_dates, past_rain, past_et0):
        cum_p = round(cum_p + (float(r_v) - float(e_v)), 2)
        series_past30.append(
            DailySeriesPoint(
                date=d_str,
                rain_mm=round(float(r_v), 2),
                et0_mm=round(float(e_v), 2),
                cum_net_mm=cum_p,
            )
        )

    q1 = Q1Payload(
        chip=chip_cur,
        glyph=g_der,
        provenance=p_der,
        tooltip=f"{p_der} · Rule: {chip_cur} based on 30d anomaly ({anom30:+d}%), 7–28 cm percentile ({rz_pct}th), and 14d dry days ({dry14}).",
        headline=q1_head,
        baseline_headline=base_q1_head,
        kpis=q1_kpis,
        baseline_years=baseline_bars,
        mean_30d_mm=m30,
        soil_layers=soil_layers,
        series_past30=series_past30,
    )

    # -------------------------------------------------------------------------
    # Q2: What is coming?
    # -------------------------------------------------------------------------
    chip_15d: RiskWord = indicators["chip_15d"]
    chip_13m: RiskWord = indicators["chip_13m"]
    r15 = float(indicators["rain_15d_mm"])
    e15 = float(indicators["et0_15d_mm"])
    pet15 = float(indicators["p_minus_et0_15d_mm"])
    sm_dir = str(indicators["sm_15d_dir"])
    s_avail = bool(indicators["seasonal_available"])
    s_stats = indicators.get("seasonal_stats", {})
    s_med = int(indicators.get("seasonal_med_anom_pct", 0))
    p25_a = int(s_stats.get("p25_anomaly_pct", -14))
    p75_a = int(s_stats.get("p75_anomaly_pct", 11))
    if what_if and s_avail:
        p25_a -= 10
        p75_a -= 10

    if s_avail:
        q2_head = _clamp_14_words(
            f"7–15 days {chip_15d} (net {pet15:+.1f} mm); 1–3 month ensemble is {chip_13m} ({s_med:+d}%)."
        )
    else:
        q2_head = _clamp_14_words(
            f"7–15 days {chip_15d} (net {pet15:+.1f} mm); 1–3 month outlook is INCONCLUSIVE."
        )

    fc_dates = indicators.get("fc_dates", [])
    fc_rain = indicators.get("fc_rain", [])
    fc_et0 = indicators.get("fc_et0", [])
    base_fc_rain = baseline_indicators.get("fc_rain", fc_rain) if baseline_indicators else fc_rain
    base_fc_et0 = baseline_indicators.get("fc_et0", fc_et0) if baseline_indicators else fc_et0

    net_series: list[DailySeriesPoint] = []
    cum_fc = 0.0
    cum_base_fc = 0.0
    for idx_d, (d_str, r_v, e_v) in enumerate(zip(fc_dates, fc_rain, fc_et0)):
        cum_fc = round(cum_fc + (float(r_v) - float(e_v)), 2)
        br = float(base_fc_rain[idx_d]) if idx_d < len(base_fc_rain) else float(r_v)
        be = float(base_fc_et0[idx_d]) if idx_d < len(base_fc_et0) else float(e_v)
        cum_base_fc = round(cum_base_fc + (br - be), 2)
        net_series.append(
            DailySeriesPoint(
                date=d_str,
                rain_mm=round(float(r_v), 2),
                et0_mm=round(float(e_v), 2),
                cum_net_mm=cum_fc,
                baseline_cum_net_mm=cum_base_fc,
            )
        )

    if not s_avail:
        seas_status = "Unavailable"
        seas_iqr = "Seasonal endpoint unavailable"
    elif p25_a < 0 < p75_a and abs(s_med) < 8:
        seas_status = "No clear signal"
        seas_iqr = f"IQR {p25_a:+d}% to {p75_a:+d}%"
    elif s_med < 0:
        seas_status = "Drier tilt"
        seas_iqr = f"IQR {p25_a:+d}% to {p75_a:+d}%"
    else:
        seas_status = "Wetter tilt"
        seas_iqr = f"IQR {p25_a:+d}% to {p75_a:+d}%"

    seasonal_summary = SeasonalSummary(
        available=s_avail,
        median_pct=s_med if s_avail else None,
        p25_pct=p25_a if s_avail else None,
        p75_pct=p75_a if s_avail else None,
        iqr_label=seas_iqr,
        status=seas_status,
        glyph=g_sea if s_avail else "FALLBACK",
        provenance=p_sea if s_avail else "UNAVAILABLE",
        tooltip=(
            f"{p_sea} · 50-member seasonal ensemble (low-to-moderate skill): median {s_med:+d}%, {seas_iqr}."
            if s_avail
            else "Seasonal ensemble endpoint unavailable; 1–3m horizon degraded to INCONCLUSIVE."
        ),
    )

    q2_kpis = [
        KpiItem(
            id="net_p_et0_15d",
            label="Next 15-day net P − ET₀",
            value=pet15,
            display_value=f"{pet15:+.1f}",
            unit=f"mm ({r15:.1f} rain vs {e15:.1f} ET₀)",
            glyph=g_der,
            provenance=p_der,
            source="Open-Meteo /v1/forecast (15-day horizon)",
            valid_time="Next 15 days",
            fetched_time=fetched_time,
            tooltip=f"{p_der} · Forecast 15-day rainfall {r15:.1f} mm minus FAO ET₀ {e15:.1f} mm = {pet15:+.1f} mm ({sm_dir}).",
        ),
        KpiItem(
            id="seasonal_anom_90d",
            label="1–3 month seasonal anomaly",
            value=float(s_med) if s_avail else None,
            display_value=f"{s_med:+d}%" if s_avail else "—",
            unit=f"{seas_iqr} · {seas_status}",
            glyph=seasonal_summary.glyph,
            provenance=seasonal_summary.provenance,
            source="Open-Meteo /v1/seasonal (50-member ensemble)",
            valid_time="Next 90 days (1–3 months)",
            fetched_time=fetched_time,
            tooltip=seasonal_summary.tooltip,
        ),
    ]

    q2 = Q2Payload(
        chip_7_15=chip_15d,
        glyph_7_15=g_der,
        tooltip_7_15=f"{p_der} · 7–15 day horizon is {chip_15d} (net P−ET₀ {pet15:+.1f} mm, root-zone trajectory {sm_dir.lower()}).",
        headline_7_15=f"7–15d: {chip_15d} ({pet15:+.1f} mm net)",
        chip_1_3m=chip_13m,
        glyph_1_3m=seasonal_summary.glyph,
        tooltip_1_3m=seasonal_summary.tooltip,
        headline_1_3m=f"1–3m: {chip_13m} ({s_med:+d}% median)" if s_avail else "1–3m: INCONCLUSIVE",
        headline=q2_head,
        kpis=q2_kpis,
        net_balance_series=net_series,
        daily_rain_et0=net_series,
        seasonal=seasonal_summary,
    )

    # -------------------------------------------------------------------------
    # Q3: What could grow?
    # -------------------------------------------------------------------------
    crop_tiles = _build_crop_tiles(crops_res, indicators, what_if=what_if)
    short_names = ", ".join(t.name for t in crop_tiles[:3])
    stemp = float(crops_res.get("soil_temp_0_7_c", 9.8))
    month_name = crops_res.get("month_name", "October")

    if what_if:
        q3_head = _clamp_14_words(
            f"Simulated dry stress in {admin}: prioritise deep-rooting or wait for topsoil recharge."
        )
    else:
        q3_head = _clamp_14_words(
            f"{month_name} in {admin} (soil {stemp:.1f} °C): {short_names}."
        )

    p_card = crops_res.get("protect_card")
    protect_pips = [
        ProtectPipModel(
            horizon="24–72 h",
            action=getattr(p_card, "action_24_72h", "Consolidate seedbeds lightly after drilling to conserve moisture."),
        ),
        ProtectPipModel(
            horizon="7 days",
            action=getattr(p_card, "action_7d", "Target drilling ahead of forecast rainfall events; avoid headland compaction."),
        ),
        ProtectPipModel(
            horizon="1–3 months",
            action=getattr(p_card, "action_1_3m", "Inspect field drains and winter water-capture capacity ahead of recharge."),
        ),
    ]

    q3_kpis = [
        KpiItem(
            id="soil_temp_0_7",
            label="Topsoil temperature (0–7 cm)",
            value=stemp,
            display_value=f"{stemp:.1f}",
            unit=f"°C · {admin} ({month_name})",
            glyph=g_mod,
            provenance=p_mod,
            source="Open-Meteo /v1/forecast hourly soil_temperature_0_to_7cm",
            valid_time="Current day mean",
            fetched_time=fetched_time,
            tooltip=f"{p_mod} · Modelled 0–7 cm soil temperature ({stemp:.1f} °C) used to filter UK autumn sowing windows.",
        ),
    ]

    q3 = Q3Payload(
        headline=q3_head,
        kpis=q3_kpis,
        crops=crop_tiles,
        protect_prepare=protect_pips,
        verification_checklist=[
            "Actual parcel land cover (arable, grassland, urban, woodland, peat, or water)",
            "In-situ topsoil moisture at 3–8 cm drilling depth and seedbed tilth",
            "Local soil texture, compaction / plough pans, pH, and field drainage class",
            "Rotation pest/disease history (e.g., black-grass, CSFB, clubroot, nematodes) and water abstraction licences",
        ],
        micro_line="Regional candidates. Verify soil and drainage.",
    )

    return q1, q2, q3


def assemble_result_payload(
    run_id: str,
    selection: dict[str, Any],
    forecast_res: dict[str, Any],
    baseline_res: dict[str, Any],
    baseline_stats: dict[str, Any],
    seasonal_res: dict[str, Any],
    indicators: dict[str, Any],
    crops_res: dict[str, Any],
    agents_res: dict[str, Any],
    feed_events: list[dict[str, Any]],
    is_demo: bool = False,
) -> ResultPayload:
    """
    Assemble the complete `ResultPayload` (including pre-computed `scenario` for 0-call
    instant client/server toggling).
    """
    fetched_time = now_london_str(include_ms=False)
    grid_cell = indicators.get("grid_cell", selection.get("grid_cell", "52.20°N, 0.10°E"))
    admin = crops_res.get("admin", selection.get("admin_area", "England"))

    q1, q2, q3 = build_q1_q2_q3_models(
        forecast_res=forecast_res,
        baseline_res=baseline_res,
        baseline_stats=baseline_stats,
        seasonal_res=seasonal_res,
        indicators=indicators,
        crops_res=crops_res,
        selection=selection,
        fetched_time=fetched_time,
        is_demo=is_demo,
        what_if=False,
    )

    # Pre-compute Scenario ("30 dry days": -35% rain, +15% ET0, -20% soil moisture) with 0 API calls
    scen_indicators = compute_drought_indicators(
        forecast_res=forecast_res,
        baseline_stats=baseline_stats,
        seasonal_res=seasonal_res,
        run_id=None,
        what_if=True,
        emit_events=False,
    )
    scen_crops = match_uk_crops(
        indicators=scen_indicators,
        selection=selection,
        run_id=run_id,
        emit_events=False,
    )
    s_q1, s_q2, s_q3 = build_q1_q2_q3_models(
        forecast_res=forecast_res,
        baseline_res=baseline_res,
        baseline_stats=baseline_stats,
        seasonal_res=seasonal_res,
        indicators=scen_indicators,
        crops_res=scen_crops,
        selection=selection,
        fetched_time=fetched_time,
        is_demo=is_demo,
        what_if=True,
        baseline_indicators=indicators,
    )

    # Agents mapping: A1 -> meteorologist, A2 -> hydrologist, A3 -> agronomist
    def _map_agent(
        key: str,
        role_slug: str,
        title: str,
        fallback_builder: Any,
    ) -> AgentDetailModel:
        a_dict = agents_res.get(key.lower()) or agents_res.get(key) or {}
        out_obj = a_dict.get("output") or fallback_builder()
        st_code = a_dict.get("status", "fallback")
        state_lit = "done" if st_code == "done" else "fallback"
        model_id = a_dict.get("model_used", PRIMARY_MODEL)
        prod_kind = a_dict.get("product_kind", "AI-GENERATED")

        if is_demo:
            glyph: GlyphKind = "CACHED"
            prov = f"CACHED · {prod_kind}"
            mode_str = "CACHED"
        elif state_lit == "fallback":
            glyph = "FALLBACK"
            prov = f"FALLBACK · {prod_kind}"
            mode_str = "FALLBACK"
        else:
            glyph = "AI-GENERATED"
            prov = "LIVE · AI-GENERATED"
            mode_str = "LIVE"

        narrative = getattr(out_obj, "public_narrative", "")
        takeaway = getattr(out_obj, "handoff_note", getattr(out_obj, "parcel_qualification", ""))
        extra_dump = out_obj.model_dump() if hasattr(out_obj, "model_dump") else {}

        return AgentDetailModel(
            agent=role_slug,  # type: ignore[arg-type]
            title=title,
            state=state_lit,  # type: ignore[arg-type]
            model=model_id,
            mode=mode_str,
            glyph=glyph,
            provenance=prov,
            text=narrative,
            takeaway=takeaway,
            extra=extra_dump,
        )

    a1_fallback = lambda: build_deterministic_a1(indicators, selection)
    a2_fallback = lambda: build_deterministic_a2(indicators, a1_fallback())
    a3_fallback = lambda: build_deterministic_a3(indicators, crops_res, selection, a2_fallback())

    agents_map = {
        "meteorologist": _map_agent("a1", "meteorologist", "Meteorologist (Weather & Soil Moisture)", a1_fallback),
        "hydrologist": _map_agent("a2", "hydrologist", "Hydrologist (Drought & Horizon Analyst)", a2_fallback),
        "agronomist": _map_agent("a3", "agronomist", "Agronomist (UK Crop & Planting Advisor)", a3_fallback),
    }

    # Sources diagnostics
    fc_st = forecast_res.get("source_state", "LIVE")
    base_st = baseline_res.get("source_state", "CACHED")
    seas_st = seasonal_res.get("source_state", "LIVE")
    seas_avail = bool(seasonal_res.get("available", True))

    sources_list = [
        SourceDiagnosticItem(
            id="forecast",
            name="Forecast",
            state="cached" if (is_demo or fc_st != "LIVE") else "done",
            glyph="CACHED" if (is_demo or fc_st != "LIVE") else "LIVE",
            provenance="CACHED · MODELLED" if (is_demo or fc_st != "LIVE") else "LIVE · MODELLED",
            latency_ms=int(forecast_res.get("latency_ms", 12)),
            valid_time="Past 30d + Next 15d daily",
            fetched_time=fetched_time,
            grid_cell=grid_cell,
            summary=f"30d rain {indicators['rain_30d_mm']:.1f} mm; 15d forecast {indicators['rain_15d_mm']:.1f} mm vs ET₀ {indicators['et0_15d_mm']:.1f} mm",
        ),
        SourceDiagnosticItem(
            id="soil",
            name="Soil layers",
            state="cached" if (is_demo or fc_st != "LIVE") else "done",
            glyph="CACHED" if (is_demo or fc_st != "LIVE") else "LIVE",
            provenance="CACHED · MODELLED" if (is_demo or fc_st != "LIVE") else "LIVE · MODELLED",
            latency_ms=int(forecast_res.get("latency_ms", 12)),
            valid_time="Hourly 3-depth profile (0–7, 7–28, 28–100 cm)",
            fetched_time=fetched_time,
            grid_cell=grid_cell,
            summary=f"0–7 cm {indicators['sm_0_7_now']:.2f}, 7–28 cm {indicators['sm_7_28_now']:.2f}, 28–100 cm {indicators['sm_28_100_now']:.2f} m³/m³",
        ),
        SourceDiagnosticItem(
            id="baseline",
            name="10-year baseline",
            state="cached" if (is_demo or base_st != "LIVE") else "done",
            glyph="CACHED" if (is_demo or base_st != "LIVE") else "LIVE",
            provenance="CACHED · MODELLED" if (is_demo or base_st != "LIVE") else "LIVE · MODELLED",
            latency_ms=int(baseline_res.get("latency_ms", 5)),
            valid_time="2016–2025 daily archive (3,653 days)",
            fetched_time=fetched_time,
            grid_cell=grid_cell,
            summary=f"10-year 30d window mean {indicators['mean_10y_30d_mm']:.1f} mm; 90d mean {baseline_stats.get('mean_90d_rain_mm', 165.0):.1f} mm",
        ),
        SourceDiagnosticItem(
            id="seasonal",
            name="Seasonal ensemble",
            state="failed" if not seas_avail else ("cached" if (is_demo or seas_st != "LIVE") else "done"),
            glyph="FALLBACK" if not seas_avail else ("CACHED" if (is_demo or seas_st != "LIVE") else "LIVE"),
            provenance="UNAVAILABLE" if not seas_avail else ("CACHED · SEASONAL ENSEMBLE" if (is_demo or seas_st != "LIVE") else "LIVE · SEASONAL ENSEMBLE"),
            latency_ms=int(seasonal_res.get("latency_ms", 18)),
            valid_time="Next 90 days (50-member ensemble)",
            fetched_time=fetched_time,
            grid_cell=grid_cell,
            summary=(
                f"50 members · median {indicators['seasonal_med_anom_pct']:+d}% vs 10y baseline"
                if seas_avail
                else "Seasonal endpoint unavailable -> 1–3m horizon marked INCONCLUSIVE"
            ),
        ),
    ]

    overall_state = "PARTIAL" if not seas_avail else "DONE"

    assumptions = [
        "Spatial resolution is ~1–25 km (Open-Meteo weather, land-surface soil model, and seasonal ensemble grids) — never parcel-scale.",
        "No satellite imagery or in-situ sensor data: NDVI, NDRE, canopy height, canopy temperature, field capacity, wilting point, true root-zone moisture, irrigated area, water assets, and yield are UNKNOWN unless entered by the user.",
        "Horizon chips (LOW, WATCH, ELEVATED, INCONCLUSIVE) are deterministic rule classifications over modelled precipitation, FAO ET₀, and volumetric soil moisture.",
        "1–3 month seasonal ensemble outlooks carry low-to-moderate skill at UK latitudes and must be read alongside their interquartile spread.",
        "Candidate UK crops come from a deterministic regional agronomy table filtered by UK nation, calendar month, modelled 0–7 cm soil temperature, and moisture regime; parcel land cover, soil texture, drainage, and pH must be verified on the ground.",
    ]

    location_dict = {
        "lat": round(float(selection.get("lat", 52.2053)), 4),
        "lon": round(float(selection.get("lon", 0.1218)), 4),
        "nation": admin,
        "grid_cell": grid_cell,
        "label": selection.get("land_status", f"UK Land ({admin})"),
        "timestamp_london": now_london_iso(),
    }

    return ResultPayload(
        run_id=run_id,
        state=overall_state,  # type: ignore[arg-type]
        is_demo=is_demo,
        scenario_active=False,
        location=location_dict,
        q1=q1,
        q2=q2,
        q3=q3,
        agents=agents_map,
        sources=sources_list,
        provenance={
            "primary_model": PRIMARY_MODEL,
            "fallback_model": FALLBACK_MODEL,
            "fetched_time_london": fetched_time,
            "is_demo": is_demo,
            "disclaimer": "Model data (about 1 to 25 km), not satellite or field measurement.",
        },
        assumptions=assumptions,
        feed=feed_events,
        scenario={
            "name": "30 dry days",
            "perturbation": "-35% rain, +15% ET₀, -20% soil moisture (0 external API calls)",
            "q1": s_q1.model_dump(),
            "q2": s_q2.model_dump(),
            "q3": s_q3.model_dump(),
        },
    )


def format_plain_text_dossier(result: ResultPayload, scenario_active: bool = False) -> str:
    """
    Generate the plain-text (.txt) agronomic dossier for export.
    """
    loc = result.location
    q1 = result.q1
    q2 = result.q2
    q3 = result.q3
    if scenario_active and result.scenario:
        q1 = Q1Payload.model_validate(result.scenario["q1"])
        q2 = Q2Payload.model_validate(result.scenario["q2"])
        q3 = Q3Payload.model_validate(result.scenario["q3"])

    mode_banner = (
        "SCENARIO SIMULATED (30 dry days: -35% rain, +15% ET0, -20% soil moisture)"
        if scenario_active
        else ("CACHED DEMO MODE" if result.is_demo else f"LIVE RUN ({result.state})")
    )

    lines = [
        "================================================================================",
        "ORBITAL AGRONOMIST — UK REGIONAL WATER-BALANCE & CROP OUTLOOK DOSSIER",
        "================================================================================",
        f"Run ID            : {result.run_id}",
        f"Run Mode          : {mode_banner}",
        f"Timestamp (London): {loc.get('timestamp_london', now_london_iso())}",
        f"Selected Point    : {loc.get('lat', 0.0):.4f} deg N, {loc.get('lon', 0.0):.4f} deg E ({loc.get('nation', 'UK')})",
        f"Model Grid Cell   : {loc.get('grid_cell', '')} (~1-25 km resolution)",
        "Disclaimer        : Model data (about 1 to 25 km), not satellite or field measurement.",
        "                    Decision-support prototype only; not certified agronomic advice.",
        "--------------------------------------------------------------------------------",
        "1. HORIZON SUMMARY",
        "--------------------------------------------------------------------------------",
        f"  * NOW (Current Dryness)       : {q1.chip} [{q1.provenance}]",
        f"  * 7-15 DAYS (Weather Forecast): {q2.chip_7_15} [{q2.glyph_7_15}]",
        f"  * 1-3 MONTHS (Seasonal Ens.)  : {q2.chip_1_3m} [{q2.seasonal.provenance}]",
        "",
        "--------------------------------------------------------------------------------",
        "2. Q1 — HOW DRY IS IT NOW?",
        "--------------------------------------------------------------------------------",
        f"Headline: {q1.headline}",
    ]
    for k in q1.kpis:
        lines.append(f"  - {k.label}: {k.display_value} {k.unit} [{k.provenance}]")
    lines.append("  Soil Moisture Profile (Modelled Volumetric m3/m3):")
    for sl in q1.soil_layers:
        lines.append(f"    * {sl.depth_label}: {sl.moisture_m3m3:.2f} m3/m3 [{sl.provenance}]")

    lines.extend([
        "",
        "--------------------------------------------------------------------------------",
        "3. Q2 — WHAT IS COMING?",
        "--------------------------------------------------------------------------------",
        f"Headline: {q2.headline}",
    ])
    for k in q2.kpis:
        lines.append(f"  - {k.label}: {k.display_value} {k.unit} [{k.provenance}]")
    lines.append(
        f"  - Seasonal Ensemble Status: {q2.seasonal.status} ({q2.seasonal.iqr_label}) [{q2.seasonal.provenance}]"
    )

    lines.extend([
        "",
        "--------------------------------------------------------------------------------",
        "4. Q3 — WHAT COULD GROW? (WEATHER-BASED REGIONAL CANDIDATES)",
        "--------------------------------------------------------------------------------",
        f"Headline: {q3.headline}",
        f"Note    : {q3.micro_line}",
    ])
    for idx, c in enumerate(q3.crops, start=1):
        lines.append(f"  ({idx}) {c.name} [{c.provenance}]")
        lines.append(f"      Window     : {c.window_label} ({c.confidence_word}, {c.confidence_dots}/3 dots)")
        lines.append(f"      Climate Fit: {c.why}")
        lines.append(f"      Watch-out  : {c.watch}")
        lines.append(f"      Verify     : {c.verify}")

    lines.append("")
    lines.append("  Protect & Prepare (Existing Crops & Grassland):")
    for p in q3.protect_prepare:
        lines.append(f"    * [{p.horizon}] {p.action}")

    lines.extend([
        "",
        "--------------------------------------------------------------------------------",
        "5. SEQUENTIAL AGENT ASSESSMENTS (GEMINI 3 STREAMED PIPELINE)",
        "--------------------------------------------------------------------------------",
    ])
    for role_key in ("meteorologist", "hydrologist", "agronomist"):
        ag = result.agents.get(role_key)
        if ag:
            lines.append(f"  [{ag.title}] — Model: {ag.model} | Provenance: {ag.provenance}")
            lines.append(f"  Narrative: {ag.text}")
            lines.append(f"  {ag.takeaway}")
            lines.append("")

    lines.extend([
        "--------------------------------------------------------------------------------",
        "6. DATA SOURCES & ASSUMPTIONS",
        "--------------------------------------------------------------------------------",
    ])
    for src in result.sources:
        lines.append(
            f"  * {src.name}: {src.provenance} ({src.latency_ms} ms, grid {src.grid_cell}) — {src.summary}"
        )
    lines.append("")
    lines.append("  Unknown / Unmeasured Without Ground Input:")
    lines.append(
        "  * Canopy height, NDVI, NDRE, canopy temperature, true root-zone moisture, field capacity,"
    )
    lines.append(
        "    wilting point, irrigated area, water assets, and yield are UNKNOWN unless user-entered."
    )
    lines.append("================================================================================")
    return "\n".join(lines) + "\n"
