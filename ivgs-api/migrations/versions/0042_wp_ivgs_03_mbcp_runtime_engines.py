"""0042 — add MBCP's four unnamed runtimes to the model_engine enum.

WP-IVGS-03. MBCP's export drain was 422'd on ``engine`` with input ``"tts"``:
four live certificates (Kokoro + three XTTS-v2) could not be delivered, and
three onboarding models — ``magihuman``, ``humo``, ``wan22_s2v`` — would have
failed identically on certification. ``magihuman`` is the model the whole
talking-head workstream is built around.

MBCP's ``models.engine`` is free text (``mbcp_core/models/model.py:33``,
``String(64)``, no enum, no CHECK); IVGS's is a closed PG enum, and nothing
keeps the two value domains in step. MBCP could not send a correct value even
in principle, which makes this a contract defect on the receiving side.

The four values were derived from where MBCP actually writes that column —
``scripts/seed_stage.py:543,576`` (``tts``) and ``scripts/ops/seed_wan22_cell.py:39``
(``wan22_s2v``), with ``magihuman``/``humo`` following MBCP's measured
``engine == adapter_key`` convention for ``engine_only`` remote engines. NOT
from ``adapter_key``, which is ``tts_coqui`` / ``ffmpeg_composition`` and is a
different thing.

``tts`` names a RUNTIME, not a model family: one ``TtsServerAdapter`` serves
both XTTS-v2 and Kokoro. That is WP-46's rule (``ad01_ingest.py:52-62``)
applied, not relaxed.

⛔ NOTHING IS REMOVED. ``coqui``, ``kokoro``, ``animatediff``, ``latentsync``
and ``sadtalker`` name model families rather than runtimes by WP-46's own
reasoning, and are inconsistent with it — but they are in use on live rows,
including the Kokoro-82M row rendering today. Ruled 2026-08-27: ledger the
inconsistency, do not clean it up. Reconciliation lands with AD-10.

Precedent: ``e613e84`` / migration ``0027`` (add ``ffmpeg``) — same shape, same
reason, same deliberate no-op downgrade.

Revision ID: 0042
Revises: 0041
"""
from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None

# The four MBCP runtimes the enum could not express. Order is the order they
# will appear in the API's 422 message.
_NEW_ENGINES = ("tts", "magihuman", "humo", "wan22_s2v")


def upgrade() -> None:
    # PG12+ permits ADD VALUE inside a transaction as long as the new value is
    # not used in the same transaction (it is not — MBCP's data arrives later,
    # over the AD-01 seam, after this migration has committed).
    for value in _NEW_ENGINES:
        op.execute(f"ALTER TYPE model_engine ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # PostgreSQL cannot remove an enum value; downgrade is a deliberate no-op,
    # as in 0027, 0040 and 0041. Dropping a value would also require proving no
    # row references it, which a downgrade cannot do safely against live data.
    pass
