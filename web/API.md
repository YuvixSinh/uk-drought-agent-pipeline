# Orbital Agronomist (v5) — REST & SSE API Contract (`web/API.md`)

All endpoints are served from `http://127.0.0.1:8000` (same origin as the front-end).
The Gemini API key (`GEMINI_API_KEY`) is loaded strictly in the backend via `python-dotenv` and is never exposed to the browser.

---

## 1. `GET /api/health`
Returns server health, whether `GEMINI_API_KEY` is configured (boolean only), verified Gemini 3 model IDs, and available pre-warmed demo locations.

```json
{
  "status": "ok",
  "gemini_key_present": true,
  "primary_model": "gemini-3-flash-preview",
  "fallback_model": "gemini-3.1-flash-lite-preview",
  "demo_locations": ["cambridge", "edinburgh", "belfast", "norwich", "cardiff"]
}
```

---

## 2. `POST /api/validate`
Validates whether a clicked or entered coordinate lies on UK land (`England`, `Scotland`, `Wales`, `Northern Ireland`, and UK islands) using `globe_component/uk_land.py` (`shapely` + `uk_10m.geojson`). Makes **zero** external weather or Gemini API calls.

- **Request**: `{"lat": 52.2053, "lon": 0.1218}`
- **Response (`200 OK`)**:
```json
{
  "valid": true,
  "nation": "England",
  "grid_cell": "52.20°N, 0.10°E",
  "status": "UK_LAND",
  "label": "UK Land · England",
  "context": "~1–25 km model grid · Regional weather context",
  "lat": 52.2053,
  "lon": 0.1218
}
```

---

## 3. `POST /api/run`
Starts a new live analysis run for a validated UK land coordinate. Automatically cancels any prior active run.

- **Request**: `{"lat": 52.2053, "lon": 0.1218, "force_model_fail": false}`
- **Response (`200 OK`)**:
```json
{
  "run_id": "run-a1b2c3d4",
  "status": "RUNNING",
  "location": { ... }
}
```

---

## 4. `GET /api/run/{run_id}/events` (Server-Sent Events)
Streams real-time pipeline events (`text/event-stream`) for the Analysis Wheel (`#analysis`) and Details Drawer (`Feed` tab). Replays any events already emitted since run start so fast sources are never missed.

- **Event types**:
  - `event: source` — `{"id": "forecast"|"soil"|"baseline"|"seasonal", "state": "fetching"|"done"|"cached"|"failed", "latency_ms": 14, "summary": "...", "ts": "17:40:12.104"}`
  - `event: compute` — `{"id": "indicators"|"crops", "state": "done", "summary": "...", "ts": "..."}`
  - `event: agent` — `{"id": "meteorologist"|"hydrologist"|"agronomist", "state": "active"|"done"|"fallback", "model": "gemini-3-flash-preview", "mode": "LIVE"|"FALLBACK", "latency_ms": 1840, "summary": "...", "ts": "..."}`
  - `event: token` — `{"agent": "meteorologist"|"hydrologist"|"agronomist", "model": "gemini-3-flash-preview", "text": "Streaming narrative preview...", "ts": "..."}`
  - `event: handoff` — `{"from": "meteorologist"|"hydrologist", "to": "hydrologist"|"agronomist", "takeaway": "Takeaway: ...", "ts": "..."}`
  - `event: progress` — `{"pct": 58, "word": "Gathering"|"Reading soil"|"Assessing"|"Planning"|"Done", "ticker": "<= 6 word ticker", "ts": "..."}`
  - `event: done` — `{"run_id": "run-a1b2c3d4", "state": "DONE"|"PARTIAL", "ts": "..."}`
  - `event: error` — `{"run_id": "run-a1b2c3d4", "message": "...", "ts": "..."}`

---

## 5. `GET /api/run/{run_id}/result`
Returns the complete structured `ResultPayload` (`q1`, `q2`, `q3`, `agents`, `sources`, `provenance`, `assumptions`, `feed`, and pre-computed `scenario` delta).

---

## 6. `POST /api/run/{run_id}/cancel`
Cancels an active run immediately, discarding any late model stream chunks.

- **Response**: `{"run_id": "run-a1b2c3d4", "cancelled": true, "status": "CANCELLED"}`

---

## 7. `POST /api/run/{run_id}/scenario`
Recomputes deterministic indicators and UK crop rules for `"dry30"` (`-35%` rain, `+15%` ET₀, `-20%` soil moisture) or `"none"` with **zero external API or model calls**.

- **Request**: `{"scenario": "dry30"}` (or `{"scenario": "none"}`)
- **Response**: Updated `ResultPayload` with `scenario_active: true|false`.

---

## 8. `GET /api/run/{run_id}/dossier.txt?scenario=false|true`
Returns a plain-text (`.txt`) agronomic dossier with `Content-Disposition: attachment` containing location, London timestamp, horizon chips, Q1/Q2/Q3 KPIs with provenance tags, crop candidates, ground verification checklist, protect & prepare actions, full sequential agent narratives + model IDs, unknown parameters list, and the model-resolution disclaimer.

---

## 9. `GET /api/demo/{name}`
Returns an instant (`< 20 ms`, zero network calls) `ResultPayload` for pre-warmed UK demo locations (`cambridge`, `edinburgh`, `belfast`, `norwich`, `cardiff`) with all items badged `CACHED`.
