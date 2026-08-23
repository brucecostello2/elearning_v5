/**
 * WP-35 regression test — the project detail page crash.
 *
 * Runs on Node's BUILT-IN test runner (`node --test`). The frontend has no test
 * framework and none was installed for this; `npm run test:logic` compiles the
 * pure helper with the repo's own tsc and tests the compiled output, so this
 * exercises the real shipped code rather than a copy of it.
 *
 *     cd ivgs-frontend && npm run test:logic
 */
import test from "node:test";
import assert from "node:assert/strict";
import { unwrapList, unwrapObject } from "../../../.test-build/unwrap.js";

/** The EXACT payload the API serialises for a project with no jobs. Captured
 *  2026-08-23 from PaginatedResponse[JobResponse] inside ivgs-fastapi. */
const JOBS_ENVELOPE_EMPTY = {
  data: [], total: 0, page: 1, per_page: 50, pages: 0, has_more: false,
};
const JOBS_ENVELOPE_FULL = {
  data: [{ id: "j1", status: "RUNNING" }, { id: "j2", status: "COMPLETE" }],
  total: 2, page: 1, per_page: 50, pages: 1, has_more: false,
};

test("THE CRASH: the pre-fix code throws on the real wire payload", () => {
  // jobsFetcher returned response.data === the envelope, and useJobs did
  // `latestData?.some(...)`. Optional chaining does not help: the value is
  // present, it is simply not an array.
  assert.throws(
    () => JOBS_ENVELOPE_EMPTY?.some((j) => j.status === "RUNNING"),
    TypeError,
    "the envelope must not be .some()-able - that is the reported crash",
  );
});

test("the fix: unwrapList turns the same payload into a usable array", () => {
  assert.deepEqual(unwrapList(JOBS_ENVELOPE_EMPTY), []);
  assert.doesNotThrow(() => unwrapList(JOBS_ENVELOPE_EMPTY).some(() => true));
  assert.equal(unwrapList(JOBS_ENVELOPE_FULL).length, 2);
  assert.equal(unwrapList(JOBS_ENVELOPE_FULL)[0].id, "j1");
});

test("unwrapList accepts a bare array unchanged (the transcripts shape)", () => {
  // GET /projects/{id}/transcripts is response_model=List[TranscriptResponse].
  const bare = [{ id: "t1" }, { id: "t2" }];
  assert.deepEqual(unwrapList(bare), bare);
});

test("unwrapList is total - it never throws and never returns a non-array", () => {
  for (const junk of [undefined, null, {}, 42, "x", true, { data: null },
                      { data: "not-a-list" }, new Date(0)]) {
    const out = unwrapList(junk);
    assert.ok(Array.isArray(out), `unwrapList(${JSON.stringify(junk)}) must be an array`);
    assert.equal(out.length, 0);
  }
});

test("the PipelineTracker guard now holds against a non-array", () => {
  // Pre-fix: `!jobs || jobs.length === 0` let the envelope through, because an
  // object is truthy and its .length is undefined.
  const jobs = JOBS_ENVELOPE_EMPTY;
  assert.equal(!jobs || jobs.length === 0, false, "the old guard is defeated");
  assert.equal(!Array.isArray(jobs) || jobs.length === 0, true, "Array.isArray holds");
});

test("unwrapObject keeps the F9 detail-route fix intact", () => {
  // GET /projects/{id} is bare ProjectResponse. Reading .data.data on it is what
  // F9 fixed; unwrapObject must not reintroduce that.
  const project = { id: "p1", name: "double digit multiplication", state: "DRAFT" };
  assert.deepEqual(unwrapObject(project), project);
  assert.equal(unwrapObject(undefined), undefined);
  assert.equal(unwrapObject(null), undefined);
  // ...but it still unwraps a genuinely wrapped object
  assert.deepEqual(unwrapObject({ data: project }), project);
});
