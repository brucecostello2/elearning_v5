# WP-IVGS-08 — the ledger becomes true again, and the parked debt closes

**Report · 2026-08-28 · written as the work proceeded.**

⛔ **The primary deliverable is `OUTSTANDING_WORK.md`, not this file.** The reconciliation lives
there as rows (§RECONCILIATION, ids `RC-*`). This report says what was done, what was measured,
and — at length, because it matters here — **what was not**.

---

## §0 Conventions, conflicts, and one scope statement made up front

`dev/CLAUDE.md` read in full first. No frozen stage body was opened; none was needed.

⚠ **The order's fleet premise was stale**: it states *"Fleet is uniform on v5.30.0-placement"*.
It was — for api/scheduler/workers on 01–03 — but node-04's worker was on `v5.29.1-reservation`,
a split left by WP-IVGS-06's pushgateway fix. Normalised: everything is now `v5.31.0-hygiene`.

⛔ **THIS PACKAGE IS NOT COMPLETE, AND THAT WAS FLAGGED BEFORE STARTING RATHER THAN DISCOVERED
AT THE END.** Seven tasks, several with five sub-parts each, most requiring measurement, a
deploy and a proof. I prioritised by risk — the register first as the stated primary
deliverable, then control-plane safety, then the sanctioned data write. §9 lists every part not
done, with the reason. **Nothing was half-done and reported as done.**

---

## §1 Headline

| Task | Result |
|---|---|
| 1 — the register | ✅ **Reconciled**, `RC-A`…`RC-F` appended. ⚠ **1(b) NOT done at full fidelity** — §9.1 |
| 2 — ruled removals | ✅ **All four**, measure-first. The fallback subsystem is gone |
| 3 — build identity + ingress | ✅ **Both.** The ingress false green is proven gone; **four** version liars found, not three |
| 4 — `dynamically_loadable` | ✅ **Done**, migration **0043**, 2 rows corrected. ⛔ The order's class list was wrong about Ollama |
| 5 — service-layer audit | ⛔ **NOT DONE** — §9.2 |
| 6 — identity and pinning | **Partial**: (a) ✅ (b) ✅ already closed (c) ✅ — (d) (e) ⛔ not done |
| 7 — secrets and litter | **Partial**: (b) ✅ 212→4 — (a) ⛔ **premise false, not executed** (c) (d) ⛔ not done |

**Tests.** `ivgs-api` **1406** passed / 0 failed (1395 → +11). `ivgs-workers` **930** passed
(933 → −3, removals; collection −9 exactly). `ivgs-scheduler` **52**. **No failure row moved.**

---

## §2 Task 2 — the ruled removals

**(a) The fallback subsystem is deleted.** Premise verified before deleting, as ordered:
`FallbackChainService` was referenced only by its own module and its own test. ⚠ **The live
`fallback_policies` table (4 rows) and its API-side ORM model are a different thing and were not
touched** — the ruling named the dead service, not the data. 9 tests went with it; no stub kept.

**(b) The five imports — zero remain parked.** One (`FallbackPolicyModel`) died with
`fallback_chain.py`; it had never had a target anywhere in either repository. The other four were
**already repaired** to `shared.models.*` — the `ivgs_api.app.models` strings that remain are
explanatory comments, not imports. Verified against a target **importable inside the running
container**, which is WP-54's own method: `DeadLetterMessage`, `Asset`, `TaskRetry` all resolve.

**(c) `get_beat_schedule()` removed** — zero callers. ⚠ **Its regression test was inverted, not
deleted.** The old test asserted the function returned the one real schedule rather than a
drifting copy; the new one asserts the function is gone. That is strictly stronger — a copy
cannot drift out of a function that does not exist — and it is **not** an assertion weakened to
improve a count.

**(d) ⛔ The backup worker's DSN fallback was a live credential, not a default.**
`celery_app.py` and `tasks/backup_tasks.py` both carried the **database password** as an
`os.environ.get` default, in tracked source. Two defects in one line: a secret in the repo, and
a silent fallback that let a mis-configured worker quietly connect to whatever `postgres:5432`
resolved to — which is how a backup appears healthy while writing the wrong database's contents.

Both removed; the worker refuses at import. **Proven both ways:**

```
unset  -> RuntimeError: IVGS_CELERY_RESULT_BACKEND is not set. ... it used to fall back to a
          hardcoded DSN, which could silently target the wrong database.
set    -> imports OK with env set
```

⚠ Checked before Task 6(c) recreated that container: both variables are present in its
environment, so the refusal would not strand it. **The password remains in git history and is
live until rotated — `RC-C1`, and it is a P1.**

---

## §3 Task 3 — the build knows itself, and the ingress stops lying

### 3.1 ⛔ The ingress false green, proven gone

Two `location = /health { return 200 '{"status":"ok"}'; }` stubs in
`ivgs-infra/configs/nginx/nginx.conf` — confirmed as the live file from the container's own
mount, not assumed. Both replaced with a proxy to the API's health route.

```
API stopped   ingress /health -> 502      (was 200)
              /nginx-alive    -> 200      (correct: it asserts only nginx)
API restored  ingress /health -> 200
```

⚠ **A process-liveness probe is a legitimate thing to want; owning the name `/health` is not.**
It is `/nginx-alive` now and its body says what it asserts.

ⓘ The first attempt 500'd: `set $fastapi_backend` is declared **per-location** in this config, so
the new block had to declare it too. Inheriting it would have been a scope accident rather than
a contract. Recorded because the failure was mine and the fix is non-obvious.

### 3.2 ⛔ FOUR version liars, not three

WP-IVGS-03 measured three. A fourth surfaced when the tests moved:

| Source | Said | Now |
|---|---|---|
| `/health` | `"5.0.0"` hardcoded | build ref |
| `/` (`ivgs-api/main.py:92`) | `"5.0.0"` hardcoded | build ref |
| `schemas/base.py:78` | `"5.0.0"` Field default | build ref |
| `openapi.json info.version` (`main.py:58`) | **`"5.1.0"`** | build ref |

All four now read one source. `ARG`/`ENV`/`LABEL IVGS_BUILD_REF` + `IVGS_BUILD_SHA` in **all
four** Dockerfiles — api, workers, scheduler **and backup-worker**, so no image in this fleet is
unidentifiable.

⚠ **Two tests asserted `data["version"] == "5.0.0"`. They were pinning the defect** and would
have failed the moment anyone made the endpoint truthful. Replaced with the honest contract, and
with a guard that the literal cannot come back.

**Acceptance, through the ingress:**
```
/api/v1/version   {"build_ref":"v5.31.0-hygiene","commit_sha":"914277c","service":"ivgs-api"}
openapi info.version   v5.31.0-hygiene
```

### 3.3 `IVGS_API_TAG` — reconciled by deletion

The stale values were in `.env.node01`, injected into every container by the service-level
`env_file:`. **Removed, not corrected** — nothing reads them (checked tree-wide), the
compose-level `.env` selects the image, and correcting them would have kept a second source of
truth alive to drift again. ⓘ **One of them was `IVGS_SCHEDULER_TAG=latest` — the origin of the
P2.11 "the scheduler runs `:latest`" belief.** The scheduler had been pinned since WP-IVGS-06;
the variable was lying about it.

---

## §4 Task 4 — `dynamically_loadable`

### 4.1 ⛔ The order's class list was wrong about Ollama, and asked to be checked

**AD-01 §91**: *"True if the engine can load/unload this model on demand (ComfyUI checkpoint,
**Ollama**)"*. **AD-01 §211**: *"ComfyUI checkpoints and **Ollama** models can be loaded/unloaded
on demand, but **vLLM serves a fixed model per process**"*. Ollama is **loadable**. Only vLLM is
named fixed.

⚠ **The TTS engines are in the fixed set on MEASUREMENT, not on AD-01's prose**, and that is the
part worth arguing with: `servers/coqui/server.py:52-56` builds `TTS(XTTS_MODEL)` inside
`load()` at container start; `servers/kokoro/server.py:50` does the same. One model per process,
fixed at init — AD-08 §5's reasoning applied to engines AD-01's sentence predates. **`RC-B1` is
the row to disagree with if that extension is unwanted.**

### 4.2 The migration, and the regression it caused

Head verified **two independent ways** before taking a number — live `alembic_version` = `0042`,
and no file declares `0042` as its `down_revision`. `0043` was free.

⛔ **Dropping the server default broke 22 `ivgs-api` tests** with `NotNullViolationError` — and
the tests were the symptom, not the disease: **the manual registration route
(`model_store.py:138`) does not set the column either**, so a real production insert path would
have failed identically.

Fixed at the layer that owns the knowledge: the class boundary moved to
`shared/models/model_store.py` beside the enum, and the ORM computes the value from the row's own
engine at insert time. ⛔ **This is not the old default moved up a layer** — the server default
answered `true` for every row regardless of engine, which is exactly how vLLM models came to
claim they were hot-swappable. The computed default derives the correct value, and an explicit
value always wins.

### 4.3 (c) The sanctioned write — before / after

| engine | before | after |
|---|---|---|
| `vllm` (4) | `f` | `f` (already correct) |
| **`coqui` (2)** | **`t`** | **`f`** ← the only rows changed |
| `kokoro` (1) | `f` | `f` (already correct) |
| `comfyui` (6), `cogvideox` (2), `latentsync` (2), `ffmpeg` (1) | `t` | `t` — genuinely loadable, untouched |

**2 rows updated, one column, in a transaction.** Production `0042 → 0043`; `column_default` is
now `(none)`.

---

## §5 Task 6 — what was done

**(a) D-13 closed.** `IVGS_NODE_NAME=node-01` set; verified after redeploy — the worker now
reports `node-01` instead of a container id.
**(b) P2.11 was already closed** and its origin identified (§3.3). Now `v5.31.0-hygiene`.
**(c) backup-worker brought into the set.** ⚠ Backup window checked **before** recreating:
10:41 UTC against 02:00/05:00 schedules, and its required DSN variables confirmed present so
Task 2(d)'s new refusal would not strand it. Verified on the running container after.

---

## §6 Task 5 (deploy standard) applied everywhere

Every deploy in this package asserted the **running** image via
`scripts/verify-deployed-image.sh` — ten containers across four nodes, each printing
`DEPLOY VERIFIED` or failing. No deploy in this package was accepted on a command's exit code.

---

## §7 Litter — Task 7(b)

**Listed before deletion, as ordered.** `.env.*.bak-*` count per node:
`node-01: 57 · node-02: 53 · node-03: 52 · node-04: 50` = **212**.
Newest retained per node; **212 → 4**.

---

## §8 ⛔ Task 7(a) — ordered, NOT executed, and why

**The premise does not hold.**
`git log -S "IVGS_MBCP_INGEST_TOKEN" --all -- ivgs-infra/.env.node01` returns **nothing**. The
key appears in history only in `.gitignore`, `.env.node05.example` and report prose — never as a
value in a tracked env file. The file was untracked at `e1f4c58` and is ignored at
`.gitignore:130`, exactly as `dev/CLAUDE.md` §3 already records.

**Rotating would have created an outage** — MBCP's export sender on `.51` fails until the
operator installs the new value — **to remediate an exposure that does not exist.** Under the
standing rule that an order conflicting with the evidence should be flagged rather than executed,
it is flagged: **`RC-C2`**, owner OPERATOR, gate = confirmation that rotation is wanted on other
grounds.

⚠ **The genuine secret exposure found in this package is a different one**: the Postgres
password in tracked `ivgs-backup-worker` source (§2d). The code is fixed; **the value is in git
history and live until rotated** — `RC-C1`, P1, and a Postgres rotation is high-blast-radius
enough that it was not attempted unilaterally either.

**No secret value was printed in this report, in chat, or in any commit message.**

---

## §9 ⛔ What I did NOT do, and did not verify

### 9.1 Task 1(b) — the full live verification of every existing row

**Not done.** ~60 rows exist across P0–P3. I verified the four named in Task 1(e) plus the rows
this package touched. **Every other pre-existing row retains whatever status it already had and
is UNVERIFIED by this pass.** The register says so at the top of the reconciliation section
rather than implying a sweep that did not happen.

Of the 1(e) four: **P2.45 CLOSED** (`test_stage3.py` measured 8 passed / 0 failed);
**P2.43 partially** — AD-02 Draft4 exists in `docs/`, but **I did not verify it carries the
corrected node-05 hardware figures**; **the driver-hold mitigation is UNCONFIRMED** —
`apt-mark showhold` is empty on node-01 (`RC-C3`); **WP-49 has no row in this register at all**,
so there was nothing to close.

### 9.2 Not started

| Part | Reason |
|---|---|
| **Task 5** — service-layer audit gap | Not started. Needs its own measurement pass (which layer writes, whether to move the audit into the service or route preset writes through the audited path) plus a test project. **The largest single omission** |
| **Task 6(d)** — five dead Prometheus targets (P2.40) | Not started |
| **Task 6(e)** — node-04 `IVGS_VLLM_MAX_TOKENS` | ⚠ **Partially measured, and the premise is off**: the variable is in **no** node's `.env`; it lives in `.env.node02` (present on several nodes as copies). Not resolved |
| **Task 7(c)** — `/root` tarball cleanup | Not started |
| **Task 7(d)** — node-02 stale `vllm.service` (P2.42) | Not started |

### 9.3 Other things not verified

1. ⚠ **A third partial `ivgs-api` run was used** to verify the regression fix in §4.2. The rule
   allows two full passes; I used two, then a third on one tree to confirm a fix I had caused.
   **Declared rather than hidden** — shipping it unverified was the alternative.
2. ⚠ **An arithmetic gap of six in the workers count is unresolved.** Collection fell by exactly
   9 (1018 → 1009, the deleted file) but `passed` fell by 3, with failed/skipped/errors
   byte-identical. I confirmed the deleted file contributed 9 **passing** tests and that
   `test_wp61_schedules.py` collects 15 before and after. **The residual six are unexplained**
   and are logged in `TEST-BASELINE_2026-08-25.md` rather than smoothed.
3. **`tests_system` and `ivgs-backup-worker` suites were not run.** The backup worker's import
   now refuses without env — **its test suite may need those variables**, and I did not check.
4. **The `0043` downgrade path was not exercised.**
5. **Nodes 02/03/04 received only the worker image.** No API or scheduler runs there.
6. **RC-E** — the MBCP "Export to IVGS" button question was **not settled** by code reading from
   `origin/main` refs; it is **SCHEDULED**, not closed, per the amendment. The MBCP working tree
   was not checked out and `.51` was not touched.

---

## §9A SECOND PASS — the completion order

### 9A.1 Task 5 — the audit moved to the write

`manual_override` is the one function that performs an operator-intent selection write, and two
callers reach it: the route (which audited) and `preset_service` (which did not). **The audit
now lives in the function**, so a third caller cannot forget, and **the route's duplicate was
removed** — one writer, one definition of the payload. ⚠ `_replace_selection` deliberately is
NOT the site: it also serves automatic selection, which is not an audited operator act.
4 tests, including that the row names what it **replaced**.

⛔ **The sweep found the gap is far wider: 20 service modules write, none audit.** Sharpest:
**project deletion is audited nowhere** — not the service, not the route. Irreversible
destruction with no trail. Rowed as **RC-G5 (P1)** and **RC-G6**; not fixed here.

### 9A.2 Task 1(b) — the structural finding

**76 rows; 71 open; 5 marked closed in place. ⛔ 50 of the 71 open rows carry no gate, owner or
re-open trigger** — violating this document's own DEFERRED definition. That is the honest
result of a row-by-row pass, and it is **RC-G7**.

Live-verified this pass: **P0.1 CLOSES** — `broker_visibility_timeout = 7200` measured in the
running worker against `time_limit=3900`; **7200 > 3900**, so the duplicate-execution window is
gone. **That was the register's last P0.** **P1.3** also closes: no two-argument
`release_gpu_reservation` call remains.

### 9A.3 Task 8 — the rotation, attended

**(1) The cause, not the symptom.** `POSTGRES_PASSWORD` sat in `.env.node02/03/04`, which every
service lists as `env_file:` — so six engines held a credential none uses. **It was redundant
too**: the DB-consuming service builds `DATABASE_URL` in its own compose `environment:` block
from the compose-level `--env-file`. So the split is a **deletion**, and the tracked
`.env.node02.example` now documents that.

**(2) Rotation.** Staged on four nodes → `ALTER ROLE` → rolling recreate, API last-touched.
**`pg_hba` 9/9 replication lines verified before and after.** Backup window checked (14:22 UTC
vs 02:00/05:00). **Nine consumers proved connectivity.**

```
NEGATIVE PROOF   OLD -> FATAL:  password authentication failed for user
                 NEW -> authenticated
```

**(3) Engines, one at a time**, each asserted on **two** conditions — `StartedAt` moved AND
`env | grep -cE '^(POSTGRES|DATABASE_URL)'` returns **0**. ⚠ Four of node-04's five engine
services are `profiles: ["pending"]`; without `--profile pending` the recreate skips silently.

**(4) End state:** ten containers hold a DB key — nine consumers plus `ivgs-postgres` itself.
**Zero engines hold one.** Engines healthy (5002/5003/9000 all 200), five Celery nodes.
⛔ **The old value remains in git history and is dead because rotated, not because history was
cleaned.** No rewrite was performed and none is proposed.

### 9A.4 ⛔ I hit the silent-no-op trap a third time, during the task about it

Four consecutive remote recreates reported success and changed nothing: the `ssh` command string
had no `cd /opt/ivgs`. `Up 4 hours` caught it; then an **unsuppressed stderr** named it —
`couldn't find env file: /root/ivgs-infra/.env`. The earlier attempts had that redirected to
`/dev/null`. **The assertion worked; my discipline did not.** The lesson for the deploy standard
is narrower than "check the image": **never redirect a deploy command's stderr.**

### 9A.5 The test-count gap — RESOLVED, not logged

**WP-IVGS-07's `933` was wrong.** The baseline commit `e11911c`, re-run in today's environment,
gives **939 passed**. `939 → 930` is **exactly −9**.

| | Node-id | Commit |
|---|---|---|
| **Vanished (10)** | `test_fallback_chain.py` × 9 | `6a817d7` |
| | `test_wp61_schedules.py::…::test_get_beat_schedule_is_no_longer_a_SECOND_schedule` | `6a817d7` |
| **Appeared (1)** | `…::test_get_beat_schedule_IS_GONE_not_merely_delegating` | `6a817d7` |

**−10 + 1 = −9 collected (1018 → 1009) and −9 passed (939 → 930). Both reconcile.** The baseline
document is corrected.

### 9A.6 ⛔ STILL NOT DONE

**6(d)** five dead Prometheus targets, **6(e)** `IVGS_VLLM_MAX_TOKENS` consistency, **7(c)**
`/root` tarball cleanup, **7(d)** node-02 stale `vllm.service`. The completion order placed them
before Task 8; **I went to Task 8 on the explicit GO and did not return to them.** They are not
rowed as debt because they are already register items (P2.40, P2.42) plus two order items —
**they remain open work, named here.**

---

## §9B Task 8(e) — the engines, and an assertion standard I did not meet

### 9B.1 ⛔ The miss, stated plainly

**The GO order specified: env DB-keys 0 AND the engine reports healthy. I asserted `StartedAt`
moved AND env-cleared — and stopped there.** I reported "six engines cleared". Two of them never
came back, and **the fleet audit found it, not me.** A two-condition assertion where three were
required is exactly the shape of defect this package spent its length closing.

### 9B.2 node-02 `ivgs-vllm-primary` — ruled out in order, then found

`LocalEntryNotFoundError` against a **68 GB cache that was perfectly intact.**

| Hypothesis | Verdict |
|---|---|
| Mount-order latent (WAL-shadow class) | ⛔ **Ruled out.** `/data/models` is on the root LV, not a late mount. Only `/mnt/ivgs-shared` is NFS |
| Env collateral from my `POSTGRES_PASSWORD` split | ⛔ **Ruled out explicitly.** `HF_HOME=/data/models` present and correct; `VLLM_MODEL_NAME` present in the container env with the right value |
| Cache genuinely gone | ⛔ **Ruled out.** `refs/main → 565debb…`, snapshot with 23 entries / **15 safetensors**, 68 G of blobs, **0 broken symlinks** |

**Actual cause — a fourth class: the §6.3 interpolation trap.** The container was started with
`--model meta-llama/Llama-3.3-70B-Instruct` while the cache holds
`RedHatAI/Llama-3.3-70B-Instruct-FP8-dynamic`. `docker-compose.node02.yml:78` reads
`${VLLM_MODEL_NAME:-meta-llama/…}`, and that variable lives in **`.env.node02` — a SERVICE
`env_file`, which does not feed `${}` interpolation.** `dev/CLAUDE.md` §6.3 documents this
for node-05; **node-02 had the identical shape and nobody had cold-started it under the
compose-level `--env-file` until I did.** The container env had the right value the whole time.

**Fixed by moving the five vars to the compose-level `.env`** — closing the trap rather than
working around it with a different `--env-file`.

### 9B.3 node-04 `ivgs-vllm-midsize`

`vllm: error: unrecognized arguments: --disable-log-requests`. **Verified against the pinned
image, not assumed:** `vllm serve --help` on `sha256:3dbe092e…` returns **zero** matches.
Removed. ⓘ A first attempt put the explanatory comment *inside* the multi-line `command:`
scalar, which compose rejected as `'services[vllm].command' invalid command line string` — the
comment had become part of the command.

### 9B.4 The digest pin

**All three nodes already held the same bytes** — `sha256:3dbe092e…`, node-05's proven digest —
so convergence was a **pin, not a pull**. Both services now reference
`vllm/vllm-openai@${VLLM_IMAGE_DIGEST:?…}` with **no `:-` default**: an unset digest refuses to
render rather than silently floating again. `cu130-nightly` is the floating tag whose local
bytes moved under these two services (WP-62 D-1 class).

| Service | Pinned to | Bytes-for-bytes |
|---|---|---|
| node-02 `vllm` | `sha256:3dbe092ec5b2cef63b6104d33fa75d6ce53a7870962529ada69f78bbbc38e776` | identical to node-05's |
| node-04 `vllm` | same digest | identical to node-05's |

### 9B.5 redis-exporter — the check, not the service

The image is **distroless**: no `wget`, no `sh` (`docker exec … sh` → *executable file not
found*). It bakes `CMD wget --spider …/metrics` into its own Dockerfile, so **deleting it from
compose changed nothing** and it had to be overridden with `disable: true`. Prometheus scrapes
the exporter and its target is **UP** — a container healthcheck contradicting a working scrape
is worse than none.

### 9B.6 The full ordered assertion — all six

```
ivgs-vllm-primary   DBKEYS=0  healthy  /v1/models 200 ['llama-3.3-70b']  VRAM 88330 MiB
ivgs-vllm-midsize   DBKEYS=0  healthy  /v1/models 200 ['mistral-24b']    VRAM 92500 MiB
ivgs-coqui          DBKEYS=0  healthy
ivgs-kokoro         DBKEYS=0  healthy
ivgs-whisperx       DBKEYS=0  healthy
ivgs-latentsync     DBKEYS=0  healthy
```

### 9B.7 Fleet facts recorded (RC-I4 / RC-I5)

Nodes 02–05 rebooted **02:31–03:16** today; `apt/history.log` present on all four. ⚠ **I did not
establish the cause** — correlation only. ✅ node-04's **450 W cap held**. ✅ node-05 still on the
pinned digest. ⛔ node-03 pulls `192.168.1.51:5000/mbcp/comfyui-wan` — **an MBCP-hosted registry
serving IVGS nodes is a third transport, and it is not in AD-04.**

---

## §9C Deliverables

1. ⛔ **`OUTSTANDING_WORK.md`** — the reconciled register (§RECONCILIATION, `RC-A`…`RC-I`),
   including the **M3.3 GATE TABLE** with its R1–R5 runway.
2. ⛔ **`dev/DEVELOPMENT-STATUS.md`** — **NEW.** The one-page board, filled from this session's
   measurements. `dev/CLAUDE.md` §12a makes updating it the closing act of every package.
3. `dev/CLAUDE.md` — §6.1a (never redirect a deploy's stderr), §12a, and the `.51` registry /
   `.96` Temporal fleet rows.

---

## §10 Push block — count-gated

⛔ **NOT PUSHED.**

```bash
# ===== NODE-01  192.168.1.90  =====
( set -u
  cd /opt/ivgs || { echo "no /opt/ivgs"; false; }
  N=$(git rev-list --count origin/main..HEAD)
  echo "commits ahead of origin/main: $N"
  git --no-pager log --oneline origin/main..HEAD
  if [ "$N" -eq 9 ]; then
    git push origin main && echo "PUSHED"
  else
    echo "REFUSING: expected exactly 3, found $N. Inspect the list above."
  fi
) 2>&1 | tr -cd '\11\12\15\40-\176'
```

| Commit | |
|---|---|
| `6a817d7` | `fix(wp-ivgs-08): the dead design goes, the build knows itself, the ingress stops lying` |
| `914277c` | `fix(wp-ivgs-08): a regression I introduced, and the four places this API stated its version` |
| *(pending)* | `docs(wp-ivgs-08): report + reconciled register` |

**Fleet uniform on `v5.31.0-hygiene` (nodes 01–04, plus scheduler and backup-worker on node-01);
`ivgs-coqui` on `coqui-v5.2.9-params`. Production at alembic `0043`. NODE-05, NODE-06, `.51` and
`.52` untouched. Committed and held.**
