"""The two human review gates, as records rather than as a button (WP-62 Task 2).

WHAT WAS THERE BEFORE, MEASURED 2026-08-26.

An "Approve storyboard" button already existed. It posts
``POST /projects/{id}/scenes/approve?tier=``, which sets ``projects.state`` to
``MEDIA_GENERATION`` and dispatches ``dispatch_media_generation``. It wrote no
row anywhere. So:

  * nothing recorded THAT an approval happened, WHO gave it, WHEN, or WHAT they
    were looking at when they gave it;
  * nothing downstream could ask whether an approval existed, so nothing
    refused for want of one;
  * re-running the storyboard after an approval left the approval standing
    over scenes that no longer existed, because there was no approval to
    invalidate.

Spec v5.1 §6.1 and the amendment's §6.4/§13 require both gates to BLOCK, and to
accept approve / reject / regenerate. This table is the blocking half's memory.

THE ARTIFACT VERSION IS THE WHOLE MECHANISM.

An approval that names only a project is a claim that the project is fine
forever. A decision here names the exact artifact it was made against --
``artifact_version`` -- and currency is RECOMPUTED ON READ by comparing that
string with the artifact as it stands now. An upstream re-run changes the
artifact, the strings stop matching, and the approval is stale without anything
having to remember to invalidate it. There is no invalidation write to forget,
and no window in which a crashed invalidator leaves a stale approval standing.

``upstream_version`` carries the same idea one level up: a draft approval also
records the storyboard version it was taken under, so re-running the storyboard
invalidates the DRAFT approval immediately - before any new draft exists to
change the draft's own version.

M3.3 COMPATIBILITY. The gates are specified as Temporal SIGNALS (spec v5.1
§6.4: "the workflow blocks at ``wait_condition`` until the API signals
approval"). Nothing here dispatches anything: a row is written, and the caller
decides what to do about it. At cutover the same service method sends a signal
instead of a Celery message and this table remains the audit of what was
signalled. ``GateDecision.signal_payload()`` is that payload, today, so the
shape is fixed now rather than invented under time pressure later.
"""
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.database import Base

#: The two gates, spelled once. Used by the schema, the routes and the tests.
GATE_STORYBOARD = "storyboard"
GATE_DRAFT = "draft"
GATES = (GATE_STORYBOARD, GATE_DRAFT)

#: The three decisions §6.4 requires a gate to accept.
DECISION_APPROVE = "approved"
DECISION_REJECT = "rejected"
DECISION_REGENERATE = "regenerate"
DECISIONS = (DECISION_APPROVE, DECISION_REJECT, DECISION_REGENERATE)


class ProjectGateDecision(Base):
    """One human decision at one gate, against one artifact version.

    Rows are APPEND-ONLY. A reject after an approval is a new row, not an edit,
    because "this was approved and then rejected" is a different fact from
    "this was never approved" and the review history is the point of the table.
    The current decision at a gate is the newest row for that (project, gate).
    """

    __tablename__ = "project_gate_decisions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    gate: Mapped[str] = mapped_column(String(32), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    #: The fingerprint of the artifact this decision was made against. Never
    #: null: a decision that cannot name what it decided about is not a gate
    #: record, it is a timestamp.
    artifact_version: Mapped[str] = mapped_column(String(128), nullable=False)
    #: For the draft gate, the storyboard version in force when it was taken.
    upstream_version: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True,
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decided_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    #: Denormalised on purpose. ``decided_by`` is SET NULL on user deletion --
    #: it must be, or deleting a user would be blocked by the review history --
    #: and a gate record that cannot say who made the decision after the
    #: reviewer leaves is not much of a record.
    decided_by_name: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True,
    )
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )

    __table_args__ = (
        Index(
            "ix_project_gate_decisions_project_gate",
            "project_id", "gate", "decided_at",
        ),
    )

    def signal_payload(self) -> dict[str, Any]:
        """The M3.3 signal body, defined now so the shape does not move later.

        Spec v5.1 §6.4 implements both gates as Temporal signals. The signal
        name is ``gate_{gate}`` and this is its argument; a Celery dispatch
        today and a ``handle.signal(...)`` at cutover carry the same object.
        """
        return {
            "gate": self.gate,
            "decision": self.decision,
            "artifact_version": self.artifact_version,
            "upstream_version": self.upstream_version,
            "note": self.note,
            "decided_by": str(self.decided_by) if self.decided_by else None,
            "decided_at": self.decided_at.isoformat() if self.decided_at else None,
        }
