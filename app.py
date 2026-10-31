from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Footer, Input, Button, Select, Tabs, Tab, TextArea, ListView, ListItem, Label
)
from textual.binding import Binding

from network import NetworkEngine
from webhook_server import WebhookServer
from storage import StorageManager

class GhostmanApp(App):
    CSS_PATH = "styles.tcss"
    BINDINGS = [
        Binding("ctrl+s", "send_request", "Send Request", priority=True),
        Binding("ctrl+w", "toggle_webhook", "Toggle Webhook Server"),
        Binding("ctrl+n", "new_request", "New Request"),
        Binding("ctrl+q", "quit", "Quit")
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
        self.network = NetworkEngine()
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
                    Tab("Body & Payload", id="tab-body"),
                    Tab("Response", id="tab-response"),
                    Tab("Live Webhooks", id="tab-webhook"),
                    id="tabs"
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
        self.query_one("#tab-response-pane").display = False
        self.query_one("#tab-webhook-pane").display = False
        self.query_one("#url-input").value = "https://jsonplaceholder.typicode.com/posts/1"

    async def on_unmount(self):
        if self.webhook_server.is_running:
            await self.webhook_server.stop()

    def populate_sidebar(self):
        list_view = self.query_one("#requests-list", ListView)
        list_view.clear()
        idx = 0
        for col in self.collections:
            for req in col.get("requests", []):
                method = req.get("method", "GET")
                name = req.get("name", "Request")
                item = ListItem(Label(f"[{method}] {name}"), id=f"req_{idx}")
                item.req_data = req
                list_view.append(item)
                idx += 1

    def on_list_view_selected(self, event: ListView.Selected):
        item = event.item
        if hasattr(item, "req_data"):
            req = item.req_data
            method = req.get("method", "GET")
            if method in [m[0] for m in self.METHODS]:
                self.query_one("#method-select", Select).value = method
            self.query_one("#url-input", Input).value = req.get("url", "")
            self.query_one("#body-input", TextArea).text = req.get("body", "") or ""
            self.notify(f"Selected: {req.get('name')}", timeout=2)

    def on_tabs_tab_activated(self, event: Tabs.TabActivated):
        tab_id = event.tab.id
        self.query_one("#tab-body-pane").display = (tab_id == "tab-body")
        self.query_one("#tab-response-pane").display = (tab_id == "tab-response")
        self.query_one("#tab-webhook-pane").display = (tab_id == "tab-webhook")

    async def action_send_request(self):
        await self.send_http_request()

    def action_new_request(self):
        self.query_one("#method-select", Select).value = "GET"
        self.query_one("#url-input", Input).value = ""
        self.query_one("#body-input", TextArea).text = ""
        self.query_one("#tabs", Tabs).active = "tab-body"
        self.query_one("#url-input", Input).focus()
        self.notify("New request ready")

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
        url = self.query_one("#url-input", Input).value.strip()
        if not url:
            self.notify("Cannot save request without URL", severity="warning")
            return
        method = self.query_one("#method-select", Select).value
        body = self.query_one("#body-input", TextArea).text

        path_part = url.split("://")[-1].split("?")[0].strip("/")
        name = path_part.split("/")[-1] if "/" in path_part else path_part
        name = name or "Endpoint"

        new_req = {
            "name": f"{method} {name[:18]}",
            "method": method,
            "url": url,
            "headers": {"Content-Type": "application/json"} if body else {},
            "body": body
        }

        if not self.collections:
            self.collections = [{"name": "My Collection", "requests": []}]
        self.collections[0]["requests"].append(new_req)
        self.storage.save_collections(self.collections)
        self.populate_sidebar()
        self.notify(f"Saved: {new_req['name']}", timeout=2)

    async def send_http_request(self):
        method = self.query_one("#method-select", Select).value
        url = self.query_one("#url-input", Input).value.strip()
        body = self.query_one("#body-input", TextArea).text

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

        res = await self.network.execute_request(method, url, body=body)

        if res["success"]:
            code = res["status_code"]
            color = "green" if code < 400 else "red"
            metrics.update(
                f"[{color}]{code} {res['reason']}[/] | {res['elapsed_ms']}ms | {res['size_bytes']} bytes"
            )
            response_box.text = res["body"]
        else:
            metrics.update(f"[red]Failed[/] | {res['elapsed_ms']}ms")
            response_box.text = res["body"]

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
            await self.webhook_server.stop()
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
            label_text = f"[{hook['timestamp']}] {hook['method']} {hook['path']} ({len(hook['raw_body'])}B)"
            list_view.append(ListItem(Label(f"[cyan]{label_text}[/] -> {hook['body'][:40]}...")))
            self.notify(f"Hook received: {hook['path']}", timeout=2)
        except Exception:
            pass
