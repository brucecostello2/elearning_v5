# WP-57-SURFACES — four dashboards that state things that are not true, and four carried decisions

**Date:** 2026-08-26 · **Node:** node-01 (192.168.1.90) · **Version set:** `v5.17.0-surfaces`

---

## 0. Headline

| Task | Outcome |
|---|---|
| **1** — Gallery thumbnails | **DONE.** No project could ever show one: `hero_image_asset_id` is NULL on all 17 and nothing sets it — and the URL it built points at a token-guarded route an `<img src>` cannot reach (403, measured). The "5:00" duration was the operator's **configured ceiling**, not a length. |
| **2** — Storage Analytics contradicts itself | **DONE.** Not missing data — a **case mismatch**. The page keyed tiers on `"HOT"`; the API sends `"hot"`. The `StorageTier` type had been widened to contain both, which is what let it compile. Dedup (P2.4) is now **derived**: 171 MB saved. |
| **3** — Migrations tab | **DONE.** Phantom family instance 14: 4 of 6 fields never on the wire. Deleted, not null-guarded. And the harder question is answered: **nothing has ever migrated a tier**, cause identified. |
| **4** — two node counts | **DONE.** Both were true and neither was labelled. Three distinct numbers now stated as what they are: **6 machines / 5 GPU / 3 scheduler workers**. node-05's stale P2.6a text corrected. |
| **5** — the sweep | **DONE, and it found more than the screenshots.** A second broken migrations table, and an admin form that **PUT fields the API ignores**. |
| **6** — PITR | **ESTABLISHED: it does not exist.** Backups are logical; no `pg_basebackup` anywhere. `restore.sh --pit` now refuses with a reason. **And the nightly DB backup had been failing for two days — found, diagnosed and fixed live.** |
| **7** — classifier | **DONE.** Default classifications **15 → 6** of 20 real messages, and the 3 "successes" were false positives. |
| **8** — `IVGS_SERVICE_TOKEN` | **DONE.** Consumers mapped, guard added, tests pin it, single operator block ready. **No value appears anywhere in this report.** |

**Test position: zero new failures, +17 tests.**

| Tree | Before | After |
|---|---|---|
| `ivgs-api` | 875 / 0 / 0 / 0 | **880** / 0 / 0 / 0 |
| `ivgs-workers` | 787 / 18 / 48 / 15 | **799** / 18 / 48 / 15 |
| `ivgs-scheduler` | 22 / 21 / 0 / 0 | unchanged |
| `ivgs-backup-worker` | 4 / 0 / 0 / 0 | unchanged |
| `tests_system` | 56 / 12 / 15 / 30 | unchanged |

---

## 1. Task 1 — the gallery could never have shown a thumbnail

Three defects stacked, and the top one hid the two beneath it.

1. **Nothing populates the source.** `hero_image_asset_id` is NULL on **all 17
   projects**; no code path in the system sets it. `hero_image_url` was therefore
   always null and every card fell to the placeholder icon.
2. **Even populated, it could not render.** `project_service.py:580` built
   `/api/v1/assets/{id}/download` — behind `Depends(get_service_or_user)`. A
   browser will not attach a Bearer header to an `<img src>`. Measured:
   that route answers **403** unauthenticated. WP-40 built `apiClient.blob()`
   for exactly this and the card did not use it.
3. **One icon meant three different things** — no asset, failed to load, still
   loading — so a broken thumbnail and an empty project were indistinguishable,
   which is what the task asked to separate.

**Fixed:** the API now derives `thumbnail_asset_id` per project (final render
first, else newest generated image; `talking_head` deliberately excluded — a
presenter plate is a picture of the *actor*, so every project sharing one would
show the same card). The card fetches it via `useAssetObjectUrl(..., 320)` — the
WP-45 Task 6(b) thumbnail route, so cards stop pulling full-size originals — and
renders three distinct states in words.

### 1.1 The duration was a configured ceiling, not a measurement

**It was not hardcoded, and it was not measured.** The badge rendered
`max_runtime_seconds` — what the operator typed at project creation. Both
populated cards read "5:00" because both carry the default **300**.

The API already sends the honest number. Measured on the deployed build:

| Project | badge showed | actually available |
|---|---|---|
| New multiplication pass | 5:00 | `total_duration_estimate_seconds` = **95.0** |
| double digit multiplication | 5:00 | **190.0** |

The badge now reads `est 1:35` / `est 3:10`, labelled **est** so an estimate
cannot pass for a measurement, and `no estimate` where there is no storyboard.

---

## 2. Task 2 — the page contradicted itself over one letter

The tier breakdown was not empty. **The lookup never matched.**

```
STORAGE_TIERS ids : "HOT"  "WARM"  "COLD"  "ARCHIVE"     (frontend)
API sends         : "hot"                                 (PostgreSQL ENUM)
tierData.find(t => t.tier === tier.id)  ->  "hot" === "HOT"  ->  false
```

Every donut fell to 0% / "no assets" / 0 B, directly beneath a populated total
computed without keying by tier. Live data says **100% hot, 159 assets**.

**Why the type system did not catch it.** `StorageTier` was declared as the union
of *both* cases — `"hot" | … | "HOT" | …`. The uppercase half existed only to
make the mismatch compile. **A type widened to accommodate a bug stops being able
to catch it** — the same disease as WP-56's phantom `PaginatedResponse<T>`.
Narrowing it to the real ENUM (`hot | warm | cold | archived | deleted`) produced
19 compile errors that named every remaining defect, including one on a page
nobody had screenshotted.

Note `"archived"`, not `"archive"`: the ENUM's actual value, verified against
`pg_enum`. Lowercasing alone would still have missed that tier.

### 2.1 Deduplication — P2.4 CLOSED, with a real number

P2.4 said the figure was derivable and nothing derived it. WP-45 restored
`content_hash`, and both needed columns are populated on all 159 assets, so the
honest answer stopped being "unknown". Now derived:

```
bytes_saved = SUM(file_size_bytes * (reference_count - 1))
```

That is what dedup **actually avoided storing** — `AssetService.upload_asset`
increments the reference instead of writing the bytes again — not an estimate of
what compression might achieve. Live on the deployed build:

```
dedup_savings: {'bytes_saved': 171091620, 'duplicate_count': 9, 'percent': 22.99}
```

A zero here is now a measurement ("dedup ran and saved nothing"), which is the
only reason it may be shown at all.

### 2.2 The two totals never disagreed

Operational Monitoring's "0.3 GB" and Storage Analytics' "347.0 MB" read the
**same `total_size_bytes` from the same endpoint**. The monitoring tile hardcoded
GB to one decimal, so 347 MB rendered as "0.3 GB". One fact, two units, and the
coarse rounding made it look like a contradiction. Both now use the shared
formatter and always agree. (Also `totalUsed ? … : "—"` was falsy for a genuine
0; an empty store is a measurement, not a missing one.)

---

## 3. Task 3 — phantom family, instance 14

Captured from the live wire, not from what the table wanted:

| Column rendered | Frontend read | API actually sends |
|---|---|---|
| ASSET ✓ | `asset_id` | `asset_id` |
| PROJECT — blank | `project_name` | **nothing** |
| CURRENT TIER ✓ | `current_tier` | `current_tier` |
| TARGET TIER — blank | `target_tier` | `next_tier` |
| SIZE — `NaN undefined` | `size_bytes` | `file_size_bytes` |
| SCHEDULED — `Invalid Date` | `scheduled_at` | `days_until_migration` |

Phantoms **deleted**, not null-guarded — the WP-40/43 fix. `m.size_bytes` is now
a compile error.

**"NaN undefined" was one formatter.** The page defined its own
`formatBytes(bytes: number)` doing `Math.log(undefined)` → `NaN` → `units[NaN]`
→ `undefined`. It was *typed* to reject undefined — but the phantom field
asserted a `number` the wire never sent, so **the type system lied on its
behalf**. `src/lib/media.ts` has had a safe `formatBytes(number | null | undefined)`
since WP-40; the page now uses it. **One more unsafe copy survives** in
`app/admin/backups/page.tsx:49` and is recorded below rather than swept in.

`scheduled_at` has **no replacement**: the API sends days, not a timestamp, and
0 means the window has passed — rendered **"overdue"**, not "today", because
"today" would imply something is about to happen.

### 3.1 The harder question: is a migration scheduler running?

**No. Nothing has ever migrated a tier, in nearly three months.**

```
storage_tier | count | ever_transitioned | oldest
hot          |   158 |                 0 | 2026-06-01
```

I first concluded the task was unregistered, from a `python -c` import that does
not autodiscover. **That was wrong** — querying the live worker shows it
registered under both names, and beat has dispatched it daily at 04:00 all along.

The real cause is in `services/retention_migration.py`. Its scan does:

```sql
SELECT id, asset_type, storage_path, storage_tier, ... FROM assets WHERE ...
```

`assets` has **`seaweedfs_path`**. There is no `storage_path` — verified:
`ERROR: column "storage_path" does not exist`. The query raises `UndefinedColumn`
on every tier, every night; a per-tier `try/except` swallows it, and the task
reports a migration that scanned nothing and moved nothing. **Seventh instance of
the inert-mechanism pattern, and a swallow-register entry.**

A second defect sits immediately behind it: `TIER_ORDER` uses
`StorageTier.ARCHIVE = 'archive'` while the ENUM value is **`archived`**, so the
archive hop would fail the moment the first is repaired.

**Not repaired here, deliberately.** Fixing the column name starts moving 158
live assets between tiers at the next 04:00 — changing live data, which this
package forbids. It is **D-1**. The surface now says so instead of implying a
mechanism that acts, and the API's `days_until <= 7` filter means every asset
older than 23 days is listed as "upcoming" forever.

---

## 4. Task 4 — three true numbers, none of them labelled

The two surfaces read **different sources**, which is why they disagreed:

| Surface | Source | Counts | Was labelled |
|---|---|---|---|
| Operational Monitoring | scheduler fleet (`useGPUFleetStatus`) | GPU workers registered with the scheduler = **3** | "GPU Nodes Online" |
| Node Monitor | `GET /api/v1/nodes` | machines in the topology = **6** | "6 nodes" |

Ground truth, and all three are different: **6 machines, 5 with a GPU, 3 in the
scheduler fleet.** node-01 is CPU-only; node-05 has a GPU and is out of service;
node-06 has an RTX 5080 and runs the CLIP scorer but **no Celery worker**, which
is exactly why the scheduler's count is 3 and not 4.

**Relabelled, not recomputed** — a number that split the difference would be true
of nothing. Operational Monitoring now says **"Scheduler GPU workers"** with a
tooltip naming what is excluded and why; Node Monitor says **"6 machines in the
fleet — including node-01 (CPU-only)"**. The API gained `has_gpu` and
`runs_pipeline_worker` so a surface *can* state what it counts. Verified live:
`gpu nodes: 5 | scheduler workers: 3 | machines: 6`.

### 4.1 node-05's stale explanation — corrected

The card said telemetry was absent because of **P2.6a**
(`utkuozdemir/nvidia_gpu_exporter:1.2.1` panicking at startup). WP-48 closed
P2.6a and node-05 served telemetry through the repaired exporter on 2026-08-25.
node-05 is silent because **its host has a confirmed memory fault**.

The reason is now derived from what is true of the node — no GPU / offline /
reachable-but-not-scraped — rather than one hardcoded sentence blaming a fixed
bug. Verified on the deployed build:

```
node-05: "no GPU telemetry: the node is offline, so nothing is reporting.
          Check why the node is down before looking at the exporter."
```

---

## 5. Task 5 — the sweep, and what it caught that the screenshots did not

Method: enumerate every dashboard surface, extract its object-field reads, and
compare against live payloads captured with a real token.

| Surface | Field | Sent? | Rendered as | Action |
|---|---|---|---|---|
| Gallery card | `hero_image_url` | yes, always **null** | placeholder icon | replaced by `thumbnail_asset_id` |
| Gallery card | `max_runtime_seconds` | yes | "5:00" **as a duration** | now `total_duration_estimate_seconds`, labelled est |
| Storage / Migrations | `project_name` | **NO** | blank | column removed |
| Storage / Migrations | `target_tier` | **NO** (`next_tier`) | blank | renamed to wire |
| Storage / Migrations | `size_bytes` | **NO** (`file_size_bytes`) | `NaN undefined` | renamed + safe formatter |
| Storage / Migrations | `scheduled_at` | **NO** (`days_until_migration`) | `Invalid Date` | days, "overdue" |
| Storage / tiers | `tier` | yes, lowercase | 0% on all four | case fixed, type narrowed |
| Storage / dedup | `dedup_savings` | **was NO** | honest "not computed" | now derived |
| **Admin Retention / migrations** | same four | **NO** | same four defects | **found by sweep**, fixed |
| **Admin Retention / policies** | `source_tier`, `target_tier`, `threshold_days`, `auto_execute`, `last_run_at`, `assets_affected` | **NO — all six** | undefined in every column | **found by sweep**, rebuilt |
| Monitoring | `totalUsed` | yes | "0.3 GB" vs "347.0 MB" | shared formatter |
| Node Monitor | `has_gpu`, `runs_pipeline_worker` | **were NO** | counts unlabelled | added to API |

### 5.1 The worst thing the sweep found: a form that saved nothing

`app/admin/retention/page.tsx` PUT `{threshold_days, auto_execute}` to
`/api/v1/retention/policies/{id}`, whose `RetentionPolicyUpdate`
(`schemas/retention.py:52`) declares **neither**. FastAPI drops undeclared fields
silently, so **the form returned 200 having saved nothing** — a green surface over
an empty action, on an **admin settings form**, which is the AD-09.3 family in the
place it can do most harm.

A retention policy on this API is a set of **per-tier durations**
(`hot_days`/`warm_days`/`cold_days`/`archive_days`/`delete_after_days`), not a
threshold with an on/off switch. The table and editor were rebuilt on the real
contract, `null` renders as "not set" rather than 0 days, and the modal carries a
banner: saving updates the record, it does not move any asset (§3.1).

### 5.2 Left, with reasons

* `app/admin/backups/page.tsx:49` — a second unsafe local `formatBytes`. Not
  reached by any phantom field today, so it produces no visible defect. Ledger it;
  sweeping every local copy is its own change.
* The four remaining `tests_system` failures/errors and the scheduler's 21 are
  pre-existing baseline rows (P2.51/52/57/58), untouched.

---

## 6. Task 6 — point-in-time recovery does not exist

Established by reading **and** measurement:

| Question | Answer |
|---|---|
| (a) What does `backup.sh` take? | `pg_dump --format=plain` (`backup.sh:310`) — a **logical** dump. `pg_basebackup` appears **nowhere** in the repository. |
| (b) What does the WAL archive hold? | **99 segments, 740 MB**, and it is live — `pg_stat_archiver.last_archived_time` was minutes old when checked. |
| (c) Is PITR possible today? | **No.** |

Not a configuration gap. WAL records **physical block changes** keyed to LSNs in
one data directory; `pg_dump` emits SQL, and restoring it builds a new cluster
with different layout and an unrelated LSN timeline. There is no base to roll
forward from, so `recovery_target_time` has nothing to seek within.

**WP-58's 7-vs-30 inconsistency is therefore moot**: the WAL window governs
nothing, because no window of WAL is replayable.
`BACKUP_RETENTION_WAL_DAYS` is currently a cost control on 740 MB, not a recovery
parameter.

**`restore.sh --pit` now refuses** (exit 5) naming the reason. It previously wrote
a `recovery.conf` to `/tmp` and told the operator to copy it into PGDATA and
restart — instructions which, if followed during an incident, put the cluster
into recovery hunting a base backup that does not exist. That is worse than
refusing: it burns the operator's time when they have least of it.

`docs/runbooks/point-in-time-recovery.md` is new and states the promise:
**recovery is checkpoint-only.**

### 6.1 The nightly database backup had been FAILING for two days — fixed live

Found while measuring (b). `backup_records` showed `full_database` **failed** on
2026-08-24 and 2026-08-25, exit 6:

```
"NAS backup directory not available: /mnt/backup/ivgs/db"
```

**Cause:** `ivgs-backup-worker`'s `/proc/mounts` showed `/mnt/backup` as local
**ext4** — not the NFS export. The container was started across the NFS mount, so
it saw the **local directory shadowed underneath the mountpoint**:

```
host      /mnt/backup/ivgs/assets : 2026-08-14 … 2026-08-25   (11, on the NAS, 56 GB)
container /mnt/backup/ivgs/assets : 2026-07-12 … 2026-07-25   (8, local disk, 45 GB)
```

So the most recent restorable dump was **2026-08-23**, and **45 GB of orphaned
July snapshots** sit on the root volume where no prune can reach them. This is the
same class `backup-failed.md` already records for postgres' WAL handle after a
remount — and it is the 75-day-gap shape: a mechanism reporting health it did not
have.

**Fixed:** `docker compose up -d --force-recreate --no-deps backup-worker`. The
routine recreate did **not** do it — compose saw no config change and left the
container alone, which is worth knowing. Verified after:

```
192.168.1.7:/mnt/store/ivgs /mnt/backup/ivgs nfs4 ...
/mnt/backup/ivgs/ -> PROTECTED-2026-05-31 _keys assets config db images wal
pre-flight target /mnt/backup/ivgs/db: PRESENT (exit 6 cause cleared)
```

The durable fix is `rshared` mount propagation so a later NFS mount reaches
running containers — a host-level change, **D-3**. The 45 GB of orphans is **D-4**.

**No restore was run and no physical base backup was introduced**, deliberately:
shipping an unrehearsed second recovery mechanism would create a second thing
nobody has proven — the same failure, one layer up. That is **D-2**.

---

## 7. Task 7 — the classifier, measured before and after

| | before | after |
|---|---|---|
| classified by a pattern | 3 | **14** |
| fell through to the DEFAULT | **15** | **6** |
| distribution | transient 17, external 3 | transient 9, external 1, config 10 |

**The 3 "successes" were false positives.** `generation\s+failed` matched
"Stage **storyboard_generation** failed" through the underscore, so every
storyboard failure was classified `external` — "the model produced bad output" —
on no evidence. A confident wrong class is worse than an honest default: it sends
the reader to the model instead of to the stage. A lookbehind now excludes a
preceding word character, while "All animation generations failed" still matches.

**Why the old set matched so little:** it was written for *exception* strings, and
what reaches this classifier is the orchestrator's own summary text, by which time
the exception is gone. Different vocabularies.

New patterns, each written against a message that is actually in the table:
`429` / `rate limit` and `worker crash` / `stranded` → **transient**;
`validation` / `no media branch` and `cancelled by` / `dispatched no celery task`
→ **config** (the nine WP-45 sweep rows are administrative cancellations of jobs
that never ran — calling them transient invites retrying nothing).

The remaining **6 defaults are content-free summaries** — "Stage prototype_draft
failed" — which carry no information. `test_a_content_free_summary_still_defaults`
pins that deliberately, so nobody improves the number by inventing a pattern that
guesses.

**The exception-object half is ledgered, not attempted.** It needs the exception
at the failure site, which lives in the frozen stage bodies; it lands at **M3.3**
when the Temporal wrappers own that site.

---

## 8. Task 8 — `IVGS_SERVICE_TOKEN`

**No token value appears in this report, in the chat, or in any commit.**

### 8.1 Consumers and files

| Consumer | Where | Effect |
|---|---|---|
| Definition / default | `shared/config.py:42` | `"dev-service-token"` — published in the repository |
| API acceptance | `app/core/auth.py:159` (`get_service_or_user`) | a match resolves to the `svc-pipeline` account |
| API rate-limit exemption | `app/middleware/rate_limit.py:145` | service traffic bypasses per-user limits |
| Worker | `ivgs-workers/config.py:187` | sent as `Authorization: Bearer` by `manifest_builder`, `quality_reporting`, `pipeline_orchestrator`, `error_handler` |
| Guarded routes | incl. CLIP scoring (`require_service_or_privileged_user`) | the quality gate depends on it |

Files that must carry it: `ivgs-infra/.env` (node-01) **and**
`ivgs-infra/.env.nodeNN` on **nodes 02, 03 and 04** — those workers call the API,
so yes, they need it.

### 8.2 The guard

`auth.py` now refuses the shipped default **once a real token is configured** —
the route must not accept both, or setting a strong value protects nothing.

It deliberately does **not** fail closed while the default is still in place:
that would stop the live fleet the moment this deploys, before the operator has
run the block. Until then, every acceptance logs
`service_token_is_the_shipped_default` so the gap is visible rather than quiet.
`test_the_default_still_works_while_no_real_token_is_set` pins that concession
and says in its docstring that it should be **deleted** once the rotation is
complete.

### 8.3 Operator block — single paste, safe to abort

Run on **node-01**. It generates the value, distributes it, and restarts only
what reads it. Nothing echoes the token.

```bash
# ── node-01 ────────────────────────────────────────────────────────────────
set -u
cd /opt/ivgs || exit 1

# 1. Generate ONCE. Never printed.
TOK="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
[ -n "$TOK" ] || { echo "generation failed"; exit 1; }

# 2. node-01 .env — replace or append, idempotent.
sudo cp ivgs-infra/.env "ivgs-infra/.env.bak-wp57-$(date +%Y%m%d-%H%M%S)"
if grep -q '^IVGS_SERVICE_TOKEN=' ivgs-infra/.env; then
  sudo sed -i "s|^IVGS_SERVICE_TOKEN=.*|IVGS_SERVICE_TOKEN=${TOK}|" ivgs-infra/.env
else
  echo "IVGS_SERVICE_TOKEN=${TOK}" | sudo tee -a ivgs-infra/.env >/dev/null
fi
grep -q '^IVGS_SERVICE_TOKEN=.\+' ivgs-infra/.env && echo "node-01 .env: set" || { echo "ABORT: .env not written"; exit 1; }

# 3. Same into .env.node01 (the backup worker and API read it via env_file).
if [ -f ivgs-infra/.env.node01 ]; then
  sudo cp ivgs-infra/.env.node01 "ivgs-infra/.env.node01.bak-wp57-$(date +%Y%m%d-%H%M%S)"
  if grep -q '^IVGS_SERVICE_TOKEN=' ivgs-infra/.env.node01; then
    sudo sed -i "s|^IVGS_SERVICE_TOKEN=.*|IVGS_SERVICE_TOKEN=${TOK}|" ivgs-infra/.env.node01
  else
    echo "IVGS_SERVICE_TOKEN=${TOK}" | sudo tee -a ivgs-infra/.env.node01 >/dev/null
  fi
  echo "node-01 .env.node01: set"
fi

# 4. Stage it for the GPU nodes on the shared mount, root-only, so the paste
#    blocks below need no retyping and the value never crosses a terminal.
sudo install -d -m 0700 /mnt/ivgs-shared/secrets
printf 'IVGS_SERVICE_TOKEN=%s\n' "$TOK" | sudo tee /mnt/ivgs-shared/secrets/service-token.env >/dev/null
sudo chmod 0600 /mnt/ivgs-shared/secrets/service-token.env
echo "staged for nodes 02/03/04"

# 5. Seed the account the token resolves to (idempotent).
sudo docker compose -f ivgs-infra/docker-compose.node01.yml \
  -f ivgs-infra/docker-compose.override.node01.yml \
  -f ivgs-infra/docker-compose.monitoring.yml --env-file ivgs-infra/.env \
  exec -T fastapi-backend python -m app.scripts.seed_service_account || \
  echo "NOTE: seed step reported non-zero; check svc-pipeline exists before step 6"

# 6. Restart exactly what reads it.
sudo docker compose -f ivgs-infra/docker-compose.node01.yml \
  -f ivgs-infra/docker-compose.override.node01.yml \
  -f ivgs-infra/docker-compose.monitoring.yml --env-file ivgs-infra/.env \
  up -d --no-deps --force-recreate \
  fastapi-backend celery-worker-default celery-worker-composition celery-beat backup-worker

unset TOK
echo "node-01 done. Verify: docker exec ivgs-fastapi env | grep -c '^IVGS_SERVICE_TOKEN='   # expect 1"
echo "Then run the node-02/03/04 blocks below, then DELETE /mnt/ivgs-shared/secrets/service-token.env"
```

**node-02** (192.168.1.91) and **node-04** (192.168.1.93) — identical but for the
compose file; node-04's `celery-worker` has `depends_on: comfyui`, so `--no-deps`
is load-bearing:

```bash
# ── node-0N (N = 2 or 4) ───────────────────────────────────────────────────
set -u
N=2   # <<< set to 2 or 4
cd /opt/ivgs/ivgs-infra || exit 1
sudo cp ".env.node0${N}" ".env.node0${N}.bak-wp57-$(date +%Y%m%d-%H%M%S)" 2>/dev/null
TOKLINE="$(sudo cat /mnt/ivgs-shared/secrets/service-token.env)"
[ -n "$TOKLINE" ] || { echo "ABORT: staged token not readable"; exit 1; }
if grep -q '^IVGS_SERVICE_TOKEN=' ".env.node0${N}" 2>/dev/null; then
  sudo sed -i "s|^IVGS_SERVICE_TOKEN=.*|${TOKLINE}|" ".env.node0${N}"
else
  echo "$TOKLINE" | sudo tee -a ".env.node0${N}" >/dev/null
fi
unset TOKLINE
sudo docker compose -f "docker-compose.node0${N}.yml" --env-file .env \
  up -d --no-deps --force-recreate celery-worker
docker exec "ivgs-celery-worker-node0${N}" env | grep -c '^IVGS_SERVICE_TOKEN=' # expect 1
```

**node-03** (192.168.1.92) — **the service is `cogvideox-worker`, NOT
`celery-worker`.** node-03 also declares a `celery-worker` under
`profiles: ["standby"]` which is not running; naming it starts a second worker
competing for the same queues and leaves the real one stale (WP-44 §6.3):

```bash
# ── node-03 ────────────────────────────────────────────────────────────────
set -u
cd /opt/ivgs/ivgs-infra || exit 1
sudo cp .env.node03 ".env.node03.bak-wp57-$(date +%Y%m%d-%H%M%S)" 2>/dev/null
TOKLINE="$(sudo cat /mnt/ivgs-shared/secrets/service-token.env)"
[ -n "$TOKLINE" ] || { echo "ABORT: staged token not readable"; exit 1; }
if grep -q '^IVGS_SERVICE_TOKEN=' .env.node03 2>/dev/null; then
  sudo sed -i "s|^IVGS_SERVICE_TOKEN=.*|${TOKLINE}|" .env.node03
else
  echo "$TOKLINE" | sudo tee -a .env.node03 >/dev/null
fi
unset TOKLINE
sudo docker compose -f docker-compose.node03.yml --env-file .env \
  up -d --no-deps --force-recreate cogvideox-worker
docker exec ivgs-cogvideox-worker-node03 env | grep -c '^IVGS_SERVICE_TOKEN=' # expect 1
```

**Finally, on node-01:** `sudo shred -u /mnt/ivgs-shared/secrets/service-token.env`

**Safe to abort:** every step gates on the previous one, `.env` files are backed
up before modification, and stopping between nodes leaves those nodes on the old
default — which still works until *every* node is switched. There is no window in
which the fleet is half-broken, because the API accepts the default until a real
value reaches it.

Nodes 05 and 06 are excluded: node-05 is out of service, node-06 is
operator-managed and runs no Celery worker.

---

## 9. Deployment — node-01 only

| Container | Image | Status |
|---|---|---|
| `ivgs-fastapi` | `ivgs-api:v5.17.0-surfaces` | healthy |
| `ivgs-celery-default` / `-composition` / `-beat` | `ivgs-workers:v5.17.0-surfaces` | healthy |
| `ivgs-nextjs` | `ivgs-frontend:v5.17.0-surfaces` | healthy |
| `ivgs-backup-worker` | `v5.1.0-stream-b` (unchanged image) | **force-recreated** to repair its mount (§6.1) |

Artifacts banked through `scripts/save-image-artifact.sh`; the WP-58 conformance
gate passes: `OK: 42 artifacts conforming, 2 allowlisted`.

Nodes 02/03/04 need `v5.17.0-surfaces` for the Task 7 classifier; those paste
blocks follow the same shape as §8.3's (artifact →
`sha256sum -c` → `docker load` → tag bump → recreate, `cogvideox-worker` on
node-03).

Verified on the deployed build:

```
thumbnail_asset_id: one project has one, one honestly has none
durations         : est 95.0 / 190.0  (badge used to read 5:00 for both)
dedup_savings     : 171,091,620 bytes, 9 avoided copies, 22.99%
node counts       : 5 GPU | 3 scheduler workers | 6 machines
node-05 telemetry : "the node is offline" — no longer blames P2.6a
```

---

## 10. Test evidence

```
ivgs-api           880 passed                                    (was 875)
ivgs-workers       799 passed, 18 failed, 48 skipped, 15 errors  (was 787)
ivgs-scheduler      22 passed, 21 failed                         (unchanged)
ivgs-backup-worker   4 passed                                    (unchanged)
tests_system        56 passed, 12 failed, 15 skipped, 30 errors  (unchanged)
```

**One regression was introduced and caught by the suite**, not by inspection: the
dedup aggregate returns `decimal.Decimal`, and `100.0 * int / Decimal` raises
`TypeError`. Four tests in `test_service_retention_extended.py` failed; the fix
is an `int()` coercion with a comment saying why it is load-bearing. The clean
re-run is the 880 above.

No assertion weakened, no skip marker added, no coverage deleted.

---

## 11. Decisions needed

**D-1 — the tier migration has never run (§3.1).** One wrong column name,
swallowed nightly for three months. Repairing it starts moving 158 live assets at
the next 04:00, and the `archive`/`archived` ENUM mismatch bites immediately
after. Fix both and let it run, or disable the schedule and say tiering is not in
service — but not the present state, where a dashboard implies a mechanism that
acts.

**D-2 — physical base backup, or accept checkpoint-only (§6).** Introduce
`pg_basebackup` so the 740 MB of archived WAL becomes replayable, or stop
archiving WAL. What must not continue is an archive faithfully maintained,
pruned on a schedule, and impossible to restore from.

**D-3 — mount propagation for `/mnt/backup` (§6.1).** The recreate fixed today's
symptom. Without `rshared`, the next NFS remount silently detaches every running
container again — and the failure is invisible until a backup needs the path.

**D-4 — 45 GB of orphaned July snapshots** on node-01's root volume, shadowed
under the NFS mountpoint. No prune can see them (the host sees the NFS, the
container saw the local tree). Reclaiming needs a deliberate unmount-and-clean.

**D-5 — restore rehearsal.** Never performed. The checkpoint-only promise in the
new runbook is inferred from code and configuration, not demonstrated. This is an
operator decision to schedule; the package forbids taking it here.

---

## 12. Push block — COMMITTED AND HELD, NOT PUSHED

| # | Commit | Subject |
|---|---|---|
| 1 | `c2c500a` | `fix(wp-57): four dashboards stop asserting what they do not know` |
| 2 | `1bd44b2` | `fix(wp-57): PITR does not exist - restore.sh says so, and the nightly DB backup is repaired` |
| 3 | `6fac8db` | `fix(wp-57): classifier patterns for real messages, and the service token stops accepting its own default` |
| 4 | *(this commit — `git log --oneline -4`)* | `docs(wp-57): report, and the baseline moved to 880/799` |

**Count gate — must print `GATE PASS`:**

```bash
cd /opt/ivgs
PGPW=$(grep '^POSTGRES_PASSWORD=' ivgs-infra/.env | cut -d= -f2-)
PGUSER=$(grep '^POSTGRES_USER=' ivgs-infra/.env | cut -d= -f2-)
export TEST_DATABASE_URL="postgresql+asyncpg://${PGUSER}:${PGPW}@192.168.1.90:5432/ivgs_reconciliation_test"
export BACKUP_TEST_DSN="postgresql://${PGUSER}:${PGPW}@192.168.1.90:5432/ivgs_reconciliation_test"
unset PGPW PGUSER

API=$(.venv/bin/python -m pytest ivgs-api/tests -q 2>&1 | tail -1)
WRK=$(.venv/bin/python -m pytest ivgs-workers/tests -q 2>&1 | tail -1)
SCH=$(.venv/bin/python -m pytest ivgs-scheduler/tests -q 2>&1 | tail -1)
BUP=$(.venv/bin/python -m pytest ivgs-backup-worker/tests -q 2>&1 | tail -1)
SYS=$(.venv/bin/python -m pytest --timeout=120 tests_system -q 2>&1 | tail -1)
printf 'api : %s\nwrk : %s\nsch : %s\nbup : %s\nsys : %s\n' "$API" "$WRK" "$SCH" "$BUP" "$SYS"

ok=1
echo "$API" | grep -q '880 passed'                          || ok=0
echo "$WRK" | grep -q '18 failed, 799 passed, 48 skipped'   || ok=0
echo "$SCH" | grep -q '21 failed, 22 passed'                || ok=0
echo "$BUP" | grep -q '4 passed'                            || ok=0
echo "$SYS" | grep -q '12 failed, 56 passed, 15 skipped'    || ok=0
( cd ivgs-frontend && npx tsc --noEmit -p tsconfig.json )   || ok=0
python3 scripts/compliance_scanner.py /opt/ivgs >/dev/null 2>&1 || ok=0
scripts/check-image-artifacts.sh >/dev/null 2>&1            || ok=0
if [ "$ok" -eq 1 ]; then echo "GATE PASS"; else echo "GATE FAIL - DO NOT PUSH"; fi
```

If it fails on `api`, check `SELECT count(*) FROM users` in
`ivgs_reconciliation_test` first — a timeout-killed run leaves it dirty and the
next run errors on its first test (baseline §2).

**Push, only after `GATE PASS` and only on the operator's word:**

```bash
git log --oneline -4 && git push origin main
```
