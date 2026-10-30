import asyncio
import os
import sys
import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from app import GhostmanApp
from network import NetworkEngine
from webhook_server import WebhookServer
from storage import StorageManager

async def run_tests():
    print("Running Ghostman test suite...")

    # 1. Storage tests
    sm = StorageManager()
    cols = sm.load_collections()
    assert len(cols) > 0, "Collections failed to initialize"
    print("  [+] Storage: OK")

    # 2. Network engine tests
    net = NetworkEngine()
    r = await net.execute_request("GET", "https://jsonplaceholder.typicode.com/posts/1")
    assert r["success"] and r["status_code"] == 200, "Network GET failed"
    
    r_post = await net.execute_request("POST", "https://jsonplaceholder.typicode.com/posts", body='{"test": 1}')
    assert r_post["success"], "Network POST failed"

    r_fail = await net.execute_request("GET", "invalid-target")
    assert not r_fail["success"], "Error handling check failed"
    print("  [+] Network Engine: OK")

    # 3. Webhook listener tests
    received = []
    ws = WebhookServer(port=9098, on_hook_received=lambda h: received.append(h))
    await ws.start()
    
    async with httpx.AsyncClient() as c:
        resp = await c.post("http://127.0.0.1:9098/test", json={"ping": "pong"})
        assert resp.status_code == 200

    await asyncio.sleep(0.1)
    assert len(received) == 1 and received[0]["path"] == "/test"
    await ws.stop()
    print("  [+] Webhook Server: OK")

    # 4. TUI Smoke tests
    app = GhostmanApp()
    async with app.run_test() as pilot:
        await pilot.press("ctrl+s")
        await pilot.pause(1.0)
        assert app.query_one("#tab-response-pane").display

        await pilot.press("ctrl+w")
        await pilot.pause(0.2)
        assert app.webhook_server.is_running
        await pilot.press("ctrl+w")
        await pilot.pause(0.2)
        assert not app.webhook_server.is_running
    print("  [+] TUI Pilot: OK")

    print("\nAll tests passed successfully.")

if __name__ == "__main__":
    asyncio.run(run_tests())
