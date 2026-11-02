"""
Orbital Agronomist — UK Drought & Crop Outlook (v2, Three-Screen Flow)
Entry point & phase state router:
  - Screen 1 (phase == 'pick'): 3D WebGL UK Globe + Plain-Language Introduction + Confirm Gate
  - Screen 2 (phase == 'analyse'): Live Analysis War Room (A1 -> A2 -> A3) + Real-Time Feed
  - Screen 3 (phase == 'outlook'): Three-Question Decision Screen (Q1, Q2, Q3) + What-If & Dossier
"""

from __future__ import annotations

import os
from dotenv import load_dotenv
import streamlit as st

from ui.components import inject_theme_css, render_global_header
from ui.screens.analyse import render_analyse_screen
from ui.screens.outlook import render_outlook_screen
from ui.screens.pick import render_pick_screen
from ui.state import init_session_state

# Load environment variables silently (never print or log GEMINI_API_KEY)
load_dotenv()
_ = os.environ.get("GEMINI_API_KEY")

st.set_page_config(
    page_title="Orbital Agronomist · UK Drought & Crop Outlook",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def main() -> None:
    """Initialize session state, inject theme CSS, render global header, and route active screen."""
    init_session_state()
    inject_theme_css()
    render_global_header()

    phase = st.session_state.get("phase", "pick")
    if phase == "pick":
        render_pick_screen()
    elif phase == "analyse":
        render_analyse_screen()
    elif phase == "outlook":
        render_outlook_screen()
    else:
        st.session_state.phase = "pick"
        render_pick_screen()


if __name__ == "__main__":
    main()
