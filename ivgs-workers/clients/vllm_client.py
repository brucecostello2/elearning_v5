from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

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
    """Raised when vLLM returns a response that cannot be parsed."""

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
    """Raised when the requested model is not loaded on the vLLM instance."""


class VLLMServerError(VLLMError):
    """Raised when vLLM returns an HTTP 5xx server-side error."""


# ---------------------------------------------------------------------------
# Response models (task-facing; re-added per H.0 WI-1).
# Lightweight stdlib dataclasses mirroring the OpenAI-compatible response shape
# that pipeline tasks read: response.content,
# response.choices[i].message.content, response.usage.prompt_tokens,
# response.model.
# ---------------------------------------------------------------------------

@dataclass
class VLLMMessage:
    role: str
    content: str


@dataclass
class VLLMUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class VLLMChoice:
    index: int = 0
    message: Optional[VLLMMessage] = None
    text: Optional[str] = None
    finish_reason: Optional[str] = None


@dataclass
class VLLMResponse:
    id: str = ""
    object: str = ""
    created: int = 0
    model: str = ""
    choices: List[VLLMChoice] = field(default_factory=list)
    usage: Optional[VLLMUsage] = None

    @property
    def content(self) -> str:
        if self.choices and self.choices[0].message:
            return self.choices[0].message.content or ""
        if self.choices and self.choices[0].text:
            return self.choices[0].text or ""
        return ""

    @property
    def finish_reason(self) -> Optional[str]:
        return self.choices[0].finish_reason if self.choices else None


class VLLMClient(LLMProvider):
    """
    vLLM implementation of the LLMProvider interface (spec 19.1).

    Targets vLLM's OpenAI-compatible API at http://node-0X:8000/v1.

    Provider interface : generate() / stream()  -> shared LLMResponse.
    Task interface (re-added H.0 WI-1):
        chat() / chat_json() / chat_completion() -> VLLMResponse,
        compute_request_hash(), and async-context support.

    The constructor accepts either a VLLMConfig (VLLMClient(config.vllm)) or an
    explicit base_url (VLLMClient(base_url=...)); detection is by duck-typing on
    `primary_base_url`, so config.py is never imported here.
    """

    def __init__(
        self,
        config_or_base_url: Any = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        failover_urls: Optional[List[str]] = None,
        *,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        cfg = config_or_base_url if hasattr(config_or_base_url, "primary_base_url") else None
        resolved = base_url or (cfg.primary_base_url if cfg else config_or_base_url)
        if not resolved:
            raise VLLMError("VLLMClient requires a base_url or a VLLMConfig")

        self.base_url = str(resolved).rstrip("/")
        self._config = cfg
        self.api_key = (
            api_key
            or (cfg.api_key if cfg is not None else None)
            or os.environ.get("IVGS_VLLM_API_KEY")
        )
        self.model = model or (cfg.primary_model if cfg else "meta-llama/Llama-3.3-70B-Instruct")
        self.timeout = timeout if timeout is not None else (float(cfg.timeout_seconds) if cfg else 120.0)
        self.max_retries = max_retries if max_retries is not None else (cfg.max_retries if cfg else 2)

        if failover_urls is not None:
            self.failover_urls = failover_urls
        elif cfg:
            self.failover_urls = [
                u for u in (cfg.secondary_base_url, cfg.midsize_base_url)
                if u and u.rstrip("/") != self.base_url
            ]
        else:
            self.failover_urls = []

        self._default_max_tokens = cfg.max_tokens if cfg else 8192
        self._default_temperature = cfg.temperature if cfg else 0.3
        self._default_top_p = cfg.top_p if cfg else 0.9
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = httpx.AsyncClient(
                headers=headers,
                timeout=httpx.Timeout(self.timeout, connect=10.0),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
        return self._client

    async def __aenter__(self) -> "VLLMClient":
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Provider interface (shared LLMResponse)
    # ------------------------------------------------------------------

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
                    raise VLLMRateLimitError(f"vLLM rate-limited at {url}") from exc
                if status == 404:
                    raise VLLMModelNotFoundError(f"Model not found on vLLM at {url}: {exc}") from exc
                if 500 <= status < 600:
                    raise VLLMServerError(f"vLLM server error ({status}) at {url}: {exc}") from exc
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
            raise VLLMTimeoutError(f"All vLLM endpoints timed out: {last_error}") from last_error
        raise VLLMConnectionError(f"All vLLM endpoints exhausted: {last_error}") from last_error

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
    # Shared execution for the task-facing chat API
    # ------------------------------------------------------------------

    async def _chat_request(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        response_format: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> VLLMResponse:
        client = await self._get_client()
        payload: Dict[str, Any] = {
            "model": model or self.model,
            "messages": messages,
            "max_tokens": max_tokens if max_tokens is not None else self._default_max_tokens,
            "temperature": temperature if temperature is not None else self._default_temperature,
            "top_p": top_p if top_p is not None else self._default_top_p,
        }
        if response_format is not None:
            payload["response_format"] = response_format

        primary = (base_url or self.base_url).rstrip("/")
        urls_to_try = [primary] + [u.rstrip("/") for u in self.failover_urls if u.rstrip("/") != primary]
        req_timeout = timeout if timeout is not None else self.timeout
        last_error: Optional[Exception] = None
        response = None

        for url in urls_to_try:
            try:
                response = await client.post(
                    f"{url}/v1/chat/completions",
                    json=payload,
                    timeout=req_timeout,
                )
                response.raise_for_status()
                return self._parse_response(response.json())
            except httpx.TimeoutException as exc:
                last_error = exc
                logger.warning("vLLM timeout", extra={"url": url, "error": str(exc)})
                continue
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status == 429:
                    raise VLLMRateLimitError(f"vLLM rate-limited at {url}") from exc
                if status == 404:
                    raise VLLMModelNotFoundError(f"Model not found on vLLM at {url}: {exc}") from exc
                if 500 <= status < 600:
                    raise VLLMServerError(f"vLLM server error ({status}) at {url}: {exc}") from exc
                last_error = exc
                logger.warning("vLLM HTTP error", extra={"url": url, "error": str(exc)})
                continue
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning("vLLM request failed", extra={"url": url, "error": str(exc)})
                continue

        if isinstance(last_error, httpx.TimeoutException):
            raise VLLMTimeoutError(f"All vLLM endpoints timed out: {last_error}") from last_error
        raise VLLMConnectionError(f"All vLLM endpoints exhausted: {last_error}") from last_error

    def _parse_response(self, data: Dict[str, Any]) -> VLLMResponse:
        """Parse a raw vLLM JSON body into a VLLMResponse."""
        try:
            choices: List[VLLMChoice] = []
            for c in data.get("choices", []):
                msg_data = c.get("message") or {}
                choices.append(
                    VLLMChoice(
                        index=c.get("index", 0),
                        message=VLLMMessage(
                            role=msg_data.get("role", "assistant"),
                            content=msg_data.get("content", ""),
                        ),
                        text=c.get("text"),
                        finish_reason=c.get("finish_reason"),
                    )
                )

            usage = None
            usage_data = data.get("usage")
            if usage_data:
                usage = VLLMUsage(
                    prompt_tokens=usage_data.get("prompt_tokens", 0),
                    completion_tokens=usage_data.get("completion_tokens", 0),
                    total_tokens=usage_data.get("total_tokens", 0),
                )

            return VLLMResponse(
                id=data.get("id", ""),
                object=data.get("object", ""),
                created=data.get("created", 0),
                model=data.get("model", self.model),
                choices=choices,
                usage=usage,
            )
        except Exception as exc:
            raise VLLMInvalidResponseError(
                f"Failed to parse vLLM response: {exc}",
                response_body=json.dumps(data)[:1000],
            ) from exc

    # ------------------------------------------------------------------
    # Task-facing convenience methods (re-added H.0 WI-1)
    # ------------------------------------------------------------------

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        response_format: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> VLLMResponse:
        """Send an explicit list of chat messages (OpenAI-style dicts)."""
        return await self._chat_request(
            messages=messages,
            model=model,
            base_url=base_url,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            response_format=response_format,
            timeout=timeout,
        )

    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        response_format: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> VLLMResponse:
        """Primary entry point for stage tasks: system + user -> VLLMResponse."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return await self._chat_request(
            messages=messages,
            model=model,
            base_url=base_url,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            response_format=response_format,
            timeout=timeout,
        )

    async def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        timeout: Optional[float] = None,
    ) -> Tuple[Dict[str, Any], VLLMResponse]:
        """Chat completion expecting JSON. Returns (parsed_json, raw_response)."""
        response = await self.chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            base_url=base_url,
            max_tokens=max_tokens,
            temperature=temperature,
            response_format={"type": "json_object"},
            timeout=timeout,
        )

        content = response.content.strip()

        # Strip markdown code fences if present.
        if content.startswith("```"):
            lines = content.split("\n")
            json_lines: List[str] = []
            in_block = False
            for line in lines:
                if line.startswith("```") and not in_block:
                    in_block = True
                    continue
                if line.startswith("```") and in_block:
                    break
                if in_block:
                    json_lines.append(line)
            if json_lines:
                content = "\n".join(json_lines)

        try:
            parsed = json.loads(content)
            return parsed, response
        except json.JSONDecodeError as exc:
            raise VLLMInvalidResponseError(
                f"vLLM response is not valid JSON: {exc}",
                response_body=content[:2000],
            ) from exc

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
        """Deterministic SHA-256 digest of request params (for idempotency)."""
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
