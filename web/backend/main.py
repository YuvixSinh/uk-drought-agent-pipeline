"""
FastAPI Backend Server — Orbital Agronomist (v5)
Serves the animated front-end (`web/frontend/`) and exposes the REST + SSE API on
`http://127.0.0.1:8000` (same origin). Keeps `GEMINI_API_KEY` strictly on the server.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

load_dotenv(ROOT_DIR / ".env")

from web.backend.adapters import (  # noqa: E402
    FALLBACK_MODEL,
    PRIMARY_MODEL,
    format_plain_text_dossier,
    validate_point,
)
from web.backend.api_models import (  # noqa: E402
    Q1Payload,
    Q2Payload,
    Q3Payload,
    ResultPayload,
    RunStartRequest,
    RunStartResponse,
    ScenarioRequest,
    ValidateRequest,
    ValidateResponse,
)
from web.backend.demo_mode import DEMO_LOCATIONS, get_demo_result  # noqa: E402
from web.backend.runner import RUN_MANAGER, sse_event_generator  # noqa: E402

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
VENDOR_DIR = FRONTEND_DIR / "vendor"
SRC_DIR = FRONTEND_DIR / "src"
SRC_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="Orbital Agronomist API (v5)",
    version="5.0.0",
    docs_url="/api/docs",
)


@app.get("/api/health")
async def health() -> dict[str, Any]:
    has_key = bool(os.environ.get("GEMINI_API_KEY", "").strip())
    return {
        "status": "ok",
        "gemini_key_present": has_key,
        "primary_model": PRIMARY_MODEL,
        "fallback_model": FALLBACK_MODEL,
        "demo_locations": list(DEMO_LOCATIONS.keys()),
    }


@app.post("/api/validate", response_model=ValidateResponse)
async def api_validate(req: ValidateRequest) -> ValidateResponse:
    return validate_point(req.lat, req.lon)


@app.post("/api/run", response_model=RunStartResponse)
async def api_start_run(req: RunStartRequest) -> RunStartResponse:
    loc = validate_point(req.lat, req.lon)
    if not loc.valid:
        raise HTTPException(status_code=400, detail="Not UK land. No data requested.")
    session = RUN_MANAGER.start_run(req.lat, req.lon, force_model_fail=req.force_model_fail)
    return RunStartResponse(
        run_id=session.run_id,
        status=session.state,
        location=session.location,
    )


@app.get("/api/run/{run_id}/events")
async def api_run_events(run_id: str) -> StreamingResponse:
    session = RUN_MANAGER.get_run(run_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return StreamingResponse(
        sse_event_generator(session),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _resolve_result(run_id: str) -> ResultPayload:
    if run_id.startswith("demo-"):
        name = run_id.replace("demo-", "", 1)
        return get_demo_result(name)
    session = RUN_MANAGER.get_run(run_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    if session.result is None:
        raise HTTPException(status_code=409, detail=f"Run {run_id} is currently {session.state}")
    return session.result


@app.get("/api/run/{run_id}/result", response_model=ResultPayload)
async def api_run_result(run_id: str) -> ResultPayload:
    return _resolve_result(run_id)


@app.post("/api/run/{run_id}/cancel")
async def api_cancel_run(run_id: str) -> dict[str, Any]:
    ok = RUN_MANAGER.cancel_run(run_id)
    return {"run_id": run_id, "cancelled": ok, "status": "CANCELLED" if ok else "NOT_FOUND"}


@app.post("/api/run/{run_id}/scenario", response_model=ResultPayload)
async def api_run_scenario(run_id: str, req: ScenarioRequest) -> ResultPayload:
    base_res = _resolve_result(run_id)
    copy_res = base_res.model_copy(deep=True)
    if req.scenario == "dry30" and copy_res.scenario:
        copy_res.scenario_active = True
        copy_res.q1 = Q1Payload.model_validate(copy_res.scenario["q1"])
        copy_res.q2 = Q2Payload.model_validate(copy_res.scenario["q2"])
        copy_res.q3 = Q3Payload.model_validate(copy_res.scenario["q3"])
    else:
        copy_res.scenario_active = False
    return copy_res


@app.get("/api/run/{run_id}/dossier.txt", response_class=PlainTextResponse)
async def api_run_dossier(
    run_id: str,
    scenario: bool = Query(default=False, description="Include 30 dry days scenario state"),
) -> PlainTextResponse:
    res = _resolve_result(run_id)
    txt = format_plain_text_dossier(res, scenario_active=scenario)
    filename = f"orbital_agronomist_{run_id}{'_scenario' if scenario else ''}.txt"
    return PlainTextResponse(
        content=txt,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/demo/{name}", response_model=ResultPayload)
async def api_demo(name: str) -> ResultPayload:
    return get_demo_result(name)


# Keep Stage 0 spike SSE endpoint so `web/test_stage0.py` remains 100% runnable
@app.get("/api/spike-sse")
async def spike_sse() -> StreamingResponse:
    async def event_gen():
        for i in range(1, 4):
            payload = json.dumps({"step": i, "status": "streaming", "source": "spike"})
            yield f"event: progress\ndata: {payload}\n\n"
            await asyncio.sleep(0.05)
        yield f"event: done\ndata: {json.dumps({'status': 'complete'})}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


app.mount("/vendor", StaticFiles(directory=str(VENDOR_DIR)), name="vendor")
app.mount("/src", StaticFiles(directory=str(SRC_DIR)), name="src")


@app.get("/spike.html")
async def serve_spike() -> FileResponse:
    return FileResponse(str(FRONTEND_DIR / "spike.html"))


@app.get("/")
async def serve_index() -> FileResponse:
    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        return FileResponse(str(FRONTEND_DIR / "spike.html"))
    return FileResponse(str(index_path))
