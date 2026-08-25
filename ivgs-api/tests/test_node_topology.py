"""Node topology pins the AD-02 Draft 3 designations.

Guards against regressing to the superseded symmetric node-02/03 roles or the
pre-swap Intel node-06. Capability (queue subscription) lives in the worker
config; this fixes the API-side fleet map that the Node Monitor renders.
"""
from app.api.v1.nodes import NODE_TOPOLOGY

# CORRECTED 2026-08-25 (WP-48). These two constants have been stale since WP-24,
# and both tests that use them have been failing ever since -- unnoticed, because
# nothing runs this suite green. WP-24 measured the real values on the boxes and
# recorded them at nodes.py:48,57: nvidia-smi reports the full product string and
# 97887 MiB, not 98304. The pins below are what the hardware says.
RTX6000 = "NVIDIA RTX PRO 6000 Blackwell Workstation Edition"
VRAM_96 = 97887

# node-06 is OFF, so its row is DECLARED, not measured, and it still carries the
# pre-swap strings. Pinning it to the measured constants above would assert a
# measurement nobody has taken -- the thing WP-24 exists to prevent. It gets its
# own pair, and the fact that they differ is the point.
RTX6000_DECLARED = "NVIDIA RTX 6000 Blackwell"
VRAM_96_DECLARED = 98304


def test_node02_is_llm_only():
    n = NODE_TOPOLOGY["node-02"]
    assert "LLM" in n["role"]
    assert "cogvideox" not in n["services"]  # video removed (AD-02.5)
    assert "vllm-primary" in n["services"]


def test_node03_is_video_only():
    n = NODE_TOPOLOGY["node-03"]
    assert "Video" in n["role"]
    # WP-48: was `"cogvideox" in n["services"]`, an exact-membership test against
    # a list holding "cogvideox-server" / "cogvideox-worker". It has been red
    # since those entries were named. Substring is what was meant.
    assert any(s.startswith("cogvideox") for s in n["services"])
    assert not any(s.startswith("vllm") for s in n["services"])  # LLM removed


def test_node06_is_cuda_video_compositor_failover():
    n = NODE_TOPOLOGY["node-06"]
    assert n["gpu_model"] == RTX6000_DECLARED  # Intel B70 swapped out (Draft 3)
    assert n["total_vram_mb"] == VRAM_96_DECLARED
    assert n["topology_verified"] is False  # declared while the node is off
    assert "cogvideox" in n["services"]  # 2nd video node
    assert "ffmpeg" in n["services"] and "remotion" in n["services"]  # compositor
    assert "Video" in n["role"] and "failover" in n["role"]


def test_three_cuda_96gb_video_class_nodes():
    """node-02/03/06 are all 96 GB-class CUDA peers after the swap.

    WP-48 split this. node-02/03 are MEASURED (WP-24, nvidia-smi on the box);
    node-06 is DECLARED and cannot be measured while it is off. Asserting one
    pair of constants across all three was wrong in both directions, and had
    been failing since WP-24 corrected the measured half.
    """
    for node_id in ("node-02", "node-03"):
        assert NODE_TOPOLOGY[node_id]["gpu_model"] == RTX6000
        assert NODE_TOPOLOGY[node_id]["total_vram_mb"] == VRAM_96
        assert NODE_TOPOLOGY[node_id]["topology_verified"] is True

    n6 = NODE_TOPOLOGY["node-06"]
    assert n6["gpu_model"] == RTX6000_DECLARED
    assert n6["total_vram_mb"] == VRAM_96_DECLARED
    assert n6["topology_verified"] is False


def test_no_node_conflates_llm_and_video():
    # AD-02 core invariant: no single node serves both LLM and CogVideoX.
    for node_id, n in NODE_TOPOLOGY.items():
        has_llm = any(s.startswith("vllm") for s in n["services"])
        has_video = "cogvideox" in n["services"]
        assert not (has_llm and has_video), f"{node_id} conflates LLM+video"
