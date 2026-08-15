# WP-12-API-CLIENT — Centralise ad-hoc fetch(); guard token reads

| | |
|---|---|
| **Ledger** | P2.24 |
| **Tier** | A · **Track P** (worktree-safe; frontend only) |
| **Report** | `reports/WP-12-API-CLIENT-report_<YYYY-MM-DD>.md` |

## Objective

16 ad-hoc `fetch()` sites across 7 frontend files (plus the GPU-history call) bypass
`src/lib/api-client.ts`, each hand-rolling auth headers and error handling. Migrate
them; add a pre-commit hook blocking unprefixed `access_token` reads.

## Tasks

1. Enumerate the sites (grep, list in pass 1 with file:line — verify the count).
2. Migrate each to the centralized client, preserving observable behaviour
   (endpoints, error surfaces, loading states).
3. Pre-commit hook rejecting direct `access_token` localStorage/cookie reads outside
   the client module. Propose the hook wiring; do not enable a hook that blocks the
   operator without his approval.

## Scope

**In:** the fetch sites, `api-client.ts` (only if a call shape needs a small
extension), the hook. **Out:** UI behaviour changes; API changes; auth flow changes.

## Exit gate

`tsc --noEmit` clean; zero raw `fetch(` to IVGS API endpoints outside the client
(grep shown); the hook rejects a deliberate violation (demonstrated) and passes the
clean tree.
