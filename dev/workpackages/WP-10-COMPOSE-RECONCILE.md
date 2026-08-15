# WP-10-COMPOSE-RECONCILE — Reconcile base.yml vs node01.yml; fix monitoring net

| | |
|---|---|
| **Ledger** | P2.29 |
| **Tier** | B · **Track P** (worktree-safe) |
| **Report** | `reports/WP-10-COMPOSE-RECONCILE-report_<YYYY-MM-DD>.md` |

## Objective

`docker-compose.base.yml` and `docker-compose.node01.yml` disagree on SeaweedFS
version (3.80 vs 3.71) and volume naming (underscore vs hyphen). Invoking the wrong
set has **twice** recreated infrastructure containers against wrong definitions.
Separately, `docker-compose.monitoring.yml` references the non-existent external
network `ivgs_default` (real: `ivgs-infra_ivgs-net`) — latent only because deploys
use `--no-deps`.

## Tasks

1. Derive the authoritative invocation from running-container labels (runbook §3.1).
2. Determine what, if anything, actually uses `base.yml`. Recommend reconcile or
   delete, with evidence. If delete: propose it — do not `git rm` yourself.
3. Fix the monitoring network reference to the real network.
4. Verify with `docker compose <derived set> config` (parse only — no `up`).

## Scope

**In:** the compose files named above. **Out:** any container recreate (operator, per
runbook §3.3 with `--no-deps`); volume changes; service definition changes beyond the
reconciliation.

## Exit gate

Deriving the invocation from labels matches the tracked files; `compose config`
parses clean for the corrected set; the base.yml recommendation is evidenced. The
operator performs the one verification recreate — provide him the exact node-labelled
block, wrapped in `( ... )`, with `--no-deps`.
