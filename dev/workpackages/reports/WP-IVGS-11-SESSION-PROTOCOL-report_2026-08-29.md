# WP-IVGS-11 — Port the session close-out / start-up protocol

**Report, 2026-08-29 · node-01 only · documentation only · commit and HOLD**

---

## STATE AT SESSION END

| | |
|---|---|
| **Done** | MBCP §0 rules 5 and 6 ported into `dev/CLAUDE.md` as a new §0, additive (68 insertions, **0 deletions**). Board corrected. `CLOSE OUT` executed against this session and it caught a real defect |
| **Mid-way through** | Nothing |
| **Package now stale because of this report** | **§0's report name** (`2026-08-28_session_protocol_port.md`) — amended, see §2. **§0's number** (WP-IVGS-10) — renumbered to 11, see §1. **§2.3's "held row"** — the row named a *dangling* SHA, not the stale row the package predicted; see §4 |
| **Not yet written down anywhere else** | An image tag is not a git tag — three tag-shaped strings on the board name deployed images that exist as no git tag. Now in §0 rule 5 |
| **Held** | **3 commits** — `70058b9` (WP-IVGS-10 addendum 2, pre-existing) plus the two written here. Nothing pushed; see §7 |

**Verified live vs inferred (`dev/CLAUDE.md` §12):**

- **Executed:** every git measurement (`git tag --list`, `git merge-base --is-ancestor`, reflog,
  `git log origin/main..HEAD`); the MBCP source read from fetched refs.
- **Read, not executed:** nothing in this package requires execution — it is documentation only.
  **No test suite was run and none needed to be: no code file was touched** (`git status
  --porcelain` filtered on code extensions returns empty).

---

## §1 The renumber

⚠ **WP-IVGS-10 was already taken**, by the v7-contract / RULE-8 / stage-2-time-limits package —
`reports/WP-IVGS-10-V7-CONTRACT-report_2026-08-29.md`, plus its appendix
`reports/WP-IVGS-10-SEAM-ANSWERS-report_2026-08-29.md`. Existing IVGS numbering is
`WP-IVGS-0, 03, 04, 06, 07, 08, 09(+b-f), 10`. **Next free number is 11.**

Done as the package's own §0 instructs: the order file is renamed
`dev/workpackages/WP-IVGS-11_Session_Protocol_Port.md` and carries a banner recording the
renumber and the reason.

## §2 The report name — the order was AMENDED, not followed

The package asked for `2026-08-28_session_protocol_port.md`. **That is MBCP's convention.**
`dev/CLAUDE.md` §12 is a **FINAL operator ruling** (2026-08-22, *"this does not flip again"*)
that reports here are `WP-<NAME>_<YYYY-MM-DD>.md` under `dev/workpackages/reports/`, and it says
in as many words: *"If an incoming work order names `dev/workorders/`, amend the order, do not
create the directory."* **Amending is the instructed response.** Landed as
`WP-IVGS-11-SESSION-PROTOCOL-report_2026-08-29.md`; the order is bannered.

## §3 The port — what landed, and what was adapted

**Source read from the landed text, not reconstructed** (§2.4 of the package forbids
reconstruction). ⚠ **The source was not readable when this package started.** `/opt/MBCP`'s
fetched refs were at `211afbf` (2026-08-27 19:39) and `654b7c5` **was not a valid object**;
MBCP's §0 there had only **four** rules. A `git fetch origin` — GitHub, **not `.51`** (`git
remote -v` confirms `https://github.com/brucecostello2/MBCP.git`) — moved `origin/main` to
`ddb3191` and `654b7c5` resolved. `/opt/MBCP` stays a read-only reference clone (§11): refs were
updated, **no checkout, no commit, `.51` never contacted.**

Landed at `dev/CLAUDE.md` **§0**, inserted before §1, matching MBCP's own placement and the
closing line *"Read `dev/CLAUDE.md`, then follow §0 rule 6."*

| MBCP text | IVGS adaptation | why |
|---|---|---|
| Rule numbers **5** and **6** | **Kept identical** | *"follow §0 rule 6"* must mean the same thing in both repos. Stated explicitly in the ported preamble |
| MBCP rules 1-4 | **Not ported** | Package scope is rules 5 and 6. Rules 1-4 are MBCP-local (its report path, its `ci.sh` gate); this repo's equivalents are §12 and §1 |
| `dev/workorders/reports/YYYY-MM-DD_name.md` | `dev/workpackages/reports/` | §12, final ruling |
| `/root/MBCP` | `/opt/ivgs` | this repo |
| *"an album… in `reports/` (~1 MB)"* | `dev/workpackages/reference/` | where this repo actually banks evidence |
| `dev/workorders/WORK_PACKAGES.md` (the index) | **`dev/DEVELOPMENT-STATUS.md`** — named explicitly, as §2.2 required | see §3.1 — **this is the one place the port genuinely diverges** |
| *"where the order and the machine disagree… (§3)"* | **(§4)** — *Ground truth beats documentation* | IVGS's §4 is the analogue of MBCP's §3 |
| Rule 6 reading order: *"§3 defect catalogue, §4 collision discipline"* | *"§3 never-touch, §4 ground truth, §7 known traps"* | the real IVGS sections |
| *"use `sudo -n` with an assert-guarded replace (§7)"* | principle kept, **section reference dropped** | this repo has no §7 sudo convention; inventing one would be a second truth |
| — | ⭐ **added:** *"an image tag is not a git tag"*, with the three live examples | measured this session; see §4 |
| — | ⭐ **added to step 5:** *"what is held (§1: it is always held)"* and the held-count clause | §1 makes holding unconditional here; MBCP's phrasing assumes a choice |

Kept verbatim, as §2.2 required: the trigger word **`CLOSE OUT`**; rule 6's ordering including
***"your work package last, and with suspicion"***; and ***"reports carry what was measured;
where a document and the machine disagree, the machine wins and both are bugs."***

### §3.1 ⛔ THE ONE REAL DIVERGENCE — rule 5 step 2 has no true target in this repo

MBCP indexes into `dev/workorders/WORK_PACKAGES.md`, which **accumulates**. IVGS has no
equivalent:

- **`dev/DEVELOPMENT-STATUS.md`** is a *one-page snapshot*, **rewritten every package** (§12a).
  Rows do not accumulate, and it currently lists **no report paths at all**.
- **`dev/workpackages/WP-QUEUE.md`** is the nearest ledger by name, and is a **sequencing**
  document that stops at WP-14 / WP-24 while this repo is at WP-IVGS-11. Its stated find-the-work
  mechanism is *"list `reports/`: the first Track-S package with no report is the current
  package"* — an index by directory listing.

**So the durable index in this repo is `ls dev/workpackages/reports/` plus git history.** The
port names the board as the target and **flags the divergence inside the ported text itself**
rather than papering over it. ⛔ **A real accumulating index was NOT created:** that would mean
editing `WP-QUEUE.md`, and this package's §3 forbids editing any workpackage. **It is an operator
ruling, and it is flagged here as one.**

## §4 The board corrections (package §2.3)

**§2.3 predicted one defect and the measurement found a different, sharper one.**

1. ⛔ **The held row named a DANGLING commit.** It read *"Held now: ONE commit — `3190f29`,
   addendum 2."* The **count was right; the SHA was not on the branch.** `git merge-base
   --is-ancestor 3190f29 HEAD` → false; the reflog shows `commit (amend)` folding `3190f29` into
   **`70058b9`** when the `__file__` import anchor and its test were added. Corrected, with the
   rule that prevents it: **a held SHA is read from `git log origin/main..HEAD` at close, never
   carried forward from the commit you first made.**
   ⚠ **The stale "held" row §2.3 actually named — *"Held now: WP-IVGS-09b's single commit"* — had
   already been corrected by the previous session.** The package's premise was one session out of
   date. Checked, not assumed (§0 rule 5's closing clause).
2. ⛔ **`f61029b` is untagged, and the tag was NOT created.** `fix(wp-ivgs-09e): the mpeg4 was
   never ours - pin the encode, and the draft exists`, 2026-08-28 — the commit that pins the draft
   encode, carrying no git tag. Added as a one-line board item. **Creating it is the operator's**,
   per §2.3. `8661b11` and `08521bd` are likewise untagged, and `v5.34.0-v7-contract` and
   `v5.35.0-rule8-at-birth` **both point at `03adc02`** — two tags on one commit.
3. ⭐ **An image tag is not a git tag.** `v5.31.0-hygiene`, `v5.34.1-v7-contract` and
   `v5.36.1-stage2-limits` all appear on the board as versions and **none exists as a git tag**
   (`git tag --list`). This is the same class as the `v5.31.0-hygiene` finding that opened this
   package. Recorded on the board **and** promoted into §0 rule 5's closing clause, because it is
   a premise-checking trap and that is where it bites.
4. ⭐ **A `## Reports filed this session` section** was added — rule 5 step 2's target, carrying
   its own warning that the board does not accumulate.

## §5 `CLOSE OUT` executed against this session — the proof (package §2.4)

| step | result |
|---|---|
| **1. Evidence out of scratch** | One scratch file, `scratchpad/s0.md` — the drafted §0 block. **Its content is now in `dev/CLAUDE.md` verbatim; nothing is lost and nothing else was produced.** A documentation-only package with no captures, exactly as the rule anticipates |
| **2. Index it** | Done — `## Reports filed this session` on the board, three rows. **This step is where the port broke; see §3.1** |
| **3. Banner what you superseded** | The order file is bannered (renumber + report-name amendment). ⛔ **One supersession NOT edited and flagged instead:** `OUTSTANDING_WORK.md` **RC-D10** reads *"⚠ SCHEDULED, not closed"* and **§RC-E** reads *"Code reading did not settle it."* **`WP-IVGS-10-SEAM-ANSWERS-report_2026-08-29.md` §B settles both** — the button and the drain are two halves of one outbox. Those are **register rows whose status is the operator's ruling**, so per step 3's own escape clause they are named here, not edited |
| **4. `STATE AT SESSION END`** | Top of this report, and top of the seam-answers report |
| **5. Declare the tree** | §7 below, and in the closing message |
| **Closing clause — premises checked** | The package's number (**taken** → renumbered); its report path (**MBCP convention** → amended); its `654b7c5` source commit (**not in the local clone** → fetched); its held-row premise (**already fixed a session earlier** → the real defect was a dangling SHA); `f61029b`'s tag state (**absent**, as predicted) |

**Defects in the port, found by running it, and fixed in the text:** the missing index target
(§3.1), the `§7` sudo cross-reference that has no IVGS analogue (dropped), and the held-count
phrasing that assumes holding is optional (§1 makes it unconditional). All three are in the
landed text.

## §6 What this package did NOT do

- ⛔ **`dev/CLAUDE.md` was not restructured.** 68 insertions, **0 deletions** — verified by
  `git diff --stat`.
- ⛔ **No git tag created**, for `f61029b` or anything else.
- ⛔ **No workpackage or report edited**, except the banner on this package's own order.
- ⛔ **No `OUTSTANDING_WORK.md` row edited** — RC-D10 and §RC-E flagged, not closed.
- ⛔ **No push, no deploy, no service restarted, no node other than node-01 contacted.**
- ⛔ **No accumulating index file created** — operator ruling (§3.1).

## §7 The tree, declared

| | |
|---|---|
| **Committed by me** | **Two commits, HELD** — `docs(wp-ivgs-10)` (the seam-answers appendix) and `docs(wp-ivgs-11)` (this port). Neither pushed |
| **Held (pre-existing)** | **1 commit — `70058b9`**, WP-IVGS-10 addendum 2. `origin/main` = `03adc02` |
| **Modified** | `dev/CLAUDE.md` (+68/−0), `dev/DEVELOPMENT-STATUS.md` (+35/−1) |
| **Untracked, mine** | `dev/workpackages/WP-IVGS-11_Session_Protocol_Port.md` (renamed from `…-10_…`), `dev/workpackages/reports/WP-IVGS-10-SEAM-ANSWERS-report_2026-08-29.md`, this report |
| **Dirty and NOT mine** | **None.** No stray files appeared; nothing of another agent's was staged |
| **Code touched** | **None.** `git status --porcelain` filtered on `.py/.ts/.tsx/.js/.json/.yml/.yaml/.sql` is empty. No test run was required |

## §8 Push block — count-gated, for the operator

⛔ **NOT PUSHED. `dev/CLAUDE.md` §1: the operator holds sole push and merge authority.**

Expected held count after this package's commits land: **3** — `70058b9` (WP-IVGS-10 addendum 2,
pre-existing), plus **two** written here: the WP-IVGS-10 seam-answers appendix and WP-IVGS-11.

⚠ **The appendix is committed SEPARATELY and `70058b9` is NOT amended.** Amending it would move
the SHA the board now names — re-creating, in the same session, the exact dangling-SHA defect §4
just corrected.

```bash
# ===== NODE-01  192.168.1.90  =====
( set -u
  cd /opt/ivgs || { echo "no /opt/ivgs"; false; }
  N=$(git rev-list --count origin/main..HEAD)
  echo "commits ahead of origin/main: $N"
  git --no-pager log --oneline origin/main..HEAD
  if [ "$N" -eq 3 ]; then
    git push origin main && echo "PUSHED"
  else
    echo "REFUSING: expected exactly 3 (WP-IVGS-10 addendum 2 + its appendix + WP-IVGS-11), found $N."
  fi
)
```
