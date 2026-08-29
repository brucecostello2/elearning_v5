# AD-10 v1.1 — Model Transport
## Amendment: the engine field, value domains, and the output capability envelope
### Supersedes v1.0 for §3.1 only · 2026-08-27 · **Awaiting ratification**

> **NARROW DIFF.** This revision replaces **§3.1** and adds **§3.1a** and **§3.1b**. Every other
> section of v1.0 — §1, §2, §3.2–§3.4, §4, §5, §6 — carries unchanged and is not restated.

---

## §0 What changed, and why

Three things, two of them found by measurement on 2026-08-27.

| # | v1.0 | v1.1 | Evidence |
|---|---|---|---|
| **1** | §3.1's envelope table lists **eleven** fields | **`engine` is added.** It was mandatory on the wire and absent from the specification | A live export was rejected `422` on `engine`. **Four certificates blocked, three more models blocked before they exist.** The transport contract did not govern the field that broke transport |
| **2** | The **zero-reader prohibition** — no field without a named consumer | ⭐ **Its mirror: the value-domain rule** (§3.1a) | The 422 was not a missing field. It was a field whose **permitted values are enumerated independently on each side with nothing keeping them in step** |
| **3** | *(silent on what a model can produce)* | ⭐ **The output capability envelope** (§3.1b) | IVGS must know, **at project creation**, what geometries and frame rates a certified model can deliver — before a user picks one it cannot honour |

---

## §3.1 The certificate envelope — **REPLACES v1.0 §3.1**

Every exported certificate carries, at minimum:

| Field | Meaning | Absent means |
|---|---|---|
| `certificate_id` | the certificate's identity | **error** |
| `model_id` | the model certified | **error** |
| ⭐ `engine` | **the RUNTIME that served it** — never a model family (§3.1a) | **error** |
| `ivgs_stage` | the stage it is certified for | **error** |
| `tier` | prototype / production | **error** |
| `artifact_kind` | weights bundle vs engine identity (§2.2) | **error — never defaulted** |
| `weights_checksum` | the checksum of the thing `artifact_kind` names | **error if `artifact_kind` says weights** |
| `bundle_manifest_url` | where to fetch it, on a **publicly resolvable** base (§2.4) | **error if `artifact_kind` says weights** |
| `driving_mode` | which AD-07 §4.7.0 contract it was earned under, where applicable | **ambiguous evidence — rejected** |
| `request_constraints` | per-model operating limits (AD-07 §5.2), **including the output capability envelope** (§3.1b) | permitted; **absence is not a constraint of zero** |
| `quality_scores` | the gate's measurements, with their scorer versions | permitted; recorded as absent |
| `gate_version` | which gate issued it | **error** |
| `issued_at` / `revoked_at` / `revocation_reason` | lifecycle (§5) | `revoked_at` absent = active |

**The zero-reader prohibition, unchanged.** *No field is added to this envelope without a named
consumer on the IVGS side, specified in the same amendment that adds it.* `request_constraints`
remains the cautionary case: **ingested and stored since migration 0029 with zero readers.** §3.1b
names its first.

---

## §3.1a ⭐ NEW — The value-domain rule

> **A field with an enumerated value domain is a shared contract, not a local type.** Neither side
> may extend, narrow or reinterpret it alone.

**Why this exists.** On 2026-08-27 a certificate was rejected `422` because MBCP sent
`engine = "tts"` and IVGS's `ModelEngine` enum did not contain it. Nothing was broken on either
side in isolation: MBCP's runtime genuinely is named `tts`, and IVGS's enum genuinely did not list
it. **The defect was in the space between them, which no document governed.**

Four rules follow:

1. **`engine` names the RUNTIME, not the model family.** This is IVGS's own ruling
   (`ad01_ingest.py:52-62`, WP-46) — *"`animatediff` is the name of ONE MBCP model family, not of an
   engine."* MBCP is bound by it too: it must send the runtime that served the model, never the
   family.
2. **The domain is jointly owned.** Its authoritative source is **MBCP's set of adapter runtimes**;
   IVGS's enum is a mirror of it and must be kept in step.
3. ⛔ **A new MBCP adapter does not ship until its engine value exists on the IVGS side.** Adding an
   adapter is a cross-repo change. **Certifying a model whose engine cannot cross the seam produces
   a certificate that cannot be delivered** — which is what happened to Kokoro, XTTS-v2 ×3, and
   would have happened silently to `magihuman`, `humo` and `wan22_s2v`.
4. ⛔ **Neither side may work around a domain mismatch by mapping.** A `tts → kokoro` map on the
   sending side would make MBCP assert a model family in a runtime field, recreating the defect
   WP-46 fixed on the receiving side, and would unblock one model while leaving three blocked.
   **Extend the domain; never translate into it.**

**Known outstanding, ledgered not fixed:** IVGS's enum currently contains `coqui`, `kokoro`,
`animatediff`, `latentsync` and `sadtalker` — **model families, by rule 1's own reasoning.** They
are in live use, including a row rendering today. **Do not remove them**; they reconcile when both
domains are next compared under rule 2.

---

## §3.1b ⭐ NEW — The output capability envelope

**The requirement, from the operator, 2026-08-27:** when IVGS pulls a certified model, it must know
**what output settings that model can actually deliver** — so that at **project creation** a user is
offered only frame rates and geometries every selected model can honour, rather than discovering the
mismatch at render time.

**Named consumer, as the zero-reader prohibition requires:** IVGS's **project-creation flow** —
constraining the frame-rate and orientation choices offered to the user — and its **stage binding**,
refusing a model that cannot meet the project's declared output settings.

### Shape

Carried inside `request_constraints`. **Not a new envelope field** — this is what that block is for.

| Key | Meaning |
|---|---|
| `frame_rates` | the rates the model can produce |
| `geometries` | supported width × height, with any divisibility rule |
| `orientations` | landscape / portrait / square, **natively** — not by post-hoc rotation |
| `duration_seconds_max` | the longest clip proven at that geometry |

### ⛔ Measured versus declared — the rule that keeps this honest

**MBCP measures what a model DID produce on the cells it ran. That is not what it CAN produce.**
Benchmark once at 25 fps and you know it does 25; you have learned nothing about 30. **A capability
envelope built from one cell is one data point wearing a promise.**

Therefore every entry carries its **basis**, and the two are never merged:

| Basis | Meaning | Weight |
|---|---|---|
| `measured` | MBCP produced this and recorded it from the artifact bytes | **Evidence** |
| `declared` | the model's documentation claims it; MBCP has not produced it | **A claim, and labelled as one** |

**IVGS may offer a `declared` option, but must mark it unproven, and must record the divergence when
a render does not honour it.**

> **This is not a new discipline — it is the one migration `0076` already established.** MBCP
> separates `requested_resolution` from `effective_resolution` precisely because they diverge, and
> `run_result.py:55` records the case that proved it: **"certified artifacts record a 30 fps request
> while running at 25."** ⛔ **A capability envelope that cannot express that divergence would
> re-create the defect it exists to prevent.**

### Preconditions — this cannot ship yet, and the reason matters

1. ⛔ **`output_fps` is recorded on 6 of 212 `run_results` rows** — and on **neither** row backing
   the two live `talking_head` certificates. **A `measured` frame rate cannot be emitted for a row
   whose frame rate was never measured.**
2. **Output geometry recording landed 2026-08-27** (WO-MBCP-03 Phase 1: display extent, coded
   extent, rotation, orientation, per artifact). **Frame-rate coverage must reach the same standard
   before this block is populated.**
3. **An empty envelope must read as "not established", never as "unrestricted."** Absence of a
   constraint is not a constraint of zero — v1.0's rule, and it applies with force here.

---

## §4 What this amendment does not do

- It does **not** lift either §3.2 hold. `bundle_manifest_url` remains stored-and-not-honoured;
  `artifact_kind` remains change-controlled.
- It does **not** rule what frame rate IVGS's composition stage runs at. **That is an open question
  to IVGS** and it should drive any production frame-rate standard — the number belongs to the
  consumer, not to a round figure.
- It does **not** clean up the model-family values in `ModelEngine` (§3.1a, ledgered).

---

*v1.1 supersedes v1.0 for §3.1 only. Ratification records three operator decisions requiring their
own Appendix-G rows: the **`engine` envelope field**, the **value-domain rule** (§3.1a), and the
**output capability envelope** (§3.1b).*
