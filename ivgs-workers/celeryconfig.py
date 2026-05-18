"""Celery configuration for IVGS Phase 1 workers.

Key Phase 1 additions:
- task_acks_late=True: Task not acknowledged until completion.
  If worker crashes mid-task, broker redelivers it.
- worker_prefetch_multiplier=1: Workers take one task at a time.
  Critical for GPU tasks that need full VRAM focus.
- task_reject_on_worker_lost=True: Requeue tasks on abrupt worker death.

Queue routing:
  default       - transcript, storyboard, motion_graphics, orchestration
  gpu_image     - image_gen (SDXL/FLUX, local GPU)
  gpu_video     - talking_head (D-ID/Synthesia API, also local GPU heavy ops)
  gpu_tts       - tts (OpenAI/ElevenLabs API)
  composition   - FFmpeg composition (CPU/GPU heavy)
"""
import os

# -- Broker & Backend --
broker_url = os.getenv("REDIS_URL", "redis://node-01:6379/0")
result_backend = os.getenv("REDIS_URL", "redis://node-01:6379/0")

# -- Serialisation --
task_serializer = "json"
result_serializer = "json"
accept_content = ["json"]
result_expires = 3600  # Results TTL: 1 hour

# -- Reliability (Phase 1 critical settings) --
task_acks_late = True               # Ack only after task completes
worker_prefetch_multiplier = 1      # One task per worker at a time
task_reject_on_worker_lost = True   # Requeue on worker crash
task_track_started = True           # Record STARTED state in backend

# -- Time limits --
# Soft limit triggers SoftTimeLimitExceeded; hard limit kills worker
task_soft_time_limit = 1800   # 30 minutes soft
task_time_limit = 1860         # 31 minutes hard (60s grace)

# -- Queue routing --
task_routes = {
    "tasks.orchestrator.execute_pipeline_task":    {"queue": "default"},
    "tasks.orchestrator.resume_pipeline_task":     {"queue": "default"},
    "tasks.transcript.refine_transcript_task":     {"queue": "default"},
    "tasks.storyboard.generate_storyboard_task":   {"queue": "default"},
    "tasks.image_generation.generate_images_task": {"queue": "gpu_image"},
    "tasks.tts.generate_tts_task":                 {"queue": "gpu_tts"},
    "tasks.talking_head.generate_talking_head_task":{"queue": "gpu_video"},
    "tasks.motion_graphics.render_motion_graphics_task": {"queue": "default"},
    "tasks.composition.compose_video_task":        {"queue": "composition"},
    "tasks.supervisor.supervise_workers_task":     {"queue": "default"},
}

# -- Celery Beat schedule (periodic tasks) --
beat_schedule = {
    "supervise-workers-every-30s": {
        "task": "tasks.supervisor.supervise_workers_task",
        "schedule": 30.0,
    },
}

# -- Worker settings --
worker_max_tasks_per_child = 50  # Restart worker after 50 tasks (memory leaks)
worker_disable_rate_limits = True

# -- Logging --
worker_hijack_root_logger = False
worker_log_format = "[%(asctime)s: %(levelname)s/%(processName)s] %(message)s"
