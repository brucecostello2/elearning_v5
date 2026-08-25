# WP-52-TESTENV — the suite gets its environment back

**Date:** 2026-08-25 · **Node:** node-01 only · **Status:** complete, committed, HELD

| | |
|---|---|
| **Deliverable** | `dev/workpackages/reference/TEST-BASELINE_2026-08-25.md` |
| **Commits** | 7, all held on `main`, nothing pushed |
| **Images built** | none |
| **Deploys** | none |
| **Nodes visited** | none — node-01 only |
| **Compose changes** | none |
| **Full-suite runs** | 2 (`ivgs-api`, before and after), plus one run each of the four other trees |
| **Live data written** | none — verified, §8.3 |

---

## 1. Headline

| Tree | Before | After |
|---|---|---|
| `ivgs-api` | 2 failed / 831 passed | **833 passed, 0 failed** |
| `ivgs-workers` | 27 failed | 22 failed / 754 passed / 48 skipped / 15 errors |
| `ivgs-scheduler` | 9 passed / 2 failed / 32 errors | 22 passed / 21 failed |
| `ivgs-backup-worker` | 4 errors (never ran) | **4 passed, 0 failed** |
| `tests_system` | 15 passed / 31 failed / 28 errors | 30 passed / 16 failed / 15 skipped / 30 errors |

**Two trees are green. The remaining 59 failures and 45 errors reduce to 11
named causes**, every one of them in the baseline document with a file:line and
a ledger id. There are no unexplained failures.

The scheduler's row needs reading carefully: it looks worse and is not. Thirty-two
of its forty-three tests errored at setup on one unresolvable import and never
ran, so nobody knew what they said. They run now — 13 pass, 19 fail, all 19
diagnosed. That trade is the package.

---

## 2. What the work order got wrong, and what was actually there

The order asked me to establish the failure before fixing it, and not to assume
its own diagnosis was the whole of it. It was not the whole of it; it was not
any of it.

**Claim:** *passlib 1.7.4 and bcrypt 4.2.1 are incompatible in `.venv`; every
fixture that creates a user raises on import; the ivgs-api suite has effectively
not run in this venv for some time.*

**Measured:** the pairing works. passlib traps its own `AttributeError` on
`bcrypt.__about__.__version__`, logs `(trapped) error reading bcrypt version`
with a traceback, and carries on. Hash and verify both succeed, `$2b$12$`,
60 chars. Same in `.venv` and same inside the **running `ivgs-fastapi`
container** (bcrypt 4.2.1, passlib 1.7.4, Python 3.12.8) — the order asked for
that answer either way, and the answer is: identical pairing, identical
behaviour, and it works there too.

And the suite has been running. It collected 833 tests with zero errors and
finished 2 failed / 831 passed — exactly where WP-45 left it. Those two failures
had nothing to do with bcrypt (§3.2).

I have kept this at the front of the report because the diagnosis had already
been written down twice and would have been actioned a third time. Pinning
`bcrypt` back to 3.x — one of the two options the order offered — would have
downgraded a security-critical library to fix something that was not broken.

---

## 3. Task 1 — the venv

### 3.1 passlib retired, bcrypt called directly

`ivgs-api/app/core/security.py` now calls `bcrypt` directly; `passlib[bcrypt]==1.7.4`
is out of `ivgs-api/requirements.txt`. **Chosen over pinning bcrypt to 3.x**, for
reasons that survive the corrected diagnosis:

* passlib's last release was 2020-10. It is unmaintained.
* It does `import crypt` at module scope. `crypt` was **removed in Python 3.13**.
  The image runs 3.12.8 today; the next base-image bump breaks authentication
  outright rather than noisily. This is the real defect, and it is a time bomb,
  not a papercut.
* One trapped traceback per process start, in the auth path, forever.

**Compatibility proven in both directions, not assumed.** A passlib-produced
hash verifies under the new code; a new hash verifies under passlib. All four
live users' stored hashes are `$2b$` (queried by prefix; no hash printed). Cost
factor 12 unchanged, per §16.1.

Two behaviours preserved deliberately:

* **>72 bytes.** bcrypt ignores everything past 72; passlib truncated
  identically. Measured both — a 100-char password hashes under each and
  verifies against its own 72-byte prefix. The schemas permit 128 characters, so
  this path is reachable, and it does not move.
* **NULL bytes.** passlib raised `PasswordValueError`; bare `bcrypt` accepts
  them, which would silently shorten a password at the C-string boundary. The
  guard is kept explicitly.

One behaviour changed deliberately, and stated rather than slipped in:
`verify_password` returns `False` on a missing or malformed stored hash instead
of raising `UnknownHashError`/`ValueError`. That exception surfaced at the one
caller, `auth_service.authenticate_user:69`, as a 500 on a login attempt. It now
fails closed and logs a warning — visible, not swallowed.

**The fix holds in the image.** It is a source-plus-requirements change, so it
lands on the next build. No build performed; none permitted by this order.

### 3.2 pytest-timeout, and the rest of the dev toolchain

`pytest-timeout==2.3.1` installed at its declared pin. `--timeout` is accepted
and the `@pytest.mark.timeout` markers in `tests_system/e2e` are live for the
first time since WP-32 declared them. **Closes WP-32's P2.46 (first booking — see §7.2).**

Pillow 12.2.0, numpy 2.2.1, onnxruntime 1.20.1 all present, as WP-44 left them.
Verified by import, not by `pip list` alone.

Still missing from `.venv`, all declared in `requirements-dev.txt`:
`pytest-celery`, `pytest-mock`, `pytest-cov`, `factory-boy`, `freezegun`. And
`pytest-asyncio` remains drifted — 0.24.0 installed, 0.25.2 declared. **Not
installed by this package**, deliberately: the order named `pytest-timeout` and
nothing else, `requirements-dev.txt`'s own header records that the operator
installs deliberately, and bumping pytest-asyncio mid-package would have moved
the baseline I was measuring. Decision D-2, §9.

---

## 4. Task 2 — tests_system points at the wrong host

`tests_system/service_urls.py` is new and is the single place this tree learns
where the services are. Ten sites routed through it:

| Site | Was |
|---|---|
| `integration/test_dlq_integration.py:14` | `http://localhost:8001/api/v1` |
| `integration/test_projects_integration.py:17` | `http://localhost:8001/api/v1` |
| `integration/test_pipeline_integration.py:17` | `http://localhost:8001/api/v1` |
| `integration/test_auth_integration.py:34` | `http://localhost:8001/api/v1` |
| `integration/test_gpu_integration.py:15` | `http://localhost:8002` |
| `e2e/test_project_lifecycle.py:20` | `os.getenv("E2E_BASE_URL", "http://localhost:8001/api/v1")` |
| `e2e/test_localization.py:17` | same |
| `conftest.py:48` | `REDIS_URL` → `redis://localhost:6379/15` |
| `conftest.py:49` | `SEAWEEDFS_MASTER_URL` → `http://localhost:9333` |
| `conftest.py:50` | `SEAWEEDFS_FILER_URL` → `http://localhost:8888` |

Convention: `IVGS_TEST_HOST` (default `192.168.1.90`), with per-service
overrides `IVGS_TEST_API_URL`, `IVGS_TEST_SCHEDULER_URL`, `IVGS_TEST_REDIS_URL`,
`IVGS_TEST_SEAWEEDFS_MASTER_URL`, `IVGS_TEST_SEAWEEDFS_FILER_URL`. `E2E_BASE_URL`
is honoured as an alias for the API URL, so existing invocations and runbooks
keep working.

**The e2e modules were the pattern to follow in shape only.** `os.getenv` with a
default is right; the default was wrong in exactly the same way as the eight
literals. They now share the convention rather than being the exception to it.

**Ports preserved, not collapsed.** 8001 is `ivgs-fastapi`; 8002 is
`ivgs-scheduler`, whose container listens on 8001 internally and is published on
8002. Pointing one at the other would have made four scheduler tests fail
against the API and looked like progress.

### 4.1 Run against the live stack

Every module now reaches its service. The evidence is in the response codes:
422, 429, 404, 200 — not connection-refused. That is the deliverable. What the
responses *say* is a different problem, and it is ledgered, not patched here, as
instructed.

`tests_system`: **30 passed, 16 failed, 15 skipped, 30 errors**, in 1.5 seconds.
Full per-test breakdown in the baseline §6. The two dominant findings:

* **P2.57 — the whole integration and e2e set authenticates with `email`.**
  `LoginRequest` (`ivgs-api/app/schemas/auth.py:12`) takes `username`, and the
  `users` table has **no `email` column at all** — checked against the live
  schema, the columns are `id, username, password_hash, role, created_at,
  last_login_at, is_active`. Every `admin_headers` fixture 422s. After five
  attempts the API's own 5/min login rate limit turns the remainder into
  `429 RATE_LIMITED`, which is why the error text changes partway down the run:
  one defect, two faces. `test_unauthenticated_register_rejected` additionally
  targets `POST /auth/register`, which returns **404** — that route does not
  exist; `auth.py` registers `/login`, `/logout`, `/refresh` and one GET, and
  user creation is `POST /users` (`users.py:54`).
* **P2.58 — three live contract mismatches.** `GET /fleet` on the scheduler
  returns an object (`{'alive_nodes': 3, 'available_vram_mb': 293661, ...}`)
  where the tests expect a list of node rows. `POST /schedule` 422s on the body
  the tests send. Unauthenticated `POST /projects` returns **403** where the
  test expects **401** — FastAPI's `HTTPBearer` default, and §16 of the spec
  says 401, so one of the two is wrong and it is worth someone deciding which.

---

## 5. Task 3 — P2.45, `test_stage3.py`

Rewritten. **7 tests → 8, all green.** The three causes WP-44 S8.4 diagnosed
were all real and all in the test file; the rewrite also had to dodge two traps
that would have produced tests passing for the wrong reason.

Causes, as diagnosed and confirmed:

1. Three patch targets named `tasks.stage3_images._update_scene_asset`. That
   attribute has never existed; `patch` raises `AttributeError` at setup.
2. One named `tasks.stage3_images.CogVideoXClient`. The module imports
   `CogVideoXGenerationParams` and `CogVideoXModel` from that client, not the
   class; the class now arrives via `build_provider`.
3. Four calls passed `flux_client=` / `cogvideox_client=`. The current signature
   is `_process_single_scene(scene, task_input, vllm_client, prompt_binding,
   image_validator, config, *, project_id, tier)`, and it resolves the
   image/video provider per scene through `get_binding` → `build_provider`
   (ARCH-1 scene scope).

The two traps, both worth recording because either would have produced a green
suite that proved nothing:

* **Non-UUID ids.** `project_id` and `scene_id` are fed to `UUID()` inside the
  function, and the old fixtures used `"proj-001"` / `"scene-001"`. Those raise
  `ValueError` — and `_process_single_scene` catches every exception and returns
  `status="failed"`. `test_flux_failure_returns_error` asserts exactly that, so
  it would have gone green on the wrong failure. Every id is a real UUID now,
  and that test pins the message (`"Timed out"`) and the `finally`-path provider
  close, not just the status.
* **The dead `image_validator` parameter.** The function accepts it and then
  ignores it: step 4 constructs its own `ImageValidator(clip_api_url=...,
  clip_auth_token=...)` because it needs to pass the CLIP URL and the service
  token. Mocking the argument validates nothing. These tests patch the class.
  The dead parameter is a real defect in the code under test — ledgered, not
  fixed here.

Two tests added, both earning their place rather than padding the count:

* `test_video_keyframe_failure_falls_back_to_flux` — the branch where an empty
  keyframe falls back to a still image and lazily resolves the IMAGE binding. A
  video-only project depends on it. Nothing covered it.
* `test_deduplication_skips_upload`, renamed from `..._skips_generation` —
  WP-45 moved the hash check to AFTER generation deliberately, because it hashes
  bytes that now exist. What dedup saves is the upload and the duplicate row,
  not the GPU time. The old name asserted a behaviour the code does not have and
  was never going to have.

`test_wp44_quality_gate.py::TestStage3CarriesTheRecord` kept, not duplicated.
Those six read `stage3_images.py` as **source** and pin the shape of the WP-44
seam — one helper at all three construction sites, submission not re-gated on
`enable_clip_scoring` — which no behavioural test can see. Its docstring
asserted that `test_stage3.py` was red; that sentence has been updated in the
same commit rather than left to rot.

---

## 6. Task 4 — the compliance-scanner group

Diagnosed as a group before anything was touched, as instructed. **Three root
causes** behind 19 failures. Two were stale test code and are fixed; one is a
real defect in the code under test and is ledgered.

1. **`"python"` is not on PATH.** node-01 has `python3` only.
   `subprocess.run(["python", ...])` raised `FileNotFoundError` before the
   scanner ran, in all 19. Now `sys.executable`, which also guarantees the
   interpreter under test is the one running the tests.
2. **`/ivgs/scripts/compliance_scanner.py`** is the path the repo is mounted at
   *inside* the containers. On the host it is `/opt/ivgs`; `/ivgs` holds only
   `rollback_points`. The path is now derived from `__file__`.
3. **The scanner does not implement §F.2 Rule 2.** `match_glob` handles only
   `*`-prefixed globs and exact filenames, so `"requirements*.txt"` matches no
   file, and **prohibited pip packages have never been scanned for.** Measured
   directly against the scanner: `openai==1.0.0`, `anthropic==0.5.0`,
   `elevenlabs==0.2.0` and `did-client==1.0.0` in a `requirements.txt` all score
   `rc=0` — clean. The CI compliance gate has a hole in it. **Ledger P2.49.**

**Causes 1 and 2 had to go together, and this is the part worth reading.**
Fixing only the interpreter would have been *worse than leaving the group
broken*: a missing script exits 2, and 18 of these 19 tests assert only
`returncode != 0`. They would all have turned green while testing nothing at
all, and the group would have been marked done. That is precisely why the order
said diagnose before fixing, and it is why the pip-package cases are the only
ones that stay red.

Blast radius of the eventual glob fix, measured so whoever takes P2.49 does not
have to: no tracked `requirements*.txt` carries a prohibited package, so
repairing `match_glob` does **not** turn the repo red.

19 failed → **15 passed, 4 honestly red.**

---

## 7. Task 5 — the honest baseline

**`dev/workpackages/reference/TEST-BASELINE_2026-08-25.md`.** Per tree: the
command that runs it, the environment it needs, pass/fail/skip/error counts, and
one line per remaining failure with a file:line cause and a ledger id or a
stated reason it is expected. 59 failures and 45 errors, **zero unexplained**.

### 7.1 Two trees outside Tasks 1–4, and why I touched them

Neither was named in the order. Both were included because Task 5 makes an
unexplained failure a package failure, and **an opaque setup error cannot be
explained** — 36 tests were collected and never ran, so what they would have
said was unknown. Both changes are environment, not assertions; no test was
weakened, skipped or deleted.

* **`ivgs-scheduler/tests/conftest.py` (new).** Three modules do
  `from test_scheduler import FakeRedis` inside a fixture. That resolved under
  pytest's default `prepend` mode; WP-32.1 switched the repo to
  `--import-mode=importlib` to stop `ivgs-api/tests` and `tests_system` both
  claiming the name `tests`, and importlib mode does not touch `sys.path`.
  pyproject's `pythonpath` lists each suite's root, not its `tests` directory.
  Same remedy `ivgs-workers/tests/conftest.py` already applies, scoped the same
  way. **9 passed / 2 failed / 32 errors → 22 passed / 21 failed.**
* **`ivgs-backup-worker/pytest.ini` (new).** `from tasks.backup_tasks import ...`
  resolved to `ivgs-workers/tasks/`. Both services ship a top-level `tasks`
  package; pyproject lists `ivgs-workers` and does not list
  `ivgs-backup-worker` at all. A `PYTHONPATH=` prefix does not help — pytest
  inserts its own entries ahead of the inherited environment. Its own inifile
  gives it its own import namespace. **4 errors → 4 passed.** The root run is
  unaffected, and this was checked rather than assumed: `pytest
  ivgs-api/tests/test_health.py` still reports `configfile: pyproject.toml`.

This is where the trade needs stating plainly. The scheduler now shows 21
failures where it showed 2. **That is the package working, not failing.** Nineteen
of those were always there, hidden behind one import error; thirteen tests that
had never executed now pass. A count that looks better while 32 tests do not run
is the exact dishonesty this package exists to remove.

### 7.2 A bookkeeping defect found on the way in

**The P2 ledger id space is double-booked.** `P2.46` is used for two different
things: WP-32-TEST-GATES:219 assigned it to *"pytest-timeout is not installed"*,
and WP-45-API:1016 assigned it to *"the scheduler's queue depth is not the
queue"*. `P2.47` and `P2.48` are likewise claimed only in report text.
`OUTSTANDING_WORK.md` — the stated SSOT — carries a heading for `P2.45` and for
none of the others, which is how the collision went unnoticed: ids are being
minted in reports and never registered.

This package allocates from **P2.49** upward and does not attempt to renumber
anyone else's entries. Someone should reconcile the register; I have not, because
it would rewrite two other packages' reports. **Decision D-3, §9.**

Closed by this package: WP-32's **P2.46** (pytest-timeout, §3.2), WP-32's
**P2.47** (`tests_system` assumes loopback, §4), and **P2.45** (`test_stage3.py`,
§5).

---

## 8. Ledger — new entries

**P2.49 — the compliance scanner has never enforced §F.2 Rule 2.**
`scripts/compliance_scanner.py`'s `match_glob` handles only `*`-prefixed globs
and exact filenames, so `"requirements*.txt"` matches no file and prohibited pip
packages are never scanned for. Measured: all four prohibited packages score
`rc=0`. Repair: make `match_glob` use `fnmatch`. Blast radius measured — no
tracked requirements file carries a prohibited package, so the repo stays green.
4 tests red until fixed.

**P2.50 — `fallback_chain` cannot reach the DLQ, in production.**
`ivgs-workers/services/fallback_chain.py:459` does
`from ivgs_workers.services.dlq_service import FailureCategory`. **No
`ivgs_workers` package exists anywhere** — the directory is `ivgs-workers`
(hyphen), which is not an importable module name. The import sits *after* the
per-level `try/except` loop and is not itself guarded, so when the L1–L4 chain is
exhausted the hand-off to the DLQ raises `ModuleNotFoundError` **before** the
message is sent. **Confirmed inside the deployed image**
(`ivgs-workers:v5.11.0-apibatch`), not just in the tree. Repair is one line —
`from services.dlq_service import FailureCategory` — but it needs a build, which
this order forbids, so it is reported rather than done. This belongs in the
swallowed-failures register's neighbourhood: the effect is that an exhausted
fallback chain never reaches the queue that exists to record it.

**P2.51 — flat per-service top-level module names collide in one pytest process.**
Four instances, one shape. `main`: `ivgs-scheduler`'s production code imports it
at nine sites (`admission_control.py:230,252,265,292,318,348`,
`scheduler.py:210,260`, `gpu_registry.py:208`) to dodge a circular import, and
`pyproject.toml` puts `ivgs-api` first on `pythonpath`, so it binds to the API's
`main.py` — 7 tests red. `ivgs-api/tests/test_ws_job_status.py:22` genuinely
needs `main` to be the API's, so path order cannot satisfy both. `tasks`:
`ivgs-backup-worker` vs `ivgs-workers` — mitigated by a per-service inifile, not
resolved. `test_scheduler`: `ivgs-workers/tests/test_quality_gate.py:43` imports
a helper out of the *scheduler's* suite — 15 errors, and it should not be doing
that at all. `tests`: already fixed by WP-32.1. Real repair is package-qualified
imports (`ivgs_scheduler.main`), or per-service pytest invocations. The
scheduler's is the urgent one, because it is production code, not test code.

**P2.52 — the scheduler's Redis double has fallen behind the real thing.**
`FakeRedis`/`FakePipeline` in `ivgs-scheduler/tests/test_scheduler.py` lack
`zremrangebyscore` and `zcount`, and `FakePipeline.hset` models only the
`mapping=` form. The production circuit breaker and load balancer moved to
sliding-window sorted sets; the fake did not follow. 14 tests red. Repair: three
methods and one signature.

**P2.53 — three worker test fixtures build an async session factory that cannot
be entered.** `mock_db_session_factory` is `AsyncMock(return_value=session)`, so
`factory()` returns a **coroutine**. Production does
`async with self._db_session_factory() as session:`, and a real
`async_sessionmaker` is a *synchronous* callable returning an async context
manager. `TypeError: 'coroutine' object does not support the asynchronous
context manager protocol`. 14 tests red across `test_dlq_service.py` (10),
`test_orphan_cleanup.py` (2), `test_retry_engine.py` (2). Repair: `MagicMock`,
three times.

**P2.54 — Stage 2's storyboard model lost its validation, and Stage 3 pays for
it.** `ivgs-workers/models/task_result.py:240` declares `media_type: str =
"image"` — a bare string, no enum coercion, no normalisation. An LLM that writes
`"video"` gets `"video"`, and `stage3_images.py:372` branches on
`scene.media_type == MediaType.VIDEO_CLIP.value`, so that scene **silently takes
the image path**. Same model, line 241: `duration_seconds: float = 10.0` with no
lower bound, so `-1` is accepted. 2 tests red, and the first has pipeline
consequences beyond the test.

**P2.55 — `_extract_json_from_response` prefers the wrong bracket.**
`ivgs-workers/tasks/stage2_storyboard.py:348` searches for `[` before `{`, so an
LLM response with a preamble around `{"scenes": [...]}` returns the inner
**array** and the object wrapper is discarded. The direct-parse and code-fence
paths are correct, which is exactly why one of the three extraction tests fails
and two pass. Repair: try `{` first, or prefer the outermost match.

**P2.56 — Stage 6 accepts a render with no audio.**
`ivgs-workers/tasks/talking_head_task.py:126` — `scene_audio_refs` has no
`min_length=1`, so `Stage6Input(scene_audio_refs=[])` constructs happily. 1 test
red.

**P2.57 — `tests_system` authenticates against an API that no longer exists.**
Every integration and e2e fixture POSTs `{"email": ...}` to `/auth/login`;
`LoginRequest` takes `username`, and the `users` table has no `email` column.
`test_unauthenticated_register_rejected` targets `POST /auth/register`, which
404s — user creation is `POST /users`. The API's 5/min login rate limit converts
the tail of each run into 429s, which disguises one defect as two. 30 errors +
7 failures. Repair: `username`, the real admin credential from a secret, the
right route, and a session-scoped token so five logins do not become forty.

**P2.58 — three live contract mismatches surfaced by Task 2.** `GET /fleet`
returns an object where the tests expect a list of nodes (2 red). `POST /schedule`
422s on the body the tests send (2 red). Unauthenticated `POST /projects`
returns 403 where the test expects 401 (1 red) — FastAPI's `HTTPBearer` default
versus §16 of the spec; **someone needs to rule which is correct**, because
right now the API and its own specification disagree.

**P2.59 — stale-test residue, five small items.** (a) `test_stage1.py` and
`test_stage2.py` full-task fixtures pass non-UUID project ids into code that
does `UUID()` — 2 red, same class as the ids WP-52 corrected in `test_stage3.py`.
(b) `quality_validator.py:299` stores `round(elapsed, 3)`, so a sub-millisecond
caption validation records `0.0` and `assert validation_duration_s > 0` fails —
1 red; repair on the *code* side with more precision, not by relaxing the
assertion. (c) `_process_single_scene` accepts an `image_validator` argument and
ignores it. (d) `tests_system/conftest.py`'s `db_session` fixture still builds a
`sqlite+aiosqlite` engine, contradicting its own header comment; nothing uses it.
(e) `tests_system/spec_compliance/test_no_hardcoded_ips.py:18` excludes
`tests/spec_compliance/...` — a path that no longer exists, so the exclusion is
dead (harmless only because the guard assembles its pattern from fragments).

---

## 9. Decisions needed

**D-1 — the scheduler and backup-worker fixes were not in the order.** §7.1.
They convert 36 never-run tests into 26 passes and 21 diagnosed failures, and
the scheduler's visible failure count rises from 2 to 21 as a result. If you
would rather the baseline recorded the original opaque errors, revert commit
`8fa9970`; the baseline would then carry two rows reading "32 tests collected,
never run, cause unknown", which I do not think is what this package is for.

**D-2 — five declared dev dependencies are still missing** and `pytest-asyncio`
is drifted 0.24.0 vs 0.25.2 declared. §3.2. The order named `pytest-timeout`
only, and installing the rest mid-package would have moved the baseline being
measured. Say the word and it is one command — but it should be its own
measurement, not a footnote to this one.

**D-3 — the P2 ledger id space is double-booked** (§7.2) and ids are being
minted in reports without ever reaching `OUTSTANDING_WORK.md`. I allocated from
P2.49 and renumbered nobody. Reconciling it means editing two other packages'
reports, which is your call, not mine.

**D-4 — P2.50 needs a build.** `fallback_chain.py`'s DLQ hand-off is broken in
the deployed image. One-line fix, forbidden here. It should not wait long: it
means an exhausted fallback chain never reaches the DLQ.

**D-5 — 401 vs 403 on unauthenticated writes** (P2.58). The API returns 403,
§16 says 401, and a test asserts 401. One of the three has to move.

---

## 10. Verification — what was observed, and what was not

Observed live, with output:

* `ivgs-api` 833 passed / 0 failed, twice-measured (before: 2 failed / 831).
* `ivgs-backup-worker` 4 passed, from a tree that had never executed.
* bcrypt round-trip compatibility in both directions, and `$2b$` on all four
  live users' stored hashes.
* passlib+bcrypt behaviour inside the **running** `ivgs-fastapi` container.
* `ivgs_workers` unimportable inside the **running** `ivgs-celery-default`
  container — P2.50 confirmed in the deployed image, not inferred from the tree.
* The compliance scanner scoring `rc=0` on all four prohibited pip packages.
* `test_health.py` passing alone and failing in-suite, then bisected to the two
  collection-time importers.
* `tests_system` reaching every service (422/429/404/200, not ECONNREFUSED).
* The root pytest config unaffected by `ivgs-backup-worker/pytest.ini`.

**Not observed, and not claimed:**

* The image behaviour of the bcrypt change. It is a source change; the running
  container still has passlib installed. It holds on the next build. No build
  was run.
* Anything about GPU nodes 02–06. No node was visited. The 15 `smoke` skips are
  reported as skips, not interpreted.
* Whether the `tests_system` integration suite would pass with correct
  credentials. It cannot be known without them, and the failures are recorded as
  contract defects (P2.57) rather than guessed at.

### 10.1 Environment notes

* `.venv` gained exactly one package: `pytest-timeout==2.3.1`.
* One run was budget-capped, not timeout-killed. No run was killed.
* Nothing was written to the live `ivgs` database. Checked, not assumed: zero
  rows added to `projects`, and the only three recent `render_jobs` rows predate
  this session by two hours (15:18–15:39 UTC; the runs began at 17:36). The e2e
  modules stop at the login and never dispatch a pipeline.

---

## 11. Commits — HELD, not pushed

```
8fa9970  fix(wp-52): two suites that could not import their own service
8ca1437  fix(wp-52): the compliance-scanner tests can now find the scanner
83c0ee2  fix(wp-52): test_stage3 rewritten against the signature that exists
1fd34d1  fix(wp-52): tests_system learns its host in one place
7273687  fix(wp-52): the health patch never reached the health route
b3fa986  fix(wp-52): passlib retired, bcrypt called directly
```

plus the documentation commit carrying this report and the baseline.

### Push block — count-gated

Run on **node-01**. It refuses unless exactly **7** WP-52 commits are ahead of
`origin/main`, so a stale or partial tree cannot be pushed by accident.

```bash
# node-01
cd /opt/ivgs && git fetch origin && \
AHEAD=$(git rev-list --count origin/main..HEAD) && \
WP52=$(git log --oneline origin/main..HEAD | grep -c 'wp-52') && \
echo "ahead=$AHEAD wp52=$WP52" && \
if [ "$AHEAD" -eq 7 ] && [ "$WP52" -eq 7 ]; then \
  git log --oneline origin/main..HEAD && \
  git push origin main && echo "PUSHED"; \
else \
  echo "REFUSING: expected 7 commits ahead, all WP-52; got ahead=$AHEAD wp52=$WP52"; \
fi
```

Nothing has been pushed. `dev/workpackages/WP-45-gpu-registry-backup-20260825-170853.txt`
is WP-45's untracked artefact and was deliberately left alone.
