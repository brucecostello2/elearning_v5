"""
WP-07-CHECKPOINTS - the worker half. Swallow-register entry 3.

`save_checkpoint` logged a warning and returned `False` on every failure. Fifteen
call sites, none checking the return value. Since the POST route did not exist,
every checkpoint write in this system's history returned 405 and vanished -
measured 2026-08-23: `pipeline_checkpoints` held 0 rows.

It raises now. An unrecorded stage is an unresumable stage, and continuing past a
failed checkpoint write produces exactly the job WP-07 exists to abolish.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from utils.error_handler import CheckpointWriteError, save_checkpoint


def _resp(code: int):
    r = MagicMock()
    r.status_code = code
    return r


def _client_returning(resp):
    client = MagicMock()
    client.post.return_value = resp
    ctx = MagicMock()
    ctx.__enter__.return_value = client
    ctx.__exit__.return_value = False
    return ctx, client


class TestFailureSurfaces:
    @pytest.mark.parametrize("code", [405, 400, 404, 409, 422, 500, 502, 503])
    def test_a_non_2xx_raises(self, code):
        ctx, _ = _client_returning(_resp(code))
        with patch("utils.error_handler.httpx.Client", return_value=ctx):
            with pytest.raises(CheckpointWriteError) as exc:
                save_checkpoint(
                    job_id="job-1",
                    stage_name="transcript_refinement",
                    stage_index=1,
                    status="success",
                )
        assert str(code) in str(exc.value)
        assert "not resumable" in str(exc.value)

    def test_405_is_named_because_that_is_what_production_returned(self):
        """The exact live condition: 405 Method Not Allowed, allow: GET."""
        ctx, _ = _client_returning(_resp(405))
        with patch("utils.error_handler.httpx.Client", return_value=ctx):
            with pytest.raises(CheckpointWriteError) as exc:
                save_checkpoint(
                    job_id="job-1", stage_name="final_render",
                    stage_index=8, status="success",
                )
        msg = str(exc.value)
        assert "405" in msg
        assert "final_render" in msg
        assert "job-1" in msg

    def test_a_transport_error_raises(self):
        with patch(
            "utils.error_handler.httpx.Client",
            side_effect=OSError("connection refused"),
        ):
            with pytest.raises(CheckpointWriteError) as exc:
                save_checkpoint(
                    job_id="job-2", stage_name="tts_audio",
                    stage_index=5, status="running",
                )
        assert "connection refused" in str(exc.value)

    def test_the_checkpoint_error_is_not_reswallowed_as_a_generic_exception(self):
        """The except-Exception below the raise must not catch our own error."""
        ctx, _ = _client_returning(_resp(500))
        with patch("utils.error_handler.httpx.Client", return_value=ctx):
            with pytest.raises(CheckpointWriteError):
                save_checkpoint(
                    job_id="j", stage_name="s", stage_index=1, status="failed",
                )


class TestSuccessPathUnchanged:
    @pytest.mark.parametrize("code", [200, 201])
    def test_a_2xx_returns_true(self, code):
        ctx, client = _client_returning(_resp(code))
        with patch("utils.error_handler.httpx.Client", return_value=ctx):
            assert save_checkpoint(
                job_id="job-3", stage_name="storyboard_generation",
                stage_index=2, status="success",
            ) is True
        assert client.post.call_count == 1

    def test_the_payload_shape_is_what_the_api_route_expects(self):
        ctx, client = _client_returning(_resp(201))
        with patch("utils.error_handler.httpx.Client", return_value=ctx):
            save_checkpoint(
                job_id="job-4", stage_name="image_generation",
                stage_index=3, status="partial_success",
                checkpoint_data={"scenes": 6},
            )
        body = client.post.call_args.kwargs["json"]
        assert set(body) == {
            "stage_name", "stage_index", "status", "checkpoint_data",
        }
        assert body["stage_name"] == "image_generation"
        assert body["stage_index"] == 3
        assert body["status"] == "partial_success"
        assert body["checkpoint_data"] == {"scenes": 6}

    def test_the_url_is_the_route_that_now_exists(self):
        ctx, client = _client_returning(_resp(201))
        with patch("utils.error_handler.httpx.Client", return_value=ctx):
            save_checkpoint(
                job_id="abc", stage_name="s", stage_index=1, status="success",
            )
        url = client.post.call_args.args[0]
        assert url.endswith("/jobs/abc/checkpoints")


class TestExplicitOptOut:
    """`required=False` restores the old behaviour - but a caller has to say so."""

    def test_opt_out_returns_false_instead_of_raising(self):
        ctx, _ = _client_returning(_resp(405))
        with patch("utils.error_handler.httpx.Client", return_value=ctx):
            assert save_checkpoint(
                job_id="j", stage_name="s", stage_index=1,
                status="success", required=False,
            ) is False

    def test_opt_out_also_covers_transport_errors(self):
        with patch(
            "utils.error_handler.httpx.Client", side_effect=OSError("down"),
        ):
            assert save_checkpoint(
                job_id="j", stage_name="s", stage_index=1,
                status="success", required=False,
            ) is False

    def test_no_call_site_opts_out(self):
        """If one ever does, this test makes it a deliberate, visible decision."""
        import pathlib
        import re

        root = pathlib.Path(__file__).resolve().parents[1] / "tasks"
        offenders = [
            str(p) for p in root.glob("*.py")
            if re.search(r"save_checkpoint\([^)]*required\s*=", p.read_text(), re.S)
        ]
        assert offenders == [], f"call sites opting out of checkpoint writes: {offenders}"


class TestOrchestratorCallSiteIsCallable:
    """pipeline_orchestrator_v2.py:625 passed `stage=` - a TypeError if it ran."""

    def test_the_orchestrator_passes_the_real_parameter_names(self):
        import inspect
        import re

        import tasks.pipeline_orchestrator_v2 as orch

        src = inspect.getsource(orch.build_composition_manifest)
        calls = re.findall(r"save_checkpoint\((.*?)\n\s*\)", src, re.S)
        assert calls, "expected a save_checkpoint call in build_composition_manifest"
        for call in calls:
            # `stage=` is legitimate on update_job_status, which this function also
            # calls (:583) - so match the save_checkpoint call body only.
            assert "stage_name=" in call
            assert "stage_index=" in call
            assert "status=" in call
            assert not re.search(r"(?<![_a-z])stage\s*=", call)

    def test_every_task_module_call_site_uses_stage_name(self):
        import pathlib
        import re

        root = pathlib.Path(__file__).resolve().parents[1] / "tasks"
        bad = []
        for p in sorted(root.glob("*.py")):
            for call in re.findall(r"save_checkpoint\((.*?)\n\s*\)", p.read_text(), re.S):
                if "stage_name=" not in call:
                    bad.append(f"{p.name}: {call.strip()[:80]}")
        assert bad == [], f"save_checkpoint call sites missing stage_name: {bad}"
