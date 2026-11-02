"""
Screen 2: LIVE ANALYSIS (War Room + Live Feed) — Orbital Agronomist (v2)
Implements Section 2, 3, 4, 5 & 8 requirements:
- Context bar (56px): coordinates, grid cell, London time, mode badge, run ID,
  small SVG UK locator, and 'Cancel and go back' button.
- Progress rail (5 stages): 1 Coordinate confirmed · 2 Weather & soil moisture ·
  3 Drought indicators · 4 AI agents (A1 -> A2 -> A3) · 5 Outlook ready
- Source checklist (5 compact tiles): Open-Meteo recent & 15-day forecast,
  Open-Meteo 10-year daily baseline, Open-Meteo seasonal ensemble,
  Soil-moisture layer check (0–7, 7–28, 28–100 cm), Crop & planting rule table.
- War room (3 agent cards with animated connector A1 ──▶ A2 ──▶ A3).
- Live feed (220px tall, monospace, Europe/London timestamps, auto-scrolls to newest).
- Completion banner: “Analysis complete — opening Outlook in 4s…” with 'View outlook' and 'Stay here'.
- Runs the live pipeline inside a single Streamlit script run using `st.empty()` placeholders
  when `dev_screen2_state == "live_or_default"`, while keeping all Section 5 preview states
  reachable via the Diagnostics drawer.
"""

from __future__ import annotations

import html
import time
from typing import Any

import streamlit as st

from agents import run_sequential_agents
from crop_rules import match_uk_crops
from events import append_feed_event, get_feed_events, now_london_str
from indicators import compute_drought_indicators
from seasonal import fetch_seasonal_ensemble
from ui.components import (
    clean_html,
    provenance_badge_html,
    render_diagnostics_drawer,
    uk_locator_svg_html,
)
from ui.state import advance_to_outlook, cancel_active_analysis
from weather import compute_10y_window_stats, fetch_10y_baseline, fetch_forecast_and_recent


def _render_rail_html(rail: list[tuple[str, str, str]]) -> str:
    rail_cards_html = ""
    for title, st_code, elapsed in rail:
        dot_color = {
            "done": "#10B981",
            "running": "#22D3EE",
            "degraded": "#F59E0B",
            "failed": "#F43F5E",
            "queued": "#5B6B82",
        }.get(st_code, "#5B6B82")
        rail_cards_html += f"""
        <div class="oa-rail-step {html.escape(st_code)}">
          <div class="oa-rail-step-top">
            <span class="oa-rail-step-title">
              <span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:{dot_color};margin-right:5px;"></span>
              {html.escape(title)}
            </span>
            <span class="oa-rail-step-ms">{html.escape(elapsed)}</span>
          </div>
          <div style="font-family:var(--font-mono);font-size:10px;color:#9AA8BC;text-transform:uppercase;">
            state: {html.escape(st_code)}
          </div>
        </div>
        """
    return clean_html(f'<div class="oa-progress-rail">{rail_cards_html}</div>')


def _render_sources_html(sources: list[dict[str, str]]) -> str:
    src_tiles_html = ""
    for src in sources:
        badge = provenance_badge_html(src["state"], src["kind"], f"{src['name']} ({src['state']})")
        src_tiles_html += f"""
        <div class="oa-source-tile">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:4px;">
            <span class="oa-source-name">{html.escape(src["name"])}</span>
          </div>
          <div style="margin:2px 0;">{badge}</div>
          <div class="oa-source-meta">{html.escape(src["meta"])}</div>
        </div>
        """
    return clean_html(f'<div class="oa-source-grid">{src_tiles_html}</div>')


def _render_war_room_html(agents: list[dict[str, Any]]) -> str:
    def _agent_card_html(ag: dict[str, Any]) -> str:
        st_cls = ag["status"]
        card_cls = (
            "active"
            if st_cls in ("thinking", "streaming")
            else ("done" if st_cls == "done" else ("fallback" if st_cls == "fallback" else ""))
        )
        chips_html = "".join(f'<span class="oa-agent-chip">{html.escape(c)}</span>' for c in ag["inputs"])
        p_kind = ag.get("product_kind", "AI-GENERATED")
        return f"""
        <div class="oa-agent-card {card_cls}">
          <div class="oa-agent-header">
            <span class="oa-agent-title">{html.escape(ag["title"])}</span>
            <span class="oa-agent-status {html.escape(st_cls)}">{html.escape(st_cls)} · {html.escape(ag["elapsed"])}</span>
          </div>
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <span class="oa-agent-model">model: {html.escape(ag["model"])}</span>
            {provenance_badge_html("FALLBACK" if st_cls == "fallback" else "LIVE", p_kind, "Gemini structured agent stream")}
          </div>
          <div class="oa-agent-chips">{chips_html}</div>
          <div class="oa-agent-stream">{html.escape(ag["stream"])}</div>
          <div class="oa-agent-takeaway">{html.escape(ag["takeaway"])}</div>
        </div>
        """

    def _connector_html(active: bool) -> str:
        cls = "active" if active else ""
        return f"""
        <div class="oa-agent-connector" aria-hidden="true">
          <span class="oa-connector-badge">──▶</span>
          <div class="oa-connector-line {cls}"></div>
        </div>
        """

    a1, a2, a3 = agents
    return clean_html(
        f'<div class="oa-war-room">'
        f"{_agent_card_html(a1)}"
        f"{_connector_html(a1['status'] in ('done', 'fallback'))}"
        f"{_agent_card_html(a2)}"
        f"{_connector_html(a2['status'] in ('done', 'fallback'))}"
        f"{_agent_card_html(a3)}"
        f"</div>"
    )


def _render_feed_html(feed_tuples: list[tuple[str, str, str, str]]) -> str:
    feed_lines_html = ""
    for ts, tag, msg, level in feed_tuples[-18:]:
        msg_cls = f"oa-feed-msg-{level}" if level in ("ok", "warn", "err") else ""
        feed_lines_html += (
            f'<div class="oa-feed-line">'
            f'<span class="oa-feed-ts">[{html.escape(ts)}]</span> '
            f'<span class="oa-feed-tag">[{html.escape(tag)}]</span> '
            f'<span class="{msg_cls}">{html.escape(msg)}</span>'
            f"</div>"
        )
    return clean_html(
        f'<div class="oa-live-feed" role="log" aria-label="Real-time analysis event feed">{feed_lines_html}</div>'
    )


def _feed_tuples_from_events(run_id: str) -> list[tuple[str, str, str, str]]:
    evs = get_feed_events(run_id)
    out: list[tuple[str, str, str, str]] = []
    for e in evs:
        lvl = (e.get("payload") or {}).get("level", "info")
        out.append((e.get("ts", ""), e.get("source", "EVENT"), e.get("text", ""), lvl))
    return out


def _build_stage1_preview_payload(state_name: str, sel: dict[str, Any], run_id: str) -> dict[str, Any]:
    """Build deterministic static preview data for all Section 5 states of Screen 2."""
    lat = sel.get("lat", 52.2053)
    lon = sel.get("lon", 0.1218)
    grid = sel.get("grid_cell", "52.20°N, 0.10°E")
    admin = sel.get("admin_area", "England")
    primary_m = st.session_state.get("primary_model_id", "gemini-3-flash-preview")
    fallback_m = st.session_state.get("fallback_model_id", "gemini-3.1-flash-lite-preview")

    s = state_name if state_name != "live_or_default" else "complete with countdown"

    if s == "queued":
        rail = [
            ("1 Coordinate confirmed", "done", "12 ms"),
            ("2 Weather & soil moisture", "queued", "—"),
            ("3 Drought indicators", "queued", "—"),
            ("4 AI agents (A1 → A2 → A3)", "queued", "—"),
            ("5 Outlook ready", "queued", "—"),
        ]
    elif s == "fetching":
        rail = [
            ("1 Coordinate confirmed", "done", "12 ms"),
            ("2 Weather & soil moisture", "running", "410 ms…"),
            ("3 Drought indicators", "queued", "—"),
            ("4 AI agents (A1 → A2 → A3)", "queued", "—"),
            ("5 Outlook ready", "queued", "—"),
        ]
    elif s == "indicators done":
        rail = [
            ("1 Coordinate confirmed", "done", "12 ms"),
            ("2 Weather & soil moisture", "done", "840 ms"),
            ("3 Drought indicators", "done", "45 ms"),
            ("4 AI agents (A1 → A2 → A3)", "queued", "—"),
            ("5 Outlook ready", "queued", "—"),
        ]
    elif s == "agents running":
        rail = [
            ("1 Coordinate confirmed", "done", "12 ms"),
            ("2 Weather & soil moisture", "done", "840 ms"),
            ("3 Drought indicators", "done", "45 ms"),
            ("4 AI agents (A1 → A2 → A3)", "running", "1,420 ms…"),
            ("5 Outlook ready", "queued", "—"),
        ]
    elif s == "partial data":
        rail = [
            ("1 Coordinate confirmed", "done", "12 ms"),
            ("2 Weather & soil moisture", "degraded", "1,180 ms"),
            ("3 Drought indicators", "degraded", "52 ms"),
            ("4 AI agents (A1 → A2 → A3)", "done", "2,490 ms"),
            ("5 Outlook ready", "degraded", "3,734 ms"),
        ]
    elif s == "offline cached replay":
        rail = [
            ("1 Coordinate confirmed", "done", "8 ms"),
            ("2 Weather & soil moisture", "done", "18 ms (cache)"),
            ("3 Drought indicators", "done", "29 ms"),
            ("4 AI agents (A1 → A2 → A3)", "done", "14 ms (cache)"),
            ("5 Outlook ready", "done", "69 ms"),
        ]
    elif s == "cancelled":
        rail = [
            ("1 Coordinate confirmed", "done", "12 ms"),
            ("2 Weather & soil moisture", "done", "810 ms"),
            ("3 Drought indicators", "done", "44 ms"),
            ("4 AI agents (A1 → A2 → A3)", "failed", "cancelled"),
            ("5 Outlook ready", "queued", "—"),
        ]
    elif s == "error":
        rail = [
            ("1 Coordinate confirmed", "done", "12 ms"),
            ("2 Weather & soil moisture", "failed", "timeout"),
            ("3 Drought indicators", "failed", "blocked"),
            ("4 AI agents (A1 → A2 → A3)", "failed", "skipped"),
            ("5 Outlook ready", "failed", "error"),
        ]
    else:
        rail = [
            ("1 Coordinate confirmed", "done", "12 ms"),
            ("2 Weather & soil moisture", "done", "842 ms"),
            ("3 Drought indicators", "done", "48 ms"),
            ("4 AI agents (A1 → A2 → A3)", "done", "2,610 ms"),
            ("5 Outlook ready", "done", "3,512 ms"),
        ]

    src_state = "CACHED" if s == "offline cached replay" else ("UNAVAILABLE" if s == "error" else "LIVE")
    seasonal_state = "UNAVAILABLE" if s in ("partial data", "error") else src_state
    sources = [
        {
            "name": "Open-Meteo recent & 15-day forecast",
            "state": "UNAVAILABLE" if s == "error" else (src_state if s != "queued" else "QUEUED"),
            "kind": "MODELLED",
            "meta": "45d daily · 1,080h soil · 312 ms" if s not in ("queued", "error") else ("0 records · pending" if s == "queued" else "HTTP timeout · 0 records"),
        },
        {
            "name": "Open-Meteo 10-year daily baseline",
            "state": "UNAVAILABLE" if s == "error" else (src_state if s not in ("queued", "fetching") else "QUEUED"),
            "kind": "MODELLED",
            "meta": "3,653 days (2016–2025) · 480 ms" if s not in ("queued", "fetching", "error") else ("fetching…" if s == "fetching" else "0 records"),
        },
        {
            "name": "Open-Meteo seasonal ensemble",
            "state": seasonal_state if s not in ("queued", "fetching") else "QUEUED",
            "kind": "SEASONAL ENSEMBLE",
            "meta": (
                "UNAVAILABLE · 1–3m marked INCONCLUSIVE"
                if s == "partial data"
                else ("50 members · 183d · 390 ms" if s not in ("queued", "fetching", "error") else "pending")
            ),
        },
        {
            "name": "Soil-moisture layer check (0–7, 7–28, 28–100 cm)",
            "state": "UNAVAILABLE" if s == "error" else (src_state if s not in ("queued", "fetching") else "QUEUED"),
            "kind": "MODELLED",
            "meta": "3/3 non-null layers · 0.24 / 0.26 / 0.29 m³/m³" if s not in ("queued", "fetching", "error") else "awaiting forecast payload",
        },
        {
            "name": "Crop & planting rule table",
            "state": "LIVE",
            "kind": "HEURISTIC",
            "meta": f"12 UK agronomy windows loaded ({admin}, Oct/Nov)",
        },
    ]

    if s in ("queued", "fetching", "indicators done"):
        a1_st, a2_st, a3_st = "queued", "queued", "queued"
    elif s == "agents running":
        a1_st, a2_st, a3_st = "done", "streaming", "queued"
    elif s == "partial data":
        a1_st, a2_st, a3_st = "done", "fallback", "done"
    elif s == "cancelled":
        a1_st, a2_st, a3_st = "done", "failed", "queued"
    elif s == "error":
        a1_st, a2_st, a3_st = "failed", "failed", "failed"
    else:
        a1_st, a2_st, a3_st = "done", "done", "done"

    agents = [
        {
            "id": "A1",
            "title": "Agent 1 — Weather & Soil Moisture Analyst",
            "model": primary_m,
            "status": a1_st,
            "elapsed": "890 ms" if a1_st == "done" else ("—" if a1_st == "queued" else "failed"),
            "inputs": ["30d Rain", "30d ET₀", "SM 0–100cm", "10y Baseline"],
            "stream": (
                f"30-day rainfall near {grid} is 41.2 mm (-28% vs 2016–2025 baseline of 57.4 mm). "
                "30-day FAO ET₀ is 38.6 mm, yielding a slight P−ET₀ surplus of +2.6 mm, though the "
                "last 14 days recorded 9 dry days (<1 mm). Modelled topsoil (0–7 cm) sits at 0.24 m³/m³ "
                "and root-zone (7–28 cm) at 0.26 m³/m³ (32nd percentile vs 10-year Oct/Nov distribution)."
                if a1_st == "done"
                else ("Waiting for drought indicators to complete…" if a1_st == "queued" else "Agent 1 halted.")
            ),
            "takeaway": (
                "Takeaway: Mild autumn topsoil moisture deficit (32nd pct vs 10-yr baseline); all 3 soil layers verified."
                if a1_st == "done"
                else "Takeaway: Pending Agent 1 completion."
            ),
        },
        {
            "id": "A2",
            "title": "Agent 2 — Drought & Horizon Analyst",
            "model": fallback_m if a2_st == "fallback" else primary_m,
            "status": a2_st,
            "elapsed": "920 ms" if a2_st in ("done", "fallback") else ("540 ms…" if a2_st == "streaming" else "—"),
            "inputs": ["A1 Summary", "15d Forecast", "50-Member Ensemble"],
            "stream": (
                "Next 15 days project 18.4 mm rainfall against 14.1 mm ET₀ (P−ET₀ +4.3 mm), keeping "
                "the 7–15 day horizon at WATCH because topsoil recharge remains gradual. Across the "
                "1–3 month seasonal ensemble (50 members), median precipitation anomaly is -4% with "
                "IQR spanning -18% to +11% — wide ensemble spread warrants WATCH / low-to-moderate confidence."
                if a2_st in ("done", "streaming", "fallback")
                else ("Queued behind Agent 1…" if a2_st == "queued" else "Agent 2 halted.")
            ),
            "takeaway": (
                "Takeaway: 7–15d WATCH (modest recharge); 1–3m INCONCLUSIVE (seasonal endpoint unavailable)."
                if s == "partial data"
                else (
                    "Takeaway: 7–15d WATCH (gradual recharge); 1–3m WATCH (ensemble median -4%, wide IQR spread)."
                    if a2_st in ("done", "streaming", "fallback")
                    else "Takeaway: Pending Agent 2 completion."
                )
            ),
        },
        {
            "id": "A3",
            "title": "Agent 3 — UK Crop & Planting Advisor",
            "model": primary_m,
            "status": a3_st,
            "elapsed": "800 ms" if a3_st == "done" else "—",
            "inputs": ["A1 + A2 Context", "UK Crop Table", f"Region: {admin}"],
            "stream": (
                f"For {admin} in late October / November with topsoil temp at 9.8 °C and WATCH moisture "
                "status: Winter Wheat (late-sown hardy cultivars), Winter Field Beans, and Overwintered "
                "Rye/Vetch Cover Crops remain viable weather-based candidates. Verify local field trafficability, "
                "drainage status, and actual seedbed structure on the ground before drilling."
                if a3_st == "done"
                else "Queued behind Agent 2…"
            ),
            "takeaway": (
                "Takeaway: 3 autumn/winter candidates matched (Winter Wheat, Field Beans, Rye/Vetch Cover); verify parcel soil & trafficability."
                if a3_st == "done"
                else "Takeaway: Pending Agent 3 completion."
            ),
        },
    ]

    rid_short = run_id.replace("run_", "")[:4]
    feed = [
        ("14:02:11.340", f"RUN {rid_short}", f"Confirmed UK point {lat:.4f}, {lon:.4f} (grid {grid}, {admin})", "info"),
    ]
    if s != "queued":
        feed.append(
            ("14:02:11.410", "OPEN-METEO", "GET /v1/forecast (past_days=30, forecast_days=15, soil 3 depths) -> 200 OK in 312 ms", "ok" if s != "error" else "err")
        )
    if s not in ("queued", "fetching"):
        feed.append(
            ("14:02:11.890", "OPEN-METEO", "GET /v1/archive (10y daily baseline 2016-2025) -> 200 OK in 480 ms (cached on disk)", "ok")
        )
        if s == "partial data":
            feed.append(
                ("14:02:12.280", "OPEN-METEO", "GET /v1/seasonal (1-3m ensemble) -> 503 UNAVAILABLE (degrading 1-3m chip to INCONCLUSIVE)", "warn")
            )
        else:
            feed.append(
                ("14:02:12.280", "OPEN-METEO", "GET /v1/seasonal (1-3m ensemble) -> 200 OK in 390 ms (50 members, 183d)", "ok")
            )
        feed.append(
            ("14:02:12.310", "INDICATORS", "30d rain = 41.2 mm (-28% vs 10y mean 57.4 mm); P-ET0 = +2.6 mm; soil 7-28 cm = 0.26 m³/m³ (32nd pct)", "info")
        )
        feed.append(
            ("14:02:12.330", "HORIZONS", f"Current = WATCH · 7-15d = WATCH · 1-3m = {'INCONCLUSIVE' if s == 'partial data' else 'WATCH'}", "warn")
        )
    if s in ("agents running", "partial data", "offline cached replay", "cancelled", "complete with countdown"):
        feed.append(
            ("14:02:12.350", f"A1 {primary_m}", "Streaming current dryness analysis...", "ai")
        )
        feed.append(
            ("14:02:13.240", f"A1 {primary_m}", "Completed in 890 ms (schema validated: Agent1Output)", "ok")
        )
        if s == "partial data":
            feed.append(
                ("14:02:13.600", f"A2 {primary_m}", "Primary model deadline exceeded; switching to fallback model...", "warn")
            )
            feed.append(
                ("14:02:14.160", f"A2 {fallback_m}", "Fallback stream completed in 920 ms (schema validated: Agent2Output)", "ok")
            )
        elif s == "cancelled":
            feed.append(
                ("14:02:13.500", f"RUN {rid_short}", "User pressed Cancel and go back — run marked cancelled; discarding late chunks.", "err")
            )
        else:
            feed.append(
                ("14:02:13.260", f"A2 {primary_m}", "Streaming 7-15d & 1-3m horizon analysis...", "ai")
            )
    if s in ("partial data", "offline cached replay", "complete with countdown"):
        feed.append(
            ("14:02:14.180", f"A3 {primary_m}", f"Matching UK crop windows for {admin} (Oct/Nov, topsoil 9.8 °C)...", "ai")
        )
        feed.append(
            ("14:02:14.980", f"A3 {primary_m}", "Completed in 800 ms -> 3 plausible candidates + Protect & Prepare card ready.", "ok")
        )
        feed.append(
            ("14:02:15.010", f"RUN {rid_short}", "Pipeline terminal state reached (COMPLETE). Auto-advance countdown started (4s).", "ok")
        )

    return {
        "state": s,
        "rail": rail,
        "sources": sources,
        "agents": agents,
        "feed": feed,
    }


def _execute_live_pipeline(
    sel: dict[str, Any],
    run_id: str,
    rail_ph: Any,
    sources_ph: Any,
    war_room_ph: Any,
    feed_ph: Any,
    banner_ph: Any,
) -> dict[str, Any] | None:
    """
    Execute the complete Stage 2 -> Stage 3 -> Stage 4 pipeline inside one script run
    using `st.empty()` placeholders (`rail_ph`, `sources_ph`, `war_room_ph`, `feed_ph`, `banner_ph`).
    """
    lat = float(sel.get("lat", 52.2053))
    lon = float(sel.get("lon", 0.1218))
    grid = sel.get("grid_cell", "52.20°N, 0.10°E")
    admin = sel.get("admin_area", "England")
    primary_m = st.session_state.get("primary_model_id", "gemini-3-flash-preview")
    fallback_m = st.session_state.get("fallback_model_id", "gemini-3.1-flash-lite-preview")
    force_fail = bool(st.session_state.get("force_model_fail", False))

    t_pipeline_start = time.perf_counter()

    def _is_cancelled() -> bool:
        return run_id in st.session_state.get("cancelled_runs", set())

    # Initial state: Step 1 done, Step 2 running
    append_feed_event(
        run_id,
        f"RUN {run_id.replace('run_', '')[:4]}",
        f"Confirmed UK point {lat:.4f}, {lon:.4f} (grid {grid}, {admin})",
        "info",
    )

    rail: list[tuple[str, str, str]] = [
        ("1 Coordinate confirmed", "done", "8 ms"),
        ("2 Weather & soil moisture", "running", "fetching…"),
        ("3 Drought indicators", "queued", "—"),
        ("4 AI agents (A1 → A2 → A3)", "queued", "—"),
        ("5 Outlook ready", "queued", "—"),
    ]
    sources: list[dict[str, str]] = [
        {"name": "Open-Meteo recent & 15-day forecast", "state": "LIVE", "kind": "MODELLED", "meta": "requesting 45d daily + 3 soil layers…"},
        {"name": "Open-Meteo 10-year daily baseline", "state": "LIVE", "kind": "MODELLED", "meta": "queued (2016–2025 archive)…"},
        {"name": "Open-Meteo seasonal ensemble", "state": "LIVE", "kind": "SEASONAL ENSEMBLE", "meta": "queued (50-member ensemble)…"},
        {"name": "Soil-moisture layer check (0–7, 7–28, 28–100 cm)", "state": "LIVE", "kind": "MODELLED", "meta": "awaiting forecast payload…"},
        {"name": "Crop & planting rule table", "state": "LIVE", "kind": "HEURISTIC", "meta": f"12 UK agronomy windows loaded ({admin})"},
    ]
    agents_ui: list[dict[str, Any]] = [
        {
            "id": "A1",
            "title": "Agent 1 — Weather & Soil Moisture Analyst",
            "model": primary_m,
            "status": "queued",
            "elapsed": "—",
            "inputs": ["30d Rain", "30d ET₀", "SM 0–100cm", "10y Baseline"],
            "stream": "Waiting for Open-Meteo weather & soil moisture indicators…",
            "takeaway": "Takeaway: Pending Agent 1 completion.",
            "product_kind": "AI-GENERATED",
        },
        {
            "id": "A2",
            "title": "Agent 2 — Drought & Horizon Analyst",
            "model": primary_m,
            "status": "queued",
            "elapsed": "—",
            "inputs": ["A1 Summary", "15d Forecast", "50-Member Ensemble"],
            "stream": "Queued behind Agent 1…",
            "takeaway": "Takeaway: Pending Agent 2 completion.",
            "product_kind": "AI-GENERATED",
        },
        {
            "id": "A3",
            "title": "Agent 3 — UK Crop & Planting Advisor",
            "model": primary_m,
            "status": "queued",
            "elapsed": "—",
            "inputs": ["A1 + A2 Context", "UK Crop Table", f"Region: {admin}"],
            "stream": "Queued behind Agent 2…",
            "takeaway": "Takeaway: Pending Agent 3 completion.",
            "product_kind": "AI-GENERATED",
        },
    ]

    def _refresh_ui() -> None:
        rail_ph.markdown(_render_rail_html(rail), unsafe_allow_html=True)
        sources_ph.markdown(_render_sources_html(sources), unsafe_allow_html=True)
        war_room_ph.markdown(_render_war_room_html(agents_ui), unsafe_allow_html=True)
        feed_ph.markdown(_render_feed_html(_feed_tuples_from_events(run_id)), unsafe_allow_html=True)

    _refresh_ui()

    # Step 2: Fetch Open-Meteo Forecast, 10y Baseline, and Seasonal Ensemble
    t_w0 = time.perf_counter()
    fc_res = fetch_forecast_and_recent(lat, lon, run_id)
    if _is_cancelled():
        return None
    sources[0] = {
        "name": "Open-Meteo recent & 15-day forecast",
        "state": fc_res["source_state"],
        "kind": "MODELLED",
        "meta": f"45d daily · 1,080h soil · {fc_res['latency_ms']} ms",
    }
    _refresh_ui()

    base_res = fetch_10y_baseline(lat, lon, run_id)
    if _is_cancelled():
        return None
    base_stats = compute_10y_window_stats(base_res["payload"])
    sources[1] = {
        "name": "Open-Meteo 10-year daily baseline",
        "state": base_res["source_state"],
        "kind": "MODELLED",
        "meta": f"3,653 days (2016–2025) · {base_res['latency_ms']} ms",
    }
    _refresh_ui()

    seas_res = fetch_seasonal_ensemble(
        lat,
        lon,
        run_id,
        baseline_90d_mm=base_stats["mean_90d_rain_mm"],
    )
    if _is_cancelled():
        return None
    w_elapsed_ms = int((time.perf_counter() - t_w0) * 1000)
    s_stats = seas_res.get("stats", {})
    sources[2] = {
        "name": "Open-Meteo seasonal ensemble",
        "state": seas_res["source_state"],
        "kind": "SEASONAL ENSEMBLE",
        "meta": (
            f"{s_stats.get('member_count', 50)} members · 90d med {s_stats.get('p50_mm', 0)} mm · {seas_res['latency_ms']} ms"
            if seas_res["available"]
            else "UNAVAILABLE · 1–3m marked INCONCLUSIVE"
        ),
    }

    rail[1] = (
        "2 Weather & soil moisture",
        "done" if seas_res["available"] else "degraded",
        f"{w_elapsed_ms} ms",
    )
    rail[2] = ("3 Drought indicators", "running", "computing…")
    _refresh_ui()

    # Step 3: Compute deterministic drought indicators & UK crop rules
    t_ind0 = time.perf_counter()
    ind = compute_drought_indicators(fc_res, base_stats, seas_res, run_id=run_id, what_if=False, emit_events=True)
    crops_res = match_uk_crops(ind, sel, run_id=run_id, emit_events=True)
    ind_elapsed_ms = max(2, int((time.perf_counter() - t_ind0) * 1000))

    sources[3] = {
        "name": "Soil-moisture layer check (0–7, 7–28, 28–100 cm)",
        "state": fc_res["source_state"],
        "kind": "MODELLED",
        "meta": f"{ind['layers_ok']}/3 layers · {ind['sm_0_7_now']:.2f} / {ind['sm_7_28_now']:.2f} / {ind['sm_28_100_now']:.2f} m³/m³",
    }
    sources[4] = {
        "name": "Crop & planting rule table",
        "state": "LIVE",
        "kind": "HEURISTIC",
        "meta": f"{crops_res['total_rules_loaded']} UK rules ({crops_res['admin']}, {crops_res['month_name']}, {crops_res['soil_temp_c']:.1f} °C)",
    }

    rail[2] = ("3 Drought indicators", "done", f"{ind_elapsed_ms} ms")
    rail[3] = ("4 AI agents (A1 → A2 → A3)", "running", "streaming…")
    _refresh_ui()

    # Update global data_mode badge if cached
    if fc_res["source_state"] in ("CACHED", "DEMO FIXTURE") and base_res["source_state"] in ("CACHED", "DEMO FIXTURE"):
        st.session_state.data_mode = "OFFLINE-CACHE"
    else:
        st.session_state.data_mode = "ONLINE"

    # Step 4: Stream A1 -> A2 -> A3 sequentially
    t_ag0 = time.perf_counter()
    idx_map = {"A1": 0, "A2": 1, "A3": 2}

    def _on_chunk(agent_id: str, model_id: str, st_code: str, preview_text: str) -> None:
        i = idx_map[agent_id]
        agents_ui[i]["model"] = model_id
        agents_ui[i]["status"] = st_code
        agents_ui[i]["elapsed"] = "streaming…"
        agents_ui[i]["stream"] = preview_text
        war_room_ph.markdown(_render_war_room_html(agents_ui), unsafe_allow_html=True)
        feed_ph.markdown(_render_feed_html(_feed_tuples_from_events(run_id)), unsafe_allow_html=True)

    def _on_agent_done(agent_id: str, res_dict: dict[str, Any]) -> None:
        i = idx_map[agent_id]
        out_obj = res_dict["output"]
        agents_ui[i]["model"] = res_dict["model_used"]
        agents_ui[i]["status"] = res_dict["status"]
        agents_ui[i]["product_kind"] = res_dict.get("product_kind", "AI-GENERATED")
        agents_ui[i]["elapsed"] = f"{res_dict['elapsed_ms']} ms"
        agents_ui[i]["stream"] = out_obj.public_narrative
        if hasattr(out_obj, "handoff_note"):
            agents_ui[i]["takeaway"] = out_obj.handoff_note
        else:
            agents_ui[i]["takeaway"] = f"Takeaway: {', '.join( getattr(out_obj, 'crop_tags', [])[:3] )} — verify parcel suitability."
        _refresh_ui()

    agents_res = run_sequential_agents(
        indicators=ind,
        crops_res=crops_res,
        selection=sel,
        run_id=run_id,
        primary_model=primary_m,
        fallback_model=fallback_m,
        force_model_fail=force_fail,
        on_chunk=_on_chunk,
        on_agent_done=_on_agent_done,
        is_cancelled=_is_cancelled,
    )
    if agents_res.get("cancelled") or _is_cancelled():
        return None

    ag_elapsed_ms = int((time.perf_counter() - t_ag0) * 1000)
    total_ms = int((time.perf_counter() - t_pipeline_start) * 1000)

    any_fallback = any(agents_res[k]["status"] == "fallback" for k in ("a1", "a2", "a3"))
    rail[3] = ("4 AI agents (A1 → A2 → A3)", "degraded" if any_fallback else "done", f"{ag_elapsed_ms} ms")
    rail[4] = ("5 Outlook ready", "done" if seas_res["available"] else "degraded", f"{total_ms} ms")

    append_feed_event(
        run_id,
        f"RUN {run_id.replace('run_', '')[:4]}",
        f"Pipeline terminal state reached in {total_ms} ms. Auto-advance countdown started (4s).",
        "ok",
    )
    _refresh_ui()

    bundle = {
        "run_id": run_id,
        "selection": sel,
        "forecast_res": fc_res,
        "baseline_res": base_res,
        "baseline_stats": base_stats,
        "seasonal_res": seas_res,
        "indicators": ind,
        "crops_res": crops_res,
        "agents_res": agents_res,
        "rail": rail,
        "sources": sources,
        "agents_ui": agents_ui,
        "feed_tuples": _feed_tuples_from_events(run_id),
    }
    st.session_state.active_run_bundle = bundle

    # Save to results_history (max 3) so user can return from Screen 1 without new API calls
    hist = st.session_state.get("results_history", [])
    hist = [h for h in hist if h.get("run_id") != run_id]
    hist.insert(0, bundle)
    st.session_state.results_history = hist[:3]

    return bundle


def render_analyse_screen() -> None:
    """Render Screen 2 (LIVE ANALYSIS: Context bar, Progress rail, Source checklist, War room, Live feed)."""
    sel = st.session_state.get("confirmed_selection") or st.session_state.get("pending_selection") or {
        "lat": 52.2053,
        "lon": 0.1218,
        "grid_cell": "52.20°N, 0.10°E",
        "admin_area": "England",
        "land_status": "UK land · England",
    }
    run_id = st.session_state.get("run_id") or "run_demo01"
    s2_state = st.session_state.get("dev_screen2_state", "live_or_default")

    lat = float(sel.get("lat", 52.2053))
    lon = float(sel.get("lon", 0.1218))
    grid = sel.get("grid_cell", "52.20°N, 0.10°E")
    admin = sel.get("admin_area", "England")
    london_time = now_london_str()
    mode_str = "OFFLINE-CACHE" if s2_state == "offline cached replay" else st.session_state.get("data_mode", "ONLINE")

    # 1. Context bar (56px) + Cancel button on the right
    ctx_col, cancel_col = st.columns([8.3, 1.7], gap="small")
    with ctx_col:
        locator_svg = uk_locator_svg_html(lat, lon)
        ctx_html = f"""
        <div class="oa-context-bar" role="region" aria-label="Selected Location Context">
          <div class="oa-context-left">
            {locator_svg}
            <div>
              <div style="font-size:13px;font-weight:600;color:#F8FAFC;">
                {html.escape(sel.get("land_status", f"UK land · {admin}"))}
                <span style="color:#9AA8BC;font-weight:400;margin-left:6px;">
                  ({html.escape(sel.get("geographic_context", "United Kingdom"))})
                </span>
              </div>
              <div style="font-family:var(--font-mono);font-size:12px;color:#22D3EE;margin-top:2px;">
                coord: {lat:.4f}°N, {lon:.4f}°E &nbsp;·&nbsp;
                <span style="color:#E2E8F0;">grid: {html.escape(grid)}</span> &nbsp;·&nbsp;
                <span style="color:#9AA8BC;">run: {html.escape(run_id)}</span> &nbsp;·&nbsp;
                <span style="color:#9AA8BC;">{html.escape(london_time)}</span>
              </div>
            </div>
          </div>
          <div>
            {provenance_badge_html("CACHED" if mode_str == "OFFLINE-CACHE" else "LIVE", "MODELLED", "Open-Meteo weather & soil-water model pipeline")}
          </div>
        </div>
        """
        st.markdown(clean_html(ctx_html), unsafe_allow_html=True)

    with cancel_col:
        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
        if st.button("✕ Cancel and go back", key="s2_cancel_btn", use_container_width=True):
            cancel_active_analysis()
            st.rerun()

    # Placeholders for single-run live streaming updates
    rail_ph = st.empty()
    sources_ph = st.empty()
    war_room_ph = st.empty()
    feed_ph = st.empty()

    b_col1, b_col2, b_col3 = st.columns([6.4, 1.8, 1.8], gap="small")
    banner_ph = b_col1.empty()
    with b_col2:
        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
        if st.button("View outlook →", key="s2_view_outlook_btn", type="primary", use_container_width=True):
            advance_to_outlook()
            st.rerun()
    with b_col3:
        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
        if st.button("Stay here", key="s2_stay_here_btn", use_container_width=True):
            st.session_state.stay_on_analyse = True
            st.rerun()

    # Decide between live pipeline execution vs Section 5 static preview state
    active_bundle = st.session_state.get("active_run_bundle")
    just_finished_live = False

    if s2_state == "live_or_default":
        if not active_bundle or active_bundle.get("run_id") != run_id:
            active_bundle = _execute_live_pipeline(
                sel=sel,
                run_id=run_id,
                rail_ph=rail_ph,
                sources_ph=sources_ph,
                war_room_ph=war_room_ph,
                feed_ph=feed_ph,
                banner_ph=banner_ph,
            )
            just_finished_live = active_bundle is not None
        if active_bundle:
            rail_ph.markdown(_render_rail_html(active_bundle["rail"]), unsafe_allow_html=True)
            sources_ph.markdown(_render_sources_html(active_bundle["sources"]), unsafe_allow_html=True)
            war_room_ph.markdown(_render_war_room_html(active_bundle["agents_ui"]), unsafe_allow_html=True)
            feed_ph.markdown(_render_feed_html(active_bundle["feed_tuples"]), unsafe_allow_html=True)
    else:
        payload = _build_stage1_preview_payload(s2_state, sel, run_id)
        rail_ph.markdown(_render_rail_html(payload["rail"]), unsafe_allow_html=True)
        sources_ph.markdown(_render_sources_html(payload["sources"]), unsafe_allow_html=True)
        war_room_ph.markdown(_render_war_room_html(payload["agents"]), unsafe_allow_html=True)
        feed_ph.markdown(_render_feed_html(payload["feed"]), unsafe_allow_html=True)

    # Diagnostics drawer at bottom of Screen 2
    st.markdown("<div style='margin-top:4px;'></div>", unsafe_allow_html=True)
    render_diagnostics_drawer("analyse_diag")

    # 6. Completion banner & 4-second visible countdown for live runs
    if s2_state == "live_or_default" and active_bundle:
        if just_finished_live and not st.session_state.get("stay_on_analyse") and "preview_phase" not in st.query_params:
            for rem in (4, 3, 2, 1):
                if run_id in st.session_state.get("cancelled_runs", set()) or st.session_state.get("stay_on_analyse"):
                    break
                banner_ph.markdown(
                    clean_html(
                        f'<div class="oa-complete-banner">'
                        f'<div class="oa-complete-text">'
                        f'<span style="color:#10B981;">✓</span> Analysis complete — opening Outlook in {rem}s… (or click Stay here)'
                        f"</div>"
                        f'<span style="font-family:var(--font-mono);font-size:11px;color:#9AA8BC;">run: {html.escape(run_id)}</span>'
                        f"</div>"
                    ),
                    unsafe_allow_html=True,
                )
                time.sleep(0.85)
            if not st.session_state.get("stay_on_analyse") and run_id not in st.session_state.get("cancelled_runs", set()):
                advance_to_outlook()
                st.rerun()
        else:
            banner_ph.markdown(
                clean_html(
                    f'<div class="oa-complete-banner">'
                    f'<div class="oa-complete-text">'
                    f'<span style="color:#10B981;">✓</span> Analysis complete — click View outlook → to open Screen 3.'
                    f"</div>"
                    f'<span style="font-family:var(--font-mono);font-size:11px;color:#9AA8BC;">run: {html.escape(run_id)}</span>'
                    f"</div>"
                ),
                unsafe_allow_html=True,
            )
    else:
        preview_state = s2_state if s2_state != "live_or_default" else "complete with countdown"
        if preview_state in ("complete with countdown", "partial data", "offline cached replay"):
            banner_msg = (
                "Analysis complete — opening Outlook in 4s… (click View outlook to inspect Screen 3)"
                if not st.session_state.get("stay_on_analyse")
                else "Analysis complete — auto-advance paused ('Stay here' selected)."
            )
            banner_ph.markdown(
                clean_html(
                    f'<div class="oa-complete-banner">'
                    f'<div class="oa-complete-text">'
                    f'<span style="color:#10B981;">✓</span> {html.escape(banner_msg)}'
                    f"</div>"
                    f'<span style="font-family:var(--font-mono);font-size:11px;color:#9AA8BC;">state: {html.escape(preview_state)}</span>'
                    f"</div>"
                ),
                unsafe_allow_html=True,
            )
        else:
            banner_ph.markdown(
                clean_html(
                    f'<div class="oa-complete-banner" style="background:rgba(30,41,59,0.55);border-color:rgba(148,163,184,0.28);">'
                    f'<div class="oa-complete-text" style="color:#E2E8F0;">'
                    f'⚡ Previewing Screen 2 state: <span style="color:#22D3EE;font-family:var(--font-mono);">{html.escape(preview_state)}</span>'
                    f"</div>"
                    f'<span style="font-family:var(--font-mono);font-size:11px;color:#9AA8BC;">Switch state in Diagnostics below</span>'
                    f"</div>"
                ),
                unsafe_allow_html=True,
            )
