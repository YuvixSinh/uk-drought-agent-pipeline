"""
Stage 0 Automated Verification Script — Orbital Agronomist (v5)
Starts the Stage 0 FastAPI spike on http://127.0.0.1:8000, verifies:
1. GET /api/health
2. POST /api/validate on two UK points (Cambridge, Edinburgh) and one sea point (Irish Sea)
3. GET /api/spike/events SSE stream
4. Headless Microsoft Edge (CDP) browser check at 1920x1080: dot-matrix globe renders with
   0 external CDN calls, SSE stream reaches the browser, and clicking the globe returns
   lat/lng to backend validation.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import websockets

EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
CDP_PORT = 9226
WEB_DIR = Path(__file__).resolve().parent
ROOT_DIR = WEB_DIR.parent


def post_json(url: str, payload: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


async def run_browser_spike_check() -> None:
    user_data_dir = tempfile.mkdtemp(prefix="oa_edge_stage0_")
    edge_proc = subprocess.Popen(
        [
            EDGE_PATH,
            "--headless=new",
            "--disable-gpu=false",
            "--enable-webgl",
            "--ignore-gpu-blocklist",
            "--window-size=1920,1080",
            f"--remote-debugging-port={CDP_PORT}",
            f"--user-data-dir={user_data_dir}",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        ws_url = None
        for _ in range(30):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/list", timeout=1) as r:
                    targets = json.loads(r.read().decode("utf-8"))
                    for t in targets:
                        if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
                            ws_url = t["webSocketDebuggerUrl"]
                            break
                if ws_url:
                    break
            except Exception:
                await asyncio.sleep(0.2)
        if not ws_url:
            raise RuntimeError("Could not connect to headless Edge CDP")

        async with websockets.connect(ws_url, max_size=50_000_000) as ws:
            msg_id = 0

            async def send_cmd(method: str, params: dict | None = None):
                nonlocal msg_id
                msg_id += 1
                await ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
                while True:
                    raw = await ws.recv()
                    data = json.loads(raw)
                    if data.get("id") == msg_id:
                        return data.get("result", {})

            await send_cmd("Page.enable")
            await send_cmd("Runtime.enable")
            await send_cmd(
                "Emulation.setDeviceMetricsOverride",
                {"width": 1920, "height": 1080, "deviceScaleFactor": 1, "mobile": False},
            )
            await send_cmd("Page.navigate", {"url": "http://127.0.0.1:8000/"})

            # Wait for globe ready & SSE completion
            for _ in range(40):
                res = await send_cmd(
                    "Runtime.evaluate",
                    {
                        "expression": "({ready: !!window.__stage0GlobeReady, sseCount: (window.__sseEvents || []).length})",
                        "returnByValue": True,
                    },
                )
                val = res.get("result", {}).get("value", {})
                if val.get("ready") and val.get("sseCount", 0) >= 5:
                    break
                await asyncio.sleep(0.25)

            sse_res = await send_cmd(
                "Runtime.evaluate",
                {"expression": "window.__sseEvents", "returnByValue": True},
            )
            sse_events = sse_res.get("result", {}).get("value", [])
            print(f"3. Browser SSE received {len(sse_events)} events; final state={sse_events[-1]['state']}")
            assert len(sse_events) == 5 and sse_events[-1]["state"] == "DONE"

            # Dispatch click at centre of 1920x1080 globe canvas (960, 540)
            await send_cmd(
                "Input.dispatchMouseEvent",
                {"type": "mousePressed", "x": 960, "y": 540, "button": "left", "clickCount": 1},
            )
            await send_cmd(
                "Input.dispatchMouseEvent",
                {"type": "mouseReleased", "x": 960, "y": 540, "button": "left", "clickCount": 1},
            )
            await asyncio.sleep(0.6)

            click_res = await send_cmd(
                "Runtime.evaluate",
                {"expression": "window.__lastValidate", "returnByValue": True},
            )
            click_val = click_res.get("result", {}).get("value")
            print("4. Globe canvas click round-trip /api/validate:", click_val)
            assert click_val is not None and "valid" in click_val

            # Click Cambridge button in browser
            await send_cmd(
                "Runtime.evaluate",
                {"expression": "document.getElementById('btn-cam').click()", "returnByValue": True},
            )
            await asyncio.sleep(0.4)
            cam_res = await send_cmd(
                "Runtime.evaluate",
                {"expression": "window.__lastValidate", "returnByValue": True},
            )
            cam_val = cam_res.get("result", {}).get("value")
            print("5. Browser Cambridge button round-trip:", cam_val)
            assert cam_val["valid"] is True and cam_val["nation"] == "England"

            # Check resource URLs loaded in browser (ensure 0 external CDN calls)
            res_urls = await send_cmd(
                "Runtime.evaluate",
                {
                    "expression": "performance.getEntriesByType('resource').map(r => r.name)",
                    "returnByValue": True,
                },
            )
            urls = res_urls.get("result", {}).get("value", [])
            ext = [u for u in urls if not u.startswith("http://127.0.0.1:8000") and not u.startswith("data:")]
            print(f"6. Browser resources loaded: {len(urls)} local, {len(ext)} external CDN")
            assert len(ext) == 0, f"Unexpected external CDN requests: {ext}"
    finally:
        edge_proc.terminate()


def main() -> None:
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "web.backend.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=str(ROOT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        for _ in range(30):
            try:
                with urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=1) as r:
                    health = json.loads(r.read().decode("utf-8"))
                    if health.get("status") == "ok":
                        print("1. Health check OK:", health)
                        break
            except Exception:
                time.sleep(0.2)
        else:
            raise RuntimeError("FastAPI server did not start on 127.0.0.1:8000")

        # Validate 2 UK points + 1 sea point
        cam = post_json("http://127.0.0.1:8000/api/validate", {"lat": 52.2053, "lon": 0.1218})
        edi = post_json("http://127.0.0.1:8000/api/validate", {"lat": 55.9533, "lon": -3.1883})
        sea = post_json("http://127.0.0.1:8000/api/validate", {"lat": 53.5000, "lon": -5.0000})
        print("2a. Validate Cambridge:", cam)
        print("2b. Validate Edinburgh:", edi)
        print("2c. Validate Irish Sea:", sea)
        assert cam["valid"] is True and cam["nation"] == "England"
        assert edi["valid"] is True and edi["nation"] == "Scotland"
        assert sea["valid"] is False and sea["nation"] is None

        asyncio.run(run_browser_spike_check())
        print("STAGE 0 SPIKE ALL CHECKS PASSED")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    main()
