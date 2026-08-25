"""WP-45 Task 1, worker side — the probe that could not tell you it had failed.

`check_duplicate_asset` caught every exception and returned `None`. Its four
call sites read `None` as "no duplicate exists". So a probe against a route that
**did not exist** answered 404, was swallowed, and reported itself as a clean
miss — content-hash dedup was dead fleet-wide for image, video, animation and
audio alike, and nothing on any surface said so (WP-46 addendum A5.2 / ledger
L-8; WP-00 swallowed-failures register).

The fix is not "catch less". It is that **"I could not check" and "I checked and
there is nothing" are different facts**, and the code now has a value for each:
`DuplicateCheckError` and `None`. Fail-open is still the behaviour — dedup is an
optimisation and a failed probe should mean "generate it anyway" — but the
decision is taken in the open, at a named call site, under one greppable event,
instead of being the accidental consequence of a bare `except`.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.media_converter import (  # noqa: E402
    DuplicateCheckError,
    asset_storage_path,
    check_duplicate_asset,
    compute_asset_sha256,
    find_duplicate_or_none,
)

API = "http://api.test/api/v1"
TOKEN = "test-service-token"
DIGEST = "a" * 64


def _client_returning(status_code, payload=None, text=""):
    """A patched httpx.Client whose GET answers with this response."""
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    response.text = text
    client = MagicMock()
    client.get.return_value = response
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    return client


class TestTheProbeDistinguishesAbsenceFromFailure:

    def test_a_clean_miss_is_none(self):
        with patch("httpx.Client", return_value=_client_returning(200, [])):
            assert check_duplicate_asset(DIGEST, API, TOKEN) is None

    def test_a_hit_returns_the_asset(self):
        asset = {"id": "abc", "seaweedfs_path": "/ivgs/images/x.png"}
        with patch("httpx.Client", return_value=_client_returning(200, [asset])):
            assert check_duplicate_asset(DIGEST, API, TOKEN) == asset

    def test_a_404_RAISES_rather_than_looking_like_a_clean_miss(self):
        # THE ORIGINAL DEFECT, pinned. The route did not exist; this was a 404;
        # the helper returned None; every caller generated and uploaded anyway
        # and reported was_deduplicated: false forever.
        with patch("httpx.Client", return_value=_client_returning(404, text="Not Found")):
            with pytest.raises(DuplicateCheckError) as exc:
                check_duplicate_asset(DIGEST, API, TOKEN)
        assert "404" in str(exc.value)

    def test_a_500_raises_too(self):
        with patch("httpx.Client", return_value=_client_returning(500, text="boom")):
            with pytest.raises(DuplicateCheckError):
                check_duplicate_asset(DIGEST, API, TOKEN)

    def test_an_unreachable_api_raises(self):
        with patch("httpx.Client", side_effect=OSError("connection refused")):
            with pytest.raises(DuplicateCheckError) as exc:
                check_duplicate_asset(DIGEST, API, TOKEN)
        assert "connection refused" in str(exc.value)


class TestTheTwoHashKindsAskDifferentQuestions:

    def _captured_params(self, **kwargs):
        client = _client_returning(200, [])
        with patch("httpx.Client", return_value=client):
            check_duplicate_asset(DIGEST, API, TOKEN, **kwargs)
        return client.get.call_args.kwargs["params"]

    def test_content_is_the_default_and_asks_by_content_hash(self):
        assert self._captured_params() == {"content_hash": DIGEST}

    def test_params_asks_by_generation_params_hash(self):
        # The expensive one: video and animation probe BEFORE rendering, so a
        # hit skips the GPU work rather than just the upload.
        assert self._captured_params(hash_kind="params") == {
            "generation_params_hash": DIGEST
        }

    def test_any_asks_the_either_column_parameter(self):
        assert self._captured_params(hash_kind="any") == {"sha256": DIGEST}

    def test_the_project_scopes_the_probe_when_given(self):
        params = self._captured_params(project_id="c12fa967")
        assert params["project_id"] == "c12fa967"

    def test_an_unknown_hash_kind_is_a_programming_error_not_a_silent_default(self):
        with pytest.raises(ValueError):
            check_duplicate_asset(DIGEST, API, TOKEN, hash_kind="vibes")


class TestFailOpenIsADecisionNotAnAccident:

    def test_the_wrapper_returns_none_on_a_failed_probe(self):
        # Dedup is an optimisation: a probe that cannot be answered should mean
        # "generate it anyway". Same outcome as before; the difference is where
        # the decision is made and that it is now logged.
        with patch("httpx.Client", return_value=_client_returning(503)):
            assert find_duplicate_or_none(DIGEST, API, TOKEN) is None

    def test_the_fail_open_is_logged_under_one_greppable_event(self):
        # The WP-08 `gpu_reservation_unavailable ... fail_open=True` precedent.
        with patch("httpx.Client", return_value=_client_returning(503)):
            with patch("utils.media_converter.logger") as log:
                find_duplicate_or_none(DIGEST, API, TOKEN)
        assert log.error.called
        event, kwargs = log.error.call_args[0][0], log.error.call_args.kwargs
        assert event == "dedup_check_unavailable"
        assert kwargs["fail_open"] is True
        assert "consequence" in kwargs

    def test_a_clean_miss_is_not_logged_as_a_failure(self):
        with patch("httpx.Client", return_value=_client_returning(200, [])):
            with patch("utils.media_converter.logger") as log:
                assert find_duplicate_or_none(DIGEST, API, TOKEN) is None
        assert not log.error.called


class TestThePayloadShapesTheApiActuallySends:

    def test_a_bare_list_is_read(self):
        # `GET /api/v1/assets` has response_model=List[AssetResponse].
        with patch("httpx.Client", return_value=_client_returning(200, [{"id": "1"}])):
            assert check_duplicate_asset(DIGEST, API, TOKEN)["id"] == "1"

    def test_a_paginated_envelope_is_also_read(self):
        # Defensive: `data` is the envelope key this API uses everywhere else,
        # so a future move to PaginatedResponse does not silently return None.
        payload = {"data": [{"id": "2"}], "total": 1}
        with patch("httpx.Client", return_value=_client_returning(200, payload)):
            assert check_duplicate_asset(DIGEST, API, TOKEN)["id"] == "2"


class TestAssetStoragePath:

    def test_it_reads_the_field_the_api_actually_sends(self):
        # THE DEFECT: three call sites read `storage_path`, a key AssetResponse
        # has never carried, so a dedup hit set the result's path to "" and the
        # scene lost its file reference.
        assert asset_storage_path({"seaweedfs_path": "/ivgs/a.png"}) == "/ivgs/a.png"

    def test_it_still_accepts_the_old_name_rather_than_asserting_either(self):
        assert asset_storage_path({"storage_path": "/ivgs/b.png"}) == "/ivgs/b.png"

    def test_an_absent_path_is_an_empty_string_not_a_crash(self):
        assert asset_storage_path({}) == ""
        assert asset_storage_path(None) == ""


class TestComputeAssetSha256:

    def test_it_is_the_plain_sha256_of_the_bytes(self):
        import hashlib

        data = b"the rendered frame"
        assert compute_asset_sha256(data) == hashlib.sha256(data).hexdigest()

    def test_it_is_the_value_the_upload_route_verifies_against(self):
        # The route recomputes this server-side and refuses a mismatch, so the
        # two must be the same function of the same bytes.
        data = b"identical output"
        assert len(compute_asset_sha256(data)) == 64
        assert compute_asset_sha256(data) == compute_asset_sha256(data)
