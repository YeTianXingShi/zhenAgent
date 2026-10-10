import asyncio
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import httpx

from .storage import encode, now


CATALOG_URL = "https://models.dev/api.json"
REFRESH_SECONDS = 3600
MAX_DOWNLOAD_BYTES = 32 * 1024 * 1024


def positive_integer(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float) and math.isfinite(value) and value > 0 and value.is_integer():
        return int(value)
    return None


class Catalog:
    def __init__(self, client: httpx.AsyncClient, directory: Path):
        self.client = client
        self.path = directory / "models-dev.json"
        self.providers: dict[str, dict] = {}
        self.fetched_at: str | None = None
        self.error: str | None = None
        self.lock = asyncio.Lock()

    @staticmethod
    def parse(data) -> dict[str, dict]:
        if not isinstance(data, dict):
            raise ValueError("Models.dev 返回的目录格式无效")
        providers = {}
        for provider_id, provider in data.items():
            if (not isinstance(provider, dict) or not isinstance(provider.get("models"), dict)
                    or not isinstance(provider.get("name"), str)):
                continue
            models = {}
            for model_id, model in provider["models"].items():
                if not isinstance(model, dict) or not isinstance(model.get("name"), str):
                    continue
                limits = model.get("limit") if isinstance(model.get("limit"), dict) else {}
                efforts: list[str] = []
                options = model.get("reasoning_options")
                for option in options if isinstance(options, list) else []:
                    if not isinstance(option, dict):
                        continue
                    if option.get("type") == "toggle":
                        efforts.append("none")
                    if option.get("type") == "effort":
                        values = option.get("values")
                        for value in values if isinstance(values, list) else []:
                            if value is None:
                                efforts.append("none")
                            elif isinstance(value, str) and len(value) <= 50:
                                efforts.append(value)
                modalities = model.get("modalities") if isinstance(model.get("modalities"), dict) else {}
                models[model_id] = {
                    "id": model_id, "name": model["name"],
                    "context_tokens": positive_integer(limits.get("context")),
                    "input_tokens": positive_integer(limits.get("input")),
                    "output_tokens": positive_integer(limits.get("output")),
                    "reasoning": model.get("reasoning") is True,
                    "reasoning_efforts": list(dict.fromkeys(efforts)),
                    "tool_call": model.get("tool_call") is True,
                    "input_modalities": modalities.get("input") if isinstance(modalities.get("input"), list) else [],
                    "output_modalities": modalities.get("output") if isinstance(modalities.get("output"), list) else [],
                    "status": model.get("status"),
                }
            if models:
                providers[provider_id] = {
                    "id": provider_id, "name": provider["name"],
                    "api": provider.get("api") if isinstance(provider.get("api"), str) else None,
                    "models": models,
                }
        if not providers:
            raise ValueError("Models.dev 目录没有可用的模型信息")
        return providers

    def load(self):
        if not self.path.exists():
            return
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
            if saved.get("source_url") != CATALOG_URL:
                raise ValueError("缓存来源不匹配")
            fetched_at = saved["fetched_at"]
            if datetime.fromisoformat(fetched_at).tzinfo is None:
                raise ValueError("缓存时间缺少时区")
            self.providers = self.parse(saved["data"])
            self.fetched_at = fetched_at
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            self.error = "Models.dev 本地缓存无法读取，将重新获取目录"

    def stale(self) -> bool:
        return not self.fetched_at or (
            datetime.now(timezone.utc) - datetime.fromisoformat(self.fetched_at)
        ).total_seconds() >= REFRESH_SECONDS

    async def refresh(self) -> bool:
        async with self.lock:
            try:
                async with asyncio.timeout(30):
                    async with self.client.stream(
                        "GET", CATALOG_URL, timeout=20, follow_redirects=True,
                        headers={"Accept": "application/json"},
                    ) as response:
                        response.raise_for_status()
                        content = bytearray()
                        async for chunk in response.aiter_bytes():
                            content.extend(chunk)
                            if len(content) > MAX_DOWNLOAD_BYTES:
                                raise ValueError("Models.dev 目录超过下载大小限制")
                data = json.loads(content)
                providers = self.parse(data)
                fetched_at = now()
                saved = encode({"source_url": CATALOG_URL, "fetched_at": fetched_at, "data": data})
                descriptor, filename = tempfile.mkstemp(dir=self.path.parent, prefix=".models-dev-")
                try:
                    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                        os.fchmod(stream.fileno(), 0o600)
                        stream.write(saved)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(filename, self.path)
                finally:
                    if os.path.exists(filename):
                        os.unlink(filename)
                self.providers = providers
                self.fetched_at = fetched_at
                self.error = None
                return True
            except (httpx.HTTPError, TimeoutError, OSError, ValueError) as error:
                self.error = f"Models.dev 目录更新失败（{type(error).__name__}）"
                return False

    async def maintain(self):
        while True:
            await asyncio.sleep(REFRESH_SECONDS)
            await self.refresh()

    def summary(self) -> dict:
        return {
            "source_url": CATALOG_URL, "fetched_at": self.fetched_at,
            "stale": self.stale(), "error": self.error,
            "providers": [
                {key: provider[key] for key in ("id", "name", "api")}
                for provider in sorted(self.providers.values(), key=lambda item: item["name"])
            ],
        }

    def model(self, provider_id: str | None, model_id: str) -> dict | None:
        return self.providers.get(provider_id, {}).get("models", {}).get(model_id)

    def infer_provider(self, provider: dict) -> str | None:
        if provider["id"] in self.providers:
            return provider["id"]
        matches = [
            entry["id"] for entry in self.providers.values()
            if entry.get("api") and entry["api"].rstrip("/") == provider["base_url"].rstrip("/")
        ]
        return matches[0] if len(matches) == 1 else None

    def resolve(self, provider: dict, model: dict) -> dict:
        metadata = self.model(provider.get("catalog_provider_id"), model["id"])
        return {
            **model, "catalog": metadata,
            "resolved_label": model.get("label") or (metadata or {}).get("name") or model["id"],
            "resolved_max_output_tokens": model.get("max_output_tokens") or (metadata or {}).get("output_tokens"),
        }
