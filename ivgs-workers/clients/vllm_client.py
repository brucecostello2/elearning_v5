from __future__ import annotations

import hashlib
import json
import logging
from typing import AsyncIterator, Optional

import httpx

from shared.providers import LLMProvider, LLMParams, LLMResponse

logger = logging.getLogger("ivgs.workers.vllm")


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------

class VLLMError(Exception):
    """Base exception for all vLLM client errors."""


class VLLMTimeoutError(VLLMError):
    """Raised when a vLLM request exceeds the configured timeout."""


class VLLMConnectionError(VLLMError):
    """Raised when the client cannot reach any vLLM endpoint."""


class VLLMRateLimitError(VLLMError):
    """Raised when vLLM returns HTTP 429 (rate-limited)."""


class VLLMInvalidResponseError(VLLMError):
    """Raised when vLLM returns a response that cannot be parsed.

    Attributes:
        response_body: The raw response text that failed parsing.
        status_code:   HTTP status code of the response, if available.
    """

    def __init__(
        self,
        message: str = "Invalid response from vLLM",
        *,
        response_body: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.response_body = response_body
        self.status_code = status_code


class VLLMModelNotFoundError(VLLMError):
    """Raised when the requested model is not loaded on the vLLM instance.

    Typically corresponds to an HTTP 404 or a payload error indicating
    the model name is not recognised by the server.
    """


class VLLMServerError(VLLMError):
    """Raised when vLLM returns an HTTP 5xx server-side error."""


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
            except httpx.TimeoutException as exc:
                last_error = exc
                logger.warning("vLLM timeout", extra={"url": url, "error": str(exc)})
                continue
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status == 429:
                    raise VLLMRateLimitError(
                        f"vLLM rate-limited at {url}"
                    ) from exc
                if status == 404:
                    raise VLLMModelNotFoundError(
                        f"Model not found on vLLM at {url}: {exc}"
                    ) from exc
                if 500 <= status < 600:
                    raise VLLMServerError(
                        f"vLLM server error ({status}) at {url}: {exc}"
                    ) from exc
                last_error = exc
                logger.warning("vLLM HTTP error", extra={"url": url, "error": str(exc)})
                continue
            except KeyError as exc:
                raise VLLMInvalidResponseError(
                    f"Missing expected key in vLLM response: {exc}",
                    response_body=response.text if response else None,
                    status_code=response.status_code if response else None,
                ) from exc
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning("vLLM request failed", extra={"url": url, "error": str(exc)})
                continue

        if isinstance(last_error, httpx.TimeoutException):
            raise VLLMTimeoutError(
                f"All vLLM endpoints timed out: {last_error}"
            ) from last_error
        raise VLLMConnectionError(
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

    # ------------------------------------------------------------------
    # Idempotency helper
    # ------------------------------------------------------------------

    @staticmethod
    def compute_request_hash(
        system_prompt: str,
        user_prompt: str,
        model: str,
        temperature: float,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Return a deterministic SHA-256 hex digest for a request.

        Used by pipeline tasks to detect duplicate LLM calls and skip
        re-processing when idempotency checking is enabled.

        Args:
            system_prompt: The system-role prompt text.
            user_prompt:   The user-role prompt text.
            model:         Model identifier string (e.g. ``meta-llama/Llama-3.3-70B-Instruct``).
            temperature:   Sampling temperature.
            max_tokens:    Maximum output tokens (``None`` treated as ``0`` for hashing).

        Returns:
            64-character lowercase hex SHA-256 digest.
        """
        canonical = json.dumps(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens if max_tokens is not None else 0,
            },
            sort_keys=True,
            ensure_ascii=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
