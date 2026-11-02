# Orbital Agronomist — UK Drought & Crop Outlook (v2, Three-Screen Flow)

**Orbital Agronomist** is an interactive UK drought-exposure and agronomy outlook platform built for the **Imperial × DeepMind Hackathon**. Users pick any point on UK land on a 3D WebGL Earth, confirm the location, watch a live three-agent Gemini pipeline stream over Open-Meteo weather, soil-water, 10-year archive baseline, and seasonal ensemble data, and explore a 3-column decision outlook with zero-API-call What-If stress simulation.

---

## Quick Start (Windows PowerShell)

```powershell
# 1. Install dependencies
py -m pip install -r requirements.txt

# 2. Ensure .env contains GEMINI_API_KEY (never committed to git)
# GEMINI_API_KEY=your_api_key_here

# 3. Run the application
py -m streamlit run app.py

# 4. Run the automated verification suite
py -m unittest discover -s tests -v
```

---

## Architecture & Three-Screen Flow

The app runs in a single Streamlit process controlled by `st.session_state.phase` (`pick` → `analyse` → `outlook`):

1. **Screen 1 — PICK (`ui/screens/pick.py` + `globe_component/`)**
   - **Left Intro Panel (~30%)**: Concise overview (`<= 120` words), 3 guiding questions, quick-launch UK city shortcuts (*Cambridge*, *Norwich*, *Edinburgh*, *Belfast*, *Cardiff*), manual lat/lon coordinate input, and instant reload of the last 3 analysed runs (`results_history`).
   - **Right 3D WebGL Globe (~70%, `820px`)**: Locally bundled `globe.gl.min.js` + Natural Earth `1:110m` world context + `1:10m` UK land polygons (`England`, `Scotland`, `Wales`, `Northern Ireland`, and UK islands).
   - **Confirm Gating**: Clicking the globe or a city chip only sets a `pending_selection`. **Zero** Open-Meteo or Gemini API calls are made until the user clicks **Confirm & analyse** (verified by the Outbound Call Log in the Diagnostics drawer).

2. **Screen 2 — LIVE ANALYSIS (`ui/screens/analyse.py`)**
   - Executes inside a single Streamlit script run using `st.empty()` placeholders so token streaming never triggers full-page reruns.
   - **Left Column**: Data source cards (*Open-Meteo Forecast + 30d Past*, *Open-Meteo 10-Year Baseline Archive*, *Open-Meteo Seasonal Ensemble*) and three sequential Gemini Agent cards:
     - **Agent 1 (`Meteorologist`)**: Synthesises current dryness, 30-day rainfall anomaly vs 10-year mean, and 3-depth volumetric soil moisture (`0–7 cm`, `7–28 cm`, `28–100 cm`).
     - **Agent 2 (`Hydrologist`)**: Synthesises 7–15 day forecast rain vs $\text{ET}_0$ deficit and 1–3 month seasonal ensemble outlook.
     - **Agent 3 (`Agronomist`)**: Evaluates deterministic UK regional crop candidates, planting windows, parcel-verification checklist, and protect/prepare actions.
   - **Right Column**: Chronological live event feed (`[SOURCE]`, `[INDICATOR]`, `[AGENT]`, `[HANDOFF]`, `[FALLBACK]`).
   - **Auto-Advance**: Displays a 4-second visible countdown on completion with **Stay here** and **View outlook →** controls.

3. **Screen 3 — OUTLOOK (`ui/screens/outlook.py`)**
   - **Top Summary Strip**: Selected coordinates, snapped model grid cell, 3 horizon risk chips (`Current` · `7–15d` · `1–3m`), **What-if stress toggle** (`-35%` rain, `+15%` $\text{ET}_0$, `-20%` soil moisture — recomputes deterministically with **0 new API calls**), **Choose another location**, and **Download `.txt` dossier**.
   - **Column 1 (Q1 — How dry is it now?)**: Bold 1-sentence answer, 4 KPI tiles with dual provenance badges, 3-depth soil moisture profile bar (`0–7 cm`, `7–28 cm`, `28–100 cm`), and 30-day rain vs $\text{ET}_0$ Plotly chart.
   - **Column 2 (Q2 — What do the next 7–15d & 1–3m suggest?)**: Bold 1-sentence answer, 14-day cumulative $\text{Rain} - \text{ET}_0$ Plotly fan chart, and 1–3 month seasonal ensemble card (degrades gracefully if unavailable).
   - **Column 3 (Q3 — Plausible UK crops & planting windows)**: Bold 1-sentence answer, explicit regional weather-candidate disclaimer, top 3 UK crop cards from `crop_rules.py`, Protect/Prepare action card, and collapsible parcel verification checklist.

---

## Model Policy & Honesty Guardrails

- **Permitted Models Only**: Uses `gemini-3-flash-preview` (primary) and `gemini-3.1-flash-lite-preview` (fallback) with `ThinkingConfig(thinking_level=ThinkingLevel.LOW, include_thoughts=False)`. Never uses Gemini 1.5, Gemini 2.5, or Argon 4.
- **3-Tier Resilience**: Primary Gemini model → Secondary Gemini fallback model → Deterministic rule-based agronomy synthesis (`FALLBACK · HEURISTIC`).
- **No Unverified Satellite Claims**: All metrics are explicitly badged (`[LIVE | CACHED | FALLBACK | DEMO FIXTURE] · [MODELLED | SEASONAL ENSEMBLE | DERIVED | SIMULATED | AI-GENERATED | HEURISTIC]`).
