"""
WP-62 — the surfaces, the operator blocks and the seed conformance gate.

This module lives in `tests_system` for the reason the other modules here do:
it drives REAL shipped artefacts — the tracked operator blocks, the tracked
compose file, the real page sources and the real
`scripts/check_seed_conformance.sh` — rather than a fixture that would be a
second statement of what somebody believed they contained.
"""
from __future__ import annotations

import pathlib
import re
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
FRONTEND = REPO / "ivgs-frontend" / "src"
BLOCKS = REPO / "dev" / "workpackages" / "WP-61-operator-blocks.md"
COMPOSE = REPO / "ivgs-infra" / "docker-compose.llm.node05.yml"
ENV_EXAMPLE = REPO / "ivgs-infra" / ".env.node05.example"
CONFORMANCE = REPO / "scripts" / "check_seed_conformance.sh"


# ===========================================================================
# TASK 4 — the Overview page stops duplicating itself
# ===========================================================================


class TestOverviewDoesNotDuplicateItself:
    """RULED: remove Quick Access entirely.

    It rendered a card per tab — Transcripts, Storyboard, Media Assets, Audio,
    Talking Head, Draft Preview, Final Renders, Prompts, Jobs, Languages — as a
    grid of links to the same ten destinations the tab bar lists an inch above
    it. Ten affordances, zero added information: no counts, no status, no
    "3 scenes need review". The cards were larger, so on a short viewport they
    were the MORE prominent of the two navigations.

    WP-43 Task 1 is why it survived: before that package the tab bar lived
    inside this page, so Quick Access was a second navigation on the one page
    that had a first. WP-43 moved the tab bar into the shell and onto all
    eleven tabs; the duplicate below it was left behind.
    """

    OVERVIEW = FRONTEND / "app" / "projects" / "[id]" / "page.tsx"

    def test_quick_access_is_gone(self):
        body = self.OVERVIEW.read_text(encoding="utf-8")
        # The removal is recorded in a comment, so the heading string may
        # appear in prose. What must not survive is the RENDER.
        assert "PROJECT_TABS.filter" not in body
        assert "tabHref(projectId, tab)" not in body

    def test_the_page_no_longer_imports_the_tab_list_at_all(self):
        """The strongest form of "it is gone": the page cannot render a second
        navigation because it no longer knows what the tabs are."""
        body = self.OVERVIEW.read_text(encoding="utf-8")
        assert "@/lib/project-tabs" not in body

    def test_the_tab_bar_is_still_rendered_exactly_once_by_the_shell(self):
        """Stepper (status) and tab bar (navigation) both STAY. They look
        similar and are not: one says where the work is, the other says where
        you are."""
        shell = (FRONTEND / "components" / "project" / "ProjectShell.tsx").read_text(
            encoding="utf-8"
        )
        assert shell.count("PROJECT_TABS.map(") == 1

    def test_no_project_page_renders_the_tab_list_itself(self):
        """The sweep. Any page that maps PROJECT_TABS is a second navigation on
        a screen that already has the shell's."""
        offenders = []
        for path in (FRONTEND / "app" / "projects").rglob("*.tsx"):
            body = path.read_text(encoding="utf-8")
            if "PROJECT_TABS" in body and ".map(" in body:
                offenders.append(str(path.relative_to(REPO)))
        assert not offenders, (
            "a project page renders the tab list a second time: "
            + ", ".join(offenders)
        )

    def test_the_approve_button_is_not_on_two_controls_of_one_screen(self):
        """Task 2(d) moved the storyboard approval into the gate panel. Leaving
        the corner button as well would be the same-screen duplication this
        task removes on Overview."""
        page = (
            FRONTEND / "app" / "projects" / "[id]" / "storyboard" / "page.tsx"
        ).read_text(encoding="utf-8")
        assert 'label="Approve storyboard"' not in page
        assert "GateReviewPanel" in page


# ===========================================================================
# TASK 1 — no hardcoded fleet hardware on the GPU page
# ===========================================================================


class TestTheGpuPageReadsTheFleetRatherThanAList:
    GPU_PAGE = FRONTEND / "app" / "monitoring" / "gpu" / "page.tsx"

    def test_the_hardcoded_card_labels_are_gone(self):
        """`GPU_LABELS` was a hand-maintained second statement of the fleet's
        hardware and it was wrong twice: WP-53 found every one of the five GPU
        rows naming a card not in this fleet, under a comment citing "§3.2";
        the corrected list then still carried node-04 at 96 GB against the
        API's own 48 GB (WP-53 D-2)."""
        body = self.GPU_PAGE.read_text(encoding="utf-8")
        assert "const GPU_LABELS" not in body
        assert "const NODE_IDS" not in body

    def test_the_label_is_derived_from_the_payload(self):
        body = self.GPU_PAGE.read_text(encoding="utf-8")
        assert "function gpuLabelFor" in body
        assert "node.gpu_model" in body

    def test_the_header_states_the_subset_relationship(self):
        """RULED: "5 GPUs - 3 scheduler workers"."""
        body = self.GPU_PAGE.read_text(encoding="utf-8")
        assert "GPUs in the fleet" in body
        assert "scheduler worker" in body
        assert "fleetStats.gpuCount" in body
        assert "fleetStats.schedulerCount" in body

    def test_drain_is_gated_on_the_payloads_own_flag(self):
        card = (
            FRONTEND / "components" / "monitoring" / "GPUNodeCard.tsx"
        ).read_text(encoding="utf-8")
        assert "node.supports_drain" in card
        assert "node.in_scheduler" in card
        assert "device_used_vram_mb" in card


# ===========================================================================
# TASK 8 — the operator blocks, corrected to what actually ran
# ===========================================================================


def _fenced_code(markdown: str) -> str:
    """Only the PASTE BLOCKS, not the prose around them.

    The corrections are recorded in this file's own header, which quotes the
    defective commands verbatim so a reader knows what changed. A test that
    scanned the whole document would fail on its own changelog -- and, worse,
    would pass if somebody moved a defective command into a comment.
    """
    out, inside = [], False
    for line in markdown.splitlines():
        if line.startswith("```"):
            inside = not inside
            continue
        if inside:
            out.append(line)
    return "\n".join(out)


def _uncommented(text: str) -> str:
    """Lines with the `#` comment tail removed. Never `#` inside a string."""
    out = []
    for line in text.splitlines():
        stripped = line.split("#", 1)[0] if line.lstrip().startswith("#") else line
        out.append(stripped)
    return "\n".join(out)


class TestOperatorBlockCorrections:
    @pytest.fixture(scope="class")
    def blocks(self) -> str:
        """The COMMANDS. Fenced code, with its `#` comment lines removed.

        The corrections are recorded twice on purpose -- once in this file's
        header and once beside the line they fixed -- and both quote the
        defective command verbatim so a reader knows what changed. Neither is
        executable. Stripping comments as well as prose means these tests
        measure what would RUN if the block were pasted, which is the only
        thing that matters about a paste block.
        """
        return _uncommented(_fenced_code(BLOCKS.read_text(encoding="utf-8")))

    def test_a_the_removed_huggingface_cli_is_gone(self, blocks):
        """`huggingface-cli` is REMOVED from the current nightly; the shim
        exits 1, so the block aborted at `RC != 0`."""
        assert "--entrypoint huggingface-cli" not in blocks
        assert "--entrypoint hf" in blocks

    def test_a_the_rejected_symlink_flag_is_gone(self, blocks):
        """`--local-dir-use-symlinks` is rejected by the newer hub, and was
        pointless anyway: there is no `--local-dir` in the command."""
        assert "--local-dir-use-symlinks" not in blocks

    def test_b_both_finds_follow_symlinks(self, blocks):
        """`find -type f` hashed NOTHING: the hub cache exposes weights under
        `snapshots/` as SYMLINKS, so a 29 GB cache produced a manifest whose
        own total line read "safetensors files: 0"."""
        finds = re.findall(r"^\s*find\b[^\n]*", blocks, flags=re.M)
        assert finds, "the manifest block no longer runs find at all"
        for line in finds:
            assert line.strip().startswith("find -L"), (
                f"a find without -L survives and will hash nothing: {line!r}"
            )

    def test_c_the_ufw_rules_are_inserted_not_appended(self, blocks):
        """node-05 carries `Anywhere ALLOW from 192.168.1.0/24`. ufw is
        first-match, so an APPENDED deny sits below it and is inert."""
        assert "sudo ufw insert" in blocks
        # No bare append of the port rules any more.
        assert not re.search(r"^\s*sudo ufw allow from .* port 8000", blocks, re.M)
        assert not re.search(r"^\s*sudo ufw deny 8000/tcp", blocks, re.M)

    def test_c_the_posture_is_measured_before_and_gated_after(self, blocks):
        """An echo telling a human to check an ordering is not a control."""
        assert "BROAD RULES ALREADY PRESENT" in blocks
        assert "192.168.1.0/24" in blocks
        assert "INERT" in blocks
        assert "CHECK THE ORDER. ufw is first-match" not in blocks

    def test_d_the_engine_is_pinned_by_digest_in_the_compose(self):
        """`cu130-nightly` MOVED mid-package: two pulls, two images, the SAME
        version string on both."""
        compose = COMPOSE.read_text(encoding="utf-8")
        assert "image: vllm/vllm-openai@${VLLM_IMAGE_DIGEST}" in compose
        # The old floating-tag form survives only in the comment that records
        # why it went; it must not survive as YAML.
        assert "vllm/vllm-openai:${VLLM_IMAGE_TAG" not in _uncommented(compose)

    def test_d_the_digest_variable_has_no_silent_fallback(self):
        """Every other ${VAR} in that file has a `:-` default so a missing env
        file fails loudly on the model name. The image is the opposite case: a
        fallback to a floating tag would fail SILENTLY -- the container would
        start and serve."""
        compose = _uncommented(COMPOSE.read_text(encoding="utf-8"))
        assert "${VLLM_IMAGE_DIGEST:-" not in compose

    #: The digest the operator READ OFF THE RUNNING CONTAINER
    #: (`docker inspect ... RepoDigests`, node-05, 2026-08-26) and committed in
    #: a6a4f8e. It is the one value that is allowed to be a complete digest
    #: here, because it is the one value that was measured.
    MEASURED_NODE05_DIGEST = (
        "sha256:3dbe092ec5b2cef63b6104d33fa75d6ce53a7870962529ada69f78bbbc38e776"
    )

    def test_d_the_env_example_records_the_pin_and_does_not_invent_it(self):
        """The example carries a MEASURED digest, or a prefix, and never a guess.

        UPDATED BY WP-63, AND IT IS A BETTER DISCRIMINATION, NOT A LOOSER GATE.

        This asserted `not re.fullmatch(r"sha256:[0-9a-f]{64}", value)` — no
        complete digest, ever. The property it was protecting is *"a tracked
        file must not ship a plausible but wrong 64-character digest"*, and
        while the real one was unknown, "no complete digest" was the only
        available way to say that.

        The operator then MEASURED it, off the running container, and committed
        it (a6a4f8e, "the full engine digest, closing WP-62 D-1 / WP62-L8").
        The old assertion turned red on the arrival of the very fact it was
        waiting for — a rule that could not distinguish a measured value from
        an invented one, and so rejected both.

        It now names the measured value. An invented 64-character digest still
        fails, and it fails BY NAME rather than by category; so does a
        truncation to a different prefix. This is strictly stronger: the old
        form would have accepted `sha256:3dbe092e-WHATEVER-I-LIKE`.
        """
        env = ENV_EXAMPLE.read_text(encoding="utf-8")
        assert "VLLM_IMAGE_DIGEST=" in env
        value = re.search(r"^VLLM_IMAGE_DIGEST=(.*)$", env, re.M).group(1)
        assert value.startswith("sha256:3dbe092e")
        if re.fullmatch(r"sha256:[0-9a-f]{64}", value):
            assert value == self.MEASURED_NODE05_DIGEST, (
                "the example ships a complete 64-character digest that is NOT "
                "the one measured on node-05. A plausible wrong digest is how "
                "a fleet gets pinned to an image nobody ran."
            )
        else:
            # Still a placeholder. It must be obviously one, not a near-miss.
            assert not re.fullmatch(r"sha256:[0-9a-f]{9,}", value), (
                "the value is neither the measured digest nor an obvious "
                "placeholder; it reads as a real digest and is not one"
            )

    def test_d_there_is_a_block_that_fills_the_digest_in(self, blocks):
        whole = BLOCKS.read_text(encoding="utf-8")
        assert "## A06B" in whole          # the heading is prose
        assert "RepoDigests" in blocks     # the command is not
        assert "sha256:3dbe092e" in blocks

    def test_e_the_publisher_prints_both_digests_named(self):
        """WP-62 Task 8(e). The reported "divergence" was two shas of the SAME
        bytes under one label: the file (`67be5991…`) and the file stripped of
        its trailing newline (`205ddaba…`, what `.strip()` produces). Measured
        2026-08-26: the baked template and the tracked one are identical."""
        script = (
            REPO / "ivgs-api" / "app" / "scripts" / "wp61_publish_prompt.py"
        ).read_text(encoding="utf-8")
        assert "file sha256" in script
        assert "stored sha256" in script
        assert re.search(r'print\(f"sha256\s+:', script) is None, (
            "the single ambiguous `sha256` label is back"
        )


class TestSeedConformanceGate:
    """Task 8(e), the half that matters going forward.

    Nothing anywhere compared the baked seed with the tracked seed, so a
    genuinely divergent one WOULD have shipped silently; the only reason it had
    not is that nobody had changed a template since the last build. A template
    that reaches the `prompts` table is a contract — `TranslationService`
    REFUSES to run under a prompt without the fail-and-flag marker — so a stale
    one is not a cosmetic drift.
    """

    def test_the_script_ships_and_is_executable(self):
        assert CONFORMANCE.exists()
        assert CONFORMANCE.stat().st_mode & 0o111, "not executable"

    def test_it_compares_file_bytes_not_stripped_text(self):
        """Introducing a third normalisation here would be the original defect
        again."""
        body = CONFORMANCE.read_text(encoding="utf-8")
        assert "sha256sum" in body
        assert "strip" not in body

    def test_it_checks_both_directions(self):
        """A template deleted from the tree but still baked in is also a
        divergence, and it is the one a one-way check misses."""
        body = CONFORMANCE.read_text(encoding="utf-8")
        assert "MISSING IN IMAGE" in body
        assert "EXTRA IN IMAGE" in body

    def test_it_does_not_read_a_tag_variable_out_of_a_container(self):
        """dev/CLAUDE.md §6: `docker exec <c> env` reports a STALE
        `IVGS_*_TAG`. The image comes from `docker inspect`."""
        body = CONFORMANCE.read_text(encoding="utf-8")
        assert "docker inspect ivgs-fastapi --format '{{.Config.Image}}'" in body
        assert "IVGS_API_TAG" not in body

    @pytest.mark.skipif(
        shutil.which("docker") is None, reason="docker is not on PATH"
    )
    def test_it_passes_against_the_deployed_image(self):
        """Gated BOTH ways matters here: a check that could never fail would be
        trivially "safe" and would gate nothing. The negative case is
        `test_it_reports_a_divergence` below, which drives the same comparison
        against a template the image cannot contain."""
        result = subprocess.run(
            ["bash", str(CONFORMANCE)],
            capture_output=True, text=True, timeout=90,
        )
        if result.returncode == 2:
            pytest.skip(f"image not readable here: {result.stdout.strip()[:200]}")
        assert result.returncode == 0, result.stdout + result.stderr
        assert "PASS:" in result.stdout

    @pytest.mark.skipif(
        shutil.which("docker") is None, reason="docker is not on PATH"
    )
    def test_it_reports_a_divergence(self, tmp_path):
        """The negative gate. A tree whose template differs by one byte must
        FAIL, or the check is decoration.

        The tree is copied to `tmp_path` and one template is altered there;
        nothing under the repo is touched.
        """
        image = subprocess.run(
            ["docker", "inspect", "ivgs-fastapi", "--format", "{{.Config.Image}}"],
            capture_output=True, text=True,
        ).stdout.strip()
        if not image:
            pytest.skip("ivgs-fastapi is not running")

        fake_repo = tmp_path / "repo"
        (fake_repo / "ivgs-api" / "seed" / "default_prompts").mkdir(parents=True)
        (fake_repo / "scripts").mkdir()
        shutil.copy(CONFORMANCE, fake_repo / "scripts" / CONFORMANCE.name)
        src = REPO / "ivgs-api" / "seed" / "default_prompts"
        for path in src.glob("*.j2"):
            shutil.copy(path, fake_repo / "ivgs-api" / "seed" / "default_prompts")
        target = (
            fake_repo / "ivgs-api" / "seed" / "default_prompts" / "translation.j2"
        )
        target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")

        result = subprocess.run(
            ["bash", str(fake_repo / "scripts" / CONFORMANCE.name), image],
            capture_output=True, text=True, timeout=90,
        )
        if result.returncode == 2:
            pytest.skip("image not readable here")
        assert result.returncode == 1, result.stdout + result.stderr
        assert "DIVERGED" in result.stdout
        assert "translation.j2" in result.stdout
