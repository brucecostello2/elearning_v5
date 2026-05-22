from __future__ import annotations

import json
import logging
from typing import AsyncIterator, Optional

import httpx

from shared.providers import LLMProvider, LLMParams, LLMResponse

logger = logging.getLogger("ivgs.workers.vllm")


class VLLMClient(LLMProvider):
    """
    vLLM implementation of LLMProvider interface (§19.1).

    Targets vLLM's OpenAI-compatible API at http://node-0X:8000/v1.
    Supports Llama 3.3 70B (tensor parallel on node-02/03),
    Qwen2.5 72B, and Mistral 24B (node-04).
    """

    def __init__(
        self,
        base_url: str,
        model: str = "meta-llama/Llama-3.3-70B-Instruct",
        timeout: float = 120.0,
        max_retries: int = 2,
        failover_urls: Optional[list[str]] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.failover_urls = failover_urls or []
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout, connect=10.0),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
        return self._client

    async def generate(self, prompt: str, params: LLMParams) -> LLMResponse:
        """Generate text from a prompt via vLLM OpenAI-compatible API."""
        client = await self._get_client()
        payload = {
            "model": params.model or self.model,
            "messages": [
                {"role": "system", "content": params.system_prompt or ""},
                {"role": "user", "content": prompt},
            ],
            "temperature": params.temperature,
            "max_tokens": params.max_tokens,
            "top_p": params.top_p,
        }

        urls_to_try = [self.base_url] + self.failover_urls
        last_error: Optional[Exception] = None

        for url in urls_to_try:
            try:
                response = await client.post(
                    f"{url}/v1/chat/completions",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                return LLMResponse(
                    text=data["choices"][0]["message"]["content"],
                    model=data.get("model", self.model),
                    usage=data.get("usage", {}),
                    finish_reason=data["choices"][0].get("finish_reason", "stop"),
                )
            except (httpx.HTTPError, httpx.TimeoutException, KeyError) as exc:
                last_error = exc
                logger.warning(
                    "vLLM request failed",
                    extra={"url": url, "error": str(exc)},
                )
                continue

        raise ConnectionError(
            f"All vLLM endpoints exhausted: {last_error}"
        ) from last_error

    async def stream(self, prompt: str, params: LLMParams) -> AsyncIterator[str]:
        """Stream generated text tokens from vLLM."""
        client = await self._get_client()
        payload = {
            "model": params.model or self.model,
            "messages": [
                {"role": "system", "content": params.system_prompt or ""},
                {"role": "user", "content": prompt},
            ],
            "temperature": params.temperature,
            "max_tokens": params.max_tokens,
            "top_p": params.top_p,
            "stream": True,
        }

        async with client.stream(
            "POST",
            f"{self.base_url}/v1/chat/completions",
            json=payload,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: ") and line != "data: [DONE]":
                    chunk = json.loads(line[6:])
                    delta = chunk["choices"][0].get("delta", {})
                    if content := delta.get("content"):
                        yield content

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
