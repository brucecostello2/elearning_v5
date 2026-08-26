"""
WP-44-QUALITY Task 4 — the storyboard templates carry the rules this week paid for.

Four rules, each bought with a specific defect from the reference project
(``c12fa967-f989-4ed4-8e20-3ea62cb92e8f``, 18 scenes, first e2e run):

(a) ``visual_description`` must never request on-screen text, numbers or
    equations. Scene 0 asked for "a whiteboard with a multiplication problem
    written on it, such as 23 x 14"; FLUX produced a whiteboard reading
    ``2? x 23.14``. Scene 2 asked for calculations "appearing on screen"; the
    image reads ``12 + 44 = 67 + 5`` and ``3 + 4 = 7 = 8``.

(b) ``media_type: animation`` only for scenes containing a character. The old
    templates said the opposite in as many words — *'Use "animation" for data
    visualizations, flowcharts, and step-by-step processes'* — and eleven of
    the eighteen scenes were typed ``animation`` on that instruction, every one
    of them an equation card with no subject in it.

(c) Narration self-consistency. The reference narration reads "we should add 92
    and 230 ... but that was also incorrect" and "this gives us 260, but we
    wrote it as 640 in the previous step, which is incorrect".

(d) Durations must sum to the runtime. Eighteen scenes summing to 190 s against
    a 300 s target.

These tests pin the TEXT, because the text is the deliverable. A prompt rule
that is not in the prompt does not exist, and this is the class of regression
WP-43 caught once already ("the storyboard prompt template still taught the
rejected vocabulary").
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

#: This module reads templates from BOTH components - `ivgs-workers/prompts/`
#: and `ivgs-api/seed/default_prompts/` - because the same four rules have to
#: be in all of them, and a rule present in one and absent from another is the
#: exact WP-43 defect. That makes it a repo-level test: inside the workers
#: image there is no `ivgs-api/` tree, so it skips there with the reason stated
#: rather than erroring 33 times or, worse, appearing to have run.
pytestmark = pytest.mark.skipif(
    not (REPO / "ivgs-api" / "seed" / "default_prompts").is_dir(),
    reason=(
        "repo-level test: needs ivgs-workers/prompts and "
        "ivgs-api/seed/default_prompts side by side. Run it from the repo "
        "root, not from inside the workers image."
    ),
)

WORKER_SYSTEM = REPO / "ivgs-workers" / "prompts" / "stage2_system.j2"
WORKER_USER = REPO / "ivgs-workers" / "prompts" / "stage2_user.j2"
SEED_STORYBOARD = (
    REPO / "ivgs-api" / "seed" / "default_prompts" / "storyboard_generation.j2"
)
SEED_ANIMATION = (
    REPO / "ivgs-api" / "seed" / "default_prompts" / "animation_generation.j2"
)

#: Every template that instructs a model about storyboard scene fields. All
#: three reach a model: the two worker files are rendered by
#: `stage2_storyboard`, and the seed file is the source of the DB row Stage 2
#: fetches. A rule present in one and absent from another is the WP-43 defect.
STORYBOARD_TEMPLATES = {
    "stage2_system.j2": WORKER_SYSTEM,
    "stage2_user.j2": WORKER_USER,
    "seed/storyboard_generation.j2": SEED_STORYBOARD,
}


#: The two templates that stand alone as a complete instruction to a model.
#: `stage2_user.j2` is the per-run half of a pair — it states the rules but
#: leans on `stage2_system.j2` for the full reasoning, so the rationale and
#: evidence assertions below apply to these two.
FULL_PROMPTS = {
    "stage2_system.j2": WORKER_SYSTEM,
    "seed/storyboard_generation.j2": SEED_STORYBOARD,
}


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _flat(path_or_text) -> str:
    """Template text with newlines collapsed, lowercased.

    The rules are prose and are hard-wrapped, so a phrase that must be present
    is routinely split across two lines. Matching the wrapped form would pin
    the line breaks rather than the rule.
    """
    body = path_or_text if isinstance(path_or_text, str) else _text(path_or_text)
    return " ".join(body.split()).lower()


@pytest.fixture(scope="module")
def templates() -> dict[str, str]:
    return {name: _text(p) for name, p in STORYBOARD_TEMPLATES.items()}


# ---------------------------------------------------------------------------
# (a) no on-screen text
# ---------------------------------------------------------------------------

class TestRuleA_NoTextInTheVisual:

    @pytest.mark.parametrize("name", sorted(STORYBOARD_TEMPLATES))
    def test_every_storyboard_template_forbids_on_screen_text(self, templates, name):
        body = templates[name].lower()
        assert "visual_description" in body
        # The prohibition must name the categories, not gesture at them.
        for term in ("text", "number", "equation"):
            assert term in body, f"{name} does not mention {term!r}"
        assert re.search(r"never\s+request|must\s+never|no\s+on-screen\s+text|no text",
                         body), (
            f"{name} does not state the prohibition"
        )

    @pytest.mark.parametrize("name", sorted(STORYBOARD_TEMPLATES))
    def test_every_storyboard_template_routes_equations_to_the_overlay(
        self, templates, name
    ):
        body = templates[name].lower()
        assert "overlay" in body, (
            f"{name} forbids text without saying where text actually goes; "
            f"the rule is 'equations belong to composition overlays'"
        )

    @pytest.mark.parametrize("name", sorted(FULL_PROMPTS))
    def test_the_full_prompts_carry_the_evidence_that_bought_the_rule(self, name):
        """A rule with its reason attached survives editing. One without does not."""
        body = _flat(FULL_PROMPTS[name])
        assert "23 x 14" in body
        assert "2? x 23.14" in body

    @pytest.mark.parametrize("name", sorted(STORYBOARD_TEMPLATES))
    def test_no_template_still_asks_for_text_in_the_image(self, templates, name):
        """The pre-WP-44 phrasing must not survive anywhere.

        `stage2_system.j2` used to carry only a parenthetical
        "DO NOT include text-in-image (titles, labels)" while the seed file
        carried nothing at all.
        """
        body = templates[name]
        forbidden_instructions = [
            "Use \"animation\" for data visualizations",
            "animation\" for data/diagrams",
        ]
        for phrase in forbidden_instructions:
            assert phrase not in body, f"{name} still contains {phrase!r}"


# ---------------------------------------------------------------------------
# (b) animation only for characters
# ---------------------------------------------------------------------------

class TestRuleB_AnimationOnlyForCharacters:

    @pytest.mark.parametrize("name", sorted(STORYBOARD_TEMPLATES))
    def test_animation_requires_a_person_or_character(self, templates, name):
        body = templates[name].lower()
        assert "animation" in body
        assert ("character" in body or "person" in body), (
            f"{name} does not tie media_type 'animation' to a character"
        )
        assert "only" in body, f"{name} does not state the constraint as exclusive"

    @pytest.mark.parametrize("name", sorted(STORYBOARD_TEMPLATES))
    def test_diagram_motion_does_not_map_to_animation(self, templates, name):
        """RENAMED AND STRENGTHENED BY WP-68, and not relaxed.

        It was `test_diagram_motion_maps_to_image`, and it asserted two things:
        that the template contains the phrase "motion-graphics" or "motion
        graphics", and that the string `"image"` appears somewhere in it.

        BOTH PREMISES WENT STALE FOR A GOOD REASON. v4 said "There is no
        motion-graphics pathway in this pipeline yet" and routed those scenes
        to `"image"`; WP-68 BUILT the pathway, so v6 says `motion_graphics`
        (the media type, underscored) and routes them there instead. The old
        assertions would have forced a prompt that describes a capability the
        system now has as one it does not.

        This version asserts the PROPERTY the original was reaching for -- that
        the template tells the model where non-person motion goes, and that it
        is not "animation" -- in a form that survives either answer. It is
        strictly stronger: the old second assertion was satisfied by the word
        `"image"` appearing anywhere for any reason, and this one requires the
        routing sentence itself.
        """
        body = _flat(templates[name])

        # It must name the alternative, in whichever spelling the template uses.
        names_the_alternative = (
            "motion-graphics" in body
            or "motion graphics" in body
            or "motion_graphics" in body
        )
        assert names_the_alternative, (
            f"{name} does not name where non-person motion goes instead of "
            f"'animation'"
        )

        # And it must name a DESTINATION for those scenes. The original
        # required `"image"`; the seed template now routes them to
        # `motion_graphics` instead, so either is a destination and the
        # assertion is that one is named -- not which.
        #
        # A first attempt at this replacement demanded the phrase "is not
        # 'animation'", which `stage2_user.j2` has never contained: it states
        # the same rule by INCLUSION ("`\"image\"` for everything else,
        # **including** any scene whose motion is equations...") rather than by
        # negation. Requiring the negation would have been imposing a wording
        # the template never had, which is a different thing from following a
        # change.
        assert re.search(
            r'"image"|`image`|"motion_graphics"|`motion_graphics`',
            templates[name],
        ), f"{name} does not say where diagram-motion scenes go instead"

    @pytest.mark.parametrize("name", sorted(STORYBOARD_TEMPLATES))
    def test_the_template_states_why_so_the_model_can_generalise(
        self, templates, name
    ):
        """The work order asks for the reason to be in the template, not just the rule."""
        body = _flat(templates[name])
        assert "pose reenactment" in body or "pose-reenactment" in body or (
            "wan2.2-animate" in body
        ), f"{name} does not name the mechanism that makes the rule necessary"

    def test_the_old_instruction_is_gone_from_the_seed(self):
        """The seed file used to teach exactly the wrong thing."""
        body = _text(SEED_STORYBOARD)
        assert 'Use "animation" for data visualizations, flowcharts' not in body
        assert "steps appearing on screen" in body.lower() or (
            "appearing on screen" in body.lower()
        )

    def test_the_animation_seed_no_longer_describes_a_diagram_renderer(self):
        """`animation_generation.j2` taught 'animated diagram ... Remotion'.

        The old phrases may still APPEAR — the corrected template names them to
        explain what changed — but not as instructions. The opening line and
        the requirements list are what the model acts on.
        """
        body = _text(SEED_ANIMATION)
        flat = _flat(body)
        assert not body.startswith("Generate an animated diagram or visualization")
        assert "there is no remotion component in this pipeline" in flat
        assert "pose reenactment" in flat
        assert "character or person" in flat


# ---------------------------------------------------------------------------
# (c) narration self-consistency
# ---------------------------------------------------------------------------

class TestRuleC_NarrationSelfConsistency:

    @pytest.mark.parametrize("name", sorted(STORYBOARD_TEMPLATES))
    def test_arithmetic_must_be_verified(self, templates, name):
        body = templates[name].lower()
        assert "arithmetic" in body, (
            f"{name} does not instruct verification of arithmetic"
        )
        assert "verify" in body

    @pytest.mark.parametrize("name", sorted(STORYBOARD_TEMPLATES))
    def test_self_referential_corrections_are_forbidden(self, templates, name):
        body = _flat(templates[name])
        assert "never narrate your own errors" in body, (
            f"{name} does not forbid narrating its own errors"
        )
        assert "contradict" in body, (
            f"{name} does not forbid contradicting an earlier scene"
        )

    @pytest.mark.parametrize("name", sorted(STORYBOARD_TEMPLATES))
    def test_the_actual_offending_narration_is_quoted(self, templates, name):
        """The rule carries the sentence that caused it.

        All three carry the quote: a rule whose evidence travels with it does
        not get edited back out by someone who does not know why it is there.
        """
        assert "but that was also incorrect" in _flat(templates[name]), (
            f"{name} does not quote the reference storyboard's own self-correction"
        )


# ---------------------------------------------------------------------------
# (d) durations sum to runtime
# ---------------------------------------------------------------------------

class TestRuleD_DurationsSumToRuntime:

    @pytest.mark.parametrize("name", sorted(STORYBOARD_TEMPLATES))
    def test_durations_must_sum_to_the_runtime(self, templates, name):
        body = templates[name].lower()
        assert "sum" in body
        assert "runtime" in body or "max_duration_seconds" in body, (
            f"{name} does not tie the sum to the project runtime"
        )

    @pytest.mark.parametrize("name", sorted(STORYBOARD_TEMPLATES))
    def test_the_tolerance_is_stated_as_a_number(self, templates, name):
        """"Approximately" is what produced 190 s against a 300 s target."""
        assert "10%" in templates[name], (
            f"{name} states no numeric tolerance for the duration sum"
        )

    def test_the_user_template_binds_the_projects_actual_runtime(self):
        body = _text(WORKER_USER)
        assert "{{ max_duration_seconds }}" in body


# ---------------------------------------------------------------------------
# The templates still render
# ---------------------------------------------------------------------------

class TestTheTemplatesStillRender:

    def test_worker_templates_render_through_stage2s_own_binder(self):
        """Rules are worthless if the template stops binding the transcript."""
        from models.task_result import RefinedTranscript
        from tasks.stage2_storyboard import _render_user_prompt

        rendered = _render_user_prompt(
            template_str=_text(WORKER_USER),
            refined_transcripts=[
                RefinedTranscript(
                    transcript_id="t-1",
                    sequence_order=1,
                    original_text="raw",
                    refined_text="WP44-TRANSCRIPT-SENTINEL",
                )
            ],
            context={
                "project_name": "WP44-TITLE-SENTINEL",
                "project_description": "d",
                "target_audience": "general",
                "max_runtime_seconds": 4242,
                "target_scene_count": 9,
                "language_code": "en-US",
            },
        )
        assert "WP44-TRANSCRIPT-SENTINEL" in rendered
        assert "WP44-TITLE-SENTINEL" in rendered
        assert "4242" in rendered
        assert "10%" in rendered

    def test_seed_template_renders_through_stage2s_own_binder(self):
        from models.task_result import RefinedTranscript
        from tasks.stage2_storyboard import _render_user_prompt

        rendered = _render_user_prompt(
            template_str=_text(SEED_STORYBOARD),
            refined_transcripts=[
                RefinedTranscript(
                    transcript_id="t-1",
                    sequence_order=1,
                    original_text="raw",
                    refined_text="WP44-TRANSCRIPT-SENTINEL",
                )
            ],
            context={
                "project_name": "WP44-TITLE-SENTINEL",
                "project_description": "d",
                "target_audience": "general",
                "max_runtime_seconds": 4242,
                "target_scene_count": 9,
                "language_code": "en-US",
            },
        )
        assert "WP44-TRANSCRIPT-SENTINEL" in rendered
        assert "WP44-TITLE-SENTINEL" in rendered
        assert "4242" in rendered

    def test_system_prompt_is_valid_jinja_and_has_no_stray_variables(self):
        from jinja2 import Environment, meta

        src = _text(WORKER_SYSTEM)
        undeclared = meta.find_undeclared_variables(Environment().parse(src))
        assert undeclared == set(), (
            f"stage2_system.j2 is a static system prompt; it must bind nothing, "
            f"but references {sorted(undeclared)}"
        )


# ---------------------------------------------------------------------------
# The held corrective SQL matches the seed files it claims to install
# ---------------------------------------------------------------------------

class TestTheHeldCorrectiveSqlMatchesTheSeedFiles:
    """The live DB row is what Stage 2 actually receives.

    Correcting the seed FILE does not change it (`seed_prompts.py` skips a type
    that already has an active global prompt), so WP-44 ships a held corrective
    SQL. If the SQL and the seed file ever diverge, the file in git stops being
    evidence of what the pipeline runs.
    """

    SQL = REPO / "dev" / "workpackages" / "WP-44-storyboard-prompt-v3.sql"

    def test_the_sql_exists_and_is_held_not_executed(self):
        body = _text(self.SQL)
        assert "HELD FOR THE OPERATOR" in body
        assert "NOT EXECUTED" in body

    def test_the_sql_is_self_consistent_about_what_it_installs(self):
        """UPDATED BY WP-63 Task 9, AND IT IS NOT A RELAXATION.

        This asserted that the seed FILE appears verbatim inside the SQL. That
        was right while the SQL was pending: the file and the row it was about
        to install had to be the same bytes or the file in git stopped being
        evidence of what the pipeline runs.

        THE SQL HAS SINCE BEEN APPLIED. `prompts` holds
        `storyboard_generation` v3, active, `created_by = 'wp-44-quality'`,
        md5 `8b120d1ff6f84f8286bf16d6022041a0` -- exactly the md5 this SQL's
        own verification section predicts. It is a historical, spent artefact,
        and rewriting it to match a LATER version of the file would make it
        lie about what it installed.

        So the property becomes self-consistency: the text this SQL embeds must
        hash to the md5 this SQL declares. That is strictly stronger than the
        old containment check, which could not have caught the SQL's embedded
        text and its own stated md5 drifting apart.

        WP-63 publishes v4 of the same template through
        `app/scripts/wp63_publish_storyboard_prompt.py`, and
        `ivgs-api/tests/test_wp63_storyboard_prompt.py` is what keeps THAT
        publisher and the current file in step. The next test below keeps the
        file an extension of what this SQL installed rather than a replacement
        of it.
        """
        import hashlib
        import re

        body = _text(self.SQL)

        # Both templates are dollar-quoted with the same tag; SECTION A
        # (storyboard) comes first, SECTION B (animation) second. The md5s are
        # the ones the SQL's own verification section predicts.
        blocks = re.findall(r"\$IVGSWP44\$(.*?)\$IVGSWP44\$", body, re.S)
        assert len(blocks) == 2, (
            f"expected two $IVGSWP44$ blocks (storyboard, animation), found "
            f"{len(blocks)}"
        )
        for block, expected_md5 in zip(
            blocks,
            ("8b120d1ff6f84f8286bf16d6022041a0",
             "d8f8b018c51931cc7caa0b1df140b9f8"),
        ):
            actual = hashlib.md5(block.encode("utf-8")).hexdigest()
            assert actual == expected_md5, (
                f"an embedded template hashes to {actual}, but this SQL's "
                f"verification section says it installs {expected_md5}. The "
                "SQL and its own stated outcome have diverged."
            )
            assert expected_md5 in body, (
                "the SQL no longer declares the md5 it installs"
            )

        assert _text(SEED_ANIMATION) in body, (
            "the corrective SQL no longer matches "
            "ivgs-api/seed/default_prompts/animation_generation.j2"
        )

    def test_the_current_seed_file_extends_what_the_sql_installed(self):
        """v4 ADDS rules; it does not drop the ones WP-44 paid for.

        The whole reason RULE 1 exists is two measured runs that produced
        "2? x 23.14" and "12 + 44 = 67 + 5". WP-63's binding rules pull in the
        opposite direction — "make the visual show the lesson" — and the risk
        in that change is that RULE 1 gets softened to make room. It is not:
        this asserts that every sentence of RULE 1 the SQL installed is still
        in the file, character for character.
        """
        import re

        sql_text = re.findall(
            r"\$IVGSWP44\$(.*?)\$IVGSWP44\$", _text(self.SQL), re.S,
        )[0]  # SECTION A, the storyboard template
        rule1 = sql_text.split("RULE 1")[1].split("RULE 2")[0]
        current = _text(SEED_STORYBOARD)
        for line in (l.strip() for l in rule1.splitlines() if l.strip()):
            assert line in current, (
                f"RULE 1 lost a line that WP-44's corrective SQL installed: "
                f"{line!r}"
            )

    def test_the_sql_guards_on_the_measured_state(self):
        body = _text(self.SQL)
        assert "GUARD FAILED" in body
        assert "md5(prompt_text)" in body
        assert "BEGIN;" in body and "COMMIT;" in body

    def test_the_sql_deactivates_rather_than_deleting(self):
        """Review and prompt history is never deleted silently."""
        body = _text(self.SQL).upper()
        assert "DELETE FROM PROMPTS" not in body
        assert "IS_ACTIVE = FALSE" in body
