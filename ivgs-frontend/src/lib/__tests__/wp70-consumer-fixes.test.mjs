/**
 * WP-70 — CONSUMER FIXES 1. One block per defect from the WP-69 report §2.
 *
 * The frontend has no component test runner (no jest/vitest; `test:logic`
 * compiles src/lib and runs node --test), and every defect here is a client
 * reading or calling something the API does not send or serve. So each test
 * reads the CONSUMER's source and checks it against the PRODUCER's source —
 * the Pydantic response model, the FastAPI route table — rather than against a
 * hand-typed fixture that would only restate the fix. Each fails on the
 * pre-fix tree and passes after; the report records both runs.
 */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FRONT = path.resolve(HERE, "../..");            // ivgs-frontend/src
const REPO = path.resolve(HERE, "../../../..");        // /opt/ivgs
const read = (p) => fs.readFileSync(p, "utf8");
const src = (rel) => read(path.join(FRONT, rel));
const api = (rel) => read(path.join(REPO, "ivgs-api", rel));

/** Field names a Pydantic response model declares (annotated assignments). */
function pydanticFields(pySource, className) {
  const m = pySource.match(
    new RegExp(`class ${className}\\(BaseModel\\):[\\s\\S]*?(?=\\nclass |$)`)
  );
  assert.ok(m, `${className} not found`);
  return new Set(
    [...m[0].matchAll(/^\s{4}([a-z_][a-z0-9_]*)\s*:/gm)]
      .map((x) => x[1])
      .filter((n) => n !== "model_config")
  );
}

/** Field names a TS interface declares. */
function tsFields(tsSource, ifaceName) {
  const m = tsSource.match(
    new RegExp(`export interface ${ifaceName} \\{([\\s\\S]*?)\\n\\}`)
  );
  assert.ok(m, `${ifaceName} not found`);
  return new Set(
    [...m[1].matchAll(/^\s+([a-z_][a-z0-9_]*)\??\s*:/gm)].map((x) => x[1])
  );
}

// `row.<field>` reads inside the JSX cell that follows a "{/* Label */}" JSX comment.
function cellReads(tsx, label, rowVar) {
  const at = tsx.indexOf(`{/* ${label} */}`);
  assert.ok(at >= 0, `no cell labelled ${label}`);
  const cell = tsx.slice(at, tsx.indexOf("</td>", at));
  return [...cell.matchAll(new RegExp(`\\b${rowVar}\\.([a-z_][a-z0-9_]*)`, "g"))].map(
    (x) => x[1]
  );
}

/* ── S11: DLQ table vs DLQMessageResponse ─────────────────────────────── */

test("S11: the DLQ table's category badge and error text read fields the API sends", () => {
  const emitted = pydanticFields(api("app/schemas/dlq.py"), "DLQMessageResponse");
  const table = src("components/monitoring/DLQTable.tsx");

  // A row as the API would send it: every emitted field carries a value.
  const wire = Object.fromEntries([...emitted].map((f) => [f, `<${f}>`]));

  const badge = cellReads(table, "Category", "msg").map((f) => wire[f]);
  const error = cellReads(table, "Error Message", "msg").map((f) => wire[f]);
  const retries = cellReads(table, "Retry Count", "msg").map((f) => wire[f]);
  const entered = cellReads(table, "Entered DLQ", "msg").map((f) => wire[f]);

  assert.ok(badge.length && badge.every(Boolean), `category badge reads ${badge}`);
  assert.ok(error.length && error.every(Boolean), `error cell reads ${error}`);
  assert.ok(retries.length && retries.every(Boolean), `retry cell reads ${retries}`);
  assert.ok(entered.length && entered.every(Boolean), `entered-at cell reads ${entered}`);
});

test("S11: every field TS DLQMessage declares is one DLQMessageResponse emits", () => {
  const emitted = pydanticFields(api("app/schemas/dlq.py"), "DLQMessageResponse");
  const declared = tsFields(src("types/monitoring.ts"), "DLQMessage");
  const missing = [...declared].filter((f) => !emitted.has(f));
  assert.deepEqual(missing, [], `declared but never sent: ${missing}`);
});
