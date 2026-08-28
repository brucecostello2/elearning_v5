"""WP-IVGS-09 Task 1 — the renderer service.

WHAT THESE TESTS ARE FOR, AND WHAT THEY DELIBERATELY DO NOT RE-TEST.

The templates and the rasteriser are WP-68's, and `ivgs-api/tests/test_wp68_motion.py`
already proves 50 things about them — including that the arithmetic is right,
which is the one property no pipeline gate can catch. **None of that is repeated
here.** Duplicating it would create a second opinion about what a template means,
free to drift from the first, which is exactly the reason the brief says *"the
Pillow reference implementation IS the renderer; do not reimplement it"*.

What is new, and therefore what is tested here, is the SERVICE: the wire it
accepts, the determinism it claims in a header, and — the half that matters most
— that every failure path names its cause and returns no picture.

WHY THE MODULE IS LOADED BY PATH.

`ivgs-scheduler` is already on `pythonpath` and ships its own `main.py`, so a
bare `import main` here would resolve to the scheduler's app roughly half the
time depending on collection order. Rather than add `ivgs-motion-renderer` to
`pythonpath` and make that a coin-toss, the file is loaded by explicit location.
`ivgs-motion-renderer` is NOT on `pythonpath` for that reason and adding it
would reintroduce the collision.
"""
from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_ROOT = Path(__file__).resolve().parents[2]
_MAIN = _ROOT / "ivgs-motion-renderer" / "main.py"

# `shared` lives at the repo root and is copied into the image as /app/shared.
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_spec = importlib.util.spec_from_file_location("ivgs_motion_renderer_main", _MAIN)
assert _spec and _spec.loader
renderer = importlib.util.module_from_spec(_spec)
sys.modules["ivgs_motion_renderer_main"] = renderer
_spec.loader.exec_module(renderer)

client = TestClient(renderer.app, raise_server_exceptions=False)

#: One real invocation, exactly as WP-68 §5.1 measured a scene storing it.
SCENE_PARAMS = {"template": "place_value_split", "number": 23}


class TestHealthzSaysWhatThisBuildIs:
    """`/healthz` reports build ref and template inventory — the brief's words."""

    def test_it_reports_a_build_ref(self):
        body = client.get("/healthz").json()
        assert "build_ref" in body
        assert "build_sha" in body

    def test_it_reports_the_template_inventory(self):
        from shared.motion.templates import template_names

        body = client.get("/healthz").json()
        assert set(body["templates"]) == set(template_names())
        assert body["template_count"] == len(template_names())

    def test_it_names_the_font_it_will_actually_draw_with(self):
        """A missing font is the one failure that leaves a service that looks
        fine and cannot render. An operator must be able to see it here."""
        font = client.get("/healthz").json()["font"]
        assert font["in_use"], "no pinned font is present"
        assert font["in_use"].endswith(".ttf")
        assert len(font["sha256"]) == 64

    def test_the_vendored_font_is_the_one_in_use_not_a_system_one(self):
        """The whole point of vendoring. If this starts passing through a
        system path, determinism has gone back to depending on what happens to
        be installed."""
        in_use = client.get("/healthz").json()["font"]["in_use"]
        assert in_use.startswith(str(_ROOT / "shared" / "motion" / "fonts")), in_use

    def test_it_declares_the_wp67_contract_it_serves(self):
        """Read from the registry, not restated here.

        The service must accept exactly the parameter set the Model Store shows
        operators for `maths_motion`. Hard-coding the list in this test would
        let the two drift apart while both looked right."""
        from shared.providers.client_registry import (
            contract_for,
            register_builtin_clients,
        )

        register_builtin_clients()
        contract = contract_for("animation_generation", "motion_graphics", "maths_motion")
        assert contract is not None, "WP-67 registers maths_motion; it is gone"

        body = client.get("/healthz").json()
        assert set(body["accepts_params"]) == set(contract.accepts_params)
        assert body["produces"] == contract.produces == "video/mp4"


class TestTheWireIsTheScenesOwnParameters:
    """Measured before it was designed: a `motion_graphics` scene stores a FLAT
    object, `template` plus that template's parameters (WP-68 §5.1)."""

    def test_the_flat_scene_object_is_accepted_unwrapped(self):
        r = client.post("/frame", json=SCENE_PARAMS)
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "image/png"

    def test_templates_lists_every_template_with_what_it_teaches(self):
        body = client.get("/templates").json()["templates"]
        assert {t["name"] for t in body} == {
            "column_multiplication_step", "place_value_split",
            "column_addition_carry", "highlight_and_hold",
        }
        for t in body:
            assert t["params"], t["name"]
            assert t["describes"], t["name"]


class TestDeterminism:
    """The property that makes this worth deploying at all."""

    def test_the_same_request_twice_gives_byte_identical_frames(self):
        a = client.post("/frame", json=SCENE_PARAMS)
        b = client.post("/frame", json=SCENE_PARAMS)
        assert a.status_code == b.status_code == 200
        assert a.content == b.content
        assert a.headers["X-IVGS-Frame-Digest"] == b.headers["X-IVGS-Frame-Digest"]

    @pytest.mark.parametrize("index", [0, 7, 40])
    def test_it_holds_across_the_template_not_just_frame_zero(self, index):
        a = client.post("/frame", json=SCENE_PARAMS, params={"index": index})
        b = client.post("/frame", json=SCENE_PARAMS, params={"index": index})
        assert a.status_code == 200, a.text
        assert a.content == b.content

    def test_different_parameters_give_different_bytes(self):
        """The other half. A renderer that returned the same bytes for every
        request would pass the test above perfectly."""
        a = client.post("/frame", json={"template": "place_value_split", "number": 23})
        b = client.post("/frame", json={"template": "place_value_split", "number": 47})
        assert a.content != b.content

    def test_the_frames_digest_is_over_frames_not_over_the_container(self):
        """So an ffmpeg upgrade does not look like a template change."""
        from shared.motion.raster import render_digest
        from shared.motion.templates import render

        r = client.post("/frame", json=SCENE_PARAMS)
        # The /frame digest is per-frame; the /render digest is the whole
        # sequence. Both come from the rasteriser, neither from the encoder.
        assert r.headers["X-IVGS-Frame-Digest"] != render_digest(render("place_value_split", number=23))


class TestEveryFailureIsNamedAndReturnsNoPicture:
    """The half that matters most. A picture that is not the requested render
    is worse than no picture, because nothing downstream can tell."""

    def test_an_unknown_template_is_refused_by_name_and_lists_the_real_ones(self):
        r = client.post("/frame", json={"template": "no_such_template"})
        assert r.status_code == 400
        detail = r.json()["detail"]
        assert "no_such_template" in detail
        assert "place_value_split" in detail
        assert r.headers["content-type"].startswith("application/json")

    def test_a_missing_template_key_is_refused(self):
        r = client.post("/frame", json={"number": 23})
        assert r.status_code == 400
        assert "template" in r.json()["detail"]

    def test_a_parameter_outside_the_wp67_contract_is_refused_not_ignored(self):
        """Ignoring it would render a picture that does not show what was asked
        for, and nothing would say so."""
        r = client.post(
            "/frame", json={"template": "place_value_split", "number": 23, "colour": "red"},
        )
        assert r.status_code == 400
        assert "colour" in r.json()["detail"]

    def test_a_parameter_the_template_does_not_take_is_refused(self):
        r = client.post(
            "/frame", json={"template": "place_value_split", "number": 23, "step": 1},
        )
        assert r.status_code == 400
        assert "step" in r.json()["detail"]

    def test_a_frame_index_past_the_end_is_refused_not_clamped(self):
        """Clamping would answer a caller's bug with a plausible-looking frame."""
        r = client.post("/frame", json=SCENE_PARAMS, params={"index": 100000})
        assert r.status_code == 400
        assert "100000" in r.json()["detail"]

    def test_a_non_object_body_is_refused(self):
        r = client.post("/frame", json=["place_value_split"])
        assert r.status_code in (400, 422)

    def test_no_font_means_a_named_503_and_no_frame(self, monkeypatch):
        """The determinism guarantee, working. A renderer that substituted a
        font here would return a picture drawn in the wrong face and call it
        the template."""
        from shared.motion import raster

        monkeypatch.setattr(raster, "FONT_PATH", "/nonexistent-a.ttf")
        monkeypatch.setattr(raster, "FONT_FALLBACK", "/nonexistent-b.ttf")
        r = client.post("/frame", json=SCENE_PARAMS)
        assert r.status_code == 503
        assert "not deterministic" in r.json()["detail"]
        assert not r.content.startswith(b"\x89PNG")

    def test_no_font_also_degrades_healthz_rather_than_reporting_ok(self, monkeypatch):
        """A green light on a service that cannot render is the false-green
        defect. It is not being reintroduced here."""
        from shared.motion import raster

        monkeypatch.setattr(raster, "FONT_PATH", "/nonexistent-a.ttf")
        monkeypatch.setattr(raster, "FONT_FALLBACK", "/nonexistent-b.ttf")
        r = client.get("/healthz")
        assert r.status_code == 503
        assert r.json()["status"] == "degraded"

    def test_no_ffmpeg_means_a_named_502_and_no_video(self, monkeypatch):
        monkeypatch.setattr(renderer, "FFMPEG", "/nonexistent-ffmpeg")
        r = client.post("/render", json=SCENE_PARAMS)
        assert r.status_code == 502
        assert "ffmpeg" in r.json()["detail"]


class TestTheEncoderPathItself:
    """⛔ THESE EXIST BECAUSE THE SUITE MISSED A REAL DEFECT.

    Before 2026-08-28 the only `/render` test was the "no ffmpeg" refusal, so
    23 green tests coexisted with an encoder that could not encode: the command
    wrote the MP4 to `/dev/stdout`, and the MP4 muxer refuses a non-seekable
    target (`muxer does not support non seekable output`). It was found by the
    first live curl, not by pytest. A test that only exercises the failure path
    proves the failure path.
    """

    def test_the_encoder_never_writes_an_mp4_to_a_non_seekable_target(self):
        """Structural, so it runs everywhere --- including where ffmpeg is not
        installed, which is the host this suite usually runs on.

        The MP4 muxer rewrites its header after the last frame and `+faststart`
        then relocates the `moov` atom. Both seek. A pipe cannot."""
        cmd = renderer.encode_cmd(30, "/tmp/some-real-file.mp4")
        target = cmd[-1]
        assert not target.startswith("/dev/"), (
            f"the encoder targets {target!r}; the MP4 muxer cannot write to a "
            f"pipe --- it must be given a real, seekable file"
        )
        assert target.endswith(".mp4")
        # `+faststart` is the other half: it relocates the `moov` atom after the
        # encode, which also seeks. Keeping it is what makes the artifact
        # playable without reading the whole file first.
        assert "+faststart" in cmd
        source = _MAIN.read_text()
        assert "tempfile.NamedTemporaryFile" in source
        assert "os.unlink(out_path)" in source, "the temp file must be removed"

    @pytest.mark.skipif(
        shutil.which("ffmpeg") is None,
        reason="ffmpeg is not installed on this host; it IS in the renderer image",
    )
    def test_a_real_encode_produces_a_real_mp4(self):
        r = client.post("/render", json=SCENE_PARAMS)
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "video/mp4"
        # `ftyp` box at offset 4 --- this is an MP4, not an error page.
        assert r.content[4:8] == b"ftyp", r.content[:32]
        assert int(r.headers["X-IVGS-Frames"]) > 0
        assert len(r.headers["X-IVGS-Frames-Digest"]) == 64

    @pytest.mark.skipif(
        shutil.which("ffmpeg") is None,
        reason="ffmpeg is not installed on this host; it IS in the renderer image",
    )
    def test_the_same_request_twice_gives_the_same_file(self):
        """`+bitexact` and `-map_metadata -1` keep the encoder version and the
        creation timestamp out of the container."""
        a = client.post("/render", json=SCENE_PARAMS)
        b = client.post("/render", json=SCENE_PARAMS)
        assert a.content == b.content


class TestThisModuleDrawsNothingItself:
    """The brief's constraint, asserted rather than trusted: *the Pillow
    reference implementation IS the renderer; do not reimplement it*. A second
    implementation would be a second answer to what a template looks like."""

    def test_it_imports_the_reference_rasteriser_and_defines_no_drawing_of_its_own(self):
        source = _MAIN.read_text()
        assert "from shared.motion import raster" in source
        for forbidden in ("ImageDraw", "ImageFont", "Image.new", "draw.text", "draw.line"):
            assert forbidden not in source, (
                f"{forbidden!r} appears in the service — drawing belongs in "
                f"shared/motion/raster.py, which is the definition of what a "
                f"drawing op means"
            )
