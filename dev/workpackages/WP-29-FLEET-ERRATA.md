# WP-29-FLEET-ERRATA — Correct every fleet-hardware claim from measured values

| | |
|---|---|
| **Ledger** | New. Supersedes AD-02 Draft 3's node-06 characterisation; corrects spec v5.1 A3/A4 |
| **Tier** | B (observable) · **Track S**, before M4 |
| **Report** | `reports/WP-29-FLEET-ERRATA-report_<YYYY-MM-DD>.md` |
| **Sources** | WP-25 (node-05), WP-28 (node-06), WP-29 readings for nodes 02/03/04 |

## Why this exists

**Every document in the repo describes a fleet that does not exist.** Three independent
surveys measured the actual cards, and not one node matches its documentation. This is
the fourth instance of the class CLAUDE.md §4 warns about ("documents found
contradicting production") and the most consequential, because M4 provisioning, VRAM
budgets, model placement and role assignment are all derived from the wrong numbers.

## Measured fleet — this is the ground truth

Driver **580.159.03**, **CUDA 13.0**, compute capability **12.0** on every GPU node.

| Node | Documented | **Measured** | Source |
|---|---|---|---|
| node-02 | RTX 6000 Blackwell 96 GB | `NVIDIA RTX PRO 6000 Blackwell Workstation Edition`, **97887 MiB** | this package, 2026-08-15 |
| node-03 | RTX 6000 Blackwell 96 GB | `NVIDIA RTX PRO 6000 Blackwell Workstation Edition`, **97887 MiB** | this package |
| node-04 | **RTX 5000 Pro Blackwell 48 GB** (spec) | `NVIDIA RTX PRO 6000 Blackwell Workstation Edition`, **97887 MiB** | this package |
| node-05 | **RTX 5080 16 GB** | `NVIDIA RTX PRO 5000 Blackwell`, **48935 MiB** | WP-25 |
| node-06 | **RTX 6000 Blackwell 96 GB** | `NVIDIA GeForce RTX 5080`, **16303 MiB** | WP-28 |

Note node-04: CLAUDE.md §2 says 96 GB and is **right**; the functional spec table says
48 GB and is **wrong**. The two have disagreed and nobody noticed.

## Provenance — record this, it explains the drift

Supplied by the operator, 2026-08-15:

1. The **July RTX 6000 96 GB** purchase was installed in **node-03**.
2. node-03's displaced **RTX PRO 5000 48 GB** moved to **node-05**.
3. **node-06** received the **GeForce RTX 5080 16 GB** (the card the documents place in
   node-05).

Every document was written against the *plan*, and the plan changed. Record the chain
so the next reader can tell drift from error.

## Consequence — the M4 roles for node-05 and node-06 invert

AD-02 Draft 3, and spec v5.1 amendments **A3 and A4** which this agent applied under
WP-15, both make **node-06** the second CUDA video node and primary compositor on the
strength of a 96 GB card it does not have. With 16 GB it cannot run CogVideoX.

**Corrected roles:**

| Node | Card | M4 role |
|---|---|---|
| **node-05** | RTX PRO 5000 48 GB | **Second video generation node** (`gpu_video`) **+ image/LLM fallbacks** |
| **node-06** | GeForce RTX 5080 16 GB | **Compositor + Remotion** (`composition`), motion graphics, Ken-Burns L2 fill |

This is the reverse of what spec v5.1 §2.2/§2.4 and AD-02 Draft 3 currently say.

## Tasks

1. **Correct every fleet-hardware claim** from the measured table:
   - `README.md` — GPU allocation table (`:24`), driver note (`:26`), Proxmox table
     (`:37`), node roles (`:48`). WP-25 additionally flags `README.md:23,36,47`.
   - `dev/CLAUDE.md` §2 — node-04 line, and §2/§7's node-06 "swapped to RTX 6000 96 GB"
     which is now known false.
   - `docs/ivgs_v5_functional_spec.md` — Tables 2-2, 2-3, 3-1, 3-2, the §3.1/§3.2
     driver notes, §2.4 compose stacks, Appendix B Table B-2 VRAM allocation.
     **Note spec v5.1's A3/A4 text was applied by WP-15 and is among what must change.**
   - `IVGS_v5_Master_Sequence_Plan_to_Production.md` — M4 fleet description.
   - `docs/IVGS_v5_Addendum_AD-02_Node_Specialization.md` — Draft 3's node-06
     characterisation. Draft 3 is *historically* correct about the Intel→CUDA swap;
     it is the 96 GB claim and the role assignment that are wrong. **Amend, do not
     rewrite history** — the same discipline WP-15 applied.
   - Driver/CUDA floors: the spec says "570.x or later, CUDA 12.4+". Measured is
     580.159.03 / CUDA 13.0. Satisfies the floor, but state the measured values.
2. **Fold in WP-25's open items** — O-1 (re-scope node-05 for 48 GB, not 16 GB;
   `README.md:23` and `ivgs-workers/configs/media_generation.yml:50-51` size the
   fallback queues for 16 GB), O-2 (weights on `/data/models` local vs `/mnt/models`
   NFS), O-3 (`default-runtime: nvidia` with no VRAM partitioning — every CUDA
   container sees the whole card), O-4 (40 GiB scratch).
3. **Fold in WP-28's N-2** and its documentation-contradiction section.
4. **Prometheus targets** — `ivgs-infra/monitoring/prometheus/prometheus.yml:95-101,
   145-…` scrapes only `node-01:9100` for node-exporter and only `node-02:9400` for
   `nvidia-gpu-exporter`. Nodes 03–06 are unmonitored. Add them.
5. **The ffmpeg-command logging gap** (WP-03 §2.2): `cmd_head` is logged only on
   failure, so a successful render's executed invocation cannot be audited. The WP-03
   brief required reading it from logs and that proved impossible. Log the invocation
   on success too, at debug or info.

## Constraints

- **Measured values only.** Every corrected figure must trace to an `nvidia-smi`
  reading quoted verbatim in a report. Do not carry a number from one document to
  another.
- Do not delete the historical record. AD-02 Draft 3 and spec v5.1 record real
  decisions taken on the information then available; amend with dated errata.
- node-05 and node-06 are **not provisioned for production** — this package corrects
  documents, it does not stand nodes up.

## Scope

**In:** the documents listed above, the Prometheus scrape config, the ffmpeg logging
gap, and the ledger entries for WP-25's O-1..O-4.
**Out:** provisioning; compose role changes for node-05/06 beyond what the corrected
roles require in documentation; any code except the ffmpeg logging line.

## Exit gate

`grep` across the repo returns no fleet-hardware claim contradicting the measured
table; every corrected figure cites its `nvidia-smi` source; node-05/06 M4 roles read
as inverted from AD-02 Draft 3 with the provenance chain recorded; Prometheus scrapes
node-exporter and the GPU exporter on every GPU node; a successful render logs its
ffmpeg invocation, demonstrated on one render.
