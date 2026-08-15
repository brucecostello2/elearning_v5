# WP-13-HYGIENE — Named-file hygiene batch

| | |
|---|---|
| **Ledger** | P3.6 + P3.15 |
| **Tier** | A · **Track P** (worktree-safe) |
| **Report** | `reports/WP-13-HYGIENE-report_<YYYY-MM-DD>.md` |

> ## ⚠ This package is the one where `git clean` destroys real work. NEVER run
> `git clean`, `git rm`, or any wildcard delete. Enumerate first; act on named
> files only; propose deletions of anything you are less than certain about.
> node-01 has held untracked SSOT documents and render artefacts with no other copy.

## Objective

Remove accumulated cruft: `.bak` files in `ivgs-workers/`, ~30 `.env.bak.*` in
`ivgs-infra/`, `/root` tarballs and stage leftovers, and the dead
`get_beat_schedule()` in `tasks/periodic_tasks.py` (P3.15).

## Method

1. **Enumerate pass (no changes):** `git status --untracked-files=all` + a listing of
   every candidate file with size, mtime, and whether tracked. Anything that is a
   document, render artefact, or is not on the named cruft list goes to a "propose
   only" table — the operator decides.
2. **Named deletions:** only files matching the cruft classes above, listed
   individually in the report BEFORE removal. `.env.bak.*` files may carry secrets —
   do not print their contents; report names and sizes only.
3. `get_beat_schedule()`: confirm nothing references it (grep across the repo,
   including compose/beat config), then remove.

## Scope

**In:** the named cruft classes; the dead function. **Out:** `ivgs-infra/.env.node01`
(never touch); the two untracked SSOT docs (operator commits them); anything in
`docs/`; anything you cannot positively classify.

## Exit gate

Named files absent; nothing else changed (`git status` diff before/after shown);
propose-only table delivered; repo builds/tests unaffected (state how verified).
