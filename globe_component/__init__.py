"""
Bidirectional 3D WebGL UK Globe Component Wrapper — Orbital Agronomist (v2)
Uses Streamlit's documented st.components.v1.declare_component mechanism to serve
locally bundled globe.gl.min.js + Natural Earth GeoJSONs and return click/confirm/clear
events with camera POV to Python.
"""

from __future__ import annotations

import os
from typing import Any

import streamlit.components.v1 as components

from .uk_land import COASTAL_TOLERANCE_KM, estimate_grid_cell, validate_uk_coordinate

_COMPONENT_DIR = os.path.dirname(os.path.abspath(__file__))
_uk_globe_component = components.declare_component("uk_globe", path=_COMPONENT_DIR)

QUICK_LAUNCH_CITIES = [
    {"name": "Cambridge", "lat": 52.2053, "lon": 0.1218},
    {"name": "Norwich", "lat": 52.6309, "lon": 1.2974},
    {"name": "Edinburgh", "lat": 55.9533, "lon": -3.1883},
    {"name": "Belfast", "lat": 54.5973, "lon": -5.9301},
    {"name": "Cardiff", "lat": 51.4816, "lon": -3.1791},
]

QUICK_CITIES = QUICK_LAUNCH_CITIES


def render_uk_globe(
    pending_selection: dict[str, Any] | None = None,
    camera_pov: dict[str, float] | None = None,
    sync_token: str = "init",
    fly_duration: int = 800,
    height: int = 820,
    key: str = "uk_orbital_globe",
) -> dict[str, Any] | None:
    """Render the interactive 3D WebGL UK globe and return the latest event dict from JS."""
    return _uk_globe_component(
        pending_selection=pending_selection,
        camera_pov=camera_pov or {"lat": 54.5, "lng": -3.0, "altitude": 1.6},
        sync_token=sync_token,
        fly_duration=fly_duration,
        cities=QUICK_LAUNCH_CITIES,
        height=height,
        key=key,
        default=None,
    )


__all__ = [
    "COASTAL_TOLERANCE_KM",
    "QUICK_LAUNCH_CITIES",
    "estimate_grid_cell",
    "render_uk_globe",
    "validate_uk_coordinate",
]
