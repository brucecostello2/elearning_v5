"""
Retry, timeout and liveness policy per activity (AD-05 §9, Draft 2 Appendix C).

AD-05 §9 is explicit that spec Table 6-4's per-stage attempts and backoff
"map directly and are **preserved as values**, not redesigned." So each row
below carries BOTH numbers:

  * ``celery_*`` — what the decorator says at HEAD, read off the source, so a
    reviewer can check the translation instead of trusting it;
  * everything else — the declarative policy the activity actually gets.

Two translations are not identity, and both are stated rather than smuggled:

**Attempts.** Celery's ``max_retries=N`` means N retries *after* the first run,
i.e. N+1 executions. Temporal's ``maximum_attempts`` is the total. Preserving
the *behaviour* therefore means ``maximum_attempts = max_retries + 1``, not
``= max_retries``. Preserving the literal integer would quietly remove one
execution from every stage. ``test_policies.py`` pins the relation.

**Timeouts.** ``start_to_close_timeout`` is taken from Appendix C, which in
several places is deliberately more generous than today's ``time_limit`` —
that is the point of §9's "a long render is *long*, not suspicious": the hard
ceiling relaxes because ``heartbeat_timeout`` now carries liveness. Today's
``time_limit`` is kept in the row so the widening is visible and reviewable,
not discovered later. Where Appendix C gives no timeout (Stage 4), today's
value is used.

Heartbeating is a REQUIREMENT on the activity wrapper, not an option (§9).
Only the reservation activities are exempt: they are sub-second calls into
``ivgs-scheduler``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from models.task_result import PipelineStage


# NOT Celery's 180. `IVGSBaseTask` (celery_app.py:677-698) overrides the class
# defaults for every stage task that inherits it:
#
#     max_retries          = 4
#     default_retry_delay  = 5      <- celery_app.py:694
#     retry_backoff        = True   <- so the 5 s is a FIRST interval, not a fixed one
#     retry_backoff_max    = 300    <- celery_app.py:696
#     retry_jitter         = True
#
# Reading 180 off the Celery docs instead of off the base class would have put
# a 180 s first retry on stages 1 and 2 where the system uses 5. The test in
# tests/temporal reads these numbers off the live task objects for exactly
# that reason.
IVGS_BASE_RETRY_DELAY_S = 5

# celery_app.py:696 -- retry_backoff_max. Preserved as maximum_interval so the
# declarative policy's backoff curve tops out where today's does.
IVGS_BASE_RETRY_BACKOFF_MAX_S = 300

# AD-05 §9: exhaustion is a failed workflow, visible in the UI. A deterministic
# failure must not burn attempts on its way there. These are the two error
# types the stub activities raise; the real wrappers extend the list with the
# stage's own deterministic failures (ValueError in Stage 4, Stage7RenderError).
DEFAULT_NON_RETRYABLE: Tuple[str, ...] = (
    "StubPermanentError",
    "ValueError",
)


@dataclass(frozen=True)
class ActivityPolicy:
    """One row of Appendix C, in executable form."""

    activity: str
    label: str                       # PipelineStage value this activity serves
    queue: str                       # AD-05 §4.2

    # --- what Celery does today, read off the decorator at HEAD -------------
    celery_task_name: str
    celery_max_retries: int
    celery_retry_delay_s: int
    celery_soft_time_limit_s: Optional[int]
    celery_time_limit_s: Optional[int]

    # --- what the activity gets --------------------------------------------
    start_to_close_s: int
    heartbeat_s: Optional[int]
    backoff_coefficient: float = 2.0
    maximum_interval_s: int = IVGS_BASE_RETRY_BACKOFF_MAX_S
    non_retryable_error_types: Tuple[str, ...] = DEFAULT_NON_RETRYABLE

    @property
    def maximum_attempts(self) -> int:
        """Celery's N retries are N+1 executions. Temporal counts executions."""
        return self.celery_max_retries + 1

    @property
    def initial_interval_s(self) -> int:
        """Celery's ``default_retry_delay`` is the first backoff interval."""
        return self.celery_retry_delay_s


# ---------------------------------------------------------------------------
# The table
# ---------------------------------------------------------------------------
#
# Sources, all at HEAD:
#   stage1_transcript.py:430-436     stage2_storyboard.py:451-457
#   stage3_images.py:568-578         video_generation_task.py:446-451
#   stage4_manifest.py:82-89         stage5_voiceover.py:490-500
#   talking_head_task.py:394-399     stage7_prototype_draft.py:328-333
#   stage8_final_render.py:342-347
# Queues for stage 3 and stage 5 come from TASK_ROUTES (celery_app.py:126-160)
# because their decorators carry no queue= of their own.

REFINE_TRANSCRIPT = ActivityPolicy(
    activity="refine_transcript",
    label=PipelineStage.TRANSCRIPT_REFINEMENT.value,
    queue="gpu_llm",
    celery_task_name="tasks.stage1_transcript.refine_transcript_task",
    celery_max_retries=4,
    celery_retry_delay_s=IVGS_BASE_RETRY_DELAY_S,
    celery_soft_time_limit_s=120,
    celery_time_limit_s=150,
    start_to_close_s=5 * 60,
    heartbeat_s=30,
)

GENERATE_STORYBOARD = ActivityPolicy(
    activity="generate_storyboard",
    label=PipelineStage.STORYBOARD_GENERATION.value,
    queue="gpu_llm",
    celery_task_name="tasks.stage2_storyboard.generate_storyboard_task",
    celery_max_retries=4,
    celery_retry_delay_s=IVGS_BASE_RETRY_DELAY_S,
    celery_soft_time_limit_s=120,
    celery_time_limit_s=150,
    start_to_close_s=5 * 60,
    heartbeat_s=30,
)

RENDER_SCENE_IMAGE = ActivityPolicy(
    activity="render_scene_image",
    label=PipelineStage.IMAGE_GENERATION.value,
    queue="gpu_image",
    celery_task_name="tasks.stage3_images.generate_scene_images_task",
    celery_max_retries=2,
    celery_retry_delay_s=10,
    celery_soft_time_limit_s=1800,
    celery_time_limit_s=2100,
    start_to_close_s=45 * 60,
    heartbeat_s=60,
)

# Same engine, same queue, same Celery task as the image branch -- and, until
# WP-39, the same stage label, which is exactly how a 12-scene run of it was
# swallowed. It gets its own policy row for the same reason it gets its own
# DagNode: so that "which stage is this" is never inferred.
RENDER_SCENE_ANIMATION = ActivityPolicy(
    activity="render_scene_animation",
    label=PipelineStage.ANIMATION_GENERATION.value,
    queue="gpu_image",
    celery_task_name="tasks.stage3_images.generate_scene_images_task",
    celery_max_retries=2,
    celery_retry_delay_s=10,
    celery_soft_time_limit_s=1800,
    celery_time_limit_s=2100,
    start_to_close_s=45 * 60,
    heartbeat_s=60,
)

RENDER_SCENE_VIDEO = ActivityPolicy(
    activity="render_scene_video",
    label=PipelineStage.VIDEO_GENERATION.value,
    queue="gpu_video",
    celery_task_name="tasks.video_generation_task.generate_video_clips",
    celery_max_retries=2,
    celery_retry_delay_s=30,
    celery_soft_time_limit_s=3600,
    # D1: 3900 sits ABOVE broker_visibility_timeout=3600 (config.py:214-215)
    # with task_acks_late (celery_app.py:288), so a task past 3600 s is
    # redelivered mid-flight. Under Temporal the visibility timeout is deleted
    # outright (Draft 2 Appendix B row 2) and liveness is the heartbeat below.
    celery_time_limit_s=3900,
    start_to_close_s=90 * 60,
    heartbeat_s=60,
)

BUILD_COMPOSITION_MANIFEST = ActivityPolicy(
    activity="build_composition_manifest",
    label=PipelineStage.COMPOSITION_MANIFEST.value,
    queue="default",
    celery_task_name="tasks.stage4_manifest.build_composition_manifest",
    celery_max_retries=2,
    celery_retry_delay_s=30,
    celery_soft_time_limit_s=None,
    celery_time_limit_s=None,
    start_to_close_s=10 * 60,
    heartbeat_s=30,
)

GENERATE_VOICEOVER = ActivityPolicy(
    activity="generate_voiceover",
    label=PipelineStage.TTS_AUDIO.value,
    queue="gpu_tts",
    # The registered name says stage4 and the file says stage5. The workflow
    # holds a direct function reference, so this string is a record of what is
    # being replaced, not a lookup key -- P2.3's defect class, closed.
    celery_task_name="tasks.stage4_voiceover.generate_voiceover_task",
    celery_max_retries=3,
    celery_retry_delay_s=10,
    celery_soft_time_limit_s=900,
    celery_time_limit_s=1200,
    start_to_close_s=30 * 60,
    heartbeat_s=60,
)

RENDER_TALKING_HEAD = ActivityPolicy(
    activity="render_talking_head",
    label=PipelineStage.TALKING_HEAD_RENDER.value,
    queue="gpu_talking_head",
    celery_task_name="tasks.talking_head_task.render_talking_head",
    celery_max_retries=2,
    celery_retry_delay_s=30,
    celery_soft_time_limit_s=3600,
    celery_time_limit_s=3900,          # D1 again, same shape as video
    start_to_close_s=90 * 60,
    heartbeat_s=60,
)

ASSEMBLE_PROTOTYPE_DRAFT = ActivityPolicy(
    activity="assemble_prototype_draft",
    label=PipelineStage.PROTOTYPE_DRAFT.value,
    queue="composition",
    celery_task_name="tasks.prototype_draft_task.assemble_prototype_draft",
    celery_max_retries=2,
    celery_retry_delay_s=30,
    celery_soft_time_limit_s=900,
    celery_time_limit_s=960,
    start_to_close_s=30 * 60,
    heartbeat_s=60,
    # WP-27 / swallow-register 14: Stage 7 raises Stage7RenderError rather than
    # returning status=failed. It is deterministic -- retrying an ffmpeg
    # composition that produced no draft produces no draft again.
    non_retryable_error_types=DEFAULT_NON_RETRYABLE + ("Stage7RenderError",),
)

RENDER_FINAL = ActivityPolicy(
    activity="render_final",
    label=PipelineStage.FINAL_RENDER.value,
    queue="composition",
    celery_task_name="tasks.final_render_task.render_final",
    celery_max_retries=2,
    celery_retry_delay_s=30,
    celery_soft_time_limit_s=1800,
    celery_time_limit_s=1860,
    # Appendix C's "s2c 60 m/segment" is a per-SEGMENT budget for the M5 child
    # workflows (AD-05 §5.4). Stage 8 is one activity in this shadow, so the
    # whole-stage ceiling is what applies here; the per-segment figure arrives
    # with the child workflows and is not invented early.
    start_to_close_s=60 * 60,
    heartbeat_s=60,
)

# AD-05 §6: bracketing activities, release in the workflow's `finally`. This is
# the structural fix for D4's 7-acquire / 3-broken-release asymmetry: the
# release cannot be forgotten at a call site, because there are no call sites.
ACQUIRE_GPU_RESERVATION = ActivityPolicy(
    activity="acquire_gpu_reservation",
    label="",
    queue="default",
    celery_task_name="utils.gpu_utils.acquire_gpu_reservation",
    # Not a Celery task today -- a helper called inline from seven stage
    # bodies. 2 retries at 1 s is a scheduler round-trip budget, not a
    # translation of an existing constant; Temporal also rejects a zero
    # initial_interval, so 0 was never an option.
    celery_max_retries=2,
    celery_retry_delay_s=1,
    celery_soft_time_limit_s=None,
    celery_time_limit_s=None,
    start_to_close_s=60,
    heartbeat_s=None,
)

RELEASE_GPU_RESERVATION = ActivityPolicy(
    activity="release_gpu_reservation",
    label="",
    queue="default",
    celery_task_name="utils.gpu_utils.release_gpu_reservation",
    celery_max_retries=2,
    celery_retry_delay_s=1,
    celery_soft_time_limit_s=None,
    celery_time_limit_s=None,
    start_to_close_s=60,
    heartbeat_s=None,
)


STAGE_POLICIES: Tuple[ActivityPolicy, ...] = (
    REFINE_TRANSCRIPT,
    GENERATE_STORYBOARD,
    RENDER_SCENE_IMAGE,
    RENDER_SCENE_VIDEO,
    RENDER_SCENE_ANIMATION,
    BUILD_COMPOSITION_MANIFEST,
    GENERATE_VOICEOVER,
    RENDER_TALKING_HEAD,
    ASSEMBLE_PROTOTYPE_DRAFT,
    RENDER_FINAL,
)

RESERVATION_POLICIES: Tuple[ActivityPolicy, ...] = (
    ACQUIRE_GPU_RESERVATION,
    RELEASE_GPU_RESERVATION,
)

ALL_POLICIES: Tuple[ActivityPolicy, ...] = STAGE_POLICIES + RESERVATION_POLICIES

POLICY_BY_LABEL: Dict[str, ActivityPolicy] = {p.label: p for p in STAGE_POLICIES}
POLICY_BY_ACTIVITY: Dict[str, ActivityPolicy] = {p.activity: p for p in ALL_POLICIES}


# ---------------------------------------------------------------------------
# GPU reservation, and why it is not fatal here
# ---------------------------------------------------------------------------
#
# AD-05 O-3 was RULED on 2026-08-22: (a) fatal-with-retry -- but explicitly
# "contingent on ledger P2.6 having made the heartbeat registry real by
# implementation time. If P2.6 has not landed when Step 4 of §11.2 is reached,
# this decision reopens rather than shipping fatal against an empty registry
# (total_nodes:0), which would fail every GPU stage."
#
# OPERATOR RULING 2026-08-23: fail-open STANDS -- and the premise WP-41 first
# argued it from was wrong, so it is corrected here rather than left to rot.
#
# The registry is NOT empty. An earlier draft of this comment cited CLAUDE.md
# §7's "total_nodes:0" (WP-08, 2026-08-23), which WP-38 superseded the same day
# by fixing the registration that _detect_gpu_identity was skipping. Reading a
# register instead of re-checking the code it describes is exactly what
# CLAUDE.md §4 warns against.
#
# What is actually true, measured at 192.168.1.90:8002/fleet, 2026-08-23
# 23:14:24Z:
#
#     total_nodes  : 6          <- for THREE physical GPU nodes; entries are
#                                  keyed by container id, so a recreation
#                                  registers a ghost rather than re-registering
#     alive_nodes  : 0          <- every heartbeat 31 min to 5.5 h stale
#     queue_depth  : urgent 24  <- still accumulating, still unexplained
#
# So neither "the registry is empty" nor "the nodes registered today" is the
# right test, and a fatal policy evaluated at that moment would have failed
# every GPU stage. The flip is re-evaluated at M3.3 step 4 against a FRESH
# REGISTRY HEALTH CHECK -- not against this comment, and not against any
# document. Flipping it is one boolean and one test edit; deciding to is not.
GPU_RESERVATION_FAILURE_IS_FATAL = False


def as_temporal_retry_policy(policy: ActivityPolicy):
    """
    Build a ``temporalio.common.RetryPolicy`` from a row.

    Imported lazily so that every other module in this package -- and every
    test of them -- keeps working in a venv with no Temporal SDK installed.
    """
    from datetime import timedelta

    from temporalio.common import RetryPolicy

    return RetryPolicy(
        initial_interval=timedelta(seconds=policy.initial_interval_s),
        backoff_coefficient=policy.backoff_coefficient,
        maximum_interval=timedelta(seconds=policy.maximum_interval_s),
        maximum_attempts=policy.maximum_attempts,
        non_retryable_error_types=list(policy.non_retryable_error_types),
    )
