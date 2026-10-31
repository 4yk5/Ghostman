import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import GhostmanApp

async def capture():
    assets_dir = os.path.join(os.getcwd(), "assets")
    os.makedirs(assets_dir, exist_ok=True)

    app = GhostmanApp()
    async with app.run_test(size=(116, 32)) as pilot:
        await pilot.pause(0.5)
        with open(os.path.join(assets_dir, "ghostman-main.svg"), "w", encoding="utf-8") as f:
            f.write(app.export_screenshot(title="Ghostman - Terminal API Studio"))

        await pilot.press("ctrl+s")
        await pilot.pause(1.2)
        with open(os.path.join(assets_dir, "ghostman-response.svg"), "w", encoding="utf-8") as f:
            f.write(app.export_screenshot(title="Ghostman - Response & Telemetry"))

        app.query_one("#tabs").active = "tab-webhook"
        await pilot.pause(0.3)
        await app.action_toggle_webhook()
        await pilot.pause(0.3)

        app.handle_incoming_webhook({
            "id": 1,
            "timestamp": "10:14:02",
            "method": "POST",
            "path": "/api/webhooks/stripe",
            "headers": {"Content-Type": "application/json"},
            "body": '{\n  "event": "payment_intent.succeeded",\n  "amount": 4900\n}',
            "raw_body": '{"event":"payment_intent.succeeded"}'
        })
        app.handle_incoming_webhook({
            "id": 2,
            "timestamp": "10:14:15",
            "method": "POST",
            "path": "/api/webhooks/github",
            "headers": {"Content-Type": "application/json"},
            "body": '{\n  "ref": "refs/heads/main",\n  "commits": 3\n}',
            "raw_body": '{"ref":"refs/heads/main"}'
        })
        await pilot.pause(0.5)

        with open(os.path.join(assets_dir, "ghostman-webhook.svg"), "w", encoding="utf-8") as f:
            f.write(app.export_screenshot(title="Ghostman - Live Webhook Receiver"))

        await app.webhook_server.stop()
    print("Assets generated.")

if __name__ == "__main__":
    asyncio.run(capture())
