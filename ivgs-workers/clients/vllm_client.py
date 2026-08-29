from __future__ import annotations

import hashlib
import json
import re
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


def _extract_json_document(content: str):
    """Pull one complete JSON document out of an LLM reply, or return None.

    WP-37. `chat_json` previously stripped markdown fences only when the reply
    *started* with them, then handed everything else straight to json.loads. A
    reply with a sentence of preamble ("Here is the storyboard:") or a trailing
    remark failed, even though a perfectly good document sat in the middle.

    Three attempts, in order of confidence:
      1. the whole string, parsed directly;
      2. the contents of any ```json / ``` fence, anywhere in the reply;
      3. the first balanced { ... } or [ ... ] span.

    Returns the parsed value, or None if nothing here is complete and valid.

    THIS DOES NOT REPAIR ANYTHING. Every candidate must parse on its own. The
    balanced-bracket scan requires the brackets to actually close, so a truncated
    document yields no candidate and this returns None - which is the correct
    outcome, because the caller has already raised
    VLLMTruncatedResponseError for that case. Nothing here invents content.
    """
    text = content.strip()
    if not text:
        return None

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fenced blocks, anywhere in the reply - not only at position 0.
    for match in re.findall(r"```(?:json|JSON)?\s*([\s\S]*?)```", text):
        candidate = match.strip()
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    # First balanced object/array, ignoring brackets inside strings so that a
    # brace in a scene description cannot end the span early.
    #
    # Ordered by WHERE each opener first appears, not by a fixed preference. A
    # fixed {-then-[ order returns the first inner OBJECT of a top-level array,
    # which is a silently wrong answer rather than a failure: stage 2's schema
    # can be a list of scenes, and the caller would have received scene 0 alone.
    openers = [(text.find(o), o, c) for o, c in (("{", "}"), ("[", "]"))]
    openers = sorted((i, o, c) for i, o, c in openers if i >= 0)
    for _first_at, opener, closer in openers:
        start = text.find(opener)
        while start >= 0:
            depth = 0
            in_string = False
            escaped = False
            for i in range(start, len(text)):
                ch = text[i]
                if escaped:
                    escaped = False
                    continue
                if ch == "\\":
                    escaped = True
                    continue
                if ch == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch == opener:
                    depth += 1
                elif ch == closer:
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start : i + 1])
                        except json.JSONDecodeError:
                            break
            start = text.find(opener, start + 1)

    return None


class VLLMTruncatedResponseError(VLLMError):
    """The model stopped because it hit the output token limit.

    WP-37. Distinct from VLLMInvalidResponseError on purpose. When vLLM returns
    ``finish_reason == "length"`` the answer is incomplete by construction, and
    the JSON it contains is unparseable *because it was cut off* - not because
    the model formatted it wrongly. Reporting that as "not valid JSON" sends the
    reader to the prompt and the model's formatting when the actual lever is
    max_tokens.

    Measured 2026-08-23, job e408515a: four attempts, ~99 s each, all reported
    "vLLM response is not valid JSON" at char 8540 / 8382 / 7972 / 8079 - a
    consistent ~8 KB ceiling that is exactly the 2048-token budget the node-02
    worker was running with. The response object carried finish_reason all along
    (VLLMChoice.finish_reason, and the VLLMResponse.finish_reason property at
    :106); chat_json simply never looked at it.

    This error is NOT recoverable by repair. A truncated answer must still fail -
    it just has to fail saying the true thing.
    """

    def __init__(
        self,
        message: str = "vLLM response truncated at the output token limit",
        *,
        max_tokens: int | None = None,
        completion_tokens: int | None = None,
        prompt_tokens: int | None = None,
        content_chars: int | None = None,
    ) -> None:
        super().__init__(message)
        self.max_tokens = max_tokens
        self.completion_tokens = completion_tokens
        self.prompt_tokens = prompt_tokens
        self.content_chars = content_chars


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


# ---------------------------------------------------------------------------
# WP-IVGS-12 — two seams the frozen stage bodies cannot reach through
# ---------------------------------------------------------------------------
#
# The eight stage task bodies are frozen (AD-05 §8). Stage 2 must, from this
# package on, (a) constrain its output against the Design Contract schema and
# (b) let that contract reach the database — and its call site passes neither a
# response_format nor anything else new. Rather than edit a frozen body or
# monkey-patch one at runtime, the client grows two small, explicit seams that
# an owned module arms. Both default to exactly the previous behaviour, so a
# worker with nothing registered behaves byte-for-byte as before.

#: Callables invoked with (content, model) for every successful chat response.
#: Registered by `design_core.capture` at worker init. ⚠ An observer MUST NOT
#: raise: this list is walked inside the request path of every LLM stage, and a
#: capture problem is never a reason to fail a render. The loop enforces it.
RESPONSE_OBSERVERS: List[Any] = []

#: Optional override for `chat_json`'s response_format, keyed by nothing —
#: there is one LLM call in flight per task process at a time. Set to a
#: `{"type": "json_schema", ...}` member to constrain the next `chat_json`;
#: cleared by the arming module when the stage ends.
#:
#: ⛔ DO NOT PUT `guided_json` HERE. It is what the recovery plan prescribes,
#: it returns HTTP 200 on the pinned engine, and it does nothing at all —
#: measured 2026-08-29, see `design_core/contract.py`. `response_format` with a
#: `json_schema` is the mechanism that was measured to ENFORCE.
_RESPONSE_FORMAT_OVERRIDE: Dict[str, Any] = {}


def set_response_format_override(value: Optional[Dict[str, Any]]) -> None:
    """Arm (or clear) the response_format `chat_json` will use next."""
    _RESPONSE_FORMAT_OVERRIDE.clear()
    if value:
        _RESPONSE_FORMAT_OVERRIDE.update(value)


def _notify_observers(content: str, model: str) -> None:
    for observer in list(RESPONSE_OBSERVERS):
        try:
            observer(content, model=model)
        except Exception:                                    # noqa: BLE001
            logger.warning(
                "vllm_response_observer_failed",
                extra={"observer": getattr(observer, "__name__", repr(observer))},
            )


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
        primary_http_error: Optional[httpx.HTTPStatusError] = None
        response = None

        for url in urls_to_try:
            try:
                response = await client.post(
                    f"{url}/v1/chat/completions",
                    json=payload,
                    timeout=req_timeout,
                )
                response.raise_for_status()
                parsed = self._parse_response(response.json())
                # WP-IVGS-12. One line, on the success path only, so the Design
                # Contract can leave a frozen stage body without the body
                # changing. Never raises — see `_notify_observers`.
                _notify_observers(parsed.content or "", parsed.model or "")
                return parsed
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
                if primary_http_error is None:
                    primary_http_error = exc
                last_error = exc
                logger.warning("vLLM HTTP error", extra={"url": url, "error": str(exc)})
                continue
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning("vLLM request failed", extra={"url": url, "error": str(exc)})
                continue

        if primary_http_error is not None:
            status = primary_http_error.response.status_code
            body = primary_http_error.response.text[:500]
            raise VLLMError(
                f"vLLM request rejected by primary (HTTP {status}); failover endpoints "
                f"unreachable, so this is the operative error. Response body: {body}"
            ) from primary_http_error
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
            # WP-IVGS-12. Was the literal `{"type": "json_object"}`, which
            # MEASURED as shape-only: the probe's closed enum was violated on
            # the very first try (`verdict: "GAMMA"`). When an owned module has
            # armed a schema, use it; otherwise this is unchanged.
            response_format=(
                dict(_RESPONSE_FORMAT_OVERRIDE) or {"type": "json_object"}
            ),
            timeout=timeout,
        )

        content = response.content.strip()

        # WP-37. Check finish_reason BEFORE parsing. If the model hit the output
        # token limit the answer is incomplete by construction, so json.loads
        # will fail - and reporting that as "not valid JSON" blames the model's
        # formatting for what is actually an exhausted budget. The information
        # was always here; it was simply never read.
        #
        # Deliberately NOT repaired: a truncated storyboard is a partial
        # storyboard, and fabricating the missing scenes to make the JSON parse
        # would produce a plausible document that nobody asked for. It still
        # fails - it now fails saying the true thing.
        if (response.finish_reason or "").lower() == "length":
            usage = response.usage
            raise VLLMTruncatedResponseError(
                "vLLM stopped at the output token limit "
                f"(finish_reason='length', max_tokens={max_tokens}, "
                f"completion_tokens={usage.completion_tokens if usage else 'unknown'}, "
                f"prompt_tokens={usage.prompt_tokens if usage else 'unknown'}, "
                f"content_chars={len(content)}). The response is incomplete, so "
                "it cannot be valid JSON. Raise max_tokens for this stage, or "
                "reduce what the prompt asks for.",
                max_tokens=max_tokens,
                completion_tokens=usage.completion_tokens if usage else None,
                prompt_tokens=usage.prompt_tokens if usage else None,
                content_chars=len(content),
            )

        parsed = _extract_json_document(content)
        if parsed is not None:
            return parsed, response

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
