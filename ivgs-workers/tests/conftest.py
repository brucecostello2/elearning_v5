"""Worker test bootstrap.

1. ``ivgs-workers`` on sys.path. The worker package imports its own modules as
   top level (``models``, ``tasks``, ``config``, ``celery_app``) because that is
   how they are laid out inside the container. pyproject's ``pythonpath`` is
   ``["ivgs-api", "."]``, so without this every module under
   ``ivgs-workers/tests`` failed to collect with ``No module named 'models'``.
   Scoped to this conftest so ``ivgs-api``'s test run is unaffected.
2. Cross-node registry env before config.py import (config reads VLLM_*_URL via
   _require at import time; setdefault keeps compose/CI env authoritative).
"""
import os
import sys

_WORKER_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WORKER_ROOT not in sys.path:
    sys.path.insert(0, _WORKER_ROOT)

os.environ.setdefault("VLLM_PRIMARY_URL", "http://192.168.1.91:8000")
os.environ.setdefault("VLLM_SECONDARY_URL", "http://192.168.1.92:8000")
os.environ.setdefault("VLLM_MIDSIZE_URL", "http://192.168.1.93:8000")
