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
- flagged: marginal scores, human review needed, OR a check could not run
- rejected: below thresholds or corrupted

WP-44 — what a quality score is allowed to claim
------------------------------------------------

The first e2e run shipped sixteen deformed images with ``quality_score: 1.0``.
Nothing in that number was earned. Three separate mechanisms manufactured it
(swallow register **instance 24**):

  1. ``numpy`` was absent from the workers image, so the blank/noise block hit
     ``ImportError`` and set ``blank_check_ok = noise_check_ok = True`` — two
     checks that never ran, recorded as passed. numpy is now a declared
     dependency (``requirements.txt``), but the import guard stays: if the
     import ever fails again the checks report themselves **missing**, they do
     not report themselves passed.
  2. The CLIP endpoint stage 3 constructs did not exist. Every call 404'd,
     ``_compute_clip_score`` returned ``None``, and ``None`` was indistinguishable
     from "not requested".
  3. ``_compute_quality_score`` awarded ``+0.15`` — the CLIP weight, in full —
     precisely when CLIP had not been computed. A missing scorer paid better
     than a marginal one.

The rules this module now enforces:

  * **An unavailable scorer contributes nothing.** Not its weight, not a
    default, not a fallback constant. It is removed from the denominator too,
    so ``quality_score`` means *"of the checks that ran, this fraction passed"*
    and never silently absorbs an un-run check as a pass.
  * **A score computed with checks missing says which.** ``checks_missing`` names
    them, ``check_coverage`` gives the fraction of the scoring weight that was
    actually exercised, and ``quality_score_complete`` is False.
  * **A gate that could not run all its checks does not approve.** Missing
    checks cap the decision at ``flagged``. The one thing the quality gate
    exists to do is withhold approval; it may not certify what it did not
    measure.
  * **CLIP records a status, not a null.** ``clip_status`` is one of
    ``scored`` / ``unavailable`` / ``not_requested``, and the serialized
    ``metadata["clip_score"]`` is the float when scored and the literal string
    ``"unavailable"`` otherwise — never a bare ``None`` that reads as a zero or
    as a score.
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


class ClipStatus(str, Enum):
    """Why ``clip_score`` holds what it holds.

    ``NOT_REQUESTED`` — no prompt, or CLIP scoring disabled for this run.
    ``UNAVAILABLE``   — CLIP was asked for and could not be obtained (no
                        endpoint configured, transport error, non-200, or an
                        unparseable body). Contributes NOTHING to the score.
    ``SCORED``        — a real number came back from a real scorer.
    """
    NOT_REQUESTED = "not_requested"
    UNAVAILABLE = "unavailable"
    SCORED = "scored"


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


#: Scoring weights. A check that does not run is removed from BOTH the
#: numerator and the denominator — see ``_compute_quality_score``.
CHECK_WEIGHTS: Dict[str, float] = {
    "corruption_ok": 0.30,
    "resolution_ok": 0.15,
    "format_ok": 0.10,
    "file_size_ok": 0.10,
    "blank_check_ok": 0.15,
    "noise_check_ok": 0.05,
    "clip_ok": 0.15,
}

@dataclass
class ImageValidationResult:
    """Comprehensive image validation result.

    ``quality_score`` is normalised over the checks that ACTUALLY RAN. Read it
    together with ``checks_missing`` / ``check_coverage``: a 1.0 across two of
    seven checks is not the same claim as a 1.0 across seven of seven, and
    ``quality_score_complete`` is the flag that separates them.
    """
    is_valid: bool
    decision: ImageQualityDecision
    quality_score: float = 0.0
    resolution_ok: bool = False
    format_ok: bool = False
    file_size_ok: bool = False
    corruption_ok: bool = False
    clip_score: Optional[float] = None
    clip_status: str = ClipStatus.NOT_REQUESTED.value
    blank_check_ok: bool = True
    noise_check_ok: bool = True
    actual_width: int = 0
    actual_height: int = 0
    actual_format: str = ""
    file_size_bytes: int = 0
    sha256_hash: str = ""
    checks_run: List[str] = field(default_factory=list)
    checks_missing: List[str] = field(default_factory=list)
    check_coverage: float = 0.0
    quality_score_complete: bool = False
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def scoring_details(self) -> Dict[str, Any]:
        """The record that goes to the Quality Scores API.

        Everything a reviewer needs to know whether the number means anything:
        the per-check outcomes, what was NOT measured, how much of the scoring
        weight was exercised, and CLIP's status alongside its value.
        """
        return {
            "clip_score": (
                self.clip_score
                if self.clip_status == ClipStatus.SCORED.value
                else self.clip_status
            ),
            "clip_status": self.clip_status,
            "resolution_ok": self.resolution_ok,
            "format_ok": self.format_ok,
            "file_size_ok": self.file_size_ok,
            "corruption_ok": self.corruption_ok,
            "blank_check_ok": self.blank_check_ok,
            "noise_check_ok": self.noise_check_ok,
            "checks_run": list(self.checks_run),
            "checks_missing": list(self.checks_missing),
            "check_coverage": self.check_coverage,
            "quality_score_complete": self.quality_score_complete,
            "actual_width": self.actual_width,
            "actual_height": self.actual_height,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


# ---------------------------------------------------------------------------
# Image Validator
# ---------------------------------------------------------------------------

class ImageValidator:
    """
    Validates generated images against quality thresholds.

    Uses PIL for image analysis and integrates with the CLIP scoring service
    (WP-44, node-05) for image/prompt similarity. Absent that service, CLIP is
    recorded ``unavailable`` and is excluded from the score entirely.
    """

    def __init__(
        self,
        thresholds: Optional[ImageQualityThresholds] = None,
        clip_api_url: Optional[str] = None,
        clip_auth_token: Optional[str] = None,
    ):
        """
        clip_auth_token
            Bearer token for the scoring route. ``/api/v1/clip/score`` is
            service-token-or-privileged-user, like every other worker→API
            route on this fleet, so the worker must present the same
            ``IVGS_SERVICE_TOKEN`` it uses for checkpoints and asset uploads.
            Omitted, the call is unauthenticated, the route answers **403**,
            and CLIP is recorded ``unavailable`` — honest, and useless. This
            was measured live on 2026-08-26 before the token was threaded
            through, which is exactly the kind of miss the old code's
            free +0.15 would have hidden.
        """
        self._thresholds = thresholds or ImageQualityThresholds()
        self._clip_api_url = clip_api_url
        self._clip_auth_token = clip_auth_token

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
        missing: List[str] = []
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

            # --- Blank / noise detection ---
            # numpy is a declared worker dependency (WP-44). If the import ever
            # fails again, the two checks it powers are MISSING, not passed.
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

            except ImportError as exc:
                missing.extend(["blank_check_ok", "noise_check_ok"])
                warnings.append(
                    f"CHECK MISSING — blank/solid-colour and pixel-variance detection "
                    f"did not run: numpy is unavailable in this image ({exc}). "
                    f"Neither check passed; neither was performed."
                )
                logger.warning("image_check_missing_numpy", error=str(exc))

            img.close()

        except Exception as e:
            corruption_ok = False
            checks["corruption_ok"] = False
            errors.append(f"Image corruption detected: {e}")
            # PIL failed, so format/resolution/blank/noise never got a verdict.
            # They are missing, not failed and not passed.
            for name in ("format_ok", "resolution_ok", "blank_check_ok", "noise_check_ok"):
                if name not in checks:
                    missing.append(name)

        # --- CLIP score ---
        clip_score: Optional[float] = None
        clip_status = ClipStatus.NOT_REQUESTED

        if prompt and self._clip_api_url:
            clip_score, clip_status = self._compute_clip_score(image_data, prompt)

        if clip_status is ClipStatus.SCORED and clip_score is not None:
            checks["clip_ok"] = clip_score >= self._thresholds.clip_score_flagged
            metadata["clip_score"] = clip_score
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
        else:
            # Not scored: excluded from the score entirely. No free 0.15.
            missing.append("clip_ok")
            metadata["clip_score"] = clip_status.value
            if clip_status is ClipStatus.UNAVAILABLE:
                warnings.append(
                    "CHECK MISSING — CLIP image/prompt similarity did not run: "
                    "the scoring service was unreachable or returned no usable "
                    "score. It contributes nothing to quality_score."
                )
            else:
                warnings.append(
                    "CHECK MISSING — CLIP image/prompt similarity was not "
                    "requested for this asset (no prompt or scoring disabled). "
                    "It contributes nothing to quality_score."
                )

        metadata["clip_status"] = clip_status.value

        # --- Compute overall quality score over the checks that ran ---
        quality_score, coverage = self._compute_quality_score(checks, missing)
        metadata["check_coverage"] = coverage
        metadata["checks_missing"] = list(missing)

        # --- Decision ---
        # A gate that could not run all of its checks may not approve. It is the
        # rubber-stamp defect (swallow register instance 24) that this clause
        # exists to make impossible.
        if errors:
            decision = ImageQualityDecision.REJECTED
        elif missing or warnings:
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
            clip_status=clip_status.value,
            blank_check_ok=checks.get("blank_check_ok", False),
            noise_check_ok=checks.get("noise_check_ok", False),
            actual_width=actual_width,
            actual_height=actual_height,
            actual_format=actual_format,
            file_size_bytes=file_size,
            sha256_hash=sha256_hash,
            checks_run=sorted(checks.keys()),
            checks_missing=sorted(set(missing)),
            check_coverage=coverage,
            quality_score_complete=not missing,
            errors=errors,
            warnings=warnings,
            metadata=metadata,
        )

    def _compute_clip_score(
        self, image_data: bytes, prompt: str
    ) -> Tuple[Optional[float], ClipStatus]:
        """Query the CLIP scoring service for image/prompt similarity.

        Returns ``(score, SCORED)`` only when a real number came back. Every
        other outcome — no endpoint, transport failure, non-200, unparseable or
        absent ``score`` field — returns ``(None, UNAVAILABLE)``. The caller
        must not treat UNAVAILABLE as any kind of pass.
        """
        if not self._clip_api_url:
            return None, ClipStatus.UNAVAILABLE

        try:
            import base64

            import httpx

            image_b64 = base64.b64encode(image_data).decode("utf-8")
            payload = {
                "image_base64": image_b64,
                "text": prompt,
            }
            headers = {"Content-Type": "application/json"}
            if self._clip_auth_token:
                headers["Authorization"] = f"Bearer {self._clip_auth_token}"

            with httpx.Client(timeout=30.0, headers=headers) as client:
                resp = client.post(
                    f"{self._clip_api_url}/score",
                    json=payload,
                )
                if resp.status_code != 200:
                    logger.warning(
                        "clip_score_unavailable",
                        reason="http_status",
                        status_code=resp.status_code,
                        url=self._clip_api_url,
                    )
                    return None, ClipStatus.UNAVAILABLE

                data = resp.json()
                raw = data.get("score", data.get("similarity"))
                if raw is None:
                    logger.warning(
                        "clip_score_unavailable",
                        reason="no_score_field",
                        url=self._clip_api_url,
                    )
                    return None, ClipStatus.UNAVAILABLE
                return float(raw), ClipStatus.SCORED

        except Exception as e:
            logger.warning(
                "clip_score_unavailable", reason="exception", error=str(e)
            )
            return None, ClipStatus.UNAVAILABLE

    @staticmethod
    def _compute_quality_score(
        checks: Dict[str, bool], missing: List[str]
    ) -> Tuple[float, float]:
        """Weighted quality score over the checks that ACTUALLY RAN.

        Returns ``(quality_score, check_coverage)``.

        A missing check is removed from the numerator *and* the denominator, so
        it can neither award nor withhold credit. ``check_coverage`` is the
        fraction of the total scoring weight that was exercised — the number
        that tells a reader how much ``quality_score`` is worth.

        With every check present this is identical to the original weighted
        sum. With CLIP absent it is emphatically NOT the original's
        ``score += 0.15  # Default pass if CLIP unavailable``.
        """
        missing_set = set(missing)
        total_weight = sum(CHECK_WEIGHTS.values())

        ran_weight = 0.0
        earned = 0.0
        for name, weight in CHECK_WEIGHTS.items():
            if name in missing_set or name not in checks:
                continue
            ran_weight += weight
            if checks[name]:
                earned += weight

        if ran_weight <= 0.0:
            # Nothing measurable ran. There is no score to report.
            return 0.0, 0.0

        return round(earned / ran_weight, 4), round(ran_weight / total_weight, 4)
