from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from .config import Settings


class OllamaError(RuntimeError):
    pass


class GenerationStopped(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def health(self) -> bool:
        try:
            timeout = httpx.Timeout(5.0)
            async with httpx.AsyncClient(base_url=self.settings.ollama_base_url, timeout=timeout) as client:
                response = await client.get("/api/tags")
                response.raise_for_status()
            return True
        except (httpx.HTTPError, OSError):
            return False

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        stop_requested: Any,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        payload = {
            "model": self.settings.ollama_model,
            "messages": messages,
            "stream": True,
            "options": {"num_ctx": self.settings.ollama_num_ctx},
        }
        timeout = httpx.Timeout(
            connect=10.0,
            read=self.settings.ollama_timeout_seconds,
            write=30.0,
            pool=10.0,
        )
        try:
            async with httpx.AsyncClient(base_url=self.settings.ollama_base_url, timeout=timeout) as client:
                async with client.stream("POST", "/api/chat", json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if stop_requested.is_set():
                            raise GenerationStopped
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError as exc:
                            raise OllamaError("Ollama returned invalid JSON") from exc
                        content = chunk.get("message", {}).get("content", "")
                        if content:
                            yield content, chunk
                        if chunk.get("done"):
                            return
        except GenerationStopped:
            raise
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            raise OllamaError(f"Ollama HTTP {exc.response.status_code}: {detail}") from exc
        except httpx.HTTPError as exc:
            raise OllamaError(f"Ollama connection failed: {exc}") from exc
