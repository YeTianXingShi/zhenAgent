import asyncio
import json
from collections.abc import Awaitable, Callable

import httpx

from .config import Limits


class ModelError(Exception):
    def __init__(self, message: str, retryable: bool = False, retry_after: float = 0):
        super().__init__(message)
        self.retryable = retryable
        self.retry_after = retry_after


class Responses:
    """保留原始 Responses items，避免丢掉服务特有的推理字段。"""

    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def generate(
        self, base_url: str, api_key: str, body: dict, limits: Limits,
        on_event: Callable[[dict], Awaitable[None]],
    ) -> dict:
        try:
            async with asyncio.timeout(limits.request_timeout):
                async with self.client.stream(
                    "POST", base_url.rstrip("/") + "/responses", json=body,
                    headers={"Authorization": f"Bearer {api_key}", "Accept": "text/event-stream"},
                    timeout=limits.request_timeout,
                ) as response:
                    if response.status_code >= 400:
                        wait = 0
                        try:
                            wait = min(30, max(0, float(response.headers.get("retry-after", "0"))))
                        except ValueError:
                            pass
                        status = response.status_code
                        label = {
                            400: "请求参数或上下文不被服务接受", 401: "API key 无效",
                            403: "模型访问被拒绝", 404: "Responses 地址或模型不存在",
                            429: "服务限流",
                        }.get(status, "模型服务请求失败")
                        raise ModelError(f"{label}（HTTP {status}）", status in {408, 429} or status >= 500, wait)

                    if "text/event-stream" not in response.headers.get("content-type", ""):
                        raise ModelError("服务未返回 SSE 流，请确认支持 Responses 的 stream=true")
                    lines: list[str] = []
                    size = 0
                    async for line in response.aiter_lines():
                        size += len(line.encode("utf-8"))
                        if size > limits.model_output_bytes:
                            raise ModelError("模型响应达到输出上限")
                        if line.startswith("data:"):
                            lines.append(line[5:].lstrip())
                        elif not line and lines:
                            raw = "\n".join(lines)
                            lines.clear()
                            if raw == "[DONE]":
                                continue
                            try:
                                event = json.loads(raw)
                            except json.JSONDecodeError as error:
                                raise ModelError("模型返回了无法解析的 SSE 数据", True) from error
                            if not isinstance(event, dict):
                                raise ModelError("模型返回了无效的事件", True)
                            await on_event(event)
                            kind = event.get("type")
                            if kind == "response.completed":
                                result = event.get("response", {})
                                if not isinstance(result.get("output"), list):
                                    raise ModelError("完整响应缺少 output items")
                                return result
                            if kind == "response.incomplete":
                                raise ModelError("模型响应不完整，可能达到 token 上限；本次工具调用不会执行")
                            if kind in {"response.failed", "error"}:
                                failure = event.get("response", {}).get("error") or event.get("error") or event
                                code = str(failure.get("code", "")) if isinstance(failure, dict) else ""
                                raise ModelError(
                                    f"模型响应失败{f'（{code}）' if code else ''}",
                                    code in {"server_error", "rate_limit_exceeded", "timeout"},
                                )
                    raise ModelError("模型流在完整响应到达前断开", True)
        except (httpx.TransportError, TimeoutError) as error:
            raise ModelError("模型连接失败或请求超时", True) from error
