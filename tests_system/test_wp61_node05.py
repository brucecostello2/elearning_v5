"""
WP-61 Task 1 — node-05's Qwen stack, asserted against the REAL files.

WHY THIS LIVES IN tests_system. It drives the shipped compose file and env
template as artefacts, the same reason `test_wp60_scripts.py` drives the real
`scripts/*.sh` rather than a fixture. A fixture here would be a second
statement of what somebody believed the invocation was, and the whole point of
these flags is that they were established by FAILURE, not by design:

  * `--max-num-seqs 128` is MANDATORY. Qwen3.8 is hybrid attention/Mamba: each
    decode sequence consumes one Mamba cache block, 216 were available at the
    48 GB budget, and vLLM's default of 1024 makes the engine REFUSE TO START.
  * `--reasoning-parser qwen3` is MANDATORY. Without it ~1400 tokens of
    chain-of-thought land in `content`, and Stage 2's JSON extractor grabs the
    schema echo out of the reasoning text.
  * The model is the FP8 build and only the FP8 build. The BF16 base is ~56 GB
    of weights and does not fit a 48 GB card.
  * `--gpu-memory-utilization` must NOT be 0.48. That was the SIMULATION cap —
    a 96 GB RTX PRO 6000 held down to 0.48 to imitate a 48 GB card. Carrying it
    onto the real card would give the model 23 GB of 48 and then report the
    result as a 48 GB measurement.

Every one of those is one careless edit away from a container that either will
not start or that starts and quietly poisons Stage 2's parser. The banked
original is `/mnt/ivgs-shared/qwen-invocation.txt`.

Nothing here talks to node-05. These are file assertions; the live acceptance
battery is the operator's and its results are in the WP-61 report.
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
COMPOSE = REPO / "ivgs-infra" / "docker-compose.llm.node05.yml"
ENV_EXAMPLE = REPO / "ivgs-infra" / ".env.node05.example"


@pytest.fixture(scope="module")
def compose_text() -> str:
    assert COMPOSE.exists(), f"{COMPOSE} is missing"
    return COMPOSE.read_text()


@pytest.fixture(scope="module")
def compose(compose_text):
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(compose_text)


@pytest.fixture(scope="module")
def env_text() -> str:
    assert ENV_EXAMPLE.exists(), f"{ENV_EXAMPLE} is missing"
    return ENV_EXAMPLE.read_text()


@pytest.fixture(scope="module")
def env(env_text) -> dict:
    """The SETTINGS, not the prose.

    Several assertions below are about what this file SETS, and the file
    deliberately explains at length what it does NOT set and why -- the 0.48
    simulation cap, `POSTGRES_PASSWORD`, the CogVideoX block. Matching those
    words in a comment and failing is the same category error as a test that
    greps a docstring: it measures the explanation instead of the artefact.
    """
    out = {}
    for line in env_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


def _command(compose) -> str:
    return compose["services"]["vllm-qwen"]["command"]


class TestTheMandatoryFlags:
    def test_max_num_seqs_is_present_and_defaults_to_128(self, compose):
        cmd = _command(compose)
        assert "--max-num-seqs" in cmd, (
            "--max-num-seqs is MANDATORY. vLLM's default of 1024 exceeds the "
            "Mamba cache blocks available at this memory budget (216 measured) "
            "and the engine REFUSES TO START."
        )
        assert "${VLLM_MAX_NUM_SEQS:-128}" in cmd
        assert ENV_EXAMPLE.read_text().count("VLLM_MAX_NUM_SEQS=128") >= 1

    def test_the_reasoning_parser_is_present_and_is_qwen3(self, compose):
        cmd = _command(compose)
        assert "--reasoning-parser" in cmd, (
            "--reasoning-parser is MANDATORY for IVGS. Without it ~1400 tokens "
            "of chain-of-thought land in `content` and Stage 2's JSON "
            "extractor grabs the schema echo out of the reasoning text."
        )
        assert "${VLLM_REASONING_PARSER:-qwen3}" in cmd

    def test_the_model_is_the_FP8_build(self, compose, env):
        cmd = _command(compose)
        assert "Qwen/Qwen3.8-27B-FP8" in cmd, (
            "the FP8 build is the only one that fits. The BF16 base is ~56 GB "
            "of weights against a 48 GB card."
        )
        assert env["VLLM_MODEL_NAME"] == "Qwen/Qwen3.8-27B-FP8"
        # And nothing has quietly offered the BF16 base as an alternative.
        assert "Qwen3.8-27B\n" not in cmd

    def test_trust_remote_code_is_set(self, compose):
        assert "--trust-remote-code" in _command(compose)

    def test_the_context_length_is_the_proven_one(self, compose, env):
        cmd = _command(compose)
        assert "${VLLM_MAX_MODEL_LEN:-131072}" in cmd
        assert env["VLLM_MAX_MODEL_LEN"] == "131072"


class TestTheSimulationCapDoesNotSurvive:
    def test_gpu_memory_utilization_is_not_0_48(self, compose, env):
        """0.48 was a 96 GB card imitating a 48 GB one. This is the real card.

        Carrying it forward would give Qwen 23 GB of 48 and then report the
        resulting KV-cache and Mamba-block figures as REAL-48GB measurements —
        which is the same class of error as quoting a simulation as an
        observation, and this package exists partly to end it.
        """
        cmd = _command(compose)
        assert "0.48" not in cmd, (
            "the 0.48 simulation cap has been carried onto the real card."
        )
        assert env["VLLM_GPU_UTIL"] != "0.48"
        assert "${VLLM_GPU_UTIL:-0.90}" in cmd
        assert env["VLLM_GPU_UTIL"] == "0.90"

    def test_the_ceiling_ruled_for_this_package_is_not_exceeded(self, env):
        """0.92 is the ceiling. If the real card gives fewer than 128 Mamba
        blocks, `--max-num-seqs` comes down; utilisation does NOT go up to
        chase the simulation's numbers."""
        assert float(env["VLLM_GPU_UTIL"]) <= 0.92


class TestTheStackShape:
    def test_it_is_its_own_compose_project(self, compose):
        """`name: ivgs-llm`, so this file can never recreate another service.

        WP-34's "additive only" rule expressed in the file rather than trusted
        to the command line.
        """
        assert compose["name"] == "ivgs-llm"
        assert list(compose["services"]) == ["vllm-qwen"]

    def test_there_is_no_networks_key(self, compose):
        """node-05 has no `ivgs-net`, and clients reach this over the host port.

        node-02 spent hours "running" while serving nothing because its
        container held a compose network that had been removed underneath it
        (WP-48 S2). The default project bridge is the one network always
        recreated with the project.
        """
        assert "networks" not in compose
        assert "networks" not in compose["services"]["vllm-qwen"]

    def test_the_healthcheck_hits_v1_models_and_carries_the_key(self, compose):
        """NOT /health.

        /health answers 200 from the moment the HTTP server binds, which is
        minutes before the weights finish loading. /v1/models answers only once
        the engine has a model to name, so it is the check that distinguishes
        "listening" from "serving". It is behind `--api-key`, so the key has to
        be sent or the healthcheck fails a healthy server.
        """
        hc = compose["services"]["vllm-qwen"]["healthcheck"]
        test = " ".join(hc["test"])
        assert "/v1/models" in test
        assert "/health" not in test
        assert "Authorization: Bearer" in test
        # Doubled `$$` so the value is expanded in the CONTAINER at run time
        # from .env.node05, not baked into the rendered compose config.
        assert "$$VLLM_API_KEY" in test

    def test_the_start_period_survives_a_29GB_download(self, compose):
        """A 60s start_period is an unhealthy-restart loop that never completes
        a single weight load."""
        hc = compose["services"]["vllm-qwen"]["healthcheck"]
        assert hc["start_period"] == "900s"

    def test_the_hf_cache_is_node_local_not_NFS(self, compose, env):
        """~29 GB of weights, mmap'd at load. mmap over NFS is why node-02
        stages CogVideoX to /opt/models."""
        volumes = compose["services"]["vllm-qwen"]["volumes"]
        assert any(v.startswith("/data/hf-cache:") for v in volumes)
        assert not any("/mnt/ivgs-shared" in v for v in volumes), (
            "the HuggingFace cache must not be on the NFS share."
        )
        assert env["HF_HOME"] == "/data/hf-cache"

    def test_the_port_is_published_and_the_api_key_pattern_is_followed(
        self, compose, env
    ):
        ports = compose["services"]["vllm-qwen"]["ports"]
        assert "0.0.0.0:8000:8000" in ports
        assert "--api-key ${VLLM_API_KEY:-ivgs-internal}" in _command(compose)
        assert env["VLLM_API_KEY"] == "ivgs-internal"

    def test_it_restarts_and_reserves_the_gpu(self, compose):
        svc = compose["services"]["vllm-qwen"]
        assert svc["restart"] == "unless-stopped"
        devices = svc["deploy"]["resources"]["reservations"]["devices"]
        assert devices[0]["driver"] == "nvidia"
        assert "gpu" in devices[0]["capabilities"]


class TestTheIdentityBlock:
    def test_the_wp38_identity_variables_are_all_present(self, env):
        """`IVGS_NODE_NAME` first, because config.py reads it first.

        The GPU scheduler keys nodes as {node_hostname}:gpu{index} and
        node_hostname defaults to the CONTAINER hostname — a hex id that
        changes on every recreate. Measured 2026-08-25: 21 registered "nodes"
        on a fleet of three GPUs.
        """
        for var in (
            "IVGS_NODE_NAME",
            "IVGS_NODE_HOSTNAME",
            "IVGS_NODE_ID",
            "NODE_HOSTNAME",
        ):
            assert env.get(var) == "node-05", f"missing identity variable: {var}"

    def test_it_was_NOT_copied_from_the_stale_node02_template(self, env):
        """The node-02 template is known stale and copying it puts four wrong
        facts on this node in the name of consistency."""
        assert not any("CHANGE_ME" in v for v in env.values()), (
            "a CHANGE_ME placeholder from .env.node02.example survived."
        )
        # node-05 runs no Celery worker and opens no database connection.
        assert "POSTGRES_PASSWORD" not in env
        # And it hosts no video engine.
        assert not any(k.startswith("COGVIDEOX") for k in env)
        assert not any(k.startswith("WAN21") for k in env)
        # ...nor the image tags for images it does not run.
        assert "IVGS_API_TAG" not in env
        assert "IVGS_WORKERS_TAG" not in env

    def test_the_prohibited_key_block_is_kept(self, env_text):
        """Read from the raw text: this block is deliberately COMMENTS."""
        for banned in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY"):
            assert f"# {banned} - NEVER" in env_text

    def test_no_real_secret_is_in_the_tracked_example(self, env):
        """`.env.node05` is gitignored; this `.example` is tracked.

        `ivgs-internal` is the shared internal vLLM key nodes 02/03/04 already
        use in tracked compose defaults — it gates a LAN port and is not a
        credential to anything external. Nothing else may appear here.
        """
        import re

        for key, value in env.items():
            if any(t in key for t in ("TOKEN", "SECRET", "PASSWORD")):
                pytest.fail(f"a secret-shaped variable is in a tracked file: {key}")
            if key == "VLLM_API_KEY":
                assert value == "ivgs-internal"
            assert not re.fullmatch(r"[A-Za-z0-9+/]{32,}={0,2}", value), (
                f"{key} looks like an encoded secret"
            )


class TestNode05IsNotWiredAsAWorker:
    def test_the_stack_declares_no_celery_service(self, compose):
        """A vLLM node is not a Celery consumer.

        AD-02's `dynamically_loadable=false` stands: this node's LLM capability
        is fixed at container start by `--model`. Adding a worker here would
        put it in the scheduler's fleet and give the scheduler a capability to
        reason about that does not exist.
        """
        for name, svc in compose["services"].items():
            assert "celery" not in name.lower(), (
                f"a Celery service has appeared in node-05's LLM stack: {name}"
            )
            command = svc.get("command") or ""
            if isinstance(command, list):
                command = " ".join(command)
            assert "celery" not in command.lower(), (
                f"service {name} runs a celery command"
            )

    def test_the_env_declares_no_queue_subscription(self, env):
        assert not any("QUEUES" in k for k in env)
        assert "IVGS_CELERY_BROKER_URL" not in env


# ---------------------------------------------------------------------------
# The operator blocks themselves
# ---------------------------------------------------------------------------

OPERATOR_BLOCKS = sorted(
    (REPO / "dev" / "workpackages").glob("WP-*-operator-blocks.md")
)


class TestOperatorBlocksAreSafeToPaste:
    """The rules in dev/CLAUDE.md §5, enforced against the blocks that carry them.

    **WP-60's own version of this check scans `.sh` files only**
    (`tests_system/test_wp60_scripts.py::test_no_shipped_script_runs_a_docker_exec_heredoc_without_stdin`,
    which globs `scripts/**/*.sh` and `dev/**/*.sh`). The defect it was written
    for was in WP-59's **operator blocks**, which are markdown — so the test
    closing that hole could not see the file the hole was in. That is not a
    criticism of WP-60; it is the same shape of gap this series keeps finding,
    and it is closed here rather than noted.
    """

    def test_the_files_exist(self):
        assert OPERATOR_BLOCKS, "no operator-block files found under dev/workpackages"

    def test_no_docker_exec_heredoc_omits_stdin(self):
        """`docker exec <c> python - <<'PY'` WITHOUT -i attaches no stdin.

        The interpreter reads EOF, executes an EMPTY script and exits 0 — a
        failure rendered as a success, which is this whole series' subject.
        """
        offenders = []
        for path in OPERATOR_BLOCKS:
            for num, line in enumerate(path.read_text().splitlines(), 1):
                if "docker exec" not in line or "<<" not in line:
                    continue
                head = line.split("<<", 1)[0]
                if " -i" not in head and " -it" not in head:
                    offenders.append(
                        f"{path.relative_to(REPO)}:{num}: {line.strip()}"
                    )
        assert not offenders, (
            "docker exec heredoc without -i in an operator block:\n"
            + "\n".join(offenders)
        )

    def test_no_block_calls_bare_exit(self):
        """`exit` in a block pasted into an interactive shell kills the login
        session (dev/CLAUDE.md §5). The permitted forms are `return 0 2>/dev/null
        || exit 0` inside a subshell, and `exit` inside a `bash -c`."""
        offenders = []
        for path in OPERATOR_BLOCKS:
            for num, line in enumerate(path.read_text().splitlines(), 1):
                stripped = line.strip()
                if not stripped.startswith("exit"):
                    continue
                offenders.append(f"{path.relative_to(REPO)}:{num}: {stripped}")
        assert not offenders, (
            "a bare `exit` at the start of a line in an operator block:\n"
            + "\n".join(offenders)
        )

    def test_no_block_contains_a_credential(self):
        """Blocks read secrets out of `.env` at run time; they never carry one.

        The weights manifest carries HASHES, not tokens (Task 1(b)).
        """
        import re

        banned = re.compile(
            r"(IVGS_SERVICE_TOKEN|IVGS_MBCP_INGEST_TOKEN|JWT_SECRET_KEY|"
            r"POSTGRES_PASSWORD|GITHUB_RUNNER_TOKEN)\s*=\s*[^\s$'\"]"
        )
        offenders = []
        for path in OPERATOR_BLOCKS:
            for num, line in enumerate(path.read_text().splitlines(), 1):
                if banned.search(line):
                    offenders.append(f"{path.relative_to(REPO)}:{num}")
        assert not offenders, (
            "a literal credential appears in an operator block: "
            + ", ".join(offenders)
        )

    def test_every_wp61_block_names_the_node_it_runs_on(self):
        """dev/CLAUDE.md §5: node-labelled. A block that does not say where it
        runs is one paste away from being run on the wrong machine — and half
        of WP-61's blocks run on node-05, which no other package has touched."""
        path = REPO / "dev" / "workpackages" / "WP-61-operator-blocks.md"
        text = path.read_text()
        # Every fenced bash block must open with a RUN ON: comment.
        blocks = text.split("\n```\n")
        opened = [b for i, b in enumerate(blocks) if i % 2 == 1]
        assert len(opened) >= 7, (
            f"only {len(opened)} fenced blocks parsed out of the file; this "
            f"package ships more than that, so the parse is wrong and the "
            f"check below would pass vacuously."
        )
        for b in opened:
            first_lines = "\n".join(b.splitlines()[:3])
            assert "RUN ON:" in first_lines, (
                "a block does not declare its node in its first three lines:\n"
                + first_lines
            )
