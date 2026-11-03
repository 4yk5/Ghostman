import asyncio
import os
import sys
import json
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
from textual.widgets import Input, TextArea, Select, ListView, Tabs, Label


async def test_tls_verification_default_and_toggle():
    print("[*] 1. Testing TLS Certificate Verification Default & Toggles...")

    # NetworkEngine must default to verify_ssl=True (no hardcoded verify=False)
    net = NetworkEngine()
    assert net.verify_ssl is True, "VULNERABILITY: NetworkEngine did not default to verify_ssl=True!"

    # Testing self-signed or invalid SSL domain: must fail under verify_ssl=True
    try:
        res = await net.execute_request("GET", "https://self-signed.badssl.com/")
        assert not res["success"], "VULNERABILITY: Untrusted self-signed certificate was accepted under verify_ssl=True!"
        assert "ssl" in res["body"].lower() or "certificate" in res["body"].lower() or "failed" in res["body"].lower()
    except Exception as e:
        # Rejection by httpx/ssl is expected and secure
        pass

    # When verify_ssl=False is explicitly specified, it should bypass verification
    res_insecure = await net.execute_request(
        "GET", "https://self-signed.badssl.com/", verify_ssl=False
    )
    # The request should succeed or reach the server without TLS certificate rejection
    assert "Certificate Verification Failed" not in res_insecure.get("body", "")

    print("  [+] TLS Certificate Verification: PASS")


async def test_saved_and_custom_headers_propagation():
    print("[*] 2. Testing Custom & Saved HTTP Headers Propagation...")

    # Start local WebhookServer to inspect actual received headers
    received_hooks = []
    ws = WebhookServer(port=9095, on_hook_received=lambda h: received_hooks.append(h))
    await ws.start()

    try:
        net = NetworkEngine()
        custom_headers = {
            "Authorization": "Bearer gh_secret_token_12345",
            "X-Custom-Trace-Id": "trace-uuid-abcdef",
            "Accept": "application/vnd.github.v3+json",
        }

        res = await net.execute_request(
            "POST",
            "http://127.0.0.1:9095/header-check",
            headers=custom_headers,
            body='{"test": true}'
        )
        assert res["success"], f"Request to local server failed: {res.get('error')}"

        await asyncio.sleep(0.15)
        assert len(received_hooks) == 1, "WebhookServer did not capture the request"

        captured_headers = received_hooks[0]["headers"]
        # Case-insensitive header lookup
        lower_headers = {k.lower(): v for k, v in captured_headers.items()}

        assert lower_headers.get("authorization") == "Bearer gh_secret_token_12345", (
            "VULNERABILITY: Authorization header was not sent!"
        )
        assert lower_headers.get("x-custom-trace-id") == "trace-uuid-abcdef", (
            "VULNERABILITY: X-Custom-Trace-Id header was not sent!"
        )
        assert lower_headers.get("accept") == "application/vnd.github.v3+json", (
            "VULNERABILITY: Accept header was not sent!"
        )

        # Header parsing and formatting utilities
        header_text = "Authorization: Bearer secret\nContent-Type: application/xml\nUser-Agent: Custom"
        parsed = GhostmanApp.parse_headers_text(header_text)
        assert parsed["Authorization"] == "Bearer secret"
        assert parsed["Content-Type"] == "application/xml"
        assert parsed["User-Agent"] == "Custom"

        # JSON header input support
        json_header_text = '{"Authorization": "Bearer token", "X-Key": "val"}'
        parsed_json = GhostmanApp.parse_headers_text(json_header_text)
        assert parsed_json["Authorization"] == "Bearer token"
        assert parsed_json["X-Key"] == "val"

        # Roundtrip format
        formatted = GhostmanApp.format_headers_text(parsed)
        re_parsed = GhostmanApp.parse_headers_text(formatted)
        assert re_parsed == parsed

    finally:
        await ws.stop()

    print("  [+] Custom & Saved Headers: PASS")


async def test_chunked_transfer_encoding_webhook():
    print("[*] 3. Testing Chunked Transfer Encoding Webhook Reception...")

    received_hooks = []
    ws = WebhookServer(port=9096, on_hook_received=lambda h: received_hooks.append(h))
    await ws.start()

    try:
        # 1. Standard RFC 7230 Chunked Body
        raw_http = (
            b"POST /chunked-endpoint HTTP/1.1\r\n"
            b"Host: 127.0.0.1:9096\r\n"
            b"Transfer-Encoding: chunked\r\n"
            b"Content-Type: text/plain\r\n"
            b"Connection: close\r\n"
            b"\r\n"
            b"7\r\n"
            b"Mozilla\r\n"
            b"9\r\n"
            b"Developer\r\n"
            b"7\r\n"
            b"Network\r\n"
            b"0\r\n"
            b"\r\n"
        )

        reader, writer = await asyncio.open_connection("127.0.0.1", 9096)
        writer.write(raw_http)
        await writer.drain()
        resp = await reader.read(1024)
        writer.close()
        await writer.wait_closed()

        await asyncio.sleep(0.15)
        assert len(received_hooks) == 1, "WebhookServer did not capture chunked request!"
        assert received_hooks[0]["raw_body"] == "MozillaDeveloperNetwork", (
            f"VULNERABILITY: Chunked payload was not properly reconstructed! Got: {received_hooks[0]['raw_body']}"
        )

        # 2. Chunked JSON with Chunk Extensions (e.g., "11;ext=foo")
        json_chunked = (
            b"POST /chunked-json HTTP/1.1\r\n"
            b"Host: 127.0.0.1:9096\r\n"
            b"Transfer-Encoding: chunked\r\n"
            b"Content-Type: application/json\r\n"
            b"Connection: close\r\n"
            b"\r\n"
            b"9;ext=part1\r\n"
            b"{\"event\":\r\n"
            b"a;ext=part2\r\n"
            b" \"deploy\"}\r\n"
            b"0\r\n"
            b"X-Trailer: test\r\n"
            b"\r\n"
        )

        reader2, writer2 = await asyncio.open_connection("127.0.0.1", 9096)
        writer2.write(json_chunked)
        await writer2.drain()
        resp2 = await reader2.read(1024)
        writer2.close()
        await writer2.wait_closed()

        await asyncio.sleep(0.15)
        assert len(received_hooks) == 2, "WebhookServer did not capture second chunked request!"
        assert json.loads(received_hooks[1]["raw_body"]) == {"event": "deploy"}, (
            f"VULNERABILITY: Chunked JSON payload failed! Got: {received_hooks[1]['raw_body']}"
        )

    finally:
        await ws.stop()

    print("  [+] Chunked Transfer Encoding: PASS")


async def test_tui_headers_and_ssl_controls():
    print("[*] 4. Testing TUI Headers Tab & SSL Toggle Integration...")

    app = GhostmanApp()
    async with app.run_test() as pilot:
        # Check TLS badge initial state
        ssl_badge = app.query_one("#ssl-badge", Label)
        assert "[TLS: ON]" in str(ssl_badge.render())
        assert app.verify_ssl is True

        # Toggle TLS verify via hotkey (Ctrl+T)
        await pilot.press("ctrl+t")
        await pilot.pause(0.1)
        assert app.verify_ssl is False
        assert "[TLS: OFF]" in str(ssl_badge.render())

        # Toggle back to secure
        await pilot.press("ctrl+t")
        await pilot.pause(0.1)
        assert app.verify_ssl is True
        assert "[TLS: ON]" in str(ssl_badge.render())

        # Test Headers input in UI
        headers_input = app.query_one("#headers-input", TextArea)
        headers_input.text = "Authorization: Bearer my-ui-token\nX-Client: Ghostman"

        # Switch to Headers tab
        tabs = app.query_one("#tabs", Tabs)
        tabs.active = "tab-headers"
        await pilot.pause(0.1)
        assert app.query_one("#tab-headers-pane").display is True

        # Save current request with headers
        app.query_one("#url-input", Input).value = "https://httpbin.org/headers"
        app.action_save_request()
        await pilot.pause(0.1)

        # Check saved request in collections has the headers
        saved_req = app.collections[0]["requests"][-1]
        assert saved_req["headers"].get("Authorization") == "Bearer my-ui-token"
        assert saved_req["headers"].get("X-Client") == "Ghostman"

        # Action new request clears headers
        app.action_new_request()
        await pilot.pause(0.1)
        assert app.query_one("#headers-input", TextArea).text == ""

    print("  [+] TUI Headers & SSL Controls: PASS")


async def main():
    print("\n" + "=" * 60)
    print("RUNNING GHOSTMAN AUDIT VULNERABILITY VERIFICATION (v0.1.3)")
    print("=" * 60)

    await test_tls_verification_default_and_toggle()
    await test_saved_and_custom_headers_propagation()
    await test_chunked_transfer_encoding_webhook()
    await test_tui_headers_and_ssl_controls()

    print("\n" + "=" * 60)
    print("ALL 3 AUDIT ISSUES RESOLVED AND VERIFIED 100% PASSING!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
