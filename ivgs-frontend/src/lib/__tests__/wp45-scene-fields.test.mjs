/**
 * WP-45 Task 6(b)/(d) — the five scene fields, and the thumbnail path.
 *
 * WP-43 D-2 found the Edit Scene modal sending nine keys to a schema that
 * declared four. Pydantic drops keys a model does not declare, silently, with a
 * 200 — so camera_angle, transition_type, effects, timing_offset_ms and
 * generation_params were serialised, sent and discarded while the dialog looked
 * exactly as though it had saved them. WP-43 could only label them; WP-45
 * migration 0028 gave them columns and SceneUpdate declares them.
 *
 * These tests pin what `sceneUpdatePayload` may emit, because the failure mode
 * is silent on both sides of the wire and no HTTP status ever revealed it.
 */
import test from "node:test";
import assert from "node:assert/strict";
import {
  sceneUpdatePayload,
  timingOffsetError,
  EFFECTS_MAX,
  TIMING_OFFSET_MIN_MS,
  TIMING_OFFSET_MAX_MS,
} from "../../../.test-build/scenes.js";
import {
  assetThumbnailPath,
  THUMBNAIL_MIN_WIDTH,
  THUMBNAIL_MAX_WIDTH,
} from "../../../.test-build/media.js";

/* ── The five fields reach the wire ─────────────────────────────────────── */

test("all nine declared keys survive when the draft carries them", () => {
  const body = sceneUpdatePayload({
    narration_text: "Multiply the tens first.",
    visual_description: "A worked sum on a board",
    media_type: "image",
    duration_seconds: 12,
    camera_angle: "wide",
    transition_type: "fade",
    effects: ["ken_burns", "vignette"],
    timing_offset_ms: -250,
    generation_params: { seed: 42 },
  });

  assert.equal(body.camera_angle, "wide");
  assert.equal(body.transition_type, "fade");
  assert.deepEqual(body.effects, ["ken_burns", "vignette"]);
  assert.equal(body.timing_offset_ms, -250);
  assert.deepEqual(body.generation_params, { seed: 42 });
  assert.equal(Object.keys(body).length, 9);
});

test("THE OLD BUG: the five keys used to be absent from the body entirely", () => {
  // The regression this guards. Before WP-45 the payload builder emitted four
  // keys by construction, so no request could have carried the other five.
  const body = sceneUpdatePayload({
    narration_text: "n",
    camera_angle: "close-up",
  });
  assert.ok("camera_angle" in body, "camera_angle must reach the wire now");
});

/* ── Omitted vs cleared ─────────────────────────────────────────────────── */

test("an omitted field is left off the body, not sent as null", () => {
  // The route reads model_dump(exclude_unset=True): a key that is present with
  // a null value CLEARS the column. Sending null for a field the operator never
  // touched would wipe it on every save.
  const body = sceneUpdatePayload({ narration_text: "only this" });
  assert.equal("camera_angle" in body, false);
  assert.equal("transition_type" in body, false);
  assert.equal("effects" in body, false);
  assert.equal("timing_offset_ms" in body, false);
  assert.equal("generation_params" in body, false);
});

test("an explicitly cleared field is sent as null", () => {
  const body = sceneUpdatePayload({
    camera_angle: null,
    transition_type: null,
    effects: null,
    timing_offset_ms: null,
    generation_params: null,
  });
  assert.equal(body.camera_angle, null);
  assert.equal(body.transition_type, null);
  assert.equal(body.effects, null);
  assert.equal(body.timing_offset_ms, null);
  assert.equal(body.generation_params, null);
});

test("a whitespace-only string clears rather than storing blanks", () => {
  const body = sceneUpdatePayload({ camera_angle: "   " });
  assert.equal(body.camera_angle, null);
});

/* ── The client mirrors the server's own bounds ─────────────────────────── */

test("blank and non-string effects are dropped, and the list is capped", () => {
  const body = sceneUpdatePayload({
    effects: ["ok", "", "   ", 7, null, "also_ok"],
  });
  assert.deepEqual(body.effects, ["ok", "also_ok"]);

  const many = sceneUpdatePayload({
    effects: Array.from({ length: EFFECTS_MAX + 10 }, (_, i) => `e${i}`),
  });
  assert.equal(many.effects.length, EFFECTS_MAX);
});

test("timing offset is rounded to a whole millisecond", () => {
  assert.equal(sceneUpdatePayload({ timing_offset_ms: 12.7 }).timing_offset_ms, 13);
});

test("a non-object generation_params is refused rather than sent into a 422", () => {
  // The route requires a JSON object. A list or a bare string would 422 the
  // whole save, including the narration edit the operator actually came for.
  assert.equal(sceneUpdatePayload({ generation_params: [1, 2] }).generation_params, null);
});

test("timingOffsetError matches the schema's own bounds and wording", () => {
  assert.equal(timingOffsetError(0), null);
  assert.equal(timingOffsetError(TIMING_OFFSET_MIN_MS), null);
  assert.equal(timingOffsetError(TIMING_OFFSET_MAX_MS), null);
  assert.equal(timingOffsetError(null), null, "absent is not an error");
  assert.equal(timingOffsetError(undefined), null);
  assert.ok(timingOffsetError(TIMING_OFFSET_MAX_MS + 1));
  assert.ok(timingOffsetError(TIMING_OFFSET_MIN_MS - 1));
  assert.ok(timingOffsetError("soon"));
  assert.ok(timingOffsetError(Number.NaN));
});

test("media_type is still dropped when it normalises to nothing (WP-43 Task 7)", () => {
  // Not a new rule; pinned so extending the payload did not quietly break it.
  const body = sceneUpdatePayload({
    narration_text: "n",
    media_type: "TALKING_HEAD",
  });
  assert.equal("media_type" in body, false);
  assert.equal(body.narration_text, "n");
});

/* ── Thumbnails ─────────────────────────────────────────────────────────── */

test("the thumbnail path is the asset-scoped route, with a width", () => {
  assert.equal(
    assetThumbnailPath("abc-123", 480),
    "/api/v1/assets/abc-123/thumbnail?w=480",
  );
});

test("width is clamped to the route's own bounds, never sent out of range", () => {
  // A 422 on a thumbnail is a blank card, so the client clamps instead.
  assert.ok(assetThumbnailPath("a", 4).endsWith(`w=${THUMBNAIL_MIN_WIDTH}`));
  assert.ok(assetThumbnailPath("a", 9999).endsWith(`w=${THUMBNAIL_MAX_WIDTH}`));
  assert.ok(assetThumbnailPath("a", 320.6).endsWith("w=321"));
});
