"""WP-31 Lane C spike — payload types shared by workflow and activities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class StageInput:
    job_id: str
    node_id: str
    label: str
    queue: str
    duration_s: float


@dataclass
class StageResult:
    node_id: str
    artifact: str
    ran_on_pid: int
    attempt: int


@dataclass
class SceneInput:
    job_id: str
    scene_index: int
    duration_s: float


@dataclass
class SceneResult:
    scene_index: int
    artifact: str
    ran_on_pid: int
    attempt: int


@dataclass
class FlakyInput:
    job_id: str
    fail_times: int


@dataclass
class PipelineInput:
    job_id: str
    scene_count: int = 6
    # Demonstration 3: run a deliberately failing activity with a bounded
    # retry policy and let the failure surface in workflow state.
    include_failing_activity: bool = False
    failing_activity_fails: int = 99


@dataclass
class PipelineState:
    job_id: str
    current_wave: int = 0
    completed_nodes: List[str] = field(default_factory=list)
    scenes_completed: List[int] = field(default_factory=list)
    waiting_on_signal: str = ""
    failure: str = ""
    finished: bool = False
