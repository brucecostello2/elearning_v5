# WP-45 — operator blocks, zero edits

Every block below is a single self-gating paste. Node-labelled, plain ASCII, no
angle brackets, no `exit` outside a subshell (dev/CLAUDE.md §5). Nothing here
prints a secret.

Run them in the order given: **B1 first on every GPU node**, then **B2**, then
optionally B3 and B4.

---

## B1 — the workers on nodes 02–05: image, and the stable node name

**Why both in one block.** They travel together and each is pointless without
the other in this window:

* `v5.11.0-apibatch` carries the Task 1 upload contract. A node still on
  `v5.10.0-quality` uploads with the pre-WP-45 field shape; the API tolerates it
  (there is a compatibility branch, and it logs
  `asset_upload_legacy_hash_field` every time it fires) but that node stores no
  provenance and no generation-parameters hash, so **dedup cannot hit for its
  branch**. node-03 is animation and node-04 is image; those are the two
  branches the hash dedup was built for.
* `IVGS_NODE_NAME` is what stops the scheduler registry filling with container
  hex ids. Until a node has it, the GPU Fleet page shows that node as
  `unnamed (61c7c02b3a…)` — which is the truth, and is how you can see at a
  glance which nodes have had this block applied.

**The image must be present before any `.env` is written** (WP-34 rule 2). The
block gates on that and refuses rather than half-applying.

```
# RUN ON: the node in question.
#   node-02 = 192.168.1.91   SVC=celery-worker           CT=ivgs-celery-node02
#   node-03 = 192.168.1.92   SVC=cogvideox-worker        CT=ivgs-cogvideox-worker-node03
#   node-04 = 192.168.1.93   SVC=celery-worker           CT=ivgs-celery-node04
#   node-05 = 192.168.1.94   SVC=celery-worker           CT=ivgs-celery-node05
#
# node-03's service is NOT celery-worker. WP-44 §6.3 recorded exactly this:
# naming celery-worker on node-03 bypasses a profile gate and starts a SECOND
# worker competing for gpu_llm while the real one stays on the old image.
# Derive it from the running container's own labels if in any doubt:
#   docker inspect CONTAINER --format '{{index .Config.Labels "com.docker.compose.service"}}'
(
  set -u
  NODE=node02        # node02 | node03 | node04 | node05
  NAME=node-02       # node-02 | node-03 | node-04 | node-05   (note the HYPHEN)
  SVC=celery-worker  # node-03: cogvideox-worker
  CT=ivgs-celery-node02
  TAG=v5.11.0-apibatch
  ART=/mnt/ivgs-shared/image-artifacts/brucecostello2_ivgs-workers_$TAG.tar.zst
  IMG=ghcr.io/brucecostello2/ivgs-workers:$TAG

  cd /opt/ivgs/ivgs-infra || { echo "ABORT: no /opt/ivgs/ivgs-infra"; exit 0; }

  # --- 1. image on this node, by artifact. The registry is off the deploy path.
  if [ -z "$(docker images -q $IMG)" ]; then
    if [ ! -f "$ART" ]; then echo "ABORT: artifact not readable at $ART"; exit 0; fi
    echo "loading $ART ..."
    zstd -d -c "$ART" | docker load || { echo "ABORT: docker load failed"; exit 0; }
  fi
  if [ -z "$(docker images -q $IMG)" ]; then
    echo "ABORT: $IMG still not present after load. .env NOT touched."; exit 0
  fi
  echo "image present: $(docker images -q $IMG)"

  # --- 2. rollback tag, recorded before anything is written
  echo "ROLLBACK TAG (write this down): $(grep -E '^IVGS_WORKERS_TAG=' .env.$NODE || echo 'not set in .env.'$NODE)"
  cp -a ".env.$NODE" ".env.$NODE.bak-pre-wp45-$(date -u +%Y%m%d-%H%M%S)" || { echo "ABORT: could not back up .env.$NODE"; exit 0; }

  # --- 3. the identity line, appended once
  if grep -q '^IVGS_NODE_NAME=' ".env.$NODE"; then
    echo "IVGS_NODE_NAME already present, not appending"
  else
    printf '%s\n' \
      '' \
      '# WP-45 Task 4(a). The GPU scheduler keys nodes as {node_hostname}:gpu{index},' \
      '# and node_hostname defaulted to the CONTAINER hostname - a hex id that changes' \
      '# on every recreate. Measured 2026-08-25: 21 registered "nodes" on a fleet of' \
      '# three GPUs, none of which could be traced to a physical machine. This is the' \
      '# stable name; config.py reads it BEFORE IVGS_NODE_HOSTNAME.' \
      "IVGS_NODE_NAME=$NAME" >> ".env.$NODE"
  fi
  grep -E '^IVGS_NODE_NAME=' ".env.$NODE"

  # --- 4. the tag
  if grep -q '^IVGS_WORKERS_TAG=' ".env.$NODE"; then
    sed -i "s/^IVGS_WORKERS_TAG=.*/IVGS_WORKERS_TAG=$TAG/" ".env.$NODE"
  else
    printf 'IVGS_WORKERS_TAG=%s\n' "$TAG" >> ".env.$NODE"
  fi
  grep -E '^IVGS_WORKERS_TAG=' ".env.$NODE"

  # --- 5. node-04 only: prove the engine tag is untouched (WP-34 rule 5)
  if [ "$NODE" = "node04" ]; then
    echo "LATENTSYNC BEFORE: $(grep -E '^IVGS_LATENTSYNC_TAG=' .env.node04)"
  fi

  # --- 6. the recreate. --no-deps or Postgres/engines come with it.
  docker compose -f "/opt/ivgs/ivgs-infra/docker-compose.$NODE.yml" \
    --env-file /opt/ivgs/ivgs-infra/.env \
    up -d --force-recreate --no-deps --pull never "$SVC" || echo "compose returned non-zero"

  sleep 25
  echo "--- running image (docker ps is the truth; env vars are NOT, CLAUDE.md §6) ---"
  docker inspect "$CT" --format '{{.Config.Image}}'
  echo "--- the node registers under its real name now ---"
  docker logs "$CT" 2>&1 | grep -E 'node_registered|node_registration_skipped|gpu_identity' | tail -3
  if [ "$NODE" = "node04" ]; then
    echo "LATENTSYNC AFTER : $(grep -E '^IVGS_LATENTSYNC_TAG=' .env.node04)"
    echo "--- engines must NOT have been recreated (uptime should be hours) ---"
    docker ps --format '{{.Names}}\t{{.Status}}' | grep -E 'latentsync|comfyui|coqui|kokoro|whisperx'
  fi
) 2>&1 | tr -cd '\11\12\15\40-\176'
```

**Evidence to collect after each node, from node-01:**

```
# RUN ON: IVGS node-01 (192.168.1.90)
curl -s http://192.168.1.90:8002/fleet \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print("total", d["total_nodes"], "alive", d["alive_nodes"]); [print(" ", n["node_id"], n["is_alive"]) for n in d["nodes"] if n["is_alive"]]'
```

A node that has taken B1 appears as `node-02:gpu0` rather than a hex id, and the
GPU Fleet page stops labelling it `unnamed (...)`.

---

## B2 — retire the dead scheduler node registrations

**Only after B1 has been applied to every GPU node you intend to run.** Until
then these hex ids include the LIVE workers, and deleting them would deregister
a node that is working.

The registry accumulated one entry per container the fleet has ever run: 21
entries on three GPUs, 18 of them dead. WP-45 did not clear them, because
"which nodes are still unnamed" is exactly what the GPU Fleet page is now
telling you, and clearing them before B1 would hide that.

```
# RUN ON: IVGS node-01 (192.168.1.90)
(
  set -u
  BK="/opt/ivgs/dev/workpackages/WP-45-gpu-registry-backup-$(date -u +%Y%m%d-%H%M%S).txt"
  {
    echo "# scheduler GPU registry, before pruning dead nodes"
    for k in $(docker exec ivgs-redis redis-cli -n 1 smembers gpu:nodes:all | tr -d '\r'); do
      echo "## $k"; docker exec ivgs-redis redis-cli -n 1 hgetall "gpu:node:$k"
    done
  } > "$BK"
  echo "backup: $BK  ($(wc -l < "$BK") lines)"

  echo "--- nodes the scheduler still considers ALIVE (these are NOT touched) ---"
  curl -s http://192.168.1.90:8002/fleet \
    | python3 -c 'import json,sys; [print(" ", n["node_id"]) for n in json.load(sys.stdin)["nodes"] if n["is_alive"]]'

  echo
  echo "--- DEAD entries that would be removed ---"
  curl -s http://192.168.1.90:8002/fleet \
    | python3 -c 'import json,sys; [print(n["node_id"]) for n in json.load(sys.stdin)["nodes"] if not n["is_alive"]]' \
    > /tmp/wp45-dead-nodes.txt
  wc -l < /tmp/wp45-dead-nodes.txt
  echo "REVIEW /tmp/wp45-dead-nodes.txt, then run B2b below to delete them."
) 2>&1 | tr -cd '\11\12\15\40-\176'
```

```
# RUN ON: IVGS node-01 (192.168.1.90) -- B2b, the deletion, after reviewing the list
(
  set -u
  if [ ! -s /tmp/wp45-dead-nodes.txt ]; then echo "nothing to do"; exit 0; fi
  while read -r NID; do
    [ -z "$NID" ] && continue
    docker exec ivgs-redis redis-cli -n 1 DEL "gpu:node:$NID" "gpu:node:$NID:jobs" "gpu:heartbeat:$NID" > /dev/null
    docker exec ivgs-redis redis-cli -n 1 SREM gpu:nodes:all "$NID" > /dev/null
    docker exec ivgs-redis redis-cli -n 1 ZREM gpu:nodes:alive "$NID" > /dev/null
    docker exec ivgs-redis redis-cli -n 1 SREM gpu:nodes:draining "$NID" > /dev/null
    echo "removed $NID"
  done < /tmp/wp45-dead-nodes.txt
  echo "--- after ---"
  curl -s http://192.168.1.90:8002/fleet \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print("total", d["total_nodes"], "alive", d["alive_nodes"])'
) 2>&1 | tr -cd '\11\12\15\40-\176'
```

---

## B3 — rollback, node-01

Verified present, not assumed: `v5.10.0-quality` (api, workers) and
`v5.9.0-telemetry` (frontend) are all still in node-01's local image store, and
their artifacts are still in `/mnt/ivgs-shared/image-artifacts`.

```
# RUN ON: IVGS node-01 (192.168.1.90)
(
  set -u
  cd /opt/ivgs/ivgs-infra || { echo "ABORT"; exit 0; }
  cp -a .env ".env.bak-pre-rollback-$(date -u +%Y%m%d-%H%M%S)"
  sed -i 's/^IVGS_API_TAG=.*/IVGS_API_TAG=v5.10.0-quality/;
          s/^IVGS_FRONTEND_TAG=.*/IVGS_FRONTEND_TAG=v5.9.0-telemetry/;
          s/^IVGS_WORKERS_TAG=.*/IVGS_WORKERS_TAG=v5.10.0-quality/' .env
  grep -E '^IVGS_(API|FRONTEND|WORKERS)_TAG=' .env
  docker compose -f docker-compose.node01.yml \
    -f docker-compose.override.node01.yml \
    -f docker-compose.monitoring.yml \
    --env-file /opt/ivgs/ivgs-infra/.env \
    up -d --force-recreate --no-deps --pull never \
    fastapi-backend nextjs-frontend celery-worker-default celery-worker-composition celery-beat
  sleep 20
  docker ps --format '{{.Names}}\t{{.Image}}' | grep -E 'fastapi|nextjs|celery'
) 2>&1 | tr -cd '\11\12\15\40-\176'
```

**The database migration does NOT need reverting to roll back the code.**
Migration 0028 only ADDS nullable columns and widens one; `v5.10.0-quality`
neither reads nor writes any of them, so it runs unchanged against the migrated
schema. Revert the schema only if you are abandoning the work entirely:

```
# RUN ON: IVGS node-01 (192.168.1.90) -- schema revert, rarely wanted
( cd /opt/ivgs/ivgs-api && \
  DATABASE_URL="postgresql+asyncpg://ivgs:PASSWORD@192.168.1.90:5432/ivgs" \
  /opt/ivgs/.venv/bin/python -m alembic downgrade 0027 ) 2>&1 | tr -cd '\11\12\15\40-\176'
```

`downgrade` **refuses** rather than truncating if any `model_approvals` row has
a `vetting_reference` longer than 512 characters — an attestation may not be
silently shortened. The pre-migration dump is at
`/mnt/ivgs-shared/db-backups/pre-wp45-0028-20260825-151437.dump` with a sha256
beside it.

---

## B4 — GHCR push (optional; the registry is off the deploy path)

WP-34 rule 1 decouples the registry from the deploy, and all three artifacts are
banked and verified, so this is a convenience rather than a recovery path.

```
# RUN ON: IVGS node-01 (192.168.1.90)
( for i in api frontend workers; do
    docker push "ghcr.io/brucecostello2/ivgs-$i:v5.11.0-apibatch" || echo "push failed: $i"
  done ) 2>&1 | tr -cd '\11\12\15\40-\176'
```
