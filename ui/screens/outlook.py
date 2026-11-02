"""
Screen 3: OUTLOOK (Three-Question Decision Screen) — Orbital Agronomist (v2)
Implements Section 3, 4, 5, 6 & 8 requirements:
- Top band (52px): location, mono coords, London time, data-mode badge, model IDs,
  'What-if: 30 days unusually dry' toggle, Export dossier, Replay analysis, Choose another location.
- Scenario banner (36px, violet border) when What-if is active (or when previewing 'scenario active').
- Three equal question panels (Q1, Q2, Q3) with horizon chips, 'How is this calculated?' popover,
  deterministic template answer lines, KPI tiles with provenance badges, compact Plotly visuals (170px)
  / Crop cards + Protect and prepare card, 4-line max Agent insights with expanders, and footers.
- Below the fold (collapsed by default): Open full charts and agent trail (5 tabs + full notes),
  Data and sources, About the data, and Diagnostics drawer.
- Persistent bottom strip (28px) with the mandatory honesty statement.
- Dynamically recomputes indicators and crop candidates when 'What-if: 30 days unusually dry' is toggled
  (zero new network or Gemini calls).
"""

from __future__ import annotations

import html
from typing import Any

import plotly.graph_objects as go
import streamlit as st

from crop_rules import match_uk_crops
from events import now_london_str
from indicators import compute_drought_indicators
from ui.components import (
    clean_html,
    crop_icon_svg,
    kpi_tile_html,
    provenance_badge_html,
    render_diagnostics_drawer,
    risk_chip_html,
)
from ui.state import return_to_pick


def _build_q1_compact_figure(
    what_if: bool = False,
    past_dates: list[str] | None = None,
    past_rain: list[float] | None = None,
    past_et0: list[float] | None = None,
) -> go.Figure:
    """Build the 170px Q1 compact visual: 30-day daily rain bars + ET0 line."""
    if past_dates and past_rain and past_et0:
        days = [d[-5:] for d in past_dates]
        rain = past_rain
        et0 = past_et0
    else:
        days = [f"Oct {d}" for d in range(2, 32)]
        base_rain = [
            0.0, 2.4, 0.8, 0.0, 0.0, 4.2, 6.1, 1.2, 0.0, 0.0,
            3.5, 0.0, 0.4, 5.8, 2.1, 0.0, 0.0, 0.0, 4.9, 3.2,
            0.0, 0.2, 0.0, 3.8, 0.0, 0.0, 1.8, 0.8, 0.0, 0.0,
        ]
        base_et0 = [
            1.6, 1.5, 1.5, 1.6, 1.4, 1.2, 1.1, 1.3, 1.4, 1.5,
            1.3, 1.4, 1.3, 1.1, 1.2, 1.4, 1.4, 1.3, 1.1, 1.1,
            1.3, 1.2, 1.3, 1.1, 1.2, 1.2, 1.1, 1.1, 1.2, 1.1,
        ]
        rain = [round(r * (0.65 if what_if else 1.0), 1) for r in base_rain]
        et0 = [round(e * (1.15 if what_if else 1.0), 2) for e in base_et0]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=days,
            y=rain,
            name="Rain (mm)",
            marker_color="#38BDF8" if not what_if else "#A78BFA",
            opacity=0.85,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=days,
            y=et0,
            name="ET₀ (mm)",
            mode="lines",
            line=dict(color="#F59E0B", width=2),
        )
    )
    fig.update_layout(
        height=165,
        margin=dict(l=28, r=10, t=22, b=22),
        paper_bgcolor="rgba(11,17,30,0.6)",
        plot_bgcolor="rgba(11,17,30,0.0)",
        font=dict(family="Segoe UI, Inter, sans-serif", size=10, color="#9AA8BC"),
        title=dict(
            text="30-Day Daily Rain (bars) vs FAO ET₀ (line) · mm/day",
            font=dict(size=10.5, color="#E2E8F0"),
            x=0.02,
            y=0.94,
        ),
        legend=dict(orientation="h", x=0.58, y=1.14, font=dict(size=9.5)),
        xaxis=dict(showgrid=False, tick0=0, dtick=7, tickfont=dict(size=9)),
        yaxis=dict(showgrid=True, gridcolor="rgba(148,163,184,0.12)", tickfont=dict(size=9)),
    )
    return fig


def _build_q2_compact_figure(
    what_if: bool = False,
    partial: bool = False,
    fc_rain: list[float] | None = None,
    fc_et0: list[float] | None = None,
    seasonal_note: str | None = None,
) -> go.Figure:
    """Build the 170px Q2 compact visual: 15-day cumulative rain vs cumulative ET0 + 1-3m summary band."""
    if fc_rain and fc_et0:
        days = [f"+{d}d" for d in range(1, len(fc_rain) + 1)]
        cum_r, cum_e = [], []
        sr, se = 0.0, 0.0
        for r, e in zip(fc_rain, fc_et0):
            sr += r
            se += e
            cum_r.append(round(sr, 1))
            cum_e.append(round(se, 1))
    else:
        days = [f"+{d}d" for d in range(1, 16)]
        daily_r = [1.2, 0.0, 2.4, 3.1, 0.4, 0.0, 0.0, 1.8, 2.9, 0.0, 1.5, 0.0, 2.1, 1.8, 1.2]
        daily_e = [1.1, 1.0, 0.9, 0.9, 1.0, 1.0, 1.0, 0.9, 0.8, 0.9, 0.9, 1.0, 0.9, 0.9, 0.9]
        mult_r = 0.65 if what_if else 1.0
        mult_e = 1.15 if what_if else 1.0
        cum_r, cum_e = [], []
        sr, se = 0.0, 0.0
        for r, e in zip(daily_r, daily_e):
            sr += r * mult_r
            se += e * mult_e
            cum_r.append(round(sr, 1))
            cum_e.append(round(se, 1))

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=days,
            y=cum_r,
            name="Cum. Rain (mm)",
            mode="lines+markers",
            marker=dict(size=4),
            line=dict(color="#22D3EE" if not what_if else "#A78BFA", width=2.2),
            fill="tozeroy",
            fillcolor="rgba(34,211,238,0.10)" if not what_if else "rgba(167,139,250,0.12)",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=days,
            y=cum_e,
            name="Cum. ET₀ (mm)",
            mode="lines",
            line=dict(color="#F59E0B", width=2, dash="dot"),
        )
    )
    band_note = (
        "1–3m: INCONCLUSIVE"
        if partial
        else (seasonal_note or ("1–3m: -14% (What-if)" if what_if else "1–3m: -4% med (IQR -18..+11%)"))
    )
    fig.add_annotation(
        x=max(0, len(days) - 2),
        y=max(cum_r[-1] if cum_r else 10.0, cum_e[-1] if cum_e else 10.0) * 0.88,
        text=band_note,
        showarrow=False,
        font=dict(size=9.5, color="#F8FAFC", family="Consolas, monospace"),
        bgcolor="rgba(18,26,43,0.9)",
        bordercolor="rgba(148,163,184,0.3)",
        borderpad=3,
    )
    fig.update_layout(
        height=165,
        margin=dict(l=28, r=10, t=22, b=22),
        paper_bgcolor="rgba(11,17,30,0.6)",
        plot_bgcolor="rgba(11,17,30,0.0)",
        font=dict(family="Segoe UI, Inter, sans-serif", size=10, color="#9AA8BC"),
        title=dict(
            text="Next 15-Day Cumulative Rain vs ET₀ (mm) + 1–3m Band",
            font=dict(size=10.5, color="#E2E8F0"),
            x=0.02,
            y=0.94,
        ),
        legend=dict(orientation="h", x=0.52, y=1.14, font=dict(size=9.5)),
        xaxis=dict(showgrid=False, tickfont=dict(size=9)),
        yaxis=dict(showgrid=True, gridcolor="rgba(148,163,184,0.12)", tickfont=dict(size=9)),
    )
    return fig


def _generate_dossier_text(
    sel: dict[str, Any],
    run_id: str,
    s3_state: str,
    what_if: bool,
    ind: dict[str, Any] | None = None,
    crops_res: dict[str, Any] | None = None,
    agents_res: dict[str, Any] | None = None,
) -> str:
    """Generate the plain-text .txt agronomic dossier with live values, provenance & honesty disclaimer."""
    lat = float(sel.get("lat", 52.2053))
    lon = float(sel.get("lon", 0.1218))
    grid = (ind or {}).get("grid_cell") or sel.get("grid_cell", "52.20°N, 0.10°E")
    admin = (crops_res or {}).get("admin") or sel.get("admin_area", "England")
    primary_m = st.session_state.get("primary_model_id", "gemini-3-flash-preview")
    fallback_m = st.session_state.get("fallback_model_id", "gemini-3.1-flash-lite-preview")

    if ind and crops_res:
        q1_chip = ind["chip_current"]
        q1_ans = ind["q1_answer_line"]
        r30_str = f"{ind['rain_30d_mm']:.1f} mm ({ind['rain_30d_anom_pct']:+d}% vs 10y mean {ind['mean_10y_30d_mm']:.1f} mm)"
        pet30_str = f"{ind['p_minus_et0_30d_mm']:+.1f} mm (ET0 {ind['et0_30d_mm']:.1f} mm)"
        dry14_str = f"{ind['dry_days_14d']} / 14 days < 1 mm (longest spell {ind['longest_dry_14d']}d)"
        sm_str = f"0-7cm={ind['sm_0_7_now']:.2f}, 7-28cm={ind['sm_7_28_now']:.2f} ({ind['root_zone_pct']}th pct), 28-100cm={ind['sm_28_100_now']:.2f} m3/m3"

        q2_chips = f"7-15d · {ind['chip_15d']} | 1-3m · {ind['chip_13m']}"
        q2_ans = ind["q2_answer_line"]
        r15_str = f"{ind['rain_15d_mm']:.1f} mm rain vs {ind['et0_15d_mm']:.1f} mm ET0 (net {ind['p_minus_et0_15d_mm']:+.1f} mm)"
        smdir_str = f"{ind['sm_15d_dir']} (projected 7-28cm {ind['sm_7_28_end']:.2f} m3/m3)"
        s_stats = ind.get("seasonal_stats", {})
        seas_str = (
            f"{ind['seasonal_med_anom_pct']:+d}% median anomaly (IQR {s_stats.get('p25_anomaly_pct', -15):+d}% to {s_stats.get('p75_anomaly_pct', 10):+d}%)"
            if ind["seasonal_available"]
            else "INCONCLUSIVE (endpoint unavailable)"
        )

        c_lines = []
        for idx, c in enumerate(crops_res["candidates_ui"], start=1):
            c_lines.append(
                f"  {idx}) {c['name']} — {c['tag']} ({c['window']})\n"
                f"     Why: {c['why']}\n"
                f"     Watch-out: {c['watch']}\n"
                f"     {c['verify']}"
            )
        crops_block = "\n".join(c_lines)
        prot_block = "\n".join(f"  - {b}" for b in crops_res.get("protect_bullets", []))
    else:
        q1_chip = "ELEVATED" if what_if else "WATCH"
        q1_ans = f"Topsoil and root-zone moisture near {grid} are {'markedly' if what_if else 'moderately'} below the 2016-2025 baseline."
        r30_str = "26.8 mm (-53% vs 10y baseline)" if what_if else "41.2 mm (-28% vs 10y baseline 57.4 mm)"
        pet30_str = "-17.6 mm deficit" if what_if else "+2.6 mm net balance"
        dry14_str = "12 days < 1 mm" if what_if else "9 days < 1 mm"
        sm_str = "0-7cm=0.19, 7-28cm=0.21, 28-100cm=0.23 m3/m3" if what_if else "0-7cm=0.24, 7-28cm=0.26, 28-100cm=0.29 m3/m3"
        q2_chips = f"7-15d · {'ELEVATED' if what_if else 'WATCH'} | 1-3m · {'INCONCLUSIVE' if s3_state == 'partial data' else ('ELEVATED' if what_if else 'WATCH')}"
        q2_ans = "15-day forecast and 1-3m seasonal ensemble summary."
        r15_str = "12.0 mm rain vs 16.2 mm ET0 (-4.2 mm)" if what_if else "18.4 mm rain vs 14.1 mm ET0 (+4.3 mm)"
        smdir_str = "Drying" if what_if else "Steady / Gradual recovery"
        seas_str = "INCONCLUSIVE" if s3_state == "partial data" else "Near-normal to slightly drier (-4% median, IQR -18% to +11%)"
        crops_block = (
            "  1) Winter Wheat (Triticum aestivum) — Good fit now (Window: Sep-Nov)\n"
            "  2) Winter Field Beans (Vicia faba) — Possible with watch-outs (Window: Oct-Nov)\n"
            "  3) Overwintered Rye + Vetch Cover Crop — Good fit now (Window: Aug-Nov)"
        )
        prot_block = (
            "  - Consolidate loose seedbeds lightly after drilling to conserve capillary moisture.\n"
            "  - Avoid high-axle-load passes on headlands where sub-surface compaction restricts root depth."
        )

    a1_txt = agents_res["a1"]["output"].public_narrative if agents_res and agents_res.get("a1") else "Agent 1 summary included above."
    a2_txt = agents_res["a2"]["output"].public_narrative if agents_res and agents_res.get("a2") else "Agent 2 summary included above."
    a3_txt = agents_res["a3"]["output"].public_narrative if agents_res and agents_res.get("a3") else "Agent 3 summary included above."

    return f"""================================================================================
ORBITAL AGRONOMIST — UK DROUGHT & CROP OUTLOOK DOSSIER
================================================================================
Run ID         : {run_id}
Generated (UK) : {now_london_str()} (Europe/London)
Coordinates    : {lat:.4f} N, {lon:.4f} E
Model Grid Cell: {grid}
UK Region      : {sel.get('land_status', f'UK land · {admin}')}
Scenario Mode  : {'WHAT-IF STRESS TEST (-35% rain, +15% ET0, -20% soil moisture) [SIMULATED]' if what_if else 'LIVE / STANDARD MODEL DATA [MODELLED]'}
Screen 3 State : {s3_state}
Primary Model  : {primary_m}
Fallback Model : {fallback_m}

--------------------------------------------------------------------------------
1. Q1 — HOW DRY IS IT NOW?
--------------------------------------------------------------------------------
Horizon Chip   : Current · {q1_chip}
Summary        : {q1_ans}
- 30-day Rainfall       : {r30_str} [MODELLED]
- 30-day P - ET0        : {pet30_str} [DERIVED]
- Dry Days (last 14d)   : {dry14_str} [DERIVED]
- Soil Moisture (3 dep) : {sm_str} [MODELLED]
- Agent 1 Narrative     : {a1_txt}

--------------------------------------------------------------------------------
2. Q2 — WHAT DO THE NEXT 7-15 DAYS AND 1-3 MONTHS SUGGEST?
--------------------------------------------------------------------------------
Horizon Chips  : {q2_chips}
Summary        : {q2_ans}
- Next 15d Rain / ET0   : {r15_str} [MODELLED]
- 15d Soil Trajectory   : {smdir_str} [DERIVED]
- 1-3m Seasonal Signal  : {seas_str} [SEASONAL ENSEMBLE]
- Agent 2 Narrative     : {a2_txt}

--------------------------------------------------------------------------------
3. Q3 — WHICH CROPS ARE PLAUSIBLE, AND WHEN SHOULD PLANTING BE CONSIDERED?
--------------------------------------------------------------------------------
Header Tag     : WEATHER-BASED REGIONAL CANDIDATES · VERIFY SOIL & PARCEL
Candidates     :
{crops_block}

Protect & Prepare (Existing Crops / Grassland):
{prot_block}

- Agent 3 Narrative     : {a3_txt}

--------------------------------------------------------------------------------
MANDATORY HONESTY & PROVENANCE STATEMENT
--------------------------------------------------------------------------------
Weather and soil-water model output (Open-Meteo, ~1-25 km grid). Not satellite
imagery or in-situ sensor data. Canopy height, NDVI, NDRE, canopy temperature,
true root-zone moisture, field capacity, wilting point, irrigated area, water
assets and yield are unknown unless user-entered. Crop suggestions are regional
weather candidates, not parcel-level agronomic advice.
================================================================================
"""


def render_outlook_screen() -> None:
    """Render Screen 3 (OUTLOOK: Top band, optional Scenario banner, 3 equal Question panels, Drawers, Bottom strip)."""
    sel = st.session_state.get("confirmed_selection") or st.session_state.get("pending_selection") or {
        "lat": 52.2053,
        "lon": 0.1218,
        "grid_cell": "52.20°N, 0.10°E",
        "admin_area": "England",
        "land_status": "UK land · England",
        "geographic_context": "East / South-East England · Great Britain",
    }
    run_id = st.session_state.get("run_id") or "run_demo01"
    s3_state = st.session_state.get("dev_screen3_state", "complete")

    what_if_effective = bool(st.session_state.get("what_if_active")) or (s3_state == "scenario active")
    is_offline = (s3_state == "offline") or (st.session_state.get("data_mode") == "OFFLINE-CACHE")
    is_partial = s3_state == "partial data"
    is_unavail_area = s3_state == "unavailable panel area"

    # Retrieve live bundle if available and recompute indicators/crops for What-If toggle (0 new API calls!)
    bundle = st.session_state.get("active_run_bundle")
    live_ind: dict[str, Any] | None = None
    live_crops: dict[str, Any] | None = None
    agents_res: dict[str, Any] | None = None

    if bundle and bundle.get("forecast_res") and not is_partial and not is_unavail_area:
        live_ind = compute_drought_indicators(
            bundle["forecast_res"],
            bundle["baseline_stats"],
            bundle["seasonal_res"],
            run_id=run_id,
            what_if=what_if_effective,
            emit_events=False,
        )
        live_crops = match_uk_crops(
            live_ind,
            sel,
            run_id=run_id,
            emit_events=False,
        )
        agents_res = bundle.get("agents_res")

    lat = float(sel.get("lat", 52.2053))
    lon = float(sel.get("lon", 0.1218))
    grid = (live_ind or {}).get("grid_cell") or sel.get("grid_cell", "52.20°N, 0.10°E")
    admin = (live_crops or {}).get("admin") or sel.get("admin_area", "England")
    src_badge_state = "CACHED" if is_offline else (live_ind.get("source_state", "LIVE") if live_ind else "LIVE")
    prod_modifier = "SIMULATED" if what_if_effective else "MODELLED"

    # 1. Top Band (52px): Location + What-if toggle + Export dossier + Replay analysis + Choose another location
    tb1, tb2, tb3, tb4, tb5 = st.columns([3.8, 2.2, 1.3, 1.3, 1.4], gap="small")
    with tb1:
        st.markdown(
            clean_html(f"""
            <div style="background:rgba(18,26,43,0.9);border:1px solid rgba(148,163,184,0.18);border-radius:10px;padding:7px 12px;">
              <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
                <span style="font-size:14px;font-weight:700;color:#F8FAFC;">
                  {html.escape(sel.get("land_status", f"UK land · {admin}"))}
                </span>
                <span style="font-family:var(--font-mono);font-size:11.5px;color:#22D3EE;">
                  {lat:.4f}°N, {lon:.4f}°E · grid {html.escape(grid)}
                </span>
              </div>
              <div style="font-size:11px;color:#9AA8BC;margin-top:1px;">
                {html.escape(sel.get("geographic_context", "United Kingdom"))} · run <span style="font-family:var(--font-mono);">{html.escape(run_id)}</span>
              </div>
            </div>
            """),
            unsafe_allow_html=True,
        )

    with tb2:
        toggled = st.toggle(
            "What-if: 30 days unusually dry",
            value=what_if_effective,
            key="s3_whatif_toggle",
            help="Single fixed stress perturbation: -35% rain, +15% ET₀, -20% modelled soil moisture across all depths.",
        )
        if toggled != st.session_state.get("what_if_active"):
            st.session_state.what_if_active = toggled
            if not toggled and st.session_state.get("dev_screen3_state") == "scenario active":
                st.session_state.dev_screen3_state = "complete"
            st.rerun()

    with tb3:
        dossier_txt = _generate_dossier_text(sel, run_id, s3_state, what_if_effective, live_ind, live_crops, agents_res)
        st.download_button(
            "⬇ Export dossier",
            data=dossier_txt,
            file_name=f"orbital_agronomist_{run_id}.txt",
            mime="text/plain",
            key="s3_export_btn",
            use_container_width=True,
        )

    with tb4:
        if st.button("▶ Replay analysis", key="s3_replay_btn", use_container_width=True):
            st.session_state.replay_feed_open = not st.session_state.get("replay_feed_open", False)
            st.rerun()

    with tb5:
        if st.button("← Choose another location", key="s3_back_pick_btn", use_container_width=True):
            hist = st.session_state.get("results_history", [])
            if not any(h.get("run_id") == run_id for h in hist):
                hist.insert(0, bundle or {"run_id": run_id, "selection": sel})
                st.session_state.results_history = hist[:3]
            return_to_pick()
            st.rerun()

    # Optional Replay Analysis drawer (opens saved Screen 2 feed without re-calling APIs)
    if st.session_state.get("replay_feed_open"):
        with st.expander("Saved Screen 2 Analysis Feed (Replayed from memory · 0 new API calls)", expanded=True):
            if bundle and bundle.get("feed_tuples"):
                lines = ""
                for ts, tag, msg, _ in bundle["feed_tuples"]:
                    lines += (
                        f'<div class="oa-feed-line"><span class="oa-feed-ts">[{html.escape(ts)}]</span> '
                        f'<span class="oa-feed-tag">[{html.escape(tag)}]</span> {html.escape(msg)}</div>'
                    )
                st.markdown(clean_html(f'<div class="oa-live-feed" style="height:140px;">{lines}</div>'), unsafe_allow_html=True)
            else:
                st.markdown(
                    clean_html(f"""
                    <div class="oa-live-feed" style="height:140px;">
                      <div class="oa-feed-line"><span class="oa-feed-ts">[14:02:11.340]</span> <span class="oa-feed-tag">[RUN {html.escape(run_id[:8])}]</span> Confirmed UK point {lat:.4f}, {lon:.4f} (grid {html.escape(grid)})</div>
                      <div class="oa-feed-line"><span class="oa-feed-ts">[14:02:11.410]</span> <span class="oa-feed-tag">[OPEN-METEO]</span> Forecast + 10y baseline + seasonal ensemble loaded from memory (0 new calls)</div>
                      <div class="oa-feed-line"><span class="oa-feed-ts">[14:02:12.310]</span> <span class="oa-feed-tag">[INDICATORS]</span> 30d rain = 41.2 mm (-28% vs 10y baseline); soil 7-28cm = 0.26 m³/m³ (32nd pct)</div>
                      <div class="oa-feed-line"><span class="oa-feed-ts">[14:02:14.980]</span> <span class="oa-feed-tag">[AGENTS A1→A2→A3]</span> All 3 agent outputs restored from session state.</div>
                    </div>
                    """),
                    unsafe_allow_html=True,
                )

    # 2. Scenario Banner (36px, appears only when What-if is active)
    if what_if_effective:
        sb_col1, sb_col2 = st.columns([8.2, 1.8], gap="small")
        with sb_col1:
            st.markdown(
                clean_html("""
                <div class="oa-scenario-banner" role="status">
                  <span>◆ SCENARIO ACTIVE · Illustrative stress test (-35% rain, +15% ET₀, -20% modelled soil moisture)</span>
                  <span style="font-family:var(--font-mono);font-size:11px;color:#DDD6FE;">Provenance: SIMULATED</span>
                </div>
                """),
                unsafe_allow_html=True,
            )
        with sb_col2:
            if st.button("Reset to live data", key="s3_reset_whatif_btn", use_container_width=True):
                st.session_state.what_if_active = False
                if st.session_state.get("dev_screen3_state") == "scenario active":
                    st.session_state.dev_screen3_state = "complete"
                st.rerun()

    # 3. Main Body: Three Equal Question Panels (4 columns each)
    q1_col, q2_col, q3_col = st.columns(3, gap="small")

    # -------------------------------------------------------------------------
    # PANEL 1 — Q1: How dry is it now?
    # -------------------------------------------------------------------------
    with q1_col:
        if live_ind:
            q1_risk = live_ind["chip_current"]
            q1_ans = live_ind["q1_answer_line"]
        else:
            q1_risk = "UNAVAILABLE" if is_unavail_area else ("ELEVATED" if what_if_effective else "WATCH")
            q1_ans = (
                "Current dryness metrics are temporarily unavailable for this grid cell."
                if is_unavail_area
                else (
                    f"Under the illustrative dry stress test (-35% rain, +15% ET₀), topsoil and root-zone moisture near {grid} drop to ELEVATED dryness (16th percentile vs 2016–2025)."
                    if what_if_effective
                    else f"Topsoil and root-zone moisture near {grid} are moderately below normal (32nd percentile vs 2016–2025) after a drier-than-average 30 days."
                )
            )
        q1_chip = risk_chip_html(q1_risk, prefix="Current")

        if is_unavail_area:
            q1_kpis_html = f"""
            <div style="padding:18px;border-radius:8px;background:rgba(244,63,94,0.08);border:1px dashed rgba(244,63,94,0.35);color:#FDA4AF;font-size:12.5px;margin:8px 0;">
              <b>Panel data unavailable</b> · Soil-moisture and 30-day rainfall records could not be retrieved for grid {html.escape(grid)}.
              <div style="margin-top:6px;">{provenance_badge_html("UNAVAILABLE", "MODELLED")}</div>
            </div>
            """
        elif live_ind:
            t1 = kpi_tile_html(
                "30-day rainfall",
                f"{live_ind['rain_30d_mm']:.1f}",
                "mm",
                f"{live_ind['rain_30d_anom_pct']:+d}% vs 10y baseline ({live_ind['mean_10y_30d_mm']:.1f} mm)",
                src_badge_state,
                prod_modifier,
            )
            t2 = kpi_tile_html(
                "30-day P − ET₀",
                f"{live_ind['p_minus_et0_30d_mm']:+.1f}",
                "mm",
                f"ET₀: {live_ind['et0_30d_mm']:.1f} mm ({'net deficit' if live_ind['p_minus_et0_30d_mm'] < 0 else 'net surplus'})",
                src_badge_state,
                "SIMULATED" if what_if_effective else "DERIVED",
            )
            t3 = kpi_tile_html(
                "Dry days (last 14d)",
                f"{live_ind['dry_days_14d']} / 14",
                "days < 1mm",
                f"Longest dry spell: {live_ind['longest_dry_14d']} days",
                src_badge_state,
                "SIMULATED" if what_if_effective else "DERIVED",
            )
            t4 = kpi_tile_html(
                "Modelled soil moisture (3 depths)",
                f"{live_ind['sm_0_7_now']:.2f} · {live_ind['sm_7_28_now']:.2f} · {live_ind['sm_28_100_now']:.2f}",
                "m³/m³",
                f"0–7 / 7–28 / 28–100 cm · {live_ind['root_zone_pct']}th pct vs 10y",
                src_badge_state,
                prod_modifier,
            )
            q1_kpis_html = f'<div class="oa-kpi-grid">{t1}{t2}{t3}{t4}</div>'
        else:
            t1 = kpi_tile_html(
                "30-day rainfall",
                "26.8" if what_if_effective else "41.2",
                "mm",
                "-53% vs 10y baseline (57.4 mm)" if what_if_effective else "-28% vs 10y baseline (57.4 mm)",
                src_badge_state,
                prod_modifier,
            )
            t2 = kpi_tile_html(
                "30-day P − ET₀",
                "-17.6" if what_if_effective else "+2.6",
                "mm",
                "Net water deficit (ET₀ 44.4 mm)" if what_if_effective else "Slight net surplus (ET₀ 38.6 mm)",
                src_badge_state,
                "SIMULATED" if what_if_effective else "DERIVED",
            )
            t3 = kpi_tile_html(
                "Dry days (last 14d)",
                "12 / 14" if what_if_effective else "9 / 14",
                "days < 1mm",
                "Longest dry spell: 8 days" if what_if_effective else "Longest dry spell: 5 days",
                src_badge_state,
                "SIMULATED" if what_if_effective else "DERIVED",
            )
            t4 = kpi_tile_html(
                "Modelled soil moisture (3 depths)",
                "0.19 · 0.21 · 0.23" if what_if_effective else "0.24 · 0.26 · 0.29",
                "m³/m³",
                "0–7 / 7–28 / 28–100 cm · 16th pct vs 10y" if what_if_effective else "0–7 / 7–28 / 28–100 cm · 32nd pct vs 10y",
                src_badge_state,
                prod_modifier,
            )
            q1_kpis_html = f'<div class="oa-kpi-grid">{t1}{t2}{t3}{t4}</div>'

        st.markdown(
            clean_html(f"""
            <div class="oa-q-panel">
              <div class="oa-q-panel-header">
                <div>
                  <div class="oa-eyebrow">QUESTION 1 · CURRENT DRYNESS</div>
                  <div class="oa-q-panel-title">How dry is it now?</div>
                </div>
                {q1_chip}
              </div>
              <div class="oa-answer-line">{html.escape(q1_ans)}</div>
              {q1_kpis_html}
            </div>
            """),
            unsafe_allow_html=True,
        )

        if not is_unavail_area:
            st.plotly_chart(
                _build_q1_compact_figure(
                    what_if=what_if_effective,
                    past_dates=live_ind.get("past_dates") if live_ind else None,
                    past_rain=live_ind.get("past_rain") if live_ind else None,
                    past_et0=live_ind.get("past_et0") if live_ind else None,
                ),
                use_container_width=True,
                config={"displayModeBar": False},
                key="q1_compact_chart",
            )

        a1_model = (
            agents_res["a1"]["model_used"]
            if agents_res and agents_res.get("a1")
            else st.session_state.get("primary_model_id", "gemini-3-flash-preview")
        )
        a1_text = (
            agents_res["a1"]["output"].public_narrative
            if agents_res and agents_res.get("a1")
            else (
                f"30-day rainfall ({'26.8' if what_if_effective else '41.2'} mm) sits below the 10-year Oct/Nov average (57.4 mm). "
                f"Modelled root-zone moisture (7–28 cm at {'0.21' if what_if_effective else '0.26'} m³/m³) indicates "
                f"{'a pronounced deficit requiring moisture conservation' if what_if_effective else 'manageable autumn dryness with intact subsoil moisture at 28–100 cm (0.29 m³/m³)'}."
            )
        )

        st.markdown(
            clean_html(f"""
            <div class="oa-agent-insight">
              <span style="color:#22D3EE;font-family:var(--font-mono);font-size:11px;font-weight:600;">
                Agent 1 ({html.escape(a1_model)}) ·
              </span>
              {html.escape(a1_text)}
            </div>
            <div class="oa-panel-footer">
              <span>Source: Open-Meteo Forecast + 10y Archive ({html.escape(src_badge_state)} · {html.escape(prod_modifier)})</span>
              <span>{html.escape(now_london_str())}</span>
            </div>
            """),
            unsafe_allow_html=True,
        )

    # -------------------------------------------------------------------------
    # PANEL 2 — Q2: What do the next 7 to 15 days and 1 to 3 months suggest?
    # -------------------------------------------------------------------------
    with q2_col:
        if live_ind:
            r_15d = live_ind["chip_15d"]
            r_13m = live_ind["chip_13m"]
            q2_ans = live_ind["q2_answer_line"]
            s_stats = live_ind.get("seasonal_stats", {})
            s_avail = live_ind["seasonal_available"]
            s_med = live_ind["seasonal_med_anom_pct"]
            k2_1 = kpi_tile_html(
                "Next 15-day rain & ET₀",
                f"{live_ind['rain_15d_mm']:.1f} vs {live_ind['et0_15d_mm']:.1f}",
                "mm",
                f"Net P − ET₀: {live_ind['p_minus_et0_15d_mm']:+.1f} mm",
                src_badge_state,
                prod_modifier,
            )
            k2_2 = kpi_tile_html(
                "15-day soil moisture direction",
                live_ind["sm_15d_dir"],
                "m³/m³",
                f"7–28 cm projected at {live_ind['sm_7_28_end']:.2f} m³/m³",
                src_badge_state,
                "SIMULATED" if what_if_effective else "DERIVED",
            )
            k2_3 = kpi_tile_html(
                f"1–3 month seasonal signal ({s_stats.get('member_count', 50)} members)",
                "INCONCLUSIVE" if not s_avail else f"{s_stats.get('direction', 'Near normal').title()} ({s_med:+d}%)",
                "" if not s_avail else "median anomaly",
                "Seasonal endpoint unavailable · degraded gracefully"
                if not s_avail
                else f"IQR spread: {s_stats.get('p25_anomaly_pct', -15):+d}% to {s_stats.get('p75_anomaly_pct', 10):+d}% · Low-to-moderate skill",
                "UNAVAILABLE" if not s_avail else live_ind.get("seasonal_source_state", src_badge_state),
                "SEASONAL ENSEMBLE",
            )
            seas_chart_note = (
                "1–3m: INCONCLUSIVE"
                if not s_avail
                else f"1–3m: {s_med:+d}% med (IQR {s_stats.get('p25_anomaly_pct', -15):+d}..{s_stats.get('p75_anomaly_pct', 10):+d}%)"
            )
        else:
            r_15d = "ELEVATED" if what_if_effective else "WATCH"
            r_13m = "INCONCLUSIVE" if is_partial else ("ELEVATED" if what_if_effective else "WATCH")
            q2_ans = (
                f"The 7–15 day forecast remains at {r_15d} ({'-4.2 mm net P−ET₀ drying' if what_if_effective else '+4.3 mm net P−ET₀ gradual recharge'}), "
                + (
                    "while the 1–3 month horizon is INCONCLUSIVE because the seasonal ensemble endpoint did not return data."
                    if is_partial
                    else f"while the 1–3 month seasonal ensemble indicates {r_13m} (-4% median anomaly, IQR -18% to +11%, low-to-moderate skill)."
                )
            )
            k2_1 = kpi_tile_html(
                "Next 15-day rain & ET₀",
                "12.0 vs 16.2" if what_if_effective else "18.4 vs 14.1",
                "mm",
                "Net P − ET₀: -4.2 mm (deficit)" if what_if_effective else "Net P − ET₀: +4.3 mm (modest recharge)",
                src_badge_state,
                prod_modifier,
            )
            k2_2 = kpi_tile_html(
                "15-day soil moisture direction",
                "Drying (-0.02)" if what_if_effective else "Steady / Recovering",
                "m³/m³",
                "7–28 cm projected at 0.19 m³/m³" if what_if_effective else "7–28 cm projected at 0.27 m³/m³",
                src_badge_state,
                "SIMULATED" if what_if_effective else "DERIVED",
            )
            k2_3 = kpi_tile_html(
                "1–3 month seasonal signal (50 members)",
                "INCONCLUSIVE" if is_partial else ("Drier (-14%)" if what_if_effective else "Near normal (-4%)"),
                "" if is_partial else "median anomaly",
                "Seasonal endpoint unavailable · degraded gracefully"
                if is_partial
                else "IQR spread: -18% to +11% · Low-to-moderate skill badge",
                "UNAVAILABLE" if is_partial else src_badge_state,
                "SEASONAL ENSEMBLE",
            )
            seas_chart_note = None

        chip_15d = risk_chip_html(r_15d, prefix="7–15d")
        chip_13m = risk_chip_html(r_13m, prefix="1–3m")

        st.markdown(
            clean_html(f"""
            <div class="oa-q-panel">
              <div class="oa-q-panel-header">
                <div>
                  <div class="oa-eyebrow">QUESTION 2 · 7–15D &amp; 1–3M OUTLOOK</div>
                  <div class="oa-q-panel-title">What do the next 7–15d &amp; 1–3m suggest?</div>
                </div>
                <div style="display:flex;gap:4px;flex-wrap:wrap;justify-content:flex-end;">
                  {chip_15d}
                  {chip_13m}
                </div>
              </div>
              <div class="oa-answer-line">{html.escape(q2_ans)}</div>
              <div class="oa-kpi-grid">
                {k2_1}
                {k2_2}
              </div>
              <div style="margin-bottom:4px;">{k2_3}</div>
            </div>
            """),
            unsafe_allow_html=True,
        )

        st.plotly_chart(
            _build_q2_compact_figure(
                what_if=what_if_effective,
                partial=is_partial or (live_ind is not None and not live_ind["seasonal_available"]),
                fc_rain=live_ind.get("fc_rain") if live_ind else None,
                fc_et0=live_ind.get("fc_et0") if live_ind else None,
                seasonal_note=seas_chart_note,
            ),
            use_container_width=True,
            config={"displayModeBar": False},
            key="q2_compact_chart",
        )

        with st.popover("How is this calculated? (Heuristic rules & thresholds)"):
            st.markdown(
                """
                **Deterministic Horizon Risk Heuristics (Section 3 & 6):**
                - **Current (`LOW | WATCH | ELEVATED`):**
                  - `ELEVATED`: 30d rain anomaly `< -35%` vs 10-yr window OR root-zone (`7–28 cm`) `< 20th` percentile.
                  - `WATCH`: 30d rain anomaly `-15% to -35%` OR root-zone `20th–35th` percentile OR `>= 9` dry days in last 14d.
                  - `LOW`: 30d rain within `±15%` of baseline and root-zone `> 35th` percentile.
                - **7–15 Day (`LOW | WATCH | ELEVATED`):**
                  - Combines Current state with 15-day forecast `P − ET₀` and projected `7–28 cm` soil-moisture delta.
                - **1–3 Month (`LOW | WATCH | ELEVATED | INCONCLUSIVE`):**
                  - Derived from 50-member Open-Meteo Seasonal ensemble median anomaly & IQR spread. Marked `INCONCLUSIVE` if seasonal data is unavailable or ensemble spread spans zero with wide IQR.
                """
            )

        a2_model_used = (
            agents_res["a2"]["model_used"]
            if agents_res and agents_res.get("a2")
            else (
                st.session_state.get("fallback_model_id", "gemini-3.1-flash-lite-preview")
                if is_partial
                else st.session_state.get("primary_model_id", "gemini-3-flash-preview")
            )
        )
        a2_text = (
            agents_res["a2"]["output"].public_narrative
            if agents_res and agents_res.get("a2")
            else (
                f"15-day synoptic rain ({'12.0' if what_if_effective else '18.4'} mm) "
                f"{'fails to offset evaporative demand' if what_if_effective else 'slightly exceeds autumn ET₀ (14.1 mm), stabilizing root-zone moisture'}. "
                + (
                    "Seasonal 1–3m ensemble was unreachable; treat medium-range outlook as INCONCLUSIVE."
                    if is_partial
                    else "Across the 50-member 1–3m ensemble, wide interquartile range (-18% to +11%) means low-to-moderate skill — plan for flexible water management."
                )
            )
        )
        st.markdown(
            clean_html(f"""
            <div class="oa-agent-insight">
              <span style="color:#22D3EE;font-family:var(--font-mono);font-size:11px;font-weight:600;">
                Agent 2 ({html.escape(a2_model_used)}) ·
              </span>
              {html.escape(a2_text)}
            </div>
            <div class="oa-panel-footer">
              <span>Source: Open-Meteo 15d + Seasonal Ensemble ({html.escape('UNAVAILABLE' if is_partial else src_badge_state)})</span>
              <span>Skill: Low-to-Moderate</span>
            </div>
            """),
            unsafe_allow_html=True,
        )

    # -------------------------------------------------------------------------
    # PANEL 3 — Q3: Which crops are plausible, and when should planting be considered?
    # -------------------------------------------------------------------------
    with q3_col:
        if live_crops:
            q3_ans = live_crops["q3_answer_line"]
            crops = live_crops["candidates_ui"]
            prot_bullets = live_crops["protect_bullets"]
        else:
            q3_ans = (
                f"For {admin} in late October / November (modelled 0–7 cm soil temp 9.8 °C), Winter Wheat, Winter Field Beans, and Overwintered Rye/Vetch Cover Crops are plausible regional weather candidates — planting window is "
                + ("WAIT FOR MOISTURE under the dry stress scenario." if what_if_effective else "OPEN NOW with seedbed moisture watch-outs.")
            )
            crops = [
                {
                    "name": "Winter Wheat (hardy cultivars)",
                    "icon": "grain",
                    "tag": "Wait / monitor" if what_if_effective else "Good fit now",
                    "tag_color": "#F59E0B" if what_if_effective else "#10B981",
                    "window": "Sep–Nov · Window OPEN (0–7 cm temp 9.8 °C >= 6 °C min)",
                    "why": "Low late-autumn ET₀ demand and vernalisation fit UK autumn drilling regimes.",
                    "watch": "Dry cloddy seedbeds reduce seed-to-soil contact and pre-emergence herbicide efficacy.",
                    "verify": "Verify on ground: seedbed moisture at 3–5 cm depth, slug pressure, field drainage & pH (6.0–7.5).",
                },
                {
                    "name": "Winter Field Beans (Vicia faba)",
                    "icon": "legume",
                    "tag": "Possible with watch-outs",
                    "tag_color": "#F59E0B",
                    "window": "Oct–Nov · Window OPEN (0–7 cm temp 9.8 °C >= 5 °C min)",
                    "why": "Deep taproot accesses 28–100 cm subsoil moisture (0.29 m³/m³) and fixes nitrogen.",
                    "watch": "Avoid compacted headlands; deep drilling (7–10 cm) into moisture is critical.",
                    "verify": "Verify on ground: absence of plough pan, P/K indices, 5+ year legume rotation gap.",
                },
                {
                    "name": "Overwintered Rye + Vetch Cover",
                    "icon": "forage",
                    "tag": "Good fit now",
                    "tag_color": "#10B981",
                    "window": "Aug–Nov · Window CLOSING SOON (establish before frosts)",
                    "why": "Rapid ground cover protects bare topsoil from winter rain splash and improves infiltration.",
                    "watch": "Requires timely spring termination so cover crop does not deplete spring seedbed moisture.",
                    "verify": "Verify on ground: surface residue clearance, machinery trafficability, spring rotation plan.",
                },
            ]
            prot_bullets = [
                "Consolidate loose seedbeds lightly after drilling to conserve capillary moisture.",
                "Avoid high-axle-load passes on headlands and check winter water-storage / ditch capture capacity.",
            ]

        crop_cards_html = ""
        for c in crops:
            svg = crop_icon_svg(c["icon"])
            crop_cards_html += f"""
            <div class="oa-crop-card">
              <div class="oa-crop-top">
                <span class="oa-crop-name">{svg} <span>{html.escape(c["name"])}</span></span>
                <span style="font-family:var(--font-mono);font-size:10.5px;font-weight:600;color:{c["tag_color"]};border:1px solid {c["tag_color"]}55;padding:1px 6px;border-radius:999px;">
                  {html.escape(c["tag"])}
                </span>
              </div>
              <div style="font-family:var(--font-mono);font-size:10.5px;color:#22D3EE;margin-bottom:2px;">
                {html.escape(c["window"])}
              </div>
              <div class="oa-crop-meta">
                <b>Why it fits:</b> {html.escape(c["why"])}<br/>
                <span style="color:#FBBF24;"><b>Watch-out:</b> {html.escape(c["watch"])}</span><br/>
                <span style="color:#9AA8BC;"><b>{html.escape(c["verify"])}</b></span>
              </div>
            </div>
            """

        prot_lines_html = "<br/>".join(f"• {html.escape(b)}" for b in prot_bullets)
        protect_html = f"""
        <div class="oa-protect-card">
          <div style="font-size:11px;font-weight:700;color:#38BDF8;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:2px;">
            🛡 Protect &amp; Prepare (Existing Crops &amp; Grassland)
          </div>
          <div style="font-size:11.5px;color:#E2E8F0;line-height:1.35;">
            {prot_lines_html}
          </div>
        </div>
        """

        a3_model = (
            agents_res["a3"]["model_used"]
            if agents_res and agents_res.get("a3")
            else st.session_state.get("primary_model_id", "gemini-3-flash-preview")
        )
        a3_text = (
            agents_res["a3"]["output"].public_narrative
            if agents_res and agents_res.get("a3")
            else (
                f"Regional candidates are filtered by UK autumn photoperiod and 0–7 cm soil temperature (9.8 °C). "
                f"Never assume parcel farmability: verify land cover, local soil texture, pH, slope, and drainage on the ground."
            )
        )

        st.markdown(
            clean_html(f"""
            <div class="oa-q-panel">
              <div class="oa-q-panel-header">
                <div>
                  <div class="oa-eyebrow">WEATHER-BASED REGIONAL CANDIDATES · VERIFY SOIL &amp; PARCEL</div>
                  <div class="oa-q-panel-title">Which crops &amp; planting window?</div>
                </div>
                {provenance_badge_html("LIVE", "HEURISTIC", "UK Crop & Planting Rule Table + Agent 3")}
              </div>
              <div class="oa-answer-line">{html.escape(q3_ans)}</div>
              {crop_cards_html}
              {protect_html}
              <div class="oa-agent-insight" style="margin-top:4px;">
                <span style="color:#22D3EE;font-family:var(--font-mono);font-size:11px;font-weight:600;">
                  Agent 3 ({html.escape(a3_model)}) ·
                </span>
                {html.escape(a3_text)}
              </div>
              <div class="oa-panel-footer">
                <span>Source: UK Agronomy Rule Table (HEURISTIC) + Agent 3 (AI-GENERATED)</span>
                <span>Verify parcel suitability</span>
              </div>
            </div>
            """),
            unsafe_allow_html=True,
        )

    # 4. Below the fold (collapsed by default): Open full charts and agent trail + Data & sources + Diagnostics
    st.markdown("<div style='margin-top:6px;'></div>", unsafe_allow_html=True)
    with st.expander("Open full charts and agent trail (4 interactive tabs + full Agent 1–3 notes)", expanded=False):
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "1 · 30d + 15d Water Balance",
            "2 · Soil Moisture (3 Depths)",
            "3 · 1–3m Seasonal Distribution",
            "4 · 10-Year Baseline Context",
            "5 · Full Agent Trail & Prompts",
        ])
        with tab1:
            st.plotly_chart(
                _build_q1_compact_figure(
                    what_if=what_if_effective,
                    past_dates=live_ind.get("past_dates") if live_ind else None,
                    past_rain=live_ind.get("past_rain") if live_ind else None,
                    past_et0=live_ind.get("past_et0") if live_ind else None,
                ),
                use_container_width=True,
                key="full_tab1_chart",
            )
        with tab2:
            sm_fig = go.Figure()
            if live_ind and live_ind.get("all_dates"):
                d_axis = [d[-5:] for d in live_ind["all_dates"]]
                y0 = live_ind["daily_sm0"]
                y7 = live_ind["daily_sm7"]
                y28 = live_ind["daily_sm28"]
            else:
                d_axis = [f"Day {i}" for i in range(-30, 15)]
                y0 = [0.24] * 45
                y7 = [0.26] * 45
                y28 = [0.29] * 45
            sm_fig.add_trace(go.Scatter(x=d_axis, y=y0, name="0–7 cm Topsoil", line=dict(color="#22D3EE", width=2)))
            sm_fig.add_trace(go.Scatter(x=d_axis, y=y7, name="7–28 cm Root-zone", line=dict(color="#10B981", width=2)))
            sm_fig.add_trace(go.Scatter(x=d_axis, y=y28, name="28–100 cm Deep", line=dict(color="#38BDF8", width=2)))
            sm_fig.update_layout(
                height=220,
                margin=dict(l=30, r=15, t=25, b=25),
                paper_bgcolor="#0B111E",
                plot_bgcolor="#0B111E",
                font=dict(color="#9AA8BC", size=11),
                title="Modelled Volumetric Soil Moisture Across 3 Depths (m³/m³)",
            )
            st.plotly_chart(sm_fig, use_container_width=True, key="full_tab2_chart")
        with tab3:
            st.plotly_chart(
                _build_q2_compact_figure(
                    what_if=what_if_effective,
                    partial=is_partial,
                    fc_rain=live_ind.get("fc_rain") if live_ind else None,
                    fc_et0=live_ind.get("fc_et0") if live_ind else None,
                ),
                use_container_width=True,
                key="full_tab3_chart",
            )
        with tab4:
            if live_ind and live_ind.get("yearly_30d_rain"):
                yr_dict = live_ind["yearly_30d_rain"]
                yrs = [str(y) for y in sorted(yr_dict.keys())]
                vals = [yr_dict[int(y)] for y in yrs]
                mean_line = live_ind["mean_10y_30d_mm"]
            else:
                yrs = [str(y) for y in range(2016, 2026)]
                vals = [52.1, 44.8, 61.3, 68.4, 71.2, 55.0, 48.9, 64.1, 59.8, 48.4]
                mean_line = 57.4
            b_fig = go.Figure(go.Bar(x=yrs, y=vals, marker_color="#38BDF8", name="30d Rain (mm)"))
            b_fig.add_hline(y=mean_line, line_dash="dash", line_color="#F59E0B", annotation_text=f"10y Mean ({mean_line:.1f} mm)")
            b_fig.update_layout(
                height=220,
                margin=dict(l=30, r=15, t=25, b=25),
                paper_bgcolor="#0B111E",
                plot_bgcolor="#0B111E",
                font=dict(color="#9AA8BC", size=11),
                title="10-Year Historical Baseline (2016–2025) for Same 30-Day Calendar Window",
            )
            st.plotly_chart(b_fig, use_container_width=True, key="full_tab4_chart")
        with tab5:
            st.markdown(
                f"""
                - **Agent 1 (`{a1_model}`)**: {a1_text}
                - **Agent 2 (`{a2_model_used}`)**: {a2_text}
                - **Agent 3 (`{a3_model}`)**: {a3_text}
                """
            )

    with st.expander("Data and sources & About the data (Attribution & Honesty Rules)", expanded=False):
        st.markdown(
            """
            - **Weather, Soil Moisture & Seasonal Ensemble**: [Open-Meteo.com](https://open-meteo.com/) (`forecast`, `archive` 2016–2025, and `seasonal` 50-member ensemble endpoints). Resolution ~1–25 km grid.
            - **UK Boundary Geometry**: Natural Earth 1:10m Admin-0 Map Units (England, Scotland, Wales, Northern Ireland) & 1:110m World land polygons (public domain).
            - **What we do NOT measure**: No satellite imagery (NDVI, NDRE, canopy temperature, canopy height) and no in-situ probe measurements are used. True field capacity, wilting point, drainage, pH, abstraction licences, and parcel land cover must be verified on the ground.
            """
        )

    render_diagnostics_drawer("outlook_diag")

    # 5. Persistent bottom strip (28px, Section 3)
    st.markdown(
        clean_html("""
        <div class="oa-bottom-strip" role="contentinfo">
          Weather and soil-water model output (Open-Meteo, ~1–25 km grid). Not satellite imagery or in-situ sensor data.
          Crop suggestions are regional weather candidates, not parcel-level agronomic advice.
        </div>
        """),
        unsafe_allow_html=True,
    )
