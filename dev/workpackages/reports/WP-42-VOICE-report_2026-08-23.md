# WP-42-VOICE — the garbled narration: diagnosis, fix, and the engine A/B

| | |
|---|---|
| **Run under diagnosis** | job `bd99fe37`, project `c12fa967-f989-4ed4-8e20-3ea62cb92e8f`, 18 scenes, stage `tts_audio` 2026-08-23 18:45:02→18:46:19 |
| **Artifacts** | 18 audio assets in SeaweedFS; draft banked at `/mnt/ivgs-shared/reference-run-2026-08-23/draft_720p_en-US.mp4` |
| **Verdict** | The audio is **acoustically clean**. It is the **wrong words**. 161 of 505 storyboard words never reach the listener. |
| **Ships** | `v5.6.9-voice` on all four nodes |
| **State** | Committed and **HELD**. Nothing pushed. No store binding changed. |

---

## 0. Executive summary

The operator heard "much of the voice is garbled" and the natural first suspicion —
sample-rate mismatch, a naive concat, clipping — is **wrong on every count**, with
numbers below to prove it. The container is clean, the concat is exact, the engine is
faithful.

What is actually broken is that stage 5 does not synthesize the narration. It
synthesizes an **LLM rewrite** of the narration, and it hands that rewrite to XTTS-v2
**with presentation markup still in it**. Measured against the banked storyboard by
WhisperX:

* **68.1% word retention.** 161 of 505 storyboard words are absent from the delivered
  audio; 85 words are spoken that the storyboard never contained.
* Per-scene retention runs **9.5% – 100%**. Five scenes are below 55%.
* The engine, called directly with the same parameters and the storyboard text,
  returns **100%**.

The divergence point is `_optimize_narration_text` plus the prompt that drives it.

---

## 1. TASK 1 — What "garbled" is, in signal terms

### 1.1 What is NOT wrong (each ruled out with numbers)

| Suspicion | Measurement | Verdict |
|---|---|---|
| Sample rate vs container header | All 18 assets: `fmt ` tag `0xFFFE`, 48000 Hz, 24-bit, 1 ch, block-align 3, byte-rate 144000. RIFF size == filesize−8 on all 18; declared `data` size == actual bytes on all 18. | **Clean** |
| Concat corruption | `-f concat -c:a copy` of the 18 assets reproduces **247.246 s**, the exact arithmetic sum of the parts, at 48000 Hz / `pcm_s24le`. Matches the reported `full_audio.wav` (247.2 s). | **Clean** |
| Scene ordering / drop-outs | Every scene located inside the draft by envelope cross-correlation: all 18 present, in `scene_index` order, r = 0.851 – 0.999, cumulative drift +0.00 s → +1.00 s over 247 s (AAC encoder delay). | **Clean** |
| Clipping | **Zero** clipped samples across all 18. Peak −0.000265 dBFS with a peak *count* of 2; RMS ≈ −16 dB. | **Clean** |
| Resampling artifacts | XTTS emits 24 kHz; the pipeline upsamples 2:1. Even-indexed samples are exactly the source samples (100% ≡ 0 mod 256), odd are interpolated (r = 0.9977 vs. linear interp). Voiced-frame spectrum above 16 kHz sits at **−110 dB** — the anti-imaging filter is working. | **Clean** |
| A new spectral defect | Voiced-band profile vs. the previously *accepted* June draft: 4–8 kHz −7.19 dB vs −7.11 dB; 8–11 kHz −13.27 dB vs −13.71 dB. Indistinguishable. | **Clean** |

### 1.2 What IS wrong

**(a) Content substitution — the dominant defect.**
WhisperX (`base`, node-04:9000) over all 18 stored assets, matched against the banked
storyboard with a token-level LCS:

```
 sc story_w  asr_w  kept  lost added retain%  ASR avg_logprob
  0      36     28    26    10     2    72.2   -0.073
  5      32     19    16    16     3    50.0   -0.123
  6      48     24    21    27     3    43.8   -0.042
 11      21     21     2    19    19     9.5   -0.132
 12      42     24    23    19     1    54.8   -0.028
 17       9      8     4     5     4    44.4   -0.241
TOTAL storyboard=505  spoken=429  matched=344
      retention=68.1%   dropped=161 words   added=85 words
```

The ASR `avg_logprob` of −0.015 … −0.251 says the recogniser is *confident*. The audio
is not slurred. It is clearly-articulated **different text**:

```
scene 11 STORYBOARD: This gives us 200 + 60, which equals 260, but we wrote it as 640
                     in the previous step, which is incorrect.
scene 11 DELIVERED : We made a mistake. The correct calculation is two hundred two
                     sixty. This equals two hundred sixty. Not six hundred forty.

scene  6 STORYBOARD: Now, let's add the two answers together. We have 92 and 320, but
                     since we are adding the results of multiplying 23 by 4 and 23 by
                     10, we should add 92 and 230, which was the result of multiplying
                     23 by 10, but that was also incorrect.
scene  6 DELIVERED : Let's add the two answers. We have 92 and 230. We multiply 23 by 4
                     and 23 by 10. Add 92 and 230 together.
```

**(b) Markup spoken as phonetic garble.** Where the rewrite carried markup, XTTS
articulated the markup:

```
scene 17 STORYBOARD: You've just learned how to multiply two-digit numbers.
scene 17 DELIVERED : You have learned to multiply HE2-digity numbers.
```

`HE2-digity` is the lowest-confidence segment in the run (−0.241). This is the audible
"garble" in the strict sense, and it is the tail of the same cause.

**(c) Timing damage, all downstream of (a) and (b).**

* **85 synthesized sentence-chunks against 36 storyboard sentences (+136%).** Coqui's
  synthesizer pads every chunk it makes with a fixed `[0] * 10000` — 0.4167 s at
  XTTS's native 24 kHz, measured here as 19939–19970 zero samples (0.4154–0.4160 s)
  at 48 kHz. Scene 14: 2 sentences → **9** chunks.
* **89.22 s of 247.04 s (36.1%) is below the voicing floor.** 36.6 s of that is the
  fixed chunk pad alone.
* Per-scene speaking rate against the storyboard narration spans **120 – 361 wpm**, a
  3.0× spread. 361 wpm (scene 6) is above the intelligibility ceiling for its word
  count — which is another way of seeing that half the scene was never spoken.
* Total audio overruns the storyboard budget by **+28.7%** (247.0 s vs 192 s), up to
  **+12.96 s** on a single scene.

**(d) Minor, real, but not the operator's complaint.** 522 sample-to-sample steps
> 0.35 FS (max 0.477 FS) across the 18 assets, clustered into ~1.6% of voiced time as
20–60 ms impulsive bursts. After the AAC encode into the draft this measures 0.3% —
identical to the accepted June baseline (0.3%). Noted, not chased.

**(e) Cosmetic spec claim.** The stored "24-bit" is packaging: 100% of even-indexed
samples are multiples of 256, i.e. the information content is 16-bit at 24 kHz. Both
engines confirm 24 kHz / 16-bit natively.

---

## 2. TASK 2 — The generation path, and the divergence point

### 2.1 The path

`tasks/stage5_voiceover.py` (header says "Stage 4"; the Celery task registers as
`tasks.stage4_voiceover.generate_voiceover_task`; all three names disagree and all
three are load-bearing) does, per scene:

1. `_optimize_narration_text()` — a vLLM chat call on the `transcript_refinement`
   binding, driven by `prompts/stage4_system.j2`, "optimising the narration for TTS".
   **The result is used verbatim. It is never validated, never length-checked, and
   never persisted.**
2. `CoquiSynthesisParams(text=…)` → `CoquiClient._synthesize` → `POST /tts_to_audio`.
   No chunking happens in the worker; splitting is entirely the engine's.
3. `AudioConverter.normalize_wav()` → ffmpeg `-ar 48000 -ac 1 -acodec pcm_s24le`.
4. `AudioValidator.validate(expected_duration=scene.duration_seconds)` — compared
   against the storyboard's **visual** budget, not the narration.
5. Upload; the `full_audio.wav` concat happens later, in
   `talking_head_task._concatenate_scene_audio` → `FFmpegClient.concat_audio`.

### 2.2 The prompt is the origin

`prompts/stage4_system.j2` as it stood asked the LLM for three things XTTS-v2 cannot
consume, because XTTS has no markup layer — it converts every character to speech:

| Instruction (old prompt) | What XTTS did with it |
|---|---|
| `"API (A-P-I)"` — "add pronunciation guidance in parentheses" | Speaks the parenthetical. The word, then its spelling. Source of `HE2-digity`. |
| `"Insert natural pauses using ellipsis (...)"` | An ellipsis is a **sentence boundary** to Coqui's splitter. Each one costs a fixed 0.4167 s of digital silence. |
| `"Mark words … with *asterisks*"` | Stray non-speech tokens in the grapheme stream. |

and, in the same breath, "Break long sentences … max ~15 words per sentence" — which
multiplies the chunk count, and therefore the pad, again.

### 2.3 The direct-call comparison (the isolating experiment)

node-04's XTTS called directly with **byte-for-byte the payload
`CoquiClient._synthesize` builds** (`coqui_client.py:201`) — `speaker_wav:""`,
`temperature 0.75`, `length_penalty 1.0`, `repetition_penalty 5.0`, `top_k 50`,
`top_p 0.85`, `speed 1.0` — and the **storyboard** text:

```
scene  0 PIPELINE (stored asset): retention= 72.2%  28 words  12.42s  logprob -0.073
scene  0 DIRECT   (same params) : retention=100.0%  36 words  12.53s  logprob -0.050
scene 17 PIPELINE (stored asset): retention= 44.4%   8 words   4.08s  logprob -0.241
         "You have learned to multiply HE2-digity numbers."
scene 17 DIRECT   (same params) : retention=100.0%   9 words   3.99s  logprob -0.085
         "You've just learned how to multiply two-digit numbers."
```

**The engine is faithful.** Same parameters, same engine, same node: 100% retention and
higher confidence. Everything lost is lost *before* the HTTP call.

> **DIVERGENCE POINT:** `tasks/stage5_voiceover.py::_process_single_voiceover` step 1 —
> the output of `_optimize_narration_text` is passed to the engine unvalidated and
> unsanitised, and `prompts/stage4_system.j2` instructs that output to contain markup
> the engine will speak.

### 2.4 Two engine-side findings, reported not fixed (no engine container changes)

* `coqui/server.py` accepts `temperature`, `length_penalty`, `repetition_penalty`,
  `top_k`, `top_p` in its request model and **never passes any of them to
  `tts_to_file()`**. Only `text`, `language`, `speed` and the speaker reach XTTS. The
  client's whole tuning surface is inert — including the `repetition_penalty=5.0`,
  which is 2.5× XTTS's own default and would have mattered if it had been applied.
* `speaker_wav` is always `""` (nothing populates `Stage4Input.speaker_wav_path`), so
  the server falls back to the built-in speaker `Claribel Dervla`. Synthesis succeeds;
  voice cloning has never been exercised. `CoquiSynthesisParams.speaker_wav` (bytes) is
  accepted by the dataclass and **never sent** — voice-clone audio is silently dropped.

---

## 3. TASK 3 — The fix

Worker code and params only. No engine container touched.

| # | File | Change |
|---|---|---|
| 1 | `ivgs-workers/utils/tts_text.py` *(new)* | `strip_tts_markup()` — removes parenthetical hints, `*emphasis*`, code fences; maps `...`/`…` and paragraph breaks to a comma so they stop being sentence boundaries. Idempotent; a no-op on clean narration. Plus `estimate_narration_seconds()` and `rewrite_within_tolerance()`. |
| 2 | `ivgs-workers/prompts/stage4_system.j2` | Rewritten. Explicitly forbids parentheses, asterisks, ellipsis, blank lines and preamble, and explains *why* ("the output is SPOKEN, not displayed"; each split costs 0.42 s). Breath groups widened to 15–25 words. Adds a ±30% word-count constraint. |
| 3 | `ivgs-workers/tasks/stage5_voiceover.py` | The optimiser's output is sanitised, then **refused** if its word count falls outside 0.70–1.35× the storyboard's; on refusal the original narration is synthesized. The storyboard narration is itself sanitised on the un-optimised path. |
| 4 | `ivgs-workers/tasks/stage5_voiceover.py` | `AudioValidator` is now given `estimate_narration_seconds(text)` instead of `scene.duration_seconds`. The storyboard budget is a layout number; it told us nothing about the audio (+28.7% overall). |
| 5 | `ivgs-workers/tasks/stage5_voiceover.py` | Records `synthesized_text`, `text_source` (`storyboard`/`optimised`/`optimised-rejected`) and `narration_estimate_seconds` on every result. The 2026-08-23 run persisted none of this, which is why this diagnosis needed ASR rather than a log. |
| 6 | `ivgs-workers/tasks/stage5_voiceover.py` | A failed `normalize_wav` now **fails the scene**. It used to fall through and upload the engine's raw 24 kHz output; the validator only *warns* on a rate mismatch, so that asset looked healthy and then met `-c:a copy`. |
| 7 | `ivgs-workers/clients/ffmpeg_client.py` | `concat_audio` probes every input and refuses a stream-copy concat unless `codec_name`, `sample_rate`, `channels` and `sample_fmt` all agree. New `audio_concat_profile()` helper. |
| 8 | `ivgs-workers/clients/kokoro_client.py` | **Kokoro had never worked.** Wrong route (`/synthesize` → HTTP 404; the engine serves `/tts_to_audio`), wrong payload (`speaker_id`), a language gate that rejected the `"en"` stage 5 actually passes it, and an `AudioResult(...)` built from four kwargs the dataclass does not define — a guaranteed `TypeError`. All four fixed; rate and duration now read from the WAV header. |
| 9 | `ivgs-workers/temporal_pipeline/payloads.py` | WP-41's mirrored `SceneVoiceoverResult` updated for the three new fields, keeping the payload-shape guard green. |
| 10 | `ivgs-infra/docker-compose.node04.yml` | `IVGS_KOKORO_URL: "http://ivgs-kokoro:5003"`. The ARCH-1 binding's shipped default is `http://node-05:8021` — a host this fleet does not have — and `build_provider` passes `binding.endpoint` to the client, so the constructor's `KOKORO_TTS_URL` fallback never applied. Without this, activating Kokoro in the GUI would fail on connect. |

### 3.1 Tests

`ivgs-workers/tests/test_wp42_voice.py` — **28 passed, 2 skipped** (the two skips need
real ffmpeg, absent on node-01's host; both were executed against real ffmpeg inside
the worker image, see 3.2).

* markup: parenthetical / asterisk / ellipsis / paragraph-break removal, idempotence,
  no-op on clean narration
* tolerance: the reference run's scene-6 drop (48→26 words) and scene-14 inflation
  (30→48) are both **refused**
* duration: judged against the narration estimate; asserts the storyboard budget is a
  different quantity
* prompt: pins that the template forbids what it used to request
* wiring: an optimiser returning `"Call the *API* (A-P-I) endpoint to begin...\n\nThen
  read the result."` results in **no** `*`, `(`, `)`, `...` or newline reaching the
  engine, and `text_source == "optimised"`; a dropping optimiser yields
  `optimised-rejected` and the **storyboard text** is spoken
* normalisation failure fails the scene and never uploads
* concat: uniform inputs copy-concat; mismatched sample rate raises before ffmpeg runs
* Kokoro: route, payload, language handling, and a usable `AudioResult`

`ivgs-workers/tests/test_stage4.py` — repaired. Three of its tests had been *erroring*
since ARCH-1 (they passed `coqui_client=` and patched `tasks.stage4_voiceover.*`, a
module path that does not exist), on the one function this WP changes. Now 5 passed.

### 3.2 The concat proof against real ffmpeg

Run inside the worker image, since a mock cannot prove what `-c:a copy` emits:

```
PASS uniform concat: sample_rate=48000 duration=4.000s   (1.5s + 2.5s, both 48k)
PASS mixed-rate concat refused: "refusing a stream-copy concat of non-uniform audio…"
OLD behaviour (unguarded copy-concat of 48k+24k): header says 48000 Hz,
    duration 2.250s — 3.000 s of audio described as 2.250 s
```

The old path silently replayed the 24 kHz half at double speed. On the 2026-08-23 run
all 18 inputs happened to match, so it did not bite; nothing guaranteed that.

### 3.3 Test suite

Full suite run **twice** (the budget), `TEST_DATABASE_URL` → `ivgs_reconciliation_test`.
Run 2, complete capture: **1305 passed, 72 failed, 53 skipped, 77 errors** in 208 s.

* **1 failure was mine**: `test_wp41_payload_shapes[SceneVoiceoverResult]` — WP-41 pins
  the payload field-for-field and I had added three fields. Fixed (item 9); that file
  now runs **65 passed**.
* **71 failures + 77 errors are pre-existing.** Reproduced identically at HEAD with the
  changes stashed: the worker/scheduler subset (28 failed / 98 passed, byte-identical
  both ways), `test_compliance_scanner` + `ivgs-api` subset (22 failed / 7 passed, both
  ways), and `test_talking_head_task::test_requires_at_least_one_audio_ref`. The
  `tests_system/integration/*` errors need live API/auth services. None touch a WP-42
  surface; the compliance/swallow scanner is unchanged by the new code.

An earlier attempt aborted at collection because `DATABASE_URL` pointed at `testdb` and
the conftest guard refused it — an environment note, not a run.

---

## 4. TASK 4 — The A/B for the operator's ears

Both engines given **byte-identical** text, through the **fixed** stage-5 path
(sanitise → synthesize → normalise to 48 kHz/24-bit/mono as the pipeline stores it).
Texts are verbatim from the banked storyboard of project `c12fa967`.

**Files — `/mnt/ivgs-shared/wp42-voice-ab/`**

```
xtts-v2_short_scene17_en-US.wav    XTTS-v2  (coqui, node-04:5002)   3.38 s
kokoro_short_scene17_en-US.wav     Kokoro   (node-04:5003)          3.23 s
xtts-v2_long_scene06_en-US.wav     XTTS-v2  (coqui, node-04:5002)  19.39 s
kokoro_long_scene06_en-US.wav      Kokoro   (node-04:5003)         19.05 s
ab_measurements.json               rates / durations / timings
README.txt                         the two sample texts, verbatim
```

**Measured**

| engine | sample | retention | ASR avg_logprob | silence | generation | speed |
|---|---|---|---|---|---|---|
| xtts-v2 | short (9 w) | 100.0% | −0.107 | 15.3% | 0.60 s | 5.65× RT |
| kokoro  | short (9 w) | 100.0% | **−0.063** | 24.4% | 2.23 s | 1.45× RT *(cold)* |
| xtts-v2 | long (48 w) | 100.0% | −0.028 | 18.7% | 3.33 s | 5.82× RT |
| kokoro  | long (48 w) | 100.0% | **−0.014** | 16.4% | **0.12 s** | **162.8× RT** |

Both engines emit 24 kHz mono natively. VRAM while resident: XTTS-v2 1823 MB,
Kokoro 318 MB.

### 4.1 Paste-ready fetch block

Run this on **node-01** (as `dev`), then pull with `pscp`:

```bash
mkdir -p /tmp/wp42-voice-ab && \
cp /mnt/ivgs-shared/wp42-voice-ab/* /tmp/wp42-voice-ab/ && \
chmod 644 /tmp/wp42-voice-ab/* && \
ls -la /tmp/wp42-voice-ab/
```

Then from the Windows box:

```
pscp dev@192.168.1.90:/tmp/wp42-voice-ab/* .
```

(Verified: the block runs clean and lands all six files.)

### 4.2 Recommendation — **Kokoro for en-US drafts; keep XTTS-v2 bound for anything else**

**Reasons.**

* *Quality (by proxy).* Identical 100% retention. Kokoro is ahead on ASR confidence on
  both samples (−0.014 vs −0.028 long; −0.063 vs −0.107 short) — the recogniser finds
  its articulation less ambiguous. The final call is the operator's ears; that is what
  the four files are for.
* *Speed.* 162.8× realtime warm against 5.8×. On this 18-scene job that is stage 5
  falling from ~77 s to a few seconds. The 1.45× cold number is first-call warm-up.
* *Stability.* 318 MB resident vs 1823 MB, no speaker-reference dependency (XTTS is
  silently running on the built-in `Claribel Dervla` anyway), and no sentence-splitting
  pad behaviour to fight.
* *Against.* Kokoro is **English-only**. §17.1 lists es / fr / de / zh-CN / ja / ar as
  targets, and XTTS-v2 is the only engine that serves them — plus it is the only one
  with voice cloning, if the reference-clip feature is ever wired up. Kokoro must not
  become the default for a non-English variant.

**NO STORE BINDING WAS CHANGED.** Activation is yours, in the GUI. Two things must be
true first (see §6).

---

## 5. Deploy evidence — `v5.6.9-voice`, WP-34 rules in full

Built from the repository root, `docker build` rc=0, image id
`sha256:41a2fd2eae9a7c2e6992190f81c43a1f586152f44879d673a2cf86017aa08329`.
(An earlier build `d5dc657…` was superseded by the payload fix; the artifact was
removed, its MANIFEST line deleted, and the image re-banked so the store holds exactly
one v5.6.9-voice line.)

**Rule 1 — registry off the deploy path.** Banked first to
`/mnt/ivgs-shared/image-artifacts/brucecostello2_ivgs-workers_v5.6.9-voice.tar.zst`
(`sha256sum -c` **OK**, `zstd -t` **OK**, 272345088 bytes, **1** MANIFEST line);
distributed by artifact copy + `docker load`. **GHCR push deliberately NOT done** — the
WP's own rule is "never push", and WP-34 makes the registry non-blocking. Flagged in §6.

**Rule 2 — presence gate before every `.env` write.** `docker image inspect` returned
`PRESENT id=sha256:41a2fd2e…` on nodes 02/03/04 before the tag was touched. Rollback
recorded on all four: `.env.bak-wp42-<ts>`, prior value `IVGS_WORKERS_TAG=v5.6.6-mediajoin`
on every node.

**Rule 3 — label-derived compose**, `--force-recreate --no-deps --pull never`, services
named explicitly, invoked with `--project-directory /opt/ivgs/ivgs-infra` and absolute
`-f` paths (a first attempt resolved the compose file against `/root` and failed; caught
by rule 4, re-run correctly).

**Rule 4 — real `$?`, and verification by CONTENT.** Every compose step wrote
`REAL_RC=0` from a real exit status, not a pipeline's. Markers confirmed **inside each
running container** — `strip_tts_markup`, `_AUDIO_CONCAT_KEYS`, `NO parentheses`,
`synthesized_text`, `tts_to_audio`:

```
node-01 ivgs-celery-default / -composition / -beat   WP42_MARKERS_OK
node-02 ivgs-celery-node02                           WP42_MARKERS_OK
node-03 ivgs-cogvideox-worker-node03                 WP42_MARKERS_OK
node-04 ivgs-celery-node04                           WP42_MARKERS_OK
```

Negative gates in the image: old prompt instruction absent, `/synthesize` route absent,
`audio_bytes=` kwarg absent, `"speaker_id"` present **zero** times as a payload key
(it survives only inside an explanatory comment). Prior-WP markers all still present:
`plan_frame_aligned_pieces`, `check_visibility_timeout`, `_MEDIA_JOIN_REPORT_LUA`,
`CheckpointWriteError`, `release_acquired_reservation`.

**Rule 5 — node-04.** `IVGS_LATENTSYNC_TAG=v5.2.7-h0` confirmed **before and after**
each of the node-04 recreates. `latentsync`, `comfyui-primary`, `coqui`, `kokoro`,
`whisperx` all still on their pinned tags with **unchanged uptime** — started, never
recreated.

**Rule 6 — secrets.** Only `^IVGS_[A-Z]*_TAG=` / `^POSTGRES_(USER|PASSWORD)=` narrow
greps; no value printed. vLLM reachability tested with the key taken from container env
and never echoed.

**Rule 7 —** no `ivgs-infra/.env*` committed. `docker-compose.node04.yml` *is* tracked
and *is* in the held commit.

**Fleet verification.** 5 workers online, same queue map as before —
`composition-worker@node01` (composition), `default-worker@node01`
(default/notifications/cleanup), `cogvideox-worker@node03` (gpu_video),
`celery-worker@node02` (gpu_llm), `image-worker@node04`
(gpu_image/gpu_tts/gpu_talking_head). All four nodes on `v5.6.9-voice`, all healthy.
Cross-node binding from the node-04 worker: `resolve_endpoint('vllm') →
http://node-02:8000`, authed `/v1/models` **HTTP 200**; `coqui → http://ivgs-coqui:5002`;
`kokoro → http://ivgs-kokoro:5003` (was `node-05:8021` before item 10).

**Live end-to-end proof from the deployed node-04 worker:**

```
sanitised text -> 'You have just learned how to multiply two-digit numbers'
   (input was: "You have just learned how to *multiply* two-digit (T-W-O digit) numbers...")
kokoro  OK  bytes=168044 rate=24000 dur=3.50s
xtts-v2 OK  bytes=164428 rate=24000 dur=3.42s
```

**Rollback.** Per node: restore `.env.bak-wp42-<ts>` and re-run the same compose
invocation. `v5.6.6-mediajoin` verified **still present** in each node's local image
store and in the artifact store — checked, not assumed.

---

## 6. Decisions needed / things you own

1. **Model activation (GUI).** Neither binding was touched. Before activating Kokoro,
   note that its `models` row has **`engine = 'coqui'`**, not `'kokoro'`. The enum
   contains `kokoro`. As the row stands, selecting "Kokoro" routes the job through
   `build_coqui` to `http://ivgs-coqui:5002` and you would be listening to XTTS-v2
   under Kokoro's name. That row needs correcting before the A/B result means anything
   in production.
2. **GHCR push.** `v5.6.9-voice` is banked and deployed but not in the registry, because
   this WP's rules say never push. Say the word if you want it pushed.
3. **Content quality is a Stage-2 problem, not a TTS one.** Even at 100% retention the
   narration this run is asked to speak contains lines like *"we should add 92 and 230
   … but that was also incorrect."* The storyboard is arguing with itself. The
   optimiser was, in its own destructive way, trying to fix that. Worth a separate WP.
4. **`repetition_penalty` and friends are inert** (§2.4). If you want XTTS tuning to do
   anything, `coqui/server.py` must forward them — an engine container change, out of
   scope here and gated by MBCP certificate provenance.

---

## 7. Fleet incident found in passing — GPU driver

Not part of the WP; found because Task 2 could not run.

`node-03` and `node-04` lost their NVIDIA drivers at **2026-08-23 22:43** — about four
hours after the reference run — to an unattended kernel upgrade. The installed
`linux-modules-nvidia-580-open-*` package covered `6.8.0-124` only; node-04 rebooted
into `6.8.0-138`, node-03 into `6.8.0-137`. Every GPU container exited 128 with
`nvidia-container-cli: initialization error: nvml error: driver not loaded`. `node-02`
survived because its driver had already moved to 580.173.02 in step with the kernel.

**node-04 — restored, on the operator's instruction** (option: install the matching
module, no reboot). `linux-modules-nvidia-580-open-6.8.0-138-generic` installed; this
pulled the stack **580.159.03 → 580.173.02**, matching node-02. `modprobe nvidia` +
`nvidia_uvm`; `nvidia-smi` reports *RTX PRO 6000 Blackwell, 580.173.02, 97887 MiB*. All
six GPU containers started on their pinned tags.

> **Consequence to record:** the model store's certified provenance for node-04's
> engines carries `gpu_driver_version: 580.159.03` under MBCP. That record is now stale
> for both node-02 and node-04. Re-certification is an operator action.

**node-03 is still down.** `cogvideox-server-node03` has been exited 128 for 23 hours;
its celery worker runs fine (it is the client, not the server). The authorisation I was
given named node-04, so I did not touch node-03. It needs
`linux-modules-nvidia-580-open-6.8.0-137-generic` — same trade, same provenance
consequence. Say the word.

---

## 8. Commit and HOLD — push block

Held commits on `main` ahead of `origin/main`: **1**.

```bash
cd /opt/ivgs
test "$(git rev-list --count origin/main..HEAD)" -eq 1 || { echo "REFUSING: expected 1 held commit, found $(git rev-list --count origin/main..HEAD)"; exit 1; }
git log --oneline origin/main..HEAD
git push origin main
```

Nothing was pushed by this work package.
