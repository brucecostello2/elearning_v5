# WP-33-MODELSTORE-PREP — Model Store truth, the 08-15 mystery, and the population plan

| | |
|---|---|
| **Ledger** | P1.4m (Model Store cannot bind 8 of 9 stages) + P1.4f (store hygiene). Blocks: deploy of WP-IVGS-0, all end-to-end verification, M2 exit evidence |
| **Tier** | B · **READ-ONLY on all live systems** — single unattended overnight session |
| **Report** | `reports/WP-33-MODELSTORE-PREP-report_<YYYY-MM-DD>.md` |
| **Nodes** | node-01 (repo + read-only DB/API). Read-only ssh to 02/03/04 (root@) permitted ONLY to confirm which engine containers are running and their served model names. |

## Unattended profile — binding

No operator overnight. Never block: record decisions needed and continue.
**HARD RULE: no writes to the live database, no Model Store mutations, no
registration, no approval, no state change of any kind — plan only.** Store
mutations are admin/GUI-only under AD-01.11 and require operator attestation;
this package PREPARES that work, it does not do it. Commit-and-HOLD only docs
and the report. A concurrent Track-S session may be working in this tree:
stage only your own explicit paths.

## Context

WP-IVGS-0's §7 (2026-08-22) measured: 13 models — 2 approved (both
talking_head), 10 candidate, 1 retired; no transcript_refinement model at
all; get_binding resolves for talking_head only, both tiers; 0 rows in
project_model_selections and model_node_availability. Yet the pipeline ran
end-to-end through all 8 stages on 2026-08-15 (WP-03: first 4K render). Both
facts are evidenced. Reconcile them.

## Task 1 — Full store truth (read-only)

Extend the WP-IVGS-0 §7 snapshot into a complete inventory: every row in
`models` (name, stage, state, tier, is_default, enabled, engine, endpoint,
created/updated timestamps), plus bindings, selections, node availability.
Include row history if an audit_log or updated_at trail exists. Plain table
in the report.

## Task 2 — The 08-15 mystery (definitive answer required)

How did stages 1-5 run on 2026-08-15 if their bindings cannot resolve today?
Establish which of these is true, with evidence:
  (a) the store's state changed since 08-15 (models approved then, since
      retired/disabled — check timestamps and any audit trail; correlate with
      the MBCP backfill and its 24 revocations, and with Model Store hygiene
      work);
  (b) the code path changed (binding resolution was optional/fallback-guarded
      at the 08-15 code version and is now mandatory — check git log/blame on
      stage1_transcript.py, shared/providers/factory.py, and the WP-02/
      v5.5.4-metrics arc; note the running containers still run PRE-WP-IVGS-0
      images, so what is deployed differs from HEAD);
  (c) some combination.
State plainly: is P1.4m a REGRESSION (something an operator action broke) or
NEWLY-EXPOSED TRUTH (the old code lied about what it ran)? This determines
whether anything needs un-breaking versus simply populating.

## Task 3 — Population plan (the deliverable)

For each of the 9 ModelStages, at prototype tier (and production where
sensible): which engine actually serves this fleet today (confirm live,
read-only: vLLM on node-02, ComfyUI/FLUX and CogVideoX on node-03, Coqui/
Kokoro/LatentSync/whisperx on node-04 — verify container names and served
model identifiers on the nodes, do not trust docs). Then, per stage:

- If a matching CANDIDATE row exists (from the MBCP backfill): what promotion
  to APPROVED requires — the exact GUI steps, and the attestation text +
  vetting reference the operator must enter (draft it for them).
- If no row exists (transcript_refinement at minimum): the full registration
  the operator must perform — every required field drafted (name, stage,
  engine, endpoint, capability tags, VRAM, license, source_url,
  weights_checksum if obtainable read-only from the serving node, tier,
  attestation draft). Flag any field that genuinely cannot be known without
  an operator decision.
- Set-default and enable steps, per stage and tier.

Order the plan so the pipeline becomes runnable stage-by-stage (1 first).
Validate each planned row against the real get_binding predicate
(is_default AND state=approved AND enabled, per factory.py at HEAD) so the
plan provably resolves once executed — show the check.

## Task 4 — Deliverables

1. The report (findings, evidence live-vs-inferred, the Task 2 verdict).
2. `dev/workpackages/WP-33-POPULATION-CHECKLIST.md` — the operator's
   step-by-step GUI checklist from Task 3, one action per line, in order,
   with attestation drafts inline. Written for a non-developer operator.
3. Ledger updates: P1.4m amended with the Task 2 verdict; anything new found.
Commit docs + report with the usual gate, HOLD, no push block.

## Exit gate

Task 2 answered definitively with evidence; the checklist exists and every
planned row provably satisfies the get_binding predicate; zero writes
performed against any live system.
