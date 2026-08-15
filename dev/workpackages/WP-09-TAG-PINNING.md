# WP-09-TAG-PINNING — Pin the scheduler tag; restore base-image digests

| | |
|---|---|
| **Ledger** | P2.11 + P2.30(c) |
| **Tier** | A · **Track P** (worktree-safe; disjoint files) |
| **Report** | `reports/WP-09-TAG-PINNING-report_<YYYY-MM-DD>.md` |

## Objective

`IVGS_SCHEDULER_TAG=latest` is the one unpinned tag in `ivgs-infra/.env` and violates
spec §19.5. Base-image `@sha256` digest pins were lost in `b933357`.

## Tasks

1. Pin `IVGS_SCHEDULER_TAG`. Ledger records `:v5.1.0` == `:latest` (same image ID) —
   **re-verify the image IDs match now** before pinning; if they have diverged, stop
   and report which is running.
2. Restore `@sha256` digest pins on base images in the Dockerfiles; pin live `v5.5.x`
   digests in compose where the convention applies. Derive digests from the running/
   pulled images, not from memory.
3. If `enforce_sha_tags.sh` (or equivalent) exists, make it pass; if not, propose one.

## Scope

**In:** `ivgs-infra/.env`, Dockerfile `FROM` lines, compose image references.
**Out:** any rebuild or recreate (operator deploys); tag bumps beyond the pin.

## Exit gate

No `:latest` anywhere in `.env` or compose; digest pins restored; the enforcement
check passes; verification is a grep the operator can re-run, shown in the report.
Zero behaviour change asserted with image-ID evidence.
