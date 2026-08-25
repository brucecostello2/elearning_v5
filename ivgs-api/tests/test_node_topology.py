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

# CORRECTED 2026-08-25 (WP-53). These were named *_DECLARED because node-06 was
# off and its row could not be measured -- pinning it to a measurement nobody
# had taken is exactly what WP-24 exists to prevent. The node is on now and it
# HAS been measured: nvidia-smi reports "NVIDIA GeForce RTX 5080", 16303 MiB,
# driver 580.173.02. So these stop being declarations and become measurements,
# and the values change by a factor of six.
#
# Worth recording why the old values were wrong rather than just replacing them:
# CLAUDE.md s2 said the card had been swapped to an RTX 6000 96 GB. It had been
# swapped -- to a consumer 5080. "The card was changed" was true; the card it
# was changed to was not what anyone wrote down.
RTX5080_MEASURED = "NVIDIA GeForce RTX 5080"
VRAM_16_MEASURED = 16303


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
    assert n["gpu_model"] == RTX5080_MEASURED  # Intel B70 swapped out (Draft 3); 5080, not 6000
    assert n["total_vram_mb"] == VRAM_16_MEASURED
    # WP-53: was `is False`, with "declared while the node is off". The node is
    # on and has been measured, so the row is a measurement now.
    assert n["topology_verified"] is True
    assert "cogvideox" in n["services"]  # 2nd video node
    assert "ffmpeg" in n["services"] and "remotion" in n["services"]  # compositor
    assert "Video" in n["role"] and "failover" in n["role"]


def test_the_cuda_video_class_nodes_are_not_one_class():
    """node-02/03 are 96 GB peers. node-06 is not, and the name said it was.

    RENAMED 2026-08-25 (WP-53), from `test_three_cuda_96gb_video_class_nodes`.
    WP-48 had already split the assertions because node-02/03 were MEASURED and
    node-06 was only DECLARED -- but the name kept asserting, in English, that
    all three were 96 GB-class, which is the claim the whole test exists to
    check. node-06 has now been measured at 16303 MiB: it is a sixth of the
    others, not a peer, and the name has to stop saying otherwise.

    This matters beyond tidiness. AD-02 gave node-06 an on-demand fp8-70B
    LLM-failover leg on the strength of 96 GB. See WP-53 D-1.
    """
    for node_id in ("node-02", "node-03"):
        assert NODE_TOPOLOGY[node_id]["gpu_model"] == RTX6000
        assert NODE_TOPOLOGY[node_id]["total_vram_mb"] == VRAM_96
        assert NODE_TOPOLOGY[node_id]["topology_verified"] is True

    n6 = NODE_TOPOLOGY["node-06"]
    assert n6["gpu_model"] == RTX5080_MEASURED
    assert n6["total_vram_mb"] == VRAM_16_MEASURED
    # Measured on the box 2026-08-25, so it is no longer a declaration.
    assert n6["topology_verified"] is True
    # The gap the role still assumes away, pinned so it cannot be forgotten.
    assert n6["total_vram_mb"] < VRAM_96 // 4


def test_no_node_conflates_llm_and_video():
    # AD-02 core invariant: no single node serves both LLM and CogVideoX.
    for node_id, n in NODE_TOPOLOGY.items():
        has_llm = any(s.startswith("vllm") for s in n["services"])
        has_video = "cogvideox" in n["services"]
        assert not (has_llm and has_video), f"{node_id} conflates LLM+video"
