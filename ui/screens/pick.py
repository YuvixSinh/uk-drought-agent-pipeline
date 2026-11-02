"""
Screen 1: PICK (Globe + Introduction) — Orbital Agronomist (v2)
Implements Section 3 & 4 requirements:
- Left intro panel (~30% width, <= 120 words excluding chips, legible from a distance)
- Quick-launch city chips (Cambridge, Norwich, Edinburgh, Belfast, Cardiff) — select only, never start analysis
- Manual lat/lon inputs & Recent Runs history (up to last 3 runs restored without new API calls)
- Right 3D WebGL Globe card (~70% width, ~820px tall) with UK 1:10m land validation,
  top-left selected-point card, bottom-left legend, bottom-centre docked Confirm bar,
  bottom-right Reset view + 2D fallback toggle.
- Strictly zero Open-Meteo or Gemini calls on Screen 1.
"""

from __future__ import annotations

import html
import time

import streamlit as st

from globe_component import QUICK_CITIES, render_uk_globe
from ui.components import clean_html, render_diagnostics_drawer
from ui.state import confirm_pending_selection, set_pending_coordinate


def render_pick_screen() -> None:
    """Render Screen 1 (PICK: 30% Intro Panel + 70% Interactive 3D UK Globe)."""
    col_intro, col_globe = st.columns([3.0, 7.0], gap="medium")

    with col_intro:
        # Intro Panel (strictly <= 120 words excluding chips, Section 3)
        intro_html = """
        <section class="oa-intro-panel" aria-label="Introduction">
          <div class="oa-eyebrow">UK DROUGHT &amp; CROP OUTLOOK</div>
          <h1 class="oa-display-title">Orbital Agronomist</h1>
          <p class="oa-lead">
            Pick any point on UK land. Three AI agents read weather and soil-water
            model data for that exact spot and answer three questions.
          </p>

          <div class="oa-q-list" role="list">
            <div class="oa-q-item" role="listitem">
              <span class="oa-q-num">1</span>
              <span>
                <svg width="13" height="13" viewBox="0 0 16 16" fill="none" style="vertical-align:-2px;margin-right:4px;">
                  <path d="M8 1.5C8 1.5 3 7.2 3 10.5C3 13.2 5.2 15 8 15C10.8 15 13 13.2 13 10.5C13 7.2 8 1.5 8 1.5Z" stroke="#22D3EE" stroke-width="1.5"/>
                </svg>
                How dry is it now?
              </span>
            </div>
            <div class="oa-q-item" role="listitem">
              <span class="oa-q-num">2</span>
              <span>
                <svg width="13" height="13" viewBox="0 0 16 16" fill="none" style="vertical-align:-2px;margin-right:4px;">
                  <path d="M2 12L6 8L9 10L14 4" stroke="#38BDF8" stroke-width="1.6" stroke-linecap="round"/>
                </svg>
                What do the next 7 to 15 days and 1 to 3 months suggest?
              </span>
            </div>
            <div class="oa-q-item" role="listitem">
              <span class="oa-q-num">3</span>
              <span>
                <svg width="13" height="13" viewBox="0 0 16 16" fill="none" style="vertical-align:-2px;margin-right:4px;">
                  <path d="M8 14V4M8 6L5 4M8 6L11 4M8 10L5 8M8 10L11 8" stroke="#10B981" stroke-width="1.5" stroke-linecap="round"/>
                </svg>
                Which crops are plausible, and when should planting be considered?
              </span>
            </div>
          </div>

          <div class="oa-steps-mini">
            <div class="oa-step-mini-card">
              <span class="oa-step-mini-num">STEP 1</span>
              <span class="oa-step-mini-text">Rotate and click.</span>
            </div>
            <div class="oa-step-mini-card">
              <span class="oa-step-mini-num">STEP 2</span>
              <span class="oa-step-mini-text">Confirm your point.</span>
            </div>
            <div class="oa-step-mini-card">
              <span class="oa-step-mini-num">STEP 3</span>
              <span class="oa-step-mini-text">Watch the analysis, then read the outlook.</span>
            </div>
          </div>

          <p class="oa-honesty-line">
            Model data, not satellite or field measurement. Crop ideas are weather-based
            candidates; land and soil suitability is not verified.
          </p>
        </section>
        """
        st.markdown(clean_html(intro_html), unsafe_allow_html=True)

        # Quick-launch city chips (only select pending point and fly globe there; never start analysis)
        st.markdown(
            '<div class="oa-label" style="margin-top:10px;margin-bottom:4px;">QUICK-LAUNCH UK SHORTCUTS (SELECTS POINT ONLY)</div>',
            unsafe_allow_html=True,
        )
        chip_cols = st.columns(5, gap="small")
        for idx, city in enumerate(QUICK_CITIES):
            is_selected = (
                st.session_state.pending_selection is not None
                and abs(st.session_state.pending_selection.get("lat", 0.0) - city["lat"]) < 0.02
                and abs(st.session_state.pending_selection.get("lon", 0.0) - city["lon"]) < 0.02
            )
            btn_label = f"● {city['name']}" if is_selected else city["name"]
            if chip_cols[idx].button(
                btn_label,
                key=f"chip_{city['name']}",
                use_container_width=True,
                help=f"Select {city['name']} ({city['lat']:.4f}, {city['lon']:.4f}) as pending point",
            ):
                set_pending_coordinate(city["lat"], city["lon"], source=f"chip:{city['name']}")
                st.session_state.camera_pov = {"lat": city["lat"], "lng": city["lon"], "altitude": 0.68}
                st.session_state.globe_sync_token = f"chip_{city['name']}_{time.time()}"
                st.rerun()

        # Manual Lat/Lon entry (bottom-left utility for keyboard accessibility & exact coordinates)
        with st.expander("Manual coordinate input (Lat / Lon)", expanded=False):
            m_c1, m_c2, m_c3 = st.columns([1.1, 1.1, 1.0])
            default_lat = (
                st.session_state.pending_selection["lat"]
                if st.session_state.pending_selection
                else 52.2053
            )
            default_lon = (
                st.session_state.pending_selection["lon"]
                if st.session_state.pending_selection
                else 0.1218
            )
            in_lat = m_c1.number_input(
                "Latitude (°N)",
                min_value=48.0,
                max_value=62.0,
                value=float(default_lat),
                step=0.05,
                format="%.4f",
                key="manual_lat_input",
            )
            in_lon = m_c2.number_input(
                "Longitude (°E)",
                min_value=-11.0,
                max_value=4.0,
                value=float(default_lon),
                step=0.05,
                format="%.4f",
                key="manual_lon_input",
            )
            m_c3.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)
            if m_c3.button("Preview point", key="manual_preview_btn", use_container_width=True):
                set_pending_coordinate(float(in_lat), float(in_lon), source="manual_input")
                st.session_state.camera_pov = {"lat": float(in_lat), "lng": float(in_lon), "altitude": 0.72}
                st.session_state.globe_sync_token = f"manual_{time.time()}"
                st.rerun()

        # Rejected click notice (if user clicked sea or non-UK land via manual input)
        rej = st.session_state.get("rejected_notice")
        if rej:
            st.markdown(
                f'<div style="margin-top:8px;padding:8px 12px;border-radius:8px;'
                f'background:rgba(244,63,94,0.12);border:1px solid rgba(244,63,94,0.38);'
                f'font-size:12px;color:#FDA4AF;font-family:var(--font-mono);">'
                f'⚠ {html.escape(rej["message"])} ({rej["lat"]:.4f}, {rej["lon"]:.4f})'
                f"</div>",
                unsafe_allow_html=True,
            )

        # Recent runs history (up to last 3 runs in session state, restore without new API calls)
        history = st.session_state.get("results_history", [])
        if history:
            st.markdown(
                '<div class="oa-label" style="margin-top:10px;margin-bottom:4px;">RECENT RUNS (INSTANT RESTORE · 0 API CALLS)</div>',
                unsafe_allow_html=True,
            )
            for idx, item in enumerate(history[:3]):
                sel = item.get("selection", {})
                h_label = (
                    f"↺ {sel.get('admin_area', 'UK')} ({sel.get('lat', 0):.2f}°, {sel.get('lon', 0):.2f}°) "
                    f"· {item.get('run_id', '')}"
                )
                if st.button(h_label, key=f"restore_hist_{idx}", use_container_width=True):
                    st.session_state.confirmed_selection = sel
                    st.session_state.run_id = item.get("run_id")
                    st.session_state.active_assessment = item.get("assessment")
                    st.session_state.phase = "outlook"
                    st.rerun()

    with col_globe:
        pending = st.session_state.get("pending_selection")
        globe_event = render_uk_globe(
            pending_selection=pending,
            camera_pov=st.session_state.get("camera_pov"),
            sync_token=st.session_state.get("globe_sync_token", "init"),
            height=820,
            key="uk_globe_screen1",
        )

        # Process bidirectional events from the WebGL / 2D fallback globe component
        if globe_event and isinstance(globe_event, dict):
            ev_ts = globe_event.get("ts", 0)
            if ev_ts != st.session_state.get("last_globe_event_ts"):
                st.session_state.last_globe_event_ts = ev_ts
                if globe_event.get("camera_pov"):
                    st.session_state.camera_pov = globe_event["camera_pov"]
                ev_type = globe_event.get("action") or globe_event.get("event_type")
                if ev_type in ("click", "select"):
                    set_pending_coordinate(
                        float(globe_event["lat"]),
                        float(globe_event["lon"]),
                        source=str(globe_event.get("source", "globe_click")),
                    )
                    st.rerun()
                elif ev_type == "rejected_click":
                    st.session_state.pending_selection = None
                    st.session_state["rejected_notice"] = {
                        "lat": round(float(globe_event.get("lat", 0.0)), 4),
                        "lon": round(float(globe_event.get("lon", 0.0)), 4),
                        "message": "Not UK land. No data requested.",
                        "ts": str(ev_ts),
                    }
                    st.rerun()
                elif ev_type == "clear":
                    st.session_state.pending_selection = None
                    st.session_state["rejected_notice"] = None
                    st.session_state.globe_sync_token = f"clear_{time.time()}"
                    st.rerun()
                elif ev_type == "confirm":
                    if globe_event.get("lat") is not None and globe_event.get("lon") is not None:
                        set_pending_coordinate(
                            float(globe_event["lat"]),
                            float(globe_event["lon"]),
                            source=str(globe_event.get("source", "globe_confirm")),
                        )
                    if confirm_pending_selection():
                        st.rerun()

    # Diagnostics drawer at bottom of Screen 1 (collapsed by default)
    st.markdown("<div style='margin-top:6px;'></div>", unsafe_allow_html=True)
    render_diagnostics_drawer("pick_diag")
