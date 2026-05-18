"""TimeoutManager — configures and enforces per-model operation timeouts.

Provides a unified timeout wrapping strategy. Uses Python signals for
the primary timeout mechanism (requires main thread; worker-safe) and
falls back to threading.Timer for non-main-thread contexts.

Usage:
    tm = TimeoutManager()
    result = tm.call_with_timeout(
        fn=openai_client.chat.completions.create,
        kwargs={"model": "gpt-4o", ...},
        model="gpt-4o",
        operation="completion",
    )
"""
from __future__ import annotations

import logging
import signal
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class TimeoutError(Exception):
    """Raised when an operation exceeds its configured timeout."""


@dataclass
class TimeoutConfig:
    """Default timeout values in seconds per model/operation."""

    # AI Generation
    cogvideox_generation: int = 1800   # 30 minutes
    wan21_generation: int = 1200       # 20 minutes
    dalle_generation: int = 300        # 5 minutes
    sdxl_generation: int = 300         # 5 minutes
    openai_tts_generation: int = 120   # 2 minutes
    elevenlabs_tts_generation: int = 120
    did_rendering: int = 600           # 10 minutes (talking head)
    synthesia_rendering: int = 600

    # Internal operations
    ffmpeg_composition: int = 900      # 15 minutes
    ffmpeg_motion_graphics: int = 300  # 5 minutes
    openai_transcript: int = 120
    openai_storyboard: int = 120

    # Warning thresholds (fractions of total timeout)
    warn_at_50_pct: bool = True
    warn_at_75_pct: bool = True

    # Custom overrides: model_operation -> seconds
    overrides: Dict[str, int] = field(default_factory=dict)


# Singleton default config (can be replaced in tests)
_default_config = TimeoutConfig()


class TimeoutManager:
    """Wraps callable operations with configurable timeouts.

    Thread-safe: uses ThreadPoolExecutor to impose timeouts in
    worker processes where signals are not available.
    """

    def __init__(self, config: Optional[TimeoutConfig] = None) -> None:
        self._config = config or _default_config

    def get_timeout(self, model: str, operation: str) -> int:
        """Look up the configured timeout for a model+operation pair.

        Args:
            model:     Model identifier (e.g., "cogvideox", "dalle",
                       "openai_tts").
            operation: Operation type (e.g., "generation", "rendering").

        Returns:
            Timeout in seconds. Defaults to 300 if not found.
        """
        override_key = f"{model}_{operation}"
        if override_key in self._config.overrides:
            return self._config.overrides[override_key]

        attr_name = f"{model}_{operation}"
        if hasattr(self._config, attr_name):
            return getattr(self._config, attr_name)

        # Try just the model name with common operations
        for op_suffix in ["generation", "rendering", "completion"]:
            attr = f"{model}_{op_suffix}"
            if hasattr(self._config, attr):
                return getattr(self._config, attr)

        logger.warning("No timeout config for %s_%s — using 300s default",
                       model, operation)
        return 300

    def call_with_timeout(
        self,
        fn: Callable[..., Any],
        *args: Any,
        timeout_seconds: Optional[int] = None,
        model: str = "default",
        operation: str = "generation",
        **kwargs: Any,
    ) -> Any:
        """Execute fn(*args, **kwargs) with a timeout.

        Args:
            fn:              The callable to execute.
            *args:           Positional arguments passed to fn.
            timeout_seconds: Override the auto-derived timeout.
            model:           Model identifier for timeout lookup.
            operation:       Operation type for timeout lookup.
            **kwargs:        Keyword arguments passed to fn.

        Returns:
            The return value of fn.

        Raises:
            TimeoutError: If fn does not return within the timeout.
            Exception:    Any exception raised by fn is re-raised.
        """
        effective_timeout = timeout_seconds or self.get_timeout(model, operation)

        # Progress warning callbacks
        def _warn_at(pct: float) -> None:
            warn_s = effective_timeout * pct
            msg = ("Operation %s:%s at %.0f%% timeout "
                   "(%ds of %ds elapsed)")
            logger.warning(msg, model, operation, pct * 100,
                           warn_s, effective_timeout)

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(fn, *args, **kwargs)

            # Schedule warning timers
            timers = []
            if self._config.warn_at_50_pct:
                t = threading.Timer(effective_timeout * 0.5,
                                    _warn_at, args=(0.5,))
                t.daemon = True
                t.start()
                timers.append(t)
            if self._config.warn_at_75_pct:
                t = threading.Timer(effective_timeout * 0.75,
                                    _warn_at, args=(0.75,))
                t.daemon = True
                t.start()
                timers.append(t)

            try:
                result = future.result(timeout=effective_timeout)
                return result
            except FuturesTimeout:
                future.cancel()
                logger.error("TIMEOUT: %s:%s exceeded %ds",
                             model, operation, effective_timeout)
                raise TimeoutError(
                    f"Operation {model}:{operation} timed out "
                    f"after {effective_timeout}s"
                )
            finally:
                for t in timers:
                    t.cancel()
