import asyncio
import os
import sys
import json
import ssl
import tempfile
import datetime
import ipaddress
import httpx

try:
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
except ImportError:
    print("[!] Error: 'cryptography' is required to run test_vulnerabilities_fixed.py.")
    print("    Install test dependencies with: pip install -e .[dev]")
    sys.exit(1)

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


def generate_self_signed_cert_files():
    """Generate ephemeral self-signed SSL cert and key for offline HTTPS testing."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
        .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
            ]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    cert_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pem")
    cert_file.write(cert.public_bytes(serialization.Encoding.PEM))
    cert_file.close()

    key_file = tempfile.NamedTemporaryFile(delete=False, suffix=".key")
    key_file.write(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    key_file.close()

    return cert_file.name, key_file.name


async def test_tls_verification_default_and_toggle():
    print("[*] 1. Testing TLS Certificate Verification Default & Toggles (Local HTTPS)...")

    cert_path, key_path = generate_self_signed_cert_files()

    ssl_server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_server_ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)

    async def handle_https(reader, writer):
        await reader.read(1024)
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 2\r\nConnection: close\r\n\r\nOK")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handle_https, "127.0.0.1", 9099, ssl=ssl_server_ctx)

    try:
        net = NetworkEngine()
        assert net.verify_ssl is True, "VULNERABILITY: NetworkEngine did not default to verify_ssl=True!"

        # A) Standard request with verify_ssl=True MUST fail because self-signed cert is untrusted
        res = await net.execute_request("GET", "https://127.0.0.1:9099/")
        assert res["success"] is False, "VULNERABILITY: Self-signed certificate was accepted under verify_ssl=True!"
        error_text = (str(res.get("error", "")) + " " + str(res.get("body", ""))).lower()
        assert (
            "certificate_verify_failed" in error_text or
            "certificate verify failed" in error_text or
            "self-signed" in error_text or
            "verification failed" in error_text
        ), f"Expected SSL certificate verification error, got: {error_text}"

        # B) Explicitly insecure request with verify_ssl=False MUST succeed
        res_insecure = await net.execute_request("GET", "https://127.0.0.1:9099/", verify_ssl=False)
        assert res_insecure["success"] is True, f"Insecure request failed: {res_insecure.get('error')}"
        assert res_insecure["status_code"] == 200
        assert res_insecure["body"] == "OK"

        # C) Request with custom CA bundle pointing to the self-signed cert MUST succeed via ssl.SSLContext
        res_ca = await net.execute_request("GET", "https://127.0.0.1:9099/", verify_ssl=True, ca_bundle=cert_path)
        assert res_ca["success"] is True, f"Request with valid custom CA bundle failed: {res_ca.get('error')}"
        assert res_ca["status_code"] == 200
        assert res_ca["body"] == "OK"

    finally:
        server.close()
        await server.wait_closed()
        for p in (cert_path, key_path):
            try:
                os.remove(p)
            except Exception:
                pass

    print("  [+] TLS Certificate Verification: PASS")


async def test_saved_and_custom_headers_propagation():
    print("[*] 2. Testing Custom & Saved HTTP Headers Propagation...")

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

        header_text = "Authorization: Bearer secret\nContent-Type: application/xml\nUser-Agent: Custom"
        parsed = GhostmanApp.parse_headers_text(header_text)
        assert parsed["Authorization"] == "Bearer secret"
        assert parsed["Content-Type"] == "application/xml"
        assert parsed["User-Agent"] == "Custom"

        json_header_text = '{"Authorization": "Bearer token", "X-Key": "val"}'
        parsed_json = GhostmanApp.parse_headers_text(json_header_text)
        assert parsed_json["Authorization"] == "Bearer token"
        assert parsed_json["X-Key"] == "val"

        formatted = GhostmanApp.format_headers_text(parsed)
        re_parsed = GhostmanApp.parse_headers_text(formatted)
        assert re_parsed == parsed

    finally:
        await ws.stop()

    print("  [+] Custom & Saved Headers: PASS")


async def test_chunked_transfer_encoding_webhook():
    print("[*] 3. Testing Chunked Transfer Encoding Webhook Reception & Resource Limits...")

    received_hooks = []
    # Set small max_payload_size to test 413 guard
    ws = WebhookServer(
        port=9096,
        on_hook_received=lambda h: received_hooks.append(h),
        max_payload_size=1024,
        read_timeout=5.0
    )
    await ws.start()

    try:
        # A) Standard RFC 7230 Chunked Body
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

        # B) Chunked JSON with Chunk Extensions
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

        # C) Payload exceeding max_payload_size must receive 413 Payload Too Large
        oversized_http = (
            b"POST /oversized HTTP/1.1\r\n"
            b"Host: 127.0.0.1:9096\r\n"
            b"Content-Length: 5000\r\n"
            b"Connection: close\r\n"
            b"\r\n" + (b"X" * 5000)
        )
        reader3, writer3 = await asyncio.open_connection("127.0.0.1", 9096)
        writer3.write(oversized_http)
        await writer3.drain()
        resp3 = await reader3.read(1024)
        writer3.close()
        await writer3.wait_closed()
        assert b"413 Payload Too Large" in resp3, f"Expected 413, got: {resp3[:100]}"

        # D) Malformed chunk size (invalid hex) MUST return 400 Bad Request and NOT record hook
        malformed_size_http = (
            b"POST /malformed-size HTTP/1.1\r\n"
            b"Host: 127.0.0.1:9096\r\n"
            b"Transfer-Encoding: chunked\r\n"
            b"Connection: close\r\n"
            b"\r\n"
            b"ZZ_NOT_HEX\r\n"
            b"payload\r\n"
            b"0\r\n\r\n"
        )
        reader4, writer4 = await asyncio.open_connection("127.0.0.1", 9096)
        writer4.write(malformed_size_http)
        await writer4.drain()
        resp4 = await reader4.read(1024)
        writer4.close()
        await writer4.wait_closed()
        assert b"400 Bad Request" in resp4, f"Expected 400 Bad Request, got: {resp4[:100]}"
        await asyncio.sleep(0.1)
        assert len(received_hooks) == 2, "VULNERABILITY: Malformed chunk size was accepted into captured_hooks!"

        # E) Malformed trailing delimiter (missing/corrupted CRLF) MUST return 400 Bad Request
        malformed_crlf_http = (
            b"POST /bad-crlf HTTP/1.1\r\n"
            b"Host: 127.0.0.1:9096\r\n"
            b"Transfer-Encoding: chunked\r\n"
            b"Connection: close\r\n"
            b"\r\n"
            b"5\r\n"
            b"helloXXXX"
            b"0\r\n\r\n"
        )
        reader5, writer5 = await asyncio.open_connection("127.0.0.1", 9096)
        writer5.write(malformed_crlf_http)
        await writer5.drain()
        resp5 = await reader5.read(1024)
        writer5.close()
        await writer5.wait_closed()
        assert b"400 Bad Request" in resp5, f"Expected 400 Bad Request, got: {resp5[:100]}"
        await asyncio.sleep(0.1)
        assert len(received_hooks) == 2, "VULNERABILITY: Malformed chunk delimiter was accepted into captured_hooks!"

        # F) Premature EOF before terminal 0-size chunk MUST NOT record hook
        premature_eof_http = (
            b"POST /premature HTTP/1.1\r\n"
            b"Host: 127.0.0.1:9096\r\n"
            b"Transfer-Encoding: chunked\r\n"
            b"Connection: close\r\n"
            b"\r\n"
            b"5\r\n"
            b"hello\r\n"
        )
        reader6, writer6 = await asyncio.open_connection("127.0.0.1", 9096)
        writer6.write(premature_eof_http)
        await writer6.drain()
        writer6.close()
        await writer6.wait_closed()
        await asyncio.sleep(0.1)
        assert len(received_hooks) == 2, "VULNERABILITY: Incomplete chunked stream was accepted into captured_hooks!"

        # G) Enforce max_chunks limit
        ws_bounded = WebhookServer(port=9097, max_chunks=3, total_timeout=5.0)
        await ws_bounded.start()
        try:
            excess_chunks_http = (
                b"POST /excess HTTP/1.1\r\n"
                b"Host: 127.0.0.1:9097\r\n"
                b"Transfer-Encoding: chunked\r\n"
                b"Connection: close\r\n"
                b"\r\n"
                b"1\r\na\r\n"
                b"1\r\nb\r\n"
                b"1\r\nc\r\n"
                b"1\r\nd\r\n"
                b"0\r\n\r\n"
            )
            reader_ex, writer_ex = await asyncio.open_connection("127.0.0.1", 9097)
            writer_ex.write(excess_chunks_http)
            await writer_ex.drain()
            resp_ex = await reader_ex.read(1024)
            writer_ex.close()
            await writer_ex.wait_closed()
            assert b"413 Payload Too Large" in resp_ex, f"Expected 413, got: {resp_ex[:100]}"
            assert len(ws_bounded.captured_hooks) == 0
        finally:
            await ws_bounded.stop()

        # H) Enforce total_timeout (absolute request deadline)
        ws_timeout = WebhookServer(port=9094, total_timeout=0.3, read_timeout=2.0)
        await ws_timeout.start()
        try:
            reader_to, writer_to = await asyncio.open_connection("127.0.0.1", 9094)
            writer_to.write(b"POST /slowloris HTTP/1.1\r\nHost: 127.0.0.1:9094\r\n")
            await writer_to.drain()
            await asyncio.sleep(0.4)
            resp_to = await reader_to.read(1024)
            writer_to.close()
            await writer_to.wait_closed()
            assert b"408 Request Timeout" in resp_to or len(resp_to) == 0
            assert len(ws_timeout.captured_hooks) == 0
        finally:
            await ws_timeout.stop()

        # I) Premature EOF after zero chunk (before final terminating CRLF)
        premature_trailer_eof = (
            b"POST /trailer-eof HTTP/1.1\r\n"
            b"Host: 127.0.0.1:9096\r\n"
            b"Transfer-Encoding: chunked\r\n"
            b"Connection: close\r\n"
            b"\r\n"
            b"5\r\n"
            b"hello\r\n"
            b"0\r\n"
            # Closed abruptly without the final terminating \r\n
        )
        reader7, writer7 = await asyncio.open_connection("127.0.0.1", 9096)
        writer7.write(premature_trailer_eof)
        await writer7.drain()
        writer7.close()
        await writer7.wait_closed()
        await asyncio.sleep(0.1)
        assert len(received_hooks) == 2, "VULNERABILITY: Unterminated trailer EOF was accepted into captured_hooks!"

        # J) Trailer section timeout -> MUST respond 408 Request Timeout
        ws_trailer = WebhookServer(port=9093, read_timeout=0.3, total_timeout=5.0)
        await ws_trailer.start()
        try:
            reader_tr, writer_tr = await asyncio.open_connection("127.0.0.1", 9093)
            writer_tr.write(
                b"POST /trailer-to HTTP/1.1\r\n"
                b"Host: 127.0.0.1:9093\r\n"
                b"Transfer-Encoding: chunked\r\n"
                b"Connection: close\r\n"
                b"\r\n"
                b"0\r\n"
                # Stop sending, wait for trailer read_timeout to expire
            )
            await writer_tr.drain()
            await asyncio.sleep(0.5)
            resp_tr = await reader_tr.read(1024)
            writer_tr.close()
            await writer_tr.wait_closed()
            assert b"408 Request Timeout" in resp_tr, f"Expected 408 on trailer timeout, got: {resp_tr[:100]}"
            assert len(ws_trailer.captured_hooks) == 0
        finally:
            await ws_trailer.stop()

        # K) Bare LF delimiter (not CRLF) MUST be rejected with 400 Bad Request
        bare_lf_http = (
            b"POST /bare-lf HTTP/1.1\r\n"
            b"Host: 127.0.0.1:9096\r\n"
            b"Transfer-Encoding: chunked\r\n"
            b"Connection: close\r\n"
            b"\r\n"
            b"5\r\n"
            b"hello\n"  # Bare LF instead of \r\n
            b"0\r\n\r\n"
        )
        reader8, writer8 = await asyncio.open_connection("127.0.0.1", 9096)
        writer8.write(bare_lf_http)
        await writer8.drain()
        resp8 = await reader8.read(1024)
        writer8.close()
        await writer8.wait_closed()
        assert b"400 Bad Request" in resp8, f"Expected 400 for bare LF, got: {resp8[:100]}"
        await asyncio.sleep(0.1)
        assert len(received_hooks) == 2, "VULNERABILITY: Bare LF delimiter was accepted into captured_hooks!"

        # L) Unsupported Transfer-Encoding (gzip, deflate) MUST return 501 Not Implemented
        unsupported_te_http = (
            b"POST /unsupported-te HTTP/1.1\r\n"
            b"Host: 127.0.0.1:9096\r\n"
            b"Transfer-Encoding: gzip, chunked\r\n"
            b"Connection: close\r\n"
            b"\r\n"
            b"0\r\n\r\n"
        )
        reader9, writer9 = await asyncio.open_connection("127.0.0.1", 9096)
        writer9.write(unsupported_te_http)
        await writer9.drain()
        resp9 = await reader9.read(1024)
        writer9.close()
        await writer9.wait_closed()
        assert b"501 Not Implemented" in resp9, f"Expected 501 for unsupported Transfer-Encoding, got: {resp9[:100]}"
        await asyncio.sleep(0.1)
        assert len(received_hooks) == 2, "VULNERABILITY: Unsupported Transfer-Encoding was accepted into captured_hooks!"

    finally:
        await ws.stop()

    print("  [+] Chunked Transfer Encoding & Limits: PASS")


async def test_tui_headers_and_gui_state():
    print("[*] 4. Testing TUI Headers Tab & Integration...")

    app = GhostmanApp()
    async with app.run_test() as pilot:
        # Initial mount state: Tab Body is active and displayed, matching original clean GUI
        assert app.query_one("#tab-body-pane").display is True
        assert app.query_one("#tab-headers-pane").display is False
        assert app.query_one("#tab-response-pane").display is False
        assert app.network.verify_ssl is True

        # Header bar is clean with exact original title and subtitle
        assert app.query_one("#title-label", Label) is not None
        assert app.query_one("#subtitle-label", Label) is not None

        # Switch to Headers tab
        tabs = app.query_one("#tabs", Tabs)
        tabs.active = "tab-headers"
        await pilot.pause(0.1)
        assert app.query_one("#tab-headers-pane").display is True
        assert app.query_one("#tab-body-pane").display is False

        # Input headers into headers editor
        headers_input = app.query_one("#headers-input", TextArea)
        headers_input.text = "Authorization: Bearer my-ui-token\nX-Client: Ghostman"

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

    print("  [+] TUI Headers & GUI State: PASS")


async def main():
    print("\n" + "=" * 60)
    print("RUNNING GHOSTMAN AUDIT VULNERABILITY VERIFICATION (v0.1.7)")
    print("=" * 60)

    await test_tls_verification_default_and_toggle()
    await test_saved_and_custom_headers_propagation()
    await test_chunked_transfer_encoding_webhook()
    await test_tui_headers_and_gui_state()

    print("\n" + "=" * 60)
    print("ALL AUDIT ISSUES RESOLVED AND VERIFIED 100% PASSING!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
