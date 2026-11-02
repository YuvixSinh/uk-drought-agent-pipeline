"""
Stage 0 Spike App — Orbital Agronomist (v2)
Proves:
1. Real WebGL 3D globe returning lat/lon clicks to Python via st.components.v1.declare_component
   (tested with two arbitrary UK land points and one sea click).
2. (a) st.session_state switching cleanly between three screens (pick -> analyse -> outlook -> pick).
3. (b) Camera POV saved on click/confirm and restored when returning from Screen 3 (outlook) to Screen 1 (pick).
4. (c) Cancel button interrupting an in-flight streaming loop that writes into st.empty() placeholders,
       marking run_id cancelled and returning to Screen 1 with pending_selection preserved.
"""

from __future__ import annotations

import time
import uuid
import streamlit as st

from globe_component import QUICK_LAUNCH_CITIES, render_uk_globe, validate_uk_coordinate

st.set_page_config(page_title="Stage 0 Spike | Orbital Agronomist", layout="wide")

# Session state initialization (Section 2 PhaseState contract)
if "phase" not in st.session_state:
    st.session_state.phase = "pick"
if "pending_selection" not in st.session_state:
    st.session_state.pending_selection = None
if "confirmed_selection" not in st.session_state:
    st.session_state.confirmed_selection = None
if "run_id" not in st.session_state:
    st.session_state.run_id = None
if "cancelled_runs" not in st.session_state:
    st.session_state.cancelled_runs = set()
if "camera_pov" not in st.session_state:
    st.session_state.camera_pov = {"lat": 54.5, "lng": -3.0, "altitude": 1.6}
if "results_history" not in st.session_state:
    st.session_state.results_history = []
if "sync_token" not in st.session_state:
    st.session_state.sync_token = "init"
if "last_event_ts" not in st.session_state:
    st.session_state.last_event_ts = 0
if "click_log" not in st.session_state:
    st.session_state.click_log = []


def _cancel_run_callback() -> None:
    """Callback fired when Cancel is clicked during Screen 2 streaming loop."""
    if st.session_state.run_id:
        st.session_state.cancelled_runs.add(st.session_state.run_id)
    st.session_state.phase = "pick"
    st.session_state.sync_token = f"restore_{time.time()}"


st.markdown(
    f"### Stage 0 Spike · Phase=`{st.session_state.phase}` · "
    f"RunID=`{st.session_state.run_id}` · "
    f"CameraPOV=`lat={st.session_state.camera_pov['lat']:.2f}, lng={st.session_state.camera_pov['lng']:.2f}, alt={st.session_state.camera_pov['altitude']:.2f}`"
)

if st.session_state.phase == "pick":
    col_info, col_globe = st.columns([3, 7])
    with col_info:
        st.subheader("Screen 1: PICK")
        st.write("Click any UK land point on the 3D WebGL globe (or use quick chips).")
        for city in QUICK_LAUNCH_CITIES[:3]:
            if st.button(f"Chip: {city['name']}", key=f"chip_{city['name']}"):
                check = validate_uk_coordinate(city["lat"], city["lon"])
                st.session_state.pending_selection = {
                    "lat": city["lat"],
                    "lon": city["lon"],
                    "source": f"chip:{city['name']}",
                    **check,
                }
                st.session_state.camera_pov = {"lat": city["lat"], "lng": city["lon"], "altitude": 0.6}
                st.session_state.sync_token = f"chip_{city['name']}_{time.time()}"
                st.rerun()

        st.markdown("**Pending Selection in Python:**")
        st.json(st.session_state.pending_selection or {"state": "idle"})

        if st.session_state.pending_selection and st.session_state.pending_selection.get("valid"):
            if st.button("Confirm and analyse (Python button)", key="py_confirm_btn", type="primary"):
                st.session_state.confirmed_selection = dict(st.session_state.pending_selection)
                st.session_state.run_id = f"run_{uuid.uuid4().hex[:8]}"
                st.session_state.phase = "analyse"
                st.rerun()

        st.markdown("**Received Globe Events Log:**")
        for entry in st.session_state.click_log[-6:]:
            st.code(entry)

    with col_globe:
        ev = render_uk_globe(
            pending_selection=st.session_state.pending_selection,
            camera_pov=st.session_state.camera_pov,
            sync_token=st.session_state.sync_token,
            height=680,
            key="spike_globe",
        )
        if ev and isinstance(ev, dict) and ev.get("ts", 0) != st.session_state.last_event_ts:
            st.session_state.last_event_ts = ev["ts"]
            action = ev.get("action")
            if ev.get("camera_pov"):
                st.session_state.camera_pov = ev["camera_pov"]

            if action == "click":
                lat = float(ev["lat"])
                lon = float(ev["lon"])
                check = validate_uk_coordinate(lat, lon)
                log_line = (
                    f"CLICK ({lat:.4f}, {lon:.4f}) -> valid={check['valid']} | "
                    f"status={check['status']} | {check['land_status']}"
                )
                st.session_state.click_log.append(log_line)
                if check["valid"]:
                    st.session_state.pending_selection = {
                        "lat": lat,
                        "lon": lon,
                        "source": ev.get("source", "globe_click"),
                        **check,
                    }
                else:
                    st.session_state.pending_selection = None
                st.rerun()
            elif action == "confirm" and st.session_state.pending_selection and st.session_state.pending_selection.get("valid"):
                st.session_state.confirmed_selection = dict(st.session_state.pending_selection)
                st.session_state.run_id = f"run_{uuid.uuid4().hex[:8]}"
                st.session_state.phase = "analyse"
                st.rerun()
            elif action == "clear":
                st.session_state.pending_selection = None
                st.rerun()

elif st.session_state.phase == "analyse":
    active_run_id = st.session_state.run_id
    st.subheader(f"Screen 2: ANALYSE (Active Run `{active_run_id}`)")
    st.button("Cancel and go back", key="cancel_analyse_btn", on_click=_cancel_run_callback)

    status_box = st.empty()
    stream_box = st.empty()
    nav_box = st.empty()

    # Stream inside a single script run using placeholders
    accumulated = []
    for step_idx in range(1, 9):
        if active_run_id in st.session_state.cancelled_runs:
            status_box.warning(f"Run {active_run_id} cancelled; discarding late chunks.")
            st.stop()
        status_box.info(f"Streaming step {step_idx}/8 for run `{active_run_id}` at {st.session_state.confirmed_selection['lat']}, {st.session_state.confirmed_selection['lon']}...")
        accumulated.append(f"[{time.strftime('%H:%M:%S')}] Chunk {step_idx} for {active_run_id}")
        stream_box.code("\n".join(accumulated))
        time.sleep(0.45)

    status_box.success(f"Analysis complete for `{active_run_id}`.")
    st.session_state.results_history.insert(0, {
        "run_id": active_run_id,
        "selection": st.session_state.confirmed_selection,
        "chunks": list(accumulated),
    })
    st.session_state.results_history = st.session_state.results_history[:3]
    st.session_state.phase = "outlook"
    st.rerun()

elif st.session_state.phase == "outlook":
    st.subheader("Screen 3: OUTLOOK")
    st.write("Confirmed selection:", st.session_state.confirmed_selection)
    st.write(f"Saved results history count: {len(st.session_state.results_history)}")
    if st.button("Choose another location", key="back_to_pick_btn"):
        st.session_state.phase = "pick"
        st.session_state.sync_token = f"return_{time.time()}"
        st.rerun()
