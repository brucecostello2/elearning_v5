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

Order matters. A05 → A06 → A07 (the long one) → A08 → A09 → A10, then N01-A and
N01-B on node-01.

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
  WANT_COMPOSE=c4f97159199a121470662a576819e115049abeabbc9c19ad6cd0a613a120eccf
  WANT_ENVEX=0c40c3487253bf44714249786119e68af383e3d4704aa197b58c81027d0fa969
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
  fi
  ls -l ivgs-infra/.env.node05
  echo
  echo "== the identity block, as it will reach the container =="
  grep -E '^(IVGS_NODE_|NODE_HOSTNAME|VLLM_MODEL_NAME|VLLM_SERVED_NAME|VLLM_MAX_NUM_SEQS|VLLM_REASONING_PARSER|VLLM_GPU_UTIL|VLLM_MAX_MODEL_LEN|HF_HOME)' \
    ivgs-infra/.env.node05
)
```

---

## A07 — the weights. **~29 GB. ALLOW 30–90 MINUTES.** Its own block, deliberately.

> **TIME WARNING.** This downloads roughly **29 GB** of FP8 safetensors from
> HuggingFace. On a domestic uplink it can take **well over an hour**. It is
> separated from every other step so that a slow or failed download costs
> nothing but itself, and so it can be re-run — `huggingface-cli download`
> resumes.
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
  docker run --rm -i \
    -v "$CACHE":/data/hf-cache \
    -e HF_HOME=/data/hf-cache \
    --entrypoint huggingface-cli \
    vllm/vllm-openai:cu130-nightly \
    download "$MODEL" --local-dir-use-symlinks False
  RC=$?
  date -u
  if [ $RC -ne 0 ]; then
    echo ">>> DOWNLOAD FAILED rc=$RC. Nothing was manifested. Re-run this block;"
    echo ">>> huggingface-cli resumes."
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
    find "$CACHE" -type f \( -name '*.safetensors' -o -name '*.json' \) \
      -printf '%s\t%p\n' | sort -k2 | while IFS=$'\t' read -r SZ F; do
        printf '%s  %12s  %s\n' "$(sha256sum "$F" | cut -d' ' -f1)" "$SZ" \
          "${F#$CACHE/}"
      done
    echo
    echo "# totals"
    find "$CACHE" -type f -name '*.safetensors' | wc -l | \
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

  for IP in 192.168.1.90 192.168.1.91 192.168.1.92 192.168.1.93; do
    sudo ufw allow from "$IP" to any port 8000 proto tcp comment 'WP-61 qwen vllm'
  done
  # Everything else is refused explicitly, so the rule set states the intent
  # rather than relying on a default that could be changed elsewhere.
  sudo ufw deny 8000/tcp comment 'WP-61 qwen vllm: fleet only'

  echo
  echo "== AFTER =="
  sudo ufw status numbered | grep -E '8000|To|--' | sed -n '1,30p'
  echo
  echo ">>> CHECK THE ORDER. ufw is first-match: the four allows must appear"
  echo ">>> ABOVE the deny. If they do not, delete and re-add with"
  echo ">>>   sudo ufw insert 1 allow from 192.168.1.90 to any port 8000 proto tcp"
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
  docker compose --env-file ivgs-infra/.env.node05 \
                 -f ivgs-infra/docker-compose.llm.node05.yml \
                 config 2>&1 | sed -n '/command:/,/^[^ ]/p' | head -20
  echo
  echo ">>> READ THE COMMAND ABOVE. It must contain, literally:"
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
    echo ">>> The image digest actually pulled, for the record:"
    docker inspect ivgs-vllm-qwen-node05 --format '{{index .RepoDigests 0}}' 2>/dev/null \
      || docker inspect vllm/vllm-openai:cu130-nightly --format '{{index .RepoDigests 0}}'
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
