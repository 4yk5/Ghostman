"""
Full feature verification for Ghostman.
Tests every tab, every button, environment management, variable substitution,
keyboard shortcuts, and UI state transitions.
"""
import asyncio
import os
import sys
import json
import shutil
import tempfile

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
from textual.widgets import Input, TextArea, Select, ListView, Tabs, Label, Button
import httpx


async def test_storage_and_environments():
    print("[*] Testing Storage & Environment persistence...")

    tmp = tempfile.mkdtemp()
    try:
        sm = StorageManager(workspace_path=tmp)

        # Collections load correctly
        cols = sm.load_collections()
        assert isinstance(cols, list) and len(cols) > 0, "Default collections missing"

        # Save and reload collections
        sm.save_collections(cols)
        reloaded = sm.load_collections()
        assert reloaded == cols, "Collections round-trip failed"

        # Environments load with defaults
        envs = sm.load_environments()
        assert isinstance(envs, dict), "Environments not a dict"
        assert "active" in envs, "No active key in environments"
        assert "environments" in envs, "No environments list"
        assert len(envs["environments"]) > 0, "Empty environments list"
        assert envs["environments"][0]["name"] == "Default", "First env should be Default"

        # Save and reload environments
        envs["environments"].append({"name": "Staging", "variables": {"host": "staging.example.com"}})
        envs["active"] = "Staging"
        sm.save_environments(envs)

        reloaded_env = sm.load_environments()
        assert reloaded_env["active"] == "Staging", "Active env not persisted"
        assert len(reloaded_env["environments"]) == 2, "Second env not saved"
        assert reloaded_env["environments"][1]["variables"]["host"] == "staging.example.com", "Variables not persisted"

        print("  [+] Storage & Environments: PASS")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


async def test_variable_substitution():
    print("[*] Testing variable substitution engine...")

    sub = GhostmanApp.substitute_variables

    # Basic substitution
    assert sub("{{host}}/api", {"host": "example.com"}) == "example.com/api"

    # Multiple variables
    assert sub("{{proto}}://{{host}}:{{port}}", {"proto": "https", "host": "api.dev", "port": "8080"}) == "https://api.dev:8080"

    # Unknown variable left as-is
    assert sub("{{known}}/{{unknown}}", {"known": "val"}) == "val/{{unknown}}"

    # Whitespace in key stripped
    assert sub("{{ host }}", {"host": "example.com"}) == "example.com"

    # Empty inputs
    assert sub("", {"host": "x"}) == ""
    assert sub(None, {"host": "x"}) == ""
    assert sub("no vars", {}) == "no vars"
    assert sub("no vars", None) == "no vars"

    # No double-replacement
    assert sub("{{a}}", {"a": "{{b}}", "b": "FAIL"}) == "{{b}}"

    print("  [+] Variable Substitution: PASS")


async def test_env_text_parsing():
    print("[*] Testing environment text parsing...")

    parse = GhostmanApp._parse_env_text
    fmt = GhostmanApp._format_env_text

    # Round-trip
    variables = {"base_url": "https://api.dev", "token": "abc123"}
    text = fmt(variables)
    parsed = parse(text)
    assert parsed == variables, f"Round-trip failed: {parsed}"

    # Comments and blank lines skipped
    text_with_comments = "# This is a comment\nhost = example.com\n\n# Another comment\nport = 8080"
    parsed = parse(text_with_comments)
    assert parsed == {"host": "example.com", "port": "8080"}, f"Comment parsing failed: {parsed}"

    # Empty key ignored
    parsed = parse(" = value")
    assert parsed == {}, "Empty key should be ignored"

    # Value with = sign
    parsed = parse("formula = a=b+c")
    assert parsed == {"formula": "a=b+c"}, f"Value with = failed: {parsed}"

    # Empty input
    assert parse("") == {}
    assert parse(None) == {}
    assert fmt({}) == ""

    print("  [+] Env Text Parsing: PASS")


async def test_header_parsing():
    print("[*] Testing header parsing...")

    parse = GhostmanApp.parse_headers_text
    fmt = GhostmanApp.format_headers_text

    # Key: Value format
    headers = parse("Content-Type: application/json\nAuthorization: Bearer abc")
    assert headers == {"Content-Type": "application/json", "Authorization": "Bearer abc"}

    # JSON format
    headers = parse('{"X-Custom": "value", "Accept": "text/html"}')
    assert headers == {"X-Custom": "value", "Accept": "text/html"}

    # Comments and blank lines
    headers = parse("# comment\nHost: example.com\n\n// another\nAccept: */*")
    assert headers == {"Host": "example.com", "Accept": "*/*"}

    # Empty
    assert parse("") == {}
    assert parse(None) == {}
    assert fmt({}) == ""
    assert fmt(None) == ""

    # Round-trip
    original = {"Content-Type": "application/json", "X-Token": "abc"}
    text = fmt(original)
    parsed_back = parse(text)
    assert parsed_back == original, "Header round-trip failed"

    print("  [+] Header Parsing: PASS")


async def test_tui_tabs_and_layout():
    print("[*] Testing TUI tab switching and layout...")

    app = GhostmanApp()
    async with app.run_test() as pilot:
        # Initial state: only body pane visible
        assert app.query_one("#tab-body-pane").display is True, "Body pane should be visible on start"
        assert app.query_one("#tab-headers-pane").display is False, "Headers pane should be hidden"
        assert app.query_one("#tab-response-pane").display is False, "Response pane should be hidden"
        assert app.query_one("#tab-webhook-pane").display is False, "Webhook pane should be hidden"
        assert app.query_one("#tab-env-pane").display is False, "Env pane should be hidden"

        # Switch to Headers tab
        tabs = app.query_one("#tabs", Tabs)
        tabs.active = "tab-headers"
        await pilot.pause(0.1)
        assert app.query_one("#tab-headers-pane").display is True, "Headers pane should show"
        assert app.query_one("#tab-body-pane").display is False, "Body pane should hide"

        # Switch to Response tab
        tabs.active = "tab-response"
        await pilot.pause(0.1)
        assert app.query_one("#tab-response-pane").display is True, "Response pane should show"
        assert app.query_one("#tab-headers-pane").display is False, "Headers pane should hide"

        # Switch to Webhook tab
        tabs.active = "tab-webhook"
        await pilot.pause(0.1)
        assert app.query_one("#tab-webhook-pane").display is True, "Webhook pane should show"
        assert app.query_one("#tab-response-pane").display is False, "Response pane should hide"

        # Switch to Environments tab
        tabs.active = "tab-env"
        await pilot.pause(0.1)
        assert app.query_one("#tab-env-pane").display is True, "Env pane should show"
        assert app.query_one("#tab-webhook-pane").display is False, "Webhook pane should hide"

        # Switch back to Body tab
        tabs.active = "tab-body"
        await pilot.pause(0.1)
        assert app.query_one("#tab-body-pane").display is True, "Body pane should show again"
        assert app.query_one("#tab-env-pane").display is False, "Env pane should hide"

        print("  [+] Tab Switching: PASS")

        # Verify all UI elements exist
        app.query_one("#title-label", Label)
        app.query_one("#subtitle-label", Label)
        app.query_one("#env-indicator", Label)
        app.query_one("#method-select", Select)
        app.query_one("#url-input", Input)
        app.query_one("#send-btn", Button)
        app.query_one("#save-btn", Button)
        app.query_one("#new-req-btn", Button)
        app.query_one("#body-input", TextArea)
        app.query_one("#headers-input", TextArea)
        app.query_one("#response-area", TextArea)
        app.query_one("#webhook-toggle-btn", Button)
        app.query_one("#webhook-list", ListView)
        app.query_one("#env-select", Select)
        app.query_one("#env-name-input", Input)
        app.query_one("#env-editor", TextArea)
        app.query_one("#env-new-btn", Button)
        app.query_one("#env-del-btn", Button)
        app.query_one("#env-save-btn", Button)
        app.query_one("#requests-list", ListView)
        app.query_one("#metrics-bar", Label)

        print("  [+] All UI Elements Present: PASS")


async def test_tui_new_request():
    print("[*] Testing new request action...")

    app = GhostmanApp()
    async with app.run_test() as pilot:
        # Set some values
        app.query_one("#url-input", Input).value = "https://example.com"
        app.query_one("#body-input", TextArea).text = '{"test": true}'
        app.query_one("#method-select", Select).value = "POST"

        # Press Ctrl+N
        await pilot.press("ctrl+n")
        await pilot.pause(0.1)

        assert app.query_one("#url-input", Input).value == "", "URL should be cleared"
        assert app.query_one("#body-input", TextArea).text == "", "Body should be cleared"
        assert app.query_one("#method-select", Select).value == "GET", "Method should reset to GET"
        assert app.query_one("#headers-input", TextArea).text == "", "Headers should be cleared"

        print("  [+] New Request: PASS")


async def test_tui_save_request():
    print("[*] Testing save request...")

    app = GhostmanApp()
    async with app.run_test() as pilot:
        initial_count = len(app.query_one("#requests-list", ListView).children)

        app.query_one("#url-input", Input).value = "https://httpbin.org/get"
        app.query_one("#method-select", Select).value = "GET"

        save_btn = app.query_one("#save-btn", Button)
        await pilot.click(save_btn)
        await pilot.pause(0.2)

        new_count = len(app.query_one("#requests-list", ListView).children)
        assert new_count == initial_count + 1, f"Sidebar should have one more item ({initial_count} -> {new_count})"

        print("  [+] Save Request: PASS")


async def test_tui_webhook_toggle():
    print("[*] Testing webhook toggle...")

    app = GhostmanApp()
    async with app.run_test() as pilot:
        assert not app.webhook_server.is_running, "Webhook should start offline"

        # Start via Ctrl+W
        await pilot.press("ctrl+w")
        await pilot.pause(0.3)
        assert app.webhook_server.is_running, "Webhook should be running after Ctrl+W"

        # Stop via Ctrl+W
        await pilot.press("ctrl+w")
        await pilot.pause(0.3)
        assert not app.webhook_server.is_running, "Webhook should stop after second Ctrl+W"

        print("  [+] Webhook Toggle: PASS")


async def test_tui_ssl_toggle():
    print("[*] Testing SSL toggle...")

    app = GhostmanApp()
    async with app.run_test() as pilot:
        assert app.verify_ssl is True, "SSL should be on by default"

        await pilot.press("ctrl+t")
        await pilot.pause(0.1)
        assert app.verify_ssl is False, "SSL should toggle off"

        await pilot.press("ctrl+t")
        await pilot.pause(0.1)
        assert app.verify_ssl is True, "SSL should toggle back on"

        print("  [+] SSL Toggle: PASS")


async def test_tui_environment_management():
    print("[*] Testing environment management in TUI...")

    app = GhostmanApp()
    async with app.run_test() as pilot:
        # Check env state is initialized
        assert app._active_env is not None, "Active env should be set"
        assert len(app.env_data["environments"]) > 0, "Should have at least one environment"

        # Switch to env tab
        tabs = app.query_one("#tabs", Tabs)
        tabs.active = "tab-env"
        await pilot.pause(0.1)

        # Verify env editor is loaded with the active env
        env_name = app.query_one("#env-name-input", Input).value
        assert env_name == app._active_env, f"Editor should show active env '{app._active_env}', got '{env_name}'"
        initial_env = app._active_env
        initial_count = len(app.env_data["environments"])

        # Create new environment via method call
        app._create_new_env()
        await pilot.pause(0.2)

        new_name = app.query_one("#env-name-input", Input).value
        assert "New Environment" in new_name, f"New env should be created, got '{new_name}'"
        assert app._active_env == new_name, "Active env should update"

        # Set variables in editor
        editor = app.query_one("#env-editor", TextArea)
        editor.text = "api_host = staging.example.com\napi_key = test-key-123"
        await pilot.pause(0.1)

        # Save environment via method call
        app._save_current_env()
        await pilot.pause(0.2)

        # Verify variables persisted
        saved_vars = app._get_active_variables()
        assert saved_vars.get("api_host") == "staging.example.com", f"api_host not saved: {saved_vars}"
        assert saved_vars.get("api_key") == "test-key-123", f"api_key not saved: {saved_vars}"

        # Cycle env with Ctrl+E
        env_count = len(app.env_data["environments"])
        current_before_cycle = app._active_env
        await pilot.press("ctrl+e")
        await pilot.pause(0.2)
        assert app._active_env != current_before_cycle, f"Should cycle to a different env, still on '{app._active_env}'"

        # Cycle through all envs to get back to start
        for _ in range(env_count - 1):
            await pilot.press("ctrl+e")
            await pilot.pause(0.2)
        assert app._active_env == current_before_cycle, f"Should cycle back to '{current_before_cycle}' after full rotation, got '{app._active_env}'"

        # Delete the created environment
        app._delete_current_env()
        await pilot.pause(0.2)
        assert len(app.env_data["environments"]) == initial_count, "Should be back to initial env count"

        # Try to delete until one remains, then verify it's protected
        while len(app.env_data["environments"]) > 1:
            app._delete_current_env()
            await pilot.pause(0.1)
        app._delete_current_env()
        await pilot.pause(0.1)
        assert len(app.env_data["environments"]) == 1, "Cannot delete last environment"

        print("  [+] Environment Management: PASS")


async def test_tui_env_substitution_in_request():
    print("[*] Testing variable substitution in HTTP requests...")

    app = GhostmanApp()
    async with app.run_test() as pilot:
        # Set up an environment with variables
        for env in app.env_data["environments"]:
            if env["name"] == app._active_env:
                env["variables"] = {
                    "base": "https://jsonplaceholder.typicode.com",
                    "post_id": "1"
                }
                break
        app.storage.save_environments(app.env_data)

        # Use variables in URL
        app.query_one("#url-input", Input).value = "{{base}}/posts/{{post_id}}"
        await pilot.press("ctrl+s")
        await pilot.pause(2.0)

        # Check response loaded
        response_text = app.query_one("#response-area", TextArea).text
        assert "userId" in response_text, f"Response should contain API data, got: {response_text[:100]}"

        # URL template should be preserved (not overwritten with resolved URL)
        url_value = app.query_one("#url-input", Input).value
        assert "{{base}}" in url_value, f"URL template should be preserved, got: {url_value}"

        print("  [+] Env Substitution in Requests: PASS")


async def test_send_request():
    print("[*] Testing HTTP request execution...")

    app = GhostmanApp()
    async with app.run_test() as pilot:
        app.query_one("#url-input", Input).value = "https://jsonplaceholder.typicode.com/posts/1"
        await pilot.press("ctrl+s")
        await pilot.pause(2.0)

        response = app.query_one("#response-area", TextArea).text
        assert response != "Waiting for response...", "Response should have loaded"

        response = app.query_one("#response-area", TextArea).text
        assert "userId" in response, "Response body should have JSON data"
        assert app.query_one("#tab-response-pane").display is True, "Response tab should be visible"

        print("  [+] HTTP Request: PASS")


async def test_webhook_capture():
    print("[*] Testing webhook capture...")

    app = GhostmanApp()
    async with app.run_test() as pilot:
        await pilot.press("ctrl+w")
        await pilot.pause(0.3)
        assert app.webhook_server.is_running

        async with httpx.AsyncClient() as c:
            resp = await c.post(
                "http://127.0.0.1:9090/test-hook",
                json={"event": "test", "value": 42}
            )
            assert resp.status_code == 200, f"Webhook should respond 200, got {resp.status_code}"

        await pilot.pause(0.5)
        assert len(app.webhook_server.captured_hooks) == 1, "Should capture one hook"

        hook = app.webhook_server.captured_hooks[0]
        assert hook["method"] == "POST", "Method should be POST"
        assert hook["path"] == "/test-hook", "Path should be /test-hook"
        assert "42" in hook["body"], "Body should contain the value"

        await pilot.press("ctrl+w")
        await pilot.pause(0.3)
        assert not app.webhook_server.is_running

        print("  [+] Webhook Capture: PASS")


async def test_sidebar_selection():
    print("[*] Testing sidebar request selection...")

    app = GhostmanApp()
    async with app.run_test() as pilot:
        list_view = app.query_one("#requests-list", ListView)
        assert len(list_view.children) > 0, "Sidebar should have default requests"

        # Select first item
        list_view.index = 0
        await pilot.pause(0.1)

        print("  [+] Sidebar Selection: PASS")


async def test_network_engine():
    print("[*] Testing network engine directly...")

    net = NetworkEngine()

    # Successful GET
    r = await net.execute_request("GET", "https://jsonplaceholder.typicode.com/posts/1")
    assert r["success"] and r["status_code"] == 200, f"GET failed: {r}"
    assert r["is_json"], "Should detect JSON"
    assert r["size_bytes"] > 0, "Should have content"
    assert r["elapsed_ms"] > 0, "Should measure time"

    # POST with body
    r = await net.execute_request("POST", "https://jsonplaceholder.typicode.com/posts", body='{"title":"test"}')
    assert r["success"] and r["status_code"] == 201, f"POST failed: {r}"

    # Invalid URL
    r = await net.execute_request("GET", "not-a-url")
    assert not r["success"], "Invalid URL should fail"

    # SSL verification flag
    net2 = NetworkEngine(verify_ssl=False)
    r = await net2.execute_request("GET", "https://jsonplaceholder.typicode.com/posts/1")
    assert r["success"], "Request with verify_ssl=False should still work"

    print("  [+] Network Engine: PASS")


async def run_all():
    print("=" * 60)
    print("Ghostman Full Feature Verification")
    print("=" * 60)

    await test_storage_and_environments()
    await test_variable_substitution()
    await test_env_text_parsing()
    await test_header_parsing()
    await test_network_engine()
    await test_tui_tabs_and_layout()
    await test_tui_new_request()
    await test_tui_save_request()
    await test_tui_webhook_toggle()
    await test_tui_ssl_toggle()
    await test_tui_environment_management()
    await test_send_request()
    await test_tui_env_substitution_in_request()
    await test_webhook_capture()
    await test_sidebar_selection()

    print()
    print("=" * 60)
    print("All feature verification tests passed.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_all())
