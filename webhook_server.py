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
        max_chunks: int = 10000,
        read_timeout: float = 10.0,
        total_timeout: float = 30.0
    ):
        self.host = host
        self.port = port
        self.on_hook_received = on_hook_received
        self.max_payload_size = max_payload_size
        self.max_chunks = max_chunks
        self.read_timeout = read_timeout
        self.total_timeout = total_timeout
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

    async def _send_error_response(self, writer: asyncio.StreamWriter, status_line: bytes, message: str = ""):
        try:
            body = f'{{"error":"{message}"}}'.encode("utf-8") if message else b""
            content_len = len(body)
            resp = (
                b"HTTP/1.1 " + status_line + b"\r\n"
                b"Content-Type: application/json\r\n"
                b"Content-Length: " + str(content_len).encode("ascii") + b"\r\n"
                b"Connection: close\r\n\r\n" + body
            )
            writer.write(resp)
            await writer.drain()
        except Exception:
            pass

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            # Enforce an absolute total deadline for the entire request
            await asyncio.wait_for(
                self._process_request(reader, writer),
                timeout=self.total_timeout
            )
        except asyncio.TimeoutError:
            try:
                writer.write(b"HTTP/1.1 408 Request Timeout\r\nConnection: close\r\n\r\n")
                await writer.drain()
            except Exception:
                pass
        except Exception:
            pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _process_request(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=self.read_timeout)
        except (asyncio.TimeoutError, asyncio.IncompleteReadError):
            return

        if not line:
            return

        req_line = line.decode("utf-8", errors="ignore").strip()
        parts = req_line.split(" ")
        method = parts[0] if parts else "GET"
        path = parts[1] if len(parts) > 1 else "/"

        headers = {}
        content_length = 0
        transfer_encoding = ""
        while True:
            try:
                header_line = await asyncio.wait_for(reader.readline(), timeout=self.read_timeout)
            except (asyncio.TimeoutError, asyncio.IncompleteReadError):
                await self._send_error_response(writer, b"400 Bad Request", "Connection interrupted during headers")
                return

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
            # Memory bounded accumulation using bytearray instead of unbounded Python list of bytes objects
            body_buffer = bytearray()
            chunk_count = 0
            has_terminated = False

            while True:
                chunk_count += 1
                if chunk_count > self.max_chunks:
                    await self._send_error_response(
                        writer,
                        b"413 Payload Too Large",
                        f"Exceeded maximum chunk count limit ({self.max_chunks})"
                    )
                    return

                try:
                    size_line = await asyncio.wait_for(reader.readline(), timeout=self.read_timeout)
                except (asyncio.TimeoutError, asyncio.IncompleteReadError):
                    await self._send_error_response(writer, b"400 Bad Request", "Unexpected EOF or timeout reading chunk size")
                    return

                if not size_line:
                    # Premature EOF before terminal chunk
                    await self._send_error_response(writer, b"400 Bad Request", "Incomplete chunked stream before terminator")
                    return

                # Strip chunk extension if present (e.g., "1a;ext=val")
                size_str = size_line.decode("utf-8", errors="ignore").split(";")[0].strip()
                if not size_str:
                    await self._send_error_response(writer, b"400 Bad Request", "Missing chunk size")
                    return

                try:
                    chunk_size = int(size_str, 16)
                except ValueError:
                    await self._send_error_response(writer, b"400 Bad Request", f"Invalid hex chunk size: {size_str}")
                    return

                if chunk_size < 0:
                    await self._send_error_response(writer, b"400 Bad Request", "Negative chunk size")
                    return

                if chunk_size == 0:
                    # Consume trailer headers until empty CRLF line
                    while True:
                        try:
                            trailer = await asyncio.wait_for(reader.readline(), timeout=self.read_timeout)
                        except (asyncio.TimeoutError, asyncio.IncompleteReadError):
                            break
                        if not trailer or trailer in (b"\r\n", b"\n"):
                            break
                    has_terminated = True
                    break

                # Guard against total payload size limit
                if len(body_buffer) + chunk_size > self.max_payload_size:
                    await self._send_error_response(
                        writer,
                        b"413 Payload Too Large",
                        f"Payload exceeded maximum size of {self.max_payload_size} bytes"
                    )
                    return

                try:
                    chunk_data = await asyncio.wait_for(reader.readexactly(chunk_size), timeout=self.read_timeout)
                except (asyncio.IncompleteReadError, asyncio.TimeoutError):
                    await self._send_error_response(writer, b"400 Bad Request", "Incomplete chunk data read")
                    return

                body_buffer.extend(chunk_data)

                # Verify and consume trailing CRLF after chunk data
                try:
                    crlf = await asyncio.wait_for(reader.readline(), timeout=self.read_timeout)
                except (asyncio.IncompleteReadError, asyncio.TimeoutError):
                    await self._send_error_response(writer, b"400 Bad Request", "Missing chunk trailing CRLF")
                    return

                if crlf not in (b"\r\n", b"\n"):
                    await self._send_error_response(writer, b"400 Bad Request", "Malformed chunk trailing delimiter (expected CRLF)")
                    return

            if not has_terminated:
                await self._send_error_response(writer, b"400 Bad Request", "Chunked stream did not terminate cleanly")
                return

            body_bytes = bytes(body_buffer)

        elif content_length > 0:
            if content_length > self.max_payload_size:
                await self._send_error_response(
                    writer,
                    b"413 Payload Too Large",
                    f"Payload exceeded maximum size of {self.max_payload_size} bytes"
                )
                return
            try:
                body_bytes = await asyncio.wait_for(reader.readexactly(content_length), timeout=self.read_timeout)
            except (asyncio.IncompleteReadError, asyncio.TimeoutError):
                await self._send_error_response(writer, b"400 Bad Request", "Incomplete body read")
                return

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
