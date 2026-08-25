"""
IVGS v5 — Wan2.2-Animate client (engine key ``comfyui``).

WP-46. Wan2.2-Animate is served by a ComfyUI instance carrying kijai's
``ComfyUI-WanVideoWrapper``, ``ComfyUI-WanAnimatePreprocess`` and
``ComfyUI-VideoHelperSuite`` custom nodes. It is therefore driven exactly the
way ``flux_client`` drives ComfyUI for images — POST the workflow graph to
``/prompt``, poll ``/history/{prompt_id}``, fetch the artifact from ``/view``
— with two additions the pose-guided family needs:

  * **Two BYTES inputs.** ``Wan2.2-Animate`` is a pose-reenactment model, not a
    text-to-video model: the graph's ``LoadImage`` and ``VHS_LoadVideo`` nodes
    take *filenames* resolved inside the engine's ``input/`` store, so the
    reference image and driving video are uploaded through ``/upload/image``
    first (that endpoint accepts any file type; VHS's own upload widget posts
    mp4s to it) and the server-side names are injected into the graph.
  * **A video artifact.** ``VHS_VideoCombine`` registers its mp4 under the
    ``gifs`` key of the history outputs, with ``videos`` as a fallback — not
    under ``images`` where ``SaveImage`` writes.

The graph in ``clients/graphs/wan_animate.json`` is MBCP's certified
``wan_animate`` workflow copied byte-for-byte (sha256
84a00a2549c3802cdb9f2365430ebc0136cccb226c1c67eed491b0bac70b2525 against
``mbcp_adapters/comfyui_graphs/wan_animate.json``) so the render IVGS performs
is the render MBCP certified. The default parameters below are likewise MBCP's
certified set (migration ``0053_comfyui_family_specs``, family ``wan_animate``).

Endpoint resolution is the ARCH-1 convention: the store row's engine key is
``comfyui``, so ``resolve_endpoint('comfyui')`` reads ``IVGS_COMFYUI_URL``.
Two ComfyUI instances now exist in the fleet behind that one key — node-04's
image engine and node-03's Wan engine — and they are told apart by the
per-worker value of that variable, not by the key. See the WP-46 report.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger("ivgs.workers.wan_animate")

#: The certified graph, alongside this module inside the image.
GRAPH_PATH = Path(__file__).resolve().parent / "graphs" / "wan_animate.json"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class WanAnimateError(Exception):
    """Base exception for Wan2.2-Animate errors."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        prompt_id: Optional[str] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.prompt_id = prompt_id


class WanAnimateConnectionError(WanAnimateError):
    """The Wan ComfyUI instance is unreachable."""


class WanAnimateTimeoutError(WanAnimateError):
    """The render did not complete inside the poll budget."""


class WanAnimateWorkflowError(WanAnimateError):
    """ComfyUI reported an execution error, or the graph was rejected."""


class WanAnimateInputError(WanAnimateError):
    """A required generation input (reference image / driving video) is missing."""


class WanAnimateDownloadError(WanAnimateError):
    """The rendered artifact could not be retrieved from /view."""


# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------

#: MBCP's certified defaults for family ``wan_animate`` — transcribed from
#: ``alembic/versions/0053_comfyui_family_specs.py``. Overridable per request
#: and, ahead of that, by the store row's ``default_params`` (ARCH-1: a model's
#: parameters are data, not code).
CERTIFIED_DEFAULTS: Dict[str, Any] = {
    "served_model_name": (
        "Wan22Animate/Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors"
    ),
    "seed": 0,
    "steps": 6,
    "cfg": 1.0,
    "shift": 5.0,
    "scheduler": "dpm++_sde",
    "output_width": 768,
    "output_height": 1408,
    "num_frames": 77,
    "frame_window_size": 77,
    "pose_strength": 1.0,
    "face_strength": 1.0,
    "output_fps": 30,
    "prompt": "a person performing the motion, photorealistic, high quality",
    "negative_prompt": "blurry, distorted, low quality, artifacts",
}

#: MBCP's certified poll budget for this family (0053: ``poll_timeout_s``).
CERTIFIED_POLL_TIMEOUT_S = 3600

#: Slots ComfyUI types as INT — quoted numbers are rejected by its INT inputs.
_INT_SLOTS = frozenset(
    {"seed", "steps", "num_frames", "output_width", "output_height", "frame_window_size"}
)
#: Slots ComfyUI types as FLOAT.
_FLOAT_SLOTS = frozenset({"cfg", "shift", "output_fps", "pose_strength", "face_strength"})


@dataclass(frozen=True)
class WanAnimateParams:
    """One render's parameters. Defaults are MBCP's certified set."""

    prompt: str = CERTIFIED_DEFAULTS["prompt"]
    negative_prompt: str = CERTIFIED_DEFAULTS["negative_prompt"]
    served_model_name: str = CERTIFIED_DEFAULTS["served_model_name"]
    seed: int = CERTIFIED_DEFAULTS["seed"]
    steps: int = CERTIFIED_DEFAULTS["steps"]
    cfg: float = CERTIFIED_DEFAULTS["cfg"]
    shift: float = CERTIFIED_DEFAULTS["shift"]
    scheduler: str = CERTIFIED_DEFAULTS["scheduler"]
    output_width: int = CERTIFIED_DEFAULTS["output_width"]
    output_height: int = CERTIFIED_DEFAULTS["output_height"]
    num_frames: int = CERTIFIED_DEFAULTS["num_frames"]
    frame_window_size: int = CERTIFIED_DEFAULTS["frame_window_size"]
    pose_strength: float = CERTIFIED_DEFAULTS["pose_strength"]
    face_strength: float = CERTIFIED_DEFAULTS["face_strength"]
    output_fps: float = CERTIFIED_DEFAULTS["output_fps"]

    def compute_hash(self) -> str:
        """Stable hash of the parameter set — the dedup key's parameter half."""
        return hashlib.sha256(
            json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @property
    def duration_seconds(self) -> float:
        """Rendered clip length implied by frames / fps."""
        return round(self.num_frames / float(self.output_fps or 1), 3)


@dataclass
class WanAnimateResult:
    """One completed render."""

    video_data: bytes
    width: int = 0
    height: int = 0
    fps: float = 0.0
    num_frames: int = 0
    duration_seconds: float = 0.0
    model_used: str = ""
    prompt_id: str = ""
    generation_time_seconds: float = 0.0
    telemetry: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def _coerce_slot(key: str, value: Any) -> Any:
    """Give an injected value the real type ComfyUI's socket expects.

    A coercion failure returns the original value rather than masking a bad
    input: the unresolved-slot guard or ComfyUI itself then names it.
    """
    if key in _INT_SLOTS:
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    if key in _FLOAT_SLOTS:
        try:
            return float(value)
        except (TypeError, ValueError):
            return value
    return value


def _inject(node: Any, ctx: Dict[str, Any]) -> Any:
    """Walk the graph replacing ``{slot}`` leaves with typed values.

    An exact ``"{slot}"`` string becomes the *typed* value (so ``"{seed}"``
    becomes an int); a slot embedded in longer text is substituted as a string.
    """
    if isinstance(node, dict):
        return {k: _inject(v, ctx) for k, v in node.items()}
    if isinstance(node, list):
        return [_inject(v, ctx) for v in node]
    if isinstance(node, str):
        if (
            node.startswith("{")
            and node.endswith("}")
            and node.count("{") == 1
            and node.count("}") == 1
        ):
            key = node[1:-1]
            return ctx[key] if key in ctx else node
        out = node
        for key, value in ctx.items():
            token = "{" + key + "}"
            if token in out:
                out = out.replace(token, str(value))
        return out
    return node


def _unresolved_slots(graph: Any, found: Optional[set] = None) -> set:
    """Every ``{slot}`` still present after injection."""
    found = set() if found is None else found
    if isinstance(graph, dict):
        for value in graph.values():
            _unresolved_slots(value, found)
    elif isinstance(graph, list):
        for value in graph:
            _unresolved_slots(value, found)
    elif isinstance(graph, str):
        if (
            graph.startswith("{")
            and graph.endswith("}")
            and graph.count("{") == 1
            and graph.count("}") == 1
        ):
            found.add(graph[1:-1])
    return found


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class WanAnimateClient:
    """Drives one Wan-capable ComfyUI instance for pose-guided animation."""

    def __init__(
        self,
        base_url: str,
        *,
        model: Optional[str] = None,
        timeout: float = 120.0,
        poll_timeout_s: int = CERTIFIED_POLL_TIMEOUT_S,
        poll_interval_s: float = 3.0,
        default_params: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        #: engine-native checkpoint name; overrides the certified default when
        #: the store row supplies ``default_params.engine_model``.
        self.model = model
        self.timeout = timeout
        self.poll_timeout_s = poll_timeout_s
        self.poll_interval_s = poll_interval_s
        self.default_params = dict(default_params or {})
        self._client: Optional[httpx.AsyncClient] = None
        self._graph_template: Optional[Dict[str, Any]] = None

    # -- plumbing ---------------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url, timeout=httpx.Timeout(self.timeout, connect=15.0)
            )
        return self._client

    def _graph(self) -> Dict[str, Any]:
        if self._graph_template is None:
            self._graph_template = json.loads(GRAPH_PATH.read_text())
        return self._graph_template

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    # -- health -----------------------------------------------------------

    async def health(self) -> Dict[str, Any]:
        """Engine liveness. ``/system_stats`` is ComfyUI's status surface.

        Returns the parsed body so a caller can log the device and the VRAM the
        engine reports, which is what the WP-46 measurement uses as a baseline.
        """
        client = await self._get_client()
        try:
            resp = await client.get("/system_stats")
        except httpx.HTTPError as exc:
            raise WanAnimateConnectionError(
                f"Wan engine unreachable at {self.base_url}: {exc}"
            ) from exc
        if resp.status_code != 200:
            raise WanAnimateConnectionError(
                f"Wan engine health returned HTTP {resp.status_code}",
                status_code=resp.status_code,
            )
        return resp.json()

    async def available_node_types(self) -> set:
        """The engine's registered node classes — the capability gate.

        A stock ComfyUI answers ``{}`` for every ``WanVideo*`` class, so a
        graph POSTed to it fails deep inside ``/prompt`` with an opaque
        validation error. Checking first lets the task say *which* instance it
        reached and what it was missing.
        """
        client = await self._get_client()
        resp = await client.get("/object_info")
        resp.raise_for_status()
        return set(resp.json().keys())

    # -- inputs -----------------------------------------------------------

    async def upload_input(self, filename: str, data: bytes, mime: str) -> str:
        """Put one file in the engine's ``input/`` store; return its name.

        ``overwrite=true`` keeps re-runs idempotent: the same logical name is
        replaced rather than duplicated under a suffix ComfyUI invents, so a
        retried scene does not accumulate inputs on the engine.
        """
        client = await self._get_client()
        try:
            resp = await client.post(
                "/upload/image",
                files={"image": (filename, data, mime)},
                data={"type": "input", "overwrite": "true"},
            )
        except httpx.HTTPError as exc:
            raise WanAnimateConnectionError(f"input upload failed: {exc}") from exc
        if resp.status_code not in (200, 201):
            raise WanAnimateWorkflowError(
                f"input upload rejected: HTTP {resp.status_code}",
                status_code=resp.status_code,
            )
        return resp.json().get("name", filename)

    # -- graph ------------------------------------------------------------

    def build_workflow(
        self,
        params: WanAnimateParams,
        *,
        ref_image_file: str,
        driving_video_file: str,
        cache_bust: bool = True,
    ) -> Dict[str, Any]:
        """The certified graph with this render's values injected.

        Precedence: certified defaults < store ``default_params`` < request
        params < the two uploaded filenames.
        """
        ctx: Dict[str, Any] = dict(CERTIFIED_DEFAULTS)
        ctx.update(self.default_params)
        ctx.update(asdict(params))
        if self.model:
            ctx["served_model_name"] = self.model
        ctx["ref_image_file"] = ref_image_file
        ctx["driving_video_file"] = driving_video_file
        ctx = {k: _coerce_slot(k, v) for k, v in ctx.items()}

        graph = _inject(json.loads(json.dumps(self._graph())), ctx)

        missing = _unresolved_slots(graph)
        if missing:
            raise WanAnimateWorkflowError(
                "unresolved workflow slot(s): "
                + ", ".join(sorted(missing))
                + " — supply via the store row's default_params or the request"
            )

        if cache_bust:
            # ComfyUI caches by graph identity. The certified params pin the
            # seed on purpose, so an identical graph would cache-hit every
            # node INCLUDING the terminal VHS_VideoCombine, and the run would
            # report success having registered no artifact. Perturbing only
            # the output filename re-runs that node and leaves the rendered
            # frames bit-identical.
            nonce = hashlib.sha256(
                f"{ref_image_file}|{driving_video_file}|{params.compute_hash()}"
                f"|{time.time_ns()}".encode()
            ).hexdigest()[:12]
            for node in graph.values():
                inputs = node.get("inputs") if isinstance(node, dict) else None
                if isinstance(inputs, dict) and "filename_prefix" in inputs:
                    inputs["filename_prefix"] = f"{inputs['filename_prefix']}_{nonce}"
        return graph

    # -- execution --------------------------------------------------------

    async def _submit(self, graph: Dict[str, Any]) -> str:
        client = await self._get_client()
        try:
            resp = await client.post("/prompt", json={"prompt": graph})
        except httpx.HTTPError as exc:
            raise WanAnimateConnectionError(
                f"Wan engine unreachable at {self.base_url}: {exc}"
            ) from exc
        if resp.status_code != 200:
            raise WanAnimateWorkflowError(
                f"ComfyUI rejected the workflow: HTTP {resp.status_code}: "
                f"{resp.text[:400]}",
                status_code=resp.status_code,
            )
        prompt_id = resp.json().get("prompt_id")
        if not prompt_id:
            raise WanAnimateWorkflowError("ComfyUI returned no prompt_id")
        return prompt_id

    @staticmethod
    def _status_error(status: Dict[str, Any]) -> Optional[str]:
        """The execution error in a history status, formatted, or None."""
        if not status:
            return None
        for msg in status.get("messages") or []:
            if isinstance(msg, (list, tuple)) and len(msg) >= 2 and msg[0] == "execution_error":
                detail = msg[1] or {}
                return (
                    f"node {detail.get('node_id')} ({detail.get('node_type')}): "
                    f"{detail.get('exception_type')}: {detail.get('exception_message')}"
                )
        if status.get("status_str") == "error":
            return f"status_str=error (no execution_error detail)"
        return None

    @staticmethod
    def _status_success(status: Dict[str, Any]) -> bool:
        if not status:
            return False
        return status.get("status_str") == "success" or bool(status.get("completed"))

    async def _await_outputs(self, prompt_id: str) -> Dict[str, Any]:
        """Poll ``/history`` until the prompt finishes, or raise saying why."""
        client = await self._get_client()
        waited = 0.0
        while waited <= self.poll_timeout_s:
            resp = await client.get(f"/history/{prompt_id}")
            resp.raise_for_status()
            entry = (resp.json() or {}).get(prompt_id)
            if entry is not None:
                status = entry.get("status") or {}
                err = self._status_error(status)
                if err:
                    # An errored prompt carries empty outputs; without this the
                    # loop would run to the cap and raise a timeout that hides
                    # the real failure.
                    raise WanAnimateWorkflowError(
                        f"ComfyUI prompt {prompt_id} failed in {err}",
                        prompt_id=prompt_id,
                    )
                outputs = entry.get("outputs")
                if outputs and (self._status_success(status) or not status):
                    return outputs
                if self._status_success(status) and not outputs:
                    raise WanAnimateWorkflowError(
                        f"ComfyUI prompt {prompt_id} completed but registered no "
                        f"output — the terminal-node cache-bust did not take",
                        prompt_id=prompt_id,
                    )
            await asyncio.sleep(self.poll_interval_s)
            waited += self.poll_interval_s
        raise WanAnimateTimeoutError(
            f"ComfyUI prompt {prompt_id} did not complete in {self.poll_timeout_s}s",
            prompt_id=prompt_id,
        )

    @staticmethod
    def _video_ref(outputs: Dict[str, Any]) -> Dict[str, Any]:
        """The mp4 reference from a completed history's outputs.

        ``VHS_VideoCombine`` registers under ``gifs`` (``videos`` on some
        builds) — never under ``images``, which is where ``SaveImage`` writes.
        """
        for node in outputs.values():
            for key in ("gifs", "videos"):
                refs = node.get(key) or []
                if refs:
                    return refs[0]
        raise WanAnimateDownloadError(
            "ComfyUI history carried no video output (looked for: gifs, videos)"
        )

    async def _download(self, ref: Dict[str, Any]) -> bytes:
        client = await self._get_client()
        resp = await client.get(
            "/view",
            params={
                "filename": ref["filename"],
                "subfolder": ref.get("subfolder", ""),
                "type": ref.get("type", "output"),
            },
        )
        if resp.status_code != 200:
            raise WanAnimateDownloadError(
                f"artifact fetch failed: HTTP {resp.status_code}",
                status_code=resp.status_code,
            )
        return resp.content

    async def generate_animation(
        self,
        *,
        reference_image: bytes,
        driving_video: bytes,
        params: Optional[WanAnimateParams] = None,
        input_key: str = "scene",
    ) -> WanAnimateResult:
        """Render one animated scene from a reference still and a driving clip.

        Both inputs are REQUIRED. Wan2.2-Animate is pose reenactment: it has no
        prompt-only mode, and the stage contract's optionality is not the
        model's — so a missing input is refused here, by name, before any GPU
        time is claimed.
        """
        params = params or WanAnimateParams()
        missing = [
            name
            for name, value in (
                ("reference_image", reference_image),
                ("driving_video", driving_video),
            )
            if not value
        ]
        if missing:
            raise WanAnimateInputError(
                f"Wan2.2-Animate requires generation input(s) {missing} — it is a "
                f"pose-reenactment model (reference image + driving video -> video) "
                f"and has no prompt-only mode"
            )

        started = time.monotonic()
        # Namespaced by scene so concurrent scenes cannot overwrite each other's
        # inputs, and a retry of the SAME scene deliberately does.
        ref_name = await self.upload_input(
            f"ivgs_wan_ref_{input_key}.png", reference_image, "image/png"
        )
        drv_name = await self.upload_input(
            f"ivgs_wan_drive_{input_key}.mp4", driving_video, "video/mp4"
        )

        graph = self.build_workflow(
            params, ref_image_file=ref_name, driving_video_file=drv_name
        )
        prompt_id = await self._submit(graph)
        outputs = await self._await_outputs(prompt_id)
        video = await self._download(self._video_ref(outputs))

        return WanAnimateResult(
            video_data=video,
            width=params.output_width,
            height=params.output_height,
            fps=float(params.output_fps),
            num_frames=params.num_frames,
            duration_seconds=params.duration_seconds,
            model_used=self.model or params.served_model_name,
            prompt_id=prompt_id,
            generation_time_seconds=round(time.monotonic() - started, 2),
            telemetry={
                "prompt_id": prompt_id,
                "node_count": len(graph),
                "ref_image_file": ref_name,
                "driving_video_file": drv_name,
                "params_hash": params.compute_hash(),
            },
        )
