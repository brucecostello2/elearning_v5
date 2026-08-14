# ADR-001: Self-Hosted Mandate — v4 Failure Analysis and v5 Rationale

> **Status:** ACCEPTED
> **Date:** May 2026
> **Spec reference:** §1.3, §19.4 — ADR-001 required

---

## Context

IVGS v3 established a solid self-hosted architecture running on a 6-node
Proxmox cluster with vLLM, ComfyUI, Coqui XTTS v2, LatentSync, SeaweedFS,
and PostgreSQL. All AI inference was performed on-premises.

IVGS v4 was an attempted improvement that introduced cloud AI service
dependencies: OpenAI GPT-4 for LLM, DALL-E 3 for image generation,
ElevenLabs for TTS, and D-ID for talking head generation. This violated
the self-hosted mandate established in v3.

## Decision

**IVGS v5 mandates 100% self-hosted AI inference with zero cloud AI
dependencies.** This mandate is absolute and cannot be overridden by any
change request, including those from the Change Review Board.

## v4 Failure Analysis

### What Went Wrong

1. **Architectural violation:** Cloud service dependencies (OpenAI, DALL-E 3,
   ElevenLabs, D-ID) were introduced without formal specification amendment.
2. **Technical debt:** The v4 codebase became non-recoverable due to tight
   coupling with cloud APIs throughout the pipeline code.
3. **Abstraction bypass:** Cloud providers were called directly from task code
   rather than through provider abstraction interfaces, making substitution
   impossible without full rewrite.
4. **No compliance enforcement:** No CI/CD checks existed to prevent
   prohibited dependencies from entering the codebase.
5. **Governance failure:** Changes were implemented without formal change
   control process or stakeholder review.

### Impact

- Codebase declared **non-recoverable** — full rewrite required
- All cloud-dependent features must be rebuilt using self-hosted alternatives
- Operational knowledge from v4 improvements was partially salvageable

### Salvaged from v4

The following operational improvements from v4 were re-implemented in v5
using self-hosted tools:
- Pipeline checkpoint/resume system
- Dead letter queue for failed jobs
- GPU scheduler with VRAM-aware admission control
- Quality scoring pipeline
- Composition manifest system
- Retention policy management

## Enforcement Mechanisms (v5)

### 1. Specification Authority (§1.4)
This specification is the single source of truth. All implementation must
match this document. Deviations require formal amendment.

### 2. CI/CD Compliance Audits (§F.2)
Automated scans for:
- Prohibited environment variables: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
  `ELEVENLABS_API_KEY`, `DID_API_KEY`, `SYNTHESIA_API_KEY`
- Prohibited pip packages: `openai`, `anthropic`, `elevenlabs`
- Prohibited API endpoints: `api.openai.com`, `api.anthropic.com`, etc.
- Prohibited imports: `import openai`, `from anthropic`, etc.

**Build fails on any violation.**

### 3. Change Review Board (§18.1)
Formal CRB with technical lead, stakeholder, and developer representation.
Unanimous consensus required for architectural changes.

### 4. Absolute Prohibitions (§18.3)
The following cannot be approved under any circumstances:
- Introduction of any cloud AI API
- "Phase N temporary" solutions using prohibited services
- Architecture changes bypassing abstraction interfaces
- Silent deviations from specification
- Disabling the CI compliance audit

## Consequences

### Positive
- Full control over AI inference pipeline
- No external service dependencies for runtime operation
- No API cost scaling with usage
- Data remains on-premises at all times
- Reproducible results (model versions pinned)

### Negative
- Higher upfront hardware investment (6-node GPU cluster)
- Model management responsibility (downloads, updates, VRAM planning)
- No access to latest cloud-only models (trade-off accepted)

### Neutral
- Requires dedicated infrastructure team for cluster maintenance
- Model upgrades must go through formal change control

## Related Decisions

- **Provider abstraction interfaces** (§19.1): All AI calls go through abstract
  interfaces, enabling future model swaps without task code changes.
- **Fallback chains** (§6.3): L1→L4 fallback per scene type provides
  resilience against individual model failures.
- **GPU scheduler** (§12): VRAM-aware scheduling prevents OOM failures.
