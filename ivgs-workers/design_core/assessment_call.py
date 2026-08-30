"""CALL 2 — the assessments, authored where the practice cannot be seen.

WP-IVGS-12h, TASKS 1 and 3. ⛔ THIS MODULE IS THE PACKAGE.

THE MEASUREMENT THAT FORCED IT

design-contract-6 made both evidence kinds structural and closed RC-Q9f in both
limbs — zero hard refusals, three of three. And it produced this, five completed
generations running:

    LO-2 practice : "Explain why we write a placeholder zero in the ones column
                     before multiplying by the tens digit."
    LO-2 assess   : "Explain why we write a placeholder zero in the ones column
                     before multiplying by the tens digit."

9 of 15 outcome-pairs verbatim identical; 2 more the same sentence with a
*"Let's practice"* prefix. RC-Q9g.

⛳ THE DIAGNOSIS, AND THE INVERSION IT DICTATES. `assessment_scenes` was declared
BEFORE `practice_scenes`; declaration order binds generation order (12d, measured
in both directions). So the model wrote the assessment, and was then asked for a
practice on the same outcome **with the assessment sitting in its context** — and
copied it. The copy happens because the assessment is present while the practice
is asked for.

Three routes were named and two were refused with reasons:

  swap the order       ⛔ trades backward design — measured, load-bearing — for a
                       duplicate that would very likely reverse direction.
  more prompt          ⛔ v7 ALREADY says *"THE PRACTICE MUST NOT BE THE
                       ASSESSMENT WEARING A LABEL"*, in the model's own reading
                       order, and was in place before a single acceptance
                       generation ran. It wrote it twice anyway.
  a second call        ⛳ THIS. The calls separate the kinds, and the second call
                       never sees what it must not copy.

⛔ WHAT CALL 2 IS GIVEN, AND THE LIST IS EXHAUSTIVE

    the OUTCOMES        id and the operator's own text, injected server-side
                        exactly as call 1 gets them (RC-Q9 — the model has not
                        been trusted with outcome text since 12b)
    the PLAN            `assessment_plan`, verbatim. This is what makes the split
                        safe for backward design: the promise the model made at
                        the TOP of call 1, before any scene existed, is the brief
                        call 2 answers.
    a code-built SUMMARY of what each outcome's practice covered — the numbers it
                        used, how far it took the learner — built by
                        `design_core.contract.practice_summary`.

⛔ AND WHAT IT IS NOT GIVEN, WHICH IS THE ENTIRE MECHANISM

    NOT the practice narrations       the strings that were copied
    NOT `scenes`                      the expository arc, and the script's own
                                      worked examples inside it
    NOT the transcript                nothing of the source text reaches here

**The model cannot copy what it never sees.** Every other package in this lineage
made a defect unrepresentable in the GRAMMAR; this one makes it unrepresentable
in the CONTEXT, because a grammar cannot forbid two strings from being equal.

⚠ AND THE HONEST COST, STATED HERE RATHER THAN DISCOVERED. Call 2 designs the
independent attempt without seeing the lesson. It cannot anchor to a real *"now
you try"* span the script may contain (12f's B1 case), and it cannot judge the
lesson's register. What it has instead is the plan's own `learner_does` sentence
and a list of the numbers already spent. Whether that is enough is the
acceptance's question and not this docstring's claim.

⛳ AND IT RUNS INSIDE THE EXISTING STAGE BOUNDARY. No new pipeline stage, no
frozen-body edit: `clients.vllm_client`'s document-transform seam gained one
`await`, so an armed transform may make an engine call of its own between call
1's parse and the frozen body seeing the document. Both calls share ONE Celery
task, ONE job context and ONE declared time budget, split by
`WorkerConfig.storyboard_call_timeouts`.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence

import httpx
import structlog

logger = structlog.get_logger("ivgs.design_core.assessment_call")

#: The lineage the call-2 SYSTEM prompt is published into. Its own name, its own
#: version history, rollback by one UPDATE — the same treatment v1..v8 of the
#: design prompt get, because a prompt that is not versioned is a prompt nobody
#: can roll back (WP-IVGS-12 Task 3's whole argument, applied to the new one).
ASSESSMENT_PROMPT_TYPE = "assessment_authoring_system"


class AssessmentCallFailed(RuntimeError):
    """Call 2 did not produce assessments. WP-IVGS-12h TASK 3.

    ⛔ NAMED, AND FATAL TO THE JOB, AND THAT IS THE ORDER'S REQUIREMENT. The
    alternative — catch it and ship call 1's document — is a silent single-call
    fallback: a storyboard with a practice for every outcome, no independent
    attempt anywhere, and a `StageStatus.SUCCESS` on it. That is the RC-E failure
    class with better paperwork, and this lineage exists because of RC-E.

    The transform seam re-raises it as `DocumentTransformFatal`, the frozen stage
    body records the message in `output.errors`, writes no scenes, and reports
    `FAILED` — which `POST /jobs/{id}/resume` can re-dispatch.
    """


def _fetch_prompt(config: Any) -> str:
    """The active `assessment_authoring_system` row, or "" when none exists.

    ⚠ THE SAME SHAPE AS `pipeline_orchestrator_v2._fetch_active_prompt`, AND
    DELIBERATELY NOT AN IMPORT OF IT. That function lives in a task module the
    worker loads through Celery's loader; importing it from here would put a
    stage-orchestration module on the import path of the LLM client's transform
    seam. The IVGS-0.4 lesson is repeated in its filter: EXACT `prompt_type`
    match only, because the endpoint once ignored the filter and the last enum
    member won.
    """
    try:
        with httpx.Client(
            timeout=config.pipeline_api.timeout_seconds,
            headers={"Authorization": f"Bearer {config.pipeline_api.service_token}"},
        ) as client:
            resp = client.get(
                f"{config.pipeline_api.full_base_url}/prompts",
                params={"prompt_type": ASSESSMENT_PROMPT_TYPE, "is_active": "true"},
            )
        if resp.status_code != 200:
            return ""
        payload = resp.json()
        rows = payload if isinstance(payload, list) else payload.get("data", [])
        for row in rows:
            if isinstance(row, dict) and row.get("prompt_type") == ASSESSMENT_PROMPT_TYPE:
                return row.get("prompt_text") or ""
        return ""
    except Exception as exc:                                     # noqa: BLE001
        logger.warning(
            "assessment_prompt_fetch_failed",
            error_type=type(exc).__name__, error=str(exc),
        )
        return ""


def _motion_catalogue() -> Dict[str, Dict[str, str]]:
    """``{template: {parameter: kind}}``, read from the renderer's own registry.

    ⚠ RETURNS EMPTY ON ANY FAILURE rather than raising. A worker that cannot
    import the motion package must still be able to author assessments; what it
    loses is the ability to author a *motion* one, and the gate says so by name
    (`MOTION_WITHOUT_TEMPLATE`) instead of the whole storyboard failing.
    """
    try:
        from shared.motion.templates import param_kinds, template_names

        return {name: param_kinds(name) for name in template_names()}
    except Exception as exc:                                     # noqa: BLE001
        logger.warning(
            "assessment_call_motion_catalogue_unavailable",
            error_type=type(exc).__name__, error=str(exc),
        )
        return {}


def build_user_message(
    *,
    outcomes: Sequence[Dict[str, Any]],
    assessment_plan: Dict[str, Any],
    summary: Dict[str, Any],
) -> str:
    """Call 2's USER turn — assembled by code, from three facts and nothing else.

    ⛔ EVERY LINE OF THIS IS AUDITABLE AND THAT IS WHY IT IS BUILT HERE RATHER
    THAN IN A TEMPLATE. A Jinja template with the whole document in scope is one
    edit away from rendering `practice_scenes` "for context", which would undo
    the package silently and pass every test. The function receives three
    arguments; it cannot render what it was not handed.
    """
    lines: List[str] = ["THE OUTCOMES. These are the operator's own words.", ""]
    for outcome in outcomes:
        lines.append(f"  {outcome.get('id')} — {outcome.get('text')}")
    lines += ["", "YOUR OWN EVIDENCE PLAN, written before this lesson had a "
                  "single scene in it. This is the promise you are now keeping.", ""]
    for oid, entry in (assessment_plan or {}).items():
        entry = entry if isinstance(entry, dict) else {}
        lines.append(
            f"  {oid} — evidence_kind: {entry.get('evidence_kind')}; "
            f"the learner will: {entry.get('learner_does')}"
        )

    per_outcome = (summary or {}).get("per_outcome") or {}
    lines += ["", "WHAT THE SUPPORTED PRACTICE ALREADY COVERED. This is a FACT "
                  "SHEET built by code from the lesson, not the practice "
                  "wording — you are not being shown the practice, because your "
                  "job is to write what comes AFTER it.", ""]
    for oid in [o.get("id") for o in outcomes]:
        facts = per_outcome.get(str(oid)) or {}
        step = facts.get("step_reached") or {}
        lines.append(
            f"  {oid}: {facts.get('practice_scene_count', 0)} supported "
            f"attempt(s), {step.get('total_seconds', 0)}s on screen; "
            f"numbers used: {facts.get('numbers_used') or 'none'}; "
            f"motion templates: {step.get('motion_templates') or 'none'}; "
            f"phases reached: {step.get('motion_phases') or 'none'}; "
            f"bloom: {step.get('bloom_levels') or 'unstated'}; "
            f"media: {facts.get('media_types') or 'unstated'}"
        )

    # ⛔ THE MOTION TEMPLATE CATALOGUE, BUILT FROM THE REGISTRY. WP-IVGS-12h,
    # added after the first acceptance generation, which is why it is here and
    # not in the prompt: call 2's LO-1 assessment chose `motion_graphics` and
    # carried NO template, and the gate refused it `MOTION_WITHOUT_TEMPLATE`.
    # Correctly — and the model had no way to comply, because the template names
    # live in call 1's USER template (42,365 characters of it) and call 2 has
    # never seen that. Telling a model to name a template while withholding the
    # list of templates is a prompt asking for a guess.
    #
    # ⛳ AND IT IS READ FROM `shared.motion.templates` RATHER THAN TYPED OUT,
    # which is the one improvement on how call 1 is told. Call 1's template
    # prose is a TRANSCRIPTION — *"Choose from EXACTLY these four templates"* —
    # and a transcription is an accurate mirror with no authority (RC-P17). This
    # list cannot go stale, and the renderer gap 12f and 12g both found on a
    # division lesson shows up here as an ABSENCE the model can see rather than
    # as a template it invents.
    lines += ["", "THE MOTION TEMPLATES THE RENDERER ACTUALLY HAS. A "
                  "`motion_graphics` scene MUST carry `generation_params` with "
                  "one of these names and every parameter it declares, using "
                  "YOUR numbers. If none of them can draw your assessment, it "
                  "is not a motion scene — choose `image` or `talking_head`.", ""]
    for name, kinds in _motion_catalogue().items():
        params = ", ".join(f"{k}: {v}" for k, v in kinds.items())
        lines.append(f"  {{\"template\": \"{name}\", {params}}}")

    spent = (summary or {}).get("numbers_already_used") or []
    lines += [
        "",
        "⛔ EVERY NUMBER THIS LESSON HAS ALREADY WORKED, anywhere in it — in the "
        "teaching and in the practice alike:",
        f"  {spent if spent else 'none — this lesson uses no numbers'}",
        "",
        "Pose each assessment in numbers that are NOT in that list. If this "
        "outcome is not numeric, then the fresh thing is the CASE: a different "
        "example, a different situation, a different thing to explain — not the "
        "same question asked again in the same words.",
        "",
        "Write `assessment_scenes` now: exactly one scene per outcome id above.",
    ]
    return "\n".join(lines)


async def author_assessments(
    *,
    raw_contract: Dict[str, Any],
    outcomes: Sequence[Dict[str, Any]],
    config: Any,
    client: Any = None,
) -> Dict[str, Any]:
    """Make call 2 and return its ``assessment_scenes`` section.

    Raises :class:`AssessmentCallFailed` for every failure mode. There is no
    partial success: an assessment layer missing one outcome is a design the
    grammar of contract-6 would never have allowed, and manufacturing a
    placeholder for it would be inventing a design nobody authored — the
    complaint this whole package lineage exists to answer.
    """
    from design_core.contract import (
        assessment_authoring_schema, practice_summary, response_format_for,
    )

    ids = [str(o.get("id")) for o in outcomes if o.get("id")]
    if not ids:
        raise AssessmentCallFailed(
            "no outcome ids: call 2 has nothing to author assessments FOR. "
            "A project whose operator stated no outcomes never reaches here."
        )

    system_prompt = _fetch_prompt(config)
    if not system_prompt:
        # ⛔ NOT A FALLBACK TO A BAKED-IN STRING. WP-IVGS-12's whole Task 3 is
        # that an unversioned prompt is unrollbackable and invisible in the run
        # record; shipping a hidden default here would recreate exactly that,
        # in the one call whose behaviour is the package's claim.
        raise AssessmentCallFailed(
            f"no active {ASSESSMENT_PROMPT_TYPE!r} prompt is published. Run "
            "`app.scripts.wpivgs12_publish_design_prompts` inside ivgs-fastapi. "
            "Refusing to author assessments from an unversioned prompt."
        )

    summary = practice_summary(raw_contract, ids)
    user_prompt = build_user_message(
        outcomes=outcomes,
        assessment_plan=raw_contract.get("assessment_plan") or {},
        summary=summary,
    )
    schema = assessment_authoring_schema(outcome_ids=ids)
    vllm = config.get_vllm_config_for_stage("storyboard_generation")
    _, call2_timeout = config.storyboard_call_timeouts()

    owns_client = client is None
    if owns_client:
        from clients.vllm_client import VLLMClient

        client = VLLMClient(base_url=vllm["base_url"])

    logger.info(
        "assessment_call_starting",
        outcome_ids=ids,
        system_chars=len(system_prompt),
        user_chars=len(user_prompt),
        max_tokens=config.vllm.storyboard_call2_max_tokens,
        timeout_s=call2_timeout,
        numbers_already_used=summary.get("numbers_already_used"),
    )

    try:
        # ⚠ `chat` AND NOT `chat_json`. `chat_json` applies the document
        # transform — which is the function calling THIS one — and would recurse.
        # It also applies `_RESPONSE_FORMAT_OVERRIDE`, which is armed with call
        # 1's schema. So call 2 goes through the plain path and passes its own
        # `response_format` explicitly, which is what the seam is for.
        response = await client.chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=vllm["model"],
            base_url=vllm["base_url"],
            max_tokens=config.vllm.storyboard_call2_max_tokens,
            temperature=vllm["temperature"],
            top_p=vllm["top_p"],
            response_format=response_format_for(
                schema, name="ivgs_assessment_authoring",
            ),
            timeout=call2_timeout,
        )
    except Exception as exc:                                     # noqa: BLE001
        raise AssessmentCallFailed(
            f"the assessment authoring call failed: {type(exc).__name__}: {exc}"
        ) from exc
    finally:
        if owns_client:
            try:
                await client.close()
            except Exception:                                    # noqa: BLE001
                pass

    if (response.finish_reason or "").lower() == "length":
        usage = response.usage
        raise AssessmentCallFailed(
            "the assessment authoring call stopped at its output token limit "
            f"(finish_reason='length', max_tokens="
            f"{config.vllm.storyboard_call2_max_tokens}, completion_tokens="
            f"{usage.completion_tokens if usage else 'unknown'}). Raise "
            "IVGS_VLLM_ASSESSMENT_CALL_MAX_TOKENS. It is NOT repaired: a "
            "truncated assessment layer is a partial one, and completing it "
            "here would manufacture an attempt nobody designed."
        )

    try:
        document = json.loads((response.content or "").strip())
    except ValueError as exc:
        raise AssessmentCallFailed(
            f"the assessment authoring call did not return JSON: {exc}"
        ) from exc

    section = document.get("assessment_scenes") if isinstance(document, dict) else None
    if not isinstance(section, dict) or not section:
        raise AssessmentCallFailed(
            "the assessment authoring call returned no `assessment_scenes`. "
            f"Top-level keys: {list(document) if isinstance(document, dict) else type(document).__name__}"
        )
    missing = [oid for oid in ids if not section.get(oid)]
    if missing:
        # Grammar-guaranteed unreachable — `required` names every id and
        # `minItems` is 1 — and checked anyway, because this lineage is a record
        # of guarantees that turned out narrower than believed.
        raise AssessmentCallFailed(
            f"the assessment authoring call omitted {missing}, which the "
            "schema's `required` and `minItems: 1` should have made impossible. "
            "The structural guarantee has stopped holding."
        )

    usage = response.usage
    logger.info(
        "assessment_call_completed",
        outcome_ids=ids,
        prompt_tokens=usage.prompt_tokens if usage else None,
        completion_tokens=usage.completion_tokens if usage else None,
        origins=[
            ((s or {}).get("provenance") or {}).get("origin")
            for oid in ids for s in (section.get(oid) or [])
        ],
    )
    return section
