from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Footer, Input, Button, Select, Tabs, Tab, TextArea, ListView, ListItem, Label
)
from textual.binding import Binding

from network import NetworkEngine
from webhook_server import WebhookServer
from storage import StorageManager

import json
import re


class GhostmanApp(App):
    CSS_PATH = "styles.tcss"
    ENABLE_COMMAND_PALETTE = False

    BINDINGS = [
        Binding("ctrl+s", "send_request", "Send Request", priority=True),
        Binding("ctrl+w", "toggle_webhook", "Toggle Webhook Server", priority=True),
        Binding("ctrl+t", "toggle_ssl", "Toggle TLS Verify", priority=True),
        Binding("ctrl+n", "new_request", "New Request", priority=True),
        Binding("ctrl+k", "save_request", "Save Request", priority=True),
        Binding("ctrl+e", "cycle_env", "Switch Env", priority=True),
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

        self.env_data = self.storage.load_environments()
        self._active_env = self.env_data.get("active", "Default")
        env_names = [e["name"] for e in self.env_data.get("environments", [])]
        if not env_names:
            self.env_data["environments"] = [{"name": "Default", "variables": {}}]
            self._active_env = "Default"
            self.env_data["active"] = "Default"
        elif self._active_env not in env_names:
            self._active_env = env_names[0]
            self.env_data["active"] = self._active_env
        self._env_options = [(e["name"], e["name"]) for e in self.env_data["environments"]]
        self._env_switching = False

        self.webhook_server = WebhookServer(
            host="127.0.0.1",
            port=9090,
            on_hook_received=self.handle_incoming_webhook
        )

    def compose(self) -> ComposeResult:
        with Horizontal(id="header-bar"):
            yield Label("[GHOSTMAN]", id="title-label")
            yield Label("Terminal API & Webhook Studio (Local-First)", id="subtitle-label")
            yield Label(f"[ENV: {self._active_env}]", id="env-indicator")

        with Horizontal(id="main-container"):
            with Vertical(id="sidebar"):
                with Horizontal(id="sidebar-header"):
                    yield Label("COLLECTIONS", id="sidebar-title")
                    yield Button("+ NEW", id="new-req-btn")
                yield ListView(id="requests-list")

            with Vertical(id="content-area"):
                with Horizontal(id="request-bar"):
                    yield Select(self.METHODS, value="GET", allow_blank=False, id="method-select")
                    yield Input(placeholder="URL (supports {{env_var}} syntax)...", id="url-input")
                    yield Button("SEND", id="send-btn")
                    yield Button("SAVE", id="save-btn")

                yield Tabs(
                    Tab("Body & Payload", id="tab-body"),
                    Tab("Headers", id="tab-headers"),
                    Tab("Response", id="tab-response"),
                    Tab("Live Webhooks", id="tab-webhook"),
                    Tab("Environments", id="tab-env"),
                    id="tabs"
                )

                with Vertical(id="tab-body-pane"):
                    yield TextArea(id="body-input", language="json", text='{\n  "hello": "world"\n}')

                with Vertical(id="tab-headers-pane"):
                    yield TextArea(id="headers-input", language="yaml", text="")

                with Vertical(id="tab-response-pane"):
                    yield Label("Status: Idle", id="metrics-bar")
                    yield TextArea(id="response-area", read_only=True, language="json", text="")

                with Vertical(id="tab-webhook-pane"):
                    with Horizontal(id="webhook-status"):
                        yield Label("Webhook Receiver: [OFFLINE] (Port 9090)", id="webhook-status-label")
                        yield Button("START RECEIVER", id="webhook-toggle-btn")
                    yield Label("Send requests to http://127.0.0.1:9090 to inspect payloads live:")
                    yield ListView(id="webhook-list")

                with Vertical(id="tab-env-pane"):
                    with Horizontal(id="env-bar"):
                        yield Select(self._env_options, value=self._active_env, allow_blank=False, id="env-select")
                        yield Input(placeholder="Environment name...", value=self._active_env, id="env-name-input")
                        yield Button("+ NEW", id="env-new-btn")
                        yield Button("DEL", id="env-del-btn")
                        yield Button("SAVE", id="env-save-btn")
                    yield Label("Define variables below (KEY = VALUE per line). Use {{KEY}} in URLs, headers, and body.", id="env-hint")
                    yield TextArea(id="env-editor", language="yaml", text="")

        yield Footer()

    async def on_mount(self):
        self.populate_sidebar()
        self.query_one("#tab-headers-pane").display = False
        self.query_one("#tab-response-pane").display = False
        self.query_one("#tab-webhook-pane").display = False
        self.query_one("#tab-env-pane").display = False
        self.query_one("#url-input").value = "https://jsonplaceholder.typicode.com/posts/1"
        self._load_env_into_editor(self._active_env)

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

    @staticmethod
    def substitute_variables(text: str, variables: dict) -> str:
        """Replace {{key}} placeholders with values from the given variable map."""
        if not text or not variables:
            return text or ""
        def replacer(match):
            key = match.group(1).strip()
            return variables.get(key, match.group(0))
        return re.sub(r'\{\{(.+?)\}\}', replacer, text)

    @staticmethod
    def _parse_env_text(text: str) -> dict:
        variables = {}
        if not text:
            return variables
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                if k:
                    variables[k] = v.strip()
        return variables

    @staticmethod
    def _format_env_text(variables: dict) -> str:
        if not variables:
            return ""
        return "\n".join(f"{k} = {v}" for k, v in variables.items())

    def _get_active_variables(self) -> dict:
        for env in self.env_data.get("environments", []):
            if env["name"] == self._active_env:
                return dict(env.get("variables", {}))
        return {}

    def _update_env_indicator(self):
        try:
            self.query_one("#env-indicator", Label).update(f"[ENV: {self._active_env}]")
        except Exception:
            pass

    def _load_env_into_editor(self, env_name: str):
        for env in self.env_data.get("environments", []):
            if env["name"] == env_name:
                try:
                    self.query_one("#env-name-input", Input).value = env["name"]
                    self.query_one("#env-editor", TextArea).text = self._format_env_text(env.get("variables", {}))
                except Exception:
                    pass
                self._active_env = env_name
                self.env_data["active"] = env_name
                self._update_env_indicator()
                return

    def _auto_save_env_variables(self):
        try:
            variables = self._parse_env_text(self.query_one("#env-editor", TextArea).text)
            for env in self.env_data.get("environments", []):
                if env["name"] == self._active_env:
                    env["variables"] = variables
                    break
            self.storage.save_environments(self.env_data)
        except Exception:
            pass

    def _save_current_env(self):
        try:
            select = self.query_one("#env-select", Select)
            if select.value == Select.BLANK:
                return
            old_name = str(select.value)
            new_name = self.query_one("#env-name-input", Input).value.strip()
            if not new_name:
                new_name = old_name

            if new_name != old_name:
                existing = {e["name"] for e in self.env_data.get("environments", []) if e["name"] != old_name}
                if new_name in existing:
                    self.notify(f"Environment '{new_name}' already exists", severity="warning")
                    return

            variables = self._parse_env_text(self.query_one("#env-editor", TextArea).text)

            for env in self.env_data.get("environments", []):
                if env["name"] == old_name:
                    env["name"] = new_name
                    env["variables"] = variables
                    break

            self._active_env = new_name
            self.env_data["active"] = new_name
            self.storage.save_environments(self.env_data)
            self._env_switching = True
            self._refresh_env_selector()
            self._env_switching = False
            self._update_env_indicator()
        except Exception as e:
            self._env_switching = False
            self.notify(f"Error saving environment: {e}", severity="error")

    def _refresh_env_selector(self):
        try:
            options = [(e["name"], e["name"]) for e in self.env_data.get("environments", [])]
            select = self.query_one("#env-select", Select)
            self._env_switching = True
            select.set_options(options)
            if self._active_env:
                select.value = self._active_env
            self._env_switching = False
        except Exception:
            self._env_switching = False

    def _create_new_env(self):
        envs = self.env_data.get("environments", [])
        existing = {e["name"] for e in envs}
        name = "New Environment"
        counter = 1
        while name in existing:
            counter += 1
            name = f"New Environment {counter}"

        envs.append({"name": name, "variables": {}})
        self._active_env = name
        self.env_data["active"] = name
        self.storage.save_environments(self.env_data)
        self._refresh_env_selector()
        self._load_env_into_editor(name)
        self.notify(f"Created: {name}", timeout=2)

    def _delete_current_env(self):
        envs = self.env_data.get("environments", [])
        if len(envs) <= 1:
            self.notify("Cannot delete the last environment", severity="warning")
            return
        deleted = self._active_env
        envs[:] = [e for e in envs if e["name"] != self._active_env]
        self._active_env = envs[0]["name"]
        self.env_data["active"] = self._active_env
        self.storage.save_environments(self.env_data)
        self._refresh_env_selector()
        self._load_env_into_editor(self._active_env)
        self.notify(f"Deleted: {deleted}", timeout=2)

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
            req_headers = req.get("headers", {})
            self.query_one("#headers-input", TextArea).text = self.format_headers_text(req_headers)
            self.notify(f"Selected: {req.get('name')}", timeout=2)
        elif hasattr(item, "hook_data"):
            hook = item.hook_data
            h_method = hook.get("method", "GET").upper()
            if h_method in [m[0] for m in self.METHODS]:
                self.query_one("#method-select", Select).value = h_method
            self.query_one("#body-input", TextArea).text = hook.get("raw_body", "") or ""
            hook_headers = hook.get("headers", {})
            self.query_one("#headers-input", TextArea).text = self.format_headers_text(hook_headers)
            self.query_one("#tabs", Tabs).active = "tab-body"
            self.notify(f"Loaded hook payload ({hook.get('path', '/')})", timeout=2)

    def on_tabs_tab_activated(self, event: Tabs.TabActivated):
        tab_id = event.tab.id
        self.query_one("#tab-body-pane").display = (tab_id == "tab-body")
        self.query_one("#tab-headers-pane").display = (tab_id == "tab-headers")
        self.query_one("#tab-response-pane").display = (tab_id == "tab-response")
        self.query_one("#tab-webhook-pane").display = (tab_id == "tab-webhook")
        self.query_one("#tab-env-pane").display = (tab_id == "tab-env")

    def on_select_changed(self, event: Select.Changed):
        if self._env_switching:
            return
        if event.select.id == "env-select" and event.value != Select.BLANK:
            new_env = str(event.value)
            if new_env != self._active_env:
                self._env_switching = True
                try:
                    self._auto_save_env_variables()
                    self._load_env_into_editor(new_env)
                finally:
                    self._env_switching = False

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
        if self.verify_ssl:
            self.notify("TLS Certificate Verification ENABLED (Secure)", timeout=3)
        else:
            self.notify("TLS Certificate Verification DISABLED (Insecure)", severity="warning", timeout=3)

    def action_cycle_env(self):
        envs = self.env_data.get("environments", [])
        if len(envs) <= 1:
            self.notify("Only one environment available", timeout=2)
            return
        self._auto_save_env_variables()
        names = [e["name"] for e in envs]
        try:
            idx = names.index(self._active_env)
            next_idx = (idx + 1) % len(names)
        except ValueError:
            next_idx = 0
        next_name = names[next_idx]
        self._load_env_into_editor(next_name)
        self._env_switching = True
        try:
            self.query_one("#env-select", Select).value = next_name
        except Exception:
            pass
        self._env_switching = False
        self.notify(f"Switched to: {next_name}", timeout=2)

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
        elif btn_id == "env-new-btn":
            self._create_new_env()
        elif btn_id == "env-del-btn":
            self._delete_current_env()
        elif btn_id == "env-save-btn":
            self._save_current_env()
            self.notify("Environment saved", timeout=2)

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

            env_vars = self._get_active_variables()
            resolved_body = self.substitute_variables(body, env_vars) if body else body

            if resolved_body and not any(k.lower() == "content-type" for k in req_headers):
                try:
                    json.loads(resolved_body)
                    req_headers["Content-Type"] = "application/json"
                except Exception:
                    stripped = resolved_body.strip()
                    if stripped.startswith("<?xml") or stripped.startswith("<soap:"):
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

            env_vars = self._get_active_variables()
            resolved_url = self.substitute_variables(url, env_vars)
            resolved_body = self.substitute_variables(body, env_vars) if body else body
            resolved_headers = {k: self.substitute_variables(v, env_vars) for k, v in req_headers.items()}

            if not resolved_url.startswith("http://") and not resolved_url.startswith("https://"):
                resolved_url = "https://" + resolved_url
                if "{{" not in url:
                    self.query_one("#url-input", Input).value = resolved_url

            self.query_one("#tabs", Tabs).active = "tab-response"
            metrics = self.query_one("#metrics-bar", Label)
            response_box = self.query_one("#response-area", TextArea)

            metrics.update(f"Sending {method} to {resolved_url}...")
            response_box.text = "Waiting for response..."

            req_body = resolved_body if method in ["POST", "PUT", "PATCH", "DELETE"] else None

            res = await self.network.execute_request(
                method=method,
                url=resolved_url,
                headers=resolved_headers,
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
