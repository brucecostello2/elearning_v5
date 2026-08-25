"""
IVGS v5 — person detection on an animation reference image  (WP-44 Task 5)
============================================================================

Wan2.2-Animate is **pose reenactment**. It takes a reference image and a
driving video and transfers the driver's motion onto the subject in the
reference. If the reference has no subject — an equation card, a diagram, a
title slate — there is nothing to animate, and the model does not refuse. It
hallucinates a body into the picture and returns five minutes of GPU time
spent on a figure that was never in the storyboard.

WP-46 already refuses a *missing* reference image by name
(``WanAnimateInputError``). This module lets the same refusal fire for a
reference image that is present and unusable, before any GPU is reserved.

THE DETECTOR
------------
YOLOv10m, COCO class 0 (``person``), run on CPU through onnxruntime.

The weights are **the engine's own**. ``yolov10m.onnx`` is one of the nine
certified component bundles that WP-46's addendum fetched from the MBCP serving
plane — manifest HMAC verified, bundle digest verified, per-file SHA-256
verified on fetch and re-verified on node-03 (23/23 OK). It is the same model
the certified Wan graph loads in its ``OnnxDetectionModelLoader`` /
``PoseAndFaceDetection`` nodes to find the subject it is about to animate. So
this guard asks exactly the question the engine will ask, with exactly the
model the engine will ask it with — one step earlier, and on a CPU instead of a
GPU reservation and a render.

Measured on node-01 (8 vCPU, single intra-op thread, warm session):
**~1.3 s per 1920×1080 still**. Against the 256 s that WP-46's addendum
measured for one real Wan2.2-Animate render, that is 0.5% of the cost of the
thing it prevents. Session load adds ~0.3 s once per task.

Running it in-process rather than as a detection graph on the ComfyUI engine is
deliberate: a graph submission needs the engine reachable, a queue slot and a
parse of ComfyUI's output shape, all to answer a yes/no that a 61 MB ONNX file
answers locally in ~40 ms.

HONESTY
-------
There are three outcomes, and they are three, not two:

  * ``present``   — a person was detected above the confidence floor.
  * ``absent``    — the detector ran and found no person. This is the only
                    outcome that fails a scene.
  * ``unavailable`` — the detector could NOT run (no onnxruntime, no weights
                    file, a load or inference error). The scene is **not**
                    failed, because "we did not look" is not "there is nobody
                    there". It is logged and recorded as a missing check, and
                    the render proceeds as it did before this guard existed.

That asymmetry is the point. A guard that fails scenes when its own detector is
missing would be the same defect as a gate that passes assets when its own
checker is missing, pointed the other way.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger("ivgs.person_detector")

#: The MBCP-provenance detection bundle WP-46 fetched and verified. Shared
#: storage, so the same file backs every node that runs the animation queue.
DEFAULT_MODEL_PATH = os.getenv(
    "IVGS_PERSON_DETECTOR_MODEL",
    "/mnt/ivgs-shared/wan-weights-staging/detection/yolov10m.onnx",
)

#: COCO class id for "person". YOLOv10m's exported metadata numbers its classes
#: 0..79 in COCO order.
PERSON_CLASS_ID = 0

#: Detection confidence floor. YOLOv10 is NMS-free and emits 300 ranked boxes
#: per image; the tail is noise at ~1e-3. 0.25 is the ultralytics default and
#: separates the two populations by two orders of magnitude on real inputs.
DEFAULT_CONFIDENCE = 0.25

#: The exported model's fixed input geometry.
INPUT_SIZE = 640


class PersonPresence(str, Enum):
    PRESENT = "present"
    ABSENT = "absent"
    UNAVAILABLE = "unavailable"


@dataclass
class PersonDetectionResult:
    presence: PersonPresence
    person_count: int = 0
    best_confidence: float = 0.0
    confidence_threshold: float = DEFAULT_CONFIDENCE
    model: str = ""
    elapsed_ms: float = 0.0
    reason: str = ""
    detections: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def ran(self) -> bool:
        return self.presence is not PersonPresence.UNAVAILABLE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "presence": self.presence.value,
            "person_count": self.person_count,
            "best_confidence": round(self.best_confidence, 4),
            "confidence_threshold": self.confidence_threshold,
            "model": self.model,
            "elapsed_ms": round(self.elapsed_ms, 2),
            "reason": self.reason,
            "detections": self.detections,
        }


class PersonDetector:
    """YOLOv10m person detection over image bytes."""

    def __init__(
        self,
        model_path: str = DEFAULT_MODEL_PATH,
        confidence: float = DEFAULT_CONFIDENCE,
    ) -> None:
        self._model_path = model_path
        self._confidence = confidence
        self._session: Optional[Any] = None
        self._input_name: str = "images"
        self._unavailable_reason: str = ""

    # -- session ------------------------------------------------------------

    def _ensure_session(self) -> bool:
        """Load the ONNX session once. A failure is remembered, not retried."""
        if self._session is not None:
            return True
        if self._unavailable_reason:
            return False

        try:
            import onnxruntime as ort
        except ImportError as exc:
            self._unavailable_reason = f"onnxruntime is not installed ({exc})"
            return False

        if not os.path.isfile(self._model_path):
            self._unavailable_reason = (
                f"detection weights not found at {self._model_path}"
            )
            return False

        try:
            opts = ort.SessionOptions()
            # One thread: this runs inside a Celery worker that is already
            # bracketing a GPU reservation. It must not fight the render for
            # CPU any more than it fights it for VRAM. Measured cost of that
            # choice: ~1.3 s single-threaded vs ~0.56 s across 8 threads — a
            # 0.7 s difference against a 256 s render, which is not worth
            # contending for.
            opts.intra_op_num_threads = 1
            opts.inter_op_num_threads = 1
            session = ort.InferenceSession(
                self._model_path,
                sess_options=opts,
                providers=["CPUExecutionProvider"],
            )
        except Exception as exc:  # noqa: BLE001 - recorded, never fatal
            self._unavailable_reason = f"onnxruntime session failed: {exc}"
            return False

        self._session = session
        self._input_name = session.get_inputs()[0].name
        return True

    # -- detection ----------------------------------------------------------

    def detect(self, image_data: bytes) -> PersonDetectionResult:
        """Is there a person in these image bytes?

        Never raises. Every failure path returns ``UNAVAILABLE`` with a reason.
        """
        started = time.monotonic()

        if not self._ensure_session():
            return PersonDetectionResult(
                presence=PersonPresence.UNAVAILABLE,
                model=self._model_path,
                confidence_threshold=self._confidence,
                reason=self._unavailable_reason,
                elapsed_ms=(time.monotonic() - started) * 1000.0,
            )

        try:
            import numpy as np
            from PIL import Image
        except ImportError as exc:
            return PersonDetectionResult(
                presence=PersonPresence.UNAVAILABLE,
                model=self._model_path,
                confidence_threshold=self._confidence,
                reason=f"numpy/Pillow unavailable ({exc})",
                elapsed_ms=(time.monotonic() - started) * 1000.0,
            )

        try:
            import io

            image = Image.open(io.BytesIO(image_data)).convert("RGB")
            tensor, scale, pad = self._letterbox(image, np)
            outputs = self._session.run(None, {self._input_name: tensor})[0]
        except Exception as exc:  # noqa: BLE001
            return PersonDetectionResult(
                presence=PersonPresence.UNAVAILABLE,
                model=self._model_path,
                confidence_threshold=self._confidence,
                reason=f"inference failed: {type(exc).__name__}: {exc}",
                elapsed_ms=(time.monotonic() - started) * 1000.0,
            )

        # YOLOv10 is NMS-free: output is (1, 300, 6) = x1,y1,x2,y2,score,class,
        # already sorted by score. No suppression pass is needed or wanted.
        boxes = outputs[0]
        detections: List[Dict[str, Any]] = []
        best = 0.0
        for row in boxes:
            cls = int(row[5])
            score = float(row[4])
            if cls != PERSON_CLASS_ID:
                continue
            best = max(best, score)
            if score < self._confidence:
                continue
            x1, y1, x2, y2 = (float(v) for v in row[:4])
            detections.append({
                "confidence": round(score, 4),
                "box_xyxy": [
                    round((x1 - pad[0]) / scale, 1),
                    round((y1 - pad[1]) / scale, 1),
                    round((x2 - pad[0]) / scale, 1),
                    round((y2 - pad[1]) / scale, 1),
                ],
            })

        elapsed_ms = (time.monotonic() - started) * 1000.0
        presence = (
            PersonPresence.PRESENT if detections else PersonPresence.ABSENT
        )
        result = PersonDetectionResult(
            presence=presence,
            person_count=len(detections),
            best_confidence=best,
            confidence_threshold=self._confidence,
            model=os.path.basename(self._model_path),
            elapsed_ms=elapsed_ms,
            detections=detections[:8],
        )
        logger.info(
            "person_detection",
            presence=presence.value,
            person_count=result.person_count,
            best_confidence=round(best, 4),
            elapsed_ms=round(elapsed_ms, 1),
        )
        return result

    # -- preprocessing ------------------------------------------------------

    @staticmethod
    def _letterbox(image: Any, np: Any):
        """Resize preserving aspect onto a 640×640 grey canvas.

        The ultralytics export expects letterboxed, 0-1 scaled, CHW float32
        input at 640×640 with 114-grey padding. Stretching to a square instead
        would distort the aspect and cost recall on the very 16:9 stills this
        guard is checking.
        """
        w, h = image.size
        scale = min(INPUT_SIZE / w, INPUT_SIZE / h)
        new_w, new_h = int(round(w * scale)), int(round(h * scale))
        resized = image.resize((new_w, new_h))

        from PIL import Image as _Image

        canvas = _Image.new("RGB", (INPUT_SIZE, INPUT_SIZE), (114, 114, 114))
        pad = ((INPUT_SIZE - new_w) // 2, (INPUT_SIZE - new_h) // 2)
        canvas.paste(resized, pad)

        arr = np.asarray(canvas, dtype=np.float32) / 255.0
        return arr.transpose(2, 0, 1)[None], scale, pad
