# WP-15-DOCS-APPLY — Apply the four outstanding amendment documents

| | |
|---|---|
| **Ledger** | Handoff §1b / §6.3; closes **ADR-003** |
| **Tier** | B (observable) · **Track S #1** |
| **Report** | `reports/WP-15-DOCS-APPLY-report_<YYYY-MM-DD>.md` |
| **Next** | WP-00-DETECTOR |

## Objective

Four documents in `docs/` are amendment INSTRUCTIONS whose edits were never made to
their base documents. Until applied, the base documents contradict their own
amendments, and the base document is the one a reader finds first. Apply all four.

## The four amendments

| Amendment doc (in `docs/`) | Applies to |
|---|---|
| `IVGS_v5_Functional_Spec_Amendment_v5.1.md` — ten amendments A1–A10 | `docs/ivgs_v5_functional_spec.md` |
| AD-01 Draft 2 amendment | `docs/IVGS_v5_Addendum_AD-01_Model_Management.md` |
| AD-03 v0.4 amendment (replaces §10–§11, adds §13–§15) | `docs/IVGS_v5_Addendum_AD-03_Composition_Fidelity.md` |
| AD-04 v3.1 amendment (replaces §3.19–§3.21, adds §3.22–§3.24) | AD-04-v3.0 — **see prerequisite below** |

**AD-04 prerequisite:** v3.0 exists only as an untracked file on node-01
(`docs/IVGS_v5_Addendum_AD-04-v3_…md`, ~451 lines). Committing it is an operator task.
If it is still untracked: apply the amendment to the on-disk file, scan the result for
tokens and IP literals, report, and flag for operator commit. Also flag the stale
v0.1 AD-04 file for deletion per the amendment's repository-action section — do not
delete it yourself.

## Method

- Each spec amendment gives exact current text and its complete replacement. Locate
  each anchor, verify the current text matches BEFORE replacing, apply in order.
- The remaining ~8,000 spec lines are untouched. **Do not regenerate any document.**
- Work through the verification checklist inside the v5.1 amendment doc itself.
- Update ADR-003's status to Resolved by spec v5.1 and ADR-004's to Superseded by
  ADR-006 if not already done.
- Propose (do not execute) the commit, message per the amendment doc:
  `spec(v5.1): orchestration migration, node-06 CUDA, stage-count errata`.

## Scope

**In:** the four base documents above; ADR status lines; `README.md` and AD-02 only
where they carry `intel b70` / `oneapi` references. **Out:** all code; all other docs;
any deletion.

## Exit gate

- `grep -c "Seven-Stage" docs/ivgs_v5_functional_spec.md` returns **0**
- `grep -ril "intel b70\|oneapi" docs/ README.md` returns nothing except the
  amendment/errata documents that quote the old text historically — list any such
  hits in the report with justification
- Spec version header reads **v5.1 — 2026-08-14**; §6.4 carries the transitional
  note (the doc must NOT claim Temporal is live before M3 cutover)
- Glossary retains Celery entries marked withdrawn (not deleted)
- `git status` shows only the intended files modified; no secrets staged
- Every checklist item in the v5.1 amendment ticked in the report
