# MBCP — Local Dev VM Setup (verified)

**Status:** verified working on `mbcp-node-01` (Ubuntu 24.04.4, x86_64) — `26 passed` including `test_real_weight_bundle_roundtrip`, 2026-06-08.
**Supersedes:** the Slice 2 report **§7** ("VM Setup & Testing Guide") and the older agent chat notes, both of which contain errors (documented in §8 below).
**Purpose:** stand up a Serving + Management dev host that can run the committed test suite (including the real SeaweedFS weight round-trip) in one pass. No GPU required.

This is a **hybrid** setup, by design: PostgreSQL and SeaweedFS run in Docker containers; the MBCP app and the test suite run in a Python venv **on the host**. The integration test runs the FastAPI app *in-process* (httpx ASGI transport) and only needs Postgres + SeaweedFS as live backing services. (The fully-containerised `deploy/*.compose.yaml` manifests are the *deployment* path, not the test path.)

---

## 0. TL;DR (the whole sequence)

```bash
# --- prerequisites (Ubuntu 24.04; run as root or with sudo) ---
apt-get update && apt-get install -y python3.12-venv git   # docker + 3.12 assumed present

# --- infra: Postgres 17 + SeaweedFS 3.80 (both as containers) ---
docker run -d --name mbcp-pg --restart unless-stopped \
  -e POSTGRES_USER=mbcp -e POSTGRES_PASSWORD=mbcp -e POSTGRES_DB=mbcp_test \
  -p 5432:5432 postgres:17

docker run -d --name seaweedfs --network host --restart unless-stopped \
  chrislusf/seaweedfs:3.80@sha256:1055999e08eed1789b0ae45d235126e4495e23d3fb9d6396293fd42539b1ae6a \
  server -ip=127.0.0.1 -dir=/data -master.port=9333 -volume.port=8080 -filer=false

# --- code + venv + deps ---
cd ~ && git clone https://github.com/brucecostello2/MBCP.git && cd MBCP
git checkout feat/slice2-weight-roundtrip          # or main once PR #2 is merged
python3 -m venv .venv && . .venv/bin/activate
pip install -U pip wheel
pip install -e ".[dev]"                            # NOTE the [dev] extra (see §8)

# --- env (point tests at the running containers) ---
export MBCP_TEST_DATABASE_URL="postgresql+asyncpg://mbcp:mbcp@127.0.0.1:5432/mbcp_test"
export MBCP_SEAWEEDFS_MASTER_URL="http://127.0.0.1:9333"

# --- run ---
python -m pytest tests/ -v
```

Expected: **26 passed, 2 warnings** (both benign — see §7).

---

## 1. Target environment & prerequisites

| Item | Verified value | Notes |
|---|---|---|
| OS | Ubuntu 24.04 LTS, x86_64 | ships Python 3.12 — **no deadsnakes PPA needed** |
| Resources | 2 vCPU / 8 GB RAM / ~40 GB disk | sufficient for Serving+Management dev + the test suite; **no GPU** |
| User | root (or a sudo user) | |
| Docker | 29.x + Compose v2/v5 | assumed present; install with `apt-get install -y docker.io docker-compose-v2` if not |
| Python | 3.12.x (system) | |
| Network egress | github.com, pypi.org, docker registry reachable | |

**Required package** (only one is strictly needed beyond Docker/Python/git):

```bash
apt-get update
apt-get install -y python3.12-venv git
```

`libpq-dev`, `build-essential`, `pkg-config` are **not required** — the DB drivers (`psycopg[binary]`, `asyncpg`) ship as binary wheels. Install them only if you later add a dependency that needs compiling.

---

## 2. Infrastructure containers

### 2.1 PostgreSQL 17

```bash
docker run -d --name mbcp-pg --restart unless-stopped \
  -e POSTGRES_USER=mbcp -e POSTGRES_PASSWORD=mbcp -e POSTGRES_DB=mbcp_test \
  -p 5432:5432 postgres:17
```

The official image binds `0.0.0.0` inside the container, so the published port (`-p 5432:5432`) is reachable from the host. Credentials/DB here are `mbcp` / `mbcp` / `mbcp_test`.

### 2.2 SeaweedFS 3.80 — **must use `--network host`**

```bash
docker run -d --name seaweedfs --network host --restart unless-stopped \
  chrislusf/seaweedfs:3.80@sha256:1055999e08eed1789b0ae45d235126e4495e23d3fb9d6396293fd42539b1ae6a \
  server -ip=127.0.0.1 -dir=/data -master.port=9333 -volume.port=8080 -filer=false
```

**Why `--network host` is mandatory here:** SeaweedFS is launched with `-ip=127.0.0.1` (so the master and volume advertise `127.0.0.1` — the address the host test process and the volume-redirect must reach). Under the default bridge network with `-p` publishing, `-ip=127.0.0.1` binds the **container's** loopback, which `docker-proxy` cannot forward to — the host gets connection-refused (`HTTP 000`) even though `docker ps` shows the container "Up". With `--network host`, `127.0.0.1` is the **host's** loopback, so the master (`:9333`), the volume (`:8080`), and the master's gRPC (`:19333`) are all directly reachable from the host. (The digest pin matches CI.)

The data dir `/data` is inside the container (ephemeral). Add `-v mbcp-weights:/data` before the image if you want persistence; not needed for the test.

### 2.3 Verify both services are healthy

The SeaweedFS volume takes **~15–20 s** to register with the master after the container starts (it retries the master gRPC first). Wait, then check:

```bash
sleep 20
docker exec mbcp-pg pg_isready -U mbcp -d mbcp_test          # -> accepting connections
curl -s -o /dev/null -w "sw master -> %{http_code}\n" http://127.0.0.1:9333/dir/status   # -> 200
curl -s -o /dev/null -w "sw volume -> %{http_code}\n" http://127.0.0.1:8080/status        # -> 200
curl -s http://127.0.0.1:9333/dir/status            # topology should list 127.0.0.1:8080
```

Healthy looks like: `pg_isready` → "accepting connections"; SeaweedFS master and volume → `200`; and `/dir/status` shows a non-null `DataCenters` listing `127.0.0.1:8080`. If the volume is still `000`, give it another 10–15 s (`docker logs --tail 20 seaweedfs` should end with `added volume server 0: 127.0.0.1:8080` and `Heartbeat to: 127.0.0.1:9333`).

---

## 3. Code, venv, and dependencies

```bash
cd ~
git clone https://github.com/brucecostello2/MBCP.git     # PRIVATE repo → enter GitHub username + PAT
cd MBCP
git checkout feat/slice2-weight-roundtrip                # use `main` once PR #2 is merged
python3 -m venv .venv
. .venv/bin/activate
pip install -U pip wheel
pip install -e ".[dev]"
```

**Install with the `.[dev]` extra, not bare `pip install -e .`.** `pytest` and `pytest-asyncio` live in the `dev` optional-dependency group; a bare editable install pulls only the runtime deps and you'll hit `Command 'pytest' not found`.

To avoid repeated PAT prompts in a session: `git config --global credential.helper 'cache --timeout=3600'`.

---

## 4. Environment variables

The test harness (`tests/conftest.py`) reads the DB URL from **`MBCP_TEST_DATABASE_URL`** and the weight store from **`MBCP_SEAWEEDFS_MASTER_URL`**. Its built-in default DB URL is `...mbcp@127.0.0.1:5434/mbcp_test` (port **5434**, **no password**) — which does **not** match the container in §2.1 — so you must override it:

```bash
export MBCP_TEST_DATABASE_URL="postgresql+asyncpg://mbcp:mbcp@127.0.0.1:5432/mbcp_test"
export MBCP_SEAWEEDFS_MASTER_URL="http://127.0.0.1:9333"
```

These are **shell-scoped** and lost when you open a new session. Capture them in a `dev.env` at the repo root and `source` it each session:

```bash
cat > ~/MBCP/dev.env <<'EOF'
export MBCP_TEST_DATABASE_URL="postgresql+asyncpg://mbcp:mbcp@127.0.0.1:5432/mbcp_test"
export MBCP_SEAWEEDFS_MASTER_URL="http://127.0.0.1:9333"
EOF
# then, each new session:
cd ~/MBCP && . .venv/bin/activate && source dev.env
```

(Do **not** commit `dev.env`; it's environment-specific. Add it to `.gitignore`.)

---

## 5. Run the test suite

```bash
cd ~/MBCP && . .venv/bin/activate && source dev.env
python -m pytest tests/ -v
```

Use `python -m pytest` (uses the venv's pytest module directly) rather than the bare `pytest` script.

The session-scoped `_migrated_db` fixture **resets `schema public` and runs `alembic upgrade head` itself**, so you do **not** run Alembic manually. To run only the round-trip:

```bash
python -m pytest tests/integration/test_weight_roundtrip.py -v
```

---

## 6. Expected result

```
collected 26 items
tests/integration/test_weight_roundtrip.py::test_real_weight_bundle_roundtrip PASSED
...
26 passed, 2 warnings in ~2s
```

The integration test proves, byte-for-byte: ingest a real tar bundle → opaque signed manifest → stream each file by logical name from SeaweedFS → reassembled bytes' SHA-256 matches, with no fid/filer path crossing the API boundary.

---

## 7. Benign warnings (no action needed now)

1. `SAWarning: transaction already deassociated from connection` — pre-existing, from the idempotency test.
2. `tarfile.py DeprecationWarning` (Python 3.14 tar-extraction filtering) — the bundle extraction doesn't pass `filter=`. Harmless on 3.12; minor future-proofing to add before Python 3.14. **Ledger item for the repo, not a blocker.**

---

## 8. Corrections vs. the Slice 2 report §7 / older agent notes

For whoever maintains the repo (fold these into a `SETUP.md` and fix §7):

1. **SeaweedFS networking.** It must run with `--network host` given `-ip=127.0.0.1`. The published-port form returns `HTTP 000` (connection-refused) from the host because the master/volume bind the container's loopback. This was the single biggest source of "it's running but unreachable."
2. **Dependency install.** Use `pip install -e ".[dev]"`. Bare `pip install -e .` omits `pytest`/`pytest-asyncio` (they're in the `dev` extra).
3. **Test DB URL.** Set `MBCP_TEST_DATABASE_URL` to match the actual container — port **5432**, password **mbcp** — overriding the conftest default of `5434` / no-password.
4. **No `docker-compose.test.yml`.** The agent notes referenced one; it does not exist. Bring up the two containers in §2. (The `deploy/*.compose.yaml` files are deployment manifests, not the test harness.)
5. **Test layout.** Tests live in `tests/` and `tests/integration/` — there is **no `tests/unit/`** (the agent note's `pytest tests/unit` is wrong).
6. **Invocation.** Prefer `python -m pytest` over the bare `pytest` console script.
7. **Python source.** Ubuntu 24.04 ships Python 3.12 — the deadsnakes PPA step is unnecessary. The frontend `npm install` is not needed to run the Serving round-trip.

---

## 9. Reuse for later slices

This host (`mbcp-node-01`) is the standing **Serving + Management** dev host (PG17 + SeaweedFS) for Slices 3–5. For **Slice 3** (the real LatentSync run), the bench worker runs separately and points at node-04's existing LatentSync engine (`node-04:7860`) while fetching weights from *this* Serving stack. If that worker runs on a different machine, SeaweedFS/Postgres must be reachable over the LAN (`192.168.1.51`) rather than `127.0.0.1`, which means: re-launch SeaweedFS with `-ip=192.168.1.51` (and open the relevant ports / firewall) instead of `127.0.0.1`. Not required for the local Slice 2 test.

## 10. Teardown / restart

```bash
# stop (keep state)
docker stop seaweedfs mbcp-pg
# start again
docker start mbcp-pg seaweedfs            # wait ~20s for the SeaweedFS volume to re-register
# full removal (destroys the ephemeral SeaweedFS data + the PG database)
docker rm -f seaweedfs mbcp-pg
```
