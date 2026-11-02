"""
Stage 1 Verification & 1920x1080 Screenshot Capture Script
Verifies:
1. Confirm gating, sea/non-UK rejection, UK land selection, and 0 outbound calls in Stage 1.
2. Launches `py -m streamlit run app.py` and captures 1920x1080 screenshots via headless Edge CDP for:
   - Screen 1 (pick — with Cambridge selected so both the 3D globe, selected-point card, and docked Confirm bar are visible)
   - Screen 2 (analyse static preview)
   - Screen 3 (outlook static preview — complete)
   - Screen 3 (outlook static preview — scenario active)
"""

from __future__ import annotations

import asyncio
import base64
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import websockets

from events import get_outbound_calls
from globe_component import validate_uk_coordinate

EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
STREAMLIT_PORT = 8506
CDP_PORT = 9224
ARTIFACT_DIR = Path(r"C:\Users\Yuvraj Singh\.gemini\antigravity\brain\a97715cc-d95e-468d-9af3-56f4bfb55bef")


def run_unit_checks() -> None:
    print("=== 1. STAGE 1 UNIT & GATING CHECKS ===")
    # Sea click
    sea = validate_uk_coordinate(55.0, 2.0)
    assert not sea["valid"] and sea["status"] == "non_uk", f"Expected sea rejection, got {sea}"
    print(f"  [PASS] North Sea (55.0, 2.0) rejected -> {sea['land_status']}")

    # Non-UK land click (Dublin, Republic of Ireland)
    dublin = validate_uk_coordinate(53.3498, -6.2603)
    assert not dublin["valid"], f"Expected Dublin rejection, got {dublin}"
    print(f"  [PASS] Dublin ROI (53.3498, -6.2603) rejected -> {dublin['land_status']}")

    # UK land clicks (England, Scotland, Wales, Northern Ireland, Orkney)
    for name, lat, lon in [
        ("Cambridge", 52.2053, 0.1218),
        ("Edinburgh", 55.9533, -3.1883),
        ("Cardiff", 51.4816, -3.1791),
        ("Belfast", 54.5973, -5.9301),
        ("Orkney", 58.98, -2.96),
    ]:
        res = validate_uk_coordinate(lat, lon)
        assert res["valid"], f"Expected {name} to be valid UK land, got {res}"
        print(f"  [PASS] {name} ({lat}, {lon}) valid -> {res['land_status']} (grid {res['grid_cell']})")

    calls = get_outbound_calls()
    assert len(calls) == 0, f"Expected 0 outbound calls in Stage 1, got {len(calls)}"
    print(f"  [PASS] Outbound Call Log count = {len(calls)} (Zero Open-Meteo or Gemini calls)")


async def capture_url_screenshot(ws_url: str, url: str, out_path: Path, wait_sec: float = 5.0, click_cambridge: bool = False) -> dict:
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
        await send_cmd("Page.navigate", {"url": url})
        await asyncio.sleep(wait_sec)

        if click_cambridge:
            # Click the "Cambridge" quick-launch button in Streamlit so the pending point & Confirm bar show on Screen 1
            js_click_chip = """
            (() => {
                const buttons = Array.from(document.querySelectorAll('button'));
                const camBtn = buttons.find(b => b.innerText && b.innerText.includes('Cambridge'));
                if (camBtn) { camBtn.click(); return 'clicked_cambridge'; }
                return 'not_found';
            })()
            """
            await send_cmd("Runtime.evaluate", {"expression": js_click_chip, "returnByValue": True})
            await asyncio.sleep(3.5)

        # Read visible text and scroll height check
        eval_res = await send_cmd(
            "Runtime.evaluate",
            {
                "expression": "({title: document.title, text: document.body.innerText.slice(0, 600), sh: document.documentElement.scrollHeight, ch: document.documentElement.clientHeight})",
                "returnByValue": True,
            },
        )
        info = eval_res.get("result", {}).get("value", {})

        shot = await send_cmd("Page.captureScreenshot", {"format": "png", "fromSurface": True})
        png_bytes = base64.b64decode(shot["data"])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(png_bytes)
        print(f"  [SCREENSHOT] Saved {out_path.name} ({len(png_bytes):,} bytes) | scrollHeight={info.get('sh')} clientHeight={info.get('ch')}")
        return info


def main() -> None:
    run_unit_checks()

    print("\n=== 2. STARTING STREAMLIT & HEADLESS EDGE (1920x1080) ===")
    st_proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "app.py",
            f"--server.port={STREAMLIT_PORT}",
            "--server.headless=true",
            "--browser.gatherUsageStats=false",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    edge_proc = None
    try:
        base_url = f"http://localhost:{STREAMLIT_PORT}"
        for _ in range(30):
            try:
                urllib.request.urlopen(base_url, timeout=1)
                break
            except Exception:
                time.sleep(0.5)

        edge_proc = subprocess.Popen(
            [
                EDGE_PATH,
                "--headless=new",
                "--disable-gpu-sandbox",
                "--enable-webgl",
                "--ignore-gpu-blocklist",
                "--use-angle=d3d11",
                "--window-size=1920,1080",
                f"--remote-debugging-port={CDP_PORT}",
                "--no-first-run",
                "--no-default-browser-check",
                base_url,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        targets = None
        for _ in range(25):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json") as r:
                    targets = json.loads(r.read().decode())
                    if targets:
                        break
            except Exception:
                time.sleep(0.5)

        page_target = next(t for t in targets if t.get("type") == "page")
        ws_url = page_target["webSocketDebuggerUrl"]

        async def run_all():
            # 1) Screen 1: Pick (select Cambridge shortcut so the selected-point card & docked Confirm bar are visible)
            await capture_url_screenshot(
                ws_url,
                f"{base_url}/?preview_phase=pick",
                ARTIFACT_DIR / "stage1_screen1_pick.png",
                wait_sec=5.5,
                click_cambridge=True,
            )
            # 2) Screen 2: Analyse static preview (complete with countdown)
            await capture_url_screenshot(
                ws_url,
                f"{base_url}/?preview_phase=analyse&s2_state=complete+with+countdown",
                ARTIFACT_DIR / "stage1_screen2_analyse.png",
                wait_sec=4.5,
            )
            # 3) Screen 3: Outlook static preview (complete)
            await capture_url_screenshot(
                ws_url,
                f"{base_url}/?preview_phase=outlook&s3_state=complete",
                ARTIFACT_DIR / "stage1_screen3_outlook.png",
                wait_sec=5.5,
            )
            # 4) Screen 3: Outlook static preview (scenario active)
            await capture_url_screenshot(
                ws_url,
                f"{base_url}/?preview_phase=outlook&s3_state=scenario+active",
                ARTIFACT_DIR / "stage1_screen3_scenario.png",
                wait_sec=5.0,
            )

        asyncio.run(run_all())

    finally:
        if edge_proc:
            edge_proc.terminate()
        st_proc.terminate()


if __name__ == "__main__":
    main()
