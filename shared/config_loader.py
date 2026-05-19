"""
IVGS v5 — YAML Configuration Loader
=====================================

Loads configuration from YAML files per §19.2 and Appendix A.1.
Replaces hardcoded values in environment variables and Python code.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger("ivgs.config_loader")

_CONFIG_DIR = Path("/ivgs/ivgs-api/config")
_cache: dict[str, Any] = {}


def load_config(filename: str, config_dir: Optional[Path] = None) -> dict[str, Any]:
    """Load a YAML configuration file, with caching."""
    dir_path = config_dir or _CONFIG_DIR
    cache_key = str(dir_path / filename)

    if cache_key in _cache:
        return _cache[cache_key]

    filepath = dir_path / filename
    if not filepath.exists():
        raise FileNotFoundError(f"Configuration file not found: {filepath}")

    with open(filepath, "r") as f:
        data = yaml.safe_load(f)

    _cache[cache_key] = data
    logger.info(f"Loaded configuration from {filepath}")
    return data


def get_timeout(model_key: str) -> dict[str, Any]:
    """Get timeout configuration for a model."""
    config = load_config("timeout_defaults.yaml")
    return config["timeouts"].get(model_key, {"timeout_seconds": 120})


def get_retry_policy(task_type: str) -> dict[str, Any]:
    """Get retry policy for a task type."""
    config = load_config("retry_policies.yaml")
    return config["retry_policies"].get(task_type, {"max_retries": 2})


def get_gpu_requirement(model_key: str) -> dict[str, Any]:
    """Get GPU VRAM requirement for a model."""
    config = load_config("gpu_requirements.yaml")
    return config["gpu_requirements"].get(model_key, {"vram_mb": 8192})


def get_quality_threshold(asset_type: str, metric: str) -> dict[str, Any]:
    """Get quality threshold for an asset type and metric."""
    config = load_config("quality_thresholds.yaml")
    return config["quality_thresholds"].get(asset_type, {}).get(metric, {})


def clear_cache() -> None:
    """Clear the configuration cache (useful for testing)."""
    _cache.clear()
