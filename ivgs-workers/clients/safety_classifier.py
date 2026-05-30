"""
IVGS v5 — Content Safety Classifier (§11.1)
Uses self-hosted LlamaGuard 3 via vLLM on node-04.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger("ivgs.workers.safety")


class SafetyClassifier:
    """Self-hosted content safety classifier using LlamaGuard 3 via vLLM."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: str = "meta-llama/Llama-Guard-3-8B",
        threshold: float = 0.98,
    ):
        self.base_url = (base_url or os.environ["SAFETY_CLASSIFIER_URL"]).rstrip("/")
        self.model = model
        self.threshold = threshold
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        return self._client

    async def classify_text(self, text: str) -> dict:
        """Classify text content for safety."""
        client = await self._get_client()
        response = await client.post(
            f"{self.base_url}/chat/completions",
            json={
                "model": self.model,
                "messages": [
                    {"role": "user", "content": text},
                ],
                "max_tokens": 100,
                "temperature": 0.0,
            },
        )
        response.raise_for_status()
        result = response.json()
        output = result["choices"][0]["message"]["content"].strip().lower()

        is_safe = output.startswith("safe")
        score = 1.0 if is_safe else 0.0

        return {
            "safe": is_safe,
            "score": score,
            "category": output if not is_safe else None,
            "model": self.model,
            "passes_threshold": score >= self.threshold,
        }

    async def classify_image_prompt(self, prompt: str) -> dict:
        """Classify image generation prompt for safety."""
        return await self.classify_text(
            f"Evaluate the safety of this image generation prompt: {prompt}"
        )

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
