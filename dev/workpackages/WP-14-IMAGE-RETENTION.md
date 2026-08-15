# WP-14-IMAGE-RETENTION — GHCR retention policy; bcrypt/passlib pin

| | |
|---|---|
| **Ledger** | P2.30(a,b) |
| **Tier** | B · **Track P** (worktree-safe) |
| **Report** | `reports/WP-14-IMAGE-RETENTION-report_<YYYY-MM-DD>.md` |

## Objective

(a) 14+ stale GHCR tags each for api/frontend with no retention policy. (b) A
bcrypt/passlib version warning at startup from incompatible versions.

## Tasks

1. **Retention policy (document + tooling, not mass deletion).** Inventory current
   GHCR tags per image; author a retention policy (keep: currently-deployed, last N
   per image, anything referenced by compose/`.env` history); provide the cleanup
   commands or workflow for the operator to run. **Do not delete images yourself** —
   registry deletion is irreversible and the recovery policy depends on specific
   artefacts.
2. **bcrypt/passlib:** reproduce the warning, identify the compatible version pair,
   pin in the dependency file, verify the warning is gone and auth still works
   (password hash round-trip test).

## Scope

**In:** policy doc, cleanup tooling/commands, dependency pins, the round-trip test.
**Out:** executing registry deletions; base-image changes (WP-09); rebuilds beyond
what the pin verification needs — if a rebuild is required to verify, provide the
operator the block and mark the item conditionally closed.

## Exit gate

Policy documented with the tag inventory; operator-runnable cleanup provided;
startup warning gone (or the rebuild block provided); hash round-trip test passes.
