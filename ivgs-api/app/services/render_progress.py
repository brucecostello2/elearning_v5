"""Real-time render progress tracking via FFmpeg output parsing.

Parses FFmpeg stderr progress lines and broadcasts percentage/ETA
to connected WebSocket clients via Redis pub/sub.
"""

import logging
import re
import time
from typing import Dict, Any, Optional

import redis as redis_lib

logger = logging.getLogger(__name__)

REDIS_URL = __import__('os').environ.get('REDIS_URL', 'redis://node-01:6379/0')
PROGRESS_KEY_TTL = 3600  # 1 hour


def _get_redis() -> redis_lib.Redis:
    return redis_lib.from_url(REDIS_URL, decode_responses=True)


class RenderProgressTracker:
    """Tracks and broadcasts render progress."""

    def __init__(self, job_id: str, total_duration_ms: int):
        self.job_id = job_id
        self.total_duration_ms = total_duration_ms
        self.redis = _get_redis()
        self.start_time = time.time()
        self._key = f"render_progress:{job_id}"

    def start_tracking(self) -> None:
        """Initialize progress record in Redis."""
        self.redis.hset(self._key, mapping={
            "job_id": self.job_id,
            "total_ms": self.total_duration_ms,
            "current_ms": 0,
            "percentage": 0,
            "eta_seconds": -1,
            "speed": "0x",
            "frame": 0,
            "started_at": self.start_time,
            "status": "rendering"
        })
        self.redis.expire(self._key, PROGRESS_KEY_TTL)
        logger.info(
            "Progress tracking started for job %s (%dms)",
            self.job_id, self.total_duration_ms
        )

    def parse_ffmpeg_output(self, line: str) -> Optional[Dict[str, Any]]:
        """Extract progress data from FFmpeg stderr output line.

        FFmpeg outputs lines like:
          frame= 125 fps= 25 q=28.0 size=    512kB time=00:00:05.00 bitrate=839.7kbits/s speed=2x
        """
        if 'time=' not in line:
            return None

        progress = {}

        # Parse time
        time_match = re.search(r'time=(\d{2}):(\d{2}):(\d{2})\.(\d{2})', line)
        if time_match:
            h, m, s, cs = map(int, time_match.groups())
            current_ms = ((h * 3600 + m * 60 + s) * 1000) + (cs * 10)
            progress['current_ms'] = current_ms
            if self.total_duration_ms > 0:
                progress['percentage'] = round(
                    min(100.0, current_ms / self.total_duration_ms * 100), 1
                )

        # Parse speed
        speed_match = re.search(r'speed=\s*([\d.]+)x', line)
        if speed_match:
            speed = float(speed_match.group(1))
            progress['speed'] = f"{speed:.2f}x"
            if speed > 0 and progress.get('current_ms', 0) > 0:
                remaining_ms = self.total_duration_ms - progress['current_ms']
                progress['eta_seconds'] = int(
                    remaining_ms / (speed * 1000)
                )

        # Parse frame
        frame_match = re.search(r'frame=\s*(\d+)', line)
        if frame_match:
            progress['frame'] = int(frame_match.group(1))

        self._broadcast_progress(progress)
        return progress

    def get_progress(self) -> Dict[str, Any]:
        """Return current progress state."""
        data = self.redis.hgetall(self._key)
        return {k: (float(v) if v.replace('.','',1).isdigit() else v)
                for k, v in data.items()} if data else {"percentage": 0}

    def mark_complete(self) -> None:
        """Mark render as complete."""
        self.redis.hset(self._key, mapping={
            "percentage": 100,
            "status": "complete",
            "completed_at": time.time(),
        })
        self.redis.expire(self._key, 3600)
        self._broadcast_progress({"status": "complete", "percentage": 100})

    # ──────────────────────────────────────────────

    def _broadcast_progress(self, progress: Dict[str, Any]) -> None:
        """Push progress update to Redis pub/sub channel."""
        try:
            import json
            self.redis.hset(self._key, mapping={
                k: str(v) for k, v in progress.items()
            })
            self.redis.publish(
                f"render_progress:{self.job_id}",
                json.dumps({**progress, "job_id": self.job_id})
            )
        except Exception as e:
            logger.debug("Progress broadcast error: %s", e)
