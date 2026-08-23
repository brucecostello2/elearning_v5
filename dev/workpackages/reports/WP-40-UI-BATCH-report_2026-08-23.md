# WP-40-UI-BATCH — five frontend defects, one recurring cause

| | |
|---|---|
| **HEAD at start** | `8796d31` (3 commits held) |
| **HEAD at report** | `29568b4` (**8** commits held — counted, not assumed) |
| **Date** | 2026-08-23 |
| **Subject** | project `c12fa967-f989-4ed4-8e20-3ea62cb92e8f` — 18 scenes, 40 assets, 23 render jobs |
| **Ships** | `ivgs-frontend` only, as `v5.6.7-uibatch` |
| **`ivgs-api`** | **not touched.** No task required it — see §7. |

---

## 0. The one sentence worth reading first

Four of the five defects are **the same defect**: a TypeScript interface asserting fields the
API does not send, which TypeScript cannot catch because it has no idea what the wire looks
like. This is the fourth, fifth, sixth and seventh occurrence in this family.

| | route shape | frontend did | result |
|---|---|---|---|
| WP-IVGS-0 **F9** | bare object | read `.data.data` | over-unwrapped → `undefined` |
| WP-35 jobs/assets | envelope | read `.data` | under-unwrapped → object where an array was expected |
| WP-38 scenes | bare array | read `.data.scenes` | over-unwrapped → `undefined` |
| **WP-40 T1** assets | envelope, correct fields | read `url` / `thumbnail_url` / `filename` | **fields do not exist** → blank cards, zero requests |
| **WP-40 T2** jobs | *wrong route entirely* | read the PROJECT list | 16 projects rendered as jobs |
| **WP-40 T5** transcripts | correct fields | read `original_text` | **field does not exist** → `.split` of `undefined` |
| **WP-40 T2b** job detail | no checkpoints in payload | read `.stage_statuses` | **field does not exist** → every stage grey |

In every case the frontend type declared the phantom field as **required**, so the compiler
signed off on reading it. Fixing the types is what stops this recurring; the guards are what
stop it crashing while it does.

---

## TASK 1 — asset cards render no media

### 1.1 The cause: an absence, not a failure

The devtools observation is the whole diagnosis. **"Img: 0 of 121 requests" is not a failed
load — it is an absent one.** `AssetBrowser` built its face from:

```tsx
<img src={asset.thumbnail_url || asset.url} alt={asset.filename} />
```

`<img src={undefined}>` renders an `<img>` element **with no `src` attribute at all**, so the
browser has nothing to request. The list fetch returning 200 was never in doubt.

`AssetResponse` (`ivgs-api/app/schemas/asset.py:27`) sends exactly:

```
id, project_id, scene_id, asset_type, seaweedfs_fid, seaweedfs_path, mime_type,
file_size_bytes, duration_seconds, language_code, generation_prompt_id,
storage_tier, preserve_flag, content_hash, reference_count, created_at
```

Verified live, `GET /api/v1/projects/c12fa967-…/assets?per_page=100` → 200, 40 assets:

```json
{ "id": "72964509-…", "asset_type": "final_render",
  "seaweedfs_path": "/ivgs/final/c12fa967-…/draft_720p_en-US.mp4",
  "mime_type": "video/mp4", "file_size_bytes": 6005929, "language_code": "en-US" }
```

The frontend interface declared **nine fields the API has never sent** — `url`,
`thumbnail_url`, `filename`, `scene_label`, `generation_prompt`, `storage_path`, `metadata`,
`quality_score`, `quality_decision` — four of them as **required**.

Two consequences beyond the blank cards, both of which the operator would have reported
separately:

- **The search box emptied the grid on any keystroke.** Its haystack was
  `filename ?? scene_label ?? generation_prompt` — all three `undefined`.
- **The type filter offered `image / video / animation`.** The live project holds *seven*
  asset types (`image` ×16, `audio` ×18, `video` ×2, `final_render`, `talking_head`,
  `document`, `reference_clip`), so the 18 audio assets and the finished 720p draft were
  unreachable by any filter, and `animation` matched nothing at all.

### 1.2 The media route exists — and required no API change

`GET /api/v1/assets/{id}/download` (`assets.py:128`) proxies from SeaweedFS. Verified live:

```
http=200   content-type: image/png   content-length: 641217
content-disposition: attachment; filename="image.png"
```

**But it is behind `Depends(get_service_or_user)`, and a browser will not attach an
Authorization header to `<img src>`, `<video src>` or `<a download>`.** That is the reason a
naïve "just point the src at the download route" fix would have produced 40 × 403 instead of
40 × nothing — worse, because it would have looked like a permissions problem.

So `apiClient` grew `blob()`: an authenticated fetch that returns the bytes, which the card
turns into an object URL. **The Bearer token previously lived only inside the JSON code path**
— `request()` — so `authedFetch()` was extracted first and both paths now share one
401-refresh implementation rather than growing a second copy.

**No API route was built and none was needed.** The STOP condition in the brief was not met.

### 1.3 What the operator will see differently on `/projects/{id}/assets`

| | before | after |
|---|---|---|
| Image cards (16) | blank | the actual image |
| Video cards (5, incl. the 720p draft) | blank | play placeholder → click → `<video controls>` |
| Audio cards (18) | blank "Asset" box | audio placeholder → click → `<audio controls>` |
| `document` / `reference_clip` | blank "Asset" box | typed icon + "Document" / "Reference clip" |
| Card label | empty (`filename` undefined) | `draft_720p_en-US.mp4`, from `seaweedfs_path` |
| Card badge | "N/A" on every card | real size — `5.7 MB`, `626 KB` |
| Download | none | on every card, and in the preview |
| Search | emptied the grid | matches filename / type / mime / language / path / id |
| Filters | all / image / video / animation | all / images / video / audio / other, on derived kind |
| Regenerate | 404 every time (see below) | reaches the route |

**Two deliberate choices, stated because the operator will feel them:**

1. **There is no thumbnail route on this API.** An image card therefore downloads the
   *full-size original* — the live ones are ~600 KB each. To keep that from being 25 MB on
   tab open, cards load **only once they scroll into view** (IntersectionObserver), and
   **video and audio are never fetched for a card at all** — a 6 MB draft render is not a
   thumbnail. They load on demand in the preview. A real thumbnail route would be better;
   see §9.
2. **The quality-score badge is gone.** Quality lives in `asset_quality_scores` behind
   `/api/v1/quality/…` and was never on this payload. A badge reading "N/A" on all 40 cards
   is worse than not claiming to know; size and type, which are real, took its place.

### 1.4 A second bug found on the way, fixed

`useAssets.regenerateAsset` POSTed to `/api/v1/projects/{pid}/assets/{aid}/regenerate`. The
asset-scoped router is mounted at **`/assets`** (`assets.py:33`) — only LIST and UPLOAD are
project-scoped. The route is `POST /api/v1/assets/{id}/regenerate` (`assets.py:154`). **Every
press of Regenerate raised a 404 toast**, and would have gone on doing so behind a
now-visible card. Corrected, with a negative gate pinning it (§6).

---

## TASK 2 — the Pipeline Tracker lies

### 2.1 It was listing projects

`usePipelineJobs` fetched **`/api/v1/projects?expand=jobs`** and returned `data.data`. That is
the PROJECT list. `expand` is not a parameter that route implements — verified live, the
response has no `jobs` key. All four reported symptoms fall out of that single fact:

| symptom | why |
|---|---|
| "16 jobs" | 16 **projects** |
| RUNNING/COMPLETE/ERROR/PENDING all 0 | a project carries `state`, not `status` |
| AVG DURATION "—" | a project has no `started_at`/`completed_at` |
| rows read "Job #c12fa967" | that is the **project** id, sliced to 8 |

### 2.2 A second defect was hiding behind the first

**Even against real jobs the counters would still have read 0.** `render_jobs.status` is
**lowercase** on the wire — `pending | running | success | failed` — and the filters compared
against `COMPLETE` / `ERROR`. Two of the four would never have matched anything. Fixing only
the data source would have produced a tracker that still lied, more convincingly.

### 2.3 There is no cross-project job route, so the list is assembled client-side

`jobs.py` exposes only `GET /projects/{id}/jobs` (project-scoped) and `GET /jobs/{id}`
(single). The hook now walks projects → that project's jobs → normalises status → attaches a
duration. Filters moved client-side too: they were being sent as query params to the projects
route, **which ignores every one of them**, so the state, search and date controls did nothing
at all.

### 2.4 Average duration — the honest answer, and why it is not a frontend bug

```sql
SELECT status, count(*), count(started_at), count(completed_at) FROM render_jobs GROUP BY status;
 status  | count | have_started | have_completed
---------+-------+--------------+----------------
 pending |     2 |            0 |              0
 running |     7 |            0 |              0
 success |     4 |            0 |              0
 failed  |     7 |            0 |              0
```

**`render_jobs.started_at` and `.completed_at` are NULL on every row, and nothing in
`ivgs-api`, `ivgs-workers` or `shared/` ever writes them** — a grep for the identifier finds
only reads and schema declarations. They are dead columns.

`pipeline_checkpoints` **does** record timing (11 rows, `started_at` on all 11,
`completed_at` on 8), so the duration comes from each job's checkpoint span via
`GET /api/v1/jobs/{id}/checkpoints`. Checkpoints of a terminal job never change, so they are
fetched **once per job per session** and memoised; a poll costs nothing after the first.
The per-pass ceiling is 40 lookups and is stated in code rather than silently truncating.

**The average is now `null`, not `0`, when nothing is measurable**, so the tile can say
*"no timing data recorded"*. `formatDuration(0)` returned `"—"`, which meant the operator
could not tell "instant" from "unrecorded" — the two worst possible things to conflate on a
duration display.

### 2.5 The job detail panel was also drawing nothing real

Invisible while every detail fetch 404'd on a project id. Two problems:

1. `GET /api/v1/jobs/{id}` returns `JobResponse`, which **has no checkpoints**. The stage
   table read `jobDetail.checkpoints` and therefore drew eight PENDING rows for every job,
   finished or not.
2. `GET /api/v1/jobs/{id}/checkpoints` — which does have them — keys rows by `stage_name` at
   **worker** granularity (`image_generation`, `video_generation`, `tts_audio`) while the
   page's DAG is keyed by the eight spec stages.

`mergeCheckpoints` maps and collapses them, **pessimistically**: any failure makes the box
FAILED, any not-yet-complete member makes it RUNNING, and only an all-complete set is
COMPLETE. On the live job that matters — `image_generation` complete, `video_generation`
pending, both in the MEDIA_GENERATION box — the box reads RUNNING, not COMPLETE. A DAG that
overclaims progress is the one failure mode worth engineering against here.

### 2.6 Two more surfaces this reaches, same cause

- **`/monitoring` dashboard** — "Active Pipelines" and "Failed Jobs" filtered
  `j.status === "running" / "failed"` over the same project list. Both read 0. Both now count.
- **The project Overview's Pipeline Progress strip** (`PipelineTracker.tsx`) — *a second
  component with the same name and the same disease*. It read `latestJob.stage_statuses`, a
  field `JobResponse` does not send, against **its own seven-name stage vocabulary**
  (`script_refinement`, `visual_asset_creation`, `quality_assurance`) that nothing on the wire
  has ever produced. It rendered grey "pending" for all seven stages even after a complete
  end-to-end run. It now draws the same eight spec stages from the same checkpoints, so the
  app has one stage vocabulary instead of two.

### 2.7 Verified against the live API

The aggregation was run against the deployed API before shipping (23 jobs across 16 projects):

```
projects: 16 | jobs: 23
RUNNING 7  COMPLETE 4  ERROR 7  PENDING 5  UNKNOWN 0
timed jobs: 2 | avg: 6472s
  Job #c57ec7b7 storyboard_generation | double digit multiplication | PENDING  | —
  Job #bd99fe37 transcript_refinement | double digit multiplication | COMPLETE | 12196s
merged stages: TRANSCRIPT_REFINEMENT=COMPLETE STORYBOARD_GENERATION=COMPLETE
               MEDIA_GENERATION=RUNNING AUDIO_GENERATION=COMPLETE
               TALKING_HEAD_RENDER=COMPLETE PROTOTYPE_DRAFT=COMPLETE
```

Only 2 of the 11 terminal jobs have checkpoint rows, so "avg over 2 timed jobs" is what the
tile will say. That is the truth about this system's records, and the tile now says which.

---

## TASK 3 — the review gates have buttons

Both endpoints **existed and worked** — WP-38 §4 traced the approve one end to end and used
it to advance this very project. What was missing was any way to call them from the GUI, so
getting past a gate meant pasting a curl block with a hand-minted token.

| | route | guard | states |
|---|---|---|---|
| (a) Approve storyboard | `POST /projects/{id}/scenes/approve?tier=` (`storyboard.py:194`) | `require_operator_or_admin` | rejects `MEDIA_GENERATION` and later (`project_service.py:374`) |
| (b) Trigger pipeline | `POST /projects/{id}/trigger?tier=` (`projects.py:146`, ledger M6) | `require_operator_or_admin` | **only** `DRAFT` and `USER_REVIEW` (`project_service.py:266`) |

One shared component (`PipelineGateButton`) so the two cannot drift apart in how they confirm
or how they report a refusal:

- **Tier selector** — `prototype` / `production`, each with what it costs, defaulting to
  prototype. Starting a production run by mis-clicking is the failure this exists to prevent.
- **Confirmation dialog** naming the tier and the consequence, and the confirm button reads
  `Approve (production)` — the tier is on the button, not only in the radio.
- **A 409 is rendered verbatim**, under the heading "The server refused this". The server
  knows why — *"Cannot trigger pipeline: no transcripts uploaded"*, *"media generation already
  started or past"* — and paraphrasing could only lose information.

**Viewer role sees neither button.** Not disabled — absent. Both routes are
`require_operator_or_admin`, so offering a control that can only 403 is a worse experience
than not offering it. Visibility also mirrors each service's own state guard, so a visible
button is a button that will work.

On `USER_REVIEW` the trigger button reads **"Start final render"**, because that is what
`trigger` does from that state (`USER_REVIEW → FINAL_RENDER`); calling it "Trigger pipeline"
there would be technically accurate and practically misleading.

**Not tested by pressing them.** Approving would dispatch real GPU work on the live project;
that is the operator's decision, not this package's. What is verified is that the routes exist,
that their guards and state preconditions are what the buttons mirror, and that the built
bundle carries both call sites (§6).

---

## TASK 4 — the `/api/v1/quotas/user/…` 404s

### 4.1 Two corrections to the premise

**The route exists.** `quotas.py:33` is `GET /quotas/{entity_type}/{entity_id}`, mounted at
`/api/v1/quotas` (`api/v1/__init__.py:109`). The 404 is its own honest answer:

```sql
SELECT count(*) FROM storage_quotas;  -->  0
```

Every lookup raises `RESOURCE_NOT_FOUND` *"No quota for user/{id}"*. Building a route would
have fixed nothing.

**It is not called on project pages.** The only caller in the tree is `useStorageQuotas`, and
its only mount is `/monitoring/storage`'s admin Quotas tab. The project detail page imports
`useProjects`, `useAuth`, `StateBadge`, `PipelineTracker`, `LoadingSpinner`, `ErrorBoundary` —
no quota path. The spam is **four 404s — one per user — on every 120-second poll and on every
window refocus**, from the storage page.

### 4.2 The fix: stop re-asking a question already answered

A 404 here means *"this entity has no quota record"*, which cannot change without an admin
`PUT`. So it is remembered for the session and never re-requested: **one probe per user on
first load, zero on every poll thereafter.** `revalidateOnFocus` and error-retry are both off
for the same reason. Anything that is **not** a 404 is a real fault, is not memoised, and is
still retried on the next poll.

Rows carry `has_quota`, and the tab now says **"No quota data"** with a line explaining that
quotas are set per entity and nothing creates them automatically — instead of a table of
`0 B / 0 B / 0% / OK` rows, which read as four real zero-byte quotas and is worse than saying
nothing.

**Nothing anywhere writes `storage_quotas`.** There is no quota provisioning path in this
system. That is backend scope and is deliberately not built — see §9.

---

## TASK 5 — P1.4r `.split()`, closed

### 5.1 The wire identified the site without a browser

WP-38 §3 produced a shortlist and stopped, correctly, rather than patching four files blind.
The shortlist was right and the answer is its first entry — **`TranscriptEditor.tsx:33`** —
and it is provable from the wire alone:

`TranscriptResponse` (`schemas/transcript.py:13`) sends `id, project_id, sequence_order,
original_asset_id, refined_text, language_code, created_at, updated_at`.

Live, project `c12fa967`'s sole transcript row:

```
{'id': '4d70b8a8-…', 'project_id': 'c12fa967-…', 'sequence_order': 1,
 'original_asset_id': '814dfcd4-…', 'refined_text': "Let's learn how to multiply…",
 'language_code': 'en-US', 'created_at': …, 'updated_at': …}
```

**There is no `original_text` — and no `original_text` COLUMN on the `transcripts` table
either** (`\d transcripts` confirms it). The source document is an asset referenced by
`original_asset_id`. The frontend type nevertheless declared `original_text: string`
**non-optional**; the transcript page passed `transcript.original_text` — `undefined` —
straight into `TranscriptEditor`; `computeLineDiff` called `original.split("\n")`.

That is the console error, and Next.js bundling `TranscriptEditor` into the same
`page-*.js` chunk is why it was reported against the project detail page.

### 5.2 Every site on the shortlist, guarded

All guards go through `@/lib/text`, which is **total by construction** —
`splitLines(undefined)` is `[]`, not a throw, because an absent document has zero lines.

| site | prop / value | can it be absent? | what renders now |
|---|---|---|---|
| `TranscriptEditor.tsx:33,34` | `originalText`, `refinedText` | **yes — `original_text` never exists** | empty diff pane + a line saying the original is not stored |
| `TranscriptEditor.tsx:117` | `refinedText` → textarea `rows` | yes | `Math.max(10, 0)` = 10 |
| `PromptHistory.tsx:48,49` | `prompt_text` of two versions | yes — `Optional[str]` | empty diff |
| `PromptHistory.tsx:476` | `selectedVersion.prompt_text` | yes | `0 chars · 0 lines`, "(this version has no content)" |
| `PromptEditor.tsx:378` | `templateContent` | via a null `prompt_text` initialiser | empty template, 0 lines |
| `AssetUploader.tsx:51` | `accept` — an **optional prop** | yes | empty accept list = accept anything |
| `AssetUploader.tsx:52` | `file.name.split(".").pop()` | extensionless filename | `""`, no phantom `.undefined` extension |

The `TranscriptEditor` "Original" pane no longer renders as a mystery blank box: it says
*"No original text is stored for this transcript. The uploaded source document is kept as an
asset; the refined text is on the right."*

### 5.3 The two remaining `.split(` sites in the tree — audited, deliberately untouched

- **`lib/auth.ts:80`** `token.split(".")` — inside `try { … } catch { return null }`. WP-38
  established it cannot produce an uncaught console error, and that holds.
- **`app/admin/nodes/page.tsx:62,63`** — `sameSubnet24(ip, node01Ip)` already returns early on
  a null `node01Ip`, and `ip` comes from controlled `useState<string>` form state.

**P1.4r covers every reachable site and is closed.** Nine `.split(` call sites exist in the
tree; seven were reachable-and-unguarded and are now guarded, two were already safe.

---

## TASK 6 — verify-only sweep: GPU nodes

**Findings only. No fix — because there is no frontend-side misread to fix.**

There are **three** node registries in this system and they disagree:

| registry | queried | answer |
|---|---|---|
| `gpu_nodes` (Postgres) → `GET /api/v1/gpu/nodes` | live | `{"data": [], "total": 0}` — **0 rows in the table** |
| → `GET /api/v1/gpu/utilization` | live | `total_nodes=0, online=0, total_vram_mb=0` |
| Scheduler registry (Redis) → `:8002/fleet` | live | `total_nodes=6, alive_nodes=3, total_vram_mb=587322` |
| Static infra inventory → `GET /api/v1/nodes` | live | 6 nodes; node-01..04 `online`, node-02/03/04 with `97887` MB and the RTX PRO 6000 model string |

**"GPU Nodes Online" reads `/api/v1/gpu/nodes`, which is empty. It shows `0/0`, and that is a
faithful read of its data source, not a misread.** Same for the GPU Fleet page: it filters
`n.status === "online"` and sums `total_vram_mb` over an empty array.

The reason the table is empty is structural, not a bug in either component:
`register_node()` (`ivgs-workers/utils/gpu_utils.py:418`) posts to **`POST /register` on the
scheduler**. Nothing in `ivgs-workers` ever calls `POST /api/v1/gpu/nodes`. **WP-39's
`alive_nodes` fix works** — 3 alive of 6 — but it works in the registry the API does not read.

One detail that makes the bridge less trivial than it looks: the scheduler keys nodes by
**container hostname** (`61c7c02b3a8a:gpu0`, `7f479b3018af:gpu0`), not by `node-02`. A
copy from one registry into the other would need an identity mapping it does not currently
have.

**Nothing was changed for this task.** Scoped item in §9. Note that `/nodes` (the infra page,
reading `/api/v1/nodes`) *does* show real fleet data today — an operator wanting node status
right now should use that page.

---

## 6. Tests and gates

| Gate | Result |
|---|---|
| `npm run test:logic` | **44 passed / 0 failed** — 10 baseline + **34 new** |
| `tsc --noEmit` | rc 0 |
| `npm run build` | rc 0, all 30 routes emitted |
| **Full Python suite, HEAD** | 252 failed / 547 passed / 15 skipped / **1093 errors** |
| **Full Python suite, clean tree (stashed)** | 252 failed / 547 passed / 15 skipped / **1093 errors** |
| **Delta** | **0 — identical, measured both ways** |

> **On that Python baseline.** It does not match WP-38's recorded 74/1095/34/77, and the
> reason is environmental, not a regression: `tests_system/integration` hardcodes
> `BASE_URL = "http://localhost:8001/api/v1"`, and `ivgs-fastapi` publishes **only** on
> `192.168.1.90:8001` — `docker port ivgs-fastapi` → `8001/tcp -> 192.168.1.90:8001`. Loopback
> gets `ConnectError: All connection attempts failed`, and every integration fixture errors.
> Rather than argue that a frontend-only package cannot affect pytest, the suite was run
> **twice** — once at HEAD, once on a `git stash -u`'d clean tree — and the four numbers are
> identical. **Zero Python files are in this package's diff.** `npm run lint` is not
> configured in this repo (`next lint` drops into an interactive setup prompt); that is
> pre-existing and was not changed.

New tests, all against **wire shapes captured live on 2026-08-23**, WP-35/38 pattern — each
file reproduces the bug first, then pins the fix:

| File | Tests | What it pins |
|---|---|---|
| `asset-media.test.mjs` | 12 | the seven phantom fields are absent; `thumbnail_url \|\| url` is `undefined`; every asset yields a URL/name/kind; the download path is **asset**-scoped not project-scoped; mime → extension → asset_type fallback chain; the old search haystack was empty |
| `pipeline-jobs.test.mjs` | 12 | the tracker was listing projects (no `status`, no timestamps, id starts `c12fa967`, no `jobs` key); lowercase statuses would have counted 0 anyway; job timing is null and the checkpoint span is not; avg distinguishes unrecorded from zero; a merged MEDIA_GENERATION box does **not** read COMPLETE while `video_generation` is open |
| `split-guards.test.mjs` | 10 | `original_text` is absent and `.split` on it throws the exact reported message; each of the seven guarded sites over its own absent input |

### Negative gates — run inside the built image

| Gate | Count | Expected |
|---|---|---|
| `expand=jobs` | **0** | 0 — the wrong route is gone |
| `stage_statuses` | **0** | 0 — the phantom job field is gone |
| project-scoped `assets/…/regenerate` | **0** | 0 — the 404 path is gone |
| `thumbnail_url` / `scene_label` / `generation_prompt` **in the Media Assets chunk** | **0 / 0 / 0** | 0 |
| `/download` in the Media Assets chunk | **1** | ≥1 |

> **A negative gate found something, so it is reported rather than rounded off.**
> `thumbnail_url` is still present in **two** chunks — `projects/[id]/storyboard` and
> `monitoring/quality`. Investigated: `SceneCard.tsx:242`, `SceneEditModal.tsx:598` and
> `QualityReviewCard.tsx:138` all read a `thumbnail_url` that **does not exist anywhere in
> `ivgs-api`** — a grep of the entire API tree for the identifier returns nothing, and the live
> scenes payload keys are `created_at, duration_seconds, id, media_type, narration_text,
> project_id, scene_index, updated_at, visual_description`. It is the **same defect** as Task 1.
> All three are `&&`-guarded, so they render placeholders rather than crashing or issuing bad
> requests — degraded, not broken. **Out of Task 1's scope (Media Assets grid), not fixed,
> scoped in §9.** Likewise `scene_label` / `generation_prompt` survive only in the audio and
> talking-head tabs, which are the same scoped item.

---

## 7. `ivgs-api` was not touched, and no task required it

| Task | Could it be done client-side? | Why |
|---|---|---|
| 1 assets | **yes** | `GET /assets/{id}/download` already exists and works; only the Bearer-header problem had to be solved, and `blob()` solves it in the client |
| 2 tracker | **yes** | no cross-project job route exists, but `GET /projects/{id}/jobs` + `GET /jobs/{id}/checkpoints` aggregate to the same answer |
| 3 gates | **yes** | both endpoints already exist; only the buttons were missing |
| 4 quotas | **yes** | the route exists; the fix is to stop re-asking it |
| 5 splits | **yes** | pure frontend guards |
| 6 GPU | **n/a** | verify-only; the fix is backend-side and is scoped, not built |

---

## 8. Build and deploy — `v5.6.7-uibatch`, node-01, frontend only

**Preflight:** tracked tree clean; `HEAD...origin/main` = `8 0` (8 ahead, 0 behind, as
expected for commit-and-HOLD).

| | `ivgs-frontend` |
|---|---|
| Local image id | `sha256:47177bae581cc1967b3e32f7aa9eaf73718b2737c5f1c5864c4d6bec98010b28` |
| Built | from the **repo root** (the Dockerfile's COPY paths are `ivgs-frontend/…`) |
| Banked **before** push | `brucecostello2_ivgs-frontend_v5.6.7-uibatch.tar.zst`, 58,353,442 B |
| `sha256sum -c` | rc 0 — `78389037297eb5754c16df892aa5adc99bd5599b10f0a608b57616953215a9a6` |
| `zstd -t` | rc 0 |
| MANIFEST lines | 1 |
| Own image-config blob inside the archive | **1** — the archive holds *this* image, not merely a valid zstd stream |
| Push | rc 0 |
| GHCR index digest | `sha256:47177bae…98010b28` — **MATCH** with the local id |

> The push initially failed `unauthorized`: GHCR credentials live in `/root/.docker/config.json`,
> not the invoking user's. Re-run under `sudo -n docker push`. Recorded rather than quietly
> worked around.

**Rollback recorded before any write**, from `.Config.Image` (not from `.env`):

```
ivgs-nextjs   ghcr.io/brucecostello2/ivgs-frontend:v5.6.5-reviewgate   (image still present: 68438ba66ce1)
ivgs-fastapi  ghcr.io/brucecostello2/ivgs-api:v5.6.5-reviewgate        (unchanged by this package)
```

`.env` backed up to `.env.bak.pre-wp40-20260823-211908` (**not committed**), the `.env` write
gated on the new image being present locally, and only the one narrow line changed:

```
IVGS_API_TAG=v5.6.5-reviewgate            <- unchanged
IVGS_FRONTEND_TAG=v5.6.7-uibatch          <- the only edit
IVGS_SCHEDULER_TAG=v5.0.0-20260522        <- unchanged
IVGS_WORKERS_TAG=v5.6.6-mediajoin         <- unchanged
IVGS_BACKUP_WORKER_TAG=v5.1.0-stream-b    <- unchanged
```

Compose invocation derived from the running container's labels
(`com.docker.compose.project.config_files` and `com.docker.compose.service`), not guessed —
the service is `nextjs-frontend`:

```
docker compose -f docker-compose.node01.yml \
               -f docker-compose.override.node01.yml \
               -f docker-compose.monitoring.yml \
               --env-file /opt/ivgs/ivgs-infra/.env \
  up -d --force-recreate --no-deps --pull never nextjs-frontend
```

### Post-deploy verification

```
ivgs-nextjs             ghcr.io/…/ivgs-frontend:v5.6.7-uibatch   Up (healthy)

UNTOUCHED, uptimes intact:
ivgs-fastapi            ghcr.io/…/ivgs-api:v5.6.5-reviewgate     Up 5 hours (healthy)
ivgs-celery-default     ghcr.io/…/ivgs-workers:v5.6.6-mediajoin  Up 4 hours (healthy)
ivgs-celery-composition ghcr.io/…/ivgs-workers:v5.6.6-mediajoin  Up 4 hours (healthy)
ivgs-celery-beat        ghcr.io/…/ivgs-workers:v5.6.6-mediajoin  Up 4 hours (healthy)
ivgs-postgres / ivgs-redis / seaweedfs ×3 / ivgs-scheduler        Up 9 days (healthy)
```

**Workers and nodes 02/03/04 were not deployed and did not need to be** — the workers image is
untouched by WP-40.

Content verified **in the running container**, and then **through nginx end to end**:

```
in ivgs-nextjs:  /download 4   /checkpoints 2   /scenes/approve 2
                 "no quota data" 2   "no timing data recorded" 2
                 "Approve storyboard" 2   "Start final render" 2
                 "No original text is stored" 2
                 expand=jobs 0   stage_statuses 0

through nginx:   https://192.168.1.90/login -> 200
                 GET /_next/static/chunks/app/projects/[id]/assets/page-cf696361115c6b09.js
                   -> 200, 23561 bytes, carries "/download", carries no "thumbnail_url"
```

**Not verified: nobody has loaded these pages in a browser — none is installed on node-01.**
The evidence is the live wire shapes, the aggregation replayed against the deployed API
(§2.7), the fixed code present in the served bundle, and 44 logic tests. **The operator should
open the four pages in §10 and confirm.**

---

## 9. Scoped, NOT done — and why

1. **The same asset defect on four sibling tabs.** The audio, talking-head, draft and renders
   tabs all read `asset.url` / `asset.scene_label` / `asset.filename`
   (`audio/page.tsx:86,89,164,231`, `talking-head/page.tsx:126,139`). They are blank for
   exactly the reason the Media Assets grid was, and `@/lib/media` + `useAssetObjectUrl` make
   each a ~3-line fix. **Not done: Task 1's scope is the Media Assets grid**, and silently
   widening it would mean shipping four more surfaces nobody asked to have changed. The
   deprecated optional fields were left on `AssetResponse` precisely so those pages still
   compile and degrade rather than being rewritten by side effect.
2. **`Scene.thumbnail_url` and `FlaggedAsset.thumbnail_url`** — `SceneCard.tsx:242`,
   `SceneEditModal.tsx:598`, `QualityReviewCard.tsx:138`. Same family; the identifier exists
   nowhere in `ivgs-api`. All guarded, so they degrade to placeholders. Same reasoning as (1).
3. **A thumbnail route.** Image cards download full-size originals because there is no
   alternative. `GET /api/v1/assets/{id}/thumbnail` (or `?w=`) would cut the Media Assets tab
   from ~10 MB to ~200 KB. **API scope — explicitly out of bounds for this package.**
4. **`render_jobs.started_at` / `.completed_at` are never written.** Two dead columns; job
   duration is reconstructed from checkpoints instead. Whatever transitions a job to
   `running`/`success` should stamp them. **API/worker scope.**
5. **`GET /api/v1/jobs` (cross-project).** The tracker makes 1 + N requests per poll (17 today)
   because no such route exists. It works and is fast on a LAN, but a single list route would
   be strictly better. **API scope.**
6. **`gpu_nodes` is empty because workers register with the scheduler, not the API** (§6).
   Either the scheduler's registry should feed `gpu_nodes`, or the API should read the
   scheduler — and either needs an identity mapping from container hostname to `node-NN`.
   **Backend scope, and a real decision (see §11).**
7. **`storage_quotas` has no provisioning path.** Nothing creates rows; the brief forbids
   building a quotas API. **Backend scope.**
8. **P1.4q (failed-path reset)** — still open from WP-38 §5, untouched here.

---

## 10. What the operator should check, page by page

| Page | Expect |
|---|---|
| `/projects/c12fa967-…/assets` | 40 cards **with visible media**: 16 image thumbnails, play placeholders on the 5 videos incl. `draft_720p_en-US.mp4`, audio placeholders on 18. Real filenames and sizes. Download works on every card. Click a video → it plays. Type in the search box → it filters instead of emptying. |
| `/monitoring/pipeline` | **23 jobs, not 16.** Counters read RUNNING 7 / COMPLETE 4 / ERROR 7 / PENDING 5. AVG DURATION shows a real figure with "over 2 timed jobs" beneath it. Rows read `Job #bd99fe37 transcript_refinement` over `double digit multiplication · <date> · 3h23m`. Clicking a row draws a real stage DAG. |
| `/monitoring` | "Active Pipelines" and "Failed Jobs" no longer both read 0. **"GPU Nodes Online" still reads 0/0 — expected, see §6.** |
| `/projects/c12fa967-…` (Overview) | Pipeline Progress shows green/blue stages instead of eight grey circles. **No "Trigger pipeline" button** — this project is `MEDIA_GENERATION`, which is not triggerable. |
| `/projects/c12fa967-…/storyboard` | An **"Approve storyboard"** button top-right (admin/operator only). Clicking opens a tier dialog; confirming calls the real endpoint. |
| A `DRAFT` project's page | A **"Trigger pipeline"** button. If it has no transcript, confirming shows the server's own *"Cannot trigger pipeline: no transcripts uploaded"*. |
| `/projects/c12fa967-…/transcript` | **No console `.split` error.** The Original pane says why it is empty instead of being blank. |
| `/monitoring/storage` → Quotas | "No quota data" with an explanation, and **four fewer 404s per poll** — one probe per user on first load, none after. |

---

## 11. Decisions needed from the operator

1. **The four sibling asset tabs (§9.1) — fix them?** Audio, talking-head, draft and renders
   are blank for exactly the reason the Media Assets grid was, and the helper that fixes them
   now exists. It is ~3 lines each plus the `Scene`/`FlaggedAsset` thumbnails in §9.2.
   Held back only because Task 1's scope was the Media Assets grid. **One word and they ship.**
2. **GPU registry reconciliation (§6).** Which direction — scheduler → `gpu_nodes` (a bridge
   or a periodic sync in the API), or the API reading the scheduler directly? Either needs a
   container-hostname → `node-NN` identity mapping. Until one exists, "GPU Nodes Online" will
   keep reading 0/0 while three GPUs are alive and working.
3. **A thumbnail route (§9.3).** Without one, the Media Assets tab pulls ~10 MB of full-size
   PNGs (lazily, only what is scrolled to). Acceptable on a LAN; worth fixing if this ever
   leaves it.
4. **Job timing (§9.4).** `render_jobs.started_at`/`.completed_at` are dead columns. Should the
   worker or the API stamp them, or is the checkpoint-derived duration the intended answer
   permanently? The tracker works either way; this decides whether it can ever show a duration
   for a job with no checkpoints — 9 of today's 11 terminal jobs.
5. **P1.4q**, still open from WP-38 §5.

---

## 12. Combined gated push block — ALL held commits

```
# RUN ON: IVGS node-01 (192.168.1.90)
( cd /opt/ivgs || exit 1
  if [ "$(git rev-parse --abbrev-ref HEAD)" != "main" ]; then echo "ABORT: not on main"; exit 1; fi
  if [ -n "$(git status --porcelain --untracked-files=no)" ]; then echo "ABORT: tracked files dirty"; exit 1; fi
  git fetch origin --quiet || { echo "ABORT: fetch failed"; exit 1; }
  if [ "$(git rev-list --count HEAD..origin/main)" != "0" ]; then echo "ABORT: origin/main moved - rebase first"; exit 1; fi
  if [ "$(git rev-list --count origin/main..HEAD)" != "9" ]; then echo "ABORT: expected exactly 9 held commits"; exit 1; fi
  if git diff --name-only origin/main..HEAD | grep -qE '(^|/)\.env'; then echo "ABORT: an .env file is in the range"; exit 1; fi
  echo "pushing 9 commits: $(git rev-parse --short origin/main) -> $(git rev-parse --short HEAD)"
  git push origin main
) | tr -cd '\11\12\15\40-\176'
```

**Held state:** branch `main`, tree clean, **9 commits ahead of `origin/main`, 0 behind**, no
`.env*` anywhere in the range.

> The count is **9**, not the 8 that existed when the code was committed: this report is the
> ninth. The guard pins the count rather than a tip SHA, per WP-38's amendment — a hardcoded
> HEAD is invalidated by the very commit that records it.

The nine:

```
<this report>                    docs(wp-40): …
29568b4  fix(p1.4r):      WP-40 close the .split() crash - it was original_text all along
f3cdd4b  fix(quotas):     WP-40 stop re-asking a question already answered
791361b  feat(gates):     WP-40 the two pipeline gates now have buttons instead of curl
8e3fc14  fix(monitoring): WP-40 the Pipeline Tracker was listing projects as jobs
bb65746  fix(assets):     WP-40 the media cards read three fields the API never sends
8796d31  docs(wp-39):     record the root cause, the watchdog finding, …
36cf538  fix(media-join,watchdog): WP-39 the animation stage could not report; …
7cdfbf4  docs(wp-39):     handoff — WP-39 was never started; nothing built, nothing deployed
```
