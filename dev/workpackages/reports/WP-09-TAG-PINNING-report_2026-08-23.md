# WP-09-TAG-PINNING (scheduler pin) — report

| | |
|---|---|
| **Package** | `dev/workpackages/WP-09-TAG-PINNING.md` — this run covers the **scheduler pin** only, as scoped by the operator's 2026-08-23 batch instruction |
| **Ledger** | **P2.11** — `IVGS_SCHEDULER_TAG=latest` is the one unpinned tag and violates §19.5 |
| **HEAD at start** | `166a802` (batch base `f70d63e`) |
| **Date** | 2026-08-23 |
| **Scope given** | Pin `ivgs-scheduler` to a real tag by **digest-confirmed identity of what is running now**; tracked compose only; **no recreate needed if the tag matches the running content — verify and say so.** |

---

## 1. What was actually running, and the finding that matters

| Fact | Value |
|---|---|
| Running container image (name) | `ghcr.io/brucecostello2/ivgs-scheduler:latest` |
| Running image ID | `sha256:efc7c7469ea4d2c09465ddd96a93d023edd7eb8381d94ef73d88f9e7ec509109` |
| Image `Created` | **2026-05-22T19:58:28Z** |
| Local tags resolving to that ID | `:latest`, and nothing else |

**`latest` was not merely unpinned — it did not exist in the registry.**

```
$ sudo docker manifest inspect ghcr.io/brucecostello2/ivgs-scheduler:latest
manifest unknown
```

And it was not in the artifact store either — no `*ivgs-scheduler*` file under
`/mnt/ivgs-shared/image-artifacts/`.

So the GPU scheduler this fleet depends on existed as **exactly one copy**: node-01's local
docker store, built three months ago and never pushed anywhere. The stack keeps starting only
because deploys are invoked with `--pull never`. A `docker compose pull`, a store prune, or a
rebuild of node-01 would have destroyed it, and it could only have been *re*built from source —
a different digest, unverifiable against what had been running.

**That is a materially worse problem than P2.11 describes**, and it is the same shape as the
irreplaceable-LatentSync risk P1.4j closed on 2026-08-22.

## 2. What was done

**No rebuild.** A rebuild changes the digest and breaks parity with what is running (runbook
§3.5a). The running image was **re-tagged**, so the content is bit-identical:

```
docker tag sha256:efc7c746… ghcr.io/brucecostello2/ivgs-scheduler:v5.0.0-20260522
```

Tag chosen from evidence, not invented: **`5.0.0`** is the version the service reports about
itself (`ivgs-scheduler/main.py:522`, `:875`), and **`20260522`** is the image's own `Created`
date. It is a real, immutable, descriptive tag.

**Banked before pushing** (rule 1):

| Check | Result |
|---|---|
| `brucecostello2_ivgs-scheduler_v5.0.0-20260522.tar.zst` | written |
| `sha256sum -c` | **rc 0** — `ccbaccbbdb45066aa997539f3b3b0345496fdf277d3e1f08ba34f4c915a3f5cf` |
| `zstd -t` | **rc 0** |
| MANIFEST lines | **1** |
| image-config blob `efc7c746…` inside the archive | **1** |

**Then pushed, separately** — `rc 0`, and verified **from the registry**:

```
Name:      ghcr.io/brucecostello2/ivgs-scheduler:v5.0.0-20260522
Digest:    sha256:efc7c7469ea4d2c09465ddd96a93d023edd7eb8381d94ef73d88f9e7ec509109
```

**The digest is identical across all four**: the running container, node-01's local store, the
artifact store, and GHCR. The single-copy risk is closed as a side effect of the pin.

## 3. Tracked compose

`ivgs-infra/docker-compose.node01.yml`:

```diff
-    image: ghcr.io/brucecostello2/ivgs-scheduler:${IVGS_SCHEDULER_TAG:?IVGS_SCHEDULER_TAG required}
+    image: ghcr.io/brucecostello2/ivgs-scheduler:${IVGS_SCHEDULER_TAG:-v5.0.0-20260522}
```

with the full reasoning in a comment beside it. The default moves **into the tracked file**, so
the repository now records the pin and a fresh node resolves a real image without depending on an
untracked `.env`. The variable is still overridable.

`ivgs-infra/.env` was updated `latest` → `v5.0.0-20260522` and backed up first
(`.env.bak.pre-wp09-<ts>`). **It is not committed** — rule 7.

Verified by rendering the real invocation:

```
$ docker compose -f docker-compose.node01.yml -f docker-compose.override.node01.yml \
                 -f docker-compose.monitoring.yml --env-file .env config | grep ivgs-scheduler:
    image: ghcr.io/brucecostello2/ivgs-scheduler:v5.0.0-20260522
```

## 4. Recreate — NOT needed, and here is the verification

The instruction asked this be verified rather than assumed.

```
running container .Image                     = sha256:efc7c7469ea4…ec509109
ghcr…/ivgs-scheduler:v5.0.0-20260522 .Id     = sha256:efc7c7469ea4…ec509109
                                               IDENTITY MATCH
```

The new tag names the **same image object** the container is already running. There is no content
difference to deploy, so **no recreate is required** and none was performed. `ivgs-scheduler` has
been up 8 days and stays up.

**One cosmetic mismatch, stated rather than hidden.** The running container's `.Config.Image`
still reads `…:latest`, because that was its name when it was created; `.env` and the compose
file now say `v5.0.0-20260522`. The *content* is identical, so this is a naming artefact, not
drift in the sense CLAUDE.md §6 warns about — but a reader running `docker inspect` will see the
old name until the container is next recreated for some other reason. If the operator wants the
name reconciled immediately:

```
# RUN ON: IVGS node-01 (192.168.1.90)
( cd /opt/ivgs/ivgs-infra || exit 1
  docker compose -f docker-compose.node01.yml -f docker-compose.override.node01.yml \
    -f docker-compose.monitoring.yml --env-file .env \
    up -d --force-recreate --no-deps --pull never ivgs-scheduler
  docker inspect ivgs-scheduler --format '{{.Config.Image}} {{.Image}}'
) | tr -cd '\11\12\15\40-\176'
```

It is a no-op on content. Left to the operator because the instruction said no recreate is needed
when the tag matches, and it does.

## 5. Out of scope / not done

- **The other services' tags were not audited.** WP-09's full brief covers tag pinning generally;
  this run was scoped to the scheduler. `IVGS_BACKUP_WORKER_TAG=v5.1.0-stream-b` and the rest are
  already real tags.
- **`ivgs-scheduler:latest` was not deleted** from the local store or GHCR — nothing is deleted
  without operator sign-off, and it is now a harmless alias for a banked, pushed image.

## 6. Ledger

**P2.11 — CLOSEABLE.** `IVGS_SCHEDULER_TAG` is pinned to `v5.0.0-20260522`, in the tracked compose
and in `.env`, digest-confirmed against the running container. The §19.5 violation is resolved.

**Propose P2.48 — audit every image the fleet runs for registry presence, not just tag pinning.**
This package found an image that was pinned-by-name to a tag that did not exist in any registry.
`docker images` and a `.env` tag both looked fine; only `docker manifest inspect` revealed it.
Nothing checks that a deployed image can actually be re-obtained. Candidates to check the same
way: `ivgs-workers:cogvideox-pilot-1` (hardcoded in node-02/03 compose) and the six
`*-v5.2.7-h0` engine images on node-04.

## 7. Exit gate

| Clause | Verdict |
|---|---|
| Pinned to a real tag | **MET** — `v5.0.0-20260522` |
| Pin is by digest-confirmed identity of what is running | **MET** — one digest across container, local store, artifact store, GHCR |
| Tracked compose only | **MET** — compose committed; `.env` edited, backed up, not committed |
| No recreate if the tag matches the running content — verified and stated | **MET** — identity verified; no recreate performed |
