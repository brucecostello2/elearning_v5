"""WP-67 Task 3 — the AnimateDiff-SD15 client, against fixtures.

NO LIVE RUN IS CLAIMED OR POSSIBLE. Its weights are unfetched (WP-65 measured
that its certification is ENGINE-ONLY, so there is nothing to fetch -- the model
ships in an engine image), and no ComfyUI on this fleet has the ``ADE_*`` custom
nodes: probed 2026-08-26, node-04's instance answers ``{}`` for
``/object_info/ADE_AnimateDiffLoaderGen1``. The operator block that would
exercise it live is in the WP-67 report, staged.

What IS proven here: the graph is filled correctly, an unfillable slot is
refused rather than shipped, the contract is enforced before a request is made,
and a ComfyUI without the custom nodes is refused with its OWN error rather than
the generic HTTP 400 that WP-65 Task 1 measured as indistinguishable from
everything else.
"""
from __future__ import annotations

import json

import pytest

from clients.animatediff_client import (
    GRAPH_PATH,
    MOTION_MODULE,
    REQUIRED_NODE_TYPES,
    AnimateDiffCapabilityError,
    AnimateDiffClient,
    AnimateDiffInputError,
    AnimateDiffParams,
    AnimateDiffWorkflowError,
)


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text

    def json(self):
        return self._payload


class _FakeHTTP:
    """Just enough httpx.AsyncClient for these paths."""

    def __init__(self, *, object_info=None, prompt_response=None):
        self._object_info = object_info if object_info is not None else {}
        self._prompt = prompt_response or _FakeResponse(200, {"prompt_id": "p-1"})
        self.submitted = None

    async def get(self, url, **kw):
        return _FakeResponse(200, self._object_info)

    async def post(self, url, json=None, **kw):
        self.submitted = json
        return self._prompt

    async def aclose(self):
        return None


def _client(**http_kw) -> AnimateDiffClient:
    c = AnimateDiffClient("http://engine:8188", model="sd15.safetensors")
    c._client = _FakeHTTP(**http_kw)
    return c


class TestTheGraphIsFilledCorrectly:
    def test_every_slot_is_resolved(self):
        """Asked with the graph walker, not with a substring search: a JSON
        document is full of braces, and `"{" not in json.dumps(...)` would be
        a test that can never pass and therefore never means anything."""
        from clients.wan_animate_client import _unresolved_slots

        c = _client()
        graph = c.build_workflow(AnimateDiffParams(prompt="a ruled line"))
        assert _unresolved_slots(graph) == set()

    def test_the_prompt_reaches_the_positive_encoder(self):
        c = _client()
        graph = c.build_workflow(AnimateDiffParams(prompt="two rows above a line"))
        positive = graph["3"]["inputs"]["text"]
        assert positive == "two rows above a line"

    def test_the_negative_prompt_forbids_text_by_default(self):
        """RULE 1's problem restated at the render layer: the whole repo's
        measured failure is image models producing text-shaped marks, and this
        family's negative prompt is the one place a client can push back."""
        p = AnimateDiffParams(prompt="x")
        for word in ("text", "numbers", "digits", "handwriting"):
            assert word in p.negative_prompt

    def test_numeric_slots_arrive_as_numbers_not_strings(self):
        c = _client()
        graph = c.build_workflow(
            AnimateDiffParams(prompt="x", num_frames=24, output_fps=12, seed=7)
        )
        assert graph["5"]["inputs"]["batch_size"] == 24
        assert graph["8"]["inputs"]["frame_rate"] == 12
        assert graph["6"]["inputs"]["seed"] == 7

    def test_an_unfillable_slot_is_refused_rather_than_shipped(self):
        """An unresolved '{slot}' is accepted as a literal string by some
        ComfyUI sockets, producing a render that looks fine and is wrong."""
        c = _client()
        c._graph_template = {"1": {"inputs": {"thing": "{not_a_param}"},
                                   "class_type": "X"}}
        with pytest.raises(AnimateDiffWorkflowError) as exc:
            c.build_workflow(AnimateDiffParams(prompt="x"))
        assert "not_a_param" in str(exc.value)

    def test_the_motion_module_is_not_parameterised(self):
        c = _client()
        graph = c.build_workflow(AnimateDiffParams(prompt="x"))
        assert graph["2"]["inputs"]["model_name"] == MOTION_MODULE

    def test_the_shipped_graph_is_the_one_on_disk(self):
        assert GRAPH_PATH.is_file()
        assert len(json.loads(GRAPH_PATH.read_text())) == 8


class TestTheContractIsEnforcedBeforeAnythingIsSent:
    def test_a_scene_with_no_prompt_is_refused(self):
        """Its declared requirement, enforced by the client that declared it."""
        c = _client()
        with pytest.raises(AnimateDiffInputError) as exc:
            c.build_workflow(AnimateDiffParams(prompt="   "))
        assert "text-to-video" in str(exc.value)

    def test_it_needs_no_still_and_no_person(self):
        """The reason this family was chosen. A prompt is enough."""
        c = _client()
        graph = c.build_workflow(AnimateDiffParams(prompt="a carry mark"))
        assert graph  # no reference image was supplied and none was needed


class TestACapabilityGapIsItsOwnError:
    """WP-65 Task 1 measured that a missing model file and a missing custom
    node both surface as "ComfyUI rejected the workflow: HTTP 400", and are
    indistinguishable from a malformed graph. This client checks first."""

    async def test_a_comfyui_without_the_nodes_is_refused_by_name(self):
        c = _client(object_info={"KSampler": {}, "CheckpointLoaderSimple": {}})
        with pytest.raises(AnimateDiffCapabilityError) as exc:
            await c.assert_capable()
        text = str(exc.value)
        assert "ADE_AnimateDiffLoaderGen1" in text
        assert "not a weights problem" in text

    async def test_a_capable_instance_passes(self):
        c = _client(object_info={n: {} for n in REQUIRED_NODE_TYPES})
        await c.assert_capable()

    async def test_the_capability_error_is_not_a_workflow_error(self):
        """Distinct classes, so a caller can tell "deploy a different engine
        image" from "your graph is wrong"."""
        assert not issubclass(AnimateDiffCapabilityError, AnimateDiffWorkflowError)


class TestParamsFromBinding:
    def test_binding_defaults_are_used(self):
        c = AnimateDiffClient(
            "http://x", model="m.safetensors",
            default_params={"num_frames": 32, "output_fps": 16},
        )
        p = c.params_from(prompt="x")
        assert p.num_frames == 32 and p.output_fps == 16
        assert p.served_model_name == "m.safetensors"

    def test_per_call_overrides_win(self):
        c = AnimateDiffClient("http://x", default_params={"num_frames": 32})
        assert c.params_from(prompt="x", num_frames=8).num_frames == 8

    def test_unknown_keys_in_default_params_are_ignored(self):
        """`default_params` is where the AD-01 ingest parks everything MBCP
        sends that has no column, including `family`, `provenance` and
        `_unknown_export_fields`. A client must not choke on them."""
        c = AnimateDiffClient(
            "http://x",
            default_params={"family": "animatediff", "provenance": {"a": 1},
                            "num_frames": 8},
        )
        assert c.params_from(prompt="x").num_frames == 8

    def test_duration_follows_frames_and_fps(self):
        assert AnimateDiffParams(num_frames=16, output_fps=8).duration_seconds == 2.0
