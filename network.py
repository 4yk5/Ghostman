import time
import json
import httpx

class NetworkEngine:
    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    async def execute_request(self, method: str, url: str, headers: dict = None, body: str = None):
        start_time = time.perf_counter()
        headers = dict(headers) if headers else {}
        
        if not any(k.lower() == "user-agent" for k in headers):
            headers["User-Agent"] = "Ghostman/0.1.0"

        if body and not any(k.lower() == "content-type" for k in headers):
            try:
                json.loads(body)
                headers["Content-Type"] = "application/json"
            except Exception:
                pass

        try:
            async with httpx.AsyncClient(verify=False, timeout=self.timeout, follow_redirects=True) as client:
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
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return {
                "success": False,
                "error": str(e),
                "elapsed_ms": round(elapsed_ms, 2),
                "status_code": 0,
                "body": f"Request Failed: {e}"
            }
