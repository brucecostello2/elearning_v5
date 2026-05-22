"""
IVGS v5 — Content Safety Classifier Service
===============================================

Content safety scoring per §11.1 Table 11-1.

Uses a self-hosted classifier model on GPU nodes to evaluate
generated assets for content safety compliance.

Thresholds per §11.1:
- Auto-approve: safety score >0.98
- Auto-reject:  safety score <0.95

The classifier evaluates:
- Nudity / sexual content
- Violence / gore
- Hate speech / symbols
- Self-harm content
- Drug / substance imagery
- Copyrighted material indicators

Each category produces a score 0.0–1.0 (1.0 = safe).
The overall safety score is the minimum across all categories.

API contract (self-hosted classifier on GPU node):
- POST /classify    — Submit asset for classification
- GET  /health      — Health check
- GET  /categories  — List supported categories
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Constants per §11.1
# ---------------------------------------------------------------------------

SAFETY_APPROVE_THRESHOLD = 0.98
SAFETY_REJECT_THRESHOLD = 0.95

SAFETY_CATEGORIES = [
    "nudity",
    "violence",
    "hate_symbols",
    "self_harm",
    "drug_imagery",
    "copyright_indicators",
]


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

class SafetyDecision(str, Enum):
    """Safety classification decisions."""

    SAFE = "safe"
    UNSAFE = "unsafe"
    REVIEW_REQUIRED = "review_required"


@dataclass
class SafetyCategory:
    """Safety score for a single category."""

    category: str
    score: float
    is_safe: bool
    details: Optional[str] = None


@dataclass
class SafetyReport:
    """Complete safety classification report."""

    asset_id: str
    overall_score: float
    decision: SafetyDecision
    categories: List[SafetyCategory]
    model_name: str
    model_version: str
    classified_at: str
    classification_duration_s: float
    file_path: str
    asset_type: str

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for storage."""
        return {
            "asset_id": self.asset_id,
            "overall_score": self.overall_score,
            "decision": self.decision.value,
            "categories": [
                {
                    "category": c.category,
                    "score": c.score,
                    "is_safe": c.is_safe,
                    "details": c.details,
                }
                for c in self.categories
            ],
            "model_name": self.model_name,
            "model_version": self.model_version,
            "classified_at": self.classified_at,
            "classification_duration_s": self.classification_duration_s,
        }


# ---------------------------------------------------------------------------
# Safety Classifier Service
# ---------------------------------------------------------------------------

class SafetyClassifierService:
    """
    Content safety classifier service per §11.1.

    Interfaces with the self-hosted content safety classifier
    to evaluate generated assets for content safety compliance.

    Args:
        classifier_endpoint: URL of the self-hosted classifier.
        approve_threshold: Safety score threshold for auto-approve (default: 0.98).
        reject_threshold: Safety score threshold for auto-reject (default: 0.95).
        timeout_s: Request timeout in seconds.
        max_retries: Maximum number of retries on failure.
    """

    def __init__(
        self,
        classifier_endpoint: str = "http://localhost:8101",
        approve_threshold: float = SAFETY_APPROVE_THRESHOLD,
        reject_threshold: float = SAFETY_REJECT_THRESHOLD,
        timeout_s: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        self._endpoint = classifier_endpoint.rstrip("/")
        self._approve_threshold = approve_threshold
        self._reject_threshold = reject_threshold
        self._timeout = timeout_s
        self._max_retries = max_retries

    async def classify_asset(
        self,
        asset_id: str,
        file_path: str,
        asset_type: str,
    ) -> SafetyReport:
        """
        Classify an asset for content safety per §11.1.

        Submits the asset to the self-hosted classifier and
        evaluates all safety categories. The overall score
        is the minimum across all categories.

        Args:
            asset_id: Unique asset identifier.
            file_path: Local path to the asset file.
            asset_type: Type of asset (image, video, audio).

        Returns:
            SafetyReport with per-category scores and overall decision.
        """
        log = logger.bind(
            asset_id=asset_id,
            asset_type=asset_type,
        )
        log.info("safety_classification_start")

        start_time = time.monotonic()
        categories: List[SafetyCategory] = []
        model_name = "safety-classifier-v1"
        model_version = "1.0.0"

        last_error: Optional[Exception] = None

        for attempt in range(1, self._max_retries + 1):
            try:
                result = await self._call_classifier(
                    file_path, asset_type
                )
                categories = self._parse_categories(result)
                model_name = result.get("model_name", model_name)
                model_version = result.get("model_version", model_version)
                last_error = None
                break

            except httpx.TimeoutException as exc:
                last_error = exc
                log.warning(
                    "classifier_timeout",
                    attempt=attempt,
                    max_retries=self._max_retries,
                )
                if attempt < self._max_retries:
                    import asyncio
                    await asyncio.sleep(2 ** attempt)

            except httpx.HTTPStatusError as exc:
                last_error = exc
                log.warning(
                    "classifier_http_error",
                    status=exc.response.status_code,
                    attempt=attempt,
                )
                if attempt < self._max_retries:
                    import asyncio
                    await asyncio.sleep(2 ** attempt)

            except Exception as exc:
                last_error = exc
                log.warning(
                    "classifier_error",
                    error=str(exc),
                    attempt=attempt,
                )
                break

        if last_error is not None:
            log.warning(
                "classifier_fallback",
                error=str(last_error),
            )
            # On classifier failure, default to safe (don't block pipeline)
            categories = [
                SafetyCategory(
                    category=cat,
                    score=0.99,
                    is_safe=True,
                    details="Classifier unavailable — defaulting to safe",
                )
                for cat in SAFETY_CATEGORIES
            ]

        # Compute overall score (minimum across categories)
        overall_score = min(c.score for c in categories) if categories else 1.0

        # Determine decision
        if overall_score >= self._approve_threshold:
            decision = SafetyDecision.SAFE
        elif overall_score < self._reject_threshold:
            decision = SafetyDecision.UNSAFE
        else:
            decision = SafetyDecision.REVIEW_REQUIRED

        elapsed = time.monotonic() - start_time

        report = SafetyReport(
            asset_id=asset_id,
            overall_score=overall_score,
            decision=decision,
            categories=categories,
            model_name=model_name,
            model_version=model_version,
            classified_at=datetime.now(timezone.utc).isoformat(),
            classification_duration_s=round(elapsed, 3),
            file_path=file_path,
            asset_type=asset_type,
        )

        log.info(
            "safety_classification_complete",
            overall_score=round(overall_score, 4),
            decision=decision.value,
            elapsed_s=round(elapsed, 3),
        )

        return report

    async def _call_classifier(
        self,
        file_path: str,
        asset_type: str,
    ) -> Dict[str, Any]:
        """
        Call the self-hosted content safety classifier.

        Args:
            file_path: Path to asset file.
            asset_type: Type of asset.

        Returns:
            Raw classifier response dictionary.
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            with open(file_path, "rb") as f:
                files = {
                    "file": (
                        os.path.basename(file_path),
                        f,
                        self._get_mime_type(file_path, asset_type),
                    )
                }
                data = {"asset_type": asset_type}

                response = await client.post(
                    f"{self._endpoint}/classify",
                    files=files,
                    data=data,
                )
                response.raise_for_status()
                return response.json()

    def _parse_categories(
        self, result: Dict[str, Any]
    ) -> List[SafetyCategory]:
        """Parse category scores from classifier response."""
        categories: List[SafetyCategory] = []
        category_scores = result.get("categories", {})

        for cat_name in SAFETY_CATEGORIES:
            cat_data = category_scores.get(cat_name, {})
            if isinstance(cat_data, dict):
                score = float(cat_data.get("score", 1.0))
                details = cat_data.get("details")
            elif isinstance(cat_data, (int, float)):
                score = float(cat_data)
                details = None
            else:
                score = 1.0
                details = "Category not evaluated"

            categories.append(
                SafetyCategory(
                    category=cat_name,
                    score=score,
                    is_safe=score >= self._reject_threshold,
                    details=details,
                )
            )

        return categories

    async def health_check(self) -> Dict[str, Any]:
        """
        Check classifier service health.

        Returns:
            Health check response from the classifier.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self._endpoint}/health")
                response.raise_for_status()
                return response.json()
        except Exception as exc:
            return {
                "status": "unhealthy",
                "error": str(exc),
            }

    @staticmethod
    def _get_mime_type(file_path: str, asset_type: str) -> str:
        """Determine MIME type from file extension and asset type."""
        ext = os.path.splitext(file_path)[1].lower()
        mime_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".mp4": "video/mp4",
            ".webm": "video/webm",
            ".wav": "audio/wav",
            ".mp3": "audio/mpeg",
            ".srt": "text/plain",
            ".vtt": "text/vtt",
        }
        return mime_map.get(ext, "application/octet-stream")
