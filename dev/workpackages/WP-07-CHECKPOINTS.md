# WP-07-CHECKPOINTS — Build the checkpoint write path; make resume real

| | |
|---|---|
| **Ledger** | **P1.2** · M2 — highest-leverage item in the milestone |
| **Tier** | A (self-proving) · **Track S #8** |
| **Report** | `reports/WP-07-CHECKPOINTS-report_<YYYY-MM-DD>.md` |
| **Next** | WP-08-GPU-RESERVATIONS |

## Objective

The checkpoint subsystem is a silent no-op. `utils/error_handler.py:409` POSTs to
`/jobs/{job_id}/checkpoints`; `ivgs-api/app/api/v1/checkpoints.py` declares only
`GET /checkpoints` (`:79`), `GET /checkpoints/{stage}` (`:106`), `POST /resume`
(`:137`), `DELETE /checkpoints` (`:175`). **There is no POST route** — hence a 405 on
every attempt. `save_checkpoint` logs a warning and returns `False` (`:435-441`);
no call site checks it. No checkpoint row has ever been written; `POST /resume`
resumes from an empty table. This is the single biggest lever on long-render test
cost: resume-from-failure collapses the iteration loop for every bug class.

## Method

- Add `POST /jobs/{id}/checkpoints` (~40 lines per the ledger estimate — verify
  against the existing GET/DELETE handlers' patterns and the
  `pipeline_checkpoints` schema, Table 14).
- At every `save_checkpoint` call site, assert on the return value — a failed
  checkpoint write must surface, not vanish (this is a WP-00 shape; fix it here,
  record it in the swallow register as closed-with-evidence).
- Verify `POST /resume` actually resumes from the newest checkpoint once rows exist —
  read its implementation; do not assume it works just because rows appear.
- Note for the report, not for code: at M3 this subsystem is superseded by workflow
  history (spec v5.1 A6). It is still built now because M2 needs a working system
  while migrating and M1/M2 testing benefits immediately.

## Scope

**In:** the API route, `error_handler.py` call-site asserts, tests, register update.
**Out:** stage task bodies; resume UX; anything Temporal.

## Exit gate

Kill a worker mid-stage on a test job; the job resumes **without re-running completed
stages** — the capability the spec promised and never had. Evidence: checkpoint rows
in `pipeline_checkpoints` (query shown), the resume log trace, and stage timestamps
proving completed stages did not re-execute.
