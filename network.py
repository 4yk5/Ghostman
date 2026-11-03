import time
import json
from typing import Optional, Union
import httpx

class NetworkEngine:
    def __init__(self, timeout: float = 15.0, verify_ssl: bool = True, ca_bundle: Optional[str] = None):
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.ca_bundle = ca_bundle

    async def execute_request(
        self,
        method: str,
        url: str,
        headers: dict = None,
        body: str = None,
        verify_ssl: Optional[bool] = None,
        ca_bundle: Optional[str] = None
    ):
        start_time = time.perf_counter()
        headers = dict(headers) if headers else {}
        
        if not any(k.lower() == "user-agent" for k in headers):
            headers["User-Agent"] = "Ghostman/0.1.3"

        if body and not any(k.lower() == "content-type" for k in headers):
            try:
                json.loads(body)
                headers["Content-Type"] = "application/json"
            except Exception:
                if body.strip().startswith("<") and body.strip().endswith(">"):
                    headers["Content-Type"] = "application/xml"
                else:
                    headers["Content-Type"] = "text/plain"

        # Determine SSL verification mode (defaults to True for MITM protection)
        if ca_bundle:
            verify_target: Union[bool, str] = ca_bundle
        elif verify_ssl is not None:
            verify_target = verify_ssl
        elif self.ca_bundle:
            verify_target = self.ca_bundle
        else:
            verify_target = self.verify_ssl

        try:
            async with httpx.AsyncClient(verify=verify_target, timeout=self.timeout, follow_redirects=True) as client:
                res = await client.request(
                    method=method.upper(),
                    url=url,
                    headers=headers,
                    content=body.encode("utf-8") if body else None
                )
                elapsed_ms = (time.perf_counter() - start_time) * 1000

                raw_text = res.text
                try:
                    formatted_body = json.dumps(res.json(), indent=2, ensure_ascii=False)
                    is_json = True
                except Exception:
                    formatted_body = raw_text
                    is_json = False

                return {
                    "success": True,
                    "status_code": res.status_code,
                    "reason": res.reason_phrase,
                    "elapsed_ms": round(elapsed_ms, 2),
                    "headers": dict(res.headers),
                    "body": formatted_body,
                    "is_json": is_json,
                    "size_bytes": len(res.content)
                }
        except httpx.ConnectError as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            err_msg = str(e)
            if "certificate" in err_msg.lower() or "ssl" in err_msg.lower() or "tls" in err_msg.lower():
                err_display = f"SSL/TLS Certificate Verification Failed: {e}"
            else:
                err_display = f"Connection Failed: {e}"
            return {
                "success": False,
                "error": str(e),
                "elapsed_ms": round(elapsed_ms, 2),
                "status_code": 0,
                "body": err_display
            }
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return {
                "success": False,
                "error": str(e),
                "elapsed_ms": round(elapsed_ms, 2),
                "status_code": 0,
                "body": f"Request Failed: {e}"
            }
