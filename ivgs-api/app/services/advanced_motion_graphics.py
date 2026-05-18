"""Remotion-powered advanced motion graphics service."""
import os
import time
import logging
import requests
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

REMOTION_URL = os.environ.get("REMOTION_SERVICE_URL",
                               "http://localhost:3002")
TEMPLATE_NAMES = [
    "title_card", "lower_third", "transition_slide",
    "data_visualization", "split_screen", "picture_in_picture",
]


class AdvancedMotionGraphics:
    """Renders motion graphics templates via the Remotion HTTP render API."""

    def __init__(
        self,
        remotion_url: str = REMOTION_URL,
        workdir: str = "/mnt/workdir",
        timeout_seconds: int = 300,
    ):
        self.remotion_url = remotion_url.rstrip("/")
        self.workdir = workdir
        self.timeout_seconds = timeout_seconds

    def is_available(self) -> bool:
        """Check if Remotion service is reachable."""
        try:
            r = requests.get(f"{self.remotion_url}/health",
                             timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def list_templates(self) -> List[str]:
        """Return list of available template names."""
        try:
            r = requests.get(f"{self.remotion_url}/templates", timeout=10)
            r.raise_for_status()
            return r.json().get("templates", TEMPLATE_NAMES)
        except Exception:
            return TEMPLATE_NAMES

    def render_template(
        self,
        template_name: str,
        params: Dict[str, Any],
        output_path: str,
        composition_id: Optional[str] = None,
    ) -> Optional[str]:
        """Render a Remotion template to MP4. Returns output path or None."""
        if template_name not in TEMPLATE_NAMES:
            logger.error("Unknown template: %s", template_name)
            return None

        os.makedirs(Path(output_path).parent, exist_ok=True)

        payload = {
            "composition": composition_id or template_name,
            "outputFile": output_path,
            "inputProps": params,
            "codec": "h264",
            "imageFormat": "jpeg",
            "jpegQuality": 85,
            "concurrency": 2,
        }

        logger.info("Remotion rendering: %s -> %s", template_name, output_path)
        t0 = time.monotonic()

        try:
            response = requests.post(
                f"{self.remotion_url}/render",
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            result = response.json()
        except requests.exceptions.Timeout:
            logger.error("Remotion render timed out after %ds",
                         self.timeout_seconds)
            return None
        except requests.exceptions.RequestException as exc:
            logger.error("Remotion API error: %s", exc)
            return None

        elapsed = time.monotonic() - t0
        if result.get("success"):
            logger.info("Remotion render complete in %.1fs: %s",
                        elapsed, output_path)
            return output_path
        else:
            logger.error("Remotion render failed: %s",
                         result.get("error", "unknown"))
            return None

    def preview_template(
        self,
        template_name: str,
        params: Dict[str, Any],
        output_path: str,
    ) -> Optional[str]:
        """Render a single-frame preview image for a template."""
        payload = {
            "composition": template_name,
            "outputFile": output_path,
            "inputProps": params,
            "frameNumber": 0,
            "imageFormat": "png",
        }
        try:
            response = requests.post(
                f"{self.remotion_url}/still",
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
            return output_path if Path(output_path).exists() else None
        except Exception as exc:
            logger.error("Remotion preview failed: %s", exc)
            return None

    def render_title_card(
        self,
        title: str,
        subtitle: Optional[str],
        duration_frames: int,
        output_path: str,
        theme: str = "dark",
    ) -> Optional[str]:
        return self.render_template("title_card", {
            "title": title,
            "subtitle": subtitle or "",
            "durationFrames": duration_frames,
            "theme": theme,
        }, output_path)

    def render_lower_third(
        self,
        name: str,
        title: str,
        duration_frames: int,
        output_path: str,
    ) -> Optional[str]:
        return self.render_template("lower_third", {
            "name": name,
            "title": title,
            "durationFrames": duration_frames,
        }, output_path)

    def render_data_viz(
        self,
        chart_type: str,
        data: Dict,
        headline: str,
        duration_frames: int,
        output_path: str,
    ) -> Optional[str]:
        return self.render_template("data_visualization", {
            "chartType": chart_type,
            "data": data,
            "headline": headline,
            "durationFrames": duration_frames,
        }, output_path)

    def render_split_screen(
        self,
        left_video: str,
        right_video: str,
        duration_frames: int,
        output_path: str,
        caption_left: Optional[str] = None,
        caption_right: Optional[str] = None,
    ) -> Optional[str]:
        return self.render_template("split_screen", {
            "leftVideoSrc": left_video,
            "rightVideoSrc": right_video,
            "durationFrames": duration_frames,
            "captionLeft": caption_left or "",
            "captionRight": caption_right or "",
        }, output_path)
