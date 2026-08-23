"""
The idempotency binding WP-31 measured into existence (AD-05 Draft 2 §6).

Why this module exists
----------------------

AD-05 Draft 1 §5.2 says D2 "becomes structurally impossible" under Temporal.
That is true of D2 as written — the Redis counter is gone. WP-31 Lane C then
measured what replaces it, on the node-07 cluster, 2026-08-22:

    A worker was SIGKILLed during the scene fan-out. Two scene activities had
    finished their work and written their completion to disk, but the worker
    died before reporting completion to the server. On restart, the server
    rescheduled both, and both bodies executed a second time.

That is correct at-least-once behaviour. The workflow advances exactly once;
activities execute *at least* once. Draft 2 §6 makes the consequence binding:

    1. Every activity that writes MUST be idempotent on
       ``(job_id, stage, scene_index)``.
    2. Activity wrappers MUST NOT assume single execution. Any increment,
       append or insert is suspect and needs a natural key or an upsert.

This module is (1) and (2) as code rather than as a paragraph: a key scheme,
and a store whose ``apply`` is a compare-and-create, so a body that runs twice
produces one effect and the second call learns it was second.

**What the store guarantees, precisely.** At most one effect record exists per
key, and every delivery -- winner or loser -- reads that same record. It does
NOT guarantee that the work runs once. Under a genuine race, two deliveries can
both do the work before either claims the key, and claiming before doing the
work would leave a poisoned claim behind every crash. Duplicated *work* is the
at-least-once property and is unavoidable; duplicated *artifacts* are the
defect, and are what this prevents.

What the real wrappers will do with it
--------------------------------------

The stub effect store here writes a JSON file per key. The production wrapper
substitutes the stage's own natural key — the ``assets`` row keyed on
``(project_id, scene_id, asset_type)``, the SeaweedFS object addressed by
``content_hash``, the ``pipeline_checkpoints`` upsert on ``(job_id,
stage_name)`` — and keeps the same ``apply`` shape. The property under test
is the same one either way: **the second delivery must converge, not
duplicate.**

Note the checkpoint upsert is itself the WP-39 lesson: ``(job_id, stage_name)``
is only a natural key if the stage NAME is right. The animation run wrote under
``image_generation`` and overwrote 4 scenes of image work with 12 scenes of
animation work — one checkpoint for two stages. An idempotency key is only as
good as the identity in it, which is why ``stage`` here comes from the DagNode
and never from a task's own default.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple


# Stage tokens. These are the values AD-05 Draft 2 Appendix C's "Idempotency
# key" column carries, with one addition: Appendix C's stage-3 row covers
# "render_scene_image / render_scene_animation" together and gives them one
# token, `s3`. They get separate tokens here.
#
# Strictly, `(job_id, "s3", scene_index)` is already unique across the two --
# a scene has exactly one media_type, so no scene_index appears under both.
# The separation is not for uniqueness. It is so that a key can be read back
# and say WHICH stage produced the artifact, which is precisely the fact the
# WP-39 defect destroyed: after the animation run overwrote the image
# checkpoint, nothing in the record could tell you the image run had happened.
STAGE_TOKENS: Dict[str, str] = {
    "transcript_refinement": "s1",
    "storyboard_generation": "s2",
    "image_generation": "s3",
    "video_generation": "s3v",
    "animation_generation": "s3a",
    "composition_manifest": "s4",
    "tts_audio": "s5",
    "talking_head_render": "s6",
    "prototype_draft": "s7",
    "final_render": "s8",
}


@dataclass(frozen=True)
class IdempotencyKey:
    """
    ``(job_id, stage, scene_index)`` — Draft 2 §6 requirement 1.

    ``scene_index`` is None for the whole-job stages (1, 2, 4, 5, 6, 7) and an
    int for the per-scene fan-out. ``segment_index`` is reserved for AD-05
    §5.4's Stage 8 child workflows; it is carried now so that adding them is
    not a key-format migration.
    """

    job_id: str
    stage: str
    scene_index: Optional[int] = None
    segment_index: Optional[int] = None

    def __post_init__(self) -> None:
        if not self.job_id:
            raise ValueError("idempotency key needs a job_id")
        if not self.stage:
            raise ValueError("idempotency key needs a stage token")

    @classmethod
    def for_stage(
        cls,
        job_id: str,
        label: str,
        scene_index: Optional[int] = None,
        segment_index: Optional[int] = None,
    ) -> "IdempotencyKey":
        """Build a key from a PipelineStage value rather than a raw token."""
        try:
            token = STAGE_TOKENS[label]
        except KeyError:
            raise ValueError(f"no idempotency token for stage label {label!r}") from None
        return cls(
            job_id=job_id,
            stage=token,
            scene_index=scene_index,
            segment_index=segment_index,
        )

    def render(self) -> str:
        """
        Flatten to the string the store and the logs use.

        Deliberately not a hash: an operator reading an event history or an
        object name has to be able to see which job, which stage and which
        scene an artifact belongs to. Opaque keys are how WP-39's collision
        stayed invisible for three hours.
        """
        parts = [self.job_id, self.stage]
        if self.scene_index is not None:
            parts.append(f"scene{self.scene_index}")
        if self.segment_index is not None:
            parts.append(f"seg{self.segment_index}")
        return ":".join(parts)

    def __str__(self) -> str:  # pragma: no cover - convenience
        return self.render()


@dataclass
class EffectOutcome:
    """What ``IdempotentEffectStore.apply`` reports back."""

    key: str
    record: Dict[str, Any]
    created: bool          # True on the delivery that did the work
    deliveries: int        # how many times apply() has been called for this key


class DuplicateDeliveryError(RuntimeError):
    """Raised only by ``apply(..., strict=True)``; the pipeline never uses it."""


class IdempotentEffectStore:
    """
    A tiny compare-and-create store, standing in for the real write path.

    ``apply`` is the whole interface. It runs ``produce()`` only if the key has
    no record yet, and the create is ``O_CREAT | O_EXCL`` so two processes
    racing on the same key cannot both win. Delivery counts are recorded in a
    separate append-only file, so "how many times was this activity delivered"
    and "how many effects exist" are two independently readable numbers — which
    is the pair the WP-31 demonstration needed and did not have on its first
    run.
    """

    def __init__(self, root: os.PathLike | str) -> None:
        self.root = Path(root)
        self.effects = self.root / "effects"
        self.deliveries = self.root / "deliveries.jsonl"

    def _ensure(self) -> None:
        self.effects.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # Keys carry ':' -- legal on Linux but noisy in a filename.
        return self.effects / (key.replace(":", "__") + ".json")

    def _record_delivery(self, key: str, attempt: int, created: bool) -> int:
        self._ensure()
        line = json.dumps(
            {
                "key": key,
                "attempt": attempt,
                "created": created,
                "pid": os.getpid(),
            }
        )
        # fsync: the worker running this is about to be SIGKILLed on purpose.
        with self.deliveries.open("a") as fh:
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        return self.delivery_count(key)

    def apply(
        self,
        key: IdempotencyKey | str,
        produce: Callable[[], Dict[str, Any]],
        *,
        attempt: int = 1,
        strict: bool = False,
    ) -> EffectOutcome:
        """
        Produce the effect for ``key`` at most once, however often we are called.

        ``produce`` is only invoked on the delivery that wins the create. Every
        delivery — winning or not — is recorded, so the demonstration can show
        N deliveries against 1 effect.
        """
        rendered = key.render() if isinstance(key, IdempotencyKey) else key
        self._ensure()
        path = self._path(rendered)

        existing = self._read(path)
        if existing is not None:
            deliveries = self._record_delivery(rendered, attempt, created=False)
            if strict:
                raise DuplicateDeliveryError(f"{rendered} already has an effect")
            return EffectOutcome(rendered, existing, created=False, deliveries=deliveries)

        record = dict(produce())
        record.setdefault("idempotency_key", rendered)

        # Write to a private temp file, fsync it, THEN link it into place.
        # os.link is atomic and fails if the target exists, so the effect path
        # never exists in a half-written state.
        #
        # The obvious version -- O_CREAT|O_EXCL on the effect path, then write
        # -- is a real bug, and it was caught as an intermittent test failure
        # before it was understood: a second delivery arriving between the
        # create and the write reads an EMPTY file, gets None from the JSON
        # decode, tries its own create, loses, and returns `{}` as "the record
        # that already existed". Two deliveries then disagree about what the
        # artifact is, which is precisely the property this class exists to
        # provide. Under a real worker the window is a disk write wide.
        tmp_fd, tmp_name = tempfile.mkstemp(dir=str(self.effects), suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w") as fh:
                json.dump(record, fh, sort_keys=True)
                fh.flush()
                os.fsync(fh.fileno())
            try:
                os.link(tmp_name, path)
            except FileExistsError:
                # Lost the race to a concurrent delivery. Its record is the
                # truth, and by construction it is fully written.
                existing = self._read(path)
                deliveries = self._record_delivery(rendered, attempt, created=False)
                return EffectOutcome(
                    rendered, existing or {}, created=False, deliveries=deliveries
                )
        finally:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass

        deliveries = self._record_delivery(rendered, attempt, created=True)
        return EffectOutcome(rendered, record, created=True, deliveries=deliveries)

    # --- read side ---------------------------------------------------------

    @staticmethod
    def _read(path: Path) -> Optional[Dict[str, Any]]:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            return None

    def get(self, key: IdempotencyKey | str) -> Optional[Dict[str, Any]]:
        rendered = key.render() if isinstance(key, IdempotencyKey) else key
        return self._read(self._path(rendered))

    def effect_count(self) -> int:
        if not self.effects.exists():
            return 0
        return len(list(self.effects.glob("*.json")))

    def keys(self) -> Tuple[str, ...]:
        if not self.effects.exists():
            return ()
        return tuple(
            sorted(p.stem.replace("__", ":") for p in self.effects.glob("*.json"))
        )

    def delivery_count(self, key: IdempotencyKey | str | None = None) -> int:
        if not self.deliveries.exists():
            return 0
        rendered = (
            key.render() if isinstance(key, IdempotencyKey) else key
        ) if key is not None else None
        count = 0
        with self.deliveries.open() as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rendered is None or rec.get("key") == rendered:
                    count += 1
        return count

    def duplicate_deliveries(self) -> Dict[str, int]:
        """Keys delivered more than once, and how many times. The headline number."""
        counts: Dict[str, int] = {}
        if not self.deliveries.exists():
            return counts
        with self.deliveries.open() as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                k = rec.get("key", "")
                counts[k] = counts.get(k, 0) + 1
        return {k: v for k, v in sorted(counts.items()) if v > 1}
