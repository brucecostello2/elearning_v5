"""0027 — add 'ffmpeg' to the model_engine enum.

AD-02 names FFmpeg the primary compositor (node-06), and MBCP composition
certifications arrive with engine="ffmpeg"; the enum created in 0026 omitted
it, so the AD-01 receiver 422'd every composition bundle.

Revision ID: 0027_add_ffmpeg_engine
Revises: 0026_ad01_model_store
"""
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PG12+ permits ADD VALUE inside a transaction as long as the new value
    # is not used in the same transaction (it is not — data arrives later).
    op.execute("ALTER TYPE model_engine ADD VALUE IF NOT EXISTS 'ffmpeg'")


def downgrade() -> None:
    # PostgreSQL cannot remove an enum value; downgrade is a deliberate no-op.
    pass
