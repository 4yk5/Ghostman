import asyncio
import os
import sys

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from app import GhostmanApp

async def capture():
    assets_dir = os.path.join(BASE_DIR, "assets")
    os.makedirs(assets_dir, exist_ok=True)

    app = GhostmanApp()
    async with app.run_test(size=(116, 32)) as pilot:
        await pilot.pause(0.5)
        # 1. Main View
        main_svg_path = os.path.join(assets_dir, "ghostman-main.svg")
        with open(main_svg_path, "w", encoding="utf-8") as f:
            f.write(app.export_screenshot(title="Ghostman - Terminal API Studio"))
        print("[+] Generated ghostman-main.svg")

        # 2. Response View
        await pilot.press("ctrl+s")
        await pilot.pause(1.5)
        resp_svg_path = os.path.join(assets_dir, "ghostman-response.svg")
        with open(resp_svg_path, "w", encoding="utf-8") as f:
            f.write(app.export_screenshot(title="Ghostman - Response & Telemetry"))
        print("[+] Generated ghostman-response.svg")

        # 3. Webhook View
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

        webhook_svg_path = os.path.join(assets_dir, "ghostman-webhook.svg")
        with open(webhook_svg_path, "w", encoding="utf-8") as f:
            f.write(app.export_screenshot(title="Ghostman - Live Webhook Receiver"))
        print("[+] Generated ghostman-webhook.svg")

        await app.webhook_server.stop()

    # Now render high-res PNG using Playwright
    try:
        from playwright.sync_api import sync_playwright
        desktop_png = r"C:\Users\Terenax\Desktop\ghostman-preview.png"
        asset_png = os.path.join(assets_dir, "ghostman-preview.png")

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1200, "height": 800}, device_scale_factor=2)
            page.goto(f"file:///{os.path.abspath(main_svg_path)}")
            page.wait_for_timeout(400)
            svg_el = page.locator("svg").first
            if svg_el.is_visible():
                svg_el.screenshot(path=desktop_png)
                svg_el.screenshot(path=asset_png)
            else:
                page.screenshot(path=desktop_png)
                page.screenshot(path=asset_png)
            browser.close()
        print(f"[+] Rendered high-res PNG to {desktop_png} and {asset_png}")
    except Exception as e:
        print(f"[-] Could not render PNG via playwright: {e}")

if __name__ == "__main__":
    asyncio.run(capture())
