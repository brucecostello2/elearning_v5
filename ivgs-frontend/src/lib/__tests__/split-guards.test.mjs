/**
 * WP-40 Task 5 / ledger P1.4r — "Cannot read properties of undefined
 * (reading 'split')" on the project detail page chunk.
 *
 * WP-38 §3 produced a shortlist of unguarded `.split(` sites but could not
 * identify the firing one without a browser. It is
 * `TranscriptEditor.tsx:33`, and the wire proves it:
 *
 *   GET /api/v1/projects/{id}/transcripts -> TranscriptResponse
 *   (schemas/transcript.py:13) sends id, project_id, sequence_order,
 *   original_asset_id, refined_text, language_code, created_at, updated_at.
 *
 * No `original_text` -- and no `original_text` COLUMN on the transcripts
 * table either (verified: \d transcripts). The frontend type nevertheless
 * declared `original_text: string`, the page passed it straight into
 * TranscriptEditor, and `original.split("\n")` threw on undefined.
 *
 * TRANSCRIPT_WIRE below is the live row for project c12fa967, 2026-08-23.
 */
import test from "node:test";
import assert from "node:assert/strict";
import {
  asText,
  hasText,
  lineCount,
  splitLines,
  splitOn,
} from "../../../.test-build/text.js";

/** The live transcript row, verbatim keys. */
const TRANSCRIPT_WIRE = {
  id: "4d70b8a8-3ce3-40a4-9454-5734ccd011ef",
  project_id: "c12fa967-f989-4ed4-8e20-3ea62cb92e8f",
  sequence_order: 1,
  original_asset_id: "814dfcd4-b042-42b7-babf-5a8743b7fbad",
  refined_text: "Let's learn how to multiply two-digit numbers.\nReady?",
  language_code: "en-US",
  created_at: "2026-08-23T08:14:32.214183Z",
  updated_at: "2026-08-23T16:01:37.268893Z",
};

test("THE BUG: original_text is not on the wire, and .split threw on it", () => {
  assert.equal(
    Object.prototype.hasOwnProperty.call(TRANSCRIPT_WIRE, "original_text"),
    false
  );
  assert.equal(TRANSCRIPT_WIRE.original_text, undefined);

  // the exact call the component made
  assert.throws(
    () => TRANSCRIPT_WIRE.original_text.split("\n"),
    /Cannot read properties of undefined \(reading 'split'\)/
  );
});

test("the fix: splitLines is total over every absent shape", () => {
  assert.deepEqual(splitLines(TRANSCRIPT_WIRE.original_text), []);
  assert.deepEqual(splitLines(null), []);
  assert.deepEqual(splitLines(undefined), []);
  assert.deepEqual(splitLines(""), []);
  assert.deepEqual(splitLines({}), []);
  assert.deepEqual(splitLines(42), ["42"]);
});

test("real text still splits exactly as before", () => {
  assert.deepEqual(splitLines(TRANSCRIPT_WIRE.refined_text), [
    "Let's learn how to multiply two-digit numbers.",
    "Ready?",
  ]);
  assert.equal(lineCount(TRANSCRIPT_WIRE.refined_text), 2);
});

test("the diff renders an empty left pane instead of crashing", () => {
  // TranscriptEditor.computeLineDiff, reduced to its two split calls
  const origLines = splitLines(TRANSCRIPT_WIRE.original_text);
  const refLines = splitLines(TRANSCRIPT_WIRE.refined_text);
  const maxLen = Math.max(origLines.length, refLines.length);
  assert.equal(origLines.length, 0);
  assert.equal(maxLen, 2, "the refined side still renders both its lines");
});

test("lineCount drives the textarea rows without throwing", () => {
  // TranscriptEditor.tsx:117 -- rows={Math.max(10, ...)}
  assert.equal(Math.max(10, lineCount(undefined)), 10);
  assert.equal(Math.max(10, lineCount(null)), 10);
  assert.equal(Math.max(10, lineCount("a\nb\nc")), 10);
});

test("PromptHistory: a version with no body diffs to nothing", () => {
  // PromptHistory.tsx:48,49 -- computeUnifiedDiff(old, new)
  assert.deepEqual(splitLines(undefined), []);
  assert.deepEqual(splitLines(null), []);
  // PromptHistory.tsx:476 -- "{n} chars · {m} lines"
  assert.equal(asText(null).length, 0);
  assert.equal(lineCount(null), 0);
});

test("PromptEditor: a null prompt_text becomes an empty template", () => {
  // PromptEditor.tsx:349 initial state, then :378 templateStats
  const templateContent = asText(null) || "";
  assert.equal(templateContent, "");
  assert.equal(lineCount(templateContent), 0);
  assert.equal(asText(templateContent).length, 0);
});

test("AssetUploader: an absent accept prop means accept anything", () => {
  // AssetUploader.tsx:51 -- accept.split(",")
  assert.deepEqual(splitOn(undefined, ","), []);
  assert.deepEqual(splitOn(null, ","), []);
  assert.deepEqual(splitOn("image/*,video/*", ","), ["image/*", "video/*"]);
});

test("AssetUploader: an extensionless filename yields no extension", () => {
  // AssetUploader.tsx:52 -- `.${file.name.split(".").pop()}`
  const parts = splitOn("README", ".");
  assert.deepEqual(parts, ["README"]);
  assert.equal(parts.length > 1 ? `.${parts.pop()}` : "", "");

  const dotted = splitOn("scene_03.PNG", ".");
  assert.equal(`.${String(dotted.pop()).toLowerCase()}`, ".png");

  // and the pathological cases do not throw
  assert.deepEqual(splitOn("", "."), []);
  assert.deepEqual(splitOn(undefined, "."), []);
});

test("asText and hasText are total", () => {
  assert.equal(asText("x"), "x");
  assert.equal(asText(null), "");
  assert.equal(asText(undefined), "");
  assert.equal(asText(7), "7");
  assert.equal(asText({}), "");
  assert.equal(asText([]), "");
  assert.equal(hasText("x"), true);
  assert.equal(hasText(""), false);
  assert.equal(hasText(null), false);
});
