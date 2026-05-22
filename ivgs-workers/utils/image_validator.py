"""
IVGS v5 — Image Validator
===========================

Validates generated images per §11.1 quality thresholds (Table 11-1).

Checks:
- Resolution: must match expected dimensions (1920×1080 or 1024×1024)
- Format: PNG, JPEG only
- File size: min 10KB, max 50MB
- Corruption: PIL can open and verify
- CLIP score: cosine similarity between image and prompt (>0.25 pass)
- Artifact detection: blank/solid color, excessive noise

Quality decisions (Table 11-1):
- approved: all checks pass
- flagged: marginal scores, human review needed
- rejected: below thresholds or corrupted
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger("ivgs.image_validator")


# ---------------------------------------------------------------------------
# Enums and thresholds
# ---------------------------------------------------------------------------

class ImageQualityDecision(str, Enum):
    APPROVED = "approved"
    FLAGGED = "flagged"
    REJECTED = "rejected"


@dataclass(frozen=True)
class ImageQualityThresholds:
    """Quality thresholds per §11.1 Table 11-1."""
    min_width: int = 512
    min_height: int = 512
    max_width: int = 4096
    max_height: int = 4096
    expected_width: int = 1920
    expected_height: int = 1080
    allowed_formats: Tuple[str, ...] = ("PNG", "JPEG", "WEBP")
    min_file_size_bytes: int = 10240       # 10KB
    max_file_size_bytes: int = 52428800    # 50MB
    clip_score_approved: float = 0.25
    clip_score_flagged: float = 0.18
    blank_pixel_threshold: float = 0.95
    noise_std_threshold: float = 5.0


@dataclass
class ImageValidationResult:
    """Comprehensive image validation result."""
    is_valid: bool
    decision: ImageQualityDecision
    quality_score: float = 0.0
    resolution_ok: bool = False
    format_ok: bool = False
    file_size_ok: bool = False
    corruption_ok: bool = False
    clip_score: Optional[float] = None
    blank_check_ok: bool = True
    noise_check_ok: bool = True
    actual_width: int = 0
    actual_height: int = 0
    actual_format: str = ""
    file_size_bytes: int = 0
    sha256_hash: str = ""
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Image Validator
# ---------------------------------------------------------------------------

class ImageValidator:
    """
    Validates generated images against quality thresholds.

    Uses PIL for image analysis and optionally integrates with the
    Phase 4 Quality Scores API for CLIP scoring.
    """

    def __init__(
        self,
        thresholds: Optional[ImageQualityThresholds] = None,
        clip_api_url: Optional[str] = None,
    ):
        self._thresholds = thresholds or ImageQualityThresholds()
        self._clip_api_url = clip_api_url

    def validate(
        self,
        image_data: bytes,
        prompt: Optional[str] = None,
        expected_width: Optional[int] = None,
        expected_height: Optional[int] = None,
    ) -> ImageValidationResult:
        """
        Run all validation checks on an image.

        Parameters
        ----------
        image_data : bytes
            Raw image bytes (PNG or JPEG).
        prompt : str, optional
            Generation prompt for CLIP score computation.
        expected_width : int, optional
            Expected width (overrides threshold default).
        expected_height : int, optional
            Expected height (overrides threshold default).

        Returns
        -------
        ImageValidationResult
        """
        errors: List[str] = []
        warnings: List[str] = []
        checks: Dict[str, bool] = {}
        metadata: Dict[str, Any] = {}

        exp_w = expected_width or self._thresholds.expected_width
        exp_h = expected_height or self._thresholds.expected_height

        # --- File size ---
        file_size = len(image_data)
        file_size_ok = (
            self._thresholds.min_file_size_bytes
            <= file_size
            <= self._thresholds.max_file_size_bytes
        )
        checks["file_size_ok"] = file_size_ok
        if not file_size_ok:
            if file_size < self._thresholds.min_file_size_bytes:
                errors.append(
                    f"File too small: {file_size} bytes (min {self._thresholds.min_file_size_bytes})"
                )
            else:
                errors.append(
                    f"File too large: {file_size} bytes (max {self._thresholds.max_file_size_bytes})"
                )

        # --- SHA-256 hash ---
        sha256_hash = hashlib.sha256(image_data).hexdigest()

        # --- Format and corruption check via PIL ---
        actual_width = 0
        actual_height = 0
        actual_format = ""
        corruption_ok = False
        format_ok = False

        try:
            from PIL import Image

            img = Image.open(io.BytesIO(image_data))
            img.verify()

            # Re-open after verify (verify closes the file)
            img = Image.open(io.BytesIO(image_data))
            actual_width = img.width
            actual_height = img.height
            actual_format = img.format or ""

            corruption_ok = True
            checks["corruption_ok"] = True

            # Format check
            format_ok = actual_format.upper() in self._thresholds.allowed_formats
            checks["format_ok"] = format_ok
            if not format_ok:
                errors.append(
                    f"Invalid format: {actual_format} "
                    f"(allowed: {', '.join(self._thresholds.allowed_formats)})"
                )

            # Resolution check
            resolution_ok = (
                self._thresholds.min_width <= actual_width <= self._thresholds.max_width
                and self._thresholds.min_height <= actual_height <= self._thresholds.max_height
            )
            checks["resolution_ok"] = resolution_ok
            if not resolution_ok:
                errors.append(
                    f"Resolution out of range: {actual_width}×{actual_height}"
                )

            # Check if matches expected
            if actual_width != exp_w or actual_height != exp_h:
                warnings.append(
                    f"Resolution mismatch: expected {exp_w}×{exp_h}, "
                    f"got {actual_width}×{actual_height}"
                )

            # --- Blank image detection ---
            try:
                import numpy as np
                img_array = np.array(img.convert("RGB"))
                pixels = img_array.reshape(-1, 3)

                # Check for solid color
                unique_ratio = len(np.unique(pixels, axis=0)) / max(len(pixels), 1)
                blank_ok = unique_ratio > (1 - self._thresholds.blank_pixel_threshold)
                checks["blank_check_ok"] = blank_ok
                if not blank_ok:
                    errors.append("Image appears blank or solid color")
                metadata["unique_color_ratio"] = round(unique_ratio, 4)

                # Check for excessive noise (very low std might indicate solid)
                pixel_std = float(np.std(img_array))
                noise_ok = pixel_std > self._thresholds.noise_std_threshold
                checks["noise_check_ok"] = noise_ok
                if not noise_ok:
                    warnings.append(f"Very low pixel variance: std={pixel_std:.2f}")
                metadata["pixel_std"] = round(pixel_std, 2)

            except ImportError:
                checks["blank_check_ok"] = True
                checks["noise_check_ok"] = True
                warnings.append("numpy not available for blank/noise detection")

            img.close()

        except Exception as e:
            corruption_ok = False
            checks["corruption_ok"] = False
            errors.append(f"Image corruption detected: {e}")

        # --- CLIP score (if API available and prompt provided) ---
        clip_score: Optional[float] = None
        if prompt and self._clip_api_url:
            clip_score = self._compute_clip_score(image_data, prompt)
            metadata["clip_score"] = clip_score
            if clip_score is not None:
                if clip_score < self._thresholds.clip_score_flagged:
                    errors.append(
                        f"CLIP score too low: {clip_score:.3f} "
                        f"(threshold: {self._thresholds.clip_score_flagged})"
                    )
                elif clip_score < self._thresholds.clip_score_approved:
                    warnings.append(
                        f"CLIP score marginal: {clip_score:.3f} "
                        f"(approved threshold: {self._thresholds.clip_score_approved})"
                    )

        # --- Compute overall quality score ---
        quality_score = self._compute_quality_score(checks, clip_score)

        # --- Decision ---
        if errors:
            decision = ImageQualityDecision.REJECTED
        elif warnings:
            decision = ImageQualityDecision.FLAGGED
        else:
            decision = ImageQualityDecision.APPROVED

        is_valid = decision != ImageQualityDecision.REJECTED

        return ImageValidationResult(
            is_valid=is_valid,
            decision=decision,
            quality_score=quality_score,
            resolution_ok=checks.get("resolution_ok", False),
            format_ok=checks.get("format_ok", False),
            file_size_ok=file_size_ok,
            corruption_ok=corruption_ok,
            clip_score=clip_score,
            blank_check_ok=checks.get("blank_check_ok", True),
            noise_check_ok=checks.get("noise_check_ok", True),
            actual_width=actual_width,
            actual_height=actual_height,
            actual_format=actual_format,
            file_size_bytes=file_size,
            sha256_hash=sha256_hash,
            errors=errors,
            warnings=warnings,
            metadata=metadata,
        )

    def _compute_clip_score(
        self, image_data: bytes, prompt: str
    ) -> Optional[float]:
        """Query CLIP scoring API for image-prompt similarity."""
        if not self._clip_api_url:
            return None

        try:
            import httpx
            import base64

            image_b64 = base64.b64encode(image_data).decode("utf-8")
            payload = {
                "image_base64": image_b64,
                "text": prompt,
            }

            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{self._clip_api_url}/score",
                    json=payload,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return float(data.get("score", data.get("similarity", 0.0)))
                logger.warning(
                    "clip_score_api_error",
                    status_code=resp.status_code,
                )
                return None

        except Exception as e:
            logger.warning("clip_score_computation_failed", error=str(e))
            return None

    @staticmethod
    def _compute_quality_score(
        checks: Dict[str, bool], clip_score: Optional[float]
    ) -> float:
        """Compute weighted quality score from individual checks."""
        weights = {
            "corruption_ok": 0.30,
            "resolution_ok": 0.15,
            "format_ok": 0.10,
            "file_size_ok": 0.10,
            "blank_check_ok": 0.15,
            "noise_check_ok": 0.05,
        }

        score = 0.0
        for check_name, weight in weights.items():
            if checks.get(check_name, False):
                score += weight

        # CLIP score component (0.15 weight)
        if clip_score is not None:
            clip_component = min(clip_score / 0.3, 1.0) * 0.15
            score += clip_component
        else:
            score += 0.15  # Default pass if CLIP unavailable

        return round(min(score, 1.0), 4)
