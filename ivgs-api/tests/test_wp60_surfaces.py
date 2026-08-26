"""
WP-60 — the component layer stops asserting what it does not know.

Every test here pins an ABSENCE. The defects this package closed all had the
same shape: a field nothing measures, given a default at the last moment, and
rendered as a measurement. Pinning the absence is the only thing that stops the
default coming back, because a default always makes the tests that assert on
"some number" pass.
"""
from __future__ import annotations

import pytest

from app.schemas.gpu import GpuNodeResponse
from app.schemas.project import ProjectResponse
from app.services import scheduler_fleet


class TestGpuTelemetryIsNullableNotZero:
    """WP-60 Task 2(a).

    `GpuNodeResponse` declared `temperature_c: float = 0.0` and
    `power_draw_w: float = 0.0`, and `to_node_view` set neither — so the
    pydantic defaults supplied them and the GPU Fleet card printed "0 C / 0 W"
    for every node. That is the same defect WP-24 removed from `/api/v1/nodes`,
    reappearing on the route next door.
    """

    def test_absent_temperature_is_none_not_zero(self):
        node = scheduler_fleet.to_node_view(
            {
                "node_id": "node-02:gpu0",
                "gpu_index": 0,
                "gpu_model": "NVIDIA RTX PRO 6000 Blackwell Workstation Edition",
                "total_vram_mb": 97887,
                "used_vram_mb": 0,
                "is_alive": True,
                "is_draining": False,
                "last_heartbeat": "2026-08-26T03:00:48.604107+00:00",
            }
        )
        assert node["temperature_c"] is None
        assert node["power_draw_w"] is None
        assert node["gpu_utilization_pct"] is None

    def test_a_real_reading_survives_the_mapping(self):
        node = scheduler_fleet.to_node_view(
            {
                "node_id": "node-04:gpu0",
                "gpu_index": 0,
                "total_vram_mb": 97887,
                "used_vram_mb": 16384,
                "gpu_utilization_pct": 73.5,
                "gpu_temperature_c": 61.0,
                "gpu_power_draw_w": 310.0,
                "is_alive": True,
                "is_draining": False,
            }
        )
        assert node["gpu_utilization_pct"] == pytest.approx(73.5)
        assert node["temperature_c"] == pytest.approx(61.0)
        assert node["power_draw_w"] == pytest.approx(310.0)

    def test_a_genuine_zero_reading_is_kept_as_a_reading(self):
        """A measured 0% is a measurement and must not become None."""
        node = scheduler_fleet.to_node_view(
            {
                "node_id": "node-03:gpu0",
                "gpu_index": 0,
                "total_vram_mb": 97887,
                "used_vram_mb": 0,
                "gpu_utilization_pct": 0.0,
                "gpu_temperature_c": 0.0,
                "is_alive": True,
                "is_draining": False,
            }
        )
        assert node["gpu_utilization_pct"] == 0.0
        assert node["temperature_c"] == 0.0

    def test_the_schema_default_is_none(self):
        """The last line of defence: even a view that forgets the key cannot
        produce a zero reading."""
        node = GpuNodeResponse(
            id="00000000-0000-0000-0000-000000000001",
            node_hostname="node-02",
            gpu_index=0,
            status="online",
            registered_at="2026-08-26T03:00:00+00:00",
        )
        assert node.temperature_c is None
        assert node.power_draw_w is None
        assert node.gpu_utilization_pct is None


class TestReservedVramIsNamedForWhatItIs:
    """WP-60 Task 2(b).

    `used_vram_mb` is reservation accounting: seeded to 0 at registration and
    moved only by the scheduler. It was labelled "VRAM" on the GPU Fleet page
    while Node Monitor, reading Prometheus, showed the physical figure for the
    same machine — 0.0 GB against 86.4 GB, both true, neither labelled.
    """

    def test_reserved_mirrors_used_under_its_true_name(self):
        node = scheduler_fleet.to_node_view(
            {
                "node_id": "node-04:gpu0",
                "gpu_index": 0,
                "total_vram_mb": 97887,
                "used_vram_mb": 16384,
                "is_alive": True,
                "is_draining": False,
            }
        )
        assert node["reserved_vram_mb"] == 16384
        assert node["used_vram_mb"] == node["reserved_vram_mb"]
        assert node["available_vram_mb"] == 97887 - 16384


class TestThumbnailReasonIsPresentWhenThereIsNoThumbnail:
    """WP-60 Task 4.

    Two gallery cards read "Preview failed to load" permanently. The loader was
    fine: `thumbnail_asset_id` pointed at a `final_render`, every one of which
    is an mp4, and `/assets/{id}/thumbnail` answers 415 for anything that is not
    an image. A permanent property of the asset was being reported as a
    transport failure.
    """

    def test_reason_and_id_are_mutually_exclusive(self):
        with_id = ProjectResponse(
            id="00000000-0000-0000-0000-000000000001",
            name="p",
            state="DRAFT",
            created_at="2026-08-26T00:00:00+00:00",
            updated_at="2026-08-26T00:00:00+00:00",
            thumbnail_asset_id="00000000-0000-0000-0000-000000000002",
        )
        assert with_id.thumbnail_unavailable_reason is None

        without = ProjectResponse(
            id="00000000-0000-0000-0000-000000000001",
            name="p",
            state="DRAFT",
            created_at="2026-08-26T00:00:00+00:00",
            updated_at="2026-08-26T00:00:00+00:00",
            thumbnail_unavailable_reason="No render yet.",
        )
        assert without.thumbnail_asset_id is None
        assert without.thumbnail_unavailable_reason
