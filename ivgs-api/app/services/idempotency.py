"""IdempotencyGuard — prevents duplicate stage execution on retry.

Before executing any generation task, the guard computes a content-
addressable key (SHA-256 of input parameters) and checks whether a
valid output already exists for that key. If it does, execution is
skipped and the cached output is returned.

Usage:
    guard = IdempotencyGuard(db_session)

    @guard.protect(job_id=42, stage="image_gen")
    def generate():
        return dalle_client.generate(prompt=prompt)

    # Or call directly:
    result = guard.check_or_execute(
        job_id=42, stage="image_gen",
        params={"prompt": "...", "size": "1024x1024"},
        executor=lambda: dalle_client.generate(...),
        validate=lambda r: os.path.exists(r["image_path"]),
    )
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tempfile
from typing import Any, Callable, Dict, Optional

from sqlalchemy.orm import Session

from app.middleware.checkpoint import CheckpointService

logger = logging.getLogger(__name__)


class IdempotencyGuard:
    """Provides idempotent operation execution for pipeline stages.

    Operations are identified by a (job_id, stage_name, params_hash)
    tuple. If a checkpoint with matching fingerprint and status='complete'
    exists, the existing output_refs are returned without re-execution.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self._checkpoint_svc = CheckpointService(db)

    def check_or_execute(
        self,
        job_id: int,
        stage: str,
        stage_index: int,
        params: Dict[str, Any],
        executor: Callable[[], Dict[str, Any]],
        validate: Optional[Callable[[Dict[str, Any]], bool]] = None,
    ) -> Dict[str, Any]:
        """Execute an operation idempotently.

        If a valid checkpoint with the same parameter fingerprint exists,
        return its output_refs immediately without calling executor.

        Args:
            job_id:       Job this stage belongs to.
            stage:        Stage name.
            stage_index:  Position in pipeline.
            params:       Input parameters (used to compute fingerprint).
            executor:     Zero-argument callable that performs the operation
                          and returns output_refs dict.
            validate:     Optional callable that checks if output_refs
                          still refers to accessible resources. If it
                          returns False, executor is called again.

        Returns:
            output_refs dict from either cached checkpoint or fresh execution.
        """
        fingerprint = self._compute_fingerprint(params)
        existing = self._checkpoint_svc.get_checkpoint(job_id, stage)

        # Cache hit: checkpoint complete with matching fingerprint
        if (
            existing is not None
            and existing.is_complete()
            and existing.version_fingerprint == fingerprint
            and existing.output_refs
        ):
            if validate is None or validate(existing.output_refs):
                logger.info(
                    "Idempotency hit: job=%s stage=%s (fingerprint=%s)",
                    job_id, stage, fingerprint[:8],
                )
                return existing.output_refs
            else:
                logger.info(
                    "Idempotency miss (validation failed): job=%s stage=%s",
                    job_id, stage,
                )

        # Execute the operation
        logger.debug("Executing: job=%s stage=%s", job_id, stage)
        self._checkpoint_svc.mark_stage_running(job_id, stage, stage_index)
        self.db.commit()

        try:
            output_refs = executor()
        except Exception:
            self._checkpoint_svc.mark_stage_failed(
                job_id, stage, "executor raised exception"
            )
            self.db.commit()
            raise

        # Persist result
        self._checkpoint_svc.save_checkpoint(
            job_id=job_id,
            stage=stage,
            stage_index=stage_index,
            data=params,
            outputs=output_refs,
        )
        self.db.commit()
        return output_refs

    @staticmethod
    def generate_operation_key(
        job_id: int,
        stage: str,
        params: Dict[str, Any],
    ) -> str:
        """Generate a deterministic SHA-256 key for this operation.

        Args:
            job_id:  Job identifier.
            stage:   Stage name.
            params:  Input parameters dict (must be JSON-serializable).

        Returns:
            Full 64-character hex SHA-256 digest.
        """
        payload = {"job_id": job_id, "stage": stage, "params": params}
        serialized = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()

    def validate_file_output(self, output_refs: Dict[str, Any],
                              key: str = "file_path") -> bool:
        """Validate that a file-based output still exists on disk."""
        path = output_refs.get(key)
        if not path:
            return False
        if path.startswith("seaweedfs://"):
            # Remote storage — assume valid if checkpoint says complete
            return True
        return os.path.exists(path) and os.path.getsize(path) > 0

    @staticmethod
    def atomic_write(content: bytes, destination: str) -> None:
        """Write bytes to destination atomically via temp file + rename.

        Prevents partial writes from polluting the output directory.

        Args:
            content:     Bytes to write.
            destination: Final destination path.
        """
        dest_dir = os.path.dirname(destination) or "."
        os.makedirs(dest_dir, exist_ok=True)

        with tempfile.NamedTemporaryFile(dir=dest_dir, delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        shutil.move(tmp_path, destination)

    @staticmethod
    def _compute_fingerprint(params: Dict[str, Any]) -> str:
        """Compute short SHA-256 fingerprint of params dict."""
        serialized = json.dumps(params, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()[:32]
