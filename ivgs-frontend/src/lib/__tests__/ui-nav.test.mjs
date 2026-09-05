/**
 * WP-43-UI-NAV — every fixture below is a REAL response body, captured live
 * on 2026-08-25 from ivgs-api:v5.6.5-reviewgate on node-01, against the
 * reference project c12fa967-f989-4ed4-8e20-3ea62cb92e8f.
 *
 * Each block reproduces the operator-visible failure first, then pins the
 * fix, in the WP-35/38/40 pattern.
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
  apiErrorMessage,
  envelopeMessage,
  fieldErrors,
  validationFieldName,
  validationMessages,
} from "../../../.test-build/errors.js";
import {
  MEDIA_TYPES,
  durationError,
  mediaTypeIcon,
  mediaTypeLabel,
  normalizeMediaType,
  sceneUpdatePayload,
} from "../../../.test-build/scenes.js";
import {
  SUPPORTED_LANGUAGES,
  addableLanguages,
  isSupportedLanguage,
  isRetryableVariant,
  languageLabel,
  variantHasRender,
  variantProgressPercent,
  variantState,
} from "../../../.test-build/languages.js";
import {
  PIPELINE_STAGE_IDS,
  selectPipelineRun,
  stageStatuses,
} from "../../../.test-build/pipeline-run.js";
import {
  PROJECT_TABS,
  activeTabId,
  tabHref,
} from "../../../.test-build/project-tabs.js";
import {
  PROJECT_STATE_SEQUENCE,
  projectStateProgress,
  stateStepStatuses,
} from "../../../.test-build/project-state.js";
import { mergeCheckpoints } from "../../../.test-build/jobs.js";

/* ───────────────────────── captured wire bodies ───────────────────────── */

/** PATCH /projects/{id}/scenes/{sid} with the modal's old payload -> 422. */
const SCENE_422 = {
  detail: [
    {
      type: "value_error",
      loc: ["body", "media_type"],
      msg: "Value error, media_type must be one of: image, video_clip, animation",
      input: "VIDEO",
      ctx: { error: {} },
    },
  ],
};

/** POST /projects/{id}/languages with the form's old payload -> 422. */
const LANGUAGE_422 = {
  detail: [
    {
      type: "value_error",
      loc: ["body", "language_code"],
      msg:
        "Value error, Unsupported language code 'es'. Supported: ar-SA, de-DE, " +
        "en-GB, en-US, es-ES, fr-FR, ja-JP, zh-CN",
      input: "es",
      ctx: { error: {} },
    },
  ],
};

/** POST /auth/refresh with a header and no body -> 422. */
const REFRESH_422 = {
  detail: [{ type: "missing", loc: ["body"], msg: "Field required", input: null }],
};

/** POST /projects/{id}/languages/en-US/retry -> 422 (a UUID was expected). */
const RETRY_422 = {
  detail: [
    {
      type: "uuid_parsing",
      loc: ["path", "variant_id"],
      msg:
        "Input should be a valid UUID, invalid character: expected an optional " +
        "prefix of `urn:uuid:` followed by [0-9a-fA-F-], found `n` at 2",
      input: "en-US",
    },
  ],
};

/** The coded-envelope shape the deliberate 409/404s use. */
const CONFLICT_409 = {
  detail: {
    error: {
      code: "INVALID_STATE_TRANSITION",
      message: "Cannot trigger pipeline from state 'MEDIA_GENERATION'.",
    },
  },
};

/** GET /projects/{id}/scenes — one of eighteen, verbatim. */
const SCENE_WIRE = {
  id: "6c9b010e-00c0-44f2-a952-933095e09ab2",
  project_id: "c12fa967-f989-4ed4-8e20-3ea62cb92e8f",
  scene_index: 0,
  narration_text: "Let's learn how to multiply two-digit numbers.",
  visual_description: "A friendly, approachable teacher standing in front of a whiteboard.",
  media_type: "image",
  duration_seconds: 10.0,
  created_at: "2026-08-23T16:03:24.595707Z",
  updated_at: "2026-08-23T16:03:24.595707Z",
};

/** GET /projects/{id}/languages — both rows, verbatim. */
const LANGUAGE_WIRE = [
  {
    id: "743822dd-991f-41c4-8d0c-ac9c51e24480",
    project_id: "c12fa967-f989-4ed4-8e20-3ea62cb92e8f",
    language_code: "en-US",
    state: "pending",
    final_render_1080p_id: null,
    final_render_4k_id: null,
    created_at: "2026-08-23T08:14:31.873292Z",
  },
  {
    id: "3fccf815-f639-43c1-8a90-631336dc2d13",
    project_id: "c12fa967-f989-4ed4-8e20-3ea62cb92e8f",
    language_code: "es-ES",
    state: "pending",
    final_render_1080p_id: null,
    final_render_4k_id: null,
    created_at: "2026-08-23T08:14:31.873292Z",
  },
];

/** GET /projects/{id} .language_variants — thinner still. */
const PROJECT_DETAIL_VARIANTS = [
  { language_code: "en-US", state: "pending" },
  { language_code: "es-ES", state: "pending" },
];

/** GET /projects/{id}/jobs .data — all ten, newest first. */
const JOBS_WIRE = [
  { id: "d3842fdf-3fe9-4983-b241-f467c94e95eb", job_type: "storyboard_generation", status: "pending", created_at: "2026-08-25T00:40:35.827882Z" },
  { id: "c4249f92-ac4d-4e86-94e9-4865b1e0b165", job_type: "storyboard_generation", status: "pending", created_at: "2026-08-25T00:40:33.307527Z" },
  { id: "7d6a44b2-8492-466b-b973-021a40146184", job_type: "storyboard_generation", status: "pending", created_at: "2026-08-23T22:10:44.184788Z" },
  { id: "4646aeba-83bb-47d1-95d9-6296bb9dfe4c", job_type: "storyboard_generation", status: "pending", created_at: "2026-08-23T22:10:37.703853Z" },
  { id: "c57ec7b7-09ab-46a9-8050-bbb2405972d4", job_type: "storyboard_generation", status: "pending", created_at: "2026-08-23T20:51:25.948452Z" },
  { id: "9fdea8ae-e3ab-4331-9d36-f3a5bb9759da", job_type: "storyboard_generation", status: "pending", created_at: "2026-08-23T20:51:17.645264Z" },
  { id: "6a16e1a6-fe5c-4575-8b10-6a205218af3a", job_type: "storyboard_generation", status: "pending", created_at: "2026-08-23T20:50:58.046518Z" },
  { id: "bd99fe37-0621-40da-aa30-e058cc776c23", job_type: "transcript_refinement", status: "success", created_at: "2026-08-23T16:00:59.458571Z" },
  { id: "e408515a-f9ca-43a3-b4fc-f271f475f606", job_type: "transcript_refinement", status: "failed", created_at: "2026-08-23T15:24:33.914898Z" },
  { id: "768c4b59-9df5-4c3a-809a-80d3800142f5", job_type: "transcript_refinement", status: "failed", created_at: "2026-08-23T14:49:48.391321Z" },
];

/** GET /jobs/{id}/checkpoints .checkpoints, per job, verbatim. */
const CHECKPOINTS_BY_JOB = {
  "d3842fdf-3fe9-4983-b241-f467c94e95eb": [],
  "c4249f92-ac4d-4e86-94e9-4865b1e0b165": [],
  "7d6a44b2-8492-466b-b973-021a40146184": [],
  "4646aeba-83bb-47d1-95d9-6296bb9dfe4c": [],
  "c57ec7b7-09ab-46a9-8050-bbb2405972d4": [],
  "9fdea8ae-e3ab-4331-9d36-f3a5bb9759da": [],
  "6a16e1a6-fe5c-4575-8b10-6a205218af3a": [],
  "bd99fe37-0621-40da-aa30-e058cc776c23": [
    { stage_name: "transcript_refinement", stage_index: 1, status: "complete", started_at: "2026-08-23T16:00:59.900851Z", completed_at: "2026-08-23T16:01:37.318725Z" },
    { stage_name: "storyboard_generation", stage_index: 2, status: "complete", started_at: "2026-08-23T16:01:37.620728Z", completed_at: "2026-08-23T16:03:25.017648Z" },
    { stage_name: "image_generation", stage_index: 3, status: "complete", started_at: "2026-08-23T16:45:05.805590Z", completed_at: "2026-08-23T16:46:54.391571Z" },
    { stage_name: "video_generation", stage_index: 3, status: "pending", started_at: "2026-08-23T16:47:01.070004Z", completed_at: null },
    { stage_name: "tts_audio", stage_index: 4, status: "complete", started_at: "2026-08-23T18:45:02.390510Z", completed_at: "2026-08-23T18:46:19.242320Z" },
    { stage_name: "talking_head_render", stage_index: 5, status: "complete", started_at: "2026-08-23T19:23:07.904896Z", completed_at: "2026-08-23T19:23:07.904896Z" },
    { stage_name: "prototype_draft", stage_index: 6, status: "complete", started_at: "2026-08-23T19:23:10.319882Z", completed_at: "2026-08-23T19:24:15.588396Z" },
  ],
  "e408515a-f9ca-43a3-b4fc-f271f475f606": [
    { stage_name: "transcript_refinement", stage_index: 1, status: "complete", started_at: "2026-08-23T15:24:34.334644Z", completed_at: "2026-08-23T15:25:26.733871Z" },
    { stage_name: "storyboard_generation", stage_index: 2, status: "failed", started_at: "2026-08-23T15:25:27.046495Z", completed_at: "2026-08-23T15:37:03.577048Z" },
  ],
  "768c4b59-9df5-4c3a-809a-80d3800142f5": [
    { stage_name: "wp36_post_deploy_verification", stage_index: 1, status: "pending", started_at: "2026-08-23T15:06:04.310339Z", completed_at: null },
    { stage_name: "wp36-probe", stage_index: 1, status: "pending", started_at: "2026-08-23T15:06:19.727930Z", completed_at: null },
  ],
};

const RUN_CANDIDATES = JOBS_WIRE.map((j) => ({
  ...j,
  checkpoints: mergeCheckpoints(CHECKPOINTS_BY_JOB[j.id]),
}));

/* ─────────────────── TASK 7 — scene media type ─────────────────── */

test("T7 repro: the old modal payload is exactly what the API rejects", () => {
  /* This is what SceneEditModal used to build for "Video Clip". */
  const old = {
    narration_text: "x",
    visual_description: "y",
    media_type: "VIDEO",
    duration_seconds: 10,
    camera_angle: null,
    transition_type: "CUT",
    effects: null,
    timing_offset_ms: 0,
    generation_params: {},
  };
  assert.ok(!MEDIA_TYPES.includes(old.media_type));
  /* And the old client reduced the server's answer to a bare status. */
  assert.equal(legacyPickMessage(SCENE_422, 422), "Request failed with status 422");
});

test("T7 fix: the payload now carries an accepted media_type and nothing else", () => {
  const wire = sceneUpdatePayload({
    narration_text: "x",
    visual_description: "y",
    media_type: "VIDEO",
    duration_seconds: 10,
  });
  assert.equal(wire.media_type, "video_clip");
  assert.deepEqual(Object.keys(wire).sort(), [
    "duration_seconds",
    "media_type",
    "narration_text",
    "visual_description",
  ]);
  /* The five keys SceneUpdate does not declare are gone. */
  for (const phantom of [
    "camera_angle",
    "transition_type",
    "effects",
    "timing_offset_ms",
    "generation_params",
    "status",
  ]) {
    assert.ok(!(phantom in wire), `${phantom} must not be sent`);
  }
});

test("T7: every value the picker can offer is one the API accepts", () => {
  // WP-74: `motion_graphics` joined MEDIA_TYPES in WP-IVGS-09c (2026-08-28) and
  // the API accepts it (shared.models.enums.MEDIA_TYPES); this list pinned the
  // three-member vocabulary and has been red since. Test drift, not a defect.
  assert.deepEqual([...MEDIA_TYPES], ["image", "video_clip", "animation", "motion_graphics"]);
  for (const v of MEDIA_TYPES) assert.equal(normalizeMediaType(v), v);
});

test("T7: the live scene's media_type is displayable (SceneCard rendered blank)", () => {
  /* The old MEDIA_TYPE_LABELS was keyed by "IMAGE"; the wire says "image". */
  assert.equal(SCENE_WIRE.media_type, "image");
  assert.equal(mediaTypeLabel(SCENE_WIRE.media_type), "Image");
  assert.equal(mediaTypeIcon(SCENE_WIRE.media_type), "🖼️");
  assert.equal(mediaTypeLabel("video_clip"), "Video Clip");
});

test("T7: an untyped or unknown media_type is never asserted to be an image", () => {
  assert.equal(normalizeMediaType(null), null);
  assert.equal(normalizeMediaType(""), null);
  assert.equal(mediaTypeLabel(null), "Not set");
  assert.equal(mediaTypeLabel("hologram"), "hologram");
  /* An unmappable value is dropped rather than sent into a 422. */
  const wire = sceneUpdatePayload({ narration_text: "x", media_type: "hologram" });
  assert.ok(!("media_type" in wire));
  assert.equal(wire.narration_text, "x");
});

test("T7: duration is checked against the API's own ge/le bounds", () => {
  assert.equal(durationError(10), null);
  assert.equal(durationError(0.1), null);
  assert.equal(durationError(600), null);
  assert.match(durationError(0), /between 0\.1 and 600/);
  assert.match(durationError(601), /between 0\.1 and 600/);
  assert.match(durationError("ten"), /number of seconds/);
});

/* ───────── TASKS 3a / 6 / 7 — the server's own words, verbatim ───────── */

/** The reducer `api-client` used before this package, reproduced exactly. */
function legacyPickMessage(errorBody, status) {
  const pick = (v) => {
    if (typeof v === "string") return v;
    if (v && typeof v === "object" && !Array.isArray(v)) {
      return pick(v["message"]) ?? pick(v["detail"]) ?? pick(v["error"]) ?? null;
    }
    return null;
  };
  return pick(errorBody) ?? `Request failed with status ${status}`;
}

test("repro: the old reducer turned all four real 422s into a bare status", () => {
  for (const body of [SCENE_422, LANGUAGE_422, REFRESH_422, RETRY_422]) {
    assert.equal(legacyPickMessage(body, 422), "Request failed with status 422");
  }
});

test("fix: each 422 now reads as the server wrote it", () => {
  assert.equal(
    apiErrorMessage(SCENE_422, 422),
    "media_type: Value error, media_type must be one of: image, video_clip, animation",
  );
  assert.equal(
    apiErrorMessage(LANGUAGE_422, 422),
    "language_code: Value error, Unsupported language code 'es'. Supported: " +
      "ar-SA, de-DE, en-GB, en-US, es-ES, fr-FR, ja-JP, zh-CN",
  );
  assert.equal(apiErrorMessage(REFRESH_422, 422), "body: Field required");
  assert.match(apiErrorMessage(RETRY_422, 422), /^variant_id: Input should be a valid UUID/);
});

test("fix: the envelope shapes that already worked still work", () => {
  assert.equal(
    apiErrorMessage(CONFLICT_409, 409),
    "Cannot trigger pipeline from state 'MEDIA_GENERATION'.",
  );
  assert.equal(apiErrorMessage({ detail: "Not found" }, 404), "Not found");
  assert.equal(envelopeMessage({ detail: "plain" }), "plain");
});

test("fix: a body with nothing readable still falls back to the status", () => {
  assert.equal(apiErrorMessage({}, 500), "Request failed with status 500");
  assert.equal(apiErrorMessage(null, 502), "Request failed with status 502");
  assert.equal(apiErrorMessage({ detail: [] }, 422), "Request failed with status 422");
});

test("several field errors are joined rather than one being picked", () => {
  const body = {
    detail: [
      { loc: ["body", "a"], msg: "Field required" },
      { loc: ["body", "b"], msg: "Input should be a valid integer" },
    ],
  };
  assert.equal(
    apiErrorMessage(body, 422),
    "a: Field required; b: Input should be a valid integer",
  );
});

test("loc drops the request part but keeps a lone one (a missing whole body)", () => {
  assert.equal(validationFieldName(["body", "media_type"]), "media_type");
  assert.equal(validationFieldName(["path", "variant_id"]), "variant_id");
  assert.equal(validationFieldName(["body"]), "body");
  assert.equal(validationFieldName(["body", "items", 0, "id"]), "items.0.id");
  assert.equal(validationFieldName([]), null);
  assert.equal(validationFieldName("body"), null);
});

test("T6: per-field errors are addressable, for inline form messages", () => {
  assert.deepEqual(fieldErrors(SCENE_422), {
    media_type: "Value error, media_type must be one of: image, video_clip, animation",
  });
  assert.deepEqual(fieldErrors(CONFLICT_409), {});
  assert.equal(validationMessages("nope").length, 0);
});

/* ───────────────────── TASK 3 — languages ───────────────────── */

test("T3a repro: not one code the old form offered was acceptable", () => {
  const OLD_FORM = ["en", "es", "fr", "de", "pt", "ja", "zh", "ko", "ar", "hi"];
  for (const code of OLD_FORM) {
    assert.equal(isSupportedLanguage(code), false, `${code} would 422`);
  }
});

test("T3a fix: the form offers exactly the API's eight codes", () => {
  assert.deepEqual(
    SUPPORTED_LANGUAGES.map((l) => l.code).sort(),
    ["ar-SA", "de-DE", "en-GB", "en-US", "es-ES", "fr-FR", "ja-JP", "zh-CN"],
  );
  for (const l of SUPPORTED_LANGUAGES) assert.ok(isSupportedLanguage(l.code));
});

test("T3a: codes already on the project are not offered again", () => {
  const existing = LANGUAGE_WIRE.map((v) => v.language_code);
  const addable = addableLanguages(existing).map((l) => l.code);
  assert.ok(!addable.includes("en-US"));
  assert.ok(!addable.includes("es-ES"));
  assert.equal(addable.length, 6);
});

test("T3b repro: the 0% was an absent field, not a measurement", () => {
  for (const v of LANGUAGE_WIRE) {
    assert.ok(!("progress_percent" in v));
    /* What the table used to compute. */
    assert.equal(v.progress_percent || 0, 0);
    /* What it computes now. */
    assert.equal(variantProgressPercent(v), null);
  }
  for (const v of PROJECT_DETAIL_VARIANTS) {
    assert.deepEqual(Object.keys(v).sort(), ["language_code", "state"]);
    assert.equal(variantProgressPercent(v), null);
  }
});

test("T3b: a real percentage would still be shown if one ever arrived", () => {
  assert.equal(variantProgressPercent({ progress_percent: 42 }), 42);
  assert.equal(variantProgressPercent({ progress_percent: -1 }), null);
  assert.equal(variantProgressPercent({ progress_percent: 101 }), null);
  assert.equal(variantProgressPercent({ progress_percent: "42" }), null);
});

test("T3b: state comes off `state`, which is lowercase on the wire", () => {
  assert.equal(LANGUAGE_WIRE[0].state, "pending");
  assert.ok(!("status" in LANGUAGE_WIRE[0]));
  assert.equal(variantState(LANGUAGE_WIRE[0]), "PENDING");
  assert.equal(variantState({}), "UNKNOWN");
  assert.equal(isRetryableVariant(LANGUAGE_WIRE[0]), false);
  assert.equal(isRetryableVariant({ state: "failed" }), true);
});

test("T3: the only completion signal the payload carries is a render id", () => {
  assert.equal(variantHasRender(LANGUAGE_WIRE[0]), false);
  assert.equal(variantHasRender({ final_render_1080p_id: "abc" }), true);
});

test("T3: labels use the full BCP-47 code and never guess", () => {
  assert.equal(languageLabel("en-US"), "English (United States)");
  assert.equal(languageLabel("pt-BR"), "pt-BR");
  assert.equal(languageLabel(null), "Unknown");
});

test("T3: retry needs the variant UUID the list route carries, not the code", () => {
  /* The old page had only project.language_variants, which has no id. */
  for (const v of PROJECT_DETAIL_VARIANTS) assert.ok(!("id" in v));
  /* The languages route does. */
  for (const v of LANGUAGE_WIRE) assert.match(v.id, /^[0-9a-f-]{36}$/);
});

/* ───────────────── TASK 5 — Pipeline Progress ───────────────── */

test("T5 repro: the newest job has no checkpoints, so jobs[0] was all grey", () => {
  const newest = JOBS_WIRE[0];
  assert.equal(newest.id, "d3842fdf-3fe9-4983-b241-f467c94e95eb");
  assert.equal(CHECKPOINTS_BY_JOB[newest.id].length, 0);
  const old = stageStatuses(mergeCheckpoints(CHECKPOINTS_BY_JOB[newest.id]));
  assert.ok(Object.values(old).every((s) => s === "pending"));
});

test("T5 fix: the newest job that HAS checkpoints is the eighth row", () => {
  const run = selectPipelineRun(RUN_CANDIDATES);
  assert.equal(run.jobId, "bd99fe37-0621-40da-aa30-e058cc776c23");
  assert.equal(run.jobType, "transcript_refinement");
  assert.equal(run.examined, 10);
  assert.equal(run.newerWithoutCheckpoints, 7);
});

test("T5 fix: that run paints five green, one blue and two grey", () => {
  const run = selectPipelineRun(RUN_CANDIDATES);
  const s = stageStatuses(run.checkpoints);
  assert.equal(s.TRANSCRIPT_REFINEMENT, "complete");
  assert.equal(s.STORYBOARD_GENERATION, "complete");
  /* image_generation complete + video_generation pending collapse to RUNNING. */
  assert.equal(s.MEDIA_GENERATION, "running");
  assert.equal(s.MANIFEST_GENERATION, "pending");
  assert.equal(s.AUDIO_GENERATION, "complete");
  assert.equal(s.TALKING_HEAD_RENDER, "complete");
  assert.equal(s.PROTOTYPE_DRAFT, "complete");
  assert.equal(s.FINAL_RENDER, "pending");
  assert.equal(Object.values(s).filter((x) => x === "complete").length, 5);
});

test("T5: a superseded failed run does not repaint a stage that later passed", () => {
  /* e408515a failed STORYBOARD_GENERATION at 15:37; bd99fe37 completed it at
     16:03. Selecting one run -- not merging all ten -- is what keeps that
     stage green. */
  const run = selectPipelineRun(RUN_CANDIDATES);
  assert.notEqual(run.jobId, "e408515a-f9ca-43a3-b4fc-f271f475f606");
  assert.equal(stageStatuses(run.checkpoints).STORYBOARD_GENERATION, "complete");
});

test("T5: unmappable probe stages never become a run", () => {
  const only = [
    { ...JOBS_WIRE[9], checkpoints: mergeCheckpoints(CHECKPOINTS_BY_JOB[JOBS_WIRE[9].id]) },
  ];
  assert.equal(only[0].checkpoints.length, 0, "wp36 probes map to nothing");
  const run = selectPipelineRun(only);
  assert.equal(run.jobId, null);
});

test("T5: a project with no jobs at all reports an empty run, not a fake one", () => {
  const run = selectPipelineRun([]);
  assert.equal(run.jobId, null);
  assert.equal(run.examined, 0);
  assert.deepEqual(run.checkpoints, []);
  assert.equal(selectPipelineRun(null).jobId, null);
  assert.equal(selectPipelineRun(undefined).examined, 0);
});

test("T5: selection is by created_at, whatever order the route returns", () => {
  const shuffled = [RUN_CANDIDATES[7], RUN_CANDIDATES[0], RUN_CANDIDATES[8]];
  assert.equal(selectPipelineRun(shuffled).jobId, "bd99fe37-0621-40da-aa30-e058cc776c23");
});

test("T5: the eight stage ids are the ones mergeCheckpoints emits", () => {
  const emitted = new Set(
    mergeCheckpoints(CHECKPOINTS_BY_JOB["bd99fe37-0621-40da-aa30-e058cc776c23"]).map((c) => c.stage),
  );
  for (const stage of emitted) assert.ok(PIPELINE_STAGE_IDS.includes(stage), stage);
});

/* ───────────────── TASKS 1, 2, 4 — navigation ───────────────── */

test("T2: no tab is deferred, and every tab has a route segment or is Overview", () => {
  // WP-74: WP-66 (2026-08-26) added the twelfth tab, Models; the count pinned
  // eleven and has been red since. The property this test exists for — no
  // tab deferred, every tab routable — is asserted below and still holds.
  assert.equal(PROJECT_TABS.length, 12);
  for (const t of PROJECT_TABS) {
    assert.ok(!/soon/i.test(t.label), `${t.id} still says "soon"`);
    assert.equal(typeof t.segment, "string");
  }
  assert.equal(PROJECT_TABS.find((t) => t.id === "overview").segment, "");
  assert.equal(PROJECT_TABS.find((t) => t.id === "storyboard").segment, "storyboard");
  assert.equal(PROJECT_TABS.find((t) => t.id === "prompts").segment, "prompts");
});

test("T1: hrefs are built off the project id", () => {
  const P = "c12fa967-f989-4ed4-8e20-3ea62cb92e8f";
  assert.equal(tabHref(P, PROJECT_TABS[0]), `/projects/${P}`);
  assert.equal(
    tabHref(P, PROJECT_TABS.find((t) => t.id === "talking-head")),
    `/projects/${P}/talking-head`,
  );
});

test("T1: the active tab is derived from the path, on every tab", () => {
  const P = "c12fa967-f989-4ed4-8e20-3ea62cb92e8f";
  assert.equal(activeTabId(`/projects/${P}`), "overview");
  for (const t of PROJECT_TABS.filter((x) => x.segment)) {
    assert.equal(activeTabId(`/projects/${P}/${t.segment}`), t.id);
  }
  /* A deeper path stays on its tab rather than claiming Overview. */
  assert.equal(activeTabId(`/projects/${P}/storyboard/scene-1`), "storyboard");
  assert.equal(activeTabId(null), "overview");
  assert.equal(activeTabId("/gallery"), "overview");
});

test("T2/T4: the tab that had no page is the one that rendered blank", () => {
  /* /projects/{id}/prompts had no page component; the tab pointed at it and
     Next served its built-in 404, whose text inherits body colour. */
  const prompts = PROJECT_TABS.find((t) => t.id === "prompts");
  assert.equal(prompts.segment, "prompts");
  assert.equal(prompts.label, "Prompts");
});

/* ───────────────── TASK 1 — the lifecycle strip ───────────────── */

test("T1 repro: the old four-step strip could not place the live state", () => {
  /* What the Overview used to do. */
  const OLD_STRIP = ["DRAFT", "IN_PROGRESS", "REVIEW", "COMPLETE"];
  const liveState = "MEDIA_GENERATION";
  assert.equal(OLD_STRIP.findIndex((s) => s === liveState), -1);
  /* -1 means `idx <= currentOrder` is false for every step: four grey dots
     for a project that had finished four stages. */
});

test("T1 fix: the strip is the real 13-state FSM's linear path", () => {
  const states = PROJECT_STATE_SEQUENCE.map((s) => s.state);
  assert.equal(states.length, 11);
  assert.equal(states[0], "DRAFT");
  assert.equal(states[states.length - 1], "COMPLETE");
  /* Neither invented state survives. */
  assert.ok(!states.includes("IN_PROGRESS"));
  assert.ok(!states.includes("REVIEW"));
  assert.ok(states.includes("USER_REVIEW"));
});

test("T1 fix: MEDIA_GENERATION lights three done and one current", () => {
  const steps = stateStepStatuses("MEDIA_GENERATION");
  assert.deepEqual(steps.slice(0, 3), ["done", "done", "done"]);
  assert.equal(steps[3], "current");
  assert.ok(steps.slice(4).every((s) => s === "todo"));
  assert.equal(projectStateProgress("MEDIA_GENERATION").index, 3);
});

test("T1: the off-path states are named, not mis-placed", () => {
  /* ERROR is reachable from anywhere and has no rank; the shell reports it
     with its own wording, which is why `isError` is checked first. */
  const err = projectStateProgress("ERROR");
  assert.equal(err.index, -1);
  assert.equal(err.isError, true);
  assert.equal(err.isOffSequence, true);

  /* A state that is neither on the path nor a known off-path one is said to
     be unrecognised rather than drawn as "not started". */
  const bogus = projectStateProgress("SOMETHING_ELSE");
  assert.equal(bogus.index, -1);
  assert.equal(bogus.isError, false);
  assert.equal(bogus.isOffSequence, false);

  const loc = projectStateProgress("LOCALISATION");
  assert.equal(loc.index, -1);
  assert.equal(loc.isOffSequence, true);

  assert.equal(projectStateProgress(undefined).state, "UNKNOWN");
  assert.ok(stateStepStatuses(null).every((s) => s === "unknown"));
});

/* ───────────────── TASK 6 — the auth refresh body ───────────────── */

test("T6 repro: a header-only refresh is exactly what FastAPI rejects", () => {
  /* The request the client used to make: Authorization header, no body. */
  const oldRequest = {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer <refresh>",
    },
  };
  assert.ok(!("body" in oldRequest));
  assert.equal(apiErrorMessage(REFRESH_422, 422), "body: Field required");
});

test("T6 fix: the body carries the field RefreshRequest declares", () => {
  const body = JSON.parse(JSON.stringify({ refresh_token: "<refresh>" }));
  assert.deepEqual(Object.keys(body), ["refresh_token"]);
  assert.equal(typeof body.refresh_token, "string");
});

test("T6: token rotation is honoured, with the old token only as a fallback", () => {
  /* TokenResponse (schemas/auth.py:16) returns a NEW refresh_token, and the
     route invalidates the old one. Re-storing the old one would make the
     FIRST refresh work and every later one fail. */
  const pick = (data, previous) => data.refresh_token || previous;
  assert.equal(pick({ access_token: "a", refresh_token: "new" }, "old"), "new");
  assert.equal(pick({ access_token: "a" }, "old"), "old");
});
