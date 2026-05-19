"""
IVGS v5 — Ollama LLM Fallback Client
======================================

Implements §7.1.2: Ollama as LLM fallback on node-05.
Models: Llama 3.2 8B, Phi-3 Medium, Gemma 2 9B.
Inherits from LLMProvider ABC interface per §19.1.
"""

from __future__ import annotations

import json
import logging
from typing import AsyncIterator, Optional

import httpx

from ivgs.shared.providers import LLMProvider, LLMParams, LLMResponse

logger = logging.getLogger("ivgs.workers.ollama")


class OllamaClient(LLMProvider):
    """
    Ollama implementation of LLMProvider interface (§19.1).

    Node: node-05 (http://10.10.0.5:11434).
    Models: llama3.2:8b, phi3:medium, gemma2:9b.
    """

    def __init__(
        self,
        base_url: str = "http://10.10.0.5:11434",
        model: str = "llama3.2:8b",
        timeout: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout, connect=10.0),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )
        return self._client

    async def generate(self, prompt: str, params: LLMParams) -> LLMResponse:
        """Generate text via Ollama API."""
        client = await self._get_client()

        payload = {
            "model": params.model or self.model,
            "messages": [
                {"role": "system", "content": params.system_prompt or ""},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {
                "temperature": params.temperature,
                "num_predict": params.max_tokens,
                "top_p": params.top_p,
            },
        }

        response = await client.post(
            f"{self.base_url}/api/chat",
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

        return LLMResponse(
            text=data["message"]["content"],
            model=data.get("model", self.model),
            usage={
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
                "total_tokens": (
                    data.get("prompt_eval_count", 0) + data.get("eval_count", 0)
                ),
            },
            finish_reason="stop" if data.get("done") else "length",
        )

    async def stream(self, prompt: str, params: LLMParams) -> AsyncIterator[str]:
        """Stream generated text tokens from Ollama."""
        client = await self._get_client()

        payload = {
            "model": params.model or self.model,
            "messages": [
                {"role": "system", "content": params.system_prompt or ""},
                {"role": "user", "content": prompt},
            ],
            "stream": True,
            "options": {
                "temperature": params.temperature,
                "num_predict": params.max_tokens,
                "top_p": params.top_p,
            },
        }

        async with client.stream(
            "POST",
            f"{self.base_url}/api/chat",
            json=payload,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.strip():
                    data = json.loads(line)
                    if content := data.get("message", {}).get("content"):
                        yield content
                    if data.get("done"):
                        break

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
