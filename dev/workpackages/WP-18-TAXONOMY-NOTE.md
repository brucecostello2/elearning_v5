# WP-18-TAXONOMY-NOTE — Document the IVGS/MBCP stage-taxonomy divergence

| | |
|---|---|
| **Ledger** | S-2 (cross-system register) |
| **Tier** | B · **Track P** (docs only) |
| **Report** | `reports/WP-18-TAXONOMY-NOTE-report_<YYYY-MM-DD>.md` |

## Objective

IVGS has **8 pipeline stages**; MBCP has **9 capability stages**
(`/opt/MBCP/mbcp_core/enums.py` — read it, do not trust this brief). MBCP's
image/video/animation generation all map to IVGS Stage 3; MBCP's `composition`
collapses IVGS Stages 4, 7 and 8; MBCP's `translation` is not an IVGS pipeline stage.
The AD-01 selection key `(stage, tier)` uses **MBCP's** taxonomy. Undocumented, this
is a standing trap for every future session (it nearly misdirected the ORCH-6 fix).

## Tasks

1. Read `mbcp_core/enums.py` in the read-only clone at `/opt/MBCP` and build the
   authoritative mapping table from the actual enum values.
2. Add the note + mapping table to AD-01 at §AD-01.16 (per the amendment's
   placement) and to the functional-spec glossary. **Sequence after WP-15** if the
   AD-01 amendment is not yet applied, so you edit the amended document.
3. Cross-reference from `dev/CLAUDE.md` §11 if its wording needs tightening (it
   already carries a short version).

## Scope

**In:** AD-01, the glossary, at most a CLAUDE.md cross-reference. **Out:** any code;
any enum change on either side; MBCP repo files (read-only clone — MBCP commits
happen on `.51`, never node-01).

## Exit gate

Both taxonomies documented with the mapping table, derived from the real enum file
with `file:line`, present in AD-01 §AD-01.16 and the glossary.
