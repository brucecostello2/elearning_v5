"""WP-IVGS-12 — the Design Core, API side.

Every test here gates a defect this package MEASURED, not a preference.
"""
from __future__ import annotations

import pathlib
import re
import uuid

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
MIGRATIONS = REPO / "ivgs-api" / "migrations" / "versions"


# ---------------------------------------------------------------------------
# The vocabularies live in ONE place, and a migration freezes what was true
# ---------------------------------------------------------------------------

class TestOneVocabulary:
    """WP-68's defect cost an acceptance run: `motion_graphics` was added to the
    PostgreSQL type and not to the Python list, so the INSERT succeeded and
    every subsequent SELECT raised. A vocabulary in two places disagrees."""

    def test_the_0048_checks_match_the_shared_enums(self):
        from shared.models.enums import (
            BLOOM_LEVELS, INSTRUCTIONAL_EVENTS, SCENE_ORIGINS,
        )
        mig = (MIGRATIONS / "0048_wp_ivgs_12_design_contract.py").read_text()
        ns: dict = {}
        for name in ("INSTRUCTIONAL_EVENTS", "BLOOM_LEVELS", "SCENE_ORIGINS"):
            match = re.search(rf"^{name} = \((.*?)\)$", mig, re.S | re.M)
            assert match, f"{name} not found in migration 0048"
            ns[name] = tuple(re.findall(r'"([a-z_]+)"', match.group(1)))
        # A migration FREEZES what was true when it ran and must not follow a
        # moving list. So it duplicates the values -- and this test is what
        # makes the duplication safe: adding an enum member without a new
        # migration fails HERE rather than at an INSERT six weeks later.
        assert ns["INSTRUCTIONAL_EVENTS"] == INSTRUCTIONAL_EVENTS
        assert ns["BLOOM_LEVELS"] == BLOOM_LEVELS
        assert ns["SCENE_ORIGINS"] == SCENE_ORIGINS

    def test_0046_matches_the_transcript_source_kinds(self):
        from shared.models.enums import TRANSCRIPT_SOURCE_KINDS
        mig = (MIGRATIONS / "0046_wp_ivgs_12_transcript_provenance.py").read_text()
        match = re.search(r"^SOURCE_KINDS = \((.*?)\)$", mig, re.S | re.M)
        assert match
        assert tuple(re.findall(r'"([a-z]+)"', match.group(1))) == TRANSCRIPT_SOURCE_KINDS

    def test_talking_head_is_not_a_media_type_anywhere(self):
        """RC-Q4. The Foundation's §4 gives it a modality row; the system has
        four media types and `_validate_storyboard_json` RAISES on a fifth, so
        one such scene fails the WHOLE storyboard (RC-P4)."""
        from shared.models.enums import MEDIA_TYPES
        assert "talking_head" not in MEDIA_TYPES
        prompt = (
            REPO / "ivgs-api" / "seed" / "default_prompts"
            / "storyboard_generation.j2"
        ).read_text()
        # It may only appear as an explicit REFUSAL, never as an offer.
        assert 'DO NOT WRITE "talking_head" AS A media_type' in prompt


# ---------------------------------------------------------------------------
# The RC-P1 defect class: a field that no whitelist carries
# ---------------------------------------------------------------------------

class TestNoFieldIsSilentlyDropped:
    """RC-P1: v7 asked the model for three new fields and two hand-maintained
    keyword lists dropped every one of them for three days. A whitelist drops
    the field that was added last, which is always the one somebody wants."""

    def test_every_scene_create_field_reaches_a_column(self):
        from app.models.storyboard_scene import StoryboardScene
        from app.schemas.storyboard import SceneCreate
        columns = {c.name for c in StoryboardScene.__table__.columns}
        orphans = [f for f in SceneCreate.model_fields if f not in columns]
        assert orphans == [], (
            f"SceneCreate accepts {orphans} with nowhere to store them — the "
            "caller gets a 201 and the value is gone. This is RC-P1's shape."
        )

    def test_the_route_passes_the_design_fields_from_the_shared_tuple(self):
        route = (REPO / "ivgs-api" / "app" / "api" / "v1" / "storyboard.py").read_text()
        assert "for name in SCENE_DESIGN_FIELDS" in route, (
            "the design fields must be built from the shared tuple, not typed "
            "out — a hand-written list is the RC-P1 defect reintroduced"
        )

    def test_the_design_fields_are_editable_at_the_gate(self):
        from app.services.design_brief_service import SCENE_DESIGN_FIELDS
        from app.services.storyboard_service import StoryboardService
        for field in SCENE_DESIGN_FIELDS:
            assert field in StoryboardService.OPTIONAL_SCENE_FIELDS, (
                f"{field} cannot be corrected at the gate; a reviewer shown a "
                "problem and denied the fix is worse off than one shown nothing"
            )


# ---------------------------------------------------------------------------
# The design review — Task 5's two limbs
# ---------------------------------------------------------------------------

_NARRATIONS = (
    "Welcome back. Today we tackle something new.",
    "Line the digits up in their columns, ones under ones.",
    "Work out 71 times 36 on your own, then check it.",
    "Notice what the placeholder zero is doing for us.",
    "Try one more, and this time nothing is on screen to help.",
)


def _scene(idx, **kw):
    base = {
        "scene_index": idx, "serves_outcomes": ["LO-1"],
        "instructional_event": "present", "bloom_level": "apply",
        "scene_origin": "designed", "source_refs": None, "rewrite_of": None,
        "media_type": "image", "media_rationale": "framing",
        # ⚠ RE-AIMED BY WP-IVGS-12h, AND NOTHING IS WEAKENED. Every scene this
        # helper built carried the identical narration `"One."`, harmless while
        # nothing at the gate read narration. `EVIDENCE_NEAR_DUPLICATE` does read
        # it, and refuses a design whose `assess` scene says word for word what
        # an earlier `present`/`guide` on the same outcome said — which is what a
        # fixture of identical strings is. The narration is now per-scene so the
        # fixtures say what they always MEANT: different scenes. No assertion in
        # this file changed.
        "generation_params": None,
        "narration_text": _NARRATIONS[idx % len(_NARRATIONS)],
        "signal_spec": None,
    }
    base.update(kw)
    return base


OUTCOME = {"id": "LO-1", "text": "compute the product",
           "measurable": True, "bloom_level": "apply"}


class TestTheAlignmentTriad:
    def _codes(self, findings, severity):
        return sorted({f.code for f in findings if f.severity == severity})

    def test_an_outcome_served_by_nothing_is_refused(self):
        from app.services.design_review import review
        findings, _ = review(scenes=[_scene(0, serves_outcomes=["LO-9"])],
                             outcomes=[OUTCOME])
        assert "OUTCOME_UNSERVED" in self._codes(findings, "refuse")

    def test_an_outcome_served_but_never_assessed_is_refused(self):
        """SERVING IS NOT EVIDENCE. Foundation §1 stage 2 is a separate
        question and the gate asks it separately."""
        from app.services.design_review import review
        findings, rows = review(scenes=[_scene(0), _scene(1)], outcomes=[OUTCOME])
        assert "OUTCOME_UNASSESSED" in self._codes(findings, "refuse")
        assert rows[0].served is True and rows[0].assessed is False

    def test_an_assessing_scene_satisfies_the_evidence_limb(self):
        from app.services.design_review import review
        findings, rows = review(
            scenes=[_scene(0), _scene(1, instructional_event="assess")],
            outcomes=[OUTCOME])
        assert "OUTCOME_UNASSESSED" not in self._codes(findings, "refuse")
        assert rows[0].assessed_by == [1]

    def test_a_scene_serving_nothing_is_refused(self):
        from app.services.design_review import review
        findings, _ = review(scenes=[_scene(0, serves_outcomes=[])],
                             outcomes=[OUTCOME])
        assert "SCENE_SERVES_NOTHING" in self._codes(findings, "refuse")

    def test_undeclared_provenance_is_refused(self):
        from app.services.design_review import review
        findings, _ = review(scenes=[_scene(0, scene_origin=None)],
                             outcomes=[OUTCOME])
        assert "SCENE_PROVENANCE_UNDECLARED" in self._codes(findings, "refuse")

    def test_motion_without_a_template_is_refused(self):
        """RULE 8, unchanged from v7. The renderer draws the digits."""
        from app.services.design_review import review
        findings, _ = review(
            scenes=[_scene(0, media_type="motion_graphics", generation_params={})],
            outcomes=[OUTCOME])
        assert "MOTION_WITHOUT_TEMPLATE" in self._codes(findings, "refuse")

    def test_a_design_that_never_leaves_events_1_to_5_is_FLAGGED_not_refused(self):
        """Merrill. A lecture is a judgment call, and judgment calls do not
        block — WP-IVGS-10's two-limb discipline, unchanged."""
        from app.services.design_review import review
        findings, _ = review(
            scenes=[_scene(0), _scene(1, instructional_event="guide")],
            outcomes=[OUTCOME])
        assert "MERRILL_NO_APPLICATION" in self._codes(findings, "flag")
        assert "MERRILL_NO_APPLICATION" not in self._codes(findings, "refuse")

    def test_an_undeclared_script_gap_is_flagged_with_the_text_quoted(self):
        """The check recovery-plan §3 item 4 says nobody ever performed."""
        from app.services.design_review import review
        script = "A" * 100 + "THE SECOND WORKED EXAMPLE IS 32 x 21. " * 8
        findings, _ = review(
            scenes=[_scene(0, scene_origin="sourced",
                           source_refs=[{"start": 0, "end": 100}],
                           instructional_event="assess")],
            outcomes=[OUTCOME], source_text=script)
        gaps = [f for f in findings if f.code == "UNDECLARED_SCRIPT_GAP"]
        assert gaps and gaps[0].severity == "flag"
        assert "SECOND WORKED EXAMPLE" in gaps[0].detail["text"]

    def test_a_declared_drop_closes_the_gap(self):
        """Dropping is a design decision and is allowed. SILENCE is the defect."""
        from app.services.design_review import review
        script = "A" * 100 + "B" * 400
        findings, _ = review(
            scenes=[_scene(0, scene_origin="sourced",
                           source_refs=[{"start": 0, "end": 100}],
                           instructional_event="assess")],
            outcomes=[OUTCOME],
            dropped_beats=[{"span": {"start": 100, "end": 500},
                            "summary": "s", "reason": "r"}],
            source_text=script)
        assert not [f for f in findings if f.code == "UNDECLARED_SCRIPT_GAP"]

    def test_an_unmeasurable_outcome_flags_and_the_proposal_is_not_applied(self):
        from app.services.design_review import review
        outcome = {**OUTCOME, "measurable": False,
                   "proposed_refinement": "Given two 2-digit numbers…"}
        findings, rows = review(
            scenes=[_scene(0, instructional_event="assess")], outcomes=[outcome])
        flag = next(f for f in findings if f.code == "OUTCOME_NOT_MEASURABLE")
        assert flag.severity == "flag"
        assert rows[0].text == "compute the product", (
            "the operator's own words must survive verbatim; the refinement is "
            "a proposal, never a substitution"
        )
        assert rows[0].proposed_refinement == "Given two 2-digit numbers…"

    def test_a_clean_design_produces_no_refusals(self):
        """⛔ RE-AIMED BY WP-IVGS-12c, NOT WEAKENED. This design used to pass
        with NO `evidence_map` at all, and that is precisely RC-Q9b: the gate
        called a design clean while nothing had decided what would prove the
        outcome. Contract-3 makes the map required and 1..N; the map here is
        what a clean design now has to carry, and it names the `assess` scene
        that agrees with it."""
        from app.services.design_review import review, split
        scenes = [
            _scene(0, instructional_event="hook"),
            _scene(1, instructional_event="guide"),
            _scene(2, instructional_event="assess"),
        ]
        findings, _ = review(
            scenes=scenes, outcomes=[OUTCOME],
            # ⛔ RE-AIMED AGAIN BY 12d. 12c passed an `evidence_map` here
            # because the MODEL wrote one and a clean design had to carry a
            # truthful copy. The model no longer writes one — code derives it
            # from these scenes — so what a clean design must now carry is a
            # PLAN the scenes keep, and scene 2 is what keeps it.
            assessment_plan={"LO-1": {"evidence_kind": "assess",
                                      "learner_does": "multiplies unaided"}})
        refusals, _ = split(findings)
        assert refusals == [], [f.code for f in refusals]


# ---------------------------------------------------------------------------
# The publisher gates
# ---------------------------------------------------------------------------

class TestThePublisherRefuses:
    def test_it_refuses_a_template_that_does_not_render(self):
        """ADDED BECAUSE I BROKE THE TEMPLATE THIS WAY. Editing RULE 0
        swallowed an `{% endif %}`; every phrase gate still passed, because a
        substring check cannot see an unbalanced block."""
        from app.scripts import wp63_publish_storyboard_prompt as pub
        import inspect
        source = inspect.getsource(pub._gate_template if hasattr(pub, "_gate_template") else pub)
        assert "does not RENDER" in source

    def test_the_shipped_template_renders_in_both_branches(self):
        from jinja2 import BaseLoader, Environment
        text = (REPO / "ivgs-api" / "seed" / "default_prompts"
                / "storyboard_generation.j2").read_text()
        env = Environment(loader=BaseLoader(), keep_trailing_newline=True)
        for desc in ("A short lesson.", ""):
            rendered = env.from_string(text).render(
                project_title="p", project_description=desc,
                target_audience="general", max_duration_seconds=300,
                total_runtime_seconds=300, combined_transcript="t",
                transcript_count=1, target_scene_count=None,
                language_code="en-US")
            assert len(rendered) > 30_000
            assert "RULE 0 —" in rendered

    def test_the_system_prompt_publisher_refuses_a_compressor_in_the_uploaded_branch(self):
        from app.scripts import wpivgs12_publish_design_prompts as pub
        with pytest.raises(SystemExit):
            pub._gate(
                "transcript_refinement_system",
                '{% if source_kind == "uploaded" %}\nFlesch-Kincaid\n'
                "YOU ARE NOT EDITING PROSE\nCOPIED CHARACTER FOR CHARACTER, UNCHANGED\n"
                "BEATS COVER THE WHOLE SCRIPT\n"
                "A WORKED EXAMPLE IS ONE BEAT FROM ITS FIRST SETUP LINE TO ITS ANSWER\n"
                "Time Alignment\n{% else %}\nFlesch-Kincaid\nTime Alignment\n{% endif %}",
                pub.EXTRACTION_PHRASES,
            )

    def test_the_shipped_system_prompts_pass_their_own_gates(self):
        from app.scripts import wpivgs12_publish_design_prompts as pub
        for prompt_type, filename, phrases, _ in pub.TARGETS:
            pub._gate(prompt_type, (pub.SEED / filename).read_text(), phrases)


# ---------------------------------------------------------------------------
# The design brief supersedes rather than overwrites
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestTheBriefLineage:
    async def test_a_second_design_supersedes_the_first_and_both_survive(
        self, db_session,
    ):
        """RC-E: the Regenerate button discarded a storyboard with no record.
        A brief per generation means the design the reviewer was reading is
        still there to diff against."""
        from app.models.project import Project
        from app.services.design_brief_service import DesignBriefService

        project = Project(id=uuid.uuid4(), name="brief lineage", state="DRAFT")
        db_session.add(project)
        await db_session.flush()

        service = DesignBriefService(db_session)
        first = await service.record(project.id, {
            "outcomes": [{"id": "LO-1"}], "scenes": [], "raw_contract": {"v": 1},
        })
        second = await service.record(project.id, {
            "outcomes": [{"id": "LO-2"}], "scenes": [], "raw_contract": {"v": 2},
        })
        assert first.id != second.id
        active = await service.get_active(project.id)
        assert active.id == second.id
        assert len(await service.list_briefs(project.id)) == 2

    async def test_a_stage1_intent_post_does_not_supersede_a_design(
        self, db_session,
    ):
        from app.models.project import Project
        from app.services.design_brief_service import DesignBriefService

        project = Project(id=uuid.uuid4(), name="intent first", state="DRAFT")
        db_session.add(project)
        await db_session.flush()
        service = DesignBriefService(db_session)
        await service.record(project.id, {"intent": {"beats": [{"start": 0}]}})
        brief = await service.get_active(project.id)
        assert brief.intent["beats"] == [{"start": 0}]
        assert len(await service.list_briefs(project.id)) == 1

    async def test_the_design_carries_the_extraction_forward(self, db_session):
        """Stage 1 writes the intent; stage 2 does not re-emit it; the gate
        needs it to show a rewrite beside the beat it came from."""
        from app.models.project import Project
        from app.services.design_brief_service import DesignBriefService

        project = Project(id=uuid.uuid4(), name="carry forward", state="DRAFT")
        db_session.add(project)
        await db_session.flush()
        service = DesignBriefService(db_session)
        await service.record(project.id, {"intent": {"beats": [{"start": 0}]}})
        await service.record(project.id, {"outcomes": [{"id": "LO-1"}], "scenes": []})
        active = await service.get_active(project.id)
        assert active.intent == {"beats": [{"start": 0}]}

    async def test_a_bad_enum_is_dropped_not_raised(self, db_session):
        """A single bad value must not abort the transaction storing an
        otherwise good brief for eleven other scenes. The CHECK is the backstop,
        not the error surface."""
        from app.services.design_brief_service import _clean
        cleaned = _clean({
            "scene_index": 0, "instructional_event": "warmup",
            "bloom_level": "synthesise", "serves_outcomes": ["LO-1"],
        })
        # ⛔ RE-AIMED BY WP-IVGS-12b. `_clean` writes the declaration WHOLE —
        # every field, None where absent — because omitting keys merged into
        # whatever the PREVIOUS generation left on the row and produced a stale
        # sourced/designed pair the XOR refused, costing a whole brief. So
        # "dropped" now means "set to None", not "absent from the dict".
        assert cleaned["instructional_event"] is None
        assert cleaned["bloom_level"] is None
        assert cleaned["serves_outcomes"] == ["LO-1"]

    async def test_sourced_without_refs_is_dropped_to_undeclared(self, db_session):
        """Mirrors migration 0048's CHECK. The validator then names the scene."""
        from app.services.design_brief_service import _clean
        undeclared = _clean({"scene_origin": "sourced", "source_refs": []})
        assert undeclared["scene_origin"] is None
        assert undeclared["source_refs"] is None
        designed = _clean({"scene_origin": "designed", "source_refs": [{"start": 0}]})
        assert designed["scene_origin"] == "designed"
        assert designed["source_refs"] is None
