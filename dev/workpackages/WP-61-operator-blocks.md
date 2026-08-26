# WP-61-QWEN — operator blocks

Every block below is **single, self-gating, plain ASCII, node-labelled**, and
**safe to abort**: a block that finds a precondition unmet prints why and stops
without having written anything. None uses `exit` at top level — they are
wrapped in `( ... )` or if/then/fi, because `exit` in a block pasted into an
interactive shell kills the login session (dev/CLAUDE.md §5).

**NODE-05 BLOCKS RUN ON NODE-05, reached by SSH from node-01.** Each says so in
its first line. Claude did not run any of them and did not read anything from
node-05; every figure they produce belongs in the report as an operator
measurement, not as a claim made here.

**NODE-06 IS OUT OF BOUNDS.** Nothing here touches it.

Order matters. A05 → A06 → A06B → A07 (the long one) → A08 → A09 → A10, then
N01-A and N01-B on node-01.

---

## CORRECTED 2026-08-26 BY WP-62 TASK 8 — five field defects, all measured

**This file is tracked, it was executed, and it was wrong in five places the
operator had to fix live.** The corrections are made IN PLACE below, each
marked, because a corrections appendix at the bottom of a file of paste blocks
is a corrections appendix nobody reads before pasting.

| | What was wrong | Where |
|---|---|---|
| (a) | `--entrypoint huggingface-cli`. The binary is REMOVED from the current nightly and its shim exits 1. `--local-dir-use-symlinks` is rejected by the newer hub. | A07 |
| (b) | `find ... -type f` hashed NOTHING. hf's cache exposes `*.safetensors` only as snapshot SYMLINKS, so a 29 GB cache manifested as "safetensors files: 0". | A07, both places |
| (c) | The ufw rules were APPENDED. node-05 carries `Anywhere ALLOW from 192.168.1.0/24`, so the appended deny sat below it and was inert. | A08 |
| (d) | The engine floated on `cu130-nightly` and THE TAG MOVED MID-PACKAGE — same version string, new digest. | A09, and the compose/env |
| (e) | Two shas of the same template were printed under the same label. Nothing had diverged. | N01-A |

**(e) is the one worth reading, because the conclusion is the opposite of the
report.** WP-62 was told the image's baked seed template differed from the tree
at the same commit — container `205ddaba…` against tracked `67be5991…`.
**Measured 2026-08-26 on the running stack: it does not.**
`sha256sum /app/seed/default_prompts/translation.j2` inside `ivgs-fastapi`
(`ivgs-api:v5.20.0-qwen`) returns `67be5991ad4819…`, byte-identical to the
tracked file. No divergence, no `.dockerignore` gap, no stale layer.

`205ddaba…` is the sha256 of the **same bytes with the trailing newline
stripped** — proven: `printf '%s' "$(cat translation.j2)" | sha256sum` gives
`205ddabad3673a5939316e622ee23a79a7b1aaa272f803d6b1ed09ccc6747a1f` exactly.
It is what `app/scripts/wp61_publish_prompt.py:70` computes, because it does
`.read_text().strip()` before hashing, and what line 73 prints under the label
`sha256`. N01-A step 1 prints `sha256sum ivgs-api/seed/default_prompts/…`
directly above it. **Two digests, of two different byte strings, one label,
five lines apart in one package.**

The defect was real and it was a MEASUREMENT defect, not a build defect. Both
halves are closed: the publish script now prints both digests each named for
what it covers, and `scripts/check_seed_conformance.sh` gates baked-equals-
tracked so a genuinely divergent seed cannot ship silently.

---

## A05 — node-05 preflight. READ-ONLY, writes nothing.

Run this first and read all of it. It establishes that the machine is the one
this package was written for, and it refuses if it is not.

```
# RUN ON: node-05 (192.168.1.94), via  ssh dev@192.168.1.94  from node-01.
# READ-ONLY. Nothing below writes, starts, stops or downloads anything.
(
  set -u
  echo "== host =="
  hostname; ip -4 addr show | grep -o '192\.168\.1\.[0-9]*' | sort -u | head -3
  echo
  echo "== card, driver, and the VRAM this package is sized against =="
  nvidia-smi --query-gpu=name,memory.total,driver_version,temperature.gpu,power.draw \
             --format=csv,noheader || echo "nvidia-smi FAILED"
  echo
  echo "== host RAM (78 GB expected after the replacement) =="
  free -g | awk 'NR<=2'
  echo
  echo "== disk headroom for a ~29 GB weight cache on /data =="
  df -h /data 2>/dev/null || df -h /
  echo
  echo "== the repo, and the commit it is on =="
  if [ -d /opt/ivgs/.git ]; then
    git -C /opt/ivgs log --oneline -1
    git -C /opt/ivgs status --porcelain | head
  else
    echo "NO /opt/ivgs CHECKOUT"
  fi
  echo
  echo "== what is running. Expect telemetry ONLY: no worker, no scorer. =="
  docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}'
  echo
  echo "== the old CLIP scorer must be gone (node-06 is the sole host now) =="
  docker ps -a --format '{{.Names}}' | grep -i clip && \
    echo ">>> A CLIP CONTAINER STILL EXISTS ON node-05. Stop here and remove it." || \
    echo "OK: no clip container"
  echo
  echo "== port 8000 must be free =="
  ss -ltnp 2>/dev/null | grep ':8000 ' && echo ">>> :8000 IS IN USE" || echo "OK: :8000 free"
  echo
  echo "== ufw, as it stands now =="
  sudo ufw status verbose 2>/dev/null | head -20
)
```

**Read before continuing.** Expect `NVIDIA RTX PRO 5000 Blackwell, 48935 MiB,
580.173.02`, ~78 GB RAM, at least ~60 GB free on `/data`, and exactly the
telemetry containers. If the card or the VRAM differs, **stop**: every number
in this package is sized against 48935 MiB.

---

## A06 — deliver the two tracked files, SHA-gated. Writes 2 files.

**Precondition: the WP-61 commits have been pushed** (the count-gated push block
in the report). This block pulls them rather than pasting them, because
`docker-compose.llm.node05.yml` contains `>` and `${...}` and pasting angle
brackets through PuTTY is forbidden (dev/CLAUDE.md §5).

```
# RUN ON: node-05 (192.168.1.94), via ssh from node-01.
# Writes: ivgs-infra/.env.node05  (mode 600). Touches nothing else.
(
  set -u
  cd /opt/ivgs || { echo "ABORT: no /opt/ivgs"; return 0 2>/dev/null || exit 0; }

  echo "== BEFORE =="; git log --oneline -1

  git fetch --all --quiet || { echo "ABORT: fetch failed"; return 0 2>/dev/null || exit 0; }
  git checkout main --quiet && git pull --ff-only || {
    echo "ABORT: could not fast-forward. Resolve by hand; do not force."
    return 0 2>/dev/null || exit 0; }

  echo "== AFTER =="; git log --oneline -1

  # --- THE SHA GATE. These are the exact bytes this package was tested against.
  # WP-62 Task 8(d): BOTH VALUES CHANGED. The compose file now pins the engine
  # by digest and .env.node05.example carries VLLM_IMAGE_DIGEST. A gate holding
  # the WP-61 shas would refuse the corrected files, which is the gate working
  # - and it would refuse them without saying why, so it is updated here rather
  # than left to fire.
  WANT_COMPOSE=__WANT_COMPOSE__
  WANT_ENVEX=__WANT_ENVEX__
  GOT_COMPOSE=$(sha256sum ivgs-infra/docker-compose.llm.node05.yml | cut -d' ' -f1)
  GOT_ENVEX=$(sha256sum ivgs-infra/.env.node05.example | cut -d' ' -f1)
  echo "compose  want=$WANT_COMPOSE"
  echo "compose  got =$GOT_COMPOSE"
  echo "env.ex   want=$WANT_ENVEX"
  echo "env.ex   got =$GOT_ENVEX"
  if [ "$WANT_COMPOSE" != "$GOT_COMPOSE" ] || [ "$WANT_ENVEX" != "$GOT_ENVEX" ]; then
    echo ">>> SHA MISMATCH. Do not continue. The files on this node are not the"
    echo ">>> files this package was tested against."
    return 0 2>/dev/null || exit 0
  fi
  echo "OK: both files match"

  # --- the env file. EVERY VALUE IN THE TEMPLATE IS ALREADY CORRECT; there is
  # nothing to fill in. It is copied rather than symlinked because .env.node05
  # is gitignored and must not be recreated by a checkout.
  if [ -f ivgs-infra/.env.node05 ]; then
    echo "ivgs-infra/.env.node05 already exists - NOT overwritten. Diff it:"
    diff -u ivgs-infra/.env.node05 ivgs-infra/.env.node05.example | head -40
  else
    cp ivgs-infra/.env.node05.example ivgs-infra/.env.node05
    chmod 600 ivgs-infra/.env.node05
    echo "wrote ivgs-infra/.env.node05 (mode 600)"
    echo
    echo ">>> WP-62 Task 8(d): VLLM_IMAGE_DIGEST in the copied file is the"
    echo ">>> RECORDED PREFIX ONLY and is not a valid digest. RUN A06B NEXT."
    echo ">>> Compose will refuse to render this file until it is filled in,"
    echo ">>> which is the intended behaviour - the previous version silently"
    echo ">>> fell back to a floating tag that had already moved once."
  fi
  ls -l ivgs-infra/.env.node05
  echo
  echo "== the identity block, as it will reach the container =="
  grep -E '^(IVGS_NODE_|NODE_HOSTNAME|VLLM_MODEL_NAME|VLLM_SERVED_NAME|VLLM_MAX_NUM_SEQS|VLLM_REASONING_PARSER|VLLM_GPU_UTIL|VLLM_MAX_MODEL_LEN|HF_HOME)' \
    ivgs-infra/.env.node05
)
```

---

## A06B — resolve the engine digest and pin it. WP-62 Task 8(d). Writes 1 line.

**NEW IN WP-62. Run it after A06 and before A09.**

The compose file references `vllm/vllm-openai@${VLLM_IMAGE_DIGEST}` and has NO
`:-` default on that variable, deliberately: an unset value makes compose
refuse to render rather than quietly starting whatever `cu130-nightly` points
at today. `cu130-nightly` MOVED during WP-61 — two pulls, two images, the same
version string `v0.19.2rc1.dev134` on both. The version string is the field a
reader would have checked, and it did not move.

This block reads the digest off the image ALREADY ON THIS NODE — the one every
REAL-48GB figure was measured against — and writes it into `.env.node05`. It
refuses if that digest does not begin `sha256:3dbe092e`, because that prefix is
the recorded identity of the measured image and a different digest means the
numbers in the WP-61 report describe a different engine.

```
# RUN ON: node-05 (192.168.1.94), via ssh from node-01.
# Writes: ONE line of ivgs-infra/.env.node05. Pulls nothing, starts nothing.
(
  set -u
  cd /opt/ivgs || { echo "ABORT: no /opt/ivgs"; return 0 2>/dev/null || exit 0; }
  ENVF=ivgs-infra/.env.node05
  WANT_PREFIX=sha256:3dbe092e

  [ -f "$ENVF" ] || { echo "ABORT: $ENVF is missing. Run A06 first."
    return 0 2>/dev/null || exit 0; }

  # Prefer the digest of the image the RUNNING container was created from; fall
  # back to the local tag only if nothing is running yet. Reading the tag when a
  # container exists is exactly the mistake dev/CLAUDE.md section 6 records.
  DIG=$(docker inspect ivgs-vllm-qwen-node05 \
          --format '{{index .RepoDigests 0}}' 2>/dev/null)
  if [ -z "$DIG" ]; then
    DIG=$(docker inspect vllm/vllm-openai:cu130-nightly \
            --format '{{index .RepoDigests 0}}' 2>/dev/null)
    echo "NOTE: no running container; read from the local tag instead."
  fi
  [ -n "$DIG" ] || { echo "ABORT: no local vllm image to read a digest from."
    return 0 2>/dev/null || exit 0; }

  # RepoDigests is "repo@sha256:..." - keep only the digest part.
  DIG=${DIG#*@}
  echo "resolved: $DIG"

  case "$DIG" in
    "$WANT_PREFIX"*) echo "OK: matches the recorded prefix $WANT_PREFIX" ;;
    *) echo ">>> DIGEST MISMATCH. Expected a digest starting $WANT_PREFIX."
       echo ">>> This is NOT the image the REAL-48GB figures were measured on."
       echo ">>> Nothing written. Establish which image this is before pinning."
       return 0 2>/dev/null || exit 0 ;;
  esac

  cp -p "$ENVF" "$ENVF.bak-$(date -u +%Y%m%d-%H%M%S)"
  if grep -q '^VLLM_IMAGE_DIGEST=' "$ENVF"; then
    sed -i "s|^VLLM_IMAGE_DIGEST=.*|VLLM_IMAGE_DIGEST=$DIG|" "$ENVF"
  else
    printf 'VLLM_IMAGE_DIGEST=%s\n' "$DIG" >> "$ENVF"
  fi
  chmod 600 "$ENVF"
  echo
  echo "== the pinned line =="
  grep '^VLLM_IMAGE_DIGEST=' "$ENVF"
  echo
  echo "== compose can now render; this proves it =="
  docker compose --env-file "$ENVF" \
    -f ivgs-infra/docker-compose.llm.node05.yml config 2>&1 \
    | grep -E '^\s+image:' | head -2
)
```

**Put the full digest in the report** and, if it differs from the one recorded
in `.env.node05.example`, say so — the example carries the prefix only.

---

## A07 — the weights. **~29 GB. ALLOW 30–90 MINUTES.** Its own block, deliberately.

> **TIME WARNING.** This downloads roughly **29 GB** of FP8 safetensors from
> HuggingFace. On a domestic uplink it can take **well over an hour**. It is
> separated from every other step so that a slow or failed download costs
> nothing but itself, and so it can be re-run — `hf download` resumes.
> (WP-62 Task 8(a): the tool is `hf`. `huggingface-cli` is removed from the
> current nightly and its shim exits 1.)
>
> **RUN IT IN `tmux` OR `screen`.** An SSH drop mid-transfer is otherwise an
> hour lost.

**PROVENANCE, RULED.** A direct HuggingFace pull is authorised as a **second
operator exception** to the weights-from-MBCP doctrine. The first was the
2026-08-25 standalone evaluation, whose clone and cache were destroyed. The
exception carries a debt and this block is what makes the debt collectable:
**every downloaded `*.safetensors` and every `*.json` is sha256'd and the
manifest is written to `/mnt/ivgs-shared/qwen-weights-manifest-<date>.txt`.**

**MBCP must bank and certify this exact bundle (work orders 5 and 7) before the
Model Store may list it as anything other than an exception.** Until then the
model is *provenance-exceptional*: running, hashed, uncertified.

```
# RUN ON: node-05 (192.168.1.94), via ssh from node-01. USE tmux.
# Writes: /data/hf-cache (~29 GB) and one manifest file on the NFS share.
# Downloads nothing else and starts no service.
(
  set -u
  MODEL=Qwen/Qwen3.8-27B-FP8
  CACHE=/data/hf-cache
  STAMP=$(date -u +%Y-%m-%d)
  MANIFEST=/mnt/ivgs-shared/qwen-weights-manifest-$STAMP.txt

  sudo mkdir -p "$CACHE" && sudo chown "$(id -u):$(id -g)" "$CACHE"
  echo "cache: $CACHE"; df -h "$CACHE" | tail -1

  if [ ! -w /mnt/ivgs-shared ]; then
    echo "ABORT: /mnt/ivgs-shared is not writable; the manifest has nowhere to go."
    return 0 2>/dev/null || exit 0
  fi

  echo
  echo "== downloading $MODEL. THIS IS THE LONG ONE. =="
  date -u
  # WP-62 Task 8(a), CORRECTED IN THE FIELD 2026-08-26.
  #
  # WAS: --entrypoint huggingface-cli ... download "$MODEL" \
  #        --local-dir-use-symlinks False
  #
  # TWO DEFECTS, both fatal, both fixed here:
  #
  #   1. `huggingface-cli` IS REMOVED from the current nightly. What remains is
  #      a deprecation shim that EXITS 1, so the block aborted at `RC != 0` and
  #      the operator had to find the replacement live. The tool is now `hf`.
  #   2. `--local-dir-use-symlinks` is REJECTED by the newer hub client. It was
  #      also pointless here: there is no `--local-dir`, so the flag was trying
  #      to control the layout of a directory the command was not writing to.
  #
  # The cache layout is therefore the hub's own snapshot layout, with the
  # weights exposed as SYMLINKS - which is the whole of defect (b) below.
  docker run --rm -i \
    -v "$CACHE":/data/hf-cache \
    -e HF_HOME=/data/hf-cache \
    --entrypoint hf \
    vllm/vllm-openai:cu130-nightly \
    download "$MODEL"
  RC=$?
  date -u
  if [ $RC -ne 0 ]; then
    echo ">>> DOWNLOAD FAILED rc=$RC. Nothing was manifested. Re-run this block;"
    echo ">>> hf download resumes."
    return 0 2>/dev/null || exit 0
  fi

  echo
  echo "== sha256 of every weight and config file =="
  {
    echo "# Qwen weights manifest - IVGS WP-61-QWEN"
    echo "# model:      $MODEL"
    echo "# node:       node-05 (192.168.1.94)"
    echo "# downloaded: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "# cache:      $CACHE"
    echo "#"
    echo "# PROVENANCE: direct HuggingFace pull, authorised as the SECOND operator"
    echo "# exception to the weights-from-MBCP doctrine (the first was the"
    echo "# 2026-08-25 standalone evaluation, whose clone and cache were destroyed)."
    echo "#"
    echo "# DEBT, EXPLICIT: MBCP must BANK AND CERTIFY THIS EXACT BUNDLE (work"
    echo "# orders 5 and 7) before the Model Store lists it as anything other than"
    echo "# an exception. Until then this model is provenance-exceptional:"
    echo "# running, hashed, uncertified."
    echo "#"
    echo "# This file carries HASHES ONLY. No token, no key, no credential."
    echo
    # WP-62 Task 8(b), CORRECTED IN THE FIELD 2026-08-26. `find -L`, NOT `find`.
    #
    # WAS: find "$CACHE" -type f \( -name '*.safetensors' ... \)
    #
    # The hub cache stores blobs under `blobs/` and exposes them under
    # `snapshots/<rev>/` as SYMLINKS. `-type f` tests the link itself, not its
    # target, so every weight was skipped: a 29 GB cache produced a manifest
    # whose own total line read "safetensors files: 0". The manifest was
    # written, the block exited 0, and the provenance debt this exception was
    # authorised against was recorded against nothing.
    #
    # `-L` makes find follow the links, so `-type f` sees the blob. Both the
    # hashing pass here and the count below needed it; only fixing one would
    # produce a manifest whose body and whose total disagreed.
    find -L "$CACHE" -type f \( -name '*.safetensors' -o -name '*.json' \) \
      -printf '%s\t%p\n' | sort -k2 | while IFS=$'\t' read -r SZ F; do
        printf '%s  %12s  %s\n' "$(sha256sum "$F" | cut -d' ' -f1)" "$SZ" \
          "${F#$CACHE/}"
      done
    echo
    echo "# totals"
    # WP-62 Task 8(b): `-L` here too. THIS is the line that printed
    # "safetensors files: 0" over a 29 GB cache, and it is the line a reader
    # would trust.
    find -L "$CACHE" -type f -name '*.safetensors' | wc -l | \
      xargs printf '# safetensors files: %s\n'
    du -sh "$CACHE" | awk '{printf "# cache on disk:     %s\n", $1}'
  } > "$MANIFEST"

  chmod 644 "$MANIFEST"
  echo "wrote $MANIFEST"
  echo
  head -20 "$MANIFEST"
  echo "..."
  tail -5 "$MANIFEST"
)
```

**Put the manifest path and the safetensors count in the report.** Do not paste
the manifest body into chat — it is long, and it belongs on the share.

---

## A08 — ufw: :8000 open to 192.168.1.90–93 ONLY. Writes firewall rules.

node-01's API is the only client today. Nodes 02/03/04 are admitted so a future
worker-side binding does not need a firewall change. **Nothing else on the LAN,
and nothing off it.**

```
# RUN ON: node-05 (192.168.1.94), via ssh from node-01.
# Writes: ufw rules for tcp/8000 only. Does not enable or disable ufw itself.
(
  set -u
  echo "== BEFORE =="
  sudo ufw status numbered | sed -n '1,40p'
  echo

  if ! sudo ufw status | head -1 | grep -qi active; then
    echo ">>> ufw is INACTIVE on this node. Adding rules would do nothing and"
    echo ">>> would read as protection. Enable ufw deliberately first (it will"
    echo ">>> need an SSH allow rule), then re-run this block."
    return 0 2>/dev/null || exit 0
  fi

  # --- WP-62 Task 8(c). THE POSTURE CHECK, AND IT IS THE WHOLE CORRECTION.
  #
  # WAS: four `ufw allow` and one `ufw deny`, APPENDED, with a closing echo
  # telling the operator to "CHECK THE ORDER" by eye.
  #
  # WHAT WENT WRONG IN THE FIELD, 2026-08-26. This block assumed a
  # default-deny posture with nothing broad in front of it. node-05 carries
  #
  #     Anywhere    ALLOW    192.168.1.0/24
  #
  # ufw is FIRST-MATCH. An appended deny sits BELOW that rule, so every host on
  # the LAN still matched the subnet allow and reached :8000. The rule set
  # LOOKED like "fleet only" and was inert. The operator had to delete and
  # re-add the whole set by hand.
  #
  # An echo telling a human to check an ordering is not a control. The block
  # now MEASURES the posture, refuses if a broad rule is present and the
  # ordering cannot be guaranteed, and INSERTS at fixed positions 1-5 so the
  # four allows and the deny are above anything that was already there.
  echo "== BROAD RULES ALREADY PRESENT (this is the trap) =="
  BROAD=$(sudo ufw status | grep -cE 'Anywhere.*(ALLOW|LIMIT).*(/[0-9]+|Anywhere)')
  sudo ufw status | grep -E 'Anywhere' | head -10
  echo "broad-rule count: $BROAD"
  echo

  # Remove any earlier attempt so re-running cannot leave duplicates at
  # unpredictable positions. `delete` by rule spec is idempotent: it prints
  # "Could not delete non-existent rule" and returns without changing anything.
  for IP in 192.168.1.90 192.168.1.91 192.168.1.92 192.168.1.93; do
    sudo ufw delete allow from "$IP" to any port 8000 proto tcp >/dev/null 2>&1
  done
  sudo ufw delete deny 8000/tcp >/dev/null 2>&1

  # INSERT, DO NOT APPEND. Positions 1-4 are the allows and 5 is the deny, so
  # the deny is above the 192.168.1.0/24 allow and below the four hosts it
  # exempts. Inserting them in reverse so each lands at 1 would reverse the
  # host order; inserting at an explicit ascending position keeps the rule set
  # readable in the order it is written here.
  N=1
  for IP in 192.168.1.90 192.168.1.91 192.168.1.92 192.168.1.93; do
    sudo ufw insert $N allow from "$IP" to any port 8000 proto tcp \
      comment 'WP-61 qwen vllm'
    N=$((N+1))
  done
  sudo ufw insert 5 deny 8000/tcp comment 'WP-61 qwen vllm: fleet only'

  echo
  echo "== AFTER =="
  sudo ufw status numbered | sed -n '1,40p'
  echo
  echo "== THE GATE. The deny must be numbered BELOW all four allows and"
  echo "== ABOVE any 192.168.1.0/24 rule. This reads the numbers rather than"
  echo "== asking you to. =="
  DENY_POS=$(sudo ufw status numbered | grep '8000/tcp *DENY' | head -1 \
             | sed 's/^\[ *\([0-9]*\).*/\1/')
  SUBNET_POS=$(sudo ufw status numbered | grep '192.168.1.0/24' | head -1 \
               | sed 's/^\[ *\([0-9]*\).*/\1/')
  ALLOW_MAX=$(sudo ufw status numbered | grep '8000.*ALLOW.*192.168.1.9[0-3]' \
              | sed 's/^\[ *\([0-9]*\).*/\1/' | sort -n | tail -1)
  echo "allows end at: ${ALLOW_MAX:-none}   deny at: ${DENY_POS:-none}   subnet allow at: ${SUBNET_POS:-none}"
  if [ -z "$DENY_POS" ] || [ -z "$ALLOW_MAX" ]; then
    echo ">>> FAIL: the rules are not both present. :8000 is NOT fleet-only."
  elif [ "$DENY_POS" -le "$ALLOW_MAX" ]; then
    echo ">>> FAIL: the deny is ABOVE an allow. The fleet cannot reach :8000."
  elif [ -n "$SUBNET_POS" ] && [ "$SUBNET_POS" -lt "$DENY_POS" ]; then
    echo ">>> FAIL: the 192.168.1.0/24 allow is ABOVE the deny, so the deny is"
    echo ">>> INERT and the whole LAN can reach :8000. This is exactly what"
    echo ">>> happened on 2026-08-26. Delete rule $SUBNET_POS or move it below."
  else
    echo "OK: fleet-only. Four hosts allowed, everything else denied, and the"
    echo "OK: subnet allow (if any) sits below the deny."
  fi
)
```

---

## A09 — start the stack. Starts ONE container.

```
# RUN ON: node-05 (192.168.1.94), via ssh from node-01.
# Starts: ivgs-vllm-qwen-node05. Touches no other container on this node.
(
  set -u
  cd /opt/ivgs || { echo "ABORT: no /opt/ivgs"; return 0 2>/dev/null || exit 0; }

  [ -f ivgs-infra/.env.node05 ] || {
    echo "ABORT: ivgs-infra/.env.node05 is missing. Run A06 first."
    return 0 2>/dev/null || exit 0; }

  # THE --env-file IS LOAD-BEARING. `env_file:` on a service injects into the
  # CONTAINER; it does NOT feed ${VAR} interpolation in the YAML, and every
  # vLLM flag in this file is a ${VAR}. See dev/CLAUDE.md §6.3.
  # WP-62 Task 8(d): the image line is now a DIGEST reference with no `:-`
  # default, so this `config` fails outright if A06B has not run. That is the
  # intended failure - it used to fall back to a floating tag that had already
  # moved once inside one package.
  docker compose --env-file ivgs-infra/.env.node05 \
                 -f ivgs-infra/docker-compose.llm.node05.yml \
                 config 2>&1 | sed -n '/image:/,/^[^ ]/p' | head -3
  docker compose --env-file ivgs-infra/.env.node05 \
                 -f ivgs-infra/docker-compose.llm.node05.yml \
                 config 2>&1 | sed -n '/command:/,/^[^ ]/p' | head -20
  echo
  echo ">>> READ THE IMAGE AND THE COMMAND ABOVE. The image must be a"
  echo ">>>   vllm/vllm-openai@sha256:3dbe092e...  reference, NOT a :tag."
  echo ">>> The command must contain, literally:"
  echo ">>>   --model Qwen/Qwen3.8-27B-FP8"
  echo ">>>   --max-num-seqs 128        (MANDATORY: 1024 makes the engine refuse to start)"
  echo ">>>   --reasoning-parser qwen3  (MANDATORY: without it 1400 thinking tokens land in content)"
  echo ">>>   --gpu-memory-utilization 0.90   (NOT 0.48 - that was the simulation cap)"
  echo ">>> If any of those is missing or wrong, STOP. Do not start the container."
  echo
  echo "Press Ctrl-C now if it is wrong. Otherwise re-run with START=1:"
  if [ "${START:-0}" = "1" ]; then
    docker compose --env-file ivgs-infra/.env.node05 \
                   -f ivgs-infra/docker-compose.llm.node05.yml up -d
    echo
    docker ps --filter name=ivgs-vllm-qwen-node05 \
      --format '{{.Names}}\t{{.Image}}\t{{.Status}}'
    echo
    echo ">>> WP-62 Task 8(d): the digest the container was CREATED FROM, and"
    echo ">>> the digest .env.node05 pins. They must be the same string."
    docker inspect ivgs-vllm-qwen-node05 --format '{{index .RepoDigests 0}}' 2>/dev/null
    grep '^VLLM_IMAGE_DIGEST=' ivgs-infra/.env.node05
    echo
    echo ">>> FIRST START LOADS 27B OF FP8 WEIGHTS. Give it several minutes."
    echo ">>> healthcheck start_period is 900s deliberately."
  else
    echo "    START=1 bash -c '<paste this block again>'"
  fi
)
```

---

## A10 — THE ACCEPTANCE BATTERY. Read-only against the running server.

Four measurements, and **the fourth is the one this package exists to produce**:
the first REAL-48 GB numbers. Everything before this package was a 96 GB card
capped at 0.48 pretending to be a 48 GB card.

```
# RUN ON: node-05 (192.168.1.94), via ssh from node-01.
# READ-ONLY. Sends three requests and reads the startup log.
(
  set -u
  KEY=$(grep -E '^VLLM_API_KEY=' /opt/ivgs/ivgs-infra/.env.node05 | cut -d= -f2-)
  H="Authorization: Bearer $KEY"
  U=http://127.0.0.1:8000

  echo "=============== 1. /v1/models ==============="
  curl -s -o /tmp/models.json -w 'HTTP %{http_code}  %{time_total}s\n' -H "$H" "$U/v1/models"
  python3 -c "import json;d=json.load(open('/tmp/models.json'));print('served ids:',[m['id'] for m in d.get('data',[])])" 2>/dev/null \
    || cat /tmp/models.json | tr -cd '\11\12\15\40-\176' | head -5
  echo

  echo "=== 2. storyboard-shaped prompt, THINKING OFF, must return parseable JSON ==="
  cat > /tmp/sb.json <<'JSON'
{"model":"qwen38-27b","max_tokens":900,"temperature":0.2,
 "chat_template_kwargs":{"enable_thinking":false},
 "messages":[{"role":"user","content":"You produce storyboards as STRICT JSON and nothing else. Return an object with one key \"scenes\", an array of exactly 3 objects, each with keys scene_index (integer, 0-based), narration_text (string, one sentence), visual_description (string), media_type (one of image|video|animation) and duration_seconds (number). Topic: multiplying two-digit numbers. Output JSON only, no prose, no code fence."}]}
JSON
  START=$(date +%s.%N)
  curl -s -H "$H" -H 'Content-Type: application/json' \
       -d @/tmp/sb.json "$U/v1/chat/completions" -o /tmp/sb.out
  END=$(date +%s.%N)
  echo "elapsed: $(echo "$END - $START" | bc)s   <<< MUST BE SINGLE DIGIT"
  python3 - <<'PY'
import json,re
d=json.load(open('/tmp/sb.out'))
c=d['choices'][0]
txt=c['message']['content'] or ''
print('finish_reason:', c.get('finish_reason'))
print('usage:', d.get('usage'))
# reasoning_content must be where the thinking went, NOT content.
print('reasoning_content present:', bool((c['message'] or {}).get('reasoning_content')))
body=re.sub(r'^```(json)?|```$','',txt.strip(),flags=re.M).strip()
try:
    obj=json.loads(body)
    print('JSON PARSED OK. scenes:', len(obj.get('scenes',[])))
except Exception as e:
    print('JSON PARSE FAILED:', e)
    print(txt[:400])
PY
  echo

  echo "=========== 3. the 60K-token context probe ==========="
  python3 - <<'PY'
import json
# ~60,000 tokens of filler. One word per ~1.3 tokens, so 46k words.
filler = ("The distributive property lets us split a two digit number into "
          "tens and ones before multiplying. ") * 2000
body = {"model":"qwen38-27b","max_tokens":64,"temperature":0.0,
        "chat_template_kwargs":{"enable_thinking":False},
        "messages":[{"role":"user","content":
            filler + "\n\nIgnore everything above. Reply with exactly: CONTEXT-OK"}]}
open('/tmp/ctx.json','w').write(json.dumps(body))
PY
  START=$(date +%s.%N)
  curl -s -H "$H" -H 'Content-Type: application/json' \
       -d @/tmp/ctx.json "$U/v1/chat/completions" -o /tmp/ctx.out
  END=$(date +%s.%N)
  echo "elapsed: $(echo "$END - $START" | bc)s"
  python3 -c "
import json;d=json.load(open('/tmp/ctx.out'))
if 'error' in d: print('ERROR:', str(d['error'])[:300])
else:
    print('prompt_tokens:', d['usage']['prompt_tokens'], ' <<< the number that matters')
    print('reply:', repr((d['choices'][0]['message']['content'] or '')[:60]))
"
  echo

  echo "===== 4. THE REAL-48GB STARTUP NUMBERS. Tabulate these in the report. ====="
  echo "--- KV cache / blocks / concurrency, from the engine's own startup log ---"
  docker logs ivgs-vllm-qwen-node05 2>&1 \
    | grep -iE 'GPU KV cache size|Maximum concurrency|mamba|blocks|memory profiling|Available KV cache|model weights take|non-torch memory|PyTorch activation peak' \
    | tr -cd '\11\12\15\40-\176' | tail -25
  echo
  echo "--- VRAM AT IDLE, whole card and this process ---"
  nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw \
             --format=csv
  nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv
)
```

**What to record in the report, against the simulated figures:**

| Figure | Simulated (96 GB @ 0.48) | REAL 48 GB @ 0.90 |
|---|---|---|
| GPU KV cache size (tokens) | | |
| Mamba cache blocks | 216 | |
| Maximum concurrency (x) | | |
| VRAM used at idle (MiB / 48935) | | |
| Model weights (GiB) | | |

> **IF MAMBA BLOCKS COME BACK BELOW 128:** lower `VLLM_MAX_NUM_SEQS` in
> `ivgs-infra/.env.node05` to fit and record the figure. **DO NOT raise
> `VLLM_GPU_UTIL` past 0.92** to chase the simulation's numbers. The simulation
> is superseded by these measurements, not the other way round.

---

## N01-A — publish the amended translation prompt. **Writes one `prompts` row.**

The active translation prompt is `e16b6502-…`, version 1, created 2026-05-23,
and **nothing has ever rendered it**. Measured 2026-08-25 against it on Qwen:
the model appended a correction to the reference project's scene 5 in **all
four** target languages, because the narration genuinely teaches
10x3=30, 10x2=20 => "320" written as 230.

WP-61 Task 3(c) rules the contract to **fail-and-flag**. `TranslationService`
**refuses to run at all** under a prompt that does not carry it (409
`TRANSLATION_CONTRACT_MISSING`), because under the old prompt the strip finds
nothing to strip and the run records a silently corrected translation as
`complete`.

This block supersedes v1 through the prompts table's own versioning: it inserts
v2 and deactivates v1. **It does not UPDATE or DELETE v1** — the row that
produced the four corrections stays readable.

**Step 1 — read the current state. Writes nothing.**

```
# RUN ON: node-01 (192.168.1.90). READ-ONLY.
(
  set -u
  cd /opt/ivgs || { echo "ABORT: no /opt/ivgs"; return 0 2>/dev/null || exit 0; }
  PGPW=$(grep '^POSTGRES_PASSWORD=' ivgs-infra/.env | cut -d= -f2-)
  PGUSER=$(grep '^POSTGRES_USER=' ivgs-infra/.env | cut -d= -f2-)
  export PGPASSWORD="$PGPW"
  psql -h 192.168.1.90 -U "$PGUSER" -d ivgs -c \
    "SELECT id, version, is_active, created_by, created_at
       FROM prompts WHERE prompt_type='translation' ORDER BY version;"
  echo
  echo "== the amended template that will become v2 =="
  sha256sum ivgs-api/seed/default_prompts/translation.j2
  grep -c 'IVGS-TRANSLATION-FLAG:' ivgs-api/seed/default_prompts/translation.j2 \
    | xargs printf 'marker mentions in template: %s (must be >= 1)\n'
  unset PGPASSWORD
)
```

**Step 2 — publish v2. This is the step that writes.**

The template is read out of the running image rather than pasted: it contains
`{{ }}`, angle brackets and newlines, and dev/CLAUDE.md §5 forbids pasting
those through PuTTY. The script refuses and writes nothing if the marker is
absent from the template, or if there is not exactly one active global
translation prompt to supersede.

```
# RUN ON: node-01 (192.168.1.90).
# Writes: ONE new prompts row (translation v2, active) and sets is_active=false
# on v1. v1 is NOT updated or deleted - the row that produced the four silent
# corrections stays readable.
sudo docker exec -i ivgs-fastapi python -m app.scripts.wp61_publish_prompt
```

> **`docker exec` + heredoc REQUIRES `-i`.** Without it the heredoc executes
> EMPTY and exits 0 — a green result from a command that never ran (WP-60 Task
> 12(d)). The form above uses `-m` rather than a heredoc, which sidesteps the
> trap entirely. Every heredoc-bearing block in this file carries `-i`.

**Expected output:** the before rows, the template sha256, `v1 -> is_active
false`, `v2 inserted <uuid>`, and the after rows. Put the v2 id in the report.

---

## N01-B — Task 3(d): translate es-ES on the reference project. **Writes to ONE variant row.**

This is the acceptance, and it is the only live-data change this package makes
outside its own schema.

Project `c12fa967-f989-4ed4-8e20-3ea62cb92e8f` ("double digit multiplication",
18 scenes). Its `es-ES` variant is `3fccf815-f639-43c1-8a90-631336dc2d13`,
state `pending` — as are all 16 variant rows on this fleet, because translation
has never run.

**The flag path is expected to fire on real data**, because scene_index 5's
narration is genuinely wrong. That is the point: it is the only real-data proof
that the marker is captured, the deliverable is free of it, and the state goes
to `flagged` rather than `complete`.

**DO NOT REGENERATE OR EDIT THE SOURCE NARRATION.** It is the test case.

```
# RUN ON: node-01 (192.168.1.90). Needs A09/A10 green: node-05 must be serving.
# Writes: language_variants row 3fccf815 (state, translation, translation_flags).
# Writes nothing else on that project - no assets, no jobs, no scene edits.
(
  set -u
  cd /opt/ivgs || { echo "ABORT: no /opt/ivgs"; return 0 2>/dev/null || exit 0; }
  PGPW=$(grep '^POSTGRES_PASSWORD=' ivgs-infra/.env | cut -d= -f2-)
  PGUSER=$(grep '^POSTGRES_USER=' ivgs-infra/.env | cut -d= -f2-)
  export PGPASSWORD="$PGPW"
  PSQL="psql -h 192.168.1.90 -U $PGUSER -d ivgs"
  PID=c12fa967-f989-4ed4-8e20-3ea62cb92e8f
  VID=3fccf815-f639-43c1-8a90-631336dc2d13

  echo "== node-05 reachable from the API container? =="
  sudo docker exec ivgs-fastapi sh -c \
    'curl -s -o /dev/null -w "GET /v1/models -> HTTP %{http_code}\n" \
      -H "Authorization: Bearer $IVGS_VLLM_API_KEY" \
      "$IVGS_VLLM_TRANSLATION_URL/v1/models"' || {
      echo "ABORT: the API cannot reach node-05. Check ufw (A08)."
      unset PGPASSWORD; return 0 2>/dev/null || exit 0; }

  echo
  echo "== BEFORE =="
  $PSQL -c "SELECT id, language_code, state,
                   translation IS NOT NULL AS has_translation,
                   translation_flags
            FROM language_variants WHERE project_id='$PID' ORDER BY language_code;"

  echo
  echo "== the erroneous source scene, UNTOUCHED, for the record =="
  $PSQL -At -c "SELECT scene_index || ': ' || narration_text
                FROM storyboard_scenes WHERE project_id='$PID'
                AND scene_index = 5;"

  echo
  echo "== RUN. This calls node-05 once per scene; 18 scenes. =="
  date -u
  sudo docker exec -i ivgs-fastapi python - <<'PY'
import asyncio, json
from uuid import UUID
from shared.database import async_session_factory
from app.services.translation_service import TranslationService

PID = UUID("c12fa967-f989-4ed4-8e20-3ea62cb92e8f")
VID = UUID("3fccf815-f639-43c1-8a90-631336dc2d13")

async def main():
    async with async_session_factory() as db:
        v = await TranslationService(db).translate_variant(PID, VID)
        print("state:", v.state)
        print("scenes translated:", len(v.translation["scenes"]))
        print("model:", v.translation["model"], "endpoint:", v.translation["endpoint"])
        print("prompt version:", v.translation["prompt_version"])
        print("flags:", json.dumps(v.translation_flags, ensure_ascii=False, indent=2))
        s5 = next(s for s in v.translation["scenes"] if s["scene_index"] == 5)
        print("\n--- scene 5, THE DELIVERABLE (marker must be ABSENT) ---")
        print(s5["text"])
        print("\nmarker in deliverable:", "IVGS-TRANSLATION-FLAG" in s5["text"])

asyncio.run(main())
PY
  date -u

  echo
  echo "== AFTER =="
  $PSQL -c "SELECT language_code, state,
                   jsonb_array_length(translation->'scenes') AS scenes,
                   jsonb_array_length(coalesce(translation_flags,'[]'::jsonb)) AS flags
            FROM language_variants WHERE project_id='$PID' ORDER BY language_code;"
  echo
  echo ">>> EXPECTED: state = flagged (NOT complete, NOT failed), 18 scenes,"
  echo ">>> at least one flag naming scene 5, and 'marker in deliverable: False'."
  echo ">>> The en-US row must be untouched and still pending."
  unset PGPASSWORD
)
```

**Report from this block:** the variant's state transition, the flag(s) captured
with their scene indexes, the elapsed time, and the confirmation that the
delivered text is free of the marker. Do not paste the whole Spanish transcript
into chat; it belongs in the report as an excerpt of scene 5 only.
