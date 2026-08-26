"""One HTTP translation for the two refusals every dispatch route can hit.

WP-62 Task 6 and Task 2(c). Five endpoints in this API can put a pipeline
message on the broker for a project, and each of them can now be refused for
one of exactly two reasons:

  PIPELINE_ALREADY_RUNNING   a run is in flight (WP-61 Task 5, extended here)
  GATE_NOT_APPROVED          a human review gate is not currently approved

They must answer identically wherever they are raised. Five hand-written 409
blocks would drift -- the six-dispatch storm of WP-60 happened partly because
"the trigger endpoint" and "the regenerate endpoint" were treated as different
problems when they were the same problem twice.

`active_job` is in the payload so a GUI can link to the run that is holding
things up instead of telling the operator to go and look for it.
"""
from fastapi import HTTPException, status

from app.services.gate_service import GateBlocked
from app.services.project_service import PipelineAlreadyRunningError


def already_running(exc: PipelineAlreadyRunningError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "error": {
                "code": "PIPELINE_ALREADY_RUNNING",
                "message": str(exc),
                "active_job": {
                    "id": str(exc.job_id),
                    "job_type": exc.job_type,
                    "status": exc.status,
                },
            }
        },
    )


def gate_blocked(exc: GateBlocked) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "error": {
                "code": "GATE_NOT_APPROVED",
                "message": str(exc),
                "gate": exc.gate,
                "gate_reason": exc.reason,
            }
        },
    )
