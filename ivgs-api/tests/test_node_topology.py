"""Node topology pins the AD-02 Draft 3 designations.

Guards against regressing to the superseded symmetric node-02/03 roles or the
pre-swap Intel node-06. Capability (queue subscription) lives in the worker
config; this fixes the API-side fleet map that the Node Monitor renders.
"""
from app.api.v1.nodes import NODE_TOPOLOGY

RTX6000 = "NVIDIA RTX 6000 Blackwell"
VRAM_96 = 98304


def test_node02_is_llm_only():
    n = NODE_TOPOLOGY["node-02"]
    assert "LLM" in n["role"]
    assert "cogvideox" not in n["services"]  # video removed (AD-02.5)
    assert "vllm-primary" in n["services"]


def test_node03_is_video_only():
    n = NODE_TOPOLOGY["node-03"]
    assert "Video" in n["role"]
    assert "cogvideox" in n["services"]
    assert not any(s.startswith("vllm") for s in n["services"])  # LLM removed


def test_node06_is_cuda_video_compositor_failover():
    n = NODE_TOPOLOGY["node-06"]
    assert n["gpu_model"] == RTX6000  # Intel B70 swapped out (Draft 3)
    assert n["total_vram_mb"] == VRAM_96
    assert "cogvideox" in n["services"]  # 2nd video node
    assert "ffmpeg" in n["services"] and "remotion" in n["services"]  # compositor
    assert "Video" in n["role"] and "failover" in n["role"]


def test_three_cuda_96gb_video_class_nodes():
    # node-02/03/06 are all RTX 6000 96 GB CUDA peers after the swap.
    for node_id in ("node-02", "node-03", "node-06"):
        assert NODE_TOPOLOGY[node_id]["gpu_model"] == RTX6000
        assert NODE_TOPOLOGY[node_id]["total_vram_mb"] == VRAM_96


def test_no_node_conflates_llm_and_video():
    # AD-02 core invariant: no single node serves both LLM and CogVideoX.
    for node_id, n in NODE_TOPOLOGY.items():
        has_llm = any(s.startswith("vllm") for s in n["services"])
        has_video = "cogvideox" in n["services"]
        assert not (has_llm and has_video), f"{node_id} conflates LLM+video"
