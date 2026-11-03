import asyncio
import json
from datetime import datetime
from typing import Callable, Optional

class WebhookServer:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9090,
        on_hook_received: Optional[Callable] = None,
        max_payload_size: int = 10 * 1024 * 1024,
        read_timeout: float = 10.0
    ):
        self.host = host
        self.port = port
        self.on_hook_received = on_hook_received
        self.max_payload_size = max_payload_size
        self.read_timeout = read_timeout
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
            line = await asyncio.wait_for(reader.readline(), timeout=self.read_timeout)
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
            transfer_encoding = ""
            while True:
                header_line = await asyncio.wait_for(reader.readline(), timeout=self.read_timeout)
                if not header_line or header_line in (b"\r\n", b"\n"):
                    break
                decoded_header = header_line.decode("utf-8", errors="ignore").strip()
                if ":" in decoded_header:
                    k, v = decoded_header.split(":", 1)
                    k_clean = k.strip()
                    v_clean = v.strip()
                    headers[k_clean] = v_clean
                    lower_k = k_clean.lower()
                    if lower_k == "content-length":
                        try:
                            content_length = int(v_clean)
                        except ValueError:
                            content_length = 0
                    elif lower_k == "transfer-encoding":
                        transfer_encoding = v_clean.lower()

            body_bytes = b""
            # Support Chunked Transfer Encoding (RFC 7230 / RFC 9112) with resource limits
            if "chunked" in transfer_encoding:
                chunks = []
                total_size = 0
                while True:
                    size_line = await asyncio.wait_for(reader.readline(), timeout=self.read_timeout)
                    if not size_line:
                        break
                    # Strip any chunk extensions (e.g., "1a;ext=val")
                    size_str = size_line.decode("utf-8", errors="ignore").split(";")[0].strip()
                    if not size_str:
                        continue
                    try:
                        chunk_size = int(size_str, 16)
                    except ValueError:
                        break
                    if chunk_size == 0:
                        # Consume trailer headers until empty CRLF line
                        while True:
                            trailer = await asyncio.wait_for(reader.readline(), timeout=self.read_timeout)
                            if not trailer or trailer in (b"\r\n", b"\n"):
                                break
                        break

                    # Guard against memory exhaustion
                    if total_size + chunk_size > self.max_payload_size:
                        writer.write(b"HTTP/1.1 413 Payload Too Large\r\nConnection: close\r\n\r\n")
                        await writer.drain()
                        return

                    chunk_data = await asyncio.wait_for(reader.readexactly(chunk_size), timeout=self.read_timeout)
                    chunks.append(chunk_data)
                    total_size += chunk_size

                    # Verify and consume trailing CRLF after chunk data
                    crlf = await asyncio.wait_for(reader.readline(), timeout=self.read_timeout)
                    if crlf not in (b"\r\n", b"\n"):
                        break
                body_bytes = b"".join(chunks)
            elif content_length > 0:
                if content_length > self.max_payload_size:
                    writer.write(b"HTTP/1.1 413 Payload Too Large\r\nConnection: close\r\n\r\n")
                    await writer.drain()
                    return
                body_bytes = await asyncio.wait_for(reader.readexactly(content_length), timeout=self.read_timeout)

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
