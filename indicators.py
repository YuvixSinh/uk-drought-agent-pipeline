"""
Deterministic Drought & Water-Balance Indicators (F4 & F6) — Orbital Agronomist (v2)
Computes:
- Q1 Current dryness KPIs (30d rain, anomaly vs 10y baseline, 30d P-ET0, dry days in last 14d,
  longest dry spell, 3-depth volumetric soil moisture 0-7 / 7-28 / 28-100 cm, 0-7cm soil temp,
  and root-zone percentile).
- Q2 7-15d & 1-3m horizon KPIs (15d rain, 15d ET0, 15d P-ET0, 15d soil-moisture trajectory,
  and 50-member seasonal ensemble summary).
- Explicit heuristic Horizon Chips (Current, 7-15d, 1-3m) with documented rules.
- Deterministic plain-English answer-line templates for Q1 and Q2.
- Supports the fixed What-If stress perturbation (-35% rain, +15% ET0, -20% soil moisture).
"""

from __future__ import annotations

from typing import Any

from events import append_feed_event


def compute_drought_indicators(
    forecast_res: dict[str, Any],
    baseline_stats: dict[str, Any],
    seasonal_res: dict[str, Any],
    run_id: str | None = None,
    what_if: bool = False,
    emit_events: bool = True,
) -> dict[str, Any]:
    """
    Compute all deterministic water-balance metrics, soil-moisture depth profiles,
    horizon risk chips, and deterministic answer lines.
    """
    payload = forecast_res.get("payload", {})
    daily = payload.get("daily", {})
    hourly = payload.get("hourly", {})

    d_times = daily.get("time", [])
    d_rain_raw = [float(x) if x is not None else 0.0 for x in daily.get("precipitation_sum", [])]
    d_et0_raw = [float(x) if x is not None else 1.1 for x in daily.get("et0_fao_evapotranspiration", [])]

    rain_mult = 0.65 if what_if else 1.0
    et0_mult = 1.15 if what_if else 1.0
    sm_mult = 0.80 if what_if else 1.0

    d_rain = [round(r * rain_mult, 2) for r in d_rain_raw]
    d_et0 = [round(e * et0_mult, 2) for e in d_et0_raw]

    # Split 30 past days and 15 forecast days
    n_past = min(30, len(d_times))
    past_dates = d_times[:n_past]
    past_rain = d_rain[:n_past]
    past_et0 = d_et0[:n_past]

    fc_dates = d_times[n_past : n_past + 15]
    fc_rain = d_rain[n_past : n_past + 15]
    fc_et0 = d_et0[n_past : n_past + 15]

    # 30-day totals & baseline comparison
    rain_30d = round(sum(past_rain), 1)
    et0_30d = round(sum(past_et0), 1)
    p_minus_et0_30d = round(rain_30d - et0_30d, 1)

    mean_10y_30d = max(10.0, float(baseline_stats.get("mean_30d_rain_mm", 58.0)))
    rain_30d_anom_pct = int(round(100.0 * (rain_30d - mean_10y_30d) / mean_10y_30d))

    # Dry days (< 1.0 mm) in last 14 days
    last_14_rain = past_rain[-14:] if len(past_rain) >= 14 else past_rain
    dry_days_14d = sum(1 for r in last_14_rain if r < 1.0)
    longest_dry_14d = 0
    cur_streak = 0
    for r in last_14_rain:
        if r < 1.0:
            cur_streak += 1
            longest_dry_14d = max(longest_dry_14d, cur_streak)
        else:
            cur_streak = 0

    # Hourly soil moisture & soil temperature (aggregate to daily means + current snapshot)
    h_sm0 = [float(x) * sm_mult if x is not None else None for x in hourly.get("soil_moisture_0_to_7cm", [])]
    h_sm7 = [float(x) * sm_mult if x is not None else None for x in hourly.get("soil_moisture_7_to_28cm", [])]
    h_sm28 = [float(x) * sm_mult if x is not None else None for x in hourly.get("soil_moisture_28_to_100cm", [])]
    h_st0_raw = [float(x) if x is not None else None for x in hourly.get("soil_temperature_0_to_7cm", [])]

    def _daily_means(h_vals: list[float | None], num_days: int) -> list[float]:
        out: list[float] = []
        for d_i in range(num_days):
            chunk = [v for v in h_vals[d_i * 24 : (d_i + 1) * 24] if v is not None]
            out.append(round(sum(chunk) / len(chunk), 3) if chunk else 0.25)
        return out

    total_days = len(d_times)
    daily_sm0 = _daily_means(h_sm0, total_days)
    daily_sm7 = _daily_means(h_sm7, total_days)
    daily_sm28 = _daily_means(h_sm28, total_days)
    daily_st0 = _daily_means(h_st0_raw, total_days)

    now_idx = max(0, n_past - 1)
    sm_0_7_now = round(daily_sm0[now_idx], 2) if daily_sm0 else 0.24
    sm_7_28_now = round(daily_sm7[now_idx], 2) if daily_sm7 else 0.26
    sm_28_100_now = round(daily_sm28[now_idx], 2) if daily_sm28 else 0.29
    soil_temp_0_7_c = round(daily_st0[now_idx], 1) if daily_st0 else 9.8

    layers_ok = sum(
        1
        for arr in (h_sm0[: n_past * 24], h_sm7[: n_past * 24], h_sm28[: n_past * 24])
        if any(v is not None for v in arr)
    )

    # Estimate root-zone (7-28 cm) percentile relative to 10-year 30d rainfall distribution & volumetric range
    rain_series_10y = sorted(baseline_stats.get("rain_30d_series", [45.0, 52.0, 58.0, 64.0, 72.0]))
    below_cnt = sum(1 for v in rain_series_10y if v <= rain_30d)
    rain_pct = int(round(100.0 * below_cnt / max(1, len(rain_series_10y))))
    sm_norm_pct = int(round(max(5.0, min(95.0, (sm_7_28_now - 0.12) / (0.38 - 0.12) * 100.0))))
    root_zone_pct = max(5, min(95, int(round(0.55 * sm_norm_pct + 0.45 * rain_pct))))

    # 15-day forecast metrics
    rain_15d = round(sum(fc_rain), 1)
    et0_15d = round(sum(fc_et0), 1)
    p_minus_et0_15d = round(rain_15d - et0_15d, 1)

    sm_7_28_end = round(daily_sm7[-1], 2) if len(daily_sm7) > now_idx else sm_7_28_now
    sm_15d_delta = round(sm_7_28_end - sm_7_28_now, 3)
    if sm_15d_delta >= 0.012 or p_minus_et0_15d >= 10.0:
        sm_15d_dir = "Recovering"
    elif sm_15d_delta <= -0.012 or p_minus_et0_15d <= -8.0:
        sm_15d_dir = "Drying"
    else:
        sm_15d_dir = "Steady / Gradual recovery" if p_minus_et0_15d >= 0 else "Steady / Slight drying"

    # -------------------------------------------------------------------------
    # Deterministic Horizon Chip Classification (Section 3 & 6)
    # -------------------------------------------------------------------------
    # 1) Current dryness chip
    if layers_ok == 0 and not d_times:
        chip_current = "UNAVAILABLE"
    elif rain_30d_anom_pct <= -35 or root_zone_pct < 20 or (dry_days_14d >= 12 and p_minus_et0_30d < -10.0):
        chip_current = "ELEVATED"
    elif rain_30d_anom_pct <= -15 or root_zone_pct <= 35 or dry_days_14d >= 9 or p_minus_et0_30d < 0.0:
        chip_current = "WATCH"
    else:
        chip_current = "LOW"

    # 2) 7-15 day chip
    if chip_current == "UNAVAILABLE":
        chip_15d = "UNAVAILABLE"
    elif (chip_current == "ELEVATED" and p_minus_et0_15d < 8.0) or p_minus_et0_15d <= -10.0 or sm_15d_dir == "Drying":
        chip_15d = "ELEVATED"
    elif chip_current in ("WATCH", "ELEVATED") or p_minus_et0_15d < 5.0 or sm_15d_delta < 0.005:
        chip_15d = "WATCH"
    else:
        chip_15d = "LOW"

    # 3) 1-3 month seasonal chip
    s_avail = bool(seasonal_res.get("available"))
    s_stats = seasonal_res.get("stats", {})
    s_med_anom = int(s_stats.get("median_anomaly_pct", 0))
    if what_if and s_avail:
        s_med_anom = s_med_anom - 12  # Reflect dry stress perturbation in scenario view

    if not s_avail:
        chip_13m = "INCONCLUSIVE"
    elif s_med_anom <= -15:
        chip_13m = "ELEVATED"
    elif s_med_anom <= -3 or (s_stats.get("p25_anomaly_pct", 0) <= -15):
        chip_13m = "WATCH"
    else:
        chip_13m = "LOW"

    # Deterministic plain-English answer lines (Section 3 & 6: generated from templates over structured values)
    grid_cell = forecast_res.get("grid_cell", "selected UK grid")
    if chip_current == "UNAVAILABLE":
        q1_answer_line = f"Current dryness metrics are unavailable for model grid {grid_cell}."
    else:
        anom_word = (
            f"{abs(rain_30d_anom_pct)}% below"
            if rain_30d_anom_pct < 0
            else f"{rain_30d_anom_pct}% above"
        )
        prefix_sim = "Under the illustrative What-If stress scenario (-35% rain, +15% ET₀), " if what_if else ""
        q1_answer_line = (
            f"{prefix_sim}Current dryness at grid {grid_cell} is {chip_current}: "
            f"30-day rainfall is {rain_30d:.1f} mm ({anom_word} the 2016–2025 baseline of {mean_10y_30d:.1f} mm) "
            f"with root-zone soil moisture (7–28 cm) at {sm_7_28_now:.2f} m³/m³ ({root_zone_pct}th percentile)."
        )

    if not s_avail:
        q2_answer_line = (
            f"The 7–15 day outlook is {chip_15d} (forecast net P−ET₀ {p_minus_et0_15d:+.1f} mm, soil moisture {sm_15d_dir.lower()}), "
            f"while the 1–3 month horizon is INCONCLUSIVE because the seasonal ensemble endpoint is unavailable."
        )
    else:
        q2_answer_line = (
            f"The 7–15 day outlook is {chip_15d} (forecast {rain_15d:.1f} mm rain vs {et0_15d:.1f} mm ET₀, net {p_minus_et0_15d:+.1f} mm), "
            f"and the 1–3 month seasonal ensemble ({s_stats.get('member_count', 50)} members) is {chip_13m} "
            f"with a {s_med_anom:+d}% median anomaly (IQR {s_stats.get('p25_anomaly_pct', -15):+d}% to {s_stats.get('p75_anomaly_pct', 10):+d}%, low-to-moderate skill)."
        )

    if emit_events and run_id:
        append_feed_event(
            run_id,
            "INDICATORS",
            f"30d rain = {rain_30d} mm ({rain_30d_anom_pct:+d}% vs 10y mean {mean_10y_30d} mm); P−ET₀ = {p_minus_et0_30d:+.1f} mm; SM 7–28cm = {sm_7_28_now:.2f} m³/m³ ({root_zone_pct}th pct)",
            "info",
        )
        append_feed_event(
            run_id,
            "HORIZONS",
            f"Current = {chip_current} · 7–15d = {chip_15d} · 1–3m = {chip_13m}",
            "warn" if "ELEVATED" in (chip_current, chip_15d, chip_13m) or "WATCH" in (chip_current, chip_15d, chip_13m) else "ok",
        )

    return {
        "what_if": what_if,
        "grid_cell": grid_cell,
        "source_state": forecast_res.get("source_state", "LIVE"),
        "seasonal_source_state": seasonal_res.get("source_state", "LIVE"),
        "layers_ok": layers_ok,
        # Q1 metrics
        "rain_30d_mm": rain_30d,
        "mean_10y_30d_mm": mean_10y_30d,
        "rain_30d_anom_pct": rain_30d_anom_pct,
        "et0_30d_mm": et0_30d,
        "p_minus_et0_30d_mm": p_minus_et0_30d,
        "dry_days_14d": dry_days_14d,
        "longest_dry_14d": longest_dry_14d,
        "sm_0_7_now": sm_0_7_now,
        "sm_7_28_now": sm_7_28_now,
        "sm_28_100_now": sm_28_100_now,
        "soil_temp_0_7_c": soil_temp_0_7_c,
        "root_zone_pct": root_zone_pct,
        # Q2 metrics
        "rain_15d_mm": rain_15d,
        "et0_15d_mm": et0_15d,
        "p_minus_et0_15d_mm": p_minus_et0_15d,
        "sm_7_28_end": sm_7_28_end,
        "sm_15d_delta": sm_15d_delta,
        "sm_15d_dir": sm_15d_dir,
        "seasonal_available": s_avail,
        "seasonal_stats": s_stats,
        "seasonal_med_anom_pct": s_med_anom,
        # Horizon chips
        "chip_current": chip_current,
        "chip_15d": chip_15d,
        "chip_13m": chip_13m,
        # Deterministic answer lines
        "q1_answer_line": q1_answer_line,
        "q2_answer_line": q2_answer_line,
        # Series for Plotly charts
        "past_dates": past_dates,
        "past_rain": past_rain,
        "past_et0": past_et0,
        "fc_dates": fc_dates,
        "fc_rain": fc_rain,
        "fc_et0": fc_et0,
        "all_dates": d_times,
        "daily_sm0": daily_sm0,
        "daily_sm7": daily_sm7,
        "daily_sm28": daily_sm28,
        "yearly_30d_rain": baseline_stats.get("yearly_30d_rain", {}),
    }
