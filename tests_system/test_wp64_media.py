"""
WP-64 — the shipped surfaces: the editor's adapt action, the outcomes field,
and the conformance gate that now covers the workers' stage templates.

This module lives in `tests_system` for the reason the others here do: it drives
REAL shipped artefacts — the real page sources, the real
`scripts/check_seed_conformance.sh`, the real seed templates — rather than a
fixture that would be a second statement of what somebody believed they
contained.
"""
from __future__ import annotations

import pathlib
import re
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
FRONTEND = REPO / "ivgs-frontend" / "src"
MODAL = FRONTEND / "components" / "storyboard" / "SceneEditModal.tsx"
OUTCOMES_PANEL = FRONTEND / "components" / "project" / "LearningOutcomesPanel.tsx"
NEW_PROJECT = FRONTEND / "app" / "projects" / "new" / "page.tsx"
OVERVIEW = FRONTEND / "app" / "projects" / "[id]" / "page.tsx"
STORYBOARD_PAGE = FRONTEND / "app" / "projects" / "[id]" / "storyboard" / "page.tsx"
HOOK = FRONTEND / "hooks" / "useStoryboard.ts"
CONFORMANCE = REPO / "scripts" / "check_seed_conformance.sh"
ADAPTATION_TEMPLATE = (
    REPO / "ivgs-api" / "seed" / "default_prompts" / "scene_media_adaptation.j2"
)
STAGE3_TEMPLATE = REPO / "ivgs-workers" / "prompts" / "stage3_system.j2"


# ===========================================================================
# TASK 3 — the editor's adapt action, and what it must not do
# ===========================================================================


class TestTheAdaptActionIsExplicit:
    @pytest.fixture(scope="class")
    def modal(self) -> str:
        return MODAL.read_text(encoding="utf-8")

    def test_the_button_exists_and_names_the_medium(self, modal):
        assert "Adapt description for" in modal
        assert "handleAdapt" in modal

    def test_the_proposal_is_never_written_into_the_field_automatically(self, modal):
        """THE CENTRAL PROPERTY. `setVisualDescription` may be called from the
        change handler and from the ACCEPT handler, and from nowhere else — in
        particular not from the adapt handler itself, which would replace the
        operator's words on a button press they have not read the result of.
        """
        assert "setProposal(result)" in modal, "the adapt handler stores a proposal"
        accept = modal[modal.index("const handleAcceptProposal"):]
        accept = accept[: accept.index("}, [proposal]);")]
        assert "setVisualDescription(proposal.adapted_description)" in accept
        adapt = modal[modal.index("const handleAdapt"):]
        adapt = adapt[: adapt.index("/** Accept the proposal")]
        assert "setVisualDescription" not in adapt

    def test_the_operator_can_discard_it(self, modal):
        assert "Use this text" in modal
        assert "Discard" in modal

    def test_the_ui_says_that_nothing_is_saved(self, modal):
        assert "this button" in modal and "saves nothing" in modal
        assert "not saved" in modal

    def test_the_hook_does_not_mutate_the_scene_cache(self):
        """It writes no scene row, so there is nothing to invalidate. Wrapping
        it in `mutate` would refetch the list to show a change that has not
        happened."""
        hook = HOOK.read_text(encoding="utf-8")
        body = hook[hook.index("const adaptSceneDescription"):]
        body = body[: body.index("const approveStoryboard")]
        assert "adapt-description" in body
        assert "mutate(" not in body
        assert "optimisticData" not in body

    def test_the_page_passes_it_through(self):
        page = STORYBOARD_PAGE.read_text(encoding="utf-8")
        assert "onAdaptDescription={adaptSceneDescription}" in page

    def test_the_animation_option_no_longer_describes_motion_graphics(self, modal):
        """MEASURED CORRECTION. The dropdown described the animation branch as
        "Motion graphics via Remotion/AnimateDiff" — a pathway this pipeline
        does not have. It is Wan2.2-Animate pose reenactment: it needs a person
        in the scene's still and REFUSES a personless one by name. That line
        was the one sentence an operator read before choosing the branch, and
        Task 5's acceptance gesture is exactly that choice."""
        block = modal[modal.index('value: "animation",'):]
        block = block[: block.index("];")]
        described = block[block.index("description:"):]
        assert "Remotion" not in described
        assert "AnimateDiff" not in described
        assert "Wan2.2-Animate" in described
        assert "no person in it is refused" in described


class TestTheAdaptationPromptCarriesItsContract:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return ADAPTATION_TEMPLATE.read_text(encoding="utf-8")

    def test_rule_1_outranks_everything(self, text):
        assert "NO TEXT IN THE VISUAL" in text
        assert "outranks everything below" in text

    def test_it_keeps_the_subject(self, text):
        """Otherwise the model writes a NEW scene, and the operator cannot tell
        by reading the output that it has happened."""
        assert "KEEP THE SUBJECT" in text
        assert "changing the MEDIUM, not the scene" in text

    def test_it_gives_all_three_media_their_own_instructions(self, text):
        assert "WRITE IT FOR THE TARGET MEDIUM" in text
        for token in ("image", "video_clip", "animation"):
            assert re.search(rf"^  {token}\s+—", text, re.M), token

    def test_it_carries_the_person_constraint_on_animation(self, text):
        assert "pose reenactment" in text
        assert "REFUSES a scene" in text

    def test_it_asks_for_the_description_and_nothing_else(self, text):
        assert "NOTHING ELSE" in text
        assert "No preamble" in text

    def test_the_publisher_gates_on_the_same_phrases(self, text):
        import sys

        sys.path.insert(0, str(REPO / "ivgs-api"))
        from app.scripts.wp64_publish_adaptation_prompt import (
            CONTRACT_PHRASES,
            REQUIRED_VARIABLES,
        )

        for phrase in CONTRACT_PHRASES:
            assert phrase in text, phrase
        for var in REQUIRED_VARIABLES:
            assert "{{ " + var + " }}" in text, var

    def test_the_service_gates_on_the_same_phrases(self, text):
        import sys

        sys.path.insert(0, str(REPO / "ivgs-api"))
        from app.services.adaptation_service import CONTRACT_PHRASES

        for phrase in CONTRACT_PHRASES:
            assert phrase in text, phrase


# ===========================================================================
# TASK 6 — the learning-outcomes field, and its notice
# ===========================================================================


class TestTheLearningOutcomesSurface:
    def test_the_new_project_form_offers_it(self):
        page = NEW_PROJECT.read_text(encoding="utf-8")
        assert "Learning outcomes" in page
        assert "what the viewer should be able to do afterwards" in page
        assert "payload.learning_outcomes" in page

    def test_it_is_optional_and_the_form_says_so(self):
        page = NEW_PROJECT.read_text(encoding="utf-8")
        assert "Optional." in page
        # The copy wraps in the source; assert the halves rather than a line.
        assert "Left empty, the storyboard is planned from the" in page
        assert "transcript alone." in page

    def test_the_overview_shows_it(self):
        page = OVERVIEW.read_text(encoding="utf-8")
        assert "LearningOutcomesPanel" in page

    def test_the_panel_says_editing_is_not_retroactive(self):
        """Scenes are rows a completed run wrote. A field that looked like it
        governed the storyboard on screen, and silently did not, is the same
        class of defect as the five scene fields WP-43 found being accepted
        with a 200 and dropped."""
        panel = OUTCOMES_PANEL.read_text(encoding="utf-8")
        assert "does not change scenes that already exist" in panel
        assert "feeds" in panel and "next storyboard generation" in panel

    def test_an_empty_field_reads_as_an_answer_not_a_failure(self):
        panel = OUTCOMES_PANEL.read_text(encoding="utf-8")
        assert "None stated." in panel

    def test_clearing_it_sends_null_not_an_empty_string(self):
        panel = OUTCOMES_PANEL.read_text(encoding="utf-8")
        assert "draft.trim() ? draft.trim() : null" in panel


# ===========================================================================
# TASK 4(b) — the seed conformance gate now covers the workers' templates
# ===========================================================================


class TestTheConformanceGateReachesTheWorkersTemplates:
    """`stage3_system.j2` is versioned data exactly as a seed prompt is, and
    until this package NOTHING compared it to anything. It ships in the WORKERS
    image, not the api image, and it never reaches the `prompts` table at all —
    Stage 3 reads it off disk. A stale baked copy would have shipped as
    silently as a stale seed prompt, with one fewer place to notice.
    """

    @pytest.fixture(scope="class")
    def body(self) -> str:
        return CONFORMANCE.read_text(encoding="utf-8")

    def test_it_checks_the_workers_prompt_directory(self, body):
        assert 'WORKER_DIR_REL="ivgs-workers/prompts"' in body
        assert 'WORKER_DIR_IMG="/app/prompts"' in body

    def test_it_resolves_the_workers_image_by_inspect_not_by_tag(self, body):
        """dev/CLAUDE.md section 6: `docker exec <c> env` reports a STALE
        `IVGS_*_TAG`."""
        assert (
            "docker inspect ivgs-celery-default --format '{{.Config.Image}}'"
            in body
        )
        assert "IVGS_WORKERS_TAG" not in body

    def test_a_directory_it_cannot_check_is_named_not_silent(self, body):
        assert "SKIPPED" in body
        assert "silence is what this script exists to remove" in body

    def test_it_still_checks_both_directions(self, body):
        assert "MISSING IN IMAGE" in body
        assert "EXTRA IN IMAGE" in body

    def test_it_refuses_to_pass_when_it_compared_nothing(self, body):
        """A check that skipped everything must not print PASS."""
        assert 'if [ "$checked" -eq 0 ]' in body
        assert "Nothing was compared." in body

    @pytest.mark.skipif(
        shutil.which("docker") is None, reason="docker is not on PATH"
    )
    def test_the_workers_pass_runs_against_the_deployed_image(self):
        """It must actually READ the workers image, not skip it into silence."""
        result = subprocess.run(
            ["bash", str(CONFORMANCE)],
            capture_output=True, text=True, timeout=180,
        )
        if "--- workers stage prompts ---" not in result.stdout:
            pytest.fail("the workers section did not run at all")
        section = result.stdout.split("--- workers stage prompts ---", 1)[1]
        if "SKIPPED" in section.split("\n\n")[0]:
            pytest.skip("the workers image is not readable here")
        assert "stage3_system.j2" in section


class TestTheStage3TemplateIsHonestAboutItsLimit:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return STAGE3_TEMPLATE.read_text(encoding="utf-8")

    def test_it_asks_for_motion_to_survive(self, text):
        assert "PRESERVE MOTION, CAMERA AND TEMPORAL LANGUAGE" in text

    def test_it_does_not_claim_to_branch_on_a_field_it_never_receives(self, text):
        """Task 4(b)'s instruction, in as many words: do not pretend the
        template can branch on a field it is never passed."""
        assert "cannot branch" in text
        assert "does not pretend" in text
        assert "P2.65" in text
