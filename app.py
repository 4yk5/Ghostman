from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Footer, Input, Button, Select, Tabs, Tab, TextArea, ListView, ListItem, Label
)
from textual.binding import Binding

from network import NetworkEngine
from webhook_server import WebhookServer
from storage import StorageManager

import os
import json
from pathlib import Path

class GhostmanApp(App):
    DEFAULT_CSS = """
/* Theme & Global Layout */
Screen {
    background: #0b0e14;
    color: #e6edf3;
}

#header-bar {
    height: 3;
    background: #161b22;
    border-bottom: solid #00ff9f;
    padding: 0 1;
    align: left middle;
}

#title-label {
    text-style: bold;
    color: #00ff9f;
}

#subtitle-label {
    color: #8b949e;
    margin-left: 2;
    width: 1fr;
}

#ssl-badge {
    color: #3fb950;
    text-style: bold;
    margin-right: 1;
    padding: 0 1;
    background: #161b22;
    border: solid #238636;
}

#ssl-badge.insecure {
    color: #f85149;
    border: solid #da3633;
}

#main-container {
    height: 1fr;
}

/* Sidebar */
#sidebar {
    width: 32;
    background: #0d1117;
    border-right: solid #30363d;
    padding: 1;
}

#sidebar-header {
    height: 3;
    margin-bottom: 1;
    align: left middle;
}

#sidebar-title {
    text-style: bold;
    color: #58a6ff;
    width: 1fr;
}

#requests-list {
    height: 1fr;
    background: transparent;
}

/* Buttons */
Button, Button.-style-default, Button.-style-flat {
    border: none !important;
    border-top: none !important;
    border-bottom: none !important;
    border-left: none !important;
    border-right: none !important;
    height: 3;
    min-width: 8;
    content-align: center middle;
    text-style: bold;
}

#new-req-btn {
    width: 8;
    background: #21262d;
    color: #58a6ff;
}

#new-req-btn:hover {
    background: #30363d;
}

#send-btn {
    width: 12;
    background: #238636;
    color: #ffffff;
    margin-left: 1;
}

#send-btn:hover {
    background: #2ea043;
}

#save-btn {
    width: 10;
    background: #1f6feb;
    color: #ffffff;
    margin-left: 1;
}

#save-btn:hover {
    background: #388bfd;
}

/* Main Request Bar */
#content-area {
    width: 1fr;
    padding: 1;
}

#request-bar {
    height: 3;
    margin-bottom: 1;
    layout: horizontal;
}

Select {
    width: 14;
    margin-right: 1;
    border: none !important;
}

SelectCurrent {
    border: solid #30363d !important;
    border-top: solid #30363d !important;
    border-bottom: solid #30363d !important;
    border-left: solid #30363d !important;
    border-right: solid #30363d !important;
    height: 3;
    background: #161b22;
    color: #f0f6fc;
}

SelectCurrent:focus {
    border: solid #58a6ff !important;
}

/* Dropdown Menu */
SelectOverlay, OptionList {
    border: solid #30363d !important;
    background: #161b22;
}

SelectOverlay:focus, OptionList:focus {
    border: solid #58a6ff !important;
}

OptionList > .option-list--option-highlighted {
    background: #1f6feb !important;
    color: #ffffff !important;
}

Input, #url-input {
    width: 1fr;
    background: #161b22;
    border: solid #30363d !important;
    border-top: solid #30363d !important;
    border-bottom: solid #30363d !important;
    color: #f0f6fc;
    height: 3;
}

Input:focus, #url-input:focus {
    border: solid #58a6ff !important;
}

/* Tabs & Panes */
#tabs {
    margin-bottom: 1;
}

TextArea, TextArea:focus, #body-input, #body-input:focus, #headers-input, #headers-input:focus {
    height: 1fr;
    background: #161b22;
    border: solid #30363d !important;
    color: #79c0ff;
}

#tab-headers-pane {
    height: 1fr;
    background: #0d1117;
    padding: 0;
}

#tab-response-pane {
    height: 1fr;
    background: #0d1117;
    border: solid #30363d;
    padding: 1;
}

#response-area, #response-area:focus {
    height: 1fr;
    background: #0d1117;
    border: none !important;
    color: #e6edf3;
}

#metrics-bar {
    height: 1;
    margin-bottom: 1;
    color: #8b949e;
    text-style: bold;
}

#tab-webhook-pane {
    height: 1fr;
    background: #0d1117;
    padding: 1;
}

#webhook-status {
    height: 3;
    padding: 0 1;
    align: left middle;
    background: #161b22;
    border: solid #30363d;
    margin-bottom: 1;
}

#webhook-toggle-btn {
    width: 20;
    margin-left: 2;
    background: #21262d;
    color: #e6edf3;
}

#webhook-toggle-btn:hover {
    background: #30363d;
}

/* Footer */
#footer-bar {
    height: 1;
    background: #161b22;
    color: #8b949e;
    padding: 0 1;
}

"""
    ENABLE_COMMAND_PALETTE = False

    BINDINGS = [
        Binding("ctrl+s", "send_request", "Send Request", priority=True),
        Binding("ctrl+w", "toggle_webhook", "Toggle Webhook", priority=True),
        Binding("ctrl+t", "toggle_ssl", "Toggle TLS Verify", priority=True),
        Binding("ctrl+n", "new_request", "New Request", priority=True),
        Binding("ctrl+k", "save_request", "Save Request", priority=True),
        Binding("ctrl+q", "quit", "Quit", priority=True)
    ]

    METHODS = [
        ("GET", "GET"),
        ("POST", "POST"),
        ("PUT", "PUT"),
        ("DELETE", "DELETE"),
        ("PATCH", "PATCH")
    ]

    def __init__(self):
        super().__init__()
        self.verify_ssl: bool = True
        self.network = NetworkEngine(verify_ssl=True)
        self.storage = StorageManager()
        self.collections = self.storage.load_collections()
        self.webhook_server = WebhookServer(
            host="127.0.0.1",
            port=9090,
            on_hook_received=self.handle_incoming_webhook
        )

    def compose(self) -> ComposeResult:
        with Horizontal(id="header-bar"):
            yield Label("[GHOSTMAN]", id="title-label")
            yield Label("Terminal API & Webhook Studio (Local-First)", id="subtitle-label")
            yield Label("[TLS: ON]", id="ssl-badge")

        with Horizontal(id="main-container"):
            with Vertical(id="sidebar"):
                with Horizontal(id="sidebar-header"):
                    yield Label("COLLECTIONS", id="sidebar-title")
                    yield Button("+ NEW", id="new-req-btn")
                yield ListView(id="requests-list")

            with Vertical(id="content-area"):
                with Horizontal(id="request-bar"):
                    yield Select(self.METHODS, value="GET", allow_blank=False, id="method-select")
                    yield Input(placeholder="Request URL (e.g. https://api.github.com)...", id="url-input")
                    yield Button("SEND", id="send-btn")
                    yield Button("SAVE", id="save-btn")

                yield Tabs(
                    Tab("Headers", id="tab-headers"),
                    Tab("Body & Payload", id="tab-body"),
                    Tab("Response", id="tab-response"),
                    Tab("Live Webhooks", id="tab-webhook"),
                    id="tabs"
                )

                with Vertical(id="tab-headers-pane"):
                    yield TextArea(
                        id="headers-input",
                        language="yaml",
                        text=""
                    )

                with Vertical(id="tab-body-pane"):
                    yield TextArea(id="body-input", language="json", text='{\n  "hello": "world"\n}')

                with Vertical(id="tab-response-pane"):
                    yield Label("Status: Idle", id="metrics-bar")
                    yield TextArea(id="response-area", read_only=True, language="json", text="")

                with Vertical(id="tab-webhook-pane"):
                    with Horizontal(id="webhook-status"):
                        yield Label("Webhook Receiver: [OFFLINE] (Port 9090)", id="webhook-status-label")
                        yield Button("START RECEIVER", id="webhook-toggle-btn")
                    yield Label("Send requests to http://127.0.0.1:9090 to inspect payloads live:")
                    yield ListView(id="webhook-list")

        yield Footer()

    async def on_mount(self):
        self.populate_sidebar()
        self.query_one("#tab-headers-pane").display = False
        self.query_one("#tab-response-pane").display = False
        self.query_one("#tab-webhook-pane").display = False
        self.query_one("#url-input").value = "https://jsonplaceholder.typicode.com/posts/1"

    async def on_unmount(self):
        try:
            if self.webhook_server and self.webhook_server.is_running:
                await self.webhook_server.stop()
        except Exception:
            pass

    @staticmethod
    def parse_headers_text(raw: str) -> dict:
        """Parse headers from either Key: Value lines or a JSON object."""
        if not raw or not raw.strip():
            return {}
        text = raw.strip()
        if text.startswith("{") and text.endswith("}"):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return {str(k): str(v) for k, v in parsed.items()}
            except Exception:
                pass
        headers = {}
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "//")):
                continue
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip()] = v.strip()
        return headers

    @staticmethod
    def format_headers_text(headers: dict) -> str:
        """Format a headers dictionary into standard Key: Value lines."""
        if not headers or not isinstance(headers, dict):
            return ""
        return "\n".join(f"{k}: {v}" for k, v in headers.items())

    def populate_sidebar(self):
        try:
            list_view = self.query_one("#requests-list", ListView)
            list_view.clear()
            if not isinstance(self.collections, list):
                return
            for col in self.collections:
                if not isinstance(col, dict):
                    continue
                for req in col.get("requests", []):
                    if not isinstance(req, dict):
                        continue
                    method = req.get("method", "GET").upper()
                    name = req.get("name", "Request")
                    item = ListItem(Label(f"[{method}] {name}"))
                    item.req_data = req
                    list_view.append(item)
        except Exception as e:
            self.notify(f"Error updating sidebar: {e}", severity="error")

    def on_list_view_selected(self, event: ListView.Selected):
        item = event.item
        if not item:
            return
        if hasattr(item, "req_data"):
            req = item.req_data
            method = req.get("method", "GET").upper()
            if method in [m[0] for m in self.METHODS]:
                self.query_one("#method-select", Select).value = method
            self.query_one("#url-input", Input).value = req.get("url", "")
            self.query_one("#body-input", TextArea).text = req.get("body", "") or ""

            # Load saved headers into the headers editor
            req_headers = req.get("headers", {})
            self.query_one("#headers-input", TextArea).text = self.format_headers_text(req_headers)

            self.notify(f"Selected: {req.get('name')}", timeout=2)
        elif hasattr(item, "hook_data"):
            hook = item.hook_data
            h_method = hook.get("method", "GET").upper()
            if h_method in [m[0] for m in self.METHODS]:
                self.query_one("#method-select", Select).value = h_method
            self.query_one("#body-input", TextArea).text = hook.get("raw_body", "") or ""

            # Load captured hook headers
            hook_headers = hook.get("headers", {})
            self.query_one("#headers-input", TextArea).text = self.format_headers_text(hook_headers)

            self.query_one("#tabs", Tabs).active = "tab-body"
            self.notify(f"Loaded hook payload ({hook.get('path', '/')})", timeout=2)

    def on_tabs_tab_activated(self, event: Tabs.TabActivated):
        tab_id = event.tab.id
        self.query_one("#tab-headers-pane").display = (tab_id == "tab-headers")
        self.query_one("#tab-body-pane").display = (tab_id == "tab-body")
        self.query_one("#tab-response-pane").display = (tab_id == "tab-response")
        self.query_one("#tab-webhook-pane").display = (tab_id == "tab-webhook")

    async def action_send_request(self):
        await self.send_http_request()

    def action_save_request(self):
        self.save_current_request()

    def action_new_request(self):
        self.query_one("#method-select", Select).value = "GET"
        self.query_one("#url-input", Input).value = ""
        self.query_one("#headers-input", TextArea).text = ""
        self.query_one("#body-input", TextArea).text = ""
        self.query_one("#tabs", Tabs).active = "tab-body"
        self.query_one("#url-input", Input).focus()
        self.notify("New request ready")

    def action_toggle_ssl(self):
        """Toggle SSL/TLS Certificate Verification (Ctrl+T)"""
        self.verify_ssl = not self.verify_ssl
        badge = self.query_one("#ssl-badge", Label)
        if self.verify_ssl:
            badge.update("[TLS: ON]")
            badge.remove_class("insecure")
            self.notify("TLS Certificate Verification ENABLED (Secure)", timeout=3)
        else:
            badge.update("[TLS: OFF]")
            badge.add_class("insecure")
            self.notify("TLS Certificate Verification DISABLED (Insecure)", severity="warning", timeout=3)

    async def on_button_pressed(self, event: Button.Pressed):
        btn_id = event.button.id
        if btn_id == "send-btn":
            await self.send_http_request()
        elif btn_id == "save-btn":
            self.save_current_request()
        elif btn_id == "new-req-btn":
            self.action_new_request()
        elif btn_id == "webhook-toggle-btn":
            await self.action_toggle_webhook()

    def save_current_request(self):
        try:
            url = self.query_one("#url-input", Input).value.strip()
            if not url:
                self.notify("Cannot save request without URL", severity="warning")
                return
            method = self.query_one("#method-select", Select).value
            body = self.query_one("#body-input", TextArea).text

            raw_headers = self.query_one("#headers-input", TextArea).text
            req_headers = self.parse_headers_text(raw_headers)

            # Smart Content-Type detection if not explicitly set
            if body and not any(k.lower() == "content-type" for k in req_headers):
                try:
                    json.loads(body)
                    req_headers["Content-Type"] = "application/json"
                except Exception:
                    if body.strip().startswith("<") and body.strip().endswith(">"):
                        req_headers["Content-Type"] = "application/xml"
                    else:
                        req_headers["Content-Type"] = "text/plain"

            path_part = url.split("://")[-1].split("?")[0].strip("/")
            name = path_part.split("/")[-1] if "/" in path_part else path_part
            name = name or "Endpoint"

            new_req = {
                "name": f"{method} {name[:18]}",
                "method": method,
                "url": url,
                "headers": req_headers,
                "body": body
            }

            if not self.collections or not isinstance(self.collections, list):
                self.collections = [{"name": "My Collection", "requests": []}]
            if "requests" not in self.collections[0] or not isinstance(self.collections[0]["requests"], list):
                self.collections[0]["requests"] = []
            self.collections[0]["requests"].append(new_req)
            self.storage.save_collections(self.collections)
            self.populate_sidebar()
            self.notify(f"Saved: {new_req['name']}", timeout=2)
        except Exception as e:
            self.notify(f"Error saving request: {e}", severity="error")

    async def send_http_request(self):
        try:
            method = self.query_one("#method-select", Select).value
            url = self.query_one("#url-input", Input).value.strip()
            body = self.query_one("#body-input", TextArea).text

            raw_headers = self.query_one("#headers-input", TextArea).text
            req_headers = self.parse_headers_text(raw_headers)

            if not url:
                self.notify("URL cannot be empty", severity="error")
                return

            if not url.startswith("http://") and not url.startswith("https://"):
                url = "https://" + url
                self.query_one("#url-input", Input).value = url

            self.query_one("#tabs", Tabs).active = "tab-response"
            metrics = self.query_one("#metrics-bar", Label)
            response_box = self.query_one("#response-area", TextArea)

            metrics.update(f"Sending {method} to {url}...")
            response_box.text = "Waiting for response..."

            req_body = body if method in ["POST", "PUT", "PATCH", "DELETE"] else None

            # Execute with full headers and TLS verification mode
            res = await self.network.execute_request(
                method=method,
                url=url,
                headers=req_headers,
                body=req_body,
                verify_ssl=self.verify_ssl
            )

            if res["success"]:
                code = res["status_code"]
                color = "green" if code < 400 else "red"
                reason = res.get('reason') or ('OK' if code == 200 else '')
                metrics.update(
                    f"[{color}]{code} {reason}[/] | {res['elapsed_ms']}ms | {res['size_bytes']} bytes"
                )
                response_box.text = res["body"]
            else:
                metrics.update(f"[red]Failed[/] | {res['elapsed_ms']}ms")
                response_box.text = res["body"]
        except Exception as e:
            self.notify(f"Request error: {e}", severity="error")

    async def action_toggle_webhook(self):
        btn = self.query_one("#webhook-toggle-btn", Button)
        lbl = self.query_one("#webhook-status-label", Label)

        if not self.webhook_server.is_running:
            try:
                await self.webhook_server.start()
                lbl.update("[green][ONLINE][/] (Listening on http://127.0.0.1:9090)")
                btn.label = "STOP RECEIVER"
                btn.variant = "error"
                self.notify("Webhook listener started on :9090")
            except Exception as e:
                self.notify(f"Could not bind port 9090: {e}", severity="error")
        else:
            try:
                await self.webhook_server.stop()
            except Exception:
                pass
            lbl.update("Webhook Receiver: [OFFLINE] (Port 9090)")
            btn.label = "START RECEIVER"
            btn.variant = "default"
            self.notify("Webhook listener stopped")

    def handle_incoming_webhook(self, hook: dict):
        try:
            self.call_from_thread(self._add_webhook_to_ui, hook)
        except RuntimeError:
            self._add_webhook_to_ui(hook)

    def _add_webhook_to_ui(self, hook: dict):
        try:
            list_view = self.query_one("#webhook-list", ListView)
            label_text = f"[{hook['timestamp']}] {hook['method']} {hook['path']} ({len(hook.get('raw_body', ''))}B)"
            item = ListItem(Label(f"[cyan]{label_text}[/] -> {hook.get('body', '')[:40]}..."))
            item.hook_data = hook
            list_view.append(item)
            self.notify(f"Hook received: {hook['path']}", timeout=2)
        except Exception:
            pass
