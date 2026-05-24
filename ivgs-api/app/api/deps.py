"""
Centralized FastAPI dependency re-exports.

This module provides a single import location for common dependencies
used across v1 routers. All symbols are re-exported from their
canonical locations — no logic lives here.

Canonical sources:
    - get_current_user   -> app.core.auth
    - require_admin      -> app.core.rbac
    - require_operator_or_admin -> app.core.rbac
    - require_any_authenticated -> app.core.rbac
    - get_db (alias)     -> shared.database.get_session
"""
from app.core.auth import get_current_user
from app.core.rbac import (
    require_admin,
    require_operator_or_admin,
    require_any_authenticated,
)
from shared.database import get_session as get_db

__all__ = [
    "get_current_user",
    "require_admin",
    "require_operator_or_admin",
    "require_any_authenticated",
    "get_db",
]
