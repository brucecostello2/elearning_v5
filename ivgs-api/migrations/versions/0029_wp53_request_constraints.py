"""0029 — WP-53: models.request_constraints, the AD-04 seam-1 field IVGS was dropping.

MBCP amended the export bundle on 2026-08-21 (WP-E32-R, operator-approved,
recorded in its Appendix G) to carry ``request_constraints`` — the DECLARED
geometry and sampler rules a request against that model must obey, sourced from
the adapter serving the cert's stage.

IVGS's ``ExportBundleIn`` had no such field and carried
``model_config = ConfigDict(extra="ignore")``, so every bundle since that date
has been accepted with a 201 and the field discarded in silence. The receiver
reported success while throwing away the contract.

WHY A COLUMN AND NOT ``default_params``. Four MBCP-sourced facts already ride in
``models.default_params`` — weight_tier, engine_version, quantization,
provenance — and adding a fifth key would have needed no migration at all. It
would also have been wrong. ``default_params`` are DEFAULTS: values a caller may
override. ``request_constraints`` are CONSTRAINTS: rules a request must obey.
Putting a constraint in a bag named "defaults" invites a consumer to treat it as
overridable, which is a shorter path to the failure MBCP's own code comment
describes than the silent drop this migration fixes.

THE FAILURE THE SENDER NAMED IN ADVANCE. A consumer reads
``quality_summary.performance.resolution`` — a MEASURED 1920x1080 for
Wan2.2-T2V — builds a request from it, and reproduces a 135/134 sampler failure
while holding MBCP's certificate. Measured-under-test geometry is not
permitted-request geometry, and until this column exists IVGS has nowhere to put
the difference. That is WP-47's scenario, named by the sender before it happened
here.

NOT INTERPRETED BY THIS MIGRATION OR BY WP-53. The column is JSONB and opaque:
carried, stored, surfaceable. Nothing reads it to make a decision yet, which is
WP-53's stated scope.

VERIFIED AGAINST PRIMARY SOURCES, and it changed the implementation. The
read-only clone at ``/opt/MBCP`` was pinned at ``ea7f91e`` (2026-08-05), sixteen
days BEFORE the amendment, so it had to be fetched first; read at
``origin/main`` = ``156ddb4``:

  * ``mbcp_core/schemas/export.py:82`` — ``request_constraints: dict | None =
    None``. NULLABLE. ``mbcp_core.request_constraints()`` returns ``None`` for
    any model with no declared rule, and MBCP's own tests pin that for
    FLUX.1-dev and for unregistered names, so **most** exports carry an explicit
    ``null``. This column is nullable for that reason and not merely for
    back-fill.
  * ``None`` and ``{}`` are DIFFERENT FACTS and MBCP says so: "An empty block
    would be the claim 'we checked'; a missing one is the truth 'we have
    declared nothing'." IVGS stores NULL for a null and never substitutes ``{}``.
  * The block leads with an honesty label — ``kind: "declared"``,
    ``declared_by``, ``declared_on`` — then optional ``geometry``,
    ``frame_count_rule``, ``value_rules``, and a NESTED ``default_params`` of
    legal defaults. That nested key is the second reason this cannot live inside
    ``models.default_params``: the two would collide by name.

Precedent: 0028 exists for the same class of defect — five scene fields the UI
had always sent and ``SceneUpdate`` silently discarded.

Revision ID: 0029
Revises: 0028
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "models",
        sa.Column(
            "request_constraints",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment=(
                "AD-04 seam 1. DECLARED geometry and sampler rules a request "
                "against this model must obey, as sent by MBCP's export bundle "
                "(WP-E32-R, 2026-08-21). Distinct from default_params: these are "
                "constraints, not overridable defaults, and distinct from "
                "quality_summary.performance, which is what was MEASURED under "
                "test rather than what is PERMITTED. Carried opaquely; IVGS does "
                "not interpret it as of WP-53. NULL means the sender supplied "
                "none, which is also what every row predating this column means."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("models", "request_constraints")
