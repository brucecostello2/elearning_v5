"""WP-65 -- the weight-fetch service, its refusals, and its placement policy.

The refusals are the point of this file. WP-65 Task 1 measured that the Model
Store's NODES column reports a Redis LRU of models a job once loaded, and says
"none" for every state that is not that -- so "certified but not fetched",
"engine-only, nothing to fetch" and "no node hosts this engine" all render
identically today. Each needs a different action from an admin, so each gets a
named refusal here and each is tested as a first-class outcome.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from shared.weights.bundle import (
    ChecksumError,
    FetchError,
    _STAGING_PREFIX,
    bundle_is_present,
    compute_bundle_digest,
    fetch_bundle,
    verify_signature,
)
from shared.weights.errors import (
    BundleVerificationError,
    CredentialsUnavailableError,
    DigestMismatchError,
    EngineOnlyCertificationError,
    NoHostForEngineError,
    NoWeightReferenceError,
    PlacementNotLocalError,
    UnknownReferenceFormError,
)
from shared.weights.placement import (
    ENGINE_HOSTS,
    hosts_for_engine,
    host_for_model,
    placement_for,
)
from shared.weights.refs import RefKind, classify_weights_ref, parse_weights_ref
from shared.weights.service import (
    NODE_HOSTNAME_ENV,
    SERVING_TOKEN_ENV,
    fetch_model_weights,
    plan_fetch,
)

#: Every fetch test that expects to REACH the transfer has to claim to be
#: running on the target node -- see TestPlacementIsRefusedOffTarget for why.
_ON_NODE_03 = {NODE_HOSTNAME_ENV: "node-03"}


# ---------------------------------------------------------------------------
# fixtures: a Model Store row, and a fake MBCP serving plane
# ---------------------------------------------------------------------------

class _Row:
    """The subset of ``Model`` the fetch service reads (ModelRowLike)."""

    def __init__(self, **kw):
        self.name = kw.get("name", "test-model")
        self.engine = kw.get("engine", "comfyui")
        self.stage = kw.get("stage", "animation_generation")
        self.weights_ref = kw.get("weights_ref")
        self.weights_checksum = kw.get("weights_checksum")
        self.default_params = kw.get("default_params") or {}


def _make_bundle(files: dict[str, bytes]) -> dict:
    entries = [
        {"logical_name": name, "sha256": hashlib.sha256(data).hexdigest()}
        for name, data in files.items()
    ]
    return {
        "bundle_digest": compute_bundle_digest(entries),
        "files": entries,
        "bundle_token": "bundle-token-for-test",
        "engine_version": "sha256:enginedigest",
    }


class FakeServing:
    """A local stand-in for the MBCP serving plane.

    The real pass is HELD -- it needs the operator's MBCP serving token, which
    is a standing pending-register item. Everything except the socket is
    exercised here: manifest shape, per-file streaming, per-file SHA-256, the
    bundle digest, staging, promotion and idempotency.
    """

    def __init__(self, files: dict[str, bytes], *, corrupt: str | None = None):
        self.files = files
        self.corrupt = corrupt
        self.manifest = _make_bundle(files)
        self.file_requests: list[str] = []
        self.calls = 0

    def fetch(self, serving_url, model_id, token, dest_dir, *, tier="certified",
              signing_key=None, timeout=600.0, chunk_size=1 << 20,
              skip_if_present=True):
        """Signature-compatible with ``bundle.fetch_bundle``."""
        self.calls += 1
        from shared.weights.bundle import FetchResult, _promote, _safe_dest

        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        entries = self.manifest["files"]

        if skip_if_present and bundle_is_present(dest, entries):
            return FetchResult(
                model_id=model_id, dest_dir=dest,
                bundle_digest=self.manifest["bundle_digest"],
                files=[e["logical_name"] for e in entries],
                size_bytes=0, digest_verified=True, skipped_present=True,
            )

        import shutil
        import uuid as _uuid
        staging = dest / f"{_STAGING_PREFIX}{_uuid.uuid4().hex}"
        staging.mkdir()
        self.staging_used = staging
        written, total = [], 0
        try:
            for entry in entries:
                logical = entry["logical_name"]
                self.file_requests.append(logical)
                data = self.files[logical]
                if self.corrupt == logical:
                    data = data + b"tampered"
                target = _safe_dest(staging, logical)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                got = hashlib.sha256(data).hexdigest()
                if got != entry["sha256"]:
                    raise ChecksumError(
                        f"{logical}: sha256 mismatch "
                        f"(manifest={entry['sha256']}, got={got})"
                    )
                written.append(logical)
                total += len(data)
            _promote(staging, dest)
        finally:
            shutil.rmtree(staging, ignore_errors=True)

        return FetchResult(
            model_id=model_id, dest_dir=dest,
            bundle_digest=self.manifest["bundle_digest"],
            files=written, size_bytes=total, digest_verified=True,
            signature_verified=signing_key is not None,
        )


_GOOD_REF = "https://serving.mbcp.internal/weights/c1d3c3a5-7771-470b-8567-81bf65e3eac5/manifest?tier=certified"


# ---------------------------------------------------------------------------
# reference parsing -- the two MBCP shapes, plus the legacy one
# ---------------------------------------------------------------------------

class TestWeightsRefParsing:
    def test_a_weight_bundle_manifest_url_is_fetchable(self):
        ref = parse_weights_ref(_GOOD_REF)
        assert ref.kind is RefKind.WEIGHT_BUNDLE
        assert ref.is_fetchable
        assert ref.model_id == "c1d3c3a5-7771-470b-8567-81bf65e3eac5"
        assert ref.tier == "certified"
        assert ref.serving_url == "https://serving.mbcp.internal"

    def test_the_legacy_mbcp_scheme_parses_and_needs_a_configured_base(self):
        """``wan2.2-animate``'s live value, written by WP-46 before the seam."""
        ref = parse_weights_ref(
            "mbcp://serving/weights/c1d3c3a5-7771-470b-8567-81bf65e3eac5?tier=candidate"
        )
        assert ref.is_fetchable
        assert ref.tier == "candidate"
        assert ref.serving_url is None
        assert ref.resolve_serving_url("http://x:8000/") == "http://x:8000"
        with pytest.raises(UnknownReferenceFormError):
            ref.resolve_serving_url(None)

    def test_an_engine_only_certification_is_refused_by_its_own_name(self):
        """MBCP's OWN branch: ``certifications.py:618`` emits this URL when a
        certification has no weights checksum, and its comment says
        "engine_only has NO weights to serve". All three MBCP-ingested
        animation rows carry this shape, which is why the store shows them as
        permanently un-fetched.
        """
        digest = "sha256:257fc2624282e57ce36457d8d9ae06a8672e5d90ebd6c475b8b7146fa36df9b5"
        with pytest.raises(EngineOnlyCertificationError) as exc:
            parse_weights_ref(f"http://serving-api:8000/engines/{digest}/manifest")
        assert exc.value.reason == "engine_only_certification"
        assert "no weights to fetch" in str(exc.value)
        assert "deploying that image" in str(exc.value)

    def test_a_null_reference_says_nothing_was_ingested(self):
        for empty in (None, "", "   "):
            with pytest.raises(NoWeightReferenceError) as exc:
                parse_weights_ref(empty)
            assert exc.value.reason == "no_weight_reference"

    @pytest.mark.parametrize("bad", [
        "file:///etc/passwd",
        "https://serving/models/abc/manifest",
        "mbcp://elsewhere/weights/abc",
        "not a url at all",
    ])
    def test_an_unrecognised_form_is_refused_not_guessed(self, bad):
        """A mis-parsed reference fetches the wrong bytes and then records
        them as verified. Refusing is the only safe default."""
        with pytest.raises(UnknownReferenceFormError):
            parse_weights_ref(bad)

    def test_classify_reports_the_slug_without_raising(self):
        assert classify_weights_ref(_GOOD_REF) == "weight_bundle"
        assert classify_weights_ref(None) == "no_weight_reference"
        assert (
            classify_weights_ref("http://s:8000/engines/abc/manifest")
            == "engine_only_certification"
        )


# ---------------------------------------------------------------------------
# placement -- Task 3
# ---------------------------------------------------------------------------

class TestPlacementPolicy:
    def test_no_node_hosts_engine_x_is_a_named_first_class_refusal(self):
        """WP-65 Task 3's required outcome, and the true state of
        AnimateDiff-SD15 and MimicMotion until a host exists."""
        with pytest.raises(NoHostForEngineError) as exc:
            placement_for("animatediff")
        assert exc.value.reason == "no_host_for_engine"
        assert "no node hosts engine 'animatediff'" in str(exc.value)

    def test_remotion_has_no_host_either(self):
        """WP-68's starting position, recorded here so it cannot be assumed."""
        with pytest.raises(NoHostForEngineError):
            placement_for("remotion")

    def test_an_engine_nobody_declared_still_refuses_with_the_fleet_listed(self):
        with pytest.raises(NoHostForEngineError) as exc:
            placement_for("stable-diffusion-xl")
        assert "the fleet serves" in str(exc.value)

    def test_one_engine_key_has_two_deployments_and_they_are_not_interchangeable(self):
        """``comfyui`` is node-03's Wan pack AND node-04's FLUX ComfyUI.
        docker-compose.node03.yml:113-120 says they are told apart by the
        per-worker IVGS_COMFYUI_URL, so placement must not pick either at
        random."""
        hosts = hosts_for_engine("comfyui")
        assert len(hosts) == 2
        nodes = {h.node_id for h in hosts}
        assert nodes == {"node-03", "node-04"}

    def test_animation_places_on_node_03_because_node_03_consumes_gpu_animation(self):
        host = host_for_model("comfyui", "animation_generation")
        assert host.node_id == "node-03"
        assert host.container == "ivgs-wan-animate-server-node03"
        assert "gpu_animation" in host.queues

    def test_image_places_on_node_04_because_node_04_consumes_gpu_image(self):
        host = host_for_model("comfyui", "image_generation")
        assert host.node_id == "node-04"
        assert host.container == "ivgs-comfyui-primary"

    def test_node_04s_comfyui_cannot_hold_an_animation_bundle(self):
        """It mounts ``checkpoints`` and nothing else
        (docker-compose.node04.yml:68). Probed live 2026-08-26: one checkpoint,
        and empty unet/lora/clip lists. Placing a diffusion_models bundle there
        would put bytes where no loader looks."""
        from shared.weights.errors import NoPlacementRuleError

        rule = placement_for("comfyui", node_id="node-04")
        with pytest.raises(NoPlacementRuleError) as exc:
            rule.dest_for("wan_animate")
        assert "does not mount" in str(exc.value)

    def test_wan_families_land_where_mbcps_materialization_map_says(self):
        """Transcribed from ``mbcp_core/weights/materialization.py:37-100``.
        IVGS follows MBCP's convention rather than inventing a second one --
        node-03's tree is written by the .51 materializer to exactly this map.
        """
        rule = placement_for("comfyui", node_id="node-03")
        root = "/opt/models/comfyui-wan/models"
        assert rule.dest_for("wan_animate") == f"{root}/diffusion_models"
        assert rule.dest_for("wan_vae") == f"{root}/vae"
        assert rule.dest_for("wan_clipvision") == f"{root}/clip_vision"
        assert rule.dest_for("wan_lora") == f"{root}/loras"
        assert rule.dest_for("wan_preproc_pose") == f"{root}/onnx"

    def test_every_declared_host_declares_at_least_one_queue(self):
        """A host with no queue receives no work, so attributing weights to it
        would be a placement nobody can reach."""
        for host in ENGINE_HOSTS:
            assert host.queues, f"{host.container} declares no queue"

    def test_node_05_and_node_06_are_not_placement_targets(self):
        """Both are out of bounds (node-05 serves Qwen, node-06 is the sole
        CLIP scorer). Nothing must ever place weights on either."""
        assert {h.node_id for h in ENGINE_HOSTS}.isdisjoint({"node-05", "node-06"})


# ---------------------------------------------------------------------------
# the fetch core -- staging, verification, idempotency
# ---------------------------------------------------------------------------

class TestBundleFetchCore:
    def test_a_clean_fetch_places_every_file_and_verifies_the_digest(self, tmp_path):
        files = {"model.safetensors": b"weights" * 100, "sub/vae.pt": b"vae-bytes"}
        serving = FakeServing(files)
        result = serving.fetch("http://fake", "mid", "tok", tmp_path / "dest")

        assert result.digest_verified
        assert not result.skipped_present
        assert result.size_bytes == sum(len(v) for v in files.values())
        for name, data in files.items():
            assert (tmp_path / "dest" / name).read_bytes() == data

    def test_a_checksum_mismatch_is_a_hard_failure_that_leaves_nothing_behind(
        self, tmp_path
    ):
        """The named-error half of Task 2, and the staging half: a partial file
        is never left where a loader could find it."""
        files = {"good.bin": b"aaaa", "bad.bin": b"bbbb"}
        serving = FakeServing(files, corrupt="bad.bin")
        dest = tmp_path / "dest"

        with pytest.raises(ChecksumError) as exc:
            serving.fetch("http://fake", "mid", "tok", dest)
        assert "sha256 mismatch" in str(exc.value)

        # Nothing promoted, and no staging tree left on disk.
        assert not (dest / "bad.bin").exists()
        assert not (dest / "good.bin").exists()
        assert list(dest.glob(f"{_STAGING_PREFIX}*")) == []

    def test_a_second_fetch_of_a_verified_bundle_is_a_no_op_that_says_so(
        self, tmp_path
    ):
        files = {"model.safetensors": b"weights" * 100}
        serving = FakeServing(files)
        dest = tmp_path / "dest"

        first = serving.fetch("http://fake", "mid", "tok", dest)
        assert not first.skipped_present
        transferred = len(serving.file_requests)

        second = serving.fetch("http://fake", "mid", "tok", dest)
        assert second.skipped_present
        assert second.size_bytes == 0
        # Not re-downloaded: no additional file requests were made.
        assert len(serving.file_requests) == transferred

    def test_presence_is_decided_by_hash_not_by_existence(self, tmp_path):
        """A truncated or swapped file must not count as present -- that is
        exactly the state an interrupted pre-WP-65 fetch used to leave."""
        files = {"model.bin": b"the-real-bytes"}
        serving = FakeServing(files)
        dest = tmp_path / "dest"
        serving.fetch("http://fake", "mid", "tok", dest)

        (dest / "model.bin").write_bytes(b"truncated")
        assert not bundle_is_present(dest, serving.manifest["files"])

        second = serving.fetch("http://fake", "mid", "tok", dest)
        assert not second.skipped_present
        assert (dest / "model.bin").read_bytes() == b"the-real-bytes"

    def test_promotion_does_not_disturb_files_other_bundles_already_placed(
        self, tmp_path
    ):
        """The destination is a LIVE engine model directory holding other
        bundles' files, which is why promotion is file-granular rather than a
        directory rename."""
        dest = tmp_path / "dest"
        dest.mkdir()
        (dest / "someone-elses.safetensors").write_bytes(b"pre-existing")

        serving = FakeServing({"mine.bin": b"mine"})
        serving.fetch("http://fake", "mid", "tok", dest)

        assert (dest / "someone-elses.safetensors").read_bytes() == b"pre-existing"
        assert (dest / "mine.bin").read_bytes() == b"mine"

    def test_the_digest_form_matches_mbcps_reference_byte_for_byte(self):
        """If these two ever diverge, a bundle that verifies on one plane fails
        on the other. Recomputed here the way MBCP's consumer does."""
        entries = [
            {"logical_name": "b.bin", "sha256": "22"},
            {"logical_name": "a.bin", "sha256": "11"},
        ]
        expected = hashlib.sha256(
            json.dumps([["a.bin", "11"], ["b.bin", "22"]],
                       separators=(",", ":")).encode()
        ).hexdigest()
        assert compute_bundle_digest(entries) == expected

    def test_a_bad_manifest_signature_is_rejected(self):
        from shared.weights.bundle import SignatureError

        manifest = {"bundle_digest": "abc", "files": [], "signature": "wrong"}
        with pytest.raises(SignatureError):
            verify_signature(manifest, b"the-key")


# ---------------------------------------------------------------------------
# the service -- the refusal ladder, in order
# ---------------------------------------------------------------------------

class TestFetchServiceRefusals:
    def test_a_row_with_no_reference_refuses_before_touching_anything(self):
        outcome = fetch_model_weights(_Row(weights_ref=None), env={})
        assert not outcome.ok
        assert isinstance(outcome.error, NoWeightReferenceError)

    def test_an_engine_only_row_refuses_before_credentials_are_even_checked(self):
        """Order matters: an admin with no token must still be told the real
        reason, which is that there are no bytes -- not that a token is
        missing."""
        row = _Row(
            name="MimicMotion", engine="comfyui",
            weights_ref="http://serving-api:8000/engines/sha256:abc/manifest",
        )
        outcome = fetch_model_weights(row, env={})
        assert isinstance(outcome.error, EngineOnlyCertificationError)

    def test_an_unhosted_engine_refuses_before_credentials(self):
        row = _Row(engine="animatediff", weights_ref=_GOOD_REF)
        outcome = fetch_model_weights(row, env={})
        assert isinstance(outcome.error, NoHostForEngineError)

    def test_a_fetchable_hosted_row_without_the_token_names_the_env_var(self):
        row = _Row(engine="comfyui", stage="animation_generation",
                   weights_ref=_GOOD_REF, default_params={"family": "wan_animate"})
        outcome = fetch_model_weights(row, env=dict(_ON_NODE_03))
        assert isinstance(outcome.error, CredentialsUnavailableError)
        assert SERVING_TOKEN_ENV in str(outcome.error)

    def test_the_token_value_never_appears_in_the_outcome(self):
        """No secrets in a record, a log line or a report."""
        secret = "s3cr3t-serving-token-value"
        row = _Row(engine="animatediff", weights_ref=_GOOD_REF)
        outcome = fetch_model_weights(row, env={SERVING_TOKEN_ENV: secret})
        assert secret not in str(outcome.error)
        assert secret not in repr(outcome.plan)

    def test_a_verified_bundle_that_is_the_wrong_bundle_is_refused(self, tmp_path):
        """It verified against its OWN manifest and is still not this model's.
        Distinct from a checksum failure, and recorded as such."""
        serving = FakeServing({"m.bin": b"x"})
        row = _Row(
            engine="comfyui", stage="animation_generation",
            weights_ref=_GOOD_REF, weights_checksum="sha256:" + "0" * 64,
            default_params={"family": "wan_animate"},
        )
        def fetcher(url, model_id, token, dest, **kw):
            return serving.fetch(url, model_id, token, tmp_path / "dest", **kw)

        outcome = fetch_model_weights(
            row, fetcher=fetcher, env={SERVING_TOKEN_ENV: "tok", **_ON_NODE_03},
        )
        assert isinstance(outcome.error, DigestMismatchError)
        assert outcome.error.reason == "digest_mismatch"

    def test_a_transport_failure_becomes_a_named_verification_error(self):
        def boom(*a, **kw):
            raise FetchError("connection reset")

        row = _Row(engine="comfyui", stage="animation_generation",
                   weights_ref=_GOOD_REF, default_params={"family": "wan_animate"})
        outcome = fetch_model_weights(
            row, fetcher=boom, env={SERVING_TOKEN_ENV: "tok", **_ON_NODE_03},
        )
        assert isinstance(outcome.error, BundleVerificationError)

    def test_every_refusal_carries_a_distinct_stable_slug(self):
        """WP-65 Task 4 renders these; two states sharing a slug is exactly the
        conflation this package exists to remove."""
        from shared.weights import errors as e

        classes = [
            e.NoWeightReferenceError, e.EngineOnlyCertificationError,
            e.UnknownReferenceFormError, e.NoHostForEngineError,
            e.NoPlacementRuleError, e.CredentialsUnavailableError,
            e.BundleVerificationError, e.DigestMismatchError,
        ]
        slugs = [c.reason for c in classes]
        assert len(set(slugs)) == len(slugs)
        assert all(s != e.WeightFetchError.reason for s in slugs)


class TestFetchServiceSuccess:
    def _row(self):
        return _Row(
            name="wan2.2-animate", engine="comfyui", stage="animation_generation",
            weights_ref=_GOOD_REF, default_params={"family": "wan_animate"},
        )

    def test_a_plan_is_computable_offline_and_names_the_real_destination(self):
        plan = plan_fetch(self._row())
        assert plan.can_fetch
        assert plan.host.node_id == "node-03"
        assert plan.dest_dir == "/opt/models/comfyui-wan/models/diffusion_models"

    def test_the_full_cycle_fetches_verifies_places_and_reports(self, tmp_path):
        serving = FakeServing({"Wan22Animate/w.safetensors": b"bytes" * 50})
        row = self._row()
        row.weights_checksum = serving.manifest["bundle_digest"]

        # Placement is pinned into tmp for the test; the rule under test is
        # that the SERVICE consults the plan, not that it can write to /opt.
        captured = {}

        def fetcher(url, model_id, token, dest, **kw):
            captured["dest"] = dest
            return serving.fetch(url, model_id, token, tmp_path / "dest", **kw)

        outcome = fetch_model_weights(
            row, fetcher=fetcher, env={SERVING_TOKEN_ENV: "tok", **_ON_NODE_03},
        )
        assert outcome.ok, outcome.error
        assert captured["dest"] == "/opt/models/comfyui-wan/models/diffusion_models"
        assert outcome.result.digest_verified
        assert outcome.result.files == ["Wan22Animate/w.safetensors"]

    def test_a_second_run_reports_skipped_rather_than_refetching(self, tmp_path):
        serving = FakeServing({"w.safetensors": b"bytes" * 50})
        row = self._row()
        row.weights_checksum = serving.manifest["bundle_digest"]

        def fetcher(url, model_id, token, dest, **kw):
            return serving.fetch(url, model_id, token, tmp_path / "dest", **kw)

        first = fetch_model_weights(row, fetcher=fetcher,
                                    env={SERVING_TOKEN_ENV: "tok", **_ON_NODE_03})
        second = fetch_model_weights(row, fetcher=fetcher,
                                     env={SERVING_TOKEN_ENV: "tok", **_ON_NODE_03})
        assert first.ok and second.ok
        assert not first.skipped_present
        assert second.skipped_present

    def test_signature_verification_is_recorded_not_assumed(self, tmp_path):
        """Without the signing key the bundle is self-consistent but not proven
        to be MBCP's, and the record must say so rather than imply it."""
        serving = FakeServing({"w.bin": b"x"})
        row = self._row()
        row.weights_checksum = serving.manifest["bundle_digest"]

        def fetcher(url, model_id, token, dest, **kw):
            return serving.fetch(url, model_id, token, tmp_path / "d", **kw)

        outcome = fetch_model_weights(row, fetcher=fetcher,
                                      env={SERVING_TOKEN_ENV: "tok", **_ON_NODE_03})
        assert outcome.ok
        assert outcome.result.signature_verified is False


class TestPlacementIsRefusedOffTarget:
    """A fetch must run ON the node whose engine mounts the destination.

    Found while authoring this package's operator block, not by reading. The
    service resolves the animation family to
    ``/opt/models/comfyui-wan/models/diffusion_models`` on node-03 -- correct.
    But nothing stopped a process on node-01 from opening that path, creating
    it locally, verifying a real bundle into it and recording it as available.
    That is bytes in a directory no engine mounts, reported as present: the
    exact failure WP-65 exists to remove, reintroduced by the fix for it.
    """

    def _row(self):
        return _Row(
            name="wan2.2-animate", engine="comfyui", stage="animation_generation",
            weights_ref=_GOOD_REF, default_params={"family": "wan_animate"},
        )

    def test_a_fetch_from_the_wrong_node_is_refused_by_name(self):
        outcome = fetch_model_weights(
            self._row(), env={SERVING_TOKEN_ENV: "tok", NODE_HOSTNAME_ENV: "node-01"},
        )
        assert isinstance(outcome.error, PlacementNotLocalError)
        assert outcome.error.reason == "placement_not_local"
        assert "node-03" in str(outcome.error)
        assert "Run the fetch on node-03" in str(outcome.error)

    def test_a_host_that_declares_no_node_name_fails_closed(self):
        """An unknown host is not the target. Fail closed, never open."""
        outcome = fetch_model_weights(
            self._row(), env={SERVING_TOKEN_ENV: "tok"},
        )
        assert isinstance(outcome.error, PlacementNotLocalError)
        assert NODE_HOSTNAME_ENV in str(outcome.error)

    def test_the_refusal_comes_before_the_network_is_touched(self):
        def boom(*a, **kw):
            raise AssertionError("the fetcher must not be called off-target")

        outcome = fetch_model_weights(
            self._row(), fetcher=boom,
            env={SERVING_TOKEN_ENV: "tok", NODE_HOSTNAME_ENV: "node-01"},
        )
        assert isinstance(outcome.error, PlacementNotLocalError)

    def test_on_the_right_node_it_proceeds(self, tmp_path):
        serving = FakeServing({"w.bin": b"x"})
        row = self._row()
        row.weights_checksum = serving.manifest["bundle_digest"]

        def fetcher(url, model_id, token, dest, **kw):
            return serving.fetch(url, model_id, token, tmp_path / "d", **kw)

        outcome = fetch_model_weights(
            row, fetcher=fetcher,
            env={SERVING_TOKEN_ENV: "tok", NODE_HOSTNAME_ENV: "node-03"},
        )
        assert outcome.ok, outcome.error

    def test_the_surface_does_not_blame_the_model_for_a_local_limitation(self):
        """`placement_not_local` is about WHERE the request was made, so the
        model still reads as "certified, not fetched" rather than as broken."""
        from app.services.weight_placement import _REASON_TO_STATE, STATE_NOT_FETCHED

        assert _REASON_TO_STATE["placement_not_local"] == STATE_NOT_FETCHED


class TestTheSurfaceDoesNotOverclaimAbsence:
    """WP-57/60's rule, applied to the one label that nearly broke it.

    "certified, weights not fetched" is a claim about the NODE. IVGS can only
    honestly make a claim about its own RECORDS: measured 2026-08-26,
    wan2.2-animate's bytes are on node-03 -- its engine enumerates
    Wan22Animate/Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors -- and no
    placement row exists, because the operator's CLI placed them before this
    table did.
    """

    def test_the_not_fetched_label_is_about_records_not_about_the_disk(self):
        from app.services.weight_placement import _STATE_LABEL, STATE_NOT_FETCHED

        label = _STATE_LABEL[STATE_NOT_FETCHED]
        assert "recorded" in label
        assert "not fetched" not in label, (
            "this label is rendered for a model whose bytes may well be on the "
            "node; it must not assert they are absent"
        )
