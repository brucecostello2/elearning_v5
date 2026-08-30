"""The seam: how the Design Contract leaves stage 2 without editing stage 2.

⛔ THE PROBLEM, MEASURED

``stage2_storyboard.py`` is one of the eight bodies AD-05 §8 freezes, and the
Design Contract cannot survive a trip through it. Two hard-coded field lists:

  * ``:314-357`` builds ``StoryboardScene`` with ELEVEN named keywords. The
    model's other keys are never passed, and ``extra="allow"`` keeps only what
    is SUPPLIED, so they are gone before the checkpoint is written.
  * ``:467-492`` POSTs five keys plus a fixed three-name tuple.

Freeze exception #2's own comment predicts this: *"a v8 field needs this line
again."* Ruling R5 says to prefer a wrapper and to STOP with a diff only if an
edit is genuinely unavoidable. **It is avoidable, and this module is how.** The
operator approved this route on 2026-08-29; no exception #3 was requested.

⛳ THE ROUTE

Three owned modules and no runtime patching:

  1. ``celery_app`` already runs ``task_prerun``/``task_postrun`` handlers.
     Prerun ARMS this module with the job and project ids off the task payload,
     and names which stage is running.
  2. ``VLLMClient`` offers every parsed response to registered observers
     (``clients/vllm_client.RESPONSE_OBSERVERS``). This module registers one at
     worker init. The client gains a list and a loop; it does not gain a
     dependency on anything here.
  3. The observer POSTs the whole emission to the API, which stores the brief
     and back-fills the per-scene design columns by ``scene_index``.

⛳ IT FLUSHES EAGERLY, AT THE MOMENT OF CAPTURE, AND NOT AT ``task_postrun``.
That is deliberate and it is not a micro-optimisation. ``_save_storyboard_scenes``
SWALLOWS a non-2xx response (recovery-plan RC-E, still true, still frozen), so
scene rows can fail to appear with the task reporting success. A brief written
before that point survives it, and the gate can then say "the design exists and
the scenes did not" instead of showing nothing and explaining nothing.

⚠ EVERY FAILURE HERE IS NON-FATAL BY CONSTRUCTION. This is an observer on the
side of a working pipeline; if it cannot reach the API, the storyboard must
still be produced. Failures are logged under one greppable event
(``design_contract_capture_failed``) and never raised into the stage.
"""
from __future__ import annotations

import contextvars
import json
from typing import Any, Dict, Optional

import httpx
import structlog

from design_core.contract import parse_contract
from shared.design.merge import merged_scene_sequence

logger = structlog.get_logger("ivgs.design_core.capture")

#: Task names this module listens for. Anything else is ignored outright, so a
#: translation or an image prompt never reaches the contract parser.
STORYBOARD_TASK = "tasks.stage2_storyboard.generate_storyboard_task"
TRANSCRIPT_TASK = "tasks.stage1_transcript.refine_transcript_task"

_armed: contextvars.ContextVar[Optional[Dict[str, Any]]] = contextvars.ContextVar(
    "ivgs_design_capture", default=None,
)


def arm(*, task_name: str, task_input: Any) -> None:
    """Called from ``task_prerun``. Records what run is about to happen."""
    if task_name not in (STORYBOARD_TASK, TRANSCRIPT_TASK):
        _armed.set(None)
        return
    ctx = {}
    if isinstance(task_input, dict):
        ctx = task_input.get("job_context") or {}
    if not isinstance(ctx, dict):
        ctx = {}
    job_id = ctx.get("job_id") or ""
    project_id = ctx.get("project_id") or ""
    if not project_id:
        # Without a project there is nothing to attach a brief to. Say so once
        # rather than failing later with a 422 nobody can trace.
        logger.warning(
            "design_contract_capture_not_armed",
            task_name=task_name,
            reason="no project_id in job_context",
        )
        _armed.set(None)
        return
    _armed.set({
        "task_name": task_name,
        "job_id": str(job_id),
        "project_id": str(project_id),
        "stage": "storyboard" if task_name == STORYBOARD_TASK else "transcript",
        "seen": False,
    })


def outcome_ids_for_current_project() -> list:
    """This project's outcome ids, parsed BY CODE from what the operator typed.

    WP-IVGS-12b. They close the contract schema's `serves_outcomes`,
    `evidence_map` and `outcome_notes`, so the model cannot cite an outcome
    that does not exist and cannot leave one unmentioned.

    ⚠ Returns [] on any failure — an unreachable API, a project with no
    outcomes — and the schema then degrades to an open string rather than an
    unsatisfiable empty enum. A design without the closed set is worse than one
    with it; a design that cannot be generated at all is worse than both.
    """
    state = _armed.get()
    if not state or not state.get("project_id"):
        return []
    try:
        from config import WorkerConfig

        config = WorkerConfig()
        with httpx.Client(
            timeout=config.pipeline_api.timeout_seconds,
            headers={"Authorization": f"Bearer {config.pipeline_api.service_token}"},
        ) as client:
            # ⛔ `/design-outcomes`, NOT `/projects/{id}`. The latter takes
            # `get_current_user` and answers a service token with 401, so this
            # returned [] every time, the enum never armed, and the model went
            # straight back to inventing ids — measured on 12b's first run.
            resp = client.get(
                f"{config.pipeline_api.full_base_url}"
                f"/projects/{state['project_id']}/design-outcomes"
            )
        if resp.status_code != 200:
            logger.warning(
                "design_contract_outcome_ids_http",
                project_id=state["project_id"],
                status_code=resp.status_code,
                detail=(
                    "the schema will NOT be closed to real outcome ids; the "
                    "model may invent them and the gate will refuse the scenes"
                ),
            )
            return []
        ids = [str(i) for i in ((resp.json() or {}).get("outcome_ids") or [])]
        logger.info(
            "design_contract_outcome_ids_resolved",
            project_id=state["project_id"],
            ids=ids,
        )
        return ids
    except Exception as exc:                                     # noqa: BLE001
        logger.warning(
            "design_contract_outcome_ids_unavailable",
            project_id=state.get("project_id"),
            error_type=type(exc).__name__,
            error=str(exc),
        )
        return []


def transform_document(document: Any) -> Any:
    """The merged sequence, handed to the frozen stage body.

    WP-IVGS-12f. Armed as `clients.vllm_client`'s document transform for the
    storyboard task only, and applied to `chat_json`'s parsed document before
    the stage sees it.

    ⛔ WHY THIS EXISTS AT ALL. Under contract-5 the model authors one invented
    unaided scene per outcome in `designed_assessments`, OUTSIDE `scenes`, and
    it does not place them — `shared.design.merge` does, after the last scene
    serving each outcome. The frozen body builds its `StoryboardScene` rows from
    `scenes` and POSTs them; without this it would build rows for the sourced
    scenes only, and every designed assessment would exist in the design brief
    and in no scene row. Designed, stored, reviewed at the gate — and never
    rendered. That is the RC-E failure class with better paperwork.

    ⛳ IT CALLS THE SAME `merged_scene_sequence` `parse_contract` CALLS, so the
    rows in `storyboard_scenes` and the brief's `scene_designs` are one list
    computed once. Two derivations of one sequence is how 12c's three accounts
    of the evidence map came to disagree.

    ⚠ IT REWRITES EXACTLY ONE KEY AND ONLY ON A DOCUMENT IT RECOGNISES. Not a
    dict, not armed for the storyboard stage, no `designed_assessments`, or a
    merge that produced nothing — the document goes back untouched, so a v7
    storyboard and every other stage's JSON pass through unchanged.
    """
    state = _armed.get()
    if not state or state.get("stage") != "storyboard":
        return document
    if not isinstance(document, dict):
        return document
    designed = document.get("designed_assessments")
    if not isinstance(designed, dict) or not designed:
        return document
    merged = merged_scene_sequence(document)
    if not merged:
        return document
    out = dict(document)
    out["scenes"] = merged
    logger.info(
        "design_contract_assessments_merged",
        project_id=state.get("project_id"),
        job_id=state.get("job_id"),
        emitted_scenes=len(document.get("scenes") or []),
        designed_assessments=len(designed),
        merged_scenes=len(merged),
    )
    return out


def disarm() -> None:
    """Called from ``task_postrun``. A stage that produced no contract is not an
    error — a v7 storyboard produces none — but it IS worth one line, because
    "the gate shows no design brief" and "stage 2 ran the old prompt" look
    identical from the outside and have different fixes."""
    state = _armed.get()
    if state and state["stage"] == "storyboard" and not state["seen"]:
        logger.info(
            "design_contract_absent",
            job_id=state["job_id"],
            project_id=state["project_id"],
            detail=(
                "stage 2 completed without emitting a design contract; the "
                "active storyboard prompt is probably pre-v8"
            ),
        )
    _armed.set(None)


def observe(content: Any, *, model: str = "", prompt_fingerprint: str = "") -> None:
    """The observer the LLM client calls with every successful chat response.

    Receives the raw assistant CONTENT — a string — because the client calls it
    from the one place both stages share. Stage 1 uses ``chat`` and parses JSON
    itself; stage 2 uses ``chat_json``. Hooking the shared path covers both and
    keeps the client from needing to know which is which.

    Cheap and silent for everything that is not a design contract: the parse
    returns ``None`` for a v7 storyboard, for a plain-text refined transcript,
    and for every other stage's JSON.
    """
    state = _armed.get()
    if not state:
        return
    try:
        parsed = content
        if isinstance(parsed, str):
            text = parsed.strip()
            # A plain-text refinement is the overwhelmingly common case and
            # must cost one failed json.loads, not an exception trace.
            if not text.startswith(("{", "[")):
                return
            try:
                parsed = json.loads(text)
            except ValueError:
                return
        if state["stage"] == "transcript":
            _capture_intent(state, parsed)
            return
        payload = parse_contract(parsed)
        if payload is None:
            return
        state["seen"] = True
        payload["job_id"] = state["job_id"] or None
        payload["model_used"] = model or None
        payload["prompt_fingerprint"] = prompt_fingerprint or None
        _post(state["project_id"], payload)
    except Exception as exc:                                     # noqa: BLE001
        # NEVER raise into a stage. See the module docstring.
        logger.warning(
            "design_contract_capture_failed",
            project_id=state.get("project_id"),
            job_id=state.get("job_id"),
            stage=state.get("stage"),
            error_type=type(exc).__name__,
            error=str(exc),
        )


def _capture_intent(state: Dict[str, Any], parsed: Any) -> None:
    """Stage 1's extraction artifact.

    ⛳ THIS IS WHY THE EXTRACTION PROMPT EMITS AN OBJECT AND NOT PROSE. The
    frozen stage-1 body already unwraps one: ``stage1_transcript.py:359-364``
    parses the response and takes ``refined_text``, discarding every sibling
    key. So ``{"refined_text": "<the script, VERBATIM>", "intent": {...}}``
    gives the frozen body exactly what it expects — and for an uploaded script
    that is the script itself, so nothing is rewritten and nothing is lost —
    while the extraction rides out through this observer.
    """
    if not isinstance(parsed, dict):
        return
    intent = parsed.get("intent")
    if not isinstance(intent, dict) or not intent:
        return
    state["seen"] = True
    _post(state["project_id"], {"intent": intent, "job_id": state["job_id"] or None})


def _post(project_id: str, payload: Dict[str, Any]) -> None:
    from config import WorkerConfig

    config = WorkerConfig()
    url = (
        f"{config.pipeline_api.full_base_url}"
        f"/projects/{project_id}/design-brief"
    )
    with httpx.Client(
        timeout=config.pipeline_api.timeout_seconds,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.pipeline_api.service_token}",
        },
    ) as client:
        resp = client.post(url, json=payload)
    if resp.status_code in (200, 201):
        logger.info(
            "design_contract_captured",
            project_id=project_id,
            scenes=len(payload.get("scenes") or []),
            outcomes=len(payload.get("outcomes") or []),
            dropped=len(payload.get("dropped_beats") or []),
            intent=bool(payload.get("intent")),
        )
        return
    # ⛔ NOT SWALLOWED. `_save_storyboard_scenes` swallowing a non-2xx is a
    # named open defect (RC-E); reproducing it here would be a choice.
    raise RuntimeError(
        f"design-brief POST returned HTTP {resp.status_code}: {resp.text[:300]}"
    )
