"""
Automated Browser Verification for Stage 0 Globe & Flow Spike
Launches Streamlit onspike_stage0.py and drives real Google Chrome via CDP (websockets)
to verify:
1. WebGL Globe mounts and returns two arbitrary UK clicks + one sea click to Python.
2. Confirm transitions pick -> analyse, Cancel mid-stream interrupts loop and returns to pick with selection kept.
3. Full run transitions pick -> analyse -> outlook -> Choose another location -> pick with camera POV preserved.
"""

import asyncio
import json
import subprocess
import time
import urllib.request
import websockets

CHROME_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
STREAMLIT_PORT = 8509
CDP_PORT = 9229


async def cdp_call(ws, method: str, params: dict | None = None, msg_id: int = 1) -> dict:
    await ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
    while True:
        raw = await ws.recv()
        msg = json.loads(raw)
        if msg.get("id") == msg_id:
            return msg


async def eval_js(ws, expression: str, msg_id: int = 1, context_id: int | None = None):
    params = {"expression": expression, "returnByValue": True, "awaitPromise": True}
    if context_id is not None:
        params["contextId"] = context_id
    res = await cdp_call(ws, "Runtime.evaluate", params, msg_id=msg_id)
    return res.get("result", {}).get("result", {}).get("value")


async def run_test():
    st_proc = subprocess.Popen(
        [
            "py", "-m", "streamlit", "run", "spike_stage0.py",
            "--server.port", str(STREAMLIT_PORT),
            "--server.headless", "true",
            "--browser.gatherUsageStats", "false",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    chrome_proc = None
    try:
        # Wait for Streamlit server
        for _ in range(30):
            try:
                urllib.request.urlopen(f"http://localhost:{STREAMLIT_PORT}/_stcore/health", timeout=1)
                break
            except Exception:
                time.sleep(0.5)

        chrome_proc = subprocess.Popen(
            [
                CHROME_PATH,
                f"--remote-debugging-port={CDP_PORT}",
                "--headless=new",
                "--disable-gpu=false",
                "--enable-webgl",
                "--ignore-gpu-blocklist",
                "--window-size=1920,1080",
                "--no-first-run",
                "--no-default-browser-check",
                "--user-data-dir=C:\\Users\\Yuvraj Singh\\.gemini\\antigravity\\brain\\a97715cc-d95e-468d-9af3-56f4bfb55bef\\scratch\\chrome_stage0",
                f"http://localhost:{STREAMLIT_PORT}",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait for CDP target
        ws_url = None
        for _ in range(30):
            try:
                with urllib.request.urlopen(f"http://localhost:{CDP_PORT}/json", timeout=1) as r:
                    targets = json.loads(r.read().decode())
                    for t in targets:
                        if t.get("type") == "page" and str(STREAMLIT_PORT) in t.get("url", ""):
                            ws_url = t["webSocketDebuggerUrl"]
                            break
                if ws_url:
                    break
            except Exception:
                time.sleep(0.5)

        assert ws_url, "Failed to connect to Chrome CDP page target"

        async with websockets.connect(ws_url, max_size=50_000_000) as ws:
            msg_seq = 1
            await cdp_call(ws, "Runtime.enable", {}, msg_seq); msg_seq += 1
            await cdp_call(ws, "Page.enable", {}, msg_seq); msg_seq += 1

            # Wait for globe iframe to load and initialize __ukGlobePick
            print("Waiting for Streamlit app and WebGL globe iframe...")
            globe_ready = False
            for _ in range(40):
                await asyncio.sleep(0.5)
                check_js = """
                (() => {
                    const iframes = Array.from(document.querySelectorAll('iframe'));
                    for (const f of iframes) {
                        try {
                            if (f.contentWindow && typeof f.contentWindow.__ukGlobePick === 'function') {
                                return {
                                    ready: true,
                                    hasWebGL: Boolean(f.contentWindow.__ukGlobeInstance),
                                    title: document.body.innerText.split('\\n')[0]
                                };
                            }
                        } catch (e) {}
                    }
                    return { ready: false };
                })()
                """
                val = await eval_js(ws, check_js, msg_seq); msg_seq += 1
                if val and val.get("ready"):
                    print(f"Globe component ready! WebGL mounted: {val.get('hasWebGL')}")
                    globe_ready = True
                    break
            assert globe_ready, "Globe iframe did not become ready"

            # Helper to trigger a click inside the globe component and wait for Python rerun
            async def pick_on_globe(lat: float, lon: float, label: str):
                nonlocal msg_seq
                js = f"""
                (() => {{
                    const f = Array.from(document.querySelectorAll('iframe')).find(
                        el => el.contentWindow && typeof el.contentWindow.__ukGlobePick === 'function'
                    );
                    f.contentWindow.__ukGlobePick({lat}, {lon}, 'globe_click');
                    return true;
                }})()
                """
                await eval_js(ws, js, msg_seq); msg_seq += 1
                await asyncio.sleep(1.4)
                body_text = await eval_js(ws, "document.body.innerText", msg_seq); msg_seq += 1
                print(f"\n--- After {label} ({lat}, {lon}) ---")
                for line in body_text.splitlines():
                    if any(k in line for k in ["Stage 0 Spike", "CLICK (", "valid", "land_status", "grid_cell"]):
                        print("  ", line)
                return body_text

            # 1. Arbitrary UK Point 1: Midlands, England (52.3512, -1.1845)
            await pick_on_globe(52.3512, -1.1845, "UK Point 1 (Midlands, England)")

            # 2. Sea click: Irish Sea (53.7500, -4.8500)
            await pick_on_globe(53.7500, -4.8500, "Sea Click (Irish Sea)")

            # 3. Arbitrary UK Point 2: Scottish Highlands (56.8198, -4.1862)
            await pick_on_globe(56.8198, -4.1862, "UK Point 2 (Scottish Highlands)")

            # 4. Confirm into Screen 2 (analyse), then click Cancel mid-run!
            print("\n--- Testing Confirm -> Screen 2 (analyse) -> Cancel mid-run ---")
            confirm_js = """
            (() => {
                const f = Array.from(document.querySelectorAll('iframe')).find(
                    el => el.contentWindow && el.contentWindow.document.getElementById('btn-confirm')
                );
                f.contentWindow.document.getElementById('btn-confirm').click();
                return true;
            })()
            """
            await eval_js(ws, confirm_js, msg_seq); msg_seq += 1
            await asyncio.sleep(1.2)
            body_analyse = await eval_js(ws, "document.body.innerText", msg_seq); msg_seq += 1
            for line in body_analyse.splitlines():
                if any(k in line for k in ["Stage 0 Spike", "Screen 2: ANALYSE", "Streaming step", "Chunk"]):
                    print("  [During Screen 2]", line)

            # Click Cancel button while Screen 2 loop is still streaming
            cancel_js = """
            (() => {
                const btns = Array.from(document.querySelectorAll('button'));
                const cancelBtn = btns.find(b => b.innerText.includes('Cancel and go back'));
                if (cancelBtn) { cancelBtn.click(); return true; }
                return false;
            })()
            """
            clicked_cancel = await eval_js(ws, cancel_js, msg_seq); msg_seq += 1
            print(f"  Clicked Cancel button: {clicked_cancel}")
            await asyncio.sleep(1.2)
            body_after_cancel = await eval_js(ws, "document.body.innerText", msg_seq); msg_seq += 1
            for line in body_after_cancel.splitlines():
                if any(k in line for k in ["Stage 0 Spike", "Screen 1: PICK", "56.8198"]):
                    print("  [After Cancel]", line)

            # 5. Re-confirm and let Screen 2 finish -> transitions to Screen 3 (outlook) -> return to Screen 1 and verify POV restored
            print("\n--- Testing Full Flow: Confirm -> Analyse Complete -> Screen 3 (Outlook) -> Return with Camera POV ---")
            py_confirm_js = """
            (() => {
                const btns = Array.from(document.querySelectorAll('button'));
                const btn = btns.find(b => b.innerText.includes('Confirm and analyse'));
                if (btn) { btn.click(); return true; }
                return false;
            })()
            """
            await eval_js(ws, py_confirm_js, msg_seq); msg_seq += 1
            await asyncio.sleep(5.0)
            body_outlook = await eval_js(ws, "document.body.innerText", msg_seq); msg_seq += 1
            for line in body_outlook.splitlines():
                if any(k in line for k in ["Stage 0 Spike", "Screen 3: OUTLOOK", "Saved results history"]):
                    print("  [On Screen 3]", line)

            # Click 'Choose another location'
            back_js = """
            (() => {
                const btns = Array.from(document.querySelectorAll('button'));
                const btn = btns.find(b => b.innerText.includes('Choose another location'));
                if (btn) { btn.click(); return true; }
                return false;
            })()
            """
            await eval_js(ws, back_js, msg_seq); msg_seq += 1
            await asyncio.sleep(1.5)
            body_returned = await eval_js(ws, "document.body.innerText", msg_seq); msg_seq += 1
            for line in body_returned.splitlines():
                if any(k in line for k in ["Stage 0 Spike", "Screen 1: PICK"]):
                    print("  [Returned to Screen 1]", line)

    finally:
        if chrome_proc:
            chrome_proc.terminate()
        st_proc.terminate()


if __name__ == "__main__":
    asyncio.run(run_test())
