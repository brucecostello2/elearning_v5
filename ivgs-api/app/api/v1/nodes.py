"""
Node status API endpoints per §5.1.7 — stub for Phase 3.

Endpoints:
- GET    /api/v1/nodes              — Node status for all 6 nodes
- GET    /api/v1/nodes/{node_id}    — Single node detail with GPU metrics

Full implementation with GPU scheduler integration in Phase 8.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import get_current_user
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nodes", tags=["Nodes"])

# Static node topology per §2.2; node-02/03/06 per AD-02 Draft 3
# (node-02 LLM-only, node-03 video-only, node-06 = 2nd CUDA video + compositor + LLM failover)
NODE_TOPOLOGY = {
    "node-01": {
        "hostname": "node-01",
        "role": "Infrastructure",
        "gpu_model": None,
        "total_vram_mb": 0,
        "services": ["postgres", "redis", "seaweedfs", "ivgs-api", "ivgs-scheduler", "nginx"],
    },
    "node-02": {
        "hostname": "node-02",
        "role": "GPU LLM (fp8 Llama-3.3-70B)",
        "gpu_model": "NVIDIA RTX 6000 Blackwell",
        "total_vram_mb": 98304,
        "services": ["vllm-primary", "celery-worker"],
    },
    "node-03": {
        "hostname": "node-03",
        "role": "GPU Video (CogVideoX/Wan2.1)",
        "gpu_model": "NVIDIA RTX 6000 Blackwell",
        "total_vram_mb": 98304,
        "services": ["cogvideox", "celery-worker"],
    },
    "node-04": {
        "hostname": "node-04",
        "role": "GPU Image + TTS + Talking Head",
        "gpu_model": "NVIDIA RTX 5000 Pro Blackwell",
        "total_vram_mb": 49152,
        "services": ["comfyui-primary", "coqui-tts", "latentsync", "celery-worker"],
    },
    "node-05": {
        "hostname": "node-05",
        "role": "GPU Fallback Image + Ollama",
        "gpu_model": "NVIDIA RTX 5080",
        "total_vram_mb": 16384,
        "services": ["comfyui-fallback", "ollama", "celery-worker"],
    },
    "node-06": {
        "hostname": "node-06",
        "role": "GPU Video + Compositor + LLM failover",
        "gpu_model": "NVIDIA RTX 6000 Blackwell",
        "total_vram_mb": 98304,
        "services": ["cogvideox", "remotion", "ffmpeg", "celery-worker"],
    },
}


@router.get("", summary="List all nodes with status")
async def list_nodes(
    current_user: User = Depends(get_current_user),
):
    """
    Node status for all 6 nodes. Polled every 10 seconds by Node Monitor.

    Phase 3 stub: returns static topology. Phase 8 adds live GPU metrics.
    """
    nodes = []
    for node_id, info in NODE_TOPOLOGY.items():
        nodes.append({
            "node_id": node_id,
            "hostname": info["hostname"],
            "status": "online",  # Stub — real status from GPU scheduler in Phase 8
            "role": info["role"],
            "gpu_model": info["gpu_model"],
            "total_vram_mb": info["total_vram_mb"],
            "used_vram_mb": 0,
            "gpu_utilization_pct": 0.0,
            "temperature_c": 0.0,
            "services": info["services"],
            "active_jobs": [],
        })
    return nodes


@router.get("/{node_id}", summary="Single node detail")
async def get_node(
    node_id: str,
    current_user: User = Depends(get_current_user),
):
    """Single node detail with GPU metrics."""
    info = NODE_TOPOLOGY.get(node_id)
    if info is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": f"Node {node_id} not found"}},
        )
    return {
        "node_id": node_id,
        "hostname": info["hostname"],
        "status": "online",
        "role": info["role"],
        "gpu_model": info["gpu_model"],
        "total_vram_mb": info["total_vram_mb"],
        "used_vram_mb": 0,
        "gpu_utilization_pct": 0.0,
        "temperature_c": 0.0,
        "power_draw_w": 0.0,
        "services": info["services"],
        "active_jobs": [],
        "last_heartbeat_at": None,
    }
