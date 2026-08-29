# WP-IVGS-11 — Port the session close-out / start-up protocol

> ⚠ **RENUMBERED 10 → 11 on 2026-08-29, per this order's own §0 instruction.** `WP-IVGS-10`
> was already taken by the v7-contract / RULE-8 / stage-2-time-limits package
> (`reports/WP-IVGS-10-V7-CONTRACT-report_2026-08-29.md`). Next free number is 11.
>
> ⚠ **The report name in §0 below is AMENDED**, not followed as written: it named
> `2026-08-28_session_protocol_port.md`, which is MBCP's convention. `dev/CLAUDE.md` §12 is a
> FINAL operator ruling that reports here are `WP-<NAME>_<YYYY-MM-DD>.md`. Amending the order is
> what §12 instructs. Landed at `reports/WP-IVGS-11-SESSION-PROTOCOL-report_2026-08-29.md`.

## Operator-approved 2026-08-28 · Documentation only · node-01 only · Small

⚠ If WP-IVGS-10 is already taken in this repo's numbering, take the next free number, rename this
file to match, and say so in your report.

**Report:** this repo's reports directory, `2026-08-28_session_protocol_port.md`, written **as you
go**. Commit and HOLD — the operator pushes. Do not deploy, do not restart anything.

---

## §1 Why

**This repo's own board has been measurably wrong three times about the same row** — most recently
claiming a "held hygiene commit" that never existed (`v5.31.0-hygiene` is an image build ref, not a
tag, and `HEAD == origin/main`). Each time, the truth lived in reports and the index lied.

MBCP had the identical disease. It was cured on 2026-08-27 by **`dev/CLAUDE.md` §0 rules 5 and 6** —
a session **close-out** checklist run unprompted (evidence out of scratch, index row written, stale
documents bannered, `STATE AT SESSION END`, tree declared) and a session **start-up** reading order
(conventions → index → newest STATE → **the work order last, with suspicion**). On its first
execution it caught a real gap four prior close-outs had missed, and its author's own tally errors.

**IVGS gets the same protocol, adapted — not invented fresh.**

## §2 The work

1. **Read the source text**: MBCP repo, `dev/CLAUDE.md` §0 rules 5 and 6, at or after commit
   `654b7c5`. A checkout exists on `.51` at `/root/MBCP`; if you cannot read across machines, ask
   the operator to paste the two rules — **do not reconstruct them from this order's summary.**
2. **Port both rules into THIS repo's `dev/CLAUDE.md`**, in its existing voice and structure:
   - Adjust paths (`/opt/ivgs`, this repo's reports and workpackages directories, its board file).
   - The **index** rule 5 step 2 targets is whatever file serves as this repo's board /
     work-package ledger — name it explicitly in the ported text.
   - Keep the trigger word **`CLOSE OUT`** identical across both repos.
   - Keep rule 6's ordering identical, including *"the work order last, and with suspicion"* and
     *"reports carry what was measured; where a document and the machine disagree, the machine wins
     and both are bugs."*
3. **Fix the board while you are there**: correct the stale "held" row your own measurement
   disproved, and add the missing tag note for `f61029b` (mpeg4 pin, untagged) as a one-line item —
   **do not create the tag**; that is the operator's.
4. **Task 3 of the original applies here too: execute a `CLOSE OUT` against your own session as the
   proof.** If any ported step is awkward or impossible in this repo as written, **that is a defect
   in the port** — fix the text and report what you changed and why.

## §3 Not to do

- ⛔ Do not restructure this repo's `dev/CLAUDE.md` — add the two rules, touch nothing else.
- ⛔ Do not edit any workpackage or report except banners a genuine supersession requires.
- ⛔ Do not push, tag, deploy, or restart services.
- Do not paraphrase MBCP's rules from memory — port from the landed text.

## §4 Exit

One or two commits, HELD. Report states: the text as landed in this repo, what was adapted and why,
the board corrections made, and the results of running `CLOSE OUT` on yourself — including anything
the protocol caught.

*After this lands, the standard fresh-session start line works on both repos:*
**`Read dev/CLAUDE.md, then follow §0 rule 6.`**
