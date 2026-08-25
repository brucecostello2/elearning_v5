"""Shared domain models and enumerations for IVGS v5.

Everything importable here is available in BOTH the API image and the worker
image, because ``shared/`` is the only source tree copied into both
(``ivgs-api/Dockerfile:32``, ``ivgs-workers/Dockerfile:30``).

That is the whole reason the ORM models below live here rather than in
``ivgs-api/app/models/``: WP-56 Task 1 moved them (ledger **P2.60**) after DLQ
replay was found dying on ``ModuleNotFoundError: ivgs_api`` inside the worker.
``app.models`` re-exports each of them, so the API side is unchanged.

A model belongs here when a WORKER needs it. Models only the API touches should
stay in ``ivgs-api/app/models/`` -- this package is a seam, not a dumping
ground.
"""

from shared.models import model_store as model_store  # noqa: F401  (AD-01 Model Store — registers tables on Base.metadata)
from shared.models.asset import Asset  # noqa: F401
from shared.models.dead_letter_queue import DeadLetterMessage  # noqa: F401
from shared.models.task_retry import TaskRetry  # noqa: F401

__all__ = [
    "model_store",
    "Asset",
    "DeadLetterMessage",
    "TaskRetry",
]
