"""
Global error handler middleware per Appendix C.2 and C.5.

Maps all exceptions to standardized error response format:
{
    "error": {
        "code": "ERROR_CODE",
        "message": "Human-readable message",
        "details": [...],
        "request_id": "uuid"
    }
}
"""
import logging
import traceback
import uuid

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Catches unhandled exceptions and returns standardized error responses."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        try:
            response = await call_next(request)
            return response

        except RequestValidationError as e:
            logger.warning(f"Validation error: {e.errors()}")
            return JSONResponse(
                status_code=422,
                content={
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "Request validation failed",
                        "details": [
                            {
                                "field": ".".join(str(loc) for loc in err.get("loc", [])),
                                "issue": err.get("msg", ""),
                            }
                            for err in e.errors()
                        ],
                        "request_id": request_id,
                    }
                },
            )

        except HTTPException:
            # Let HTTPExceptions propagate — they already have proper status codes
            raise

        except Exception as e:
            logger.error(
                f"Unhandled exception: {e}\n{traceback.format_exc()}",
                extra={"request_id": request_id},
            )
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "An unexpected error occurred",
                        "request_id": request_id,
                    }
                },
            )
