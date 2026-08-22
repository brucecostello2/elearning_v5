# FOR THE IVGS AGENT — Consume MBCP's Operating Envelope and Deployment Spec

**Issued by the operator (Bruce), 2026-08-19.** MBCP is amending its certification export so that every certified model arrives with two new artifacts. This directive tells you what is coming, what IVGS must build to consume it, and why. Implement against the contract below; MBCP's side lands in its next engine batch.

## Why this exists — the MagiHuman lesson

MBCP proved daVinci-MagiHuman renders 1080p talking heads — but only on a machine with 82 GB of RAM and a 128 GB swapfile, in an execution environment that permits paging. Every earlier attempt "proved" the model needed more memory than existed, because container limits silently forbade swap. That knowledge currently lives in an MBCP runbook. If IVGS stands the model up from the weight bundle alone, it will faithfully reproduce the failure and misdiagnose the model.

**The rule going forward: a certified model arrives with its machine requirements, and IVGS refuses to schedule it onto a machine that cannot meet them — loudly, before any GPU time, naming the shortfall.**

## What arrives in the export bundle (the contract)

Alongside the existing attestation and weight reference, two new blocks:

**1. `operating_envelope`** — measured on the certified configuration, every number traceable to a real run:

```
operating_envelope: {
  host_ram_gb:      e.g. 82        // host memory the render peaks at
  swap_gb:          e.g. 10        // swap used at peak; 0 if none
  swap_permitted:   true|false     // true = the workload REQUIRES pageable memory
  scratch_disk_gb:  e.g. 40        // working disk during a render
  gpu_vram_gb:      e.g. 94        // measured GPU peak
  scaling_note:     "host memory grows with clip duration; figures are at 30 s"
  measured_from:    [run ids]
}
```

**2. `deployment` (EngineDeploymentSpec)** — how to actually run the engine: image pinned by digest (the digest carries any patches — never substitute a "same version" image), command, environment variables, mounts, port, GPU claim.

A bundle may lack either block (historical certificates say "not recorded"). **Absent is a fact, not a default: treat a missing envelope as "requirements unknown — operator decision to schedule", never as "no requirements."**

## What IVGS must build

**1. Ingest and store both blocks** with the model registration (AD-01 candidate record). They are part of the model's identity, not documentation.

**2. A placement check at engine bring-up, per stage/model.** Before starting a certified engine on a node:
- host RAM ≥ `host_ram_gb`, or RAM + available swap covers it **and** `swap_permitted` is honoured;
- **if `swap_permitted` is true, the execution environment must actually permit paging** — for containers that means memory-swap limit strictly greater than the memory limit. This is the exact mistake that burned three weeks on the MBCP side: a cap of memory-swap == memory silently forbids swap and the failure blames the model;
- scratch disk and GPU memory likewise;
- **failure is a refusal in plain English before any GPU work**, naming the node, the requirement, the shortfall, and that this is the machine rather than the model. Never a mid-render death.

**3. Launch from the deployment spec, not from a hand-written service definition.** The pinned image digest is load-bearing: MagiHuman's 1080p capability exists only in the patched image the spec names.

**4. Respect the request-side constraints already in the model's contract** (these travel with the adapter/param data, not the envelope): MagiHuman renders only dimensions divisible by 32 — 1080p is rendered at 1920×1088 and trimmed to 1920×1080 by the deliverer; frame rate is fixed by engine config (30 after MBCP's current batch), not per-request.

**5. Surface it.** Wherever IVGS shows which model serves a stage, show whether the current node satisfies the model's envelope — the same honesty rule as everywhere else: "cannot run here (needs 82 GB host RAM, node has 64)" beats a queued job that dies.

## Concrete first case: daVinci-MagiHuman, stage 6 (talking head)

Expect approximately: host_ram_gb 82+ (grows with clip length), swap_permitted TRUE with ~10 GB+ used at 17 s, NVMe-backed swap acceptable (~2% penalty measured), gpu_vram_gb ~94 on a 96 GB card, dimensions /32 with trim-to-1080 on delivery, 30 fps fixed. Exact certified numbers arrive with the bundle after MBCP's 30-second measurement round — build against the contract shape now, not these provisional figures.

## Acceptance

IVGS can take a bundle for a model it has never seen, answer "which of my nodes can run this?" without consulting any MBCP document or person, place it correctly, and refuse incorrect placement with a sentence a human can act on. When that works for MagiHuman — the model whose requirements are the most unusual — the mechanism is proven.
