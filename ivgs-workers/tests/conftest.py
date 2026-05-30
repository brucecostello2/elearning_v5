"""Seed cross-node registry env before config.py import (config reads VLLM_*_URL via _require at import time; setdefault keeps compose/CI env authoritative)."""
import os
os.environ.setdefault("VLLM_PRIMARY_URL", "http://192.168.1.91:8000")
os.environ.setdefault("VLLM_SECONDARY_URL", "http://192.168.1.92:8000")
os.environ.setdefault("VLLM_MIDSIZE_URL", "http://192.168.1.93:8000")
