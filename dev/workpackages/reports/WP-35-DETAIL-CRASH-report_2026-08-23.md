# WP-35-DETAIL-CRASH — the project detail page crashes on render

| | |
|---|---|
| **Reported** | 2026-08-23, operator. `/projects/[id]` crashes immediately after creating a project through the fixed New Project form. Component stack points into `app/projects/[id]/page.js`. |
| **HEAD at start** | `0a87f36` |
| **Date** | 2026-08-23 |
| **Subject row** | `c12fa967-f989-4ed4-8e20-3ea62cb92e8f` — "double digit multiplication", the newest `projects` row, created 08:14:31Z |
| **Deploy** | `ivgs-frontend:v5.6.2-detailfix`, node-01 only, under WP-34's binding rules |

## Root cause, one sentence

`GET /api/v1/projects/{id}/jobs` returns a `PaginatedResponse` envelope, but `jobsFetcher`
handed that envelope straight to `useSWR<RenderJob[]>` as if it were the array, so the moment
the jobs request resolved `useJobs`' `refreshInterval` callback ran `latestData?.some(...)` on an
object and threw `TypeError: latestData?.some is not a function`, taking down the whole page.

**Why it appeared only now.** Before WP-IVGS-0 **F9**, `projectFetcher` read `response.data.data`
on a route that returns the project unwrapped, so `project` was always `undefined` and the page
short-circuited into its `if (error || !project)` branch at `page.tsx:171`. `PipelineTracker`
was **never mounted**. F9 made the page render for the first time — and the first thing it
mounted was the component whose data hook had been broken all along. **F9 did not introduce this
bug; it stopped hiding it.**

---

## 1. The data — read first, read-only

The newest `projects` row, verbatim:

```
id                    c12fa967-f989-4ed4-8e20-3ea62cb92e8f
name                  double digit multiplication
max_runtime_seconds   300
state                 DRAFT
hero_image_asset_id   (null)      talking_head_asset_id (null)
target_audience       (null)
created_at            2026-08-23 08:14:31.873292+00
created_by            285c7930-8ff7-4613-a52c-79beeb5ad45f
```

Related records: `language_variants` **2**, `transcripts` **1**, `assets` **2**,
`storyboard_scenes` **0**, `render_jobs` **0**, `prompts` **0**.

**`projects` has no `target_languages` column** — the page reads `project.target_languages`
(`page.tsx:212`, `:358`) and it is simply absent from the wire. Both sites are guarded
(`&&` and `?.`), so this is dead UI rather than a crash. Recorded, not fixed: it is a separate
question whether that field should be sourced from `language_variants`.

Serialised through the route's own `response_model=ProjectResponse`, the page receives:

```json
{"id":"c12fa967-…","name":"double digit multiplication","description":"…",
 "max_runtime_seconds":300,"state":"DRAFT","hero_image_url":null,"scene_count":0,
 "total_duration_estimate_seconds":null,"created_at":"2026-08-23T08:14:31.873292Z",
 "updated_at":"2026-08-23T08:14:31.873292Z","language_variants":[],"active_job":null,
 "created_by":"285c7930-…"}
```

Every field the page touches is present and non-null except `total_duration_estimate_seconds`,
`hero_image_url` and `active_job` — none of which the Overview tab dereferences unguarded.
**The project payload is not the problem.**

## 2. The crash — the jobs envelope

`ivgs-api/app/api/v1/jobs.py:31`:

```python
@project_job_router.get("", response_model=PaginatedResponse[JobResponse], …)
```

So the wire shape is `{data, total, page, per_page, pages, has_more}` — captured live from the
running API for a project with zero jobs:

```json
{"data": [], "total": 0, "page": 1, "per_page": 50, "pages": 0, "has_more": false}
```

`ivgs-frontend/src/hooks/useJobs.ts:21-24`, as written:

```typescript
const jobsFetcher = async (url: string): Promise<any> => {
  const response = await apiClient.get<{ data: RenderJob[] }>(url);
  return response.data;          // ← the ENVELOPE, not the array
};
```

then `useJobs.ts:29-43`:

```typescript
const { data, … } = useSWR<RenderJob[]>(url, jobsFetcher, {
  refreshInterval: (latestData) => {
    const hasActive = latestData?.some(…)      // ← throws
```

**Why TypeScript did not catch it.** The fetcher is annotated `Promise<any>`. `any` satisfies
`useSWR<RenderJob[]>`, so the declaration *asserts* "array" over a value the compiler knows
nothing about. `tsc --noEmit` passed on this code the whole time.

**Why optional chaining did not save it.** `?.` guards `null`/`undefined`. The envelope is
neither — it is present, and simply not an array. This is the precise failure mode that makes
`?.` a false comfort.

**Second defect, same value.** `PipelineTracker.tsx:74`:

```typescript
if (!jobs || jobs.length === 0) return statusMap;
```

An envelope is truthy and its `.length` is `undefined`, so `undefined === 0` is false and the
guard **passes execution through on a non-list**. It survives only because the next line uses
`latestJob?.stage_statuses`. The guard was doing nothing.

## 3. Reproduced mechanically

Replaying the real payload through the code as written:

```
first render, data undefined  -> 30000
after data arrives -> THROWS: TypeError: latestData?.some is not a function

PipelineTracker guard  !jobs || jobs.length === 0  -> false   (expected true)
jobs.length -> undefined      jobs[0] -> undefined
```

Then the **whole render path** of `page.tsx` and its children, against the real row above:

```
=== PRE-FIX  (jobsFetcher returns the envelope) ===
    RESULT: CRASH -> TypeError: jobs?.some is not a function

=== POST-FIX (unwrapList returns an array) ===
    name                       double digit multiplication
    StateBadge                 DRAFT
    description                shown
    runtime                    5:00
    createdDate                23/08/2026
    target_languages guard     skipped
    timeline currentOrder      0
    useJobs refreshInterval    30000
    PipelineTracker guard      true
    created                    23/08/2026, 08:14:31
    updated                    23/08/2026, 08:14:31
    createdBy                  285c7930-8ff7-4613-a52c-79beeb5ad45f
    languages                  None specified
    RESULT: page rendered to completion
```

## 4. The fix

**`src/lib/unwrap.ts` (new).** `unwrapList<T>()` accepts either shape and **always** returns an
array; `unwrapObject<T>()` is its detail-route mirror. `unwrapList` is deliberately *total* — it
has no failure mode, because a list endpoint returning something unrecognisable should render as
"nothing to show", not take the page down. The module documents which routes use which envelope,
so the next person does not have to rediscover it.

| File | Change |
|---|---|
| `hooks/useJobs.ts` | `jobsFetcher` returns `unwrapList<RenderJob>(…)`, typed `Promise<RenderJob[]>` — no more `any` |
| `hooks/useJobs.ts` | `refreshInterval` uses `Array.isArray(latestData) ? … : []` instead of `?.` |
| `hooks/useAssets.ts` | same envelope defect, same fix (see 5) |
| `components/PipelineTracker.tsx` | guard is `!Array.isArray(jobs) \|\| jobs.length === 0` |
| `components/StateBadge.tsx` | `state.toUpperCase()` × 3 on a prop typed `string` with no runtime guard; now falls back to `UNKNOWN`. A badge with nothing to show must not crash its parent. |

Dropping `Promise<any>` is the part that stops this recurring: the fetcher's return type is now
checked against `useSWR`'s parameter.

## 5. One extra file, and why

`useAssets.ts` carries the **identical** defect — `GET /projects/{id}/assets` is
`PaginatedResponse` (`assets.py:38`) and its fetcher returned `response.data`. It is not on the
Overview tab, so it is outside a literal reading of "every component the detail page renders",
but `assets` is consumed by `.map`/`.filter` on the **assets, talking-head and audio** tabs of
this same project, which would throw `assets.map is not a function`. Fixing one and knowingly
leaving its twin one file away would have been indefensible. Recorded as a deliberate scope
extension.

**Checked and NOT changed:** `useTranscripts.ts`. `GET /projects/{id}/transcripts` is
`response_model=List[TranscriptResponse]` (`transcripts.py:36`) — a bare array — so
`response.data` is already correct there. Changing it would have broken it.

## 6. Tests

The frontend has **no test framework and no test dependencies**, and none was installed. The
regression test runs on Node's built-in runner against the **compiled real helper**, so it
exercises shipped code rather than a copy:

```
cd ivgs-frontend && npm run test:logic
# tests 6   # pass 6   # fail 0
```

`test:logic` compiles `src/lib/unwrap.ts` with the repo's own `tsc` into `.test-build/`
(git-ignored) and runs `node --test`. Coverage: the exact captured wire payload throws under the
pre-fix expression (**the test asserts the crash**, so it demonstrably discriminates);
`unwrapList` handles the envelope, a bare array, and nine junk inputs without ever throwing or
returning a non-array; the old `PipelineTracker` guard is shown to be defeated and the new one to
hold; and `unwrapObject` is pinned so it cannot reintroduce the F9 `.data.data` regression.

`npx tsc --noEmit` — **rc 0**.

## 7. What was NOT verified

**No browser was driven.** None is installed on node-01 (`chromium`, `firefox`, playwright,
puppeteer all absent), so nobody has *looked* at the rendered page. The evidence is: the crash
reproduced mechanically from the real payload, the full render path completing against the real
row, `tsc` clean, the Next production build succeeding, and the fixed code verified present in
the deployed bundle. That is strong, and it is not the same as seeing it.

**The operator should load `/projects/c12fa967-f989-4ed4-8e20-3ea62cb92e8f` and confirm.**

## 8. Recorded, not fixed

- **`project.target_languages` does not exist** on the wire or in the schema. Two guarded reads
  render "None specified" forever. Either source it from `language_variants` (this project has 2)
  or remove the field.
- **Nothing checks frontend/API envelope agreement.** This is the third shape mismatch found in
  two days — F9 (`.data.data` on a bare route), WP-23 (four field names that never existed), and
  now this. Extends **P2.40**; generating the TS types from the OpenAPI schema would close the
  whole class.
- **`Promise<any>` on fetchers defeats the type system.** `useNodes`, `useTranscripts` and the
  `useMonitoring` fetchers are all still `Promise<any>`. Not changed here — out of scope — but
  each is a place this can happen again.
