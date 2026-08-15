# IVGS banked reference output - 2026-08-15

**Purpose.** The verification target for the M3 Temporal migration (ledger WS-T.3).
After cutover, the same inputs must reproduce these artefacts. Deviation is a
migration defect until proven otherwise.

**Produced by** WP-03-STAGE8-VALIDATION on 2026-08-15, node-01 and node-04.
Report: `dev/workpackages/reports/WP-03-STAGE8-VALIDATION-report_2026-08-15.md`.

---

## READ THIS FIRST - THIS REFERENCE IS NARROW

**It does NOT cover Stages 1, 2 or 3.** It covers Stage 6 (talking head),
Stage 7 (draft) and Stage 8 (final, both profiles). Four limitations, all material:

1. **Stages 1 and 2 were never run.** The transcripts and storyboard scenes are
   June's, reused. `gpu_llm` had no ARCH-1-capable worker: node-02/03 ran
   `v5.4.7-h0`, which predates the provider factory.
2. **Stage 3 was never run.** The scene images and video clips are June's.
3. **Stage 4's manifest was NOT used.** A freshly built manifest is malformed -
   it binds audio assets as background layers (register instance 15). This
   reference was produced against the **June manifest**, job
   `79b90f48-8c14-4884-9364-6957cf77ac5b`, which has one background layer per
   scene. A Stage-4 run against today's asset set does not reproduce it.
4. **Stage 5 was never run.** `voiceover_tts` has no approved default model, so
   the stage raises `SelectionError`. The audio is June's.

**Therefore this reference is superseded the moment a genuine Stages 1-8 run is
possible.** WP-26-MODEL-STORE and WP-27-MANIFEST-BUILDER exist to make that
possible; their completion re-banks this file. **The full reference must exist
before the Temporal migration's verification gate** - this narrow one does not
satisfy that gate on its own.

---

## Source

| | |
|---|---|
| Project | `2B-scenes2-222906` |
| Project ID | `3814f845-4668-496b-a88a-53fea95897c2` |
| Scenes | 6 |
| Reference clip | asset `32c2e4d8-e2c5-4170-8fb7-7ab02e8b9981`, fid `5,59e57b9d2c`, 12,113,799 bytes |
| Manifest used | `b636fe87-5adf-4288-8c4f-1089f36ad001` (job `79b90f48-...`), `locked`, `total_duration_ms` 115000 |
| Worker image | `ghcr.io/brucecostello2/ivgs-workers:v5.5.2-orch6` (revision `09e4212`) |
| Repo | `134c34f` |

Note the manifest's `total_duration_ms` of 115000 is the **stale 115 s storyboard
estimate**, not the real 214.88 s narration (AD-03 S11.2). The pipeline anchors on
probed audio, so the outputs are correct despite it.

## Model selections in force

| Stage | Stage key | Model | Engine | Endpoint | Selected via |
|---|---|---|---|---|---|
| 6 | `talking_head` | `latentsync-alt` | `latentsync` | `http://latentsync:7860` (node-04) | `is_default` |

Every other binding stage had **no approved default** at the time of this run, which
is why Stages 1-5 could not be re-run. Recorded so a later comparison knows what was,
and was not, selection-driven.

## Artefacts - storage is fid-based on the SeaweedFS volume server

`assets.seaweedfs_path` is metadata only and the filer is empty. Fetch by fid:
`http://192.168.1.90:8080/{fid}`.

| Stage | Asset ID | fid | Bytes | sha256 |
|---|---|---|---|---|
| 6 talking head | `b45b19ce-c12a-459f-bdf0-1dcae7625a4e` | `5,5b66d602e3` | 50,104,735 | `5a6e89a9fecd4d4b295b28d0cabf4f01e3b8a0dd29d10fd327f23da89bbde6a9` |
| 7 draft 720p | `f78eb063-6f5f-4591-a668-967241306bea` | `1,5f616980b9` | 7,476,242 | `014a9044dde0330bf2843afc9fa27d79c4482769e03200b764daed87d7d77efe` |
| 8 final 1080p | `9007b2cf-6b55-4cd5-bc66-8226811f7e60` | `3,60dc085e2d` | 18,502,995 | `f90466161dd79904cade8ef72a916ba0491ee0131034cfa4d073d5bfcf61dc3c` |
| 8 final 4K | `d23ee9d8-cc40-4a43-9b4e-ad0f1d2b490a` | `7,617bb3baf9` | 31,149,351 | `a3a395a6c9c108b11b153860b409c6b414bd96114b020ab8cc92c46bc2e8a581` |

## Measured properties

| Property | 7 draft | 8 final 1080p | 8 final 4K |
|---|---|---|---|
| Duration | 214.938 s | 215.07 s | 215.067 s |
| Resolution | 1280x720 | 1920x1080 | **3840x2160** |
| Video codec | h264 | h264 (High) | **hevc (H.265)** |
| Pixel format | - | - | **yuv420p10le** |
| Frame rate | 30 | 30 | 30 |
| Video bitrate | ~153 kb/s | ~506 kb/s | **939,325 bps** |
| Audio | AAC 48 kHz stereo | AAC LC 172 kb/s | AAC 210,408 bps |
| Overall bitrate | - | - | 1,158,684 bps |
| Corruption checks | 6/6 | 6/6 | 5/5 at render; **6/6** re-validated with the new bitrate check |

4K measured directly with `ffprobe` on the downloaded artefact, 2026-08-15 12:22 UTC.
The 4K profile had **never been exercised before this run** (AD-03 S13).

## Behaviour-neutrality evidence

Three outputs reproduced **byte-identically** against pre-change references, proving
the ARCH-1 promotion (WP-02) changed no rendered output:

| Artefact | Evidence |
|---|---|
| Stage 6 head | sha256 identical across 3 runs; `reference_count` 1 -> 3 by dedup |
| Stage 7 draft | deduped onto June's `f78eb063`; `reference_count` -> 2 |
| Stage 8 1080p | deduped onto June's `9007b2cf`; `reference_count` -> 3 |

The 4K final is the only genuinely new artefact (`reference_count` 1).

## Known-open items visible in this reference

- **Head A/V drift 0.6187 s** - `lipsync_duration_mismatch`, video 215.5 s vs audio
  214.881 s. AD-03 S10 criterion 3, owned by WP-04-FRAME-ALIGN. Present here, not fixed.
- **GPU reservations fail open** - `"No alive GPU nodes available in the fleet"`.
  Register instance 4 / ledger P1.3. Every render here ran without a reservation.
- **Checkpoint writes 405** - ledger P1.2. No checkpoint row was written.

## How to re-verify

```
curl -sS "http://192.168.1.90:8080/7,617bb3baf9" | sha256sum
  expect a3a395a6c9c108b11b153860b409c6b414bd96114b020ab8cc92c46bc2e8a581
```

Repeat per fid. A mismatch means either the stored bytes changed or the pipeline
no longer reproduces them; distinguish before concluding.
