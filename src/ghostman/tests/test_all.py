import asyncio
import httpx
import pytest
from ghostman.storage import StorageManager
from ghostman.network import NetworkEngine
from ghostman.webhook_server import WebhookServer
from ghostman.app import GhostmanApp

# Tell pytest that all async tests should automatically use an event loop
pytestmark = pytest.mark.asyncio


# 1. Storage tests
async def test_storage_initialization():
    sm = StorageManager()
    cols = sm.load_collections()
    assert len(cols) > 0, "Collections failed to initialize"


# 2. Network engine tests
async def test_network_engine_requests():
    net = NetworkEngine()
    
    r = await net.execute_request("GET", "https://jsonplaceholder.typicode.com/posts/1")
    assert r["success"] and r["status_code"] == 200, "Network GET failed"
    
    r_post = await net.execute_request("POST", "https://jsonplaceholder.typicode.com/posts/1", body='{"test": 1}')
    assert r_post["success"], "Network POST failed"
    
    r_fail = await net.execute_request("GET", "invalid-target")
    assert not r_fail["success"], "Error handling check failed"


# 3. Webhook listener tests
async def test_webhook_server():
    received = []
    ws = WebhookServer(port=9098, on_hook_received=lambda h: received.append(h))
    await ws.start()
    
    try:
        async with httpx.AsyncClient() as c:
            resp = await c.post("http://127.0.0.1:9098/test", json={"ping": "pong"})
            assert resp.status_code == 200
            
        await asyncio.sleep(0.1)
        assert len(received) == 1 and received[0]["path"] == "/test"
    finally:
        # Wrap in try/finally to ensure the server stops even if assertions fail
        await ws.stop()


# 4. TUI Smoke tests (Textual app)
async def test_tui_smoke():
    app = GhostmanApp()
    # Textual's run_test() works perfectly inside pytest-asyncio
    async with app.run_test() as pilot:
        await pilot.press("ctrl+s")
        await pilot.pause(1.0)

