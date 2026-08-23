"""
WP-41 — the idempotency binding (AD-05 Draft 2 §6).

Draft 2 §6 exists because WP-31 Lane C measured it on node-07: a worker
SIGKILLed mid-fan-out left two scene activities whose bodies had finished but
whose completion had not reached the server, and **both bodies ran a second
time** on restart. Temporal guarantees the WORKFLOW advances exactly once;
activities execute AT LEAST once.

So this file asserts the property that has to hold at the other end of that
window: **a twice-delivered activity produces one effect.** It is the
executable half of WP-41 Task 3 -- the live SIGKILL demonstration is the other.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from temporal_pipeline.dag import build_pipeline_dag
from temporal_pipeline.idempotency import (
    STAGE_TOKENS,
    DuplicateDeliveryError,
    IdempotencyKey,
    IdempotentEffectStore,
)
from temporal_pipeline.reference_storyboard import reference_storyboard


@pytest.fixture
def store(tmp_path) -> IdempotentEffectStore:
    return IdempotentEffectStore(tmp_path / "job-under-test")


class TestKeyScheme:
    def test_key_is_job_stage_scene(self):
        key = IdempotencyKey("job-1", "s3a", scene_index=4)
        assert key.render() == "job-1:s3a:scene4"

    def test_whole_job_stages_carry_no_scene(self):
        assert IdempotencyKey("job-1", "s1").render() == "job-1:s1"

    def test_segment_index_is_reserved_for_stage_8_children(self):
        """AD-05 §5.4. Carried now so adding it is not a key-format migration."""
        key = IdempotencyKey("job-1", "s8", segment_index=3)
        assert key.render() == "job-1:s8:seg3"

    def test_key_is_readable_not_hashed(self):
        """
        An operator reading an object name or an event history must be able to
        see which job, stage and scene an artifact belongs to. WP-39's
        collision stayed invisible for hours partly because nothing in the
        record named the stage that was missing.
        """
        rendered = IdempotencyKey("bd99fe37", "s3a", scene_index=11).render()
        assert "bd99fe37" in rendered and "s3a" in rendered and "11" in rendered

    def test_for_stage_maps_every_pipeline_label(self):
        for label, token in STAGE_TOKENS.items():
            key = IdempotencyKey.for_stage("job-1", label, scene_index=0)
            assert key.stage == token

    def test_image_and_animation_get_different_tokens(self):
        """
        The two stages that shared one label on 2026-08-23. Scene indexes alone
        would already separate them -- a scene has one media_type -- but a key
        that cannot say WHICH stage produced an artifact is the fact WP-39
        destroyed when the animation run overwrote the image checkpoint.
        """
        image = IdempotencyKey.for_stage("job-1", "image_generation", 3)
        animation = IdempotencyKey.for_stage("job-1", "animation_generation", 3)
        assert image.render() != animation.render()

    def test_unknown_label_is_rejected(self):
        with pytest.raises(ValueError, match="no idempotency token"):
            IdempotencyKey.for_stage("job-1", "hologram_generation")

    def test_empty_job_or_stage_is_rejected(self):
        with pytest.raises(ValueError):
            IdempotencyKey("", "s1")
        with pytest.raises(ValueError):
            IdempotencyKey("job-1", "")

    def test_every_dag_node_has_a_token(self):
        for node in build_pipeline_dag(reference_storyboard()):
            if node.is_gate:
                continue
            assert node.idempotency_stage
            assert node.idempotency_stage == STAGE_TOKENS[node.label]


class TestAtLeastOnceProducesOneEffect:
    def test_second_delivery_does_not_re_produce(self, store):
        key = IdempotencyKey("job-1", "s3a", scene_index=4)
        calls = []

        def produce():
            calls.append(len(calls) + 1)
            return {"artifact": f"stub://render-{len(calls)}"}

        first = store.apply(key, produce, attempt=1)
        second = store.apply(key, produce, attempt=1)   # same attempt: a redelivery

        assert calls == [1], "the body produced twice"
        assert first.created is True
        assert second.created is False
        assert second.record == first.record
        assert store.effect_count() == 1

    def test_deliveries_and_effects_are_counted_separately(self, store):
        """
        Two independently readable numbers. WP-31's first evidence script
        reported a false PASS over an empty table; a pair of counts cannot be
        trivially true the way one can.
        """
        key = IdempotencyKey("job-1", "s1")
        for attempt in (1, 2, 3):
            store.apply(key, lambda: {"artifact": "stub://one"}, attempt=attempt)

        assert store.delivery_count(key) == 3
        assert store.effect_count() == 1
        assert store.duplicate_deliveries() == {"job-1:s1": 3}

    def test_a_clean_run_reports_no_duplicates(self, store):
        for i in range(6):
            store.apply(
                IdempotencyKey("job-1", "s3", scene_index=i),
                lambda i=i: {"artifact": f"stub://scene-{i}"},
            )
        assert store.effect_count() == 6
        assert store.duplicate_deliveries() == {}

    def test_different_scenes_do_not_collide(self, store):
        for i in (0, 1, 2):
            store.apply(
                IdempotencyKey("job-1", "s3", scene_index=i),
                lambda i=i: {"artifact": f"stub://scene-{i}"},
            )
        assert store.effect_count() == 3
        assert sorted(store.keys()) == [
            "job-1:s3:scene0",
            "job-1:s3:scene1",
            "job-1:s3:scene2",
        ]

    def test_image_and_animation_on_the_same_scene_index_do_not_collide(self, store):
        """
        Cannot happen from one storyboard -- but this is the exact shape of
        WP-39's collision, and a key scheme that permitted it would be one
        upstream change away from repeating it.
        """
        store.apply(
            IdempotencyKey.for_stage("job-1", "image_generation", 3),
            lambda: {"artifact": "stub://image-3"},
        )
        store.apply(
            IdempotencyKey.for_stage("job-1", "animation_generation", 3),
            lambda: {"artifact": "stub://animation-3"},
        )
        assert store.effect_count() == 2

    def test_the_record_carries_its_own_key(self, store):
        key = IdempotencyKey("job-1", "s7")
        outcome = store.apply(key, lambda: {"artifact": "stub://draft"})
        assert outcome.record["idempotency_key"] == "job-1:s7"

    def test_concurrent_deliveries_converge_on_one_effect(self, store):
        """
        Two workers can hold the same activity at once -- which is exactly what
        D1's redelivery does today, and what Temporal's at-least-once delivery
        can still do at a much smaller window.

        Note what is and is not claimed. Under a genuine race MORE THAN ONE
        BODY MAY RUN: a delivery cannot know it has lost until it tries to
        claim the key, and claiming before doing the work would leave a
        poisoned claim behind every crash. That duplicated work IS the
        at-least-once property; WP-31 Lane C measured two scene bodies doing
        it. What must hold, and what Draft 2 §6 requires, is that they
        CONVERGE: one effect record exists and every delivery reads that same
        one. A second render must not become a second artifact.
        """
        # 25 rounds, because one round on a fast machine may never actually
        # race. The first version of this test raced perhaps one run in five,
        # and the intermittent failure it produced was a genuine bug in the
        # store's write path -- see the comment on IdempotentEffectStore.apply.
        for round_number in range(25):
            key = IdempotencyKey("job-1", "s3v", scene_index=round_number)
            produced: list[int] = []

            def deliver(n, key=key, produced=produced):
                def produce():
                    produced.append(n)
                    return {"artifact": f"stub://by-{n}"}

                return store.apply(key, produce, attempt=1)

            with ThreadPoolExecutor(max_workers=8) as pool:
                outcomes = list(pool.map(deliver, range(8)))

            assert sum(1 for o in outcomes if o.created) == 1, "two writers both won"
            assert store.delivery_count(key) == 8
            assert len(produced) >= 1  # >1 is the at-least-once window, not a defect
            # The one that matters: nobody reads a half-written record.
            assert all(o.record.get("artifact") for o in outcomes), (
                "a delivery read an empty or partial effect record"
            )
            assert len({json.dumps(o.record, sort_keys=True) for o in outcomes}) == 1

        assert store.effect_count() == 25

    def test_strict_mode_can_raise_but_the_pipeline_never_uses_it(self, store):
        key = IdempotencyKey("job-1", "s2")
        store.apply(key, lambda: {"artifact": "stub://storyboard"})
        with pytest.raises(DuplicateDeliveryError):
            store.apply(key, lambda: {"artifact": "x"}, strict=True)

    def test_the_effect_survives_a_new_store_object(self, tmp_path):
        """A restarted worker must see what the dead one wrote."""
        key = IdempotencyKey("job-1", "s6")
        IdempotentEffectStore(tmp_path / "job").apply(
            key, lambda: {"artifact": "stub://head"}
        )
        after_restart = IdempotentEffectStore(tmp_path / "job")
        outcome = after_restart.apply(key, lambda: {"artifact": "stub://head-again"})
        assert outcome.created is False
        assert outcome.record["artifact"] == "stub://head"
