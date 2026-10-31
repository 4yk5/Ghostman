import asyncio
import os
import sys

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

    # High-resolution, dark/transparent PNG rendering
    try:
        from playwright.async_api import async_playwright
        from PIL import Image

        asset_png = os.path.join(assets_dir, "ghostman-preview.png")

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(viewport={"width": 1200, "height": 800}, device_scale_factor=2)
            await page.goto(f"file:///{os.path.abspath(main_svg_path)}")
            await page.wait_for_timeout(400)
            svg_el = page.locator("svg").first
            await svg_el.screenshot(path=asset_png, omit_background=True)
            await browser.close()

        # Crop to tight bounding box
        im = Image.open(asset_png)
        bbox = im.getbbox()
        if bbox:
            cropped = im.crop(bbox)
            cropped.save(asset_png)
        print(f"[+] Rendered clean, tightly cropped PNG to {asset_png}")
    except Exception as e:
        print(f"[-] Could not render PNG: {e}")

if __name__ == "__main__":
    asyncio.run(capture())
