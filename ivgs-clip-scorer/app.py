"""
IVGS v5 — CLIP image/text scoring service  (WP-44-QUALITY, node-05)
====================================================================

An image-text scoring service. One model, one job: return the cosine
similarity between an image and a piece of text, and say nothing at all when
it cannot.

WHY IT EXISTS
-------------
IVGS's image quality gate has always had a CLIP term. It has never had a CLIP
model. `tasks/stage3_images.py` constructed a scorer URL, the URL 404'd, and
the validator credited the *full* CLIP weight for the miss — so sixteen
deformed images from the first e2e run carry `quality_score: 1.0`
(swallow register instance 24). This is the missing half.

THE MODEL
---------
`openai/clip-vit-base-patch32` — the original OpenAI CLIP ViT-B/32, and the
model the CLIPScore literature is calibrated on. It is chosen over the larger
variants deliberately: IVGS's thresholds (`clip_score_approved: 0.25`,
`clip_score_flagged: 0.18`, in `configs/media_generation.yml` and
`ImageQualityThresholds`) are on the raw-cosine scale that ViT-B/32 produces.
Swapping in a bigger tower would shift that scale and silently re-calibrate
every threshold in the fleet, which is a change that needs its own measurement
pass, not a default.

Weights are **baked into the image at build time** (`Dockerfile`), so the
running container needs no network and no HuggingFace reachability. The exact
revision is pinned and reported by `/health`.

HONESTY CONTRACT
----------------
* `/score` returns a score or an error. There is no fallback constant, no
  "conservative default", no `0.80`-on-exception. A model that did not load
  yields 503 for every request, forever, loudly.
* `/health` reports `model_loaded` from the actual object, not from the fact
  that the process is up.
* The score is the raw cosine similarity of the L2-normalised embeddings, in
  [-1, 1]. It is NOT the 2.5·max(cos,0) "CLIPScore" rescaling and it is NOT a
  softmax over candidate captions — both are transformations IVGS's thresholds
  are not calibrated for. `scale` in the response says which convention was
  used so a future re-calibration can tell.
"""

from __future__ import annotations

import base64
import binascii
import io
import logging
import os
import time
from typing import Any, Dict, List, Optional

import torch
from fastapi import FastAPI, HTTPException, status
from PIL import Image
from pydantic import BaseModel, Field
from transformers import CLIPModel, CLIPProcessor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("ivgs.clip_scorer")

MODEL_ID = os.getenv("IVGS_CLIP_MODEL", "openai/clip-vit-base-patch32")
MODEL_DIR = os.getenv("IVGS_CLIP_MODEL_DIR", "/models/clip")
DEVICE = os.getenv("IVGS_CLIP_DEVICE", "cuda" if torch.cuda.is_available() else "cpu")
#: CLIP's text tower is hard-capped at 77 tokens. Longer prompts are truncated
#: by the processor; the response says so rather than pretending the whole
#: prompt was scored.
MAX_TEXT_TOKENS = 77

app = FastAPI(
    title="IVGS CLIP Scorer",
    description="Image/text similarity for the IVGS quality gate (WP-44)",
    version="1.0.0",
)

_state: Dict[str, Any] = {
    "model": None,
    "processor": None,
    "load_error": None,
    "device": DEVICE,
    "loaded_at": None,
}


class ScoreRequest(BaseModel):
    image_base64: str = Field(description="Base64-encoded image bytes")
    text: str = Field(description="Text to compare the image against")


class ScoreResponse(BaseModel):
    score: float
    model: str
    served_by: str
    device: str
    latency_ms: float
    scale: str
    text_truncated: bool
    image_size: List[int]


class BatchScoreRequest(BaseModel):
    """One image against several texts — the shape a re-scoring sweep wants."""
    image_base64: str
    texts: List[str] = Field(min_length=1, max_length=32)


@app.on_event("startup")
def _load_model() -> None:
    """Load once, at startup. A failure here is remembered, not retried away."""
    src = MODEL_DIR if os.path.isdir(MODEL_DIR) else MODEL_ID
    try:
        t0 = time.monotonic()
        model = CLIPModel.from_pretrained(src)
        processor = CLIPProcessor.from_pretrained(src)
        model.eval()
        model.to(DEVICE)
        _state["model"] = model
        _state["processor"] = processor
        _state["loaded_at"] = time.time()
        logger.info(
            "clip_model_loaded src=%s device=%s elapsed_s=%.2f",
            src, DEVICE, time.monotonic() - t0,
        )
    except Exception as exc:  # noqa: BLE001 - recorded and served as 503
        _state["load_error"] = f"{type(exc).__name__}: {exc}"
        logger.error("clip_model_load_failed src=%s error=%s", src, exc)


def _require_model() -> None:
    if _state["model"] is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "code": "MODEL_NOT_LOADED",
                    "message": (
                        "The CLIP model is not loaded; no score can be "
                        "computed. This service does not return a default."
                    ),
                    "load_error": _state["load_error"],
                }
            },
        )


def _decode_image(image_base64: str) -> Image.Image:
    try:
        raw = base64.b64decode(image_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "BAD_IMAGE", "message": f"not base64: {exc}"}},
        )
    try:
        return Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "BAD_IMAGE", "message": f"undecodable: {exc}"}},
        )


def _embed(image: Image.Image, texts: List[str]) -> tuple[torch.Tensor, torch.Tensor, bool]:
    """L2-normalised image and text embeddings, plus whether text was truncated."""
    processor = _state["processor"]
    model = _state["model"]

    tokenized = processor.tokenizer(texts, padding=False, truncation=False)
    truncated = any(len(ids) > MAX_TEXT_TOKENS for ids in tokenized["input_ids"])

    inputs = processor(
        text=texts,
        images=image,
        return_tensors="pt",
        padding=True,
        truncation=True,
        max_length=MAX_TEXT_TOKENS,
    ).to(DEVICE)

    with torch.no_grad():
        image_features = model.get_image_features(pixel_values=inputs["pixel_values"])
        text_features = model.get_text_features(
            input_ids=inputs["input_ids"],
            attention_mask=inputs.get("attention_mask"),
        )

    image_features = image_features / image_features.norm(dim=-1, keepdim=True)
    text_features = text_features / text_features.norm(dim=-1, keepdim=True)
    return image_features, text_features, truncated


@app.post("/score", response_model=ScoreResponse)
def score(req: ScoreRequest) -> ScoreResponse:
    """Cosine similarity between one image and one text."""
    _require_model()
    image = _decode_image(req.image_base64)

    t0 = time.monotonic()
    image_features, text_features, truncated = _embed(image, [req.text])
    similarity = float((image_features @ text_features.T)[0, 0].item())
    latency_ms = round((time.monotonic() - t0) * 1000.0, 2)

    logger.info(
        "scored score=%.4f latency_ms=%.1f size=%dx%d truncated=%s",
        similarity, latency_ms, image.width, image.height, truncated,
    )
    return ScoreResponse(
        score=similarity,
        model=MODEL_ID,
        served_by=os.getenv("IVGS_NODE_NAME", "node-05"),
        device=DEVICE,
        latency_ms=latency_ms,
        scale="raw_cosine_similarity",
        text_truncated=truncated,
        image_size=[image.width, image.height],
    )


@app.post("/score/batch")
def score_batch(req: BatchScoreRequest) -> Dict[str, Any]:
    """One image against several texts, one forward pass for the image."""
    _require_model()
    image = _decode_image(req.image_base64)

    t0 = time.monotonic()
    image_features, text_features, truncated = _embed(image, req.texts)
    sims = (image_features @ text_features.T)[0].tolist()
    latency_ms = round((time.monotonic() - t0) * 1000.0, 2)

    return {
        "scores": [
            {"text": t, "score": float(s)} for t, s in zip(req.texts, sims)
        ],
        "model": MODEL_ID,
        "served_by": os.getenv("IVGS_NODE_NAME", "node-05"),
        "device": DEVICE,
        "latency_ms": latency_ms,
        "scale": "raw_cosine_similarity",
        "text_truncated": truncated,
    }


@app.get("/health")
def health() -> Dict[str, Any]:
    """The real state of the model, not the state of the process."""
    body: Dict[str, Any] = {
        "status": "ok" if _state["model"] is not None else "degraded",
        "model_loaded": _state["model"] is not None,
        "model": MODEL_ID,
        "device": _state["device"],
        "scale": "raw_cosine_similarity",
        "served_by": os.getenv("IVGS_NODE_NAME", "node-05"),
    }
    if _state["load_error"]:
        body["load_error"] = _state["load_error"]
    if torch.cuda.is_available():
        body["cuda"] = {
            "device_name": torch.cuda.get_device_name(0),
            "allocated_mib": round(torch.cuda.memory_allocated(0) / 1048576, 1),
            "reserved_mib": round(torch.cuda.memory_reserved(0) / 1048576, 1),
            "max_allocated_mib": round(torch.cuda.max_memory_allocated(0) / 1048576, 1),
        }
    return body


@app.get("/thresholds")
def thresholds() -> Dict[str, Any]:
    """The scale this service produces, so a consumer can check calibration.

    These are the IVGS image thresholds as of WP-44. They are stated here for
    reference only — this service does not apply them and does not decide.
    """
    return {
        "scale": "raw_cosine_similarity",
        "range": [-1.0, 1.0],
        "calibrated_for": MODEL_ID,
        "ivgs_image_thresholds": {
            "clip_score_approved": 0.25,
            "clip_score_flagged": 0.18,
        },
        "note": (
            "Changing the model changes this scale. Any substitution needs a "
            "re-measurement against banked assets before the thresholds above "
            "mean the same thing."
        ),
    }
