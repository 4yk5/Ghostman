import asyncio
import json
from datetime import datetime
from typing import Callable, Optional

class WebhookServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 9090, on_hook_received: Optional[Callable] = None):
        self.host = host
        self.port = port
        self.on_hook_received = on_hook_received
        self.server: Optional[asyncio.AbstractServer] = None
        self.is_running = False
        self.captured_hooks = []

    async def start(self):
        if self.is_running:
            return
        self.server = await asyncio.start_server(self._handle_client, self.host, self.port)
        self.is_running = True

    async def stop(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.server = None
        self.is_running = False

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            line = await reader.readline()
            if not line:
                writer.close()
                await writer.wait_closed()
                return

            req_line = line.decode("utf-8", errors="ignore").strip()
            parts = req_line.split(" ")
            method = parts[0] if parts else "GET"
            path = parts[1] if len(parts) > 1 else "/"

            headers = {}
            content_length = 0
            while True:
                header_line = await reader.readline()
                if not header_line or header_line in (b"\r\n", b"\n"):
                    break
                decoded_header = header_line.decode("utf-8", errors="ignore").strip()
                if ":" in decoded_header:
                    k, v = decoded_header.split(":", 1)
                    k_clean = k.strip().title()
                    v_clean = v.strip()
                    headers[k_clean] = v_clean
                    if k_clean.lower() == "content-length":
                        try:
                            content_length = int(v_clean)
                        except ValueError:
                            content_length = 0

            body_bytes = b""
            if content_length > 0:
                body_bytes = await reader.readexactly(content_length)

            body_str = body_bytes.decode("utf-8", errors="ignore")
            try:
                formatted_body = json.dumps(json.loads(body_str), indent=2, ensure_ascii=False)
            except Exception:
                formatted_body = body_str

            hook_entry = {
                "id": len(self.captured_hooks) + 1,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "method": method,
                "path": path,
                "headers": headers,
                "body": formatted_body,
                "raw_body": body_str
            }
            self.captured_hooks.append(hook_entry)

            # quick 200 response
            response = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n{\"status\":\"ok\",\"source\":\"ghostman\"}"
            writer.write(response)
            await writer.drain()

            if self.on_hook_received:
                if asyncio.iscoroutinefunction(self.on_hook_received):
                    await self.on_hook_received(hook_entry)
                else:
                    self.on_hook_received(hook_entry)
        except Exception:
            pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
