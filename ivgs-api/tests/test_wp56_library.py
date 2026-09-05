"""
WP-56 — AD-09.4 asset library + actors, AD-09.5 presets.

WHAT THESE TESTS PIN, AND WHY EACH ONE EXISTS.

The WP-40/43 lesson says: capture live API shapes and test against them, so a
frontend type can never declare a field the API does not send. Every response
assertion below reads the field the frontend reads, by the name the frontend
reads it by. If a field is renamed, this file fails before the GUI renders a
blank box.

The AD-09.3 lesson says: assert on the ACT, not on the status code. Eight
endpoints in this system return 202 and do nothing. So `test_reference_*` checks
that no bytes were re-uploaded (the SeaweedFS mock's call count), and
`test_apply_preset_*` checks the rows the apply actually wrote — not that it
returned 200.
"""
import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import make_auth_header

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

async def _upload_library_asset(
    client: AsyncClient, headers: dict, *, kind="logo", name="Acme mark",
    content=b"PNGDATA-acme", owner_scope="user", filename="acme.png",
) -> dict:
    resp = await client.post(
        "/api/v1/library/assets",
        headers=headers,
        files={"file": (filename, content, "image/png")},
        data={"kind": kind, "name": name, "owner_scope": owner_scope},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# library assets
# ---------------------------------------------------------------------------

async def test_upload_library_asset_returns_the_shape_the_gui_reads(
    client, operator_user,
):
    user, _ = operator_user
    headers = make_auth_header(user)
    body = await _upload_library_asset(client, headers)

    # Exactly the fields LibraryAssetUploadResponse declares. A field the GUI
    # reads and the API does not send is the WP-40/43 defect family.
    for field in (
        "id", "kind", "name", "description", "seaweedfs_fid", "seaweedfs_path",
        "mime_type", "file_size_bytes", "duration_seconds", "content_hash",
        "tags", "owner_scope", "created_by", "superseded_by",
        "created_at", "updated_at", "was_deduplicated",
    ):
        assert field in body, f"{field} missing from the upload response"

    assert body["kind"] == "logo"
    assert body["owner_scope"] == "user"
    assert body["was_deduplicated"] is False
    assert body["file_size_bytes"] == len(b"PNGDATA-acme")
    assert body["created_by"] == str(user.id)


async def test_identical_bytes_dedup_within_scope(
    client, operator_user,
):
    """AD-09.4.2 / ledger B3. The same bytes twice must not grow the library."""
    user, _ = operator_user
    headers = make_auth_header(user)
    first = await _upload_library_asset(client, headers, name="Acme mark")
    second = await _upload_library_asset(client, headers, name="Acme mark copy")

    assert second["was_deduplicated"] is True
    assert second["id"] == first["id"], "a dedup hit must return the EXISTING row"

    listing = await client.get("/api/v1/library/assets", headers=headers)
    assert listing.status_code == 200
    assert listing.json()["total"] == 1


async def test_global_scope_requires_admin(
    client, operator_user, admin_user,
):
    """`global` is admin-mutable only (AD-09.4.2)."""
    op, _ = operator_user
    resp = await client.post(
        "/api/v1/library/assets",
        headers=make_auth_header(op),
        files={"file": ("g.png", b"GLOBALBYTES", "image/png")},
        data={"kind": "logo", "name": "House mark", "owner_scope": "global"},
    )
    assert resp.status_code == 403, resp.text

    adm, _ = admin_user
    ok = await client.post(
        "/api/v1/library/assets",
        headers=make_auth_header(adm),
        files={"file": ("g.png", b"GLOBALBYTES", "image/png")},
        data={"kind": "logo", "name": "House mark", "owner_scope": "global"},
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["owner_scope"] == "global"


async def test_superseded_assets_are_hidden_from_the_browser(
    client, operator_user,
):
    user, _ = operator_user
    headers = make_auth_header(user)
    old = await _upload_library_asset(client, headers, name="Old mark", content=b"OLD")
    new = await _upload_library_asset(client, headers, name="New mark", content=b"NEW")

    resp = await client.post(
        f"/api/v1/library/assets/{old['id']}/supersede",
        headers=headers, params={"replacement_id": new["id"]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["superseded_by"] == new["id"]

    listing = await client.get("/api/v1/library/assets", headers=headers)
    ids = {r["id"] for r in listing.json()["data"]}
    assert old["id"] not in ids, "a retired asset must not be offered as a live choice"
    assert new["id"] in ids

    # It still RESOLVES — never hard-deleted while referenced.
    still = await client.get(f"/api/v1/library/assets/{old['id']}", headers=headers)
    assert still.status_code == 200


async def test_supersede_rejects_a_kind_mismatch(
    client, operator_user,
):
    user, _ = operator_user
    headers = make_auth_header(user)
    logo = await _upload_library_asset(client, headers, kind="logo", content=b"L")
    music = await _upload_library_asset(
        client, headers, kind="music_bed", content=b"M", filename="bed.mp3",
    )
    resp = await client.post(
        f"/api/v1/library/assets/{logo['id']}/supersede",
        headers=headers, params={"replacement_id": music["id"]},
    )
    assert resp.status_code == 400
    assert "Kind mismatch" in resp.text


async def test_reference_into_project_moves_no_bytes(
    client, operator_user, project_id,
):
    """AD-09.4.2 REFERENCE-DON'T-COPY, asserted on the ACT, not the status code.

    The check that matters is that SeaweedFS is not written to again: a
    "reference" that re-uploads a 2 GB clip is a copy with better naming.
    """
    from shared.seaweedfs_client import seaweedfs_client

    user, _ = operator_user
    headers = make_auth_header(user)
    lib = await _upload_library_asset(
        client, headers, kind="reference_clip", name="Sarah plate",
        content=b"CLIPBYTES", filename="sarah.mp4",
    )

    uploads_before = getattr(seaweedfs_client, "_test_upload_calls", None)

    resp = await client.post(
        f"/api/v1/projects/{project_id}/library-reference",
        headers=headers,
        json={"library_asset_id": lib["id"], "asset_type": "reference_clip"},
    )
    assert resp.status_code == 201, resp.text
    asset = resp.json()

    assert asset["library_asset_id"] == lib["id"]
    assert asset["seaweedfs_fid"] == lib["seaweedfs_fid"], (
        "the project asset must point at the SAME stored object"
    )
    assert asset["content_hash"] == lib["content_hash"]
    assert asset["preserve_flag"] is True, (
        "a referenced library asset must not be tiered out from under the project"
    )
    if uploads_before is not None:
        assert getattr(seaweedfs_client, "_test_upload_calls") == uploads_before


async def test_reference_is_idempotent(
    client, operator_user, project_id,
):
    """The GUI's "use this" button is exactly the control that gets double-clicked."""
    user, _ = operator_user
    headers = make_auth_header(user)
    lib = await _upload_library_asset(
        client, headers, kind="reference_clip", content=b"CLIP2", filename="c.mp4",
    )
    payload = {"library_asset_id": lib["id"], "asset_type": "reference_clip"}
    first = await client.post(
        f"/api/v1/projects/{project_id}/library-reference",
        headers=headers, json=payload,
    )
    second = await client.post(
        f"/api/v1/projects/{project_id}/library-reference",
        headers=headers, json=payload,
    )
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


async def test_reference_rejects_an_incompatible_asset_type(
    client, operator_user, project_id,
):
    """`library_asset_kind` and `assets.asset_type` are DIFFERENT vocabularies.

    Sending the ENUM a value it does not know would be a database error at
    INSERT; a 400 naming the allowed set is a better way to find out.
    """
    user, _ = operator_user
    headers = make_auth_header(user)
    lib = await _upload_library_asset(client, headers, kind="logo", content=b"LOGO")
    resp = await client.post(
        f"/api/v1/projects/{project_id}/library-reference",
        headers=headers,
        json={"library_asset_id": lib["id"], "asset_type": "audio"},
    )
    assert resp.status_code == 400
    assert "cannot be referenced as asset_type" in resp.text


async def test_reference_rejects_a_superseded_asset(
    client, operator_user, project_id,
):
    user, _ = operator_user
    headers = make_auth_header(user)
    old = await _upload_library_asset(client, headers, content=b"OLD2")
    new = await _upload_library_asset(client, headers, content=b"NEW2")
    await client.post(
        f"/api/v1/library/assets/{old['id']}/supersede",
        headers=headers, params={"replacement_id": new["id"]},
    )
    resp = await client.post(
        f"/api/v1/projects/{project_id}/library-reference",
        headers=headers,
        json={"library_asset_id": old["id"], "asset_type": "image"},
    )
    assert resp.status_code == 400
    assert "superseded" in resp.text


async def test_upload_on_use_writes_through_to_the_library(
    client, operator_user, project_id,
):
    """AD-09.4.2 upload-on-use, and it must be OPT-IN."""
    user, _ = operator_user
    headers = make_auth_header(user)

    # Without library_kind: nothing enters the library. This is the path every
    # media task in the fleet uses.
    plain = await client.post(
        f"/api/v1/projects/{project_id}/assets/upload",
        headers=headers,
        files={"file": ("frame.png", b"GENERATED-FRAME", "image/png")},
        data={"asset_type": "image"},
    )
    assert plain.status_code == 201, plain.text
    assert plain.json()["library_asset_id"] is None

    listing = await client.get("/api/v1/library/assets", headers=headers)
    assert listing.json()["total"] == 0, (
        "worker uploads must never enter the library — AD-09.14 Q7 (library "
        "retention and quota) is unanswered"
    )

    # With library_kind: written through, and linked.
    through = await client.post(
        f"/api/v1/projects/{project_id}/assets/upload",
        headers=headers,
        files={"file": ("brand.png", b"OPERATOR-LOGO", "image/png")},
        data={"asset_type": "image", "library_kind": "logo", "library_name": "Brand mark"},
    )
    assert through.status_code == 201, through.text
    assert through.json()["library_asset_id"] is not None

    listing2 = await client.get("/api/v1/library/assets", headers=headers)
    assert listing2.json()["total"] == 1
    assert listing2.json()["data"][0]["name"] == "Brand mark"
    assert listing2.json()["data"][0]["kind"] == "logo"


# ---------------------------------------------------------------------------
# actors
# ---------------------------------------------------------------------------

async def test_create_actor_and_read_it_back(
    client, operator_user,
):
    user, _ = operator_user
    headers = make_auth_header(user)
    clip = await _upload_library_asset(
        client, headers, kind="reference_clip", name="Sarah plate",
        content=b"SARAH", filename="sarah.mp4",
    )
    resp = await client.post(
        "/api/v1/actors",
        headers=headers,
        json={
            "name": "Sarah — corporate",
            "reference_clip_id": clip["id"],
            "voice_profile": {"engine": "coqui", "speaker_id": "sarah-01"},
            "default_orientation": "landscape",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    for field in (
        "id", "name", "description", "reference_clip_id", "reference_image_id",
        "voice_profile", "engine_bindings", "default_orientation",
        "certified_model_id", "owner_scope", "is_active",
        "created_by", "created_at", "updated_at",
    ):
        assert field in body, f"{field} missing from ActorResponse"
    assert body["voice_profile"]["speaker_id"] == "sarah-01"
    assert body["engine_bindings"] is None, (
        "AD-09.14 Q1 is OPEN — the API must not invent a default binding"
    )


async def test_engine_bindings_are_stored_verbatim_and_unvalidated(
    client, operator_user,
):
    """AD-09.14 open question 1 is UNANSWERED.

    A validator written against a guess would reject the operator's real
    MagiHuman values on the day they are finally recorded. The column carries
    whatever shape arrives, keyed by engine.
    """
    user, _ = operator_user
    headers = make_auth_header(user)
    weird = {"magihuman": {"anything": [1, 2, {"at": "all"}]}, "latentsync": {}}
    resp = await client.post(
        "/api/v1/actors",
        headers=headers,
        json={"name": "Binding probe", "engine_bindings": weird},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["engine_bindings"] == weird


async def test_actor_reference_clip_must_be_the_right_kind(
    client, operator_user,
):
    """The FK catches a missing row. It cannot catch a clip that is a font."""
    user, _ = operator_user
    headers = make_auth_header(user)
    font = await _upload_library_asset(
        client, headers, kind="font", name="Inter", content=b"TTF", filename="i.ttf",
    )
    resp = await client.post(
        "/api/v1/actors",
        headers=headers,
        json={"name": "Wrong media", "reference_clip_id": font["id"]},
    )
    assert resp.status_code == 400
    assert "kind" in resp.text


async def test_duplicate_active_actor_name_is_rejected(
    client, operator_user,
):
    user, _ = operator_user
    headers = make_auth_header(user)
    payload = {"name": "Sarah — corporate"}
    first = await client.post("/api/v1/actors", headers=headers, json=payload)
    assert first.status_code == 201
    second = await client.post("/api/v1/actors", headers=headers, json=payload)
    assert second.status_code == 400
    assert "already exists" in second.text


async def test_retiring_an_actor_hides_it_by_default(
    client, operator_user,
):
    user, _ = operator_user
    headers = make_auth_header(user)
    created = await client.post(
        "/api/v1/actors", headers=headers, json={"name": "Temp actor"},
    )
    actor_id = created.json()["id"]
    patched = await client.patch(
        f"/api/v1/actors/{actor_id}", headers=headers, json={"is_active": False},
    )
    assert patched.status_code == 200
    assert patched.json()["is_active"] is False

    listing = await client.get("/api/v1/actors", headers=headers)
    assert listing.json()["total"] == 0
    with_inactive = await client.get(
        "/api/v1/actors", headers=headers, params={"include_inactive": "true"},
    )
    assert with_inactive.json()["total"] == 1


# ---------------------------------------------------------------------------
# presets
# ---------------------------------------------------------------------------

async def test_create_preset_starts_at_version_1(client, operator_user):
    user, _ = operator_user
    headers = make_auth_header(user)
    resp = await client.post(
        "/api/v1/presets",
        headers=headers,
        json={
            "name": "Corporate 2026",
            "description": "House style",
            "payload": {"max_runtime_seconds": 600, "target_audience": "New starters"},
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["version"] == 1
    assert body["is_active"] is True
    assert body["payload"]["max_runtime_seconds"] == 600


async def test_revise_creates_a_new_version_and_leaves_the_old_one_readable(
    client, operator_user,
):
    """AD-09.5. This is the whole reason presets are versioned rather than
    mutated: a project pinned to v1 must stay inspectable after v2 lands."""
    user, _ = operator_user
    headers = make_auth_header(user)
    await client.post(
        "/api/v1/presets", headers=headers,
        json={"name": "Corporate 2026", "payload": {"max_runtime_seconds": 600}},
    )
    revised = await client.post(
        "/api/v1/presets/by-name/Corporate 2026/revise",
        headers=headers,
        json={"payload": {"max_runtime_seconds": 900}},
    )
    assert revised.status_code == 201, revised.text
    assert revised.json()["version"] == 2
    assert revised.json()["is_active"] is True

    versions = await client.get(
        "/api/v1/presets/by-name/Corporate 2026/versions", headers=headers,
    )
    rows = versions.json()
    assert [r["version"] for r in rows] == [2, 1]
    v1 = next(r for r in rows if r["version"] == 1)
    assert v1["is_active"] is False
    assert v1["payload"]["max_runtime_seconds"] == 600, (
        "revising must not rewrite the payload of an earlier version"
    )

    # Only the current version is offered as a live choice.
    active = await client.get("/api/v1/presets", headers=headers)
    assert active.json()["total"] == 1
    assert active.json()["data"][0]["version"] == 2


async def test_a_second_preset_with_the_same_name_is_rejected(client, operator_user):
    user, _ = operator_user
    headers = make_auth_header(user)
    await client.post(
        "/api/v1/presets", headers=headers,
        json={"name": "Corporate 2026", "payload": {}},
    )
    dup = await client.post(
        "/api/v1/presets", headers=headers,
        json={"name": "Corporate 2026", "payload": {}},
    )
    assert dup.status_code == 400
    assert "new VERSION" in dup.text


async def test_preset_payload_rejects_unknown_blocks(client, operator_user):
    """`extra="forbid"`. A typo'd block that stores silently is a preset that
    quietly does less than the operator configured."""
    user, _ = operator_user
    headers = make_auth_header(user)
    resp = await client.post(
        "/api/v1/presets", headers=headers,
        json={"name": "Typo", "payload": {"brandign": {"logo_policy": "always"}}},
    )
    assert resp.status_code == 422, resp.text


async def test_preset_rejects_an_actor_that_does_not_exist(client, operator_user):
    """Fail at CREATION, where the operator can still fix it — not at apply
    time in front of a project they were halfway through."""
    user, _ = operator_user
    headers = make_auth_header(user)
    resp = await client.post(
        "/api/v1/presets", headers=headers,
        json={"name": "Ghost actor", "payload": {"actor_id": str(uuid.uuid4())}},
    )
    assert resp.status_code == 400
    assert "does not exist" in resp.text


async def test_preset_logo_must_be_a_logo(
    client, operator_user,
):
    user, _ = operator_user
    headers = make_auth_header(user)
    music = await _upload_library_asset(
        client, headers, kind="music_bed", name="Bed", content=b"MP3",
        filename="bed.mp3",
    )
    resp = await client.post(
        "/api/v1/presets", headers=headers,
        json={
            "name": "Wrong logo",
            "payload": {"branding": {"logo_library_asset_id": music["id"]}},
        },
    )
    assert resp.status_code == 400
    assert "not a logo" in resp.text


async def test_apply_preset_writes_into_the_project_and_records_provenance(
    client, operator_user, project_id, db_session,
):
    """AD-09.15 criterion 1, asserted on the ROWS the apply wrote."""
    from sqlalchemy import select
    from app.models.project import Project

    user, _ = operator_user
    headers = make_auth_header(user)

    clip = await _upload_library_asset(
        client, headers, kind="reference_clip", name="Sarah plate",
        content=b"SARAHCLIP", filename="sarah.mp4",
    )
    actor = await client.post(
        "/api/v1/actors", headers=headers,
        json={"name": "Sarah — corporate", "reference_clip_id": clip["id"]},
    )
    assert actor.status_code == 201, actor.text

    preset = await client.post(
        "/api/v1/presets", headers=headers,
        json={
            "name": "Corporate 2026",
            "payload": {
                "actor_id": actor.json()["id"],
                "max_runtime_seconds": 720,
                "target_audience": "New starters",
            },
        },
    )
    assert preset.status_code == 201, preset.text

    applied = await client.post(
        f"/api/v1/projects/{project_id}/apply-preset",
        headers=headers, json={"preset_id": preset.json()["id"]},
    )
    assert applied.status_code == 200, applied.text
    result = applied.json()
    assert result["preset_version"] == 1
    assert any("max_runtime_seconds=720" in a for a in result["applied"])
    assert any("Sarah" in a for a in result["applied"])

    # The rows, not the status code.
    row = await db_session.scalar(
        select(Project).where(Project.id == uuid.UUID(project_id))
    )
    await db_session.refresh(row)
    assert row.max_runtime_seconds == 720
    assert row.target_audience == "New starters"
    assert row.preset_id is not None
    assert row.preset_version == 1
    # WP-70 fix S10 re-aimed this assertion. It used to require
    # `talking_head_asset_id` to be SET — which pinned the defect: the clip was
    # written as `talking_head` while Stage 6 looks up `reference_clip`, and
    # that column names the RENDERED head. Same risk, correct target: the
    # actor's clip is referenced into the project under the member Stage 6
    # reads, and the rendered-head column is untouched.
    from app.models.asset import Asset
    referenced = await db_session.scalar(
        select(Asset).where(
            Asset.project_id == uuid.UUID(project_id),
            Asset.library_asset_id == uuid.UUID(clip["id"]),
        )
    )
    assert referenced is not None, "the actor's reference clip must be referenced into the project"
    assert referenced.asset_type == "reference_clip", referenced.asset_type
    assert row.talking_head_asset_id is None, (
        "talking_head_asset_id names the RENDERED head; preset apply must leave it null"
    )


async def test_apply_preset_reports_branding_as_recorded_not_applied(
    client, operator_user, project_id,
):
    """The honesty test, and the reason this package does not ship a ninth
    instance of the AD-09.3 stub family.

    Branding is stored and returned; NOTHING in the render path reads it (WP-56
    Task 3 stopped on the presenter/logo chain). The apply result must say so
    rather than counting a logo as applied.
    """
    user, _ = operator_user
    headers = make_auth_header(user)
    logo = await _upload_library_asset(
        client, headers, kind="logo", name="Acme mark", content=b"ACMEPNG",
    )
    preset = await client.post(
        "/api/v1/presets", headers=headers,
        json={
            "name": "Branded",
            "payload": {
                "branding": {
                    "logo_library_asset_id": logo["id"],
                    "logo_policy": "always",
                },
            },
        },
    )
    assert preset.status_code == 201, preset.text

    applied = await client.post(
        f"/api/v1/projects/{project_id}/apply-preset",
        headers=headers, json={"preset_id": preset.json()["id"]},
    )
    assert applied.status_code == 200, applied.text
    result = applied.json()
    assert not any("branding" in a.lower() for a in result["applied"]), (
        "branding must NOT be reported as applied — nothing renders it"
    )
    assert any("branding" in r.lower() for r in result["recorded_not_applied"])


async def test_apply_preset_rejects_a_retired_actor(
    client, operator_user, project_id,
):
    user, _ = operator_user
    headers = make_auth_header(user)
    actor = await client.post(
        "/api/v1/actors", headers=headers, json={"name": "Retiring soon"},
    )
    actor_id = actor.json()["id"]
    preset = await client.post(
        "/api/v1/presets", headers=headers,
        json={"name": "Has actor", "payload": {"actor_id": actor_id}},
    )
    assert preset.status_code == 201, preset.text

    await client.patch(
        f"/api/v1/actors/{actor_id}", headers=headers, json={"is_active": False},
    )
    applied = await client.post(
        f"/api/v1/projects/{project_id}/apply-preset",
        headers=headers, json={"preset_id": preset.json()["id"]},
    )
    assert applied.status_code == 400
    assert "retired" in applied.text


async def test_library_routes_require_authentication(client):
    for path in ("/api/v1/library/assets", "/api/v1/actors", "/api/v1/presets"):
        resp = await client.get(path)
        assert resp.status_code in (401, 403), f"{path} was reachable unauthenticated"
