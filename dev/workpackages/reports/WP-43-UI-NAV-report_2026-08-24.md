# WP-43-UI-NAV — one tab bar, eleven tabs, and four 422s the client refused to read

| | |
|---|---|
| **HEAD at start** | `cee3b69` — clean tree, `HEAD == origin/main` |
| **HEAD at report** | this `docs(wp-43)` commit — **8** commits held, counted after a real `git fetch`, not assumed |
| **Date** | 2026-08-24 (verification and build executed 2026-08-25 UTC) |
| **Subject** | project `c12fa967-f989-4ed4-8e20-3ea62cb92e8f` — 18 scenes, 40 assets, 10 jobs, 2 language variants |
| **Ships** | `ivgs-frontend` only, as **`v5.7.0-uinav`**, node-01 only |
| **`ivgs-api`** | **not touched.** No task required it. The STOP condition was not met — see §8. |
| **Everything else** | workers, engines, scheduler, node-02/03/04, Postgres, Redis, SeaweedFS — **untouched.** |

---

## 0. The one paragraph worth reading first

Seven tasks; **three causes**.

1. **A type asserting a shape the wire does not have** — the WP-40 §0 family, now
   in its eighth through thirteenth instances. `media_type` (Task 7),
   `progress_percent` (Task 3b), `target_languages` / `asset_count` /
   `current_job_id` (Task 3b sweep), the `IN_PROGRESS` / `REVIEW` project states
   (Task 1). In each case the frontend declared a field or a vocabulary the API
   has never used, TypeScript signed off because it cannot see the wire, and the
   UI rendered a confident wrong answer rather than an error.
2. **A message rendered where nobody could see it** — Tasks 3a, 6a, 6b and 7 all
   ended in "Request failed with status 422" over a body that named the field and
   the reason in plain English, because `api-client`'s reducer skipped ARRAYS and
   a 422's `detail` is always an array. Task 6a adds a second layer: the one
   message that did exist was painted *behind* the modal that needed it.
3. **Looking at the wrong row** — Task 5's all-grey strip read `jobs[0]`, and the
   newest seven jobs on this project have never written a checkpoint.

Task 4's black page needed **two** of these at once, which is why it looked like
nothing rather than like a 404. Details in §4.

---

## 1. TASK 1 — the tab bar existed on one tab out of eleven

### 1.1 What was actually wrong

The project header, the lifecycle strip and the entire tab bar were **JSX inside
the Overview page component** (`src/app/projects/[id]/page.tsx`). Consequences,
all of them structural rather than cosmetic:

- Ten of the eleven tabs showed **no tab bar at all** — only a bare `← Back` link.
- Switching from Transcripts to Audio meant Back → Overview → Audio. Three clicks
  and two page loads for one lateral move.
- On ten pages out of eleven there was **no indication of which tab you were on**,
  because the only thing that renders the active-tab highlight was on the page you
  had left.
- The tab bar navigated with `router.push` from a `<button>`, so no tab was a real
  link: no middle-click, no open-in-new-tab, no hover target.

### 1.2 The fix

`src/components/project/ProjectShell.tsx`, rendered by a **Next.js segment layout**
at `src/app/projects/[id]/layout.tsx`. A segment layout wraps `/projects/{id}` and
every `/projects/{id}/*` route by construction, which is the point: a page added
under that segment inherits navigation whether or not its author thought about it.

- All **nine** per-page `← Back` links removed (`transcript`, `assets`, `audio`,
  `talking-head`, `draft`, `renders`, `jobs`, `languages`, and the Overview's own
  `← Gallery` button which moves into the shell).
- `← Gallery` survives **once**, in the shell header, at the top level.
- Tabs are `<Link>` elements now, with `aria-current="page"` on the active one.
- Each page's duplicate `max-w-… mx-auto px-4 … py-8` wrapper was replaced with a
  plain content container, since the shell supplies the page frame.
- The project is read through the same `useProjects(projectId)` SWR key the pages
  already use, so the shell adds **no extra request**; loading and error states
  now happen once, in one place, instead of in eleven pages with eleven wordings.

`src/lib/project-tabs.ts` holds the tab list, `tabHref` and `activeTabId`. The
invariant it exists to keep: **every tab points at a page that ships** — there is
no `phase` field any more, so a deferred tab cannot be declared.

### 1.3 The lifecycle strip was wrong on its own terms

Moving it exposed a second defect. The strip drew four steps —
`DRAFT / IN_PROGRESS / REVIEW / COMPLETE` — and located the current one with:

```ts
stateTimeline.findIndex((s) => s.state === project.state)
```

**`IN_PROGRESS` and `REVIEW` are not project states.** `ProjectState`
(`shared/models/enums.py:15`) is a **thirteen**-state machine and contains
neither. The reference project's live state is `MEDIA_GENERATION`, so `findIndex`
returned **-1**, `idx <= currentOrder` was false for every step, and all four
circles rendered grey for a project that had completed transcript refinement,
storyboard generation, audio and a prototype draft. **It could only ever have lit
up for a project sitting in `DRAFT` or `COMPLETE`.**

`src/lib/project-state.ts` draws the real linear path (11 steps, DRAFT →
COMPLETE), and names `ERROR` and `LOCALISATION` as off-path rather than placing
them at a rank they do not hold.

---

## 2. TASK 2 — honest tab labels

| Tab | Was | Now | Why |
|---|---|---|---|
| **Storyboard** | `Storyboard (soon)` | `Storyboard` → `/projects/{id}/storyboard` | The page existed, worked, and is the one **WP-38** fixed and **WP-40** extended. The label was simply stale. |
| **Prompts** | `Prompts (soon)`, linked to a route with **no page component** | `Prompts` → a real page | `GET /projects/{id}/prompts` has shipped since IVGS-0.4. See below. |

**The Prompts tab was never "soon".** Verified live 2026-08-25:

```
GET /api/v1/projects/c12fa967-…/prompts   -> 200, bare array, 10 entries
  master               GLOBAL  v1   523 chars
  transcript_refinement GLOBAL v2   751
  storyboard_generation GLOBAL v2  1075
  image_generation     GLOBAL  v1   468
  video_generation     GLOBAL  v1   490
  animation_generation GLOBAL  v1   472
  tts_voice            GLOBAL  v1   376
  talking_head         GLOBAL  v1   301
  composition          GLOBAL  v1   489
  translation          GLOBAL  v1   615
```

The new page lists the **effective** prompt per type with the tier that won
resolution (§9.1: scene → project → global), shows the template, and lets an
operator or admin create a **project-tier override** via
`POST /projects/{id}/prompts`.

**One trap avoided deliberately.** The route's response model is `EffectivePrompt`
— **six** keys: `prompt_type, prompt_id, prompt_text, version, source, scene_id`.
It is **not** `PromptResponse`, and the frontend's existing `PromptRecord` type
declares `id`, `scope`, `is_active`, `created_at`, `created_by` and `change_note`
as well. Reusing `PromptRecord` here would have been the WP-40 §0 defect again,
committed on a page built to fix an instance of it. The page declares the wire
shape and nothing more.

`PromptCreate.change_note` is `min_length=1` and **required**; the form says so at
the field rather than letting the server say it in a 422 the operator has to
decode.

No tab claims "soon" for a page that ships, and no tab 404s.

---

## 3. TASK 3 — the Languages tab

### 3.1 (a) Not one code the picker offered could ever be added

The form offered ten bare ISO-639-1 codes: `en, es, fr, de, pt, ja, zh, ko, ar, hi`.
`LanguageVariantCreate.validate_language_code`
(`ivgs-api/app/schemas/language_variant.py:24`) accepts exactly **eight BCP-47**
codes and rejects everything else. **None of the ten is in that set**, and `pt`,
`ko` and `hi` have no accepted form at all — three of the entries were invention.

Reproduced live 2026-08-25:

```
POST /api/v1/projects/c12fa967-…/languages   {"language_code":"es"}   -> 422
{"detail":[{"type":"value_error","loc":["body","language_code"],
  "msg":"Value error, Unsupported language code 'es'. Supported: ar-SA, de-DE,
         en-GB, en-US, es-ES, fr-FR, ja-JP, zh-CN","input":"es"}]}
```

The picker now offers exactly `ar-SA, de-DE, en-GB, en-US, es-ES, fr-FR, ja-JP,
zh-CN`, minus whatever the project already has, and names the constraint under the
field. Proof the new codes reach the service rather than bouncing off validation:

```
POST … {"language_code":"es-ES"}  -> 409
{"detail":{"error":{"code":"VALIDATION_ERROR",
  "message":"Language variant 'es-ES' already exists for this project"}}}
```

**409, not 422** — the code is accepted; that variant simply already exists. And
that message is now what the operator sees, verbatim.

### 3.2 Retry was broken the same way, for a related reason

`retryLanguage` put a language **code** in a path whose parameter is a **UUID**:

```
POST /api/v1/projects/c12fa967-…/languages/en-US/retry   -> 422
{"detail":[{"type":"uuid_parsing","loc":["path","variant_id"],
  "msg":"Input should be a valid UUID, … found `n` at 2","input":"en-US"}]}
```

The variant id is **not on the project detail payload at all** — its
`language_variants` entries are `{language_code, state}` and nothing else. So the
page now reads `GET /projects/{id}/languages`, which carries `id`. Verified:

```
POST …/languages/00000000-0000-4000-8000-000000000000/retry  -> 404
{"detail":{"error":{"code":"RESOURCE_NOT_FOUND",
  "message":"Language variant 00000000-… not found"}}}
```

404, not 422: the path parameter is now the right type and the route runs.

### 3.3 (b) "PENDING 0%" was an absent field, not a measurement

The table read `variant.progress_percent || 0`. **`progress_percent` does not
exist.** `LanguageVariantResponse` (`schemas/language_variant.py:35`) sends exactly
seven keys, verified live:

```json
{"id":"743822dd-…","project_id":"c12fa967-…","language_code":"en-US",
 "state":"pending","final_render_1080p_id":null,"final_render_4k_id":null,
 "created_at":"2026-08-23T08:14:31.873292Z"}
```

The frontend interface declared **ten fields the API has never sent**, including
both the table read: `progress_percent` and `status`. `undefined || 0` is `0`, so
an absent field rendered as a confident zero — beside a language that has a
**finished 720p draft on disk** (`draft_720p_en-US.mp4`, 6,005,929 bytes, asset
`72964509-…`). Two more of the ten were wrong twice over:
`final_render_1080p_url` / `final_render_4k_url` are **ids**, not URLs.

The column now reads **"not tracked yet"**, and the page states plainly why. A
real percentage will render the day one arrives — `variantProgressPercent`
returns a number if the field is ever present and in range, and `null` otherwise.

### 3.4 The backend gap, recorded

> **BACKEND GAP — no per-language progress exists.**
> `LanguageVariantResponse` carries a `state` and two final-render ids. Nothing in
> `ivgs-api`, `ivgs-workers` or `shared/` computes or stores a per-language
> completion figure; `language_variants` has no progress column and
> `LanguageService` writes none. **This is not a frontend defect and cannot be
> fixed client-side.** Closing it means either (a) a progress column written by the
> localisation pipeline, or (b) deriving it from that variant's checkpoints, which
> requires the localisation run to be checkpointed per language. Both are API/worker
> work. Flagged for the backlog; no frontend change is pending on it.

### 3.5 The same sweep on `ProjectResponse`

`ProjectResponse` declared `asset_count`, `target_languages` and `current_job_id`
as **required**; the API sends none of them. The live payload has thirteen keys:

```
id, name, description, max_runtime_seconds, state, hero_image_url, scene_count,
total_duration_estimate_seconds, created_at, updated_at, language_variants,
active_job, created_by
```

`target_languages` is the one that showed: the Overview header rendered a
"Languages: …" row from it, so that row was **permanently absent**, and the
metadata card said "None specified" for a project with two variants. Both now read
`language_variants`, which is the field that is sent. `max_runtime_seconds` is
`Optional[int]`, so `formatRuntime` in `ProjectCard` and `ProjectModal` no longer
formats an absent value as `NaN:NaN`.

---

## 4. TASK 4 — the blank page

### 4.1 It is the Prompts tab, and it took two defects to look black

**Defect one — the route did not exist.** The Prompts tab pointed at
`/projects/{id}/prompts` regardless of its "(soon)" label (`handleTabClick` pushed
`tab.href` unconditionally), and there was no page component. Confirmed live:

```
GET http://192.168.1.90/projects/c12fa967-…/prompts   ->  http=404
markers in body:  next-error-h1 · "This page could not be found"
```

This app had **no `not-found.tsx`**, so Next's built-in error page rendered inside
the root layout. That page styles nothing but its own `<h1>` and inherits
everything else from `body`.

**Defect two — `body` was painting near-black text on a near-black background.**
The root layout's `<body>` className carried each dark utility **twice**, with
contradictory values:

```
min-h-screen bg-gray-50 dark:bg-gray-950 font-sans text-gray-900
dark:text-gray-100 antialiased dark:bg-gray-50 dark:bg-gray-950
dark:text-gray-900 dark:text-gray-100
```

Attribute order does **not** settle a Tailwind conflict — sheet order does, and
Tailwind emits colour utilities by ascending shade. Measured in the **deployed**
bundle, `/app/.next/static/css/23624bb2737bd75a.css` inside `ivgs-nextjs`:

| Rule | Byte offset | Wins? |
|---|---|---|
| `.dark\:text-gray-100:is(.dark *){color:rgb(243 244 246…)}` | 54618 | no |
| `.dark\:text-gray-900:is(.dark *){color:rgb(17 24 39…)}` | **55113** | **yes** |
| `.dark\:bg-gray-50:is(.dark *){background:rgb(249 250 251…)}` | 51982 | no |
| `.dark\:bg-gray-950:is(.dark *){background:rgb(3 7 18…)}` | **52808** | **yes** |

So in dark mode the body painted **`rgb(17 24 39)` on `rgb(3 7 18)`**.

Every other page in the app sets its own text colours on inner elements, which is
exactly why **the only surface ever invisible was the one that inherits from
`body`** — Next's 404. Header and footer are separate components with their own
colours, hence "nav bar only".

### 4.2 The fix, all three parts

1. The Prompts page now exists (§2).
2. `src/app/not-found.tsx` — an honest 404 in the app's own chrome, with links out.
   The backstop for the next missing route.
3. The duplicate/contradictory body classes are gone.

### 4.3 Every other tab, checked against the reference project

| Tab | Route | Live check | Verdict |
|---|---|---|---|
| Overview | `/projects/{id}` | project 200, 13 keys | renders; strip fixed (§5) |
| Transcripts | `…/transcript` | 200, bare array, 1 row, `refined_text` present | renders |
| Storyboard | `…/storyboard` | 200, bare array, 18 scenes | renders; filter fixed (§7) |
| Media Assets | `…/assets` | 200, envelope, 40 assets | renders (WP-40) |
| Audio | `…/audio` | derived from assets, 18 audio | renders (WP-40) |
| Talking Head | `…/talking-head` | 1 `talking_head` asset, 50.5 MB | renders (WP-40) |
| Draft Preview | `…/draft` | `draft_720p_en-US.mp4` in assets | renders (WP-40) |
| Final Renders | `…/renders` | from assets | renders (WP-40) |
| **Prompts** | `…/prompts` | **was 404** | **fixed — the blank page** |
| Jobs | `…/jobs` | 200, envelope, 10 jobs | renders |
| Languages | `…/languages` | 200, bare array, 2 variants | renders; fixed (§3) |

---

## 5. TASK 5 — Overview Pipeline Progress

### 5.1 Verdict: stale, not a caching artifact

The operator's screenshot was **accurate**. The all-grey strip reproduces
deterministically from the captured payloads in the test file.

WP-40 §2.6's half of the fix is **correct and unchanged**: `mergeCheckpoints` maps
the worker's lowercase `stage_name` (`transcript_refinement`, `tts_audio`, …) onto
the eight display stages and normalises `complete`/`failed` to the page's
vocabulary. That was verified, not assumed.

### 5.2 The remaining fault was job SELECTION

`PipelineTracker` took `jobs[0]`. `GET /projects/{id}/jobs` is ordered
**newest-first**. Measured live 2026-08-25 — all ten jobs of c12fa967, with the
checkpoint count of each:

| Job | Type | Status | Created | Checkpoints |
|---|---|---|---|---|
| `d3842fdf` | storyboard_generation | pending | 2026-08-25T00:40:35Z | **0** |
| `c4249f92` | storyboard_generation | pending | 2026-08-25T00:40:33Z | 0 |
| `7d6a44b2` | storyboard_generation | pending | 2026-08-23T22:10:44Z | 0 |
| `4646aeba` | storyboard_generation | pending | 2026-08-23T22:10:37Z | 0 |
| `c57ec7b7` | storyboard_generation | pending | 2026-08-23T20:51:25Z | 0 |
| `9fdea8ae` | storyboard_generation | pending | 2026-08-23T20:51:17Z | 0 |
| `6a16e1a6` | storyboard_generation | pending | 2026-08-23T20:50:58Z | 0 |
| **`bd99fe37`** | **transcript_refinement** | **success** | **2026-08-23T16:00:59Z** | **7 (6 complete)** |
| `e408515a` | transcript_refinement | failed | 2026-08-23T15:24:33Z | 2 (1 failed) |
| `768c4b59` | transcript_refinement | failed | 2026-08-23T14:49:48Z | 2 (unmappable probes) |

**The run that produced this project's draft is the eighth row.** Seven
checkpoint-less rows stood in front of it, and the strip faithfully reported the
emptiness of the newest one.

`bd99fe37`'s checkpoints, verbatim:

```
1 transcript_refinement complete  16:00:59 -> 16:01:37
2 storyboard_generation complete  16:01:37 -> 16:03:25
3 image_generation      complete  16:45:05 -> 16:46:54
3 video_generation      pending   16:47:01 -> (open)
4 tts_audio             complete  18:45:02 -> 18:46:19
5 talking_head_render   complete  19:23:07 -> 19:23:07
6 prototype_draft       complete  19:23:10 -> 19:24:15
```

### 5.3 The fix, and what the strip will now draw

`useProjectPipelineRun` fetches every job's checkpoints (capped at 25 newest, and
the cap is *reported* if it bites) and `selectPipelineRun` picks the newest job
that has checkpoints the display can map. **The strip names that run.** That is
the substantive part: once the run is identified, a grey node means "this run did
not reach that stage" and can no longer mean "the strip is looking somewhere
else". It also reports how many newer jobs recorded nothing — which, on this
project, is the whole story.

For c12fa967 the strip now draws:

| Stage | Colour | From |
|---|---|---|
| Transcript Refinement | **green ✓** | complete |
| Storyboard Generation | **green ✓** | complete |
| Media Generation | **blue (running)** | image complete + video still open — the merge is pessimistic |
| Manifest | grey | no checkpoint in this run |
| Audio Generation | **green ✓** | `tts_audio` complete |
| Talking-Head Sync | **green ✓** | complete |
| Prototype Draft | **green ✓** | complete |
| Final Render | grey | no checkpoint in this run |

**Five green, one blue, two grey** — pinned as a test.

### 5.4 One thing deliberately not done

**Merging checkpoints across all ten jobs.** `e408515a` holds a **failed**
`storyboard_generation` from a superseded 15:24 attempt that `bd99fe37` then
completed at 16:03. `mergeCheckpoints` is pessimistic by design (any failure wins),
so a cross-job merge would paint Storyboard Generation **red** over a stage that
demonstrably succeeded. One run, named, is the honest unit.

A project whose jobs have written no checkpoint at all now says so in words,
instead of drawing eight grey circles that read as "the pipeline has not started".

---

## 6. TASK 6 — Model Store dialog, and the auth refresh 422

### 6.1 (a) The message existed. It was rendered underneath the dialog.

The Approve dialog silently rejected checklist JSON that is not an object; an
**array** produced a dead Approve button with no message of any kind.

The validation was right all along. The chain:

```
parseJsonField  throws
  -> submitApprove's catch
    -> flashErr(e)
      -> setActionError(msg)
        -> rendered at PAGE level, page.tsx ~line 419
```

…and the Approve modal is a `fixed inset-0 z-50` overlay with a `bg-black/50`
backdrop, rendered *after* that banner in the tree. **The one message that existed
was painted behind the dialog the operator was looking at.** The modal does not
close on error, so it stayed up, unchanged.

It was worse than a hidden message: `parseJsonField` throws **before**
`setBusyId(approveTarget.id)`, so the button was not even disabled. Nothing moved
at all.

**Fix.** `jsonFieldError` returns the message instead of throwing, and the dialog
renders it **at the field**, with the input outlined and `aria-invalid` set. Array,
`null` and scalar each get their own wording — the array case is the one that bit,
and it now says to wrap the entries in an object. The empty-checklist rule the
route enforces itself (`if not body.checklist` → *"attestation checklist must not
be empty (AD-01.7.2)"*, `model_store.py:174`) is checked here too, so it does not
cost a round trip. Attested-by and vetting reference get the same treatment, and
all fields are validated together so the operator sees every problem at once.

A **server** refusal now lands in the modal as well, and a 422's per-field detail
is placed at the field it names, via `fieldErrors`.

### 6.2 (b) The recurring `POST /api/v1/auth/refresh` 422 — client-side, and fixed

The client sent the refresh token as an **`Authorization` header with no body**:

```ts
fetch("/api/v1/auth/refresh", {
  method: "POST",
  headers: { "Content-Type": "application/json",
             Authorization: `Bearer ${refreshToken}` },
});                                    // <- no body
```

`auth_refresh` (`ivgs-api/app/api/v1/auth.py:102`) takes `body: RefreshRequest` —
a JSON object with a **required** `refresh_token` field — and ignores the header
entirely. FastAPI rejected every refresh before the route ran. Reproduced live:

```
POST /api/v1/auth/refresh   (header only, no body)   -> 422
{"detail":[{"type":"missing","loc":["body"],"msg":"Field required","input":null}]}
```

**That is the console 422, and it explains the operator's symptom exactly.** A
refresh could never succeed → `refreshAccessToken` always returned `false` →
`clearTokens()` ran → the next request went out unauthenticated. Reads already in
the SWR cache kept displaying; **writes failed quietly.**

**A second bug in the same six lines.** `TokenResponse` (`schemas/auth.py:16`)
returns a **new** `refresh_token`, and the route's own docstring says the old one
is invalidated after exchange. The client did `setTokens(data.access_token,
refreshToken)` — re-storing the **old** token. So even a correctly-shaped request
would have worked once and failed forever after. Both are fixed together.

**Verified live** (a refresh token registered in Redis exactly as `login()`
registers one, then exercised through the real route):

```
OLD shape (header, no body)  -> 422  {"detail":[{"loc":["body"],"msg":"Field required"}]}
NEW shape (JSON body)        -> 200  keys: access_token, expires_in,
                                            refresh_token, token_type
                                     ROTATED: True     expires_in: 3600
```

**No API change was needed. The request was simply the wrong shape.**

---

## 7. TASK 7 — Edit Scene: the media type (run-blocker)

### 7.1 Exactly what the frontend sent vs what the route accepts

**What the route accepts.** `SceneUpdate.validate_media_type`
(`ivgs-api/app/schemas/storyboard.py:39`):

```python
if v is not None and v not in ("image", "video_clip", "animation"):
    raise ValueError("media_type must be one of: image, video_clip, animation")
```

**What the frontend sent.** `src/types/storyboard.ts` declared five **UPPERCASE**
values — `IMAGE`, `VIDEO`, `ANIMATION`, `TALKING_HEAD`, `STOCK` — and the modal
offered all five. **Not one of the five is accepted.** Two of them
(`TALKING_HEAD`, `STOCK`) name pipelines this route cannot select at all, so the
picker was offering a promise the API never made.

Reproduced live 2026-08-25 with the modal's exact body:

```
PATCH /api/v1/projects/c12fa967-…/scenes/6c9b010e-…  -> 422
{"detail":[{"type":"value_error","loc":["body","media_type"],
  "msg":"Value error, media_type must be one of: image, video_clip, animation",
  "input":"VIDEO"}]}
```

`src/types/api.ts:212` had the union **right the whole time**
(`"image" | "video_clip" | "animation"`). The two type files contradicted each
other; the wire settles it.

### 7.2 The same mismatch was visible without pressing Save

- **`SceneCard`** keyed `MEDIA_TYPE_ICONS` and `MEDIA_TYPE_LABELS` by `"IMAGE"`
  over a wire value of `"image"`. Both resolved to `undefined`: the type badge on
  every card rendered as an **empty pill**, and the thumbnail fallback fell through
  to a generic frame.
- **The storyboard's media-type filter** compared `"image" === "IMAGE"`, so **every
  option emptied the grid**.

### 7.3 A third finding: five fields were being sent and discarded

The modal sent **nine** keys. `SceneUpdate` declares **four**. Pydantic ignores
unknown keys, so `camera_angle`, `transition_type`, `effects`, `timing_offset_ms`
and `generation_params` were serialised, sent, and dropped on the floor — no error,
no storage, and a UI that looked as though it had saved them.

Adding the columns is API work and out of scope for a frontend-only package, so
those controls now carry an explicit **"Not saved to the server"** notice.
`sceneUpdatePayload` emits exactly the four declared keys.

Two further deliberate behaviours: a `media_type` that normalises to nothing is
**dropped** rather than sent into a 422 — so an edit to narration still lands
instead of the whole save failing — and a null `media_type` displays as
**"Not set"** rather than being asserted to be an image.

### 7.4 Verified live on the reference project

Scene `6c9b010e-00c0-44f2-a952-933095e09ab2` (scene_index 0), each read back with
an **independent** `GET`:

| Step | PATCH body | HTTP | Read back |
|---|---|---|---|
| before | — | — | `media_type='image'`, updated `2026-08-23T16:03:24Z` |
| 1 | full four-key payload, `"media_type":"video_clip"` | **200** | **`'video_clip'`**, updated `2026-08-25T01:35:21.588029Z` |
| 2 | `{"media_type":"animation"}` | **200** | **`'animation'`**, updated `01:35:37.947091Z` |
| 3 | `{"media_type":"image"}` | **200** | `'image'`, updated `01:35:37.974943Z` |

All three transitions succeed, and **the scene is left exactly as it was found.**
The round trip was completed rather than left on `video_clip` deliberately: proving
the capability does not require changing what scene 0 of the operator's live
project will generate. Reverting is one click in the dialog if that is wanted.

### 7.5 A fourth finding, from the same vocabulary

The Prompt Editor's built-in `storyboard_generation` sample instructed the model
to emit `media_type: one of IMAGE, VIDEO, ANIMATION, TALKING_HEAD`. All four are
refused by `SceneCreate`/`SceneUpdate`, so the sample was **teaching the exact
vocabulary that produced the 422** — and an operator who copied it into a live
prompt would have produced scenes whose `media_type` the API drops on create.
Corrected to `image / video_clip / animation`, matching the wire and the picker.

---

## 8. `ivgs-api` was not touched — and the STOP condition was not met

Every task was completable client-side. The full diff is **35 files, all under
`ivgs-frontend/`** — zero Python, zero `ivgs-api`, zero `ivgs-workers`.

Two things were found that the API *would* have to fix, and neither blocked a task:

| Gap | Task | Status |
|---|---|---|
| No per-language progress figure exists anywhere in the system | 3b | **Recorded** (§3.4). Frontend says "not tracked yet" — honest, and complete for this package. |
| `SceneUpdate` stores 4 of the 9 scene properties the editor presents | 7 | **Recorded** (§7.3). Frontend labels the other five as not persisted. |

Neither is a case of "the task cannot be done client-side" — in both, the honest
frontend behaviour *is* the deliverable, and the API work is a separate item.

---

## 9. What the operator should see differently, per tab

| Tab | Before | After |
|---|---|---|
| **Every tab** | tab bar on Overview only; bare "← Back" everywhere else | project name, state badge, lifecycle strip and all eleven tabs on **every** page, active tab highlighted, tabs are real links |
| **Overview** | four grey lifecycle circles; Pipeline Progress all grey; "Languages: None specified" | lifecycle strip lit to `MEDIA_GENERATION` (3 done + current); progress strip **5 green, 1 blue, 2 grey**, captioned with which run it is showing; Languages reads `en-US, es-ES` |
| **Storyboard** | tab said "(soon)"; every media-type filter option emptied the grid; every card's type badge was an empty pill | tab routes normally; filter offers Image / Video Clip / Animation and matches; badges read "🖼️ Image" |
| **Edit Scene** | any media-type change → "Request failed with status 422"; storyboards stuck all-static | Image / Video Clip / Animation, all three save; the field shows the exact value being sent; server refusals appear in full words |
| | five controls silently discarded | those five now say "Not saved to the server" and why |
| **Prompts** | **black page, nav bar only** | ten effective prompts with GLOBAL / PROJECT / SCENE badges, versions, full templates, and a project-override editor |
| **Languages** | Add → "Request failed with status 422", always; Retry → the same; "PENDING 0%" beside a finished draft | picker offers the eight accepted BCP-47 codes; failures show the server's own sentence at the field; Retry reaches the route; progress column says **"not tracked yet"** with the reason stated |
| **Jobs / Assets / Audio / Talking Head / Draft / Renders / Transcripts** | working (WP-40), but each isolated behind a back link | unchanged content, now reachable from any tab in one click |
| **Prompt Editor (global)** | the storyboard sample template taught `IMAGE, VIDEO, ANIMATION, TALKING_HEAD` — all four rejected by the API | teaches `image, video_clip, animation` |
| **Admin → Model Store** | Approve with an array checklist: button dead, no message anywhere | inline red message at the checklist field naming the problem and the fix; server refusals land inside the dialog |
| **Anywhere** | recurring `auth/refresh` 422; writes failing quietly on a stale session | refresh succeeds and rotates; writes keep working |
| **Any bad URL** | Next's default 404, invisible in dark mode | a readable 404 in the app's chrome, with links out |

---

## 10. Tests

### 10.1 `npm run test:logic` — **98 passing, 0 failing**

`src/lib/__tests__/ui-nav.test.mjs` — every fixture is a **real** response body
captured live on 2026-08-25 from `ivgs-api:v5.6.5-reviewgate`. Per the WP-35/38/40
pattern, each defect is **reproduced first**, then its fix is pinned. The old
`api-client` reducer is reproduced verbatim inside the test file so the "before"
is executable, not asserted.

| Group | Tests | What is pinned |
|---|---|---|
| T7 media type | 5 | the old payload is rejected; the new one is four accepted keys; the five phantom keys are gone; `"image"` is displayable; unknown/null is never asserted to be an image; duration honours `ge=0.1 le=600` |
| Errors (T3a/T6/T7) | 6 | all four real 422s reduced to a bare status by the old reducer; each now reads as the server wrote it; the envelope shapes still work; multi-field joins; a genuinely empty body still falls back to the status |
| T3 languages | 8 | none of the ten old codes is acceptable; the eight new ones are; existing variants are not re-offered; `progress_percent` absent on both payload shapes; a real percentage would still show; state is lowercase on the wire; retry needs the UUID the list route carries |
| T5 pipeline | 6 | `jobs[0]` yields eight greys; the 8th row is selected; five green / one blue / two grey; a superseded failure does not repaint a passed stage; unmappable probes never become a run; empty and shuffled inputs |
| T1/T2/T4 nav | 4 | eleven tabs, no "soon", every tab has a route; hrefs; active tab on every tab and on deeper paths; the Prompts tab identified as the blank one |
| T1 lifecycle | 4 | the old four-step strip cannot place `MEDIA_GENERATION`; the new one is the real FSM; `IN_PROGRESS`/`REVIEW` are gone; off-path states are named |
| T6 refresh | 3 | the header-only request is what FastAPI rejects; the new body carries the declared field; rotation is honoured with the old token only as fallback |

New pure modules, all under test: `errors.ts`, `scenes.ts`, `languages.ts`,
`pipeline-run.ts`, `project-tabs.ts`, `project-state.ts`.

### 10.2 Type check and build

```
npx tsc --noEmit     ->  rc 0
npm run build        ->  rc 0
```

The build output lists `ƒ /projects/[id]/prompts` — the route that used to 404 —
and `○ /_not-found`.

### 10.3 Python suite — run once, zero delta

Not required by any change in this package (the diff contains no Python), run as a
regression baseline. `TEST_DATABASE_URL` → `ivgs_reconciliation_test`.

```
71 failed, 1306 passed, 53 skipped, 1438 warnings, 77 errors in 209.51s
```

**Identical to the post-WP-42 baseline** recorded at
`WP-42-VOICE-report_2026-08-23.md:250` (that report's run 2 was 1305/72/53/77 with
one WP-42 failure, which WP-42 then fixed — leaving exactly 1306/71/53/77). Zero
delta, as expected for a diff with no Python in it.

**Two environment notes, neither of which is a run:**

- The system `python3` has no `pytest` module; the suite runs from `.venv`.
- A first attempt aborted at collection: `DATABASE_URL` pointed at `testdb` and
  the conftest guard refused it — *"REFUSING TO RUN TESTS: target database 'testdb'
  does not look like a test database"*. The same note WP-42 recorded. Neither
  attempt consumed the two-run budget; **one** real run was used.

Honest qualification: the capture was the tail of the output, so the counts above
are from the summary line and the errors list, not a full enumeration of all 71
failure ids. The equality with the recorded baseline is the claim being made.

---

## 11. Deploy — `v5.7.0-uinav`, node-01 frontend only

### 11.1 Preflight, and one recorded deviation from WP-34 R1

| Check | Result |
|---|---|
| Tracked tree clean before build | **yes** — only the untracked report |
| `HEAD == origin/main` | **no — 7 ahead.** See below. |
| `tsc --noEmit` | **rc 0** |
| `npm run build` | **rc 0** |
| `npm run test:logic` | **98 pass, 0 fail** |
| Python suite | 71F / 1306P / 53S / 77E — identical to the recorded baseline |

**Deviation, stated rather than assumed.** WP-34 R1 required `HEAD == origin/main`
because that package deployed a *pushed* commit across four nodes. This package's
brief says **commit and HOLD — never push**, *and* build/deploy as `v5.7.0-uinav`.
The two cannot both hold, so the image is built from local `HEAD`, which is
`origin/main` plus exactly the seven WP-43 commits and nothing else — verified by
`git log --oneline origin/main..HEAD`. The tracked tree was clean at build time, so
the image content is reproducible from those commits.

### 11.2 The image

```
docker build -f ivgs-frontend/Dockerfile -t ghcr.io/brucecostello2/ivgs-frontend:v5.7.0-uinav .
BUILD_RC=0
```

| | |
|---|---|
| Tag | `ghcr.io/brucecostello2/ivgs-frontend:v5.7.0-uinav` |
| Image id | `sha256:bf5f20f0800d979c1addbc44863092e9477b23416820b79fa91ff0a5d1d1f3f5` |
| Size | 259 MB |
| Pushed to a registry | **no** — built and used locally, as with every prior frontend deploy on this node |

Build success was re-checked against `docker images`, not trusted from the exit
code.

### 11.3 Content gates — every one is a `grep` INSIDE the image

The runtime image is a Next.js **standalone** build: compiled, minified JS, not
`.tsx`. So the gates are split, exactly as WP-34 §2.1 split them.

**Builder stage** (`--target builder` — the exact `COPY` that fed the bundle):

| Gate | Path | Count |
|---|---|---|
| T1 tab list | `/app/src/lib/project-tabs.ts` — `PROJECT_TABS` | 2 |
| T1 real FSM strip | `/app/src/lib/project-state.ts` — `TRANSCRIPT_REFINEMENT` | 1 |
| T3a supported codes | `/app/src/lib/languages.ts` — `en-GB` | 2 |
| T3b honest progress | `/app/src/lib/languages.ts` — `variantProgressPercent` | 1 |
| T5 run selection | `/app/src/lib/pipeline-run.ts` — `selectPipelineRun` | 1 |
| T6b refresh body | `/app/src/lib/api-client.ts` — `refresh_token: refreshToken` | 1 |
| T3a/6/7 verbatim 422 | `/app/src/lib/errors.ts` — `apiErrorMessage` | 1 |
| T7 wire media types | `/app/src/lib/scenes.ts` — `video_clip` | 9 |
| T6a inline field error | `/app/src/app/admin/models/page.tsx` — `jsonFieldError` | 4 |

**Files that must exist** — all four `present`:
`/app/src/app/not-found.tsx`, `/app/src/app/projects/[id]/layout.tsx`,
`/app/src/app/projects/[id]/prompts/page.tsx`,
`/app/src/components/project/ProjectShell.tsx`.

**Runtime image** (`/app/.next`):

| Gate | Result |
|---|---|
| `video_clip` in the compiled bundle | 4 files |
| `not tracked yet` in the compiled bundle | 2 files |
| the run caption ("recorded no…") | 2 files |
| `projects/[id]/prompts` in `app-paths-manifest.json` | **present** |
| the prompts page's own chunk | `/app/.next/server/app/projects/[id]/prompts/page.js` and `/app/.next/static/chunks/app/projects/[id]/prompts/page-53ade92ac701c281.js` |

### 11.4 Negative gates — two needed interpretation, and both pass

| Negative gate | Literal | Verdict |
|---|---|---|
| no `Back to Overview` under `app/projects` | 0 | **PASS** |
| no uppercase media type in the modal | 0 | **PASS** |
| no `(soon)` under `app/` | **1** | **PASS, comment-scoped** |
| no `dark:text-gray-900` in `layout.tsx` | **2** | **PASS, comment-scoped** |

Both non-zero results are **comments**, and a naive whole-tree grep would have
failed on correct code — the same shape of result WP-34 §2.2 recorded for
`latentsync_low_alignment`.

- The one `(soon)` is at `prompts/page.tsx:18`, inside the docstring explaining
  the defect this page fixes. Outside comments: **0**.
- Both `dark:text-gray-900` hits are at `layout.tsx:71` and `:76`, inside the
  comment block that quotes the old className and the measured byte offsets.

**The decisive check is the `<body>` element itself**, and it is clean at source
and in the compiled bundle:

```
source  layout.tsx:88
  <body className="min-h-screen bg-gray-50 dark:bg-gray-950 font-sans
                   text-gray-900 dark:text-gray-100 antialiased">

compiled /app/.next/server (the only two matches, and they agree)
  min-h-screen bg-gray-50 dark:bg-gray-950
  min-h-screen bg-gray-50 dark:bg-gray-950 font-sans text-gray-900
  dark:text-gray-100 antialiased
```

No duplicate, no contradiction. All four utilities still exist *in the stylesheet*
(one rule each) because other components legitimately use them — what changed is
that `<body>` no longer applies two of each.

### 11.5 The deploy — node-01, one service

Compose invocation **derived from container labels**, not guessed:

```
docker inspect ivgs-nextjs --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}'
  -> /opt/ivgs/ivgs-infra/docker-compose.node01.yml,
     /opt/ivgs/ivgs-infra/docker-compose.override.node01.yml,
     /opt/ivgs/ivgs-infra/docker-compose.monitoring.yml
docker inspect ivgs-nextjs --format '{{index .Config.Labels "com.docker.compose.service"}}'
  -> nextjs-frontend
```

`ivgs-infra/.env` backed up first, per the existing convention:
`.env.bak.pre-frontend-v5.7.0-uinav-20260825-015056`. Then exactly one line changed:

```
IVGS_FRONTEND_TAG=v5.6.8-uibatch2   ->   IVGS_FRONTEND_TAG=v5.7.0-uinav
```

Proven, not asserted — masking that one key and diffing the backup against the
live file gives an **empty diff**. The other four tag variables are untouched:
`IVGS_API_TAG=v5.6.5-reviewgate`, `IVGS_SCHEDULER_TAG=v5.0.0-20260522`,
`IVGS_WORKERS_TAG=v5.6.9-voice`, `IVGS_BACKUP_WORKER_TAG=v5.1.0-stream-b`.

```
docker compose -f docker-compose.node01.yml \
               -f docker-compose.override.node01.yml \
               -f docker-compose.monitoring.yml \
               --env-file .env  up -d --no-deps nextjs-frontend
  Container ivgs-nextjs Recreated / Started      rc=0
```

`--no-deps` matters here: `nginx` carries
`depends_on: nextjs-frontend: condition: service_healthy`, so without it the
recreate would have reached further than its name suggests.

### 11.6 Deploy evidence

**Which image is running** — read from `docker inspect`, never from a container
env var (WP-34 §6's trap):

```
docker inspect ivgs-nextjs --format '{{.Config.Image}}'
  -> ghcr.io/brucecostello2/ivgs-frontend:v5.7.0-uinav
docker inspect ivgs-nextjs --format '{{.Image}}'
  -> sha256:bf5f20f0800d979c1addbc44863092e9477b23416820b79fa91ff0a5d1d1f3f5
```

That id is byte-identical to the one `docker build` produced.

**Exactly one container was recreated.** `docker ps` captured before and after;
the diff is one line:

```
< ivgs-nextjs  ghcr.io/brucecostello2/ivgs-frontend:v5.6.8-uibatch2
> ivgs-nextjs  ghcr.io/brucecostello2/ivgs-frontend:v5.7.0-uinav
```

Uptimes confirm it — `ivgs-nextjs` "Up 16 seconds (healthy)", and **every other
one of the eighteen containers still reads "Up 4 hours" or "Up 5 hours"**:
Postgres, Redis, all three SeaweedFS services, `ivgs-fastapi`, all three Celery
workers, the scheduler, nginx and the whole monitoring stack. `ivgs-nextjs` reached
`healthy` on its own healthcheck.

**Every project tab, live through nginx** (HTTPS, following the http→https 301):

| Tab | Before | After |
|---|---|---|
| `/projects/{id}` | 200 | **200** |
| `/transcript` | 200 | **200** |
| `/storyboard` | 200 | **200** |
| `/assets` | 200 | **200** |
| `/audio` | 200 | **200** |
| `/talking-head` | 200 | **200** |
| `/draft` | 200 | **200** |
| `/renders` | 200 | **200** |
| **`/prompts`** | **404 (the black page)** | **200** |
| `/jobs` | 200 | **200** |
| `/languages` | 200 | **200** |

**The prompts route serves the real page**, not an error page: 15,449 bytes,
`next-error-h1` count **0**, its own chunk `page-53ade92ac701c281.js` referenced,
and the project shell present.

**The tab bar is now on a sub-page.** Server-rendered HTML of
`/projects/{id}/languages` — a page that until now had only a "← Back" link —
contains `Media Assets`, `Talking Head`, `Draft Preview`, `Final Renders`,
`Storyboard`, `Prompts` and `Gallery`, and contains `(soon)` **zero** times.

**The 404 backstop works:**

```
GET /no-such-page   -> 404
markers: "This page does not exist", "Go to Gallery"
next-error-h1: absent
```

### 11.7 Rollback

One command, and the image it needs is already on the node:

```
# RUN ON: IVGS node-01 (192.168.1.90)
( cd /opt/ivgs/ivgs-infra
  sed -i 's|^IVGS_FRONTEND_TAG=.*|IVGS_FRONTEND_TAG=v5.6.8-uibatch2|' .env
  docker compose -f docker-compose.node01.yml \
                 -f docker-compose.override.node01.yml \
                 -f docker-compose.monitoring.yml \
                 --env-file .env up -d --no-deps nextjs-frontend
  docker inspect ivgs-nextjs --format '{{.Config.Image}}' )
```

Verified present in the local store: `ivgs-frontend:v5.6.8-uibatch2`
(`7511ba25f290`), plus `v5.6.7-uibatch` and `v5.6.5-reviewgate` behind it. The
`.env` backup is a second path: `cp .env.bak.pre-frontend-v5.7.0-uinav-20260825-015056 .env`.

### 11.8 What was NOT touched

`ivgs-api`, `ivgs-workers`, `ivgs-scheduler`, `ivgs-backup-worker`, Postgres,
Redis, SeaweedFS (master, volume, filer), nginx, Prometheus, Grafana,
Alertmanager, Pushgateway, node-exporter — **none recreated**, all still on their
pre-existing uptimes. **node-02, node-03 and node-04 were not contacted at all**;
no vLLM, CogVideoX or LatentSync container was touched. The only registry tag
changed anywhere is `IVGS_FRONTEND_TAG` on node-01.

---

## 12. Push block — count-gated, ALL held commits

**Nothing has been pushed.** `git fetch origin` was run before counting, so the
number below is measured against a fresh remote ref, not a stale one.

```
git rev-list --left-right --count HEAD...origin/main   ->   8    0
```

**8 ahead, 0 behind. All eight are this package.** No commit from WP-40, WP-41 or
WP-42 is still held — `origin/main` is at `cee3b69`, WP-42's commit.

| # | SHA | Subject |
|---|---|---|
| 1 | `e83e635` | fix(wp-43): the server named the field and the reason; the client showed the status |
| 2 | `92fb2ea` | fix(wp-43): no media type the picker offered was one the API would accept |
| 3 | `00dd6aa` | fix(wp-43): the 0% was an absent field, and no code in the picker was addable |
| 4 | `450e9b7` | fix(wp-43): the progress strip was reading a job that had never run |
| 5 | `dd28ef4` | fix(wp-43): the attestation error was rendered underneath the dialog showing it |
| 6 | `76397bf` | feat(wp-43): the tab bar existed on one tab out of eleven |
| 7 | `6a7cbfc` | fix(wp-43): the storyboard prompt template still taught the rejected vocabulary |
| 8 | *(this commit)* | docs(wp-43): the report — seven tasks, three causes, and the deploy evidence |

**The block is count-gated: it refuses to push unless the count is exactly what
this report states.** Run it only when you intend to publish.

```
# RUN ON: IVGS node-01 (192.168.1.90)
( set -u
  cd /opt/ivgs || { echo "ABORT: no /opt/ivgs"; exit 1; }

  EXPECTED_AHEAD=8
  EXPECTED_HEAD_SUBJECT="docs(wp-43): the report"

  echo "--- fetching, so the count is against a fresh ref ---"
  git fetch origin || { echo "ABORT: fetch failed"; exit 1; }

  DIRTY=$(git status --porcelain --untracked-files=no | wc -l)
  if [ "$DIRTY" -ne 0 ]; then
    echo "ABORT: tracked files are dirty ($DIRTY). Not pushing."
    git status --short
    exit 1
  fi

  AHEAD=$(git rev-list --count origin/main..HEAD)
  BEHIND=$(git rev-list --count HEAD..origin/main)
  HEAD_SHA=$(git rev-parse --short HEAD)
  HEAD_SUBJECT=$(git log -1 --format=%s)

  echo "  ahead=$AHEAD  behind=$BEHIND  head=$HEAD_SHA"
  echo "  subject: $HEAD_SUBJECT"
  echo "  expected ahead=$EXPECTED_AHEAD  expected subject starts: $EXPECTED_HEAD_SUBJECT"

  if [ "$BEHIND" -ne 0 ]; then
    echo "ABORT: $BEHIND commit(s) behind origin/main. Rebase first."
    exit 1
  fi
  if [ "$AHEAD" -ne "$EXPECTED_AHEAD" ]; then
    echo "ABORT: expected $EXPECTED_AHEAD held commits, found $AHEAD."
    echo "       Something changed since the report. Re-read before pushing."
    git log --oneline origin/main..HEAD
    exit 1
  fi
  case "$HEAD_SUBJECT" in
    "$EXPECTED_HEAD_SUBJECT"*) : ;;
    *) echo "ABORT: HEAD is not the WP-43 report commit."
       echo "       subject is: $HEAD_SUBJECT"
       exit 1 ;;
  esac

  echo "--- the 8 commits about to be pushed ---"
  git log --oneline origin/main..HEAD

  echo
  printf 'Type PUSH to publish these 8 commits to origin/main: '
  read -r CONFIRM
  if [ "$CONFIRM" != "PUSH" ]; then echo "Not pushed."; exit 0; fi

  git push origin HEAD:main && echo "Pushed. origin/main is now $HEAD_SHA."
) 2>&1 | tr -cd '\11\12\15\40-\176'
```

---

## 13. Decisions for the operator

| # | Decision | Recommendation |
|---|---|---|
| **D-1** | **Per-language progress (§3.4).** Nothing in IVGS records it. The column now says "not tracked yet". Close the gap with a progress column written by the localisation pipeline, or derive it from per-language checkpoints? | Derive from checkpoints — it reuses machinery that exists and cannot drift from reality the way a separately-written column can. API/worker work, not this package. |
| **D-2** | **Five scene properties are presented but not stored (§7.3).** Camera angle, transition, effects, timing offset, generation params. They now say so. Extend `SceneUpdate` and the `scenes` table, or remove the controls? | Extend the API. `camera_angle` and `transition_type` are referenced by the generation and composition prompts; removing them loses intent the operator is already expressing. |
| **D-3** | **Seven `storyboard_generation` jobs on c12fa967 are `pending` with zero checkpoints**, two of them created 2026-08-25. Nothing is consuming them. This is what made the progress strip look dead. Separate investigation? | Yes — worth its own item. The frontend now reports the situation honestly, but seven stranded jobs on a live project is a pipeline question, not a UI one. |
| **D-4** | **Scene `6c9b010e` was restored to `image`** after proving all three media types save (§7.4). The alternative was leaving it on `video_clip` as standing evidence. | Left as found. Say the word if you would rather scene 0 actually be a video clip. |
