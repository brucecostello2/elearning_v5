"""WP-IVGS-12b — outcomes cannot be paraphrased, artifacts cannot lie.

Every test gates a defect this package MEASURED.
"""
from __future__ import annotations

import json
import pathlib
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]


class TestTheParserIsReversible:
    """⛔ REVERSIBILITY IS THE CONTRACT. The Task 1(d) byte-compare is only
    worth having if `reconstruct(parse(x)) == x`; otherwise it compares against
    a normalisation and passes on a design whose outcomes drifted."""

    CORPUS = {
        "LO- prefixed": "LO-1: Compute the product.\nLO-2: Explain the zero.\nLO-3: Check.",
        "wrapped": "LO-1: Given two 2-digit numbers,\n  compute the product\n  with carries.\nLO-2: Explain.",
        "numbered": "1. Compute.\n2) Explain.\n3: Check.",
        "bullets": "- Compute.\n* Explain.\n• Check.",
        "no markers, one per line": "Compute the product.\nExplain the zero.\nCheck the work.",
        "single": "Understand multiplication.",
        "blank lines": "LO-1: Compute.\n\nLO-2: Explain.",
        "odd numbering": "LO-2: Compute.\nLO-5: Explain.\nLO-9: Check.",
        "trailing blank": "LO-1: Compute.\nLO-2: Explain.\n\n",
        "empty": "",
        "whitespace": "   \n  \n",
    }

    @pytest.mark.parametrize("name", sorted(CORPUS))
    def test_round_trips(self, name):
        from shared.design.outcomes import is_faithful, parse_outcomes
        raw = self.CORPUS[name]
        assert is_faithful(raw, parse_outcomes(raw))

    def test_ids_are_positional_not_the_operators_numbering(self):
        """An operator who numbers 2, 5, 9 still gets LO-1..3: the ids close a
        schema enum and must not depend on anything they typed."""
        from shared.design.outcomes import outcome_ids, parse_outcomes
        assert outcome_ids(parse_outcomes("LO-2: a\nLO-5: b\nLO-9: c")) == ["LO-1", "LO-2", "LO-3"]

    def test_unmarked_lines_do_not_collapse_into_one_outcome(self):
        """⛳ EARNED BY A TEST CASE. The continuation rule is right for a wrapped
        marked outcome and WRONG for three unmarked ones — collapsing them is
        the same silent-loss shape this module exists to remove."""
        from shared.design.outcomes import parse_outcomes
        assert len(parse_outcomes("Compute.\nExplain.\nCheck.")) == 3
        assert len(parse_outcomes("LO-1: Given two numbers,\n  compute it.")) == 1


class TestTheModelCannotWriteOutcomeText:
    def test_the_schema_carries_no_outcome_text_field(self):
        """RC-Q9's structural cure. If outcome text reappears in what the model
        emits, the paraphrase can come back and no wording will stop it."""
        import sys
        sys.path.insert(0, str(REPO / "ivgs-workers"))
        from design_core.contract import design_contract_schema
        s = design_contract_schema(outcome_ids=["LO-1", "LO-2"])
        assert "outcomes" not in s["properties"]
        assert "outcome_notes" in s["properties"]
        blob = json.dumps(s)
        assert '"text"' not in blob

    def test_serves_outcomes_and_the_plan_are_closed_to_the_real_ids(self):
        """RC-Q9's cure — the model may cite only ids CODE assigned.

        ⛔ RE-AIMED BY 12d, NOT WEAKENED. This asserted the closure on
        `evidence_map`, which the model no longer emits at all (contract-4
        derives it from the scenes). The same closure is asserted on
        `assessment_plan`, which is the field that replaced it as the model's
        per-outcome commitment — and the risk is identical: a model that can
        invent an outcome id can invent an outcome.
        """
        import sys
        sys.path.insert(0, str(REPO / "ivgs-workers"))
        from design_core.contract import design_contract_schema
        ids = ["LO-1", "LO-2", "LO-3"]
        s = design_contract_schema(outcome_ids=ids)
        scene = s["properties"]["scenes"]["items"]
        assert scene["properties"]["serves_outcomes"]["items"]["enum"] == ids
        assert "evidence_map" not in s["properties"]
        assert s["properties"]["assessment_plan"]["required"] == ids
        assert s["properties"]["assessment_plan"]["additionalProperties"] is False
        assert s["properties"]["outcome_notes"]["required"] == ids

    def test_every_array_is_bounded(self):
        """⛔ MEASURED: an array with minItems and NO max gives constrained
        decoding an infinite LEGAL continuation and the model takes it —
        ["LO-1","LO-3","LO-3",…] to the token limit, nothing parseable.
        `maxItems` compiles into the grammar; `uniqueItems` is refused HTTP 400."""
        import sys
        sys.path.insert(0, str(REPO / "ivgs-workers"))
        from design_core.contract import design_contract_schema

        def unbounded(node, path="$"):
            bad = []
            if isinstance(node, dict):
                if node.get("type") == "array" and "maxItems" not in node:
                    bad.append(path)
                for k, v in node.items():
                    bad += unbounded(v, f"{path}.{k}")
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    bad += unbounded(v, f"{path}[{i}]")
            return bad

        for ids in (["LO-1", "LO-2"], []):
            assert unbounded(design_contract_schema(outcome_ids=ids)) == []

    def test_no_ids_degrades_rather_than_producing_an_empty_enum(self):
        import sys
        sys.path.insert(0, str(REPO / "ivgs-workers"))
        from design_core.contract import design_contract_schema
        s = design_contract_schema(outcome_ids=[])
        scene = s["properties"]["scenes"]["items"]
        assert "enum" not in scene["properties"]["serves_outcomes"]["items"]
        assert "outcome_notes" not in s["properties"]


LO = "LO-1: Compute the product.\nLO-2: Explain the zero."
GOOD = [{"id": "LO-1", "text": "Compute the product."},
        {"id": "LO-2", "text": "Explain the zero."}]
SCENE = {"scene_index": 0, "serves_outcomes": ["LO-1", "LO-2"],
         "instructional_event": "assess", "bloom_level": "apply",
         "scene_origin": "sourced", "source_refs": [{"start": 0, "end": 50}],
         "media_type": "image", "media_rationale": "r", "narration_text": "One."}


class TestTheBelt:
    """⛳ WITH THE STRUCTURAL FIX THIS CANNOT FAIL. It exists so that a future
    regression which routes outcome text back through a model is LOUD."""

    def _refusals(self, outcomes):
        from app.services.design_review import review, split
        f, _ = review(scenes=[SCENE], outcomes=outcomes, learning_outcomes=LO)
        return [x.code for x in split(f)[0]]

    def test_faithful_outcomes_pass(self):
        assert "OUTCOMES_TEXT_DRIFTED" not in self._refusals(GOOD)
        assert "OUTCOMES_COUNT_DRIFTED" not in self._refusals(GOOD)

    def test_a_paraphrase_is_refused(self):
        para = [{"id": "LO-1", "text": "The learner can multiply."}, GOOD[1]]
        assert "OUTCOMES_TEXT_DRIFTED" in self._refusals(para)

    def test_a_dropped_outcome_is_refused(self):
        assert "OUTCOMES_COUNT_DRIFTED" in self._refusals(GOOD[:1])


class TestSilenceAboutDropsIsRefused:
    """Task 1(d). An empty `dropped_beats` is the model CLAIMING it used
    everything; the uncovered length is measured BY CODE. Both cannot be true.

    ⛔ **SUPERSEDED IN PART BY WP-IVGS-12i2, RC-S2(a), 2026-08-30. THE CHANGE OF
    SENSE IS DELIBERATE AND THE HISTORY IS THE POINT.**

    12b's rule was `gap >= 400 AND dropped_beats is empty`, and the second
    clause is GLOBAL where the first is PER-SPAN — so **one throwaway declared
    drop anywhere in the design made every hole in the script soft.** That is
    not a hypothetical: measured on the operator's live project, a regenerated
    design declared ONE drop, cited spans covering **110 of 3,138 characters**,
    left a single undeclared 2,968-character stretch, and drew zero refusals.

    The rule is now per-span: an uncovered stretch over the threshold refuses
    **regardless of what was declared elsewhere**. The second test below used to
    assert the downgrade and now asserts that it does NOT happen; the first is
    unchanged in sense and only in the code it names. The full argument and the
    calibration against both live designs live in
    `test_wpivgs12i2_rcs_batch.py::TestFidelitySpanRule`.
    """

    SCRIPT = "A" * 50 + "B" * 900

    def _codes(self, dropped):
        from app.services.design_review import review, split
        f, _ = review(scenes=[SCENE], outcomes=GOOD, learning_outcomes=LO,
                      source_text=self.SCRIPT, dropped_beats=dropped)
        ref, flg = split(f)
        return [x.code for x in ref], [x.code for x in flg]

    def test_empty_drops_over_a_big_hole_is_a_HARD_refusal(self):
        """Unchanged in sense. The code is renamed because the rule no longer
        turns on emptiness: `UNDECLARED_SPAN_OVER_THRESHOLD` says what is now
        actually being refused."""
        ref, _ = self._codes([])
        assert "UNDECLARED_SPAN_OVER_THRESHOLD" in ref

    def test_a_drop_declared_ELSEWHERE_no_longer_downgrades_it(self):
        """⛔ THIS TEST'S ASSERTION IS INVERTED FROM 12b's, ON PURPOSE.

        It used to read `assert "UNDECLARED_GAP_WITH_NO_DROPS" not in ref` — it
        pinned the loophole as the intended behaviour. The drop below spans
        900..950 and the hole is at 50..900, so this drop declares nothing about
        this stretch, and a design may no longer buy silence about one beat by
        declaring another.
        """
        ref, flg = self._codes(
            [{"span": {"start": 900, "end": 950}, "summary": "s", "reason": "r"}])
        assert "UNDECLARED_SPAN_OVER_THRESHOLD" in ref
        assert "UNDECLARED_SCRIPT_GAP" not in flg


class TestTheDeclarationIsWrittenWhole:
    """⛔ EARNED BY A CHECK VIOLATION. Omitting absent fields merged into
    whatever the PREVIOUS generation left on the row: gen 1 left scene 6
    `sourced` with refs, gen 2 called it `designed`, the stale refs stayed, and
    PostgreSQL refused the row — costing the whole brief."""

    def test_every_field_is_present(self):
        from app.services.design_brief_service import SCENE_DESIGN_FIELDS, _clean
        assert set(_clean({"scene_index": 1})) == set(SCENE_DESIGN_FIELDS)

    def test_designed_clears_a_stale_source_refs(self):
        from app.services.design_brief_service import _clean
        out = _clean({"scene_origin": "designed", "serves_outcomes": ["LO-1"]})
        assert out["scene_origin"] == "designed"
        assert out["source_refs"] is None

    def test_sourced_without_usable_refs_becomes_undeclared(self):
        from app.services.design_brief_service import _clean
        out = _clean({"scene_origin": "sourced", "source_refs": []})
        assert out["scene_origin"] is None and out["source_refs"] is None

    def test_the_design_jsonb_columns_write_sql_null_not_json_null(self):
        """⛔ THE SECOND DEFECT IN THE SAME CONSTRAINT. SQLAlchemy's JSONB
        default is `none_as_null=False`, so a Python None is written as the JSON
        value `null`. `source_refs IS NULL` is FALSE for that, so a legitimately
        `designed` scene could not satisfy the XOR and every ingest 500'd."""
        from app.models.storyboard_scene import StoryboardScene
        for name in ("serves_outcomes", "source_refs", "rewrite_of", "signal_spec"):
            col = StoryboardScene.__table__.columns[name]
            assert col.type.none_as_null is True, name


class TestTheArtifactIdentityIncludesTheDigest:
    """RC-Q8. node-01 ran e9c1001a while three nodes ran aa89c778 under ONE tag,
    with DEPLOY VERIFIED green on all of them."""

    LIB = REPO / "scripts" / "lib" / "artifact_name.sh"
    SAVE = REPO / "scripts" / "save-image-artifact.sh"

    def _sh(self, snippet):
        return subprocess.run(
            ["bash", "-c", f"source {self.LIB}\n{snippet}"],
            capture_output=True, text=True, timeout=30).stdout.strip()

    def test_the_name_is_still_derived_from_the_tag(self):
        """Unchanged on purpose: `artifact_path_for` resolves from a REF alone,
        which is the deploy contract — a remote node has the tag and not the
        image. A digest in the NAME would invert that."""
        assert self._sh("artifact_name_for ghcr.io/ns/repo:v1.2.3") == "ns_repo_v1.2.3"

    def test_the_digest_sidecar_sits_beside_the_artifact(self):
        out = self._sh(
            "IVGS_IMAGE_ARTIFACTS=/tmp/x artifact_digest_path_for ghcr.io/ns/repo:v1.2.3")
        assert out == "/tmp/x/ns_repo_v1.2.3.digest"

    def test_an_unrecorded_digest_reads_empty_not_matching(self):
        assert self._sh(
            "IVGS_IMAGE_ARTIFACTS=/tmp/nope artifact_banked_digest ghcr.io/ns/repo:v1") == ""

    def test_the_save_script_refuses_a_digest_mismatch(self):
        text = self.SAVE.read_text()
        assert "names DIFFERENT BYTES than the banked artifact" in text
        assert "DIGEST MATCHES" in text
        assert 'BANKED_DIGEST" != "$LOCAL_DIGEST' in text

    def test_the_checker_reports_artifacts_with_no_recorded_digest(self):
        assert "NO DIGEST RECORDED" in (
            REPO / "scripts" / "check-image-artifacts.sh").read_text()


class TestThePromptTypeEnumIsOneList:
    """⛔ WP-68's defect, repeating. Migration 0047 added two members to the
    PostgreSQL type and not to the hand-typed ORM tuple; the rows published
    fine and the next SELECT that touched one raised LookupError."""

    def test_the_orm_column_uses_the_shared_list(self):
        from app.models.prompt import Prompt
        from shared.models.enums import PROMPT_TYPES
        assert tuple(Prompt.__table__.columns["prompt_type"].type.enums) == PROMPT_TYPES

    def test_the_system_prompt_types_are_known_to_the_orm(self):
        from shared.models.enums import PROMPT_TYPES
        assert "storyboard_generation_system" in PROMPT_TYPES
        assert "transcript_refinement_system" in PROMPT_TYPES
