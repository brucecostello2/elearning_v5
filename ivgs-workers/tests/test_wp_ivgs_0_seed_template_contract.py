"""
WP-IVGS-0 finding F6 — the seeded prompt templates must bind to the workers.

IVGS-0.4 fixed WHICH prompt Stage 1 receives. It did not fix what that prompt
renders to. The seeded templates used ``{{ narration_text }}``; the workers bind
``transcript_text`` (Stage 1) and ``combined_transcript`` (Stage 2). Jinja
rendered the unbound name as empty, so with DB prompts seeded the transcript
still vanished — the same symptom the translation template produced, from a
different cause.

Operator ruling 2026-08-22: the WORKERS' names are the proven contract; the seed
templates were renamed to match. This module is the guard that keeps them
matched.

It does not read the template and reason about it. It calls the worker's REAL
render function on the REAL seed file with a unique sentinel behind every
binding, and asserts every sentinel the template asks for actually appears in
the rendered text. A variable the worker does not bind renders empty, its
sentinel is absent, and the test fails naming it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from jinja2 import Environment, meta

from models.task_result import RefinedTranscript, TranscriptRecord

SEED_DIR = (
    Path(__file__).resolve().parents[2]
    / "ivgs-api" / "seed" / "default_prompts"
)

# Every seed template, and the pipeline stage that fetches it from the API.
# None = no worker consumes it today. Stages 3 and 5 load their own templates
# from ivgs-workers/prompts/ and never call the prompts endpoint, so eight of
# the ten seeded types are currently write-only. That is recorded, not hidden:
# wiring one up without adding its bind context here will fail this module.
CONSUMERS = {
    "transcript_refinement.j2": "stage1",
    "storyboard_generation.j2": "stage2",
    "master.j2": None,
    "image_generation.j2": None,
    "video_generation.j2": None,
    "animation_generation.j2": None,
    "tts_voice.j2": None,
    "talking_head.j2": None,
    "composition.j2": None,
    "translation.j2": None,
}

# One unmistakable sentinel per Jinja variable the workers bind.
SENTINELS = {
    "project_title": "SENTINEL-PROJECT-TITLE",
    "project_description": "SENTINEL-PROJECT-DESCRIPTION",
    "target_audience": "SENTINEL-TARGET-AUDIENCE",
    "language_code": "SENTINEL-LANG",
    "transcript_text": "SENTINEL-TRANSCRIPT-TEXT",
    "combined_transcript": "SENTINEL-COMBINED-TRANSCRIPT",
    # Numeric binds: values no template default could produce by accident.
    "max_duration_seconds": "4242",
    "total_runtime_seconds": "4242",
    "sequence_order": "77",
    "total_transcripts": "88",
    "transcript_count": "88",
    "target_scene_count": "99",
}


def _template_variables(path: Path) -> set[str]:
    src = path.read_text(encoding="utf-8")
    return meta.find_undeclared_variables(Environment().parse(src))


def _render_stage1(path: Path) -> str:
    """Render through Stage 1's own bind context — no reimplementation."""
    from tasks.stage1_transcript import _render_user_prompt

    return _render_user_prompt(
        template_str=path.read_text(encoding="utf-8"),
        transcript=TranscriptRecord(
            id="t-1",
            project_id="p-1",
            sequence_order=77,
            original_text=SENTINELS["transcript_text"],
            language_code=SENTINELS["language_code"],
        ),
        context={
            "project_name": SENTINELS["project_title"],
            "project_description": SENTINELS["project_description"],
            "target_audience": SENTINELS["target_audience"],
            "max_runtime_seconds": 4242,
            "total_transcripts": 88,
        },
    )


def _render_stage2(path: Path) -> str:
    """Render through Stage 2's own bind context — no reimplementation."""
    from tasks.stage2_storyboard import _render_user_prompt

    return _render_user_prompt(
        template_str=path.read_text(encoding="utf-8"),
        refined_transcripts=[
            RefinedTranscript(
                transcript_id="t-1",
                sequence_order=1,
                original_text="raw",
                refined_text=SENTINELS["combined_transcript"],
            )
        ],
        context={
            "project_name": SENTINELS["project_title"],
            "project_description": SENTINELS["project_description"],
            "target_audience": SENTINELS["target_audience"],
            "max_runtime_seconds": 4242,
            "target_scene_count": 99,
            "language_code": SENTINELS["language_code"],
        },
    )


RENDERERS = {"stage1": _render_stage1, "stage2": _render_stage2}
CONSUMED = sorted(f for f, s in CONSUMERS.items() if s is not None)
UNCONSUMED = sorted(f for f, s in CONSUMERS.items() if s is None)


class TestSeedTemplatesBindToTheWorkers:
    @pytest.mark.parametrize("filename", CONSUMED)
    def test_every_variable_renders_non_empty(self, filename):
        path = SEED_DIR / filename
        assert path.exists(), f"seed template missing: {path}"

        stage = CONSUMERS[filename]
        rendered = RENDERERS[stage](path)

        unbound = []
        for var in sorted(_template_variables(path)):
            sentinel = SENTINELS.get(var)
            if sentinel is None:
                unbound.append(
                    f"{var} (no {stage} binding known to this test)"
                )
            elif sentinel not in rendered:
                unbound.append(f"{var} (rendered empty)")

        assert not unbound, (
            f"{filename} references variables {stage} does not bind: "
            f"{unbound}. The workers' names are the contract (operator "
            f"ruling 2026-08-22) — rename the template, not the worker."
        )

    def test_the_transcript_actually_reaches_stage1(self):
        """The exact F6 regression, stated as its own assertion."""
        rendered = _render_stage1(SEED_DIR / "transcript_refinement.j2")
        assert SENTINELS["transcript_text"] in rendered
        assert "narration_text" not in rendered

    def test_the_transcript_actually_reaches_stage2(self):
        rendered = _render_stage2(SEED_DIR / "storyboard_generation.j2")
        assert SENTINELS["combined_transcript"] in rendered

    def test_the_runtime_is_the_projects_not_the_template_default(self):
        """Both templates carry `| default(1800)`; 1800 means unbound."""
        for filename in CONSUMED:
            rendered = RENDERERS[CONSUMERS[filename]](SEED_DIR / filename)
            assert "4242" in rendered, filename
            assert "1800" not in rendered, (
                f"{filename} fell back to its own default — "
                f"max_duration_seconds is not reaching it"
            )


class TestTheConsumerMapIsHonest:
    def test_every_seed_file_is_accounted_for(self):
        on_disk = {p.name for p in SEED_DIR.glob("*.j2")}
        assert on_disk == set(CONSUMERS), (
            "seed templates and the consumer map have diverged: "
            f"unmapped={sorted(on_disk - set(CONSUMERS))} "
            f"missing={sorted(set(CONSUMERS) - on_disk)}"
        )

    def test_only_stage1_and_stage2_fetch_prompts_from_the_api(self):
        """If a stage starts fetching, its template needs a bind context here."""
        import inspect
        import pkgutil

        import tasks

        fetchers = []
        for mod in pkgutil.iter_modules(tasks.__path__):
            if not mod.name.startswith("stage") and mod.name != "talking_head_task":
                continue
            try:
                m = __import__(f"tasks.{mod.name}", fromlist=["_"])
            except Exception:
                continue
            if hasattr(m, "_resolve_prompts_from_api"):
                fetchers.append(mod.name)

        assert sorted(fetchers) == ["stage1_transcript", "stage2_storyboard"], (
            f"a new stage fetches prompts from the API ({fetchers}); add its "
            f"seed template's bind context to CONSUMERS/SENTINELS above"
        )

    def test_the_unconsumed_templates_are_recorded(self):
        """Eight of ten seeded types have no reader. Stated, not hidden."""
        assert len(UNCONSUMED) == 8
        assert "translation.j2" in UNCONSUMED
