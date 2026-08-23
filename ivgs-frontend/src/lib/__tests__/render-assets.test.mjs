/**
 * WP-40 addendum — the four sibling asset tabs.
 *
 * Same defect as the Media Assets grid, on four more surfaces. Two of them
 * failed differently and more completely than the grid did, because they read
 * phantom fields off the PROJECT rather than off an asset:
 *
 *   draft/page.tsx    read `project.draft_video_url`   -- no such field
 *   renders/page.tsx  read `project.render_variants`   -- no such field
 *
 * so both tabs rendered their empty state unconditionally, on every project,
 * forever. Project c12fa967 has had a 5.7 MB `draft_720p_en-US.mp4` in its
 * asset list since 19:24 and the Draft Preview tab said "No draft preview
 * available yet".
 *
 * The load-bearing new fact is that DRAFTS AND FINAL RENDERS SHARE ONE
 * asset_type. Verified in the workers, which are the ground truth:
 *   stage7_prototype_draft.py:191  `draft_720p_{lang}.mp4`   asset_type=final_render
 *   stage8_final_render.py:205     `final_{profile}_{lang}.mp4` asset_type=final_render
 *   stage8_final_render.py:103     render_profiles = ["1080p", "4k"]
 * Only the filename prefix separates them. Getting that wrong would put a
 * 720p review draft on the Final Renders tab.
 */
import test from "node:test";
import assert from "node:assert/strict";
import {
  assetLabel,
  assetMediaKind,
  assetRenderKind,
  assetRenderProfile,
  formatDuration,
} from "../../../.test-build/media.js";

/** The live draft asset, verbatim. */
const DRAFT = {
  id: "72964509-d773-4da7-8ce8-4091f7bc2a4c",
  project_id: "c12fa967-f989-4ed4-8e20-3ea62cb92e8f",
  scene_id: null,
  asset_type: "final_render",
  seaweedfs_path:
    "/ivgs/final/c12fa967-f989-4ed4-8e20-3ea62cb92e8f/draft_720p_en-US.mp4",
  mime_type: "video/mp4",
  file_size_bytes: 6005929,
  language_code: "en-US",
  created_at: "2026-08-23T19:24:15.524298Z",
};

/** What stage 8 will write, per stage8_final_render.py:205. */
const FINAL_1080 = {
  ...DRAFT,
  id: "aaaa0000-0000-0000-0000-000000000001",
  seaweedfs_path: "/ivgs/final/c12fa967/renders/en-US/final_1080p_en-US.mp4",
  file_size_bytes: 18502995,
};
const FINAL_4K = {
  ...DRAFT,
  id: "aaaa0000-0000-0000-0000-000000000002",
  seaweedfs_path: "/ivgs/final/c12fa967/renders/en-US/final_4k_en-US.mp4",
  file_size_bytes: 74011980,
};
const FINAL_ES = {
  ...FINAL_1080,
  id: "aaaa0000-0000-0000-0000-000000000003",
  seaweedfs_path: "/ivgs/final/c12fa967/renders/es-ES/final_1080p_es-ES.mp4",
  language_code: "es-ES",
};

/** The live talking-head clip, verbatim. */
const TALKING_HEAD = {
  ...DRAFT,
  id: "bbbb0000-0000-0000-0000-000000000001",
  asset_type: "talking_head",
  seaweedfs_path:
    "/ivgs/talking-heads/c12fa967-f989-4ed4-8e20-3ea62cb92e8f/talking_head_en-US.mp4",
};

/** Two live audio rows -- note the IDENTICAL path. */
const AUDIO_A = {
  id: "cccc0000-0000-0000-0000-000000000001",
  project_id: DRAFT.project_id,
  scene_id: "f09c2b43-8a47-4b0a-b54b-8ef6b03d599d",
  asset_type: "audio",
  seaweedfs_path: "/ivgs/audio/c12fa967-f989-4ed4-8e20-3ea62cb92e8f/en-US.wav",
  mime_type: "audio/wav",
  file_size_bytes: 220500,
  duration_seconds: null,
  language_code: "en-US",
  created_at: "2026-08-23T18:46:19.242320Z",
};
const AUDIO_B = {
  ...AUDIO_A,
  id: "cccc0000-0000-0000-0000-000000000002",
  scene_id: "6019b4c2-ba8a-4398-8c60-ac1d0e7bfe1c",
};

// ── Draft vs final ────────────────────────────────────────────────────────

test("THE BUG: both tabs read fields the PROJECT does not have", () => {
  // the live ProjectResponse, trimmed to its real keys
  const project = {
    id: "c12fa967-f989-4ed4-8e20-3ea62cb92e8f",
    name: "double digit multiplication",
    state: "MEDIA_GENERATION",
    scene_count: 18,
    hero_image_url: null,
    language_variants: [
      { language_code: "en-US", state: "pending" },
      { language_code: "es-ES", state: "pending" },
    ],
    active_job: null,
  };

  assert.equal(project.draft_video_url, undefined, "draft tab: always empty");
  assert.equal(project.render_variants, undefined, "renders tab: always empty");
  assert.equal((project.render_variants || []).length, 0);

  // and the variants that DO exist carry none of the fields the page read
  const v = project.language_variants[0];
  assert.equal(v.url_1080p, undefined);
  assert.equal(v.url_4k, undefined);
  assert.equal(v.subtitle_vtt_url, undefined);
  assert.equal(v.language, undefined, "the page keyed on `language`, not `language_code`");
});

test("the draft is separated from finals by filename, not asset_type", () => {
  assert.equal(DRAFT.asset_type, FINAL_1080.asset_type, "same asset_type");
  assert.equal(assetRenderKind(DRAFT), "draft");
  assert.equal(assetRenderKind(FINAL_1080), "final");
  assert.equal(assetRenderKind(FINAL_4K), "final");
});

test("a draft can never appear on the Final Renders tab", () => {
  const all = [DRAFT, FINAL_1080, FINAL_4K, FINAL_ES, TALKING_HEAD, AUDIO_A];
  const finals = all.filter((a) => assetRenderKind(a) === "final");
  const drafts = all.filter((a) => assetRenderKind(a) === "draft");

  assert.equal(drafts.length, 1);
  assert.equal(drafts[0].id, DRAFT.id);
  assert.equal(finals.length, 3);
  assert.ok(!finals.some((f) => f.id === DRAFT.id));
});

test("non-render assets are not classified as renders at all", () => {
  assert.equal(assetRenderKind(TALKING_HEAD), null);
  assert.equal(assetRenderKind(AUDIO_A), null);
  assert.equal(assetRenderKind(null), null);
  assert.equal(assetRenderKind(undefined), null);
});

test("an unrecognised final_render is shown, not hidden", () => {
  // an operator can see from the name that it is not a draft; they cannot see
  // an asset the UI silently dropped
  const odd = { ...DRAFT, seaweedfs_path: "/ivgs/final/c12fa967/output.mp4" };
  assert.equal(assetRenderKind(odd), "final");
});

test("quality profiles come from the filename the worker wrote", () => {
  assert.equal(assetRenderProfile(DRAFT), "720p");
  assert.equal(assetRenderProfile(FINAL_1080), "1080p");
  assert.equal(assetRenderProfile(FINAL_4K), "4K");
  assert.equal(assetRenderProfile(TALKING_HEAD), null);
  assert.equal(assetRenderProfile(null), null);
});

test("renders group by the language the API actually sends", () => {
  const finals = [FINAL_1080, FINAL_4K, FINAL_ES];
  const languages = [];
  for (const f of finals) {
    const l = f.language_code || "—";
    if (!languages.includes(l)) languages.push(l);
  }
  assert.deepEqual(languages, ["en-US", "es-ES"]);

  const en = finals.filter((f) => f.language_code === "en-US");
  assert.deepEqual(en.map(assetRenderProfile), ["1080p", "4K"]);

  const es = finals.filter((f) => f.language_code === "es-ES");
  assert.deepEqual(es.map(assetRenderProfile), ["1080p"], "only what was rendered");
});

// ── Audio and talking head ────────────────────────────────────────────────

test("the audio tab finds tracks by derived kind", () => {
  const all = [DRAFT, FINAL_1080, TALKING_HEAD, AUDIO_A, AUDIO_B];
  const audio = all.filter((a) => assetMediaKind(a) === "audio");
  assert.equal(audio.length, 2);
  assert.equal(assetMediaKind(TALKING_HEAD), "video");
});

test("cards are distinguishable even though the paths collide", () => {
  // this is the real weakness: all 18 audio assets of c12fa967 share one path
  assert.equal(AUDIO_A.seaweedfs_path, AUDIO_B.seaweedfs_path);
  assert.equal(assetLabel(AUDIO_A), assetLabel(AUDIO_B), "filename alone is ambiguous");

  // scene_id IS populated, so the scene index disambiguates
  assert.notEqual(AUDIO_A.scene_id, AUDIO_B.scene_id);
  assert.equal(assetLabel(AUDIO_A, 3), "Scene 4 · en-US.wav");
  assert.equal(assetLabel(AUDIO_B, 11), "Scene 12 · en-US.wav");
  assert.notEqual(assetLabel(AUDIO_A, 3), assetLabel(AUDIO_B, 11));
});

test("assetLabel degrades to the filename when there is no scene", () => {
  assert.equal(assetLabel(DRAFT, null), "draft_720p_en-US.mp4");
  assert.equal(assetLabel(DRAFT, undefined), "draft_720p_en-US.mp4");
  assert.equal(assetLabel(null, 0), "Scene 1 · asset");
});

test("duration formats the recorded value and admits an absent one", () => {
  assert.equal(formatDuration(95), "1:35");
  assert.equal(formatDuration(0), "0:00");
  // the live audio rows have duration_seconds: null
  assert.equal(AUDIO_A.duration_seconds, null);
  assert.equal(formatDuration(AUDIO_A.duration_seconds), "—");
  assert.equal(formatDuration(undefined), "—");
});

// ── Scene thumbnails ──────────────────────────────────────────────────────

test("a scene's picture is its image asset, joined on scene_id", () => {
  // `thumbnail_url` is on no payload in this system; `scene_id` is on 36 of 40
  const scene = {
    id: "f09c2b43-8a47-4b0a-b54b-8ef6b03d599d",
    project_id: DRAFT.project_id,
    scene_index: 3,
    media_type: "image",
  };
  assert.equal(scene.thumbnail_url, undefined);

  const IMAGE = {
    id: "dddd0000-0000-0000-0000-000000000001",
    scene_id: scene.id,
    asset_type: "image",
    mime_type: "image/png",
    seaweedfs_path: "/ivgs/images/c12fa967/image.png",
  };
  const assets = [DRAFT, AUDIO_A, IMAGE, AUDIO_B];

  const found = assets.find(
    (a) => a.scene_id === scene.id && assetMediaKind(a) === "image"
  );
  assert.equal(found?.id, IMAGE.id, "the image, not the audio on the same scene");

  // a scene with no image yields nothing, and the caller renders its fallback
  const orphan = assets.find(
    (a) => a.scene_id === "no-such-scene" && assetMediaKind(a) === "image"
  );
  assert.equal(orphan, undefined);
});

// ── Flagged assets ────────────────────────────────────────────────────────

test("a flagged asset is previewable from asset_id, and scores may be null", () => {
  // FlaggedAssetResponse, schemas/quality.py:32
  const flagged = {
    id: "eeee0000-0000-0000-0000-000000000001",
    asset_id: "8431cc40-1e57-473e-be17-2745308526d0",
    job_id: null,
    quality_score: null,
    safety_score: null,
    scoring_details: { sharpness: 0.42, artifacts: 0.9, note: "not a number" },
    decision: "flagged",
    created_at: "2026-08-23T16:46:54.391571Z",
    asset_type: "image",
    project_id: DRAFT.project_id,
    project_name: "double digit multiplication",
  };

  assert.equal(flagged.thumbnail_url, undefined, "no such field, anywhere");
  assert.equal(flagged.scene_index, undefined);
  assert.equal(flagged.metrics, undefined, "the breakdown is scoring_details");
  assert.equal(flagged.score_id, undefined, "approve/reject POSTed to .../undefined/approve");
  assert.equal(typeof flagged.id, "string", "the primary key is `id`");

  // only numeric details become metric rows; a string must not be compared
  // against a numeric threshold and silently read as "fail"
  const metrics = Object.entries(flagged.scoring_details)
    .filter(([, v]) => typeof v === "number" && Number.isFinite(v))
    .map(([type, value]) => ({ type, value }));
  assert.deepEqual(metrics.map((m) => m.type), ["sharpness", "artifacts"]);
});
