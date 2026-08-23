/**
 * WP-38 — the storyboard page showed "No scenes yet" over 18 real scenes.
 *
 * GET /api/v1/projects/{id}/scenes is response_model=List[SceneResponse]
 * (storyboard.py:33) - a BARE ARRAY. Verified live 2026-08-23 for project
 * c12fa967: HTTP 200, top-level list, length 18, no `scenes` key. The fetcher
 * read `response.data.scenes`, which is undefined on an array.
 *
 * Third direction of the same shape defect: F9 over-unwrapped a bare OBJECT,
 * WP-35's jobs/assets under-unwrapped an ENVELOPE, this over-unwrapped an ARRAY.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { unwrapList } from "../../../.test-build/unwrap.js";

/** The live wire shape, trimmed to the keys the page uses. */
const WIRE = Array.from({ length: 18 }, (_, i) => ({
  id: `scene-${i}`, project_id: "c12fa967", scene_index: i,
  narration_text: "n", visual_description: "v",
  media_type: "image", duration_seconds: 10,
}));

test("THE BUG: reading .scenes off a bare array yields undefined", () => {
  assert.equal(WIRE.scenes, undefined);
  // and that is exactly what drove the empty state
  const scenes = WIRE.scenes;
  assert.equal(!scenes || scenes.length === 0, true, "renders 'No scenes yet'");
});

test("the fix returns all 18 scenes", () => {
  const scenes = unwrapList(WIRE);
  assert.equal(scenes.length, 18);
  assert.equal(scenes[0].scene_index, 0);
  assert.equal(scenes[17].scene_index, 17);
  assert.equal(!scenes || scenes.length === 0, false, "no longer empty");
});

test("it still works if the route ever gains an envelope", () => {
  assert.equal(unwrapList({ data: WIRE, total: 18 }).length, 18);
});

test("a genuinely empty storyboard is still empty, not an error", () => {
  assert.deepEqual(unwrapList([]), []);
  assert.deepEqual(unwrapList(undefined), []);
});
