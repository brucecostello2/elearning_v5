# WP-19-VRAM-CONSUMER — Does ivgs-scheduler consume MBCP's declared VRAM figures?

| | |
|---|---|
| **Ledger** | S-7 / decision D-8 |
| **Tier** | B (investigation — answer, no code) · **Track P** |
| **Report** | `reports/WP-19-VRAM-CONSUMER-report_<YYYY-MM-DD>.md` |

## Objective

MBCP's `comfyui.py` carries **15 PROVISIONAL VRAM placeholder figures**. Decision
D-8: does `ivgs-scheduler` bin-pack from *declared* VRAM figures (from model specs /
the Model Store), or does it *measure* locally? The answer sets sequencing: if
declared figures are consumed, MBCP WP-A (the GPU smoke that makes them real)
becomes an **M4 prerequisite**, because the scheduler would be packing against
fiction on five nodes.

## Method

Trace the admission-control path in `ivgs-scheduler` source: where VRAM requirements
enter a scheduling decision, and the provenance of each input (request payload,
Model Store record, static config, live NVML/exporter query). Follow the data to its
origin — do not stop at the first variable name that sounds like an answer. Check
both the reservation/admission path and any capacity registration path.

## Scope

**In:** reading `ivgs-scheduler/` and whatever it calls; reading MBCP's export/spec
fields in the read-only clone for the producing side. **Out:** all code changes on
either side.

## Exit gate

The question answered **with `file:line` for every hop** in the chain, a clear
verdict (declared / measured / mixed, and under which conditions), and the sequencing
consequence stated: whether MBCP WP-A must gate M4. If the answer is "declared",
say so prominently — it changes the M4 plan.
