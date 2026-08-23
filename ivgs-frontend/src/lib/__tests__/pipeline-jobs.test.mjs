/**
 * WP-40 Task 2 — the /monitoring Pipeline Tracker listed 16 jobs with every
 * counter at 0, AVG DURATION "—", and rows labelled with PROJECT ids.
 *
 * One cause: `usePipelineJobs` fetched `/api/v1/projects?expand=jobs` and
 * returned `data.data`, which is the PROJECT list. `expand` is not a
 * parameter that route implements.
 *
 * PROJECT_WIRE and JOB_WIRE below are the real responses, captured
 * 2026-08-23 for project c12fa967.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { unwrapList } from "../../../.test-build/unwrap.js";
import {
  averageDurationMs,
  checkpointStage,
  isTerminalStatus,
  jobDurationMs,
  mergeCheckpoints,
  normalizeJobStatus,
} from "../../../.test-build/jobs.js";

/** What /api/v1/projects?expand=jobs actually returns (trimmed to 1 of 16). */
const PROJECT_WIRE = {
  data: [
    {
      id: "c12fa967-f989-4ed4-8e20-3ea62cb92e8f",
      name: "double digit multiplication",
      state: "MEDIA_GENERATION",
      scene_count: 18,
      created_at: "2026-08-23T08:14:31.873292Z",
      active_job: null,
    },
  ],
  total: 16,
};

/** What /api/v1/projects/{id}/jobs actually returns. */
const JOB_WIRE = {
  data: [
    {
      id: "bd99fe37-0621-40da-aa30-e058cc776c23",
      project_id: "c12fa967-f989-4ed4-8e20-3ea62cb92e8f",
      job_type: "transcript_refinement",
      status: "success",
      started_at: null,
      completed_at: null,
      created_at: "2026-08-23T16:00:59.458571Z",
    },
    {
      id: "e408515a-f9ca-43a3-b4fc-f271f475f606",
      project_id: "c12fa967-f989-4ed4-8e20-3ea62cb92e8f",
      job_type: "transcript_refinement",
      status: "failed",
      started_at: null,
      completed_at: null,
      created_at: "2026-08-23T15:24:33.914898Z",
    },
  ],
  total: 2,
};

/** What /api/v1/jobs/{id}/checkpoints actually returns. */
const CHECKPOINT_WIRE = {
  job_id: "bd99fe37-0621-40da-aa30-e058cc776c23",
  total_stages: 7,
  checkpoints: [
    {
      stage_name: "transcript_refinement", status: "complete",
      started_at: "2026-08-23T16:00:59.900851Z",
      completed_at: "2026-08-23T16:01:37.318725Z",
    },
    {
      stage_name: "storyboard_generation", status: "complete",
      started_at: "2026-08-23T16:01:37.620728Z",
      completed_at: "2026-08-23T16:03:25.017648Z",
    },
    {
      stage_name: "image_generation", status: "complete",
      started_at: "2026-08-23T16:45:05.805590Z",
      completed_at: "2026-08-23T16:46:54.391571Z",
    },
    {
      stage_name: "video_generation", status: "pending",
      started_at: "2026-08-23T16:47:01.070004Z",
      completed_at: null,
    },
    {
      stage_name: "tts_audio", status: "complete",
      started_at: "2026-08-23T18:45:02.390510Z",
      completed_at: "2026-08-23T18:46:19.242320Z",
    },
    {
      stage_name: "talking_head_render", status: "complete",
      started_at: "2026-08-23T19:23:07.904896Z",
      completed_at: "2026-08-23T19:23:07.904896Z",
    },
    {
      stage_name: "prototype_draft", status: "complete",
      started_at: "2026-08-23T19:23:10.319882Z",
      completed_at: "2026-08-23T19:24:15.588396Z",
    },
  ],
};

test("THE BUG: the tracker was listing projects, not jobs", () => {
  const rows = unwrapList(PROJECT_WIRE);
  assert.equal(rows.length, 1, "one of the 16 'jobs' the page listed");

  // a project has no `status`, so every counter filter matched nothing
  assert.equal(rows[0].status, undefined);
  assert.equal(rows.filter((r) => r.status === "RUNNING").length, 0);
  assert.equal(rows.filter((r) => r.status === "COMPLETE").length, 0);
  assert.equal(rows.filter((r) => r.status === "ERROR").length, 0);
  assert.equal(rows.filter((r) => r.status === "PENDING").length, 0);

  // and no timestamps, so the average was 0 and formatted as "—"
  assert.equal(rows[0].started_at, undefined);
  assert.equal(rows[0].completed_at, undefined);

  // "Job #c12fa967" -- the label came from the PROJECT id
  assert.equal(rows[0].id.slice(0, 8), "c12fa967");

  // `expand=jobs` was ignored: there is no jobs key to read
  assert.equal(rows[0].jobs, undefined);
});

test("SECOND BUG: even against real jobs the counters would read 0", () => {
  const jobs = unwrapList(JOB_WIRE);
  // the wire is lowercase; the page compared against COMPLETE / ERROR
  assert.equal(jobs[0].status, "success");
  assert.equal(jobs[1].status, "failed");
  assert.equal(jobs.filter((j) => j.status === "COMPLETE").length, 0);
  assert.equal(jobs.filter((j) => j.status === "ERROR").length, 0);
});

test("the fix: normalised statuses make the counters count", () => {
  const jobs = unwrapList(JOB_WIRE).map((j) => ({
    ...j,
    status: normalizeJobStatus(j.status),
  }));
  assert.equal(jobs.filter((j) => j.status === "COMPLETE").length, 1);
  assert.equal(jobs.filter((j) => j.status === "ERROR").length, 1);
  assert.equal(jobs.filter((j) => j.status === "RUNNING").length, 0);
});

test("status normalisation covers the whole wire vocabulary", () => {
  assert.equal(normalizeJobStatus("pending"), "PENDING");
  assert.equal(normalizeJobStatus("running"), "RUNNING");
  assert.equal(normalizeJobStatus("success"), "COMPLETE");
  assert.equal(normalizeJobStatus("failed"), "ERROR");
  assert.equal(normalizeJobStatus("REVOKED"), "CANCELLED");
  assert.equal(normalizeJobStatus(null), "UNKNOWN");
  assert.equal(normalizeJobStatus(undefined), "UNKNOWN");
  assert.equal(normalizeJobStatus("something-new"), "UNKNOWN");
});

test("terminal jobs are the ones worth measuring", () => {
  assert.equal(isTerminalStatus("success"), true);
  assert.equal(isTerminalStatus("failed"), true);
  assert.equal(isTerminalStatus("running"), false);
  assert.equal(isTerminalStatus("pending"), false);
});

test("THIRD BUG: job-level timing does not exist, so duration needs checkpoints", () => {
  const job = unwrapList(JOB_WIRE)[0];
  // nothing in ivgs-api, ivgs-workers or shared/ writes these; all 20 rows null
  assert.equal(job.started_at, null);
  assert.equal(job.completed_at, null);
  assert.equal(jobDurationMs(job, null), null, "unknowable without checkpoints");

  const ms = jobDurationMs(job, CHECKPOINT_WIRE.checkpoints);
  assert.ok(ms !== null, "the checkpoint span IS knowable");
  // 16:00:59.900851 -> 19:24:15.588396 is a shade over 3h23m
  assert.ok(ms > 3 * 3600_000 && ms < 3.5 * 3600_000, `got ${ms}ms`);
});

test("job timestamps win when they eventually exist", () => {
  const job = {
    started_at: "2026-08-23T16:00:00.000Z",
    completed_at: "2026-08-23T16:02:00.000Z",
  };
  assert.equal(jobDurationMs(job, CHECKPOINT_WIRE.checkpoints), 120_000);
});

test("the average distinguishes 'unrecorded' from 'zero'", () => {
  assert.equal(averageDurationMs([]), null);
  assert.equal(averageDurationMs([null, null]), null, "not 0 -- unknown");
  assert.equal(averageDurationMs([1000, 3000]), 2000);
  assert.equal(averageDurationMs([1000, null, 3000]), 2000, "nulls excluded");
  assert.equal(averageDurationMs([0]), 0, "a measured zero is still a measurement");
});

test("worker stage names map onto the eight stages the DAG draws", () => {
  assert.equal(checkpointStage("transcript_refinement"), "TRANSCRIPT_REFINEMENT");
  assert.equal(checkpointStage("image_generation"), "MEDIA_GENERATION");
  assert.equal(checkpointStage("video_generation"), "MEDIA_GENERATION");
  assert.equal(checkpointStage("tts_audio"), "AUDIO_GENERATION");
  assert.equal(checkpointStage("prototype_draft"), "PROTOTYPE_DRAFT");
  assert.equal(checkpointStage("not_a_stage"), null);
  assert.equal(checkpointStage(null), null);
});

test("checkpoints collapse onto display stages without overclaiming progress", () => {
  const merged = mergeCheckpoints(CHECKPOINT_WIRE.checkpoints);
  const byStage = Object.fromEntries(merged.map((c) => [c.stage, c]));

  assert.equal(byStage.TRANSCRIPT_REFINEMENT.status, "COMPLETE");
  assert.equal(byStage.STORYBOARD_GENERATION.status, "COMPLETE");
  assert.equal(byStage.AUDIO_GENERATION.status, "COMPLETE");
  assert.equal(byStage.PROTOTYPE_DRAFT.status, "COMPLETE");

  // image_generation (complete) + video_generation (pending) share one box,
  // and the box must NOT read complete
  assert.equal(byStage.MEDIA_GENERATION.status, "RUNNING");
  assert.equal(
    byStage.MEDIA_GENERATION.completed_at,
    null,
    "still open while a member is open"
  );
  assert.equal(
    byStage.MEDIA_GENERATION.started_at,
    "2026-08-23T16:45:05.805Z",
    "spans from the earliest member"
  );

  // stages the run never reached are simply absent, not invented
  assert.equal(byStage.FINAL_RENDER, undefined);
  assert.equal(byStage.MANIFEST_GENERATION, undefined);
});

test("a failure anywhere in a merged box makes the box failed", () => {
  const merged = mergeCheckpoints([
    { stage_name: "image_generation", status: "complete",
      started_at: "2026-08-23T16:00:00Z", completed_at: "2026-08-23T16:01:00Z" },
    { stage_name: "video_generation", status: "failed",
      started_at: "2026-08-23T16:01:00Z", completed_at: "2026-08-23T16:02:00Z" },
  ]);
  assert.equal(merged.length, 1);
  assert.equal(merged[0].stage, "MEDIA_GENERATION");
  assert.equal(merged[0].status, "FAILED");
});

test("checkpoint merging is total -- it never throws", () => {
  assert.deepEqual(mergeCheckpoints(null), []);
  assert.deepEqual(mergeCheckpoints(undefined), []);
  assert.deepEqual(mergeCheckpoints([]), []);
  assert.deepEqual(mergeCheckpoints([{}, { stage_name: null }]), []);
  assert.deepEqual(mergeCheckpoints("not an array"), []);
});
