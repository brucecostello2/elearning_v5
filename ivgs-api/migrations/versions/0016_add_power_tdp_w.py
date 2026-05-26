"""Add power_tdp_w column to gpu_nodes per spec Appendix C.4

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-25

Spec Appendix C.4 defines GpuNodeResponse with power_tdp_w (e.g. 350 for
RTX 5000 Pro Blackwell). The original gpu_nodes table (migration 0003)
omitted this column. This migration corrects the gap.

Nullable to support existing rows. When the GPU Scheduler microservice
(Phase 8) auto-registers nodes per spec D.4 seed data, it will populate
power_tdp_w from the GPU hardware spec. Manual registration remains
supported via PATCH /gpu/nodes/{id}.

References:
  - IVGS v5 Functional Specification, Appendix C.4
  - GPU Fleet Monitoring Spec v1.1, section 2.1 pre-existing gap (1)
"""
from alembic import op
import sqlalchemy as sa


revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "gpu_nodes",
        sa.Column(
            "power_tdp_w",
            sa.Integer(),
            nullable=True,
            comment="GPU thermal design power in watts (e.g., 350 for RTX 5000 Pro Blackwell). Per spec Appendix C.4.",
        ),
    )


def downgrade() -> None:
    op.drop_column("gpu_nodes", "power_tdp_w")
