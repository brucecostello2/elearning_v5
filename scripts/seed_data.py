#!/usr/bin/env python3
# =============================================================================
# IVGS v5 — Seed Default Data
# =============================================================================
# Spec reference: Appendix D.4 — Seed Data Requirements
#
# Seeds:
#   1. Default global prompts — all 10 prompt types per §9
#   2. Default retention policies — 3 policies per Appendix D.4
#   3. Default fallback policies — 4 scene types per Appendix D.4
# =============================================================================

import os
import sys
from datetime import datetime, timezone
from uuid import uuid4

import psycopg

DATABASE_URL = os.getenv("DATABASE_URL")

# ---------------------------------------------------------------------------
# Default Prompts — 10 prompt types per §9
# ---------------------------------------------------------------------------
DEFAULT_PROMPTS = [
    {
        "prompt_type": "transcript_refinement",
        "name": "Default Transcript Refinement",
        "template": (
            "You are an educational content specialist. Refine the following "
            "transcript for an instructional video. Maintain the original meaning "
            "but improve clarity, structure, and engagement.\n\n"
            "Transcript:\n{{ transcript_content }}\n\n"
            "Target audience: {{ target_audience | default('general') }}\n"
            "Max runtime: {{ max_runtime_seconds }}s\n\n"
            "Output a refined transcript with scene markers."
        ),
    },
    {
        "prompt_type": "storyboard_generation",
        "name": "Default Storyboard Generation",
        "template": (
            "Generate a detailed storyboard from the following refined transcript. "
            "For each scene, provide: scene number, duration estimate, visual "
            "description, camera direction, and transition type.\n\n"
            "Transcript:\n{{ refined_transcript }}\n\n"
            "Output as JSON array of scene objects."
        ),
    },
    {
        "prompt_type": "image_generation",
        "name": "Default Image Generation",
        "template": (
            "Generate a high-quality educational illustration for the following "
            "scene.\n\nScene description: {{ scene_description }}\n"
            "Visual style: {{ visual_style | default('modern, clean, professional') }}\n"
            "Aspect ratio: 16:9\nResolution: 1920x1080"
        ),
    },
    {
        "prompt_type": "video_generation",
        "name": "Default Video Generation",
        "template": (
            "Generate a short video clip for the following scene.\n\n"
            "Scene: {{ scene_description }}\n"
            "Duration: {{ duration_seconds }}s\n"
            "Style: {{ visual_style | default('realistic, educational') }}"
        ),
    },
    {
        "prompt_type": "tts_synthesis",
        "name": "Default TTS Synthesis",
        "template": (
            "Synthesize speech for the following text.\n\n"
            "Text: {{ scene_text }}\n"
            "Language: {{ language_code }}\n"
            "Voice: {{ voice_id | default('default') }}\n"
            "Speed: {{ speed | default(1.0) }}"
        ),
    },
    {
        "prompt_type": "talking_head",
        "name": "Default Talking Head",
        "template": (
            "Generate a talking head video synchronized with the audio.\n\n"
            "Audio file: {{ audio_asset_id }}\n"
            "Face image: {{ face_image_asset_id }}\n"
            "Duration: {{ duration_seconds }}s"
        ),
    },
    {
        "prompt_type": "composition",
        "name": "Default Final Composition",
        "template": (
            "Compose the final video from scene assets.\n\n"
            "Project: {{ project_id }}\n"
            "Resolution: {{ resolution | default('1920x1080') }}\n"
            "Format: MP4 H.264\nCaption style: burned-in, Noto Sans 36pt"
        ),
    },
    {
        "prompt_type": "translation",
        "name": "Default Translation",
        "template": (
            "Translate the following instructional text to {{ target_language }}. "
            "Maintain educational tone and technical accuracy.\n\n"
            "Source ({{ source_language }}): {{ source_text }}"
        ),
    },
    {
        "prompt_type": "scene_description",
        "name": "Default Scene Description",
        "template": (
            "Write a concise visual description for an educational scene.\n\n"
            "Topic: {{ topic }}\nKey concept: {{ key_concept }}\n"
            "Target visual: {{ visual_hint | default('diagram or illustration') }}"
        ),
    },
    {
        "prompt_type": "quality_evaluation",
        "name": "Default Quality Evaluation",
        "template": (
            "Evaluate the quality of the generated asset.\n\n"
            "Asset type: {{ asset_type }}\nExpected: {{ expected_description }}\n"
            "Score criteria: relevance (0-1), technical quality (0-1), "
            "educational value (0-1)"
        ),
    },
]

# ---------------------------------------------------------------------------
# Default Retention Policies — 3 policies per Appendix D.4
# ---------------------------------------------------------------------------
DEFAULT_RETENTION_POLICIES = [
    {
        "name": "standard",
        "hot_days": 30,
        "warm_days": 90,
        "cold_days": 365,
        "description": "Standard retention: 30 days hot, 90 days warm, 365 days cold",
    },
    {
        "name": "long-term",
        "hot_days": 90,
        "warm_days": 180,
        "cold_days": 730,
        "description": "Long-term: 90 days hot, 180 days warm, 730 days cold",
    },
    {
        "name": "compliance",
        "hot_days": 365,
        "warm_days": 730,
        "cold_days": -1,  # -1 = indefinite
        "description": "Compliance: 365 days hot, 730 days warm, indefinite cold",
    },
]

# ---------------------------------------------------------------------------
# Default Fallback Policies — 4 scene types per Appendix D.4
# ---------------------------------------------------------------------------
DEFAULT_FALLBACK_POLICIES = [
    {
        "scene_type": "action",
        "l1_provider": "cogvideox-5b",
        "l2_provider": "cogvideox-2b",
        "l3_provider": "wan21",
        "l4_provider": "static_image_with_ken_burns",
        "description": "Action scene fallback: CogVideoX 5B → 2B → Wan2.1 → Ken Burns",
    },
    {
        "scene_type": "talking_head",
        "l1_provider": "latentsync",
        "l2_provider": "sadtalker",
        "l3_provider": "static_image_with_audio",
        "l4_provider": "audio_only",
        "description": "Talking head fallback: LatentSync → SadTalker → static + audio → audio only",
    },
    {
        "scene_type": "broll",
        "l1_provider": "flux-dev",
        "l2_provider": "sdxl",
        "l3_provider": "sd35",
        "l4_provider": "placeholder_image",
        "description": "B-roll fallback: FLUX.1 Dev → SDXL → SD3.5 → placeholder",
    },
    {
        "scene_type": "title_card",
        "l1_provider": "remotion",
        "l2_provider": "ffmpeg_drawtext",
        "l3_provider": "static_image",
        "l4_provider": "text_only",
        "description": "Title card fallback: Remotion → FFmpeg drawtext → static → text",
    },
]


def seed_prompts(cur) -> int:
    """Seed default global prompts. Returns count of inserted rows."""
    count = 0
    now = datetime.now(timezone.utc)
    for prompt in DEFAULT_PROMPTS:
        cur.execute(
            "SELECT id FROM prompts WHERE prompt_type = %s AND is_global = TRUE",
            (prompt["prompt_type"],),
        )
        if cur.fetchone():
            continue
        cur.execute(
            """
            INSERT INTO prompts (id, prompt_type, name, template, is_global,
                                 created_at, updated_at)
            VALUES (%s, %s, %s, %s, TRUE, %s, %s)
            """,
            (str(uuid4()), prompt["prompt_type"], prompt["name"],
             prompt["template"], now, now),
        )
        count += 1
    return count


def seed_retention_policies(cur) -> int:
    """Seed default retention policies."""
    count = 0
    now = datetime.now(timezone.utc)
    for policy in DEFAULT_RETENTION_POLICIES:
        cur.execute(
            "SELECT id FROM retention_policies WHERE name = %s",
            (policy["name"],),
        )
        if cur.fetchone():
            continue
        cur.execute(
            """
            INSERT INTO retention_policies (id, name, hot_days, warm_days, cold_days,
                                            description, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (str(uuid4()), policy["name"], policy["hot_days"], policy["warm_days"],
             policy["cold_days"], policy["description"], now, now),
        )
        count += 1
    return count


def seed_fallback_policies(cur) -> int:
    """Seed default fallback policies for 4 scene types."""
    count = 0
    now = datetime.now(timezone.utc)
    for policy in DEFAULT_FALLBACK_POLICIES:
        cur.execute(
            "SELECT id FROM fallback_policies WHERE scene_type = %s",
            (policy["scene_type"],),
        )
        if cur.fetchone():
            continue
        cur.execute(
            """
            INSERT INTO fallback_policies (id, scene_type, l1_provider, l2_provider,
                                           l3_provider, l4_provider, description,
                                           created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (str(uuid4()), policy["scene_type"], policy["l1_provider"],
             policy["l2_provider"], policy["l3_provider"], policy["l4_provider"],
             policy["description"], now, now),
        )
        count += 1
    return count


def main() -> int:
    if not DATABASE_URL:
        print("Error: DATABASE_URL not set", file=sys.stderr)
        return 1

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            prompts = seed_prompts(cur)
            retention = seed_retention_policies(cur)
            fallback = seed_fallback_policies(cur)
        conn.commit()

    print("IVGS v5 — Seed Data Complete")
    print(f"  Prompts seeded:          {prompts}/10")
    print(f"  Retention policies:      {retention}/3")
    print(f"  Fallback policies:       {fallback}/4")
    print("✓ Seed data applied successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
