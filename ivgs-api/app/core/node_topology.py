"""The fleet's static node topology, in ONE place.

WP-62 Task 1. This dictionary lived in ``app/api/v1/nodes.py``, which made it
reachable only from the Node Monitor route. The GPU Fleet page needs the same
facts -- which machines carry a GPU at all, what card, how much VRAM, what the
node is FOR -- because the requirement it has failed three times is to show
every GPU-bearing machine whether or not a Celery worker registered it with the
scheduler.

Moving it here rather than importing ``app.api.v1.nodes`` from a service:
``app.core.node_health`` already keeps its own ``_NODES_WITHOUT_GPU`` set
precisely to avoid importing the route module (see that file), so the topology
was already duplicated once for want of a home. This is the home. ``nodes.py``
re-exports ``NODE_TOPOLOGY`` unchanged, so every existing importer -- including
four test modules that import it from there -- keeps working.

NOTHING ABOUT THE FACTS BELOW CHANGED IN THE MOVE. Every measurement, every
correction note and every dispute marker is carried across verbatim; `git show`
on this commit is a pure relocation for the dictionary body.
"""
from typing import Dict, List, Optional

# Static node topology per §2.2; node-02/03/06 per AD-02 Draft 3
# (node-02 LLM-only, node-03 video-only, node-06 = 2nd CUDA video + compositor + LLM failover)
NODE_TOPOLOGY = {
    "node-01": {
        # WP-57 Task 4: CPU-only infrastructure: Postgres, Redis, SeaweedFS, API, frontend. Its celery workers run orchestration, not GPU stages.
        "runs_pipeline_worker": False,
        "hostname": "node-01",
        "role": "Infrastructure",
        "gpu_model": None,
        "total_vram_mb": 0,
        "topology_verified": True,
        "services": ["postgres", "redis", "seaweedfs", "ivgs-api", "ivgs-scheduler", "nginx"],
    },
    "node-02": {
        # WP-57 Task 4: vLLM worker, in the scheduler fleet.
        "runs_pipeline_worker": True,
        "hostname": "node-02",
        "role": "GPU LLM (fp8 Llama-3.3-70B)",
        # Measured 2026-08-23 (WP-24): nvidia-smi reports 97887 MiB, not 98304.
        "gpu_model": "NVIDIA RTX PRO 6000 Blackwell Workstation Edition",
        "total_vram_mb": 97887,
        "topology_verified": True,
        "services": ["vllm-primary", "celery-worker"],
    },
    "node-03": {
        # WP-57 Task 4: cogvideox-worker (NOT celery-worker; that one is profiles:[standby] and is not running - WP-44 S6.3).
        "runs_pipeline_worker": True,
        "hostname": "node-03",
        "role": "GPU Video (CogVideoX/Wan2.1)",
        # Measured 2026-08-23 (WP-24): nvidia-smi reports 97887 MiB, not 98304.
        "gpu_model": "NVIDIA RTX PRO 6000 Blackwell Workstation Edition",
        "total_vram_mb": 97887,
        "topology_verified": True,
        "services": ["cogvideox-server", "cogvideox-worker"],
    },
    "node-04": {
        # WP-57 Task 4: celery-worker, in the scheduler fleet.
        "runs_pipeline_worker": True,
        "hostname": "node-04",
        "role": "GPU Image + TTS + Talking Head",
        # CORRECTED 2026-08-23 (WP-24). This read "NVIDIA RTX 5000 Pro Blackwell"
        # / 49152 MB -- the wrong card at half the real VRAM. Measured on the box:
        # nvidia-smi reports "NVIDIA RTX PRO 6000 Blackwell Workstation Edition,
        # 97887 MiB". Capacity read off this page would have sized jobs against
        # 48 GB on a 96 GB card.
        "gpu_model": "NVIDIA RTX PRO 6000 Blackwell Workstation Edition",
        "total_vram_mb": 97887,
        "topology_verified": True,
        "services": ["comfyui-primary", "coqui-tts", "kokoro-tts", "whisperx",
                     "latentsync", "vllm-midsize", "celery-worker"],
    },
    "node-05": {
        # WP-61 Task 2. BACK IN SERVICE, AND IT IS THE LLM NODE.
        #
        # This row read "OUT OF SERVICE: confirmed host memory fault, memtest
        # test 8, 2026-08-25" with role "Quality services (earmarked)". Both
        # halves are now wrong and each was wrong in a different way:
        #
        #   * The fault was real and is FIXED. The RAM was replaced and the
        #     Proxmox host passed multiple full memtest cycles clean
        #     (operator, 2026-08-26). The VM has 78 GB RAM and the card below.
        #   * The quality-services earmark is SUPERSEDED by operator ruling,
        #     2026-08-26. The CLIP scorer runs on node-06 and node-06 is its
        #     sole host - verified `served_by: node-06`. node-05's old scorer
        #     is stopped and removed. AD-02 Draft 4 proposed the earmark; see
        #     that file's section 7 for the superseding record. History is not
        #     rewritten there and it is not rewritten here.
        #
        # `runs_pipeline_worker` STAYS FALSE, and that is the whole point of
        # the field. node-05 now has a GPU serving a model and NO Celery worker
        # - exactly node-06's shape. It must not enter the scheduler's "3/3",
        # because a vLLM server is not a Celery consumer, and AD-02's
        # `dynamically_loadable=false` stands: its LLM capability is fixed at
        # container start by `--model` and cannot be swapped at runtime.
        "runs_pipeline_worker": False,
        "hostname": "node-05",
        "role": "GPU LLM (Qwen3.8-27B-FP8, translation)",
        # CORRECTED 2026-08-25 (WP-48). This read "NVIDIA RTX 5080" / 16384 MB
        # and the node was documented OFFLINE everywhere -- CLAUDE.md s2,
        # README, AD-02, the functional spec. All three claims were wrong.
        # Measured on the box the same day: nvidia-smi reports "NVIDIA RTX PRO
        # 5000 Blackwell, 48935 MiB, driver 580.173.02", the node answers, and
        # its node-exporter has been UP in Prometheus throughout. A fallback
        # sized against 16 GB on a 48 GB card is the same class of error WP-24
        # corrected on node-04, in the other direction.
        "gpu_model": "NVIDIA RTX PRO 5000 Blackwell",
        "total_vram_mb": 48935,
        "topology_verified": True,
        # WP-61: `vllm-qwen` is DECLARED here from the moment the compose file
        # is tracked, and the honest reading of this list has always been
        # "what this node's stack file defines", not "what answered a probe a
        # second ago" - `status` and `telemetry` are the observations on this
        # payload. The three telemetry entries are observed: node-05 has served
        # node-exporter throughout and its GPU exporter was repaired by WP-48.
        "services": ["vllm-qwen", "node-exporter", "nvidia-gpu-exporter",
                     "node-logs"],
    },
    "node-06": {
        # WP-57 Task 4: Has a GPU and runs the CLIP scorer, but NO Celery worker - which is exactly why the scheduler's count is 3 and not 4.
        "runs_pipeline_worker": False,
        "hostname": "node-06",
        # DISPUTED, and left as-is on purpose. AD-02 gave node-06 an on-demand
        # fp8-70B LLM-failover leg, which was sized against the 96 GB this row
        # used to claim. The card is 16 GB. That leg is not possible on this
        # hardware and the role needs an operator re-ruling, not a silent edit
        # here -- WP-53 D-1. Correcting the measured facts below without
        # touching the role keeps the contradiction visible, which is the point.
        "role": "GPU Video + Compositor + LLM failover",
        # CORRECTED 2026-08-25 (WP-53). This read "NVIDIA RTX 6000 Blackwell" /
        # 98304 MB with topology_verified False, carrying WP-24 D-5's DISPUTED
        # flag because the node was off and could not be measured.
        #
        # It is on now, and it was measured: nvidia-smi reports "NVIDIA GeForce
        # RTX 5080", 16303 MiB, driver 580.173.02. A Proxmox VM on host rtx5080
        # with the card passed through. So the swap CLAUDE.md recorded did not
        # put a 96 GB card in this box -- it is a 16 GB consumer 5080, six times
        # smaller than the row claimed, and the third node-06 hardware claim in
        # this file's history.
        #
        # topology_verified True: this is now a measurement, not a declaration.
        "gpu_model": "NVIDIA GeForce RTX 5080",
        "total_vram_mb": 16303,
        "topology_verified": True,
        # DECLARED, not observed. node-06 has never been provisioned -- it has no
        # /opt/ivgs and, measured from node-01 the same day, only :9100
        # (node-exporter) answers; 9400 and 9430 are closed. Provisioning is an
        # operator job and is deliberately not part of WP-53.
        "services": ["cogvideox", "remotion", "ffmpeg", "celery-worker"],
    },
}


# ---------------------------------------------------------------------------
# Derived views. Computed from the dictionary above so a node added there
# appears on every surface without a second list being edited.
# ---------------------------------------------------------------------------

#: Every node that physically carries a GPU, in fleet order.
#:
#: WP-62 Task 1. "GPU-bearing" is ``total_vram_mb > 0`` and nothing else -- not
#: "registered with the scheduler", not "runs a Celery worker", not "appears in
#: the scheduler's /fleet". Those are three different questions and conflating
#: them with this one is the defect the GPU Fleet page has carried since it was
#: written: it drew the scheduler's registry and called the result "the fleet",
#: so node-05 and node-06 -- each with a card, each serving a model -- were
#: invisible on the page whose title is GPU Fleet Status.
def gpu_node_ids() -> List[str]:
    return [
        node_id
        for node_id, info in NODE_TOPOLOGY.items()
        if int(info.get("total_vram_mb") or 0) > 0
    ]


def topology_for(hostname: Optional[str]) -> Optional[Dict]:
    """The topology row for a hostname, or None if the fleet does not declare it.

    Tolerant on purpose: a worker registered without ``IVGS_NODE_NAME`` reports
    a container hex id, which is not a topology key. Returning None lets the
    caller say "the scheduler knows this node and the topology does not", which
    is a fact worth showing rather than a lookup to crash on.
    """
    if not hostname:
        return None
    return NODE_TOPOLOGY.get(hostname)


def runs_scheduler_worker(hostname: Optional[str]) -> bool:
    """Whether this node is declared to run a pipeline (Celery) worker."""
    info = topology_for(hostname)
    return bool(info and info.get("runs_pipeline_worker"))
