/**
 * WP-40 Task 1 — the Media Assets grid rendered 40 blank cards and issued
 * ZERO image requests (devtools Img filter: 0 of 121) while the asset list
 * fetch returned 200.
 *
 * The card built its `<img>` from `asset.thumbnail_url || asset.url`. The API
 * sends neither. `<img src={undefined}>` renders an element with NO src
 * attribute, so the browser has nothing to request -- which is why the
 * network tab showed an absence rather than a failure.
 *
 * WIRE below is the real response, copied from
 *   GET /api/v1/projects/c12fa967-.../assets?per_page=100
 * on 2026-08-23 (40 assets, envelope-wrapped).
 */
import test from "node:test";
import assert from "node:assert/strict";
import { unwrapList } from "../../../.test-build/unwrap.js";
import {
  assetDownloadPath,
  assetExtension,
  assetFilename,
  assetMediaKind,
  assetSearchText,
  assetTypeLabel,
  formatBytes,
} from "../../../.test-build/media.js";

/** Verbatim keys of a live asset row. */
const FINAL_RENDER = {
  id: "72964509-d773-4da7-8ce8-4091f7bc2a4c",
  project_id: "c12fa967-f989-4ed4-8e20-3ea62cb92e8f",
  scene_id: null,
  asset_type: "final_render",
  seaweedfs_fid: "3,89a02975a3",
  seaweedfs_path:
    "/ivgs/final/c12fa967-f989-4ed4-8e20-3ea62cb92e8f/draft_720p_en-US.mp4",
  mime_type: "video/mp4",
  file_size_bytes: 6005929,
  duration_seconds: null,
  language_code: "en-US",
  generation_prompt_id: null,
  storage_tier: "hot",
  preserve_flag: false,
  content_hash: "67b34cb5",
  reference_count: 1,
  created_at: "2026-08-23T19:24:15.524298Z",
};

const IMAGE = {
  ...FINAL_RENDER,
  id: "8431cc40-1e57-473e-be17-2745308526d0",
  asset_type: "image",
  seaweedfs_path: "/ivgs/media/c12fa967/scene_03_image.png",
  mime_type: "image/png",
  file_size_bytes: 641217,
};

const AUDIO = {
  ...FINAL_RENDER,
  id: "aaaa1111-0000-0000-0000-000000000000",
  asset_type: "audio",
  seaweedfs_path: "/ivgs/audio/c12fa967/scene_03_en-US.wav",
  mime_type: "audio/wav",
  file_size_bytes: 220500,
};

const DOCUMENT = {
  ...FINAL_RENDER,
  id: "dddd2222-0000-0000-0000-000000000000",
  asset_type: "document",
  seaweedfs_path: "/ivgs/uploads/c12fa967/source.txt",
  mime_type: "text/plain",
  file_size_bytes: 4096,
};

test("THE BUG: the fields the card read are absent from the wire", () => {
  for (const key of [
    "url",
    "thumbnail_url",
    "filename",
    "scene_label",
    "generation_prompt",
    "quality_score",
    "storage_path",
  ]) {
    assert.equal(
      Object.prototype.hasOwnProperty.call(IMAGE, key),
      false,
      `the API does not send ${key}`
    );
  }
  // and this is the exact expression the component evaluated
  const src = IMAGE.thumbnail_url || IMAGE.url;
  assert.equal(src, undefined, "<img src={undefined}> requests nothing");
});

test("the fix derives a working media URL for every asset", () => {
  for (const asset of [IMAGE, FINAL_RENDER, AUDIO, DOCUMENT]) {
    assert.equal(
      assetDownloadPath(asset.id),
      `/api/v1/assets/${asset.id}/download`
    );
  }
});

test("the download path is asset-scoped, NOT project-scoped", () => {
  // assets.py:33 mounts the asset router at /assets; only LIST and UPLOAD
  // are project-scoped. useAssets.regenerateAsset had this wrong and 404'd.
  const path = assetDownloadPath(IMAGE.id);
  assert.ok(!path.includes("/projects/"), path);
  assert.ok(path.startsWith("/api/v1/assets/"), path);
});

test("media kind comes from mime_type, not the pipeline role", () => {
  assert.equal(assetMediaKind(IMAGE), "image");
  assert.equal(assetMediaKind(AUDIO), "audio");
  assert.equal(assetMediaKind(DOCUMENT), "other");
  // the old switch only knew image/animation/video, so the finished 720p
  // draft fell through to a bare "Asset" box despite being playable video
  assert.equal(assetMediaKind(FINAL_RENDER), "video");
});

test("media kind falls back to the extension when mime_type is missing", () => {
  assert.equal(assetMediaKind({ ...IMAGE, mime_type: null }), "image");
  assert.equal(assetMediaKind({ ...FINAL_RENDER, mime_type: null }), "video");
  assert.equal(assetMediaKind({ ...AUDIO, mime_type: null }), "audio");
});

test("media kind falls back to asset_type when both are missing", () => {
  const bare = { id: "x", asset_type: "talking_head", seaweedfs_path: null, mime_type: null };
  assert.equal(assetMediaKind(bare), "video");
});

test("filename comes from the SeaweedFS path", () => {
  assert.equal(assetFilename(FINAL_RENDER), "draft_720p_en-US.mp4");
  assert.equal(assetFilename(IMAGE), "scene_03_image.png");
  assert.equal(assetExtension(FINAL_RENDER), "mp4");
});

test("filename degrades to a stable synthetic name, never a throw", () => {
  assert.equal(
    assetFilename({ id: "8431cc40-1e57-473e", asset_type: "image", seaweedfs_path: null }),
    "image-8431cc40"
  );
  assert.equal(assetFilename(null), "asset");
  assert.equal(assetFilename(undefined), "asset");
  assert.equal(assetExtension(null), "");
});

test("search matches what the API actually sends", () => {
  // the old haystack was filename/scene_label/generation_prompt -- all
  // undefined -- so typing anything at all emptied the grid
  const oldHaystack =
    (IMAGE.filename ?? "") + (IMAGE.scene_label ?? "") + (IMAGE.generation_prompt ?? "");
  assert.equal(oldHaystack, "", "the old search had nothing to search");

  assert.ok(assetSearchText(IMAGE).includes("scene_03"));
  assert.ok(assetSearchText(AUDIO).includes("audio"));
  assert.ok(assetSearchText(FINAL_RENDER).includes("en-us"));
  assert.equal(assetSearchText(null), "");
});

test("type labels are human, and total", () => {
  assert.equal(assetTypeLabel(FINAL_RENDER), "Final render");
  assert.equal(assetTypeLabel(IMAGE), "Image");
  assert.equal(assetTypeLabel(null), "Asset");
  assert.equal(assetTypeLabel({ id: "x", asset_type: null }), "Asset");
});

test("byte formatting handles the real sizes and the absent ones", () => {
  assert.equal(formatBytes(6005929), "5.7 MB");
  assert.equal(formatBytes(641217), "626 KB");
  assert.equal(formatBytes(0), "0 B");
  assert.equal(formatBytes(null), "—");
  assert.equal(formatBytes(undefined), "—");
});

test("the list envelope still unwraps to 40 usable assets", () => {
  const envelope = { data: [IMAGE, FINAL_RENDER, AUDIO, DOCUMENT], total: 4 };
  const assets = unwrapList(envelope);
  assert.equal(assets.length, 4);
  // every one of them yields a URL, a name and a kind -- no blanks
  for (const a of assets) {
    assert.ok(assetDownloadPath(a.id).length > 0);
    assert.ok(assetFilename(a).length > 0);
    assert.ok(["image", "video", "audio", "other"].includes(assetMediaKind(a)));
  }
});
