"""WP-67 Task 3 — AnimateDiff-SD15, the second animation family.

WHY THIS FAMILY AND NOT MimicMotion. Chosen on the brief's own criteria --
simpler graph, and an input contract an educational still can satisfy --
measured against MBCP's certified graphs for both:

  ``mbcp_adapters/comfyui_graphs/animatediff-sd15.json``   **8 nodes**
      CheckpointLoaderSimple, ADE_AnimateDiffLoaderGen1, CLIPTextEncode x2,
      ADE_EmptyLatentImageLarge, KSampler, VAEDecode, VHS_VideoCombine.
      Latent starts EMPTY: it needs a prompt and nothing else.

  ``mbcp_adapters/comfyui_graphs/mimicmotion.json``        **16 nodes**
      adds LoadImage, VHS_LoadVideo, MimicMotionGetPoses, InspyrenetRembg,
      GrowMask, FeatherMask, ImageCompositeMasked...
      It is pose transfer: it needs a still AND a driving video.

MimicMotion therefore has the same input contract that makes Wan2.2-Animate
unusable for a mathematics lesson -- it needs a driving clip of a moving subject.
AnimateDiff needs a prompt. For a repo whose measured problem is "thirteen scenes
about column multiplication and no animation was possible", the family that
needs no person and no driving video is worth strictly more.

THE GRAPH IS MBCP'S, COPIED VERBATIM, for the same reason
``clients/graphs/wan_animate.json`` is: the render IVGS performs must be the
render MBCP certified, or the certification describes something else. The file
is ``clients/graphs/animatediff_sd15.json`` and its slot names are MBCP's.

**NO LIVE RUN IS CLAIMED.** AnimateDiff-SD15's weights are unfetched (WP-65: its
certification is engine-only, so there is nothing to fetch -- the model ships in
an engine image that is not deployed), and no ComfyUI on this fleet has the
``ADE_*`` custom nodes installed. This client is proven against fixtures. The
operator block that would exercise it live is in the WP-67 report, staged.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from clients.wan_animate_client import (
    _inject,
    _unresolved_slots,
)

GRAPH_PATH = Path(__file__).resolve().parent / "graphs" / "animatediff_sd15.json"

#: The motion module the certified graph names. Not a parameter: MBCP certified
#: the model against THIS module, and swapping it silently would make the
#: attestation describe a different render.
MOTION_MODULE = "mm_sd_v15_v2.ckpt"


class AnimateDiffError(Exception):
    """Base exception for AnimateDiff-SD15 errors."""

    def __init__(self, message: str, *, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class AnimateDiffConnectionError(AnimateDiffError):
    """The engine could not be reached."""


class AnimateDiffWorkflowError(AnimateDiffError):
    """ComfyUI reported an execution error, or the graph was rejected."""


class AnimateDiffInputError(AnimateDiffError):
    """The scene does not satisfy this client's declared contract."""


class AnimateDiffCapabilityError(AnimateDiffError):
    """The engine instance lacks the custom nodes this graph needs.

    A DISTINCT error, deliberately. WP-65 Task 1 measured that a missing model
    file and a missing custom node both surface as "ComfyUI rejected the
    workflow: HTTP 400" and are indistinguishable. This client checks
    ``/object_info`` first so the two can be told apart before a render is
    attempted -- the failure an operator can actually act on is "this ComfyUI
    does not have AnimateDiff-Evolved installed", not "HTTP 400".
    """


@dataclass
class AnimateDiffParams:
    """Everything the certified graph's slots need."""

    prompt: str = ""
    negative_prompt: str = (
        "text, watermark, letters, numbers, digits, handwriting, caption, "
        "blurry, distorted"
    )
    served_model_name: str = "v1-5-pruned-emaonly.safetensors"
    output_width: int = 512
    output_height: int = 512
    num_frames: int = 16
    output_fps: int = 8
    seed: int = 0

    def as_context(self) -> Dict[str, Any]:
        return {
            "prompt": self.prompt,
            "negative_prompt": self.negative_prompt,
            "served_model_name": self.served_model_name,
            "output_width": int(self.output_width),
            "output_height": int(self.output_height),
            "num_frames": int(self.num_frames),
            "output_fps": int(self.output_fps),
            "seed": int(self.seed),
        }

    @property
    def duration_seconds(self) -> float:
        return self.num_frames / float(self.output_fps or 1)


@dataclass
class AnimateDiffResult:
    prompt_id: str = ""
    video_data: bytes = b""
    width: int = 0
    height: int = 0
    fps: int = 0
    duration_seconds: float = 0.0
    frames: int = 0
    graph_hash: str = ""
    warnings: list[str] = field(default_factory=list)


#: Node types the certified graph needs that are NOT in stock ComfyUI. Checked
#: against /object_info before a render, so "not installed" is its own error.
REQUIRED_NODE_TYPES = ("ADE_AnimateDiffLoaderGen1", "ADE_EmptyLatentImageLarge")


class AnimateDiffClient:
    """Drives one AnimateDiff-capable ComfyUI instance.

    Text-to-video: a prompt in, an mp4 out. No reference image, no driving
    clip, no person. That is the whole point of choosing this family.
    """

    def __init__(
        self,
        base_url: str,
        *,
        model: str = "",
        timeout: float = 600.0,
        default_params: Optional[Dict[str, Any]] = None,
        **_ignored: Any,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.default_params = dict(default_params or {})
        self._client: Optional[httpx.AsyncClient] = None
        self._graph_template: Optional[Dict[str, Any]] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _graph(self) -> Dict[str, Any]:
        if self._graph_template is None:
            self._graph_template = json.loads(GRAPH_PATH.read_text())
        return self._graph_template

    # -- capability ------------------------------------------------------

    async def available_node_types(self) -> set:
        """The node types this ComfyUI instance actually has."""
        client = await self._get_client()
        try:
            resp = await client.get(f"{self.base_url}/object_info")
        except httpx.HTTPError as exc:
            raise AnimateDiffConnectionError(
                f"could not read /object_info from {self.base_url}: {exc}"
            ) from exc
        if resp.status_code != 200:
            raise AnimateDiffConnectionError(
                f"/object_info returned HTTP {resp.status_code}",
                status_code=resp.status_code,
            )
        return set(resp.json().keys())

    async def assert_capable(self) -> None:
        """Refuse BEFORE rendering if the AnimateDiff nodes are absent.

        This is the check WP-65 Task 1 found missing everywhere: without it a
        ComfyUI that has never had AnimateDiff-Evolved installed answers a
        render with the same HTTP 400 as a malformed graph.
        """
        available = await self.available_node_types()
        missing = [n for n in REQUIRED_NODE_TYPES if n not in available]
        if missing:
            raise AnimateDiffCapabilityError(
                f"the ComfyUI at {self.base_url} does not have "
                f"{', '.join(missing)}. AnimateDiff-SD15 needs the "
                f"AnimateDiff-Evolved custom nodes; this instance has "
                f"{len(available)} node types and none of them. Deploy an "
                f"engine image that carries them -- this is not a weights "
                f"problem and fetching weights will not fix it."
            )

    # -- workflow --------------------------------------------------------

    def build_workflow(self, params: AnimateDiffParams) -> Dict[str, Any]:
        """Inject params into the certified graph. Refuses an unfilled slot.

        Same discipline as the Wan client: an unresolved ``{slot}`` reaching
        ComfyUI is accepted as a literal string by some sockets and produces a
        render that looks fine and is wrong.
        """
        if not params.prompt.strip():
            raise AnimateDiffInputError(
                "AnimateDiff-SD15 is text-to-video: it requires a prompt, and "
                "this scene supplied none"
            )
        graph = _inject(json.loads(json.dumps(self._graph())), params.as_context())
        unresolved = _unresolved_slots(graph)
        if unresolved:
            raise AnimateDiffWorkflowError(
                f"graph has unfilled slots after injection: "
                f"{', '.join(sorted(unresolved))}"
            )
        return graph

    async def submit(self, graph: Dict[str, Any]) -> str:
        client = await self._get_client()
        try:
            resp = await client.post(f"{self.base_url}/prompt", json={"prompt": graph})
        except httpx.HTTPError as exc:
            raise AnimateDiffConnectionError(f"submit failed: {exc}") from exc
        if resp.status_code != 200:
            raise AnimateDiffWorkflowError(
                f"ComfyUI rejected the workflow: HTTP {resp.status_code}: "
                f"{resp.text[:400]}",
                status_code=resp.status_code,
            )
        prompt_id = resp.json().get("prompt_id")
        if not prompt_id:
            raise AnimateDiffWorkflowError("ComfyUI returned no prompt_id")
        return str(prompt_id)

    def params_from(self, **overrides: Any) -> AnimateDiffParams:
        """Params from the binding's defaults, then per-call overrides."""
        merged: Dict[str, Any] = {}
        fields = AnimateDiffParams.__dataclass_fields__
        for source in (self.default_params, overrides):
            for key, value in (source or {}).items():
                if key in fields and value is not None:
                    merged[key] = value
        if self.model and "served_model_name" not in merged:
            merged["served_model_name"] = self.model
        return AnimateDiffParams(**merged)
