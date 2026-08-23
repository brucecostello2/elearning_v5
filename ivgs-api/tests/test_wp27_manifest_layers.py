"""
WP-27 / swallow-register instance 15 — the manifest builder must not bind every
scene asset as a background layer.

Each test names the pre-fix behaviour it catches. The pre-fix mapping is
reproduced verbatim in `_PREFIX_MAPPING` and exercised in
`TestTheDefectIsReal`, so these tests are demonstrably not vacuous.

Hermetic: pure functions and a replica of the layer-assembly loop. No DB.
"""
import pytest

from app.api.v1.manifests import (
    _ASSET_TYPE_TO_LAYER,
    _ASSET_TYPES_NOT_LAYERS,
    _asset_type_to_layer,
)

# The real enum, verified 2026-08-23 against the live database:
#   SELECT unnest(enum_range(NULL::asset_type))
REAL_ASSET_TYPES = [
    "image", "video", "audio", "document",
    "talking_head", "final_render", "reference_clip",
]

# manifests.py:369-380 as it stood at 01a35ed, before this package.
_PREFIX_MAPPING = {
    "scene_image": "background",
    "video_clip": "background",
    "animation": "background",
    "tts_audio": "audio",
    "talking_head": "talking_head",
    "caption_srt": "captions",
    "caption_vtt": "captions",
    "lower_third": "lower_third",
}


def _prefix_asset_type_to_layer(asset_type: str) -> str:
    """The pre-fix function, including its `"background"` default."""
    return _PREFIX_MAPPING.get(asset_type, "background")


class TestTheDefectIsReal:
    """Proof that the pre-fix code produced the register's observed symptom."""

    def test_prefix_mapping_missed_all_but_one_real_asset_type(self):
        missed = [t for t in REAL_ASSET_TYPES if t not in _PREFIX_MAPPING]
        assert missed == [
            "image", "video", "audio", "document", "final_render", "reference_clip",
        ]
        assert [t for t in REAL_ASSET_TYPES if t in _PREFIX_MAPPING] == ["talking_head"]

    def test_prefix_typed_audio_and_documents_as_background(self):
        """This is the exact symptom recorded in instance 15: ffmpeg received a
        WAV as the scene background."""
        for offending in ("audio", "document", "reference_clip", "final_render"):
            assert _prefix_asset_type_to_layer(offending) == "background"

    def test_fixed_mapping_does_not(self):
        """Same inputs, current code: none of them becomes a background."""
        for offending in ("document", "reference_clip", "final_render"):
            assert _asset_type_to_layer(offending) is None
        assert _asset_type_to_layer("audio") == "audio"


class TestAssetTypeMapping:
    def test_mapping_keys_are_all_real_enum_values(self):
        """The pre-fix mapping was keyed on names this schema has never used."""
        for key in _ASSET_TYPE_TO_LAYER:
            assert key in REAL_ASSET_TYPES, f"{key!r} is not an asset_type"

    def test_only_visual_types_are_backgrounds(self):
        backgrounds = {
            k for k, v in _ASSET_TYPE_TO_LAYER.items() if v == "background"
        }
        assert backgrounds == {"image", "video"}

    def test_unmapped_type_is_excluded_not_defaulted_to_background(self):
        """The single most damaging line in the pre-fix code was
        `mapping.get(asset_type, "background")`."""
        assert _asset_type_to_layer("something_new_in_the_enum") is None
        assert _asset_type_to_layer("") is None

    def test_non_layer_types_are_declared_and_excluded(self):
        for t in _ASSET_TYPES_NOT_LAYERS:
            assert t in REAL_ASSET_TYPES
            assert _asset_type_to_layer(t) is None

    def test_every_real_enum_value_is_accounted_for(self):
        """Either it maps to a layer, or it is explicitly declared not-a-layer.
        Nothing is left to a default."""
        for t in REAL_ASSET_TYPES:
            mapped = t in _ASSET_TYPE_TO_LAYER
            declared_not = t in _ASSET_TYPES_NOT_LAYERS
            assert mapped != declared_not, f"{t!r} is unclassified or double-classified"


class _Asset:
    """Stand-in for the SQL row: the loop reads these five attributes."""
    def __init__(self, asset_id, asset_type, fid="fid", content_hash="h"):
        self.id = asset_id
        self.asset_type = asset_type
        self.seaweedfs_fid = fid
        self.content_hash = content_hash


def _build_layers(scene_assets):
    """Replica of the fixed layer-assembly loop in generate_manifest.

    Kept in step with manifests.py by TestAssetTypeMapping above, which pins the
    mapping this depends on.
    """
    latest_by_layer = {}
    for asset in scene_assets:
        layer_type = _asset_type_to_layer(asset.asset_type)
        if layer_type is None:
            continue
        latest_by_layer[layer_type] = {
            "layer_type": layer_type,
            "asset_id": str(asset.id),
        }
    return [latest_by_layer[k] for k in sorted(latest_by_layer)]


def _build_layers_prefix(scene_assets):
    """Replica of the PRE-FIX loop, for contrast."""
    return [
        {"layer_type": _prefix_asset_type_to_layer(a.asset_type), "asset_id": str(a.id)}
        for a in scene_assets
    ]


class TestLayerAssembly:
    # The register's captured scene 0: two audio and two images, in that order,
    # every one of them emitted as layer_type "background".
    OBSERVED_SCENE = [
        _Asset("d83c6ac7", "audio"),
        _Asset("be4453e8", "audio"),
        _Asset("7de1b630", "image"),
        _Asset("ca6d7f83", "image"),
    ]

    def test_prefix_produced_four_background_layers(self):
        """Reproduces job 7980c0b9 scene 0 exactly."""
        layers = _build_layers_prefix(self.OBSERVED_SCENE)
        assert len(layers) == 4
        assert [l["layer_type"] for l in layers] == ["background"] * 4
        # And the first input - the one ffmpeg treats as the background - is a WAV.
        assert layers[0]["asset_id"] == "d83c6ac7"

    def test_same_scene_now_yields_one_background_and_one_audio(self):
        layers = _build_layers(self.OBSERVED_SCENE)
        assert [l["layer_type"] for l in layers] == ["audio", "background"]
        assert len(layers) == 2

    def test_dedupe_keeps_the_latest_of_each_layer_type(self):
        """Assets arrive ordered created_at ASC, so the last one wins."""
        layers = _build_layers(self.OBSERVED_SCENE)
        by_type = {l["layer_type"]: l["asset_id"] for l in layers}
        assert by_type["background"] == "ca6d7f83"   # the later image
        assert by_type["audio"] == "be4453e8"        # the later audio

    def test_documents_and_reference_clips_never_reach_the_timeline(self):
        scene = [
            _Asset("doc1", "document"),
            _Asset("clip1", "reference_clip"),
            _Asset("fin1", "final_render"),
            _Asset("img1", "image"),
        ]
        layers = _build_layers(scene)
        assert [l["layer_type"] for l in layers] == ["background"]
        assert layers[0]["asset_id"] == "img1"

    def test_scene_with_only_audio_produces_no_background(self):
        """The separate media-generation gap the register notes. It must be
        detectable, not silently absent."""
        layers = _build_layers([_Asset("a1", "audio"), _Asset("a2", "audio")])
        assert [l["layer_type"] for l in layers] == ["audio"]
        assert not any(l["layer_type"] == "background" for l in layers)

    def test_empty_scene_yields_no_layers(self):
        assert _build_layers([]) == []
