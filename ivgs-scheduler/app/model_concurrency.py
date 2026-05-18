"""Model concurrency and residency manager.

Tracks loaded AI models per GPU to enable model-resident scheduling:
prefer GPUs that already have the needed model in VRAM to avoid
the 30–90 second model load penalty.

State stored in Redis:
    Key: gpu_models:{hostname}:{gpu_index}
    Value: JSON array of currently loaded model names
    TTL: 300 seconds (refreshed on heartbeat)
"""

import json
import logging
from typing import List, Dict, Optional, Set

logger = logging.getLogger(__name__)

MAX_CONCURRENT_MODELS = 2    # Max models loaded on one GPU simultaneously
MODEL_STATE_TTL = 300        # Seconds before model state expires


class ModelConcurrencyManager:
    """Manages model loading state per GPU for residency-aware scheduling."""

    def __init__(self, redis_client):
        self.redis = redis_client

    def can_load_model(self, hostname: str, gpu_index: int,
                       model_name: str) -> bool:
        """Check if model can be loaded on this GPU.

        Returns True if:
        - Model already loaded (free operation), OR
        - Fewer than MAX_CONCURRENT_MODELS loaded (room to load)
        """
        loaded = self._get_loaded_models(hostname, gpu_index)
        if model_name in loaded:
            return True
        return len(loaded) < MAX_CONCURRENT_MODELS

    def track_model_load(self, hostname: str, gpu_index: int,
                         model_name: str) -> None:
        """Record that a model was loaded on a GPU."""
        loaded = self._get_loaded_models(hostname, gpu_index)
        loaded.add(model_name)
        self._set_loaded_models(hostname, gpu_index, loaded)
        logger.info(
            "Model '%s' loaded on %s:%d (total=%d)",
            model_name, hostname, gpu_index, len(loaded)
        )

    def track_model_unload(self, hostname: str, gpu_index: int,
                           model_name: str) -> None:
        """Record that a model was unloaded from a GPU."""
        loaded = self._get_loaded_models(hostname, gpu_index)
        loaded.discard(model_name)
        self._set_loaded_models(hostname, gpu_index, loaded)
        logger.info(
            "Model '%s' unloaded from %s:%d",
            model_name, hostname, gpu_index
        )

    def get_model_residency(self) -> Dict[str, List[str]]:
        """Return map of GPU key → list of loaded models."""
        pattern = "gpu_models:*"
        result = {}
        try:
            for key in self.redis.scan_iter(pattern):
                raw = self.redis.get(key)
                if raw:
                    gpu_key = key.replace("gpu_models:", "")
                    result[gpu_key] = json.loads(raw)
        except Exception as e:
            logger.error("get_model_residency failed: %s", e)
        return result

    def prefer_resident_gpu(
        self, model_name: str
    ) -> List[str]:
        """Return list of GPU keys that already have model loaded.

        Scheduler checks this before load balancer to prefer
        no-load-latency GPUs.
        Returns list of keys in format 'hostname:gpu_index'.
        """
        residents = []
        residency = self.get_model_residency()
        for gpu_key, models in residency.items():
            if model_name in models:
                residents.append(gpu_key)
        return residents

    def refresh_state(self, hostname: str, gpu_index: int,
                      loaded_models: List[str]) -> None:
        """Called on worker heartbeat to sync model state."""
        self._set_loaded_models(hostname, gpu_index, set(loaded_models))

    # ──────────────────────────────────────────────

    def _get_loaded_models(self, hostname: str, gpu_index: int) -> Set[str]:
        key = f"gpu_models:{hostname}:{gpu_index}"
        raw = self.redis.get(key)
        if not raw:
            return set()
        return set(json.loads(raw))

    def _set_loaded_models(self, hostname: str, gpu_index: int,
                           models: Set[str]) -> None:
        key = f"gpu_models:{hostname}:{gpu_index}"
        self.redis.setex(key, MODEL_STATE_TTL, json.dumps(list(models)))
