# Orbital Agronomist — Animated Website (v5)

A sleek, minimalist, three-page animated web application (`1920×1080`, zero scroll) built on a single FastAPI origin (`http://127.0.0.1:8000`) that reuses the root-level UK water-balance, seasonal ensemble, crop-matching, and sequential Gemini 3 agent modules while leaving the root Streamlit prototype (`app.py`) 100% untouched.

## Quick Start (Windows PowerShell)

From the project root (`"C:\Daily Use\Imperial\Hackathon\Halloween x deepmind"`):

```powershell
.\web\run.ps1
```

Or directly via Python:

```powershell
py -m uvicorn web.backend.main:app --host 127.0.0.1 --port 8000
```

Then open **`http://127.0.0.1:8000`** in Microsoft Edge or Chrome (`1920×1080`).

---

## Three-Page Architecture (`#place`, `#analysis`, `#outlook`)

1. **`#place` — UK 3D Globe Selection**:
   - Persistent WebGL dot-matrix globe (`globe.gl` `2.35.1`) with highlighted UK land polygon (`uk_10m.geojson`) and 5 UK city shortcut beacons (`Cambridge`, `Norwich`, `Edinburgh`, `Belfast`, `Cardiff`).
   - Clicking sea or non-UK land shows `"Not UK land. No data requested."` with **zero** weather or Gemini API calls.
   - Clicking UK land displays the slim bottom-centre **Confirm** bar (`52.21°N 0.12°E · England`, `Confirm`, `Clear`).
   - Top-right `⋯ Menu` provides manual Lat/Lon coordinate inputs, cached **Demo Mode (`D`)**, and a **Force primary model fallback** toggle.

2. **`#analysis` — The Wheel**:
   - The persistent 3D globe smoothly shrinks into the `140px` centre hub of a `760px × 760px` SVG choreography wheel.
   - **Outer Ring (4 Data Sources)**: `Forecast`, `Soil layers`, `10-year baseline`, `Seasonal ensemble` stream particles inward as real-time Server-Sent Events (`SSE`) arrive.
   - **Inner Ring (3 Sequential Gemini Agents, 120° apart)**: `Meteorologist`, `Hydrologist`, and `Agronomist` light up in sequence with rotating halos and hand-off arcs.
   - Clicking any node opens the right-hand **Details Drawer** focused on that source or agent.

3. **`#outlook` — Three-Question Split View**:
   - **Column 1 (`01 · How dry is it now?`)**: 3-segment SVG arc gauge, 30-day rainfall anomaly & root-zone (`7–28 cm`) moisture KPIs, 10-year baseline bar strip (`2016–2025` + `Now`), and 3-layer volumetric soil moisture profile (`0–7 cm`, `7–28 cm`, `28–100 cm`).
   - **Column 2 (`02 · What is coming?`)**: Dual horizon gauges (`7–15 DAYS`, `1–3 MONTHS`), 15-day cumulative `P − ET₀` curve with hatched deficit area below `0 mm`, and 50-member seasonal ensemble interquartile (`p25`–`p75`) spread bar.
   - **Column 3 (`03 · What could grow?`)**: Topsoil temperature (`0–7 cm`), 3 candidate UK crop tiles with `Oct–Apr` sowing window bars, confidence dots, constraint icons, and the **Protect & Prepare** horizon strip (`24–72 h`, `7 days`, `1–3 months`).
   - **Scenario: 30 dry days (`S`)**: Instant in-memory perturbation (`-35%` rain, `+15%` ET₀, `-20%` soil moisture, 0 external API calls) with `800 ms` chart morphing and dashed baseline ghost lines.
   - **Export `.txt`**: Downloads a complete plain-text agronomic dossier (`/api/run/{run_id}/dossier.txt`).

---

## Keyboard Shortcuts

- `←` / `→` : Flick between `#place`, `#analysis`, and `#outlook`
- `Enter` : Confirm selected UK point on `#place` and start analysis
- `D` : Toggle instant cached **Demo Mode** (`Cambridge`, `Edinburgh`, `Belfast`, `Norwich`, `Cardiff`)
- `S` : Toggle **Scenario: 30 dry days** on `#outlook`
- `Escape` : Close the **Details Drawer** or menu popover
