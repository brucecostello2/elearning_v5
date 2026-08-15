INSTRUCTIONAL TECHNOLOGY GROUP

Instructional Video Generation System
(IVGS)
Version 5.1 Functional Specification

Document Date:
Version:

August 14, 2026
5.1

Supersedes:

v3.0 Specification (self-hosted baseline)

Repository:

github.com/brucecostello2/elearning_v5

AUTHORITATIVE — SINGLE SOURCE OF TRUTH

All amendments require formal change control approval.
Implementation must conform to this document at all times.

I N T E R N A L U S E O N LY |

NOT FOR DISTRIBUTION

IVGS v5 Functional Specification

INTERNAL USE ONLY

Document Control
Table DC-1 Document Identification
Attribute

Value

Document Title

Instructional Video Generation System (IVGS) — Version 5.1 Functional
Specification

Version

5.1

Status

AUTHORITATIVE — Single Source of Truth

Issue Date

August 14, 2026 (v5.1); May 18, 2026 (v5.0 baseline)

Supersedes

v3.0 Functional Specification (all prior versions deprecated)

Repository

github.com/brucecostello2/elearning_v5

Confidentiality

Internal Use Only

Revision History
Ve
rsi

Date

Status

Summary of Changes

Pre-

DEPRECATE

Original self-hosted specification. Defined 6-node Proxmox cluster, vLLM,

May

D

ComfyUI, Coqui XTTS v2, LatentSync, SeaweedFS, PostgreSQL. Solid

on

3.0

2026
4.0

5.0

architectural foundation.

May

DEPRECATE

Compromised implementation that introduced cloud service dependencies (OpenAI

2026

D — NON-

GPT-4, DALL-E 3, ElevenLabs TTS, D-ID talking head). Violated v3 self-hosted

RECOVERAB

mandate. Accumulated technical debt making codebase non-recoverable. Declared

LE

deprecated.

May

CURRENT —

Clean rewrite from v3 baseline with v4 operational improvements extracted and re-

18,

AUTHORITAT

implemented using only self-hosted tools. All cloud dependencies permanently

2026

IVE

removed. Strict change control process introduced. This document supersedes all
prior versions.

5.1

August 14,

CURRENT —

Amendment to v5.0 approved by the change review board 2026-08-14. Six

2026

AUTHORITAT

sections and the glossary amended: orchestration layer moves from Celery/Redis

IVE

to Temporal durable execution (AD-05, ADR-005); node-06 hardware corrected from
Intel B70 Pro to NVIDIA RTX 6000 Blackwell 96 GB, CUDA (AD-02 Draft 3); the
§6.1 stage-count errata is closed (ADR-003). The orchestration amendments
describe the TARGET architecture and take effect at M3 cutover; the transitional
note in §6.4 records what is running until then. All other sections unchanged.

Change Control Requirements
All amendments to this specification require:

2

IVGS v5 Functional Specification

INTERNAL USE ONLY

1. Formal written change request submitted to the technical lead
2. Impact analysis covering compliance, timeline, and resource implications
3. Explicit approval from the change review board before any code changes are made
4. Immediate update to this specification document upon approval
5. Audit trail entry recording the requester, approver, date, and rationale
PROHIBITED ACTIONS

No implementation changes may proceed without prior specification amendment approval. "Phase N
temporary" solutions that violate architecture principles are not permitted. Silent deviations from this
specification will trigger immediate rollback.

Applicable Documents
Document

Status

Notes

IVGS v3.0 Functional Specification

Supersed

Architecture baseline; self-hosted principles

ed

incorporated into v5

Deprecat

Operational enhancements extracted; cloud

ed

dependencies stripped

IVGS v4 Implementation Shortfalls &

Deprecat

Failure analysis used to inform v5 governance rules

Recommendations

ed

IVGS v5 Specification Synthesis

Source

IVGS v4 Phased Deployment Roadmap

Internal working document used to produce this
specification

IVGS v5 Functional Specification Amendment

Applied

The amendment applied to produce v5.1; retained as the

to v5.1 (2026-08-14)

record of what changed and why

AD-02 Node Specialization, Draft 3

Authoritati

node-06 hardware swap (Intel B70 Pro → RTX 6000

(2026-07-07)

ve

Blackwell 96 GB, CUDA) and role redesignation; source
for the §2.2 / §3.1 / §3.2 corrections in v5.1

AD-05 Orchestration Migration (2026-

Authoritati

Celery/Redis → Temporal durable execution; source for

08-14)

ve

the §2.1, §2.4, §2.5, §4.2, §6.2 and §6.4 amendments in
v5.1. Effective at M3 cutover

ADR-003 Pipeline Stage Count Errata

Resolved

Closed by v5.1 §6.1 ("Eight-Stage")

ADR-005 Durable Execution Engine

Accepted

Engine selection rationale and rejected alternatives

ADR-006 Native Postgres Partitioning

Accepted

Supersedes ADR-004 (TimescaleDB, never implemented)

3

IVGS v5 Functional Specification

INTERNAL USE ONLY

Table of Contents
1. Executive Summary

6

1.1 System Purpose and Scope

6

1.2 Key Capabilities

6

1.3 Lessons Learned from v4 Failure

7

1.4 v5 Mandate and Enforcement

8

2. System Architecture

9

2.1 Architectural Pattern

9

2.2 Node Topology and Roles

10

2.3 Network Architecture

12

2.4 Docker Compose Stacks

12

2.5 Microservices Overview

13

3. Hardware Configuration

14

3.1 Node Specifications

14

3.2 GPU Requirements

15

3.3 Storage Architecture

15

4. Database Schema

16

4.1 v3 Core Tables (Content Creation)

16

4.2 v4 Operational Tables (Production Hardening)

22

4.3 Pipeline State Machine

27

5. API Specification

28

5.1 v3 Content CRUD Operations

28

5.2 v4 Monitoring and Operations

32

5.3 Authentication

34

4

IVGS v5 Functional Specification

INTERNAL USE ONLY

6. Pipeline Processing

34

6.1 Eight-Stage Pipeline

34

6.2 Operational Layer

37

6.3 Fallback Chains

38

6.4 Workflow Orchestration

39

7. AI Model Specifications

40

7.1 Mandatory Self-Hosted Models

40

7.2 Explicit Prohibitions

42

8. UI / Dashboard

43

8.1 Content Creation Views

43

8.2 Operational Monitoring Views
8.3 Role-Based Access Control

9. Prompt Management System
10. Digital Asset Management
11. Quality Assurance Pipeline
12. GPU Scheduler Microservice
13. Monitoring and Alerting
14. Backup and Disaster Recovery
15. Deployment Architecture
16. Authentication and Authorization
17. Localization Support
18. Change Control Process
19. Development Standards
Appendix A: Configuration Reference
Appendix B: VRAM Requirements Matrix
Appendix C: API Response Schemas

5

IVGS v5 Functional Specification

INTERNAL USE ONLY

Appendix D: Database Migration Strategy
Appendix E: Glossary
Appendix F: Compliance Checklist

1. Executive Summary
1.1 System Purpose and Scope
The Instructional Video Generation System (IVGS) is a fully self-hosted, AI-powered platform that
automates the production of professional instructional videos from raw source transcripts. The system
accepts uploaded source material (PDF, DOCX, or plain text), refines and structures it using large
language models, generates synchronized visual media (images, video clips, animations), synthesizes
narration audio in multiple languages, renders a lip-synced talking head presenter, and produces
broadcast-quality final video at 1080p and 4K.
IVGS v5 is the authoritative specification for a clean rewrite from the v3 self-hosted baseline,
incorporating operational resilience improvements extracted from the v4 operational experience. The v4
codebase has been declared non-recoverable due to irrecoverable cloud service dependencies. v5 restores
the self-hosted mandate with no exceptions and adds the operational hardening features (checkpointing,
retry policies, quality gates, GPU scheduling, dead letter queue, asset lifecycle management) originally
targeted by v4 — implemented using exclusively self-hosted tools.
System Scope: The v5 specification covers all components of the IVGS platform: content creation
pipeline, digital asset management, GPU scheduler microservice, quality assurance pipeline, monitoring
and alerting infrastructure, backup and disaster recovery, and the unified web dashboard. All AI model
inference runs on the six-node Proxmox cluster. No external AI API calls are permitted under any
circumstances.

6

IVGS v5 Functional Specification

INTERNAL USE ONLY

1.2 Key Capabilities
Capability

Description

Automated video production

End-to-end pipeline from raw transcript to final 1080p/4K MP4 with narration,
visuals, talking head, and captions

Self-hosted AI inference

All LLM, image generation, video generation, TTS, lip-sync, and alignment runs
on local GPU cluster; zero cloud AI dependency

Multi-language support

8 languages: English (US/UK), Spanish, French, German, Mandarin Chinese,
Japanese, Arabic

3-tier prompt management

Jinja2-based prompt hierarchy with per-scope overrides (global / project / scene),
versioning, and rollback

Resilient pipeline execution

Stage-level checkpoints, exponential backoff retries, timeout policies, 4-level
fallback chains, dead letter queue

VRAM-aware GPU scheduling

Dedicated GPU scheduler microservice with bin-packing, admission control,
circuit breaker, priority queues

Automated quality assurance

CLIP-score image validation, FFprobe video validation, SNR audio validation,
lip-sync alignment scoring

4-tier asset lifecycle

Hot (SeaweedFS SSD) → Warm → Cold (NAS) → Archive with automated tier
migration and quota management

Compliance enforcement

CI/CD pipeline scans for prohibited cloud API dependencies; build fails on any
violation

Operational dashboards

Unified Next.js 14 interface: content creation views (v3) + operational monitoring
views (v4) with role-based access

1.3 Lessons Learned from v4 Failure
The v4 implementation introduced cloud service dependencies that fundamentally violated the v3 selfhosted mandate. The following root causes have been identified and must be addressed by governance
mechanisms in v5.
1.3.1 Risk Conflation
The v4 design conflated two separate concerns: (a) operational resilience improvements (checkpoints,
retry policies, GPU scheduling, DLQ) and (b) AI service substitutions (cloud LLM, TTS, image
generation). The legitimate need for operational resilience was used to justify the architectural

7

IVGS v5 Functional Specification

INTERNAL USE ONLY

compromise of introducing cloud AI services. v5 separates these concerns entirely: operational resilience
is implemented using self-hosted infrastructure while all AI inference remains on the local cluster.
1.3.2 "Phase 1 Temporary" Solutions Became Permanent
The v4 phased roadmap explicitly used cloud APIs as "temporary Phase 1" solutions with commitments to
replace them in later phases. The shortfalls analysis and recommendations documents promoted OpenAI
GPT-4, DALL-E 3, ElevenLabs TTS, and D-ID API as concrete implementations. These "temporary"
solutions were never replaced — technical debt accumulated to the point that removal was no longer
feasible. v5 mandates that all implementations use self-hosted tools from day one. No temporary cloud
solutions are permitted under any phase structure.
1.3.3 Lack of Abstraction Layer Made Reversal Impossible
v4 worker tasks directly called specific cloud API endpoints (OpenAI, ElevenLabs, D-ID). Switching to
self-hosted equivalents would have required rewriting every pipeline task. v5 mandates that all AI service
calls

go

through

abstraction

interfaces

( LLMProvider ,

ImageProvider ,

TTSProvider ,

VideoProvider ). The implementation provides the self-hosted engine; the interface enables swap

without task code changes.
1.3.4 No Change Control Process
Architectural decisions in v4 were made without formal specification amendment or approval. Cloud API
keys appeared in configuration templates. Service substitutions were committed without review. v5
establishes a mandatory change review board (Section 18) with formal change request processes, impact
analysis requirements, and audit trail maintenance.
1.3.5 Technical Debt Exceeded Recovery Threshold
The combination of direct cloud API calls in all pipeline tasks, absence of abstraction layers, and
entangled cloud-specific logic made the v4 codebase non-recoverable within a reasonable remediation
timeline. The decision was made to declare v4 deprecated and begin a clean rewrite from the v3 baseline.
v5 is the result of that decision.
1.3.6 Open WebUI Added Unnecessary Complexity
Open WebUI was included in v3/v4 as a prompt testing interface. It duplicated functionality available in
the IVGS dashboard, introduced a separate authentication surface, and created configuration drift risk. v5
permanently removes Open WebUI. Prompt testing is handled by the built-in Prompt Playground
embedded in the IVGS dashboard (Section 8).

8

IVGS v5 Functional Specification

INTERNAL USE ONLY

1.4 v5 Mandate and Enforcement
The v5 mandate is absolute: 100% self-hosted AI inference, zero cloud AI dependencies. This mandate
is enforced through three mechanisms:
1. Specification Authority: This document is the single source of truth. All implementation must
match this specification. Deviations require formal amendment before code changes.
2. CI/CD Compliance Audits: The CI pipeline includes automated scans for prohibited environment
variables ( OPENAI_API_KEY , ANTHROPIC_API_KEY , ELEVENLABS_API_KEY , DID_API_KEY ),
prohibited API endpoints, and prohibited pip/npm packages ( openai , anthropic ,
elevenlabs ). The build fails on any violation.

3. Change Review Board: A formal change review board with stakeholder and technical lead
representation must approve all architectural amendments. Quarterly compliance audits are
conducted post-deployment.

2. System Architecture
2.1 Architectural Pattern
(v5.1: target architecture, effective at M3 cutover. Until cutover the Celery implementation described in
the §6.4 transitional note remains live.)

IVGS v5 uses a microservices architecture with durable workflow execution for pipeline orchestration.
All services run as Docker containers orchestrated via Docker Compose, with one Compose file per
physical node. The frontend communicates with the FastAPI backend via Nginx on node-01.

Pipeline execution is coordinated by a Temporal server on a dedicated orchestration node. A render job
is a single durable workflow spanning all eight stages; each stage executes as an activity on a
capability-scoped task queue, dispatched to workers on the GPU nodes. Workflow state, execution
history, retries and timers are persisted by the orchestration engine, so a job survives worker or node
failure and resumes from its last completed step without operator intervention.

The two human review gates (storyboard approval, draft approval) are implemented as workflow signals:
the workflow blocks at the gate for an unbounded period — days are normal — and resumes when the API
signals approval.

Binary assets are stored in SeaweedFS on node-01; metadata, prompts, and operational state are stored in
PostgreSQL 17 on node-01. Redis is retained as a cache and worker-heartbeat store; it is not a pipeline
message broker. GPU admission control remains the responsibility of the ivgs-scheduler microservice
(§12), which the pipeline invokes from an activity.

Engine rationale and rejected alternatives: ADR-005. Migration design, scope boundary and cutover
procedure: AD-05.

9

IVGS v5 Functional Specification

INTERNAL USE ONLY

Table 2-1 Architectural Layers
Layer

Components

Node(s)

Presentation

Next.js 14 dashboard, video player, prompt editor, node

node-01

monitor
API

FastAPI REST API, WebSocket for live status updates and

node-01

log streaming
Orchestration

Temporal server + Web UI; VideoPipelineWorkflow (8 stages);

node-07 (server/UI),

activity workers; Temporal Schedules for periodic operations

node-01–06 (activity workers)

(v5.1: target architecture, effective at M3 cutover. Until then the
orchestration layer is the Celery task graph, pipeline state machine, Redis
broker and Celery Beat scheduler — node-01 (broker), node-02–06 (workers).
See the §6.4 transitional note.)

GPU Scheduling

ivgs-scheduler microservice (VRAM-aware, admission

node-01 (port 8001)

control)
LLM Inference

vLLM (primary), Ollama (fallback)

node-02, node-03, node-04,
node-05

Image Generation

ComfyUI — FLUX.1 Dev / SDXL / SD3.5 / AnimateDiff

node-04, node-05

Video Generation

CogVideoX 5B, Wan2.1

node-02, node-03

Audio & Talking

Coqui XTTS v2, Kokoro TTS, WhisperX, LatentSync,

node-04

Head

SadTalker

Composition

FFmpeg compositor, Remotion renderer

node-05, node-06

Storage

PostgreSQL 17 (metadata), SeaweedFS (binary assets)

node-01

Cache / Heartbeat

Redis 7.4 — result cache, worker heartbeat registry

node-01

Monitoring

Prometheus + node-exporter + GPU exporters; Grafana

node-01 (server), all nodes

(REQUIRED)

(exporters)

10

IVGS v5 Functional Specification

INTERNAL USE ONLY

2.2 Node Topology and Roles
Table 2-2 Six-Node Cluster — Node Assignments
Nod
e

VR

GPU

AM

nod

None (CPU

e-

VM)

—

Primary Roles

Infrastructure: Next.js frontend, FastAPI backend, PostgreSQL 17, SeaweedFS
(master/volume/filer), Redis, Nginx, Prometheus, Grafana, GPU Scheduler (ivgs-

01

scheduler), CI/CD runner, Celery Beat, Celery default worker

nod

NVIDIA RTX

96

vLLM inference (70B+ models, tensor parallel with node-03), CogVideoX / Wan2.1

e-

6000

GB

video generation

02

Blackwell

nod

NVIDIA RTX

96

vLLM inference (70B+ models, tensor parallel with node-02), CogVideoX / Wan2.1

e-

6000

GB

video generation

03

Blackwell

nod

NVIDIA RTX

48

ComfyUI (FLUX.1 Dev, AnimateDiff), Coqui XTTS v2, Kokoro TTS, WhisperX

e-

5000 Pro

GB

alignment, LatentSync, SadTalker, vLLM mid-size models (Mistral 24B)

04

Blackwell

nod

NVIDIA RTX

16

ComfyUI (SDXL / SD3.5 fallback), Ollama (small models), FFmpeg composition,

e-

5080

GB

utility tasks

NVIDIA RTX 6000

96

Primary FFmpeg compositor; Remotion renderer (lower-thirds, captions, animated

Blackwell

GB

titles, Ken-Burns L2 fill); second CUDA video generation node ( gpu_video );

on-demand fp8-70B LLM failover (profile-gated, stopped by default)

05
nod
e06

Proxmox VM Specifications
Table 2-3 Proxmox VM Configurations
Node

vCPUs

RAM

Boot Disk

Data Disk

GPU Passthrough

node-01

8

16 GB

500 GB SSD

—

None

node-02

16

48 GB

200 GB SSD

2 TB NVMe

RTX 6000 Blackwell 96 GB (#1)

node-03

16

48 GB

200 GB SSD

2 TB NVMe

RTX 6000 Blackwell 96 GB (#2)

node-04

12

32 GB

200 GB SSD

1 TB NVMe

RTX 5000 Pro Blackwell 48 GB

node-05

8

24 GB

200 GB SSD

1 TB NVMe

RTX 5080 16 GB

node-06

8

24 GB

200 GB SSD

1 TB NVMe

RTX 6000 Blackwell 96 GB (#3)

11

IVGS v5 Functional Specification

INTERNAL USE ONLY

All nodes run Ubuntu 24.04 LTS. GPU nodes (node-02 through node-06) use IOMMU/VFIO passthrough
with the NVIDIA Container Toolkit. Every GPU-bearing node is CUDA; the Intel oneAPI/IPEX path is
withdrawn. Proxmox Backup Server (PBS) is configured for weekly VM snapshots on all nodes.

2.3 Network Architecture
All inter-node traffic runs on a private VLAN (192.168.1.0/24). Static IP assignments: node-01 =
192.168.1.90, node-02 = 192.168.1.91, ..., node-06 = 192.168.1.95. A shared NFS volume hosted on
node-01 is mounted at /mnt/ivgs-shared on all nodes. No external internet access is required or
permitted for runtime AI inference.
Table 2-4 Service Network Map
Service

Host

Port

Access

Nginx reverse proxy

node-01

443 HTTPS / 80 HTTP

LAN users

FastAPI Backend

node-01

8001 HTTP

Via Nginx

Next.js Frontend

node-01

3001 HTTP

Via Nginx

GPU Scheduler

node-01

8001 HTTP

Internal only

PostgreSQL 17

node-01

5432 TCP

Internal VLAN only

Redis 7

node-01

6379 TCP

Internal VLAN only

SeaweedFS Master

node-01

9333 HTTP

Internal only

SeaweedFS Volume

node-01

8080 HTTP

Internal only

SeaweedFS Filer

node-01

8888 HTTP

Internal only

vLLM (large models)

node-02, node-03

8000 HTTP

Internal only

vLLM (mid-size)

node-04

8000 HTTP

Internal only

Ollama (fallback)

node-05

11434 HTTP

Internal only

ComfyUI

node-04, node-05

8188 HTTP

Internal only

Coqui TTS / Kokoro

node-04

5002 HTTP

Internal only

LatentSync / SadTalker

node-04

7860 HTTP

Internal only

Remotion Renderer

node-06

3002 HTTP

Internal only

Prometheus

node-01

9090 HTTP

Internal only

Grafana

node-01

3000 HTTP

Internal only (REQUIRED)

GitHub Actions Runner

node-01

Outbound HTTPS

GitHub only

12

IVGS v5 Functional Specification

INTERNAL USE ONLY

2.4 Docker Compose Stacks
node-01 (Infrastructure)
Services:

nginx ,

nextjs-frontend ,

fastapi-backend ,

ivgs-scheduler ,

celery-worker-

default , postgres , redis , seaweedfs-master , seaweedfs-volume , seaweedfsfiler ,

prometheus ,

grafana ,

node-exporter ,

github-actions-runner .

Optional:

loki ,

promtail , alertmanager .

node-02 & node-03 (LLM + Video Diffusion)
Services: vllm (OpenAI-compatible API, GPU-enabled), cogvideox-worker (CogVideoX/Wan2.1
Celery worker), celery-worker (LLM and video generation queues), node-exporter , nvidia-gpuexporter .

node-04 (Image Diffusion, TTS, Talking Head)
Services: vllm (mid-size models), comfyui , coqui-tts , kokoro-tts , whisperx , latentsync ,
sadtalker , celery-worker , node-exporter , nvidia-gpu-exporter .

node-05 (Image Generation, Utility)
Services: comfyui (SDXL/SD3.5 fallback), ollama , ffmpeg-worker , celery-worker , nodeexporter , nvidia-gpu-exporter .

node-06 (Composition, Motion Graphics, Second Video Node)
Services: remotion-renderer , ffmpeg-worker , cogvideox , temporal-worker , node-exporter ,
nvidia-gpu-exporter , and a profile-gated vllm failover service (stopped by default; started on
demand per AD-02 Draft 3, Option C).

node-07 (Orchestration)
Services: temporal , temporal-ui , temporal-worker (default queue), node-exporter .

(v5.1: node-07 and every temporal-worker service are target architecture, effective at M3 cutover.
Until then the GPU nodes run celery-worker and node-01 runs celery-beat . See the §6.4 transitional
note.)

13

IVGS v5 Functional Specification

INTERNAL USE ONLY

2.5 Microservices Overview
Microservi
ce

ivgs-api

Technology

Node

Purpose

FastAPI

node-01

REST API, WebSocket, pipeline orchestration, all business logic

node-01

Unified web dashboard for content creation and operational

(Python)
ivgs-

Next.js 14

frontend

(TypeScript)

ivgs-

FastAPI

node-01

GPU scheduler microservice — VRAM-aware bin packing,

scheduler

(Python)

:8001

admission control, load balancing

ivgs-

Temporal Python SDK

node-01 –

Activity workers — execute pipeline stage activities on

workers

node-06

capability-scoped task queues

temporal

Temporal (Go)

node-07

Durable workflow engine — execution history, timers, retries,
signals, schedules

temporal-ui

Temporal Web

node-07

Operator run inspection: history, inputs/outputs, retries,
timings, failure detail

Periodic operations formerly run by Celery Beat (heartbeat supervision, DLQ processing, orphan cleanup,
retention migration, backup verification, GPU fleet metrics) become Temporal Schedules; the
ivgs-celery-beat microservice is withdrawn.

(v5.1: target architecture, effective at M3 cutover. Until then ivgs-workers runs Celery on node-02 –
node-06 and ivgs-celery-beat runs Celery Beat on node-01. See the §6.4 transitional note.)

3. Hardware Configuration
3.1 Node Specifications
All six nodes are Proxmox VMs running on Ryzen 9 host machines with 64 GB host RAM. The full
hardware specifications are defined in Section 2.2. GPU nodes use IOMMU/VFIO passthrough; GPU
workloads run inside Docker containers with the NVIDIA Container Toolkit (nodes 02–06). All GPU-bearing
nodes are CUDA; the Intel oneAPI/IPEX path is withdrawn (AD-02 Draft 3).
Table 3-1 Per-Node Resource Summary
Node

vCPUs

RAM

Local Storage

Shared NFS

node-01

8

16 GB

500 GB SSD

/mnt/ivgs-shared (host)

node-02

16

48 GB

200 GB SSD + 2 TB NVMe

/mnt/ivgs-shared

node-03

16

48 GB

200 GB SSD + 2 TB NVMe

/mnt/ivgs-shared

node-04

12

32 GB

200 GB SSD + 1 TB NVMe

/mnt/ivgs-shared

node-05

8

24 GB

200 GB SSD + 1 TB NVMe

/mnt/ivgs-shared

node-06

8

24 GB

200 GB SSD + 1 TB NVMe

/mnt/ivgs-shared

14

IVGS v5 Functional Specification

INTERNAL USE ONLY

3.2 GPU Requirements
Table 3-2 GPU Allocations per Node
VRA

Node

GPU Model

node-

NVIDIA RTX 6000

96

Llama 3.3 70B (tensor parallel), CogVideoX 5B (24 GB), Wan2.1

02

Blackwell

GB

(16 GB)

node-

NVIDIA RTX 6000

96

Qwen2.5 72B (tensor parallel), CogVideoX 5B, Wan2.1

03

Blackwell

GB

node-

NVIDIA RTX 5000 Pro

48

FLUX.1 Dev (24 GB), Coqui XTTS v2 (16 GB), LatentSync (12

04

Blackwell

GB

GB), Mistral 24B

node-

NVIDIA RTX 5080

16

SDXL (10 GB), Ollama small models (8 GB), FFmpeg (CPU)

05
node06

M

Primary Models Served

GB
NVIDIA RTX 6000

96

CogVideoX 5B / Wan2.1 (second video node), Remotion, FFmpeg composition,

Blackwell

GB

Llama-3.3-70B-FP8 (failover only)

NVIDIA driver version 570.x or later required. CUDA 12.4+ required for Blackwell architecture GPUs.
All GPU-bearing nodes (node-02 through node-06) are CUDA; the Intel oneAPI/IPEX path is withdrawn.

15

IVGS v5 Functional Specification

INTERNAL USE ONLY

3.3 Storage Architecture
Table 3-3 Storage Subsystems
Subsystem

Technology

Capacity

Purpose

PostgreSQL

SSD (node-01)

500 GB

All metadata, operational tables, prompt versions, audit

datadir
Redis data

logs
RAM (node-01)

64 GB

Celery broker, result backend, session cache, GPU
scheduler state

SeaweedFS hot

SSD volumes

tier

(node-01)

SeaweedFS warm

HDD volumes

tier

(node-01)

NAS cold tier

NFS-mounted NAS

~2 TB

Active binary assets: images, videos, audio, renders (0–
30 days)

~10 TB

Recent project assets (30–90 days)

~20 TB

Archived project assets (90–365 days) via rsync from
SeaweedFS

NAS archive

NFS-mounted NAS

~20 TB

Long-term compressed archives (>365 days, manual
retrieval)

Backup NAS

NFS target

/mnt/backup/i

Daily pg_dump, rsync incremental, config backups (30-

vgs

day retention)

Worker local

NVMe per GPU

1–2 TB per

Model weights, temporary generation artifacts,

NVMe

node

node

intermediate files

4. Database Schema
PostgreSQL 17 on node-01. The v5 unified schema contains 23 tables: 9 v3 core tables for content creation
plus 14 v4 operational tables for production hardening. All tables use UUID primary keys and TIMESTAMPTZ
for timestamps.

4.1 v3 Core Tables (Content Creation)

16

IVGS v5 Functional Specification

INTERNAL USE ONLY

Table 1: projects
Column

Type

Constraints

Description

id

UUID

PK

Project identifier

name

VARCHAR(2

NOT NULL

Video title

55)
description

TEXT

Short description for dashboard display

max_runtime_seco

INTEGER

Target maximum video runtime; constrains transcript

nds
state

refinement
ENUM

NOT NULL, DEFAULT

Pipeline state (see §4.3 for full state machine)

'DRAFT'
hero_image_asset_

UUID

FK → assets.id

Thumbnail/hero image for gallery

UUID

FK → assets.id

Uploaded presenter video clip

TIMESTAMP

NOT NULL, DEFAULT

Creation timestamp

TZ

now()

TIMESTAMP

NOT NULL, DEFAULT

TZ

now()

id
talking_head_asset
_id
created_at

updated_at

Last update timestamp

Table 2: transcripts
Column

Type

Constraints

Description

id

UUID

PK

Transcript identifier

project_id

UUID

FK → projects.id, NOT NULL

Parent project

sequence_order

INTEGER

NOT NULL

User-defined playback order (drag-and-drop)

original_asset_id

UUID

FK → assets.id

Uploaded source file reference (SeaweedFS)

refined_text

TEXT

vLLM-refined transcript text

language_code

VARCHAR(10)

BCP-47 language tag

Index: (project_id, sequence_order)

17

IVGS v5 Functional Specification

INTERNAL USE ONLY

Table 3: storyboard_scenes
Column

Type

Constraints

Description

id

UUID

PK

Scene identifier

project_id

UUID

FK → projects.id, NOT NULL

Parent project

scene_index

INTEGER

NOT NULL

Scene sequence number

narration_text

TEXT

Narration for this scene

visual_description

TEXT

vLLM-generated visual description

media_type

ENUM

image / video_clip / animation

duration_seconds

FLOAT

Target scene duration

Index: (project_id, scene_index)
Table 4: assets
Extended with v4 operational columns for tier management and deduplication.

18

IVGS v5 Functional Specification

INTERNAL USE ONLY

Column

Type

Constraints

Description

id

UUID

PK

Asset identifier

project_id

UUID

FK → projects.id, NOT NULL

Parent project

scene_id

UUID

FK → storyboard_scenes.id,

Associated scene

nullable
asset_type

ENUM

NOT NULL

image / video / audio / document / talking_head /
final_render

seaweedfs_fid

VARCHAR

SeaweedFS file ID (volume,needle format)

seaweedfs_path

VARCHAR

SeaweedFS Filer path

mime_type

VARCHAR

MIME type

file_size_bytes

BIGINT

File size in bytes

duration_seconds

FLOAT

Duration for audio/video assets

language_code

VARCHAR(1

Language variant (null = language-neutral)

0)
generation_prompt_i

UUID

FK → prompts.id

Prompt used to generate this asset

storage_tier

ENUM

DEFAULT 'hot'

hot / warm / cold / archived / deleted (v4 addition)

tier_transition_at

TIMESTAMP

d

Time of last tier transition (v4)

TZ
preserve_flag

BOOLEAN

last_accessed_at

TIMESTAMP

DEFAULT false

Exempt from auto-delete if true (v4)
Last access for LRU tier management (v4)

TZ
content_hash

VARCHAR(6

SHA-256 hash for deduplication (v4)

4)
reference_count

INTEGER

generation_params_

VARCHAR(6

hash

4)

created_at

TIMESTAMP

DEFAULT 1

Reference count for orphan detection (v4)
Idempotency key hash (v4)

NOT NULL

Creation timestamp

TZ

19

IVGS v5 Functional Specification

INTERNAL USE ONLY

Table 5: prompts
Colum

Type

Description

id

UUID PK

Prompt identifier

project

UUID FK → projects.id

Project scope; null = global default

_id

(nullable)

scene_i

UUID FK →

d

storyboard_scenes.id

n

Scene scope

(nullable)
prompt

ENUM

master / transcript_refinement / storyboard_generation / image_generation /

_type

video_generation / animation_generation / tts_voice / talking_head / composition /
translation

prompt

TEXT NOT NULL

Full Jinja2 prompt content

version

INTEGER NOT NULL

Auto-incrementing version per type+scope

is_acti

BOOLEAN DEFAULT

Only one active version per type+scope

ve

false

created

VARCHAR

Username of creator

created

TIMESTAMPTZ NOT

Version creation timestamp

_at

NULL

change

TEXT

_text

_by

Required description of changes

_note

Table 6: users
Column

Type

Description

id

UUID PK

User identifier

username

VARCHAR(64) UNIQUE NOT NULL

Login username

password_hash

VARCHAR NOT NULL

bcrypt-hashed password

role

ENUM NOT NULL

admin / operator / viewer

created_at

TIMESTAMPTZ NOT NULL

Account creation timestamp

last_login_at

TIMESTAMPTZ

Last successful login

20

IVGS v5 Functional Specification

INTERNAL USE ONLY

Table 7: render_jobs
Extended with v4 retry columns.
Column

Type

Description

id

UUID PK

Job identifier

project_id

UUID FK → projects.id

Parent project

celery_task_id

VARCHAR

Celery task reference

job_type

ENUM

Pipeline stage type

node_id

VARCHAR

Executing node (e.g., node-04)

status

ENUM

pending / running / success / failed

started_at

TIMESTAMPTZ

Job start time

completed_at

TIMESTAMPTZ

Job completion time

error_message

TEXT

Error detail if failed

retry_count

INTEGER DEFAULT 0

Current retry attempt number (v4)

max_retries

INTEGER

Maximum retries per retry policy (v4)

failure_category

ENUM

transient / config / external / resource (v4)

Table 8: language_variants
Column

Type

Description

id

UUID PK

Variant identifier

project_id

UUID FK → projects.id

Parent project

language_code

VARCHAR(10) NOT NULL

Target language BCP-47 code

state

ENUM

Localization pipeline state

final_render_1080p_id

UUID FK → assets.id

1080p final render asset

final_render_4k_id

UUID FK → assets.id

4K final render asset

21

IVGS v5 Functional Specification

INTERNAL USE ONLY

Table 9: audit_log
Column

Type

Description

id

UUID PK

Log entry identifier

user_id

UUID FK → users.id

User who performed the action

action_type

VARCHAR NOT NULL

Type of action (CREATE, UPDATE, DELETE, etc.)

resource_type

VARCHAR NOT NULL

Type of resource affected

resource_id

UUID

ID of affected resource

before_payload

JSONB

State snapshot before change

after_payload

JSONB

State snapshot after change

client_ip

INET

Client IP address

timestamp

TIMESTAMPTZ NOT NULL

When the action occurred

Index: (resource_type, resource_id) , timestamp DESC

4.2 v4 Operational Tables (Production Hardening)
Table 10: pipeline_checkpoints
Column

Type

Description

id

UUID PK

Checkpoint identifier

job_id

UUID FK → render_jobs.id

Parent job

stage_name

VARCHAR NOT NULL

Pipeline stage name

stage_index

INTEGER

Stage sequence number

checkpoint_data

JSONB

Intermediate outputs, metadata, generation parameters

output_refs

JSONB

References to generated output files

version_fingerprint

VARCHAR

Reproducibility hash

status

ENUM

pending / complete / failed / skipped

started_at

TIMESTAMPTZ

Stage start time

completed_at

TIMESTAMPTZ

Stage completion time

created_at

TIMESTAMPTZ NOT NULL

Record creation timestamp

Index: (job_id, stage_name)

v5.1 note. From M3 cutover, workflow execution history is the recovery mechanism; recovery is
inherent to the orchestration engine rather than an application concern. pipeline_checkpoints is
retained for historical rows and audit continuity. New rows are not written and
POST /api/v1/jobs/{id}/resume is superseded by workflow reset.

(Historical note: the v5.0 checkpoint write path was never operable — no POST /jobs/{id}/checkpoints
route existed, and the worker-side write failed silently. No checkpoint rows were ever persisted. See
OUTSTANDING_WORK.md v4.0 P1.2.)

22

IVGS v5 Functional Specification

INTERNAL USE ONLY

Table 11: gpu_nodes
Column

Type

Description

id

UUID PK

GPU node identifier

node_hostname

VARCHAR NOT NULL

Node hostname

gpu_index

INTEGER NOT NULL

GPU device index

gpu_model

VARCHAR

GPU model name

total_vram_mb

INTEGER

Total VRAM in megabytes

compute_capability

VARCHAR

CUDA compute capability string

status

ENUM DEFAULT 'online'

online / offline / draining

registered_at

TIMESTAMPTZ

First registration timestamp

last_heartbeat_at

TIMESTAMPTZ

Last heartbeat received

Unique constraint: (node_hostname, gpu_index)
Table 12: gpu_reservations
Column

Type

Description

id

UUID PK

Reservation identifier

gpu_node_id

UUID FK → gpu_nodes.id

Target GPU node

job_id

UUID FK → render_jobs.id

Scheduled job

reserved_vram_mb

INTEGER

Reserved VRAM in megabytes

model_name

VARCHAR

Model to be loaded

status

ENUM

reserved / active / released / expired

reserved_at

TIMESTAMPTZ

Reservation creation time

expires_at

TIMESTAMPTZ

Expiry (5-minute TTL default)

23

IVGS v5 Functional Specification

INTERNAL USE ONLY

Table 13: task_retries
Column

Type

Description

id

UUID PK

Retry record identifier

job_id

UUID FK → render_jobs.id

Parent job

stage_name

VARCHAR

Pipeline stage

attempt_number

INTEGER

Attempt count

failure_type

ENUM

transient / config / external / resource

error_message

TEXT

Error description

error_traceback

TEXT

Full stack trace

retry_after_seconds

FLOAT

Backoff delay before next attempt

created_at

TIMESTAMPTZ NOT NULL

Attempt timestamp

Table 14: worker_heartbeats
Column

Type

Description

id

UUID PK

Heartbeat record identifier

worker_id

VARCHAR NOT NULL

Worker process identifier

node_hostname

VARCHAR

Host node

gpu_index

INTEGER

GPU device index

current_job_id

UUID FK → render_jobs.id (nullable)

Currently executing job

current_stage

VARCHAR

Currently executing stage

heartbeat_data

JSONB

GPU temperature, memory, utilization

last_heartbeat_at

TIMESTAMPTZ NOT NULL

Last heartbeat time

status

ENUM

alive / suspected_dead / confirmed_dead

Index: last_heartbeat_at DESC

24

IVGS v5 Functional Specification

INTERNAL USE ONLY

Table 15: dead_letter_messages
Column

Type

Description

id

UUID PK

DLQ message identifier

original_queue

VARCHAR

Source Celery queue name

task_name

VARCHAR

Celery task name

task_args

JSONB

Task positional arguments

task_kwargs

JSONB

Task keyword arguments

exception_type

VARCHAR

Exception class name

exception_message

TEXT

Error message

traceback

TEXT

Full stack trace

failure_category

ENUM

transient / config / external / resource

retry_count_exhausted

INTEGER

Total retries before DLQ entry

created_at

TIMESTAMPTZ NOT NULL

When message entered DLQ

reviewed_at

TIMESTAMPTZ

When reviewed by operator

reviewed_by

VARCHAR

Reviewing operator username

resolution

ENUM

replayed / discarded / escalated

Index: (failure_category, created_at DESC)

25

IVGS v5 Functional Specification

INTERNAL USE ONLY

Table 16: composition_manifests
Column

Type

Description

id

UUID PK

Manifest identifier

job_id

UUID FK → render_jobs.id UNIQUE

Parent render job

manifest_version

VARCHAR

Schema version string

total_duration_ms

INTEGER

Total video duration in milliseconds

resolution_width

INTEGER

Output width in pixels

resolution_height

INTEGER

Output height in pixels

framerate

INTEGER

Output frames per second

audio_sample_rate

INTEGER

Audio sample rate in Hz

timeline

JSONB

Full timeline structure (scenes → layers)

status

ENUM

draft / locked / rendered / invalid

locked_at

TIMESTAMPTZ

When timeline was frozen for render

rendered_at

TIMESTAMPTZ

When render completed

checksum

VARCHAR(64)

SHA-256 manifest integrity hash

26

IVGS v5 Functional Specification

INTERNAL USE ONLY

Tables 17–23: Remaining Operational Tables
#

Table

Key Columns

Purpose

1

asset_quali

asset_id, quality_score (FLOAT), safety_score, scoring_details

Automated quality validation results per

7

ty_scores

(JSONB), decision (approved/flagged/rejected)

asset

1

render_seg

job_id, segment_index, start_ms, end_ms, output_path,

Segment-based partial render recovery

8

ments

output_checksum, status, attempts

1

gpu_metri

gpu_node_id, gpu_util_pct, mem_util_pct, temperature_c,

Time-series GPU metrics for load

9

cs_history

power_draw_w, active_job_count, queue_depth, recorded_at

balancing. Partitioned daily. 30-day
retention.

2

retention_

name, hot_days, warm_days, cold_days, archive_days,

Asset lifecycle tier transition rules

0

policies

delete_after_days, applies_to, is_default

2

storage_qu

entity_type (user/org), entity_id, max_bytes, current_bytes, tier,

Per-user and per-organization storage

1

otas

alert_threshold_pct

limits

2

backup_re

backup_type, scope, status, backup_path, size_bytes, started_at,

Automated backup and restore tracking

2

cords

completed_at, verified_at, verification_checksum,
retention_days

2

fallback_p

scene_type, level_1_strategy, level_2_strategy, level_3_strategy,

Configurable fallback chains per scene

3

olicies

level_4_strategy

type

4.3 Pipeline State Machine
The projects.state ENUM drives the pipeline state machine. The dashboard status badges and
pipeline tracker UI reflect these states.

27

IVGS v5 Functional Specification

INTERNAL USE ONLY

Table 4-3 Project State Machine
State

Description

Next State(s)

DRAFT

Project created; inputs uploaded; not yet processed

TRANSCRIPT_REFINEMENT

TRANSCRIPT_REFINE

vLLM refining and simplifying uploaded transcripts

STORYBOARD_GENERATIO

MENT
STORYBOARD_GENE

N, ERROR
vLLM generating scene-by-scene storyboard

RATION
MEDIA_GENERATION

MANIFEST_GENERAT

ERROR
Images, video clips, and animations being generated

MANIFEST_GENERATION,

per scene

ERROR

Composition manifest built and locked (v5 addition)

AUDIO_GENERATION,

ION
AUDIO_GENERATION

TALKING_HEAD_REN

MEDIA_GENERATION,

ERROR
TTS generating voice audio per scene for all

TALKING_HEAD_RENDER,

languages

ERROR

LatentSync rendering lip-synced talking head

PROTOTYPE_DRAFT,

DER

ERROR

PROTOTYPE_DRAFT

720p draft assembled for user review

USER_REVIEW, ERROR

USER_REVIEW

Awaiting user approval or modification

FINAL_RENDER

FINAL_RENDER

Full 1080p and 4K composition and encoding

COMPLETE, ERROR

(segment-based)
COMPLETE

Final video available for download

LOCALISATION (optional)

LOCALISATION

Re-processing pipeline for target language variants

COMPLETE, ERROR

ERROR

Pipeline halted; error details in render_jobs table;

Any state (via resume)

resume via checkpoints

5. API Specification
All endpoints are under the

/api/v1/

prefix. All endpoints except

/api/v1/health

and

/api/v1/auth/login require Bearer token authentication. Responses use standard HTTP status codes.

Pagination uses ?page=N&per_page=50 query parameters.

28

IVGS v5 Functional Specification

INTERNAL USE ONLY

5.1 v3 Content CRUD Operations
5.1.1 Authentication
Meth
od
POST

POST

POST

GET

Path

Aut
h

Purpose

/api/v1/auth/l

Non

Issue Bearer token. Body: {username, password} . Returns: {access_token,

ogin

e

token_type, expires_in}

/api/v1/auth/l

Bear

Invalidate session token

ogout

er

/api/v1/auth/r

Bear

efresh

er

/api/v1/health

Non

Issue new token before expiry

Service health check. Returns 200 with service status

e

5.1.2 Projects
Metho
d
GET

Path

Purpose

/api/v1/projects

List all projects with pagination. Supports ?state=DRAFT&search=text
filters.

POST

/api/v1/projects

Create new project. Body: {name, description,
max_runtime_seconds, target_languages[]}

GET

/api/v1/projects/{id}

Get project detail including scene count, job status, asset counts

PATC

/api/v1/projects/{id}

Update project metadata (name, description, max_runtime_seconds)

/api/v1/projects/{id}

Delete project and all associated assets (Admin only). Queues asset cleanup.

POST

/api/v1/projects/{id}/trigger

Trigger pipeline execution from current state

POST

/api/v1/projects/{id}/upload-

Upload talking head presenter clip (MP4/MOV). Returns asset_id.

H
DELE
TE

talking-head

29

IVGS v5 Functional Specification

INTERNAL USE ONLY

5.1.3 Transcripts
Method

Path

Purpose

GET

/api/v1/projects/{id}/transcripts

List transcripts ordered by sequence_order

POST

/api/v1/projects/{id}/transcripts/uplo

Upload transcript files (PDF/DOCX/TXT, multipart). Text extracted

ad

server-side.

/api/v1/projects/{id}/transcripts/{tid

Update refined_text inline or reorder sequence_order

PATCH

}
POST

/api/v1/projects/{id}/transcripts/reor

Bulk reorder. Body: [{id, sequence_order}]

der
DELET

/api/v1/projects/{id}/transcripts/{tid

E

}

Remove transcript from project

5.1.4 Storyboard Scenes
Metho

Path

Purpose

GET

/api/v1/projects/{id}/scenes

List all scenes ordered by scene_index

PATCH

/api/v1/projects/{id}/scenes/{sid}

Update narration_text, visual_description, media_type, or

d

duration_seconds
POST

/api/v1/projects/{id}/scenes/reorder

Bulk reorder. Body: [{id, scene_index}]

POST

/api/v1/projects/{id}/scenes/{sid}/regener

Queue LLM regeneration of a specific scene

ate

5.1.5 Assets
Method

Path

Purpose

GET

/api/v1/projects/{id}/assets

List all assets. Supports ?scene_id=&asset_type=&language_code=
filters.

POST

/api/v1/projects/{id}/assets/u

Upload asset file to SeaweedFS. Returns {id, seaweedfs_fid,

pload

seaweedfs_path}

GET

/api/v1/assets/{id}

Get asset metadata including quality scores

GET

/api/v1/assets/{id}/download

Proxy download from SeaweedFS

POST

/api/v1/assets/{id}/regenerate

Queue asset regeneration using stored generation_prompt_id

DELET

/api/v1/assets/{id}

Delete asset from SeaweedFS and database

E

30

IVGS v5 Functional Specification

INTERNAL USE ONLY

5.1.6 Prompts
Meth

Path

Purpose

GET

/api/v1/prompts

List global prompts. Supports ?prompt_type= filter.

GET

/api/v1/projects/{id}/prompts

List project-level prompts with effective source (SCENE/PROJECT/GLOBAL)

POST

/api/v1/prompts

Create new global prompt version. Body: {prompt_type, prompt_text,

od

change_note}
POST

/api/v1/projects/{id}/prompts

Create project-level override

POST

/api/v1/projects/{id}/scenes/

Create scene-level override

{sid}/prompts
POST

/api/v1/prompts/{id}/restore

Restore a previous version (set is_active = true for that version)

POST

/api/v1/prompts/test

Prompt Playground: send prompt to selected self-hosted model. Body:
{prompt_text, model_id, parameters}

5.1.7 Render Jobs and Node Status
Method

Path

Purpose

GET

/api/v1/projects/{id}/jobs

List render jobs for project, ordered by created_at DESC

GET

/api/v1/jobs/{id}

Get job detail including checkpoint states and retry history

POST

/api/v1/jobs/{id}/cancel

Cancel running job

GET

/api/v1/nodes

Node status for all 6 nodes. Polled every 10 seconds by Node Monitor.

GET

/api/v1/nodes/{node_id}

Single node detail with GPU metrics

WS

/api/v1/nodes/{node_id}/logs

WebSocket stream for live log output from node

WS

/api/v1/jobs/{id}/status

WebSocket stream for real-time job progress

5.1.8 Language Variants
Metho

Path

Purpose

GET

/api/v1/projects/{id}/languages

List language variants with status badges

POST

/api/v1/projects/{id}/languages

Add localization target. Body: {language_code,

d

translation_prompt_override?}
POST

/api/v1/projects/{id}/languages/{l

Retry failed localization pipeline

id}/retry

31

IVGS v5 Functional Specification

INTERNAL USE ONLY

5.1.9 Users (Admin Only)
Method

Path

Purpose

GET

/api/v1/users

List all users

POST

/api/v1/users

Create new user. Body: {username, password, role}

PATCH

/api/v1/users/{id}

Update user role or password

DELETE

/api/v1/users/{id}

Delete user account

5.2 v4 Monitoring and Operations
5.2.1 GPU Management
Method

Path

Purpose

GET

/api/v1/gpu/nodes

List all registered GPU nodes with current status and VRAM utilization

GET

/api/v1/gpu/nodes/{id}/reservations

Active VRAM reservations for a GPU node

POST

/api/v1/gpu/nodes/{id}/drain

Mark node for draining (stop scheduling new jobs)

GET

/api/v1/gpu/utilization

Fleet-wide GPU utilization summary with per-node breakdown

5.2.2 Dead Letter Queue
Metho
d
GET

Path

Purpose

/api/v1/dlq/messages

Paginated list. Supports ?
category=&task_name=&from_date=&to_date= filters.

GET

/api/v1/dlq/messages/{id}

Detail with full traceback and task arguments

POST

/api/v1/dlq/messages/{id}/rep

Re-enqueue original task

lay
POST

/api/v1/dlq/messages/{id}/dis

Mark as discarded with reason

card
GET

/api/v1/dlq/analytics

Failure analytics: counts by category, task, time period

POST

/api/v1/dlq/bulk-replay

Bulk replay by filter criteria

32

IVGS v5 Functional Specification

INTERNAL USE ONLY

5.2.3 Quality Assurance
Method

Path

Purpose

GET

/api/v1/jobs/{id}/quality

All quality scores for a job with per-asset breakdown

GET

/api/v1/quality/flagged

Assets needing human review (decision = flagged)

POST

/api/v1/quality/{score_id}/approve

Manually approve flagged asset

POST

/api/v1/quality/{score_id}/reject

Manually reject flagged asset (triggers regeneration)

5.2.4 Pipeline Checkpoints
Method

Path

Purpose

GET

/api/v1/jobs/{id}/checkpoints

List all stage checkpoints with status

GET

/api/v1/jobs/{id}/checkpoints/{stage}

Get specific stage checkpoint data

POST

/api/v1/jobs/{id}/resume

Trigger pipeline resume from last successful checkpoint

DELETE

/api/v1/jobs/{id}/checkpoints

Clear all checkpoints for full restart

5.2.5 Composition Manifests
Method

Path

Purpose

GET

/api/v1/jobs/{id}/manifest

Get composition manifest with timeline JSON

POST

/api/v1/jobs/{id}/manifest/generate

Build manifest from storyboard and generated assets

POST

/api/v1/jobs/{id}/manifest/lock

Freeze timeline (prevents further modification)

POST

/api/v1/jobs/{id}/manifest/validate

Validate all referenced assets exist and pass checksums

5.2.6 Retention and Quotas
Method

Path

Purpose

GET

/api/v1/retention/policies

List all retention policies

PUT

/api/v1/retention/policies/{id}

Update retention policy tiers and thresholds

GET

/api/v1/retention/report

Asset distribution across tiers, upcoming migrations

GET

/api/v1/quotas/{entity_type}/{entity_id}

Get storage quota, current usage, and alert status

PUT

/api/v1/quotas/{entity_type}/{entity_id}

Set quota limits (Admin only)

33

IVGS v5 Functional Specification

INTERNAL USE ONLY

5.2.7 Backup
Method

Path

Purpose

GET

/api/v1/backup/records

List backup records with status and size

POST

/api/v1/backup/trigger

Trigger on-demand backup (Admin only)

POST

/api/v1/backup/{id}/verify

Trigger integrity verification of a backup

5.3 Authentication Details
All /api/v1/* endpoints except /health and /auth/login require a Bearer token in the
Authorization

header. Tokens are short-lived JWTs (1-hour expiration) signed with a shared secret

from environment variable JWT_SECRET_KEY . Refresh tokens (7-day expiration) are issued alongside
access tokens and stored in Redis. No external auth providers are used.
Table 5-3 Standard Error Response Codes
HTTP Code

Meaning

When

200 OK

Success

GET, PATCH, DELETE (with body)

201 Created

Resource created

POST creates

400 Bad Request

Validation error

Invalid request body or parameters

401 Unauthorized

Missing/invalid token

No or expired Bearer token

403 Forbidden

Insufficient role

Role not permitted for operation

404 Not Found

Resource not found

ID not in database

409 Conflict

State conflict

Operation invalid for current state

422 Unprocessable Entity

Business logic error

Quota exceeded, invalid pipeline state

500 Internal Server Error

Unhandled exception

Unexpected server errors (logged)

6. Pipeline Processing
6.1 Eight-Stage Content Creation Pipeline

34

IVGS v5 Functional Specification

INTERNAL USE ONLY

Stage 1 — Transcript Ingestion and Refinement
Trigger: User uploads transcripts and triggers pipeline. Input: One or more files (PDF, DOCX, TXT)
with user-defined sequence order. Text extraction: PyMuPDF (PDF), python-docx (DOCX). LLM
Engine: vLLM — Llama 3.3 70B on node-02/03. Prompt: transcript_refinement type. LLM
persona: instructional designer. Processing rules: Reduce complexity, eliminate redundancy, align with
max_runtime_seconds , apply Mayer's Multimedia Learning principles, maintain learning intent, target

Flesch-Kincaid Grade 8. Output: Refined transcript stored in transcripts table. Timeout: 120
seconds. Checkpoint: Saved after each transcript file refinement.
Stage 2 — Storyboard Generation
Input: Refined transcripts. LLM Engine: vLLM, Llama 3.3 70B, storyboard_generation prompt.
Output JSON per scene: scene_index , narration_text , visual_description , media_type
(image/video_clip/animation), duration_seconds . Storage: storyboard_scenes table. User gate:
Review, reorder, edit, or regenerate individual scenes. Timeout: 120 seconds.
Stage 3 — Media Generation (Parallel Scene Activities)
Dispatches one parallel activity per scene, routed to appropriate nodes based on media_type and GPU
availability.
Table 6-1 Media Generation Task Routing
Media Type

Prompt LLM

Generation Engine

Node

Timeout

Image

vLLM Mistral 24B (node-04) — FLUX.1-

ComfyUI →

node-04

300s

compatible prompt

FLUX.1 Dev

Same prompt

ComfyUI → SDXL

node-05

300s

CogVideoX 5B or

node-02 /

1800s /

Wan2.1

node-03

30s

AnimateDiff via

node-04

600s

node-06

300s

Image (fallback)

/ SD3.5
Video clip

Animation

vLLM — CogVideoX-compatible prompt

vLLM — AnimateDiff prompt

(ComfyUI)
Animation

ComfyUI
vLLM — Remotion component spec

Remotion renderer

(Remotion)

All generated prompts are stored in the prompts table and are user-editable. All outputs stored in
SeaweedFS. Each generated asset triggers the quality validation pipeline (Section 11) before proceeding.

35

IVGS v5 Functional Specification

INTERNAL USE ONLY

Stage 4 — Composition Manifest Generation (v5 Addition)
Before audio generation, a composition manifest is built from the locked storyboard and generated media
assets. The manifest encodes the full timeline: scene boundaries, layer assignments (background/talking
head/lower-third/captions/audio), asset references with checksums, and render parameters. The manifest
is written to composition_manifests with status draft , then locked (status locked ) after validation
confirms all asset checksums match. Locked manifests cannot be modified; regeneration requires a new
manifest.
Stage 5 — Audio Generation (TTS)
Primary Engine: Coqui XTTS v2 on node-04. Fallback: Kokoro TTS on node-04. Alignment:
WhisperX large-v3 on node-04 — word-level timestamps for caption generation. Audio format: WAV, 48
kHz, 24-bit mono. Prompt type: tts_voice . Quality gate: SNR > 20 dB, clipping < 1%. Timeout:
120 seconds per scene.
Stage 6 — Talking Head Rendering
Input: Uploaded talking-head video clip + full concatenated audio track. Primary Engine: LatentSync
on node-04 (lip-sync score threshold > 0.85). Fallback Engine: SadTalker on node-04. Output: Lipsynced talking-head video stored at /ivgs/talking-heads/{project_id}/{language_code}.mp4 .
Timeout: 600 seconds.

Stage 6 resolves its rendering engine through the AD-01 provider factory using the per-(stage, tier)
model selection, not a hard-coded engine client. A newly certified talking-head model enters production
as a GUI selection, never a code change. (LatentSync and SadTalker above are the current default and
fallback selections, not fixed engines. AD-01 Draft 2 §AD-01.15 records that the live Stage-6 task does
not yet honour this — ledger P1.0 / ORCH-6.)

Stage 7 — Prototype Draft Assembly
Compositor: FFmpeg on node-06 (primary), node-05 (overflow). Components: talking-head overlay,
scene media, audio track, lower-thirds and captions (Remotion on node-06). Resolution: 720p draft for
rapid review. Post-assembly: Project state transitions to USER_REVIEW ; user notified via dashboard.
Timeout: 900 seconds.
Stage 8 — Final Render (Segment-Based)
Trigger: User approval from USER_REVIEW state. Compositor: FFmpeg on node-06. Segment
planning: Manifest split into 10–30 second segments stored in render_segments . Segments rendered in
parallel where GPU capacity allows. Failed segments retry independently without discarding completed
segments. Final assembly via FFmpeg concat demuxer.
Table 6-2 Final Render Output Specifications
Format

Resolution

Video Codec

Quality

Audio

FPS

1080p MP4

1920×1080

H.264 (libx264)

CRF 18, VBV 8 Mbps

AAC 192 kbps, 48 kHz stereo

30

4K MP4

3840×2160

H.265 (libx265)

CRF 20, VBV 20 Mbps

AAC 256 kbps, 48 kHz stereo

30

36

IVGS v5 Functional Specification

INTERNAL USE ONLY

FFmpeg Composition Layout
Table 6-3 Video Composition Layer Stack
Layer

Content

Position

Background

Scene image / video clip / animation

Full frame

Talking

Lip-synced presenter (chroma-key or PiP)

Bottom-right or full-

Head

screen

Lower Third

Scene title / key term overlay (Remotion-rendered)

Bottom 20% of frame

Captions

Burned-in subtitles from WhisperX timestamps (Noto Sans, 36pt at

Bottom center

1080p)
Audio

TTS voice track (WAV 48 kHz)

—

6.2 Operational Layer
Every pipeline stage in v5 is wrapped with the following operational guarantees:
(v5.1: the subsections below describe the target architecture under AD-05, effective at M3 cutover.
Until then the Celery implementation and its recorded defects apply — see the §6.4 transitional note.)

Durable Execution
Every stage runs as an activity within a durable workflow. Workflow state and every completed step are
persisted to execution history as they occur. On worker crash, node failure, or restart, the workflow
resumes from its last completed step — completed stages are never re-executed. No application-level
checkpointing is required.
Retry Policies
Retry is declared per activity and enforced by the orchestration engine. The per-stage attempt counts and
backoff sequences below are preserved as configured values.

Non-retriable failures are declared as non_retryable_error_types and fail immediately rather than
consuming attempts. The dead_letter_messages table (Table 15) is retained as the operator audit
record; replay is performed by workflow reset rather than by re-queueing a message.

Table 6-4 Retry Policy per Stage Type
Stage Type

Max attempts

Backoff Sequence

On Exhaustion

LLM (transcript, storyboard)

4

5s → 15s → 45s → 135s

Workflow failure, operator-visible

Image generation

3

10s → 30s → 90s

Fallback chain, then workflow failure

Video generation

2

30s → 90s

Fallback chain, then workflow failure

TTS audio

3

10s → 30s → 90s

Kokoro fallback, then workflow failure

Talking head

2

30s → 90s

SadTalker fallback, then workflow failure

Composition / FFmpeg

2

30s → 90s

Workflow failure

37

IVGS v5 Functional Specification

INTERNAL USE ONLY

Timeout and Liveness Policies
Each activity declares a start_to_close_timeout — the per-model values of Table 6-5 — and a
heartbeat_timeout . Long-running activities (video generation, talking-head render, FFmpeg segment
render) heartbeat while working.

Liveness is therefore reported, not inferred. An activity that is slow but progressing is not interrupted;
one that has stopped progressing fails within its heartbeat timeout. There is no message visibility timeout
and no possibility of a task being redelivered while still executing.

Table 6-5 Per-Model Timeout Thresholds
Model / Service

Timeout

Warning at

vLLM (transcript/storyboard)

120s

60s, 90s, 120s

ComfyUI / FLUX.1 Dev

300s

150s, 225s, 300s

CogVideoX 5B

1800s

900s, 1350s, 1800s

Wan2.1

30s

15s, 22s, 30s

Coqui XTTS v2 / Kokoro

120s

60s, 90s, 120s

LatentSync

600s

300s, 450s, 600s

FFmpeg composition

900s

450s, 675s, 900s

Idempotency
Deduplication is provided at two levels. Each render job runs under a deterministic workflow ID, so a
duplicate trigger attaches to the running workflow rather than starting a second one. Within Stage 3, the
generation_params_hash content check is retained: before executing any generation activity the worker
computes a SHA-256 hash of the activity parameters, and if a completed asset with the same hash exists
in the database the activity returns the cached result without re-executing.

Worker Liveness
Workers report liveness by polling their task queues; a worker that stops polling has its in-flight activities
timed out and retried on another worker of the same capability. The separate 10-second Redis heartbeat is
retained for GPU telemetry (temperature, memory, utilisation) feeding the scheduler and dashboards — a
monitoring concern, distinct from work distribution.

GPU Reservation
Each GPU-bearing stage brackets its work with acquire_gpu_reservation and
release_gpu_reservation activities against ivgs-scheduler (§12), with release guaranteed in the
workflow's finally block. Reservation failure is fatal to the stage and retried under the stage's retry
policy — it does not soft-skip. (v5.0 behaviour was fail-open, which concealed an empty node registry for
an extended period; see OUTSTANDING_WORK.md v4.0 P1.3 and P2.6.)

6.3 Fallback Chains
Media generation failures trigger a 4-level fallback chain before routing to the DLQ:

38

IVGS v5 Functional Specification

INTERNAL USE ONLY

Table 6-6 Media Generation Fallback Chain
Level

Strategy

Description

Phase Status

L1 — AI Video

ai_video

CogVideoX 5B or Wan2.1 video clip

Enabled after maturity

generation

proven (Phase 2+)
Phase 1 default primary

L2 — Animated

animated_s

Ken Burns pan/zoom on generated image

Still

till

(MotionGraphicsService)

L3 — Static

zoom_pan

Simple FFmpeg zoom and pan on static image

Fallback to L2

L4 — Static

static_ima

Static image only, no motion

Last resort before DLQ

Image

ge

Pan/Zoom

Fallback chain configuration is stored in the fallback_policies table, configurable per scene type
(action, talking_head, broll, title_card).

6.4 Workflow Orchestration
A render job executes as a single durable workflow, VideoPipelineWorkflow , spanning all eight stages.
Sequencing is expressed as ordinary control flow — each stage is an awaited activity call — rather than as
a lookup table of task names. A reference to a non-existent stage is therefore a load-time error, not a
runtime dispatch failure.

Stage sequence. Stages 1 → 2 → [gate] → 3 → 4 → 5 → 6 → 7 → [gate] → 8, as defined in §6.1.

Fan-out and join. Stage 3 fans out one activity per scene and joins by awaiting all handles. There is no
counter, no join watchdog, and no compensating sweeper. A failed scene is drained and recorded; the
workflow advances to Stage 4 with a failed_count and whatever media rendered (partial advance),
preserving v5.0 behaviour.

Human gates. Both review gates are workflow signals. The workflow blocks at wait_condition until the
API signals approval; the API's approval endpoints signal the running workflow rather than dispatching a
task. Gates additionally accept reject / regenerate signals, and every workflow accepts cancel_job .

Segment rendering. Stage 8's segment render, and the parallel talking-head render, execute as child
workflows — one per segment — each with its own retry policy and heartbeating. Segment planning
remains application logic ( segment_planner ); the render_segments table is an operator-facing record,
not the resume mechanism.

Progress and state. Pipeline state is exposed by workflow query and is truthful by construction.
projects.state is retained as a denormalised read model for the dashboard, written from the workflow; it
is not the source of truth.

Table 6-7 Task Queue Routing

Celery queues become Temporal task queues. Node assignments follow AD-02 Draft 3 and differ from the
v5.0 table: node-02 is LLM-only, node-03 is video-only, and node-06 becomes a second video node and the
primary compositor.

Queue

Workers

Activity types

default

node-01, node-07

Orchestration, admin, scheduled operations

gpu_llm

node-02, node-04 (node-06

vLLM inference — transcript refinement, storyboard

failover)

gpu_image

node-04, node-05

ComfyUI image and animation generation

gpu_video

node-03, node-06

CogVideoX / Wan2.1 video generation

gpu_tts

node-04

Coqui XTTS v2, Kokoro TTS, WhisperX alignment

gpu_talking_hea

node-04

Provider-resolved lip-sync rendering

node-06, node-05

FFmpeg composition, Remotion rendering

d
composition

39

IVGS v5 Functional Specification

INTERNAL USE ONLY

Key configuration. Activity concurrency of 1 per worker on GPU queues prevents VRAM contention.
Workflow code is deterministic and performs no I/O; all external interaction occurs in activities. Workflow
logic changes ship behind version gates, and a replay test runs against captured histories before any
worker deployment — a requirement, not a convention, because multi-hour renders and multi-day review
gates mean workflows are always in flight during a deployment.

Scheduled operations (heartbeat supervision, DLQ processing, orphan cleanup, retention migration,
backup verification, GPU fleet metrics) run as Temporal Schedules. Celery Beat is withdrawn.

Transitional note (v5.1, until M3 cutover). The implementation at the time of this amendment uses
Celery with a Redis broker and event-driven handle_stage_completion callbacks, per v5.0 §6.4. In that
implementation the pipeline uses event-driven dispatch (not Celery chains): when a stage completes
successfully the callback determines the next stage and enqueues the corresponding task. Its key Celery
configuration is task_acks_late = True (message not acknowledged until the task completes),
worker_prefetch_multiplier = 1 (prevents VRAM starvation), and
task_reject_on_worker_lost = True (auto-requeue on worker crash); Celery Beat is REQUIRED for DLQ
processing (every 5 minutes), orphan cleanup (daily), retention tier migration (daily), backup verification
(daily) and heartbeat supervision (every 30 seconds). That implementation carries four recorded
correctness defects ( OUTSTANDING_WORK.md v4.0 P0.1, P1.1–P1.3), remediated under Master Plan M2.
This section describes the architecture approved under AD-05 and takes effect at M3 cutover. Migration
sequence, scope boundary, verification gate and rollback: AD-05 §11–§12.

7. AI Model Specifications
7.1 Mandatory Self-Hosted Models
7.1.1 Large Language Models — vLLM
Table 7-1 vLLM Configuration
Model

Nodes

VRAM

Context

Purpose

Llama 3.3

node-02 + node-03 (tensor

96 GB ×

128K

Primary LLM: transcript refinement,

70B

parallel)

2

tokens

storyboard generation

Qwen2.5

node-02 + node-03 (tensor

96 GB ×

128K

Alternative LLM (CJK languages, code-heavy

72B

parallel)

2

tokens

content)

Mistral 24B

node-04

48 GB

32K

Mid-size LLM: image prompt generation,

tokens

scene analysis

vLLM serves an OpenAI-compatible API at http://node-0X:8000/v1 . Tensor parallelism for 70B+
models uses NCCL over the 10GbE VLAN. All vLLM calls go through the LLMProvider abstraction
interface.
7.1.2 LLM Fallback — Ollama
Model

Node

VRAM

Purpose

Llama 3.2 8B

node-05

8 GB

LLM fallback for development, low-priority tasks

Phi-3 Medium

node-05

8 GB

Fast inference for utility tasks

Gemma 2 9B

node-05

8 GB

Fallback option

40

IVGS v5 Functional Specification

INTERNAL USE ONLY

7.1.3 Image Generation — ComfyUI
Model

Node

VRAM

Resolution

Steps

Purpose

FLUX.1 Dev

node-04

24 GB

1024×1024

50

Primary image generation for scene visuals

FLUX.1 Schnell

node-04

16 GB

1024×1024

4

Rapid prototyping variant

SDXL 1.0

node-05

10 GB

1024×1024

30

Fallback image generation

SD 3.5 Medium

node-05

10 GB

1024×1024

30

Style-specific fallback

AnimateDiff

node-04

16 GB

512×512

30

Animated image sequences

7.1.4 Video Generation
Model

Node

VRAM

Max Clip

Resolution

Timeout

CogVideoX 5B

node-02 / node-03

24 GB

6 seconds

480p

1800s

CogVideoX 2B

node-02 / node-03

14 GB

6 seconds

480p

900s

Wan2.1

node-02 / node-03

16 GB

5 seconds

720p

30s/segment

7.1.5 Text-to-Speech — Coqui XTTS v2
Node: node-04. VRAM: 16 GB. Supported languages: 8 (en-US, en-GB, es-ES, fr-FR, de-DE, zh-CN,
ja-JP, ar-SA). Features: voice cloning (speaker reference clip), SSML-compatible emphasis markers,
natural prosody. Audio output: WAV 48 kHz 24-bit mono. Fallback: Kokoro TTS (English-only, lower
VRAM, faster).
7.1.6 Alignment — WhisperX
Model: WhisperX large-v3. Node: node-04. Output: Word-level timestamps used for caption generation
and talking head alignment. Output formats: SRT (word-level), VTT (web player), burned-in subtitles
(FFmpeg subtitles filter, Noto Sans CJK+RTL, 36pt at 1080p / 72pt at 4K).
7.1.7 Talking Head — LatentSync / SadTalker
Primary: LatentSync on node-04 (12 GB VRAM, 30 fps). Lip-sync quality threshold: alignment score >
0.85. Fallback: SadTalker on node-04 (8 GB VRAM). Input: talking-head video clip (user-uploaded,
MP4/MOV). Output: lip-synced video stored at /ivgs/talking-heads/ . Timeout: 600 seconds.
7.1.8 Motion Graphics — Remotion
Node: node-06. Technology: Remotion (React-based animation engine). Use cases: lower-third overlays,
animated titles, data visualization animations, scene transition graphics. Fallback role: Ken Burns
animated stills (L2 fallback) and pan/zoom effects (L3 fallback).

41

IVGS v5 Functional Specification

INTERNAL USE ONLY

7.2 Explicit Prohibitions
PERMANENT PROHIBITION — V5 MANDATE

The following services and APIs are permanently banned from IVGS v5. Their introduction in v4 caused the
codebase to become non-recoverable. No exceptions, no phase exemptions, no temporary allowances.
Table 7-2 Prohibited Cloud AI Services
Category

Prohibited Service / Package

Self-Hosted Replacement

Cloud LLM

OpenAI GPT-3.5, GPT-4, GPT-4o; openai pip

vLLM + Llama 3.3 70B / Qwen2.5

package
Cloud LLM

Anthropic Claude; anthropic pip package

vLLM + Llama 3.3 70B

Cloud LLM

Google Gemini API

vLLM + Qwen2.5

Cloud LLM

AWS Bedrock, Azure OpenAI, Google Vertex AI

vLLM self-hosted

Cloud Image

OpenAI DALL-E 2, DALL-E 3

ComfyUI + FLUX.1 Dev

Cloud Image

Midjourney API

ComfyUI + FLUX.1 Dev

Cloud Image

Stability AI hosted API

Self-hosted SDXL/SD3.5 via
ComfyUI

Cloud

Runway, Pika Labs

CogVideoX, Wan2.1

OpenAI TTS; ElevenLabs; elevenlabs pip

Coqui XTTS v2 / Kokoro TTS

Image/Video
Cloud TTS

package
Cloud TTS

Google Cloud TTS; Amazon Polly

Coqui XTTS v2

Cloud Talking

D-ID API; did_api_key env var

LatentSync / SadTalker

Synthesia API; HeyGen API

LatentSync / SadTalker

Cloud STT

OpenAI Whisper API; Google STT

Self-hosted WhisperX large-v3

Cloud Storage

AWS S3, S3 Glacier; Google Cloud Storage

SeaweedFS + NAS archival

Cloud Queue

Amazon SQS, Google Pub/Sub

Redis Celery broker

Head
Cloud Talking
Head

42

IVGS v5 Functional Specification

INTERNAL USE ONLY

Permitted External Services (Non-AI)
Service

Purpose

Notes

GitHub

Code hosting, CI/CD runner, GHCR container registry

Build-time and deployment only

NTP servers

Time synchronization across cluster

chrony on each node

apt / pip / npm

Package installation

Build-time only; pinned versions required

8. UI / Dashboard
The IVGS dashboard is a unified Next.js 14 (TypeScript) application served on node-01 via Nginx. It merges
the v3 content creation interface with v4 operational monitoring views into a single role-aware application.
Open WebUI is permanently removed; prompt testing is handled by the built-in Prompt Playground.

8.0 Navigation Structure
Top Navigation: Dashboard | New Project | Node Monitor | Admin (role-gated). Sidebar in expanded
views: content sections and operational sections based on user role.

8.1 Content Creation Views (All Authenticated Users)
8.1.1 Video Gallery (Dashboard Home)
Responsive grid of hero image cards, one per project. Each card displays: hero image/thumbnail, video
title, short description, runtime estimate, state badge (DRAFT / IN PROGRESS / REVIEW /
COMPLETE / ERROR), and language variant chips. Clicking a card opens the Project Modal showing
full description, runtime, link to Project Detail, link to Video Player, and language variant selector.

43

IVGS v5 Functional Specification

INTERNAL USE ONLY

8.1.2 New Project / Input Form
Table 8-1 New Project Form Fields
Field

Input Type

Validation

Video Name

Text input

Required, max 255 chars

Description

Textarea

Optional, max 1000 chars

Maximum Runtime

Number (minutes:seconds)

Required, 1–120 minutes

Talking Head Clip

File upload (MP4/MOV)

Required, max 500 MB

Voice Transcripts

Multi-file upload (PDF/DOCX/TXT)

Required, at least one file

Transcript Order

Drag-and-drop reorder list

User sets sequence

Existing Storyboard

File upload (PDF/DOCX, optional)

Optional

Target Languages

Multi-select dropdown

Optional at creation

44

IVGS v5 Functional Specification

INTERNAL USE ONLY

8.1.3 Project Detail Page (Tabbed Navigation)
Table 8-2 Project Detail Tabs
Tab

Features

Overview

Project metadata, state timeline, runtime estimate, pipeline progress tracker

Transcripts

Original uploads + refined transcript side-by-side diff; inline edit of refined text; reorder uploads

Storyboard

Scene cards with narration, visual description, media type, duration; edit, regenerate, reorder scenes

Media

Grid of generated images/clips/animations per scene; quality score badge; generation prompt with edit

Assets

button; regenerate

Audio

Per-scene audio player with waveform; quality score (SNR); regenerate button per scene

Talking

Preview of rendered talking head video; lip-sync alignment score

Head
Draft

Embedded video player for 720p prototype draft

Preview
Final

Download links for 1080p and 4K MP4; SRT/VTT captions; language variant selector

Renders
Prompts

Full 3-tier prompt management (global/project/scene); version history; Prompt Playground test
interface

Jobs

Pipeline job history: status, node, stage, timing, error details, retry count; checkpoint resume button

Languages

Language variant table with status badges; Add Language button; Retry button for failed variants

8.1.4 Video Player
Embedded HLS-compatible player (Video.js or Plyr). Features: quality selector (1080p / 4K), language
selector for localized variants, subtitle/caption toggle (burned-in + VTT), chapter navigation, download
button for MP4 and SRT.
8.1.5 Node Monitor Page
Card grid: one card per node (node-01 through node-06). Each card shows: node name, online/offline
status, GPU model, VRAM total/used (progress bar), GPU utilization %, GPU temperature (color coded:
green <70°C / amber 70–85°C / red >85°C), GPU power draw vs TDP, CPU/RAM mini-bars, current
active job. Polls /api/v1/nodes every 10 seconds. Node Detail Modal: live-streaming log output
(WebSocket), log level filter, free-text search, log download, historical job list.

45

IVGS v5 Functional Specification

INTERNAL USE ONLY

8.1.6 Prompt Playground
Replaces Open WebUI. Accessible from the Prompts tab and from Settings. Features: self-hosted model
selector (lists only vLLM models and Ollama models — no cloud options), parameter tuning
(temperature, max_tokens, top_p), prompt input with Jinja2 syntax highlighting, response display,
conversation history, comparison view (test same prompt against two models). Results can be saved as
new prompt versions directly from the Playground.

8.2 Operational Monitoring Views (Admin Focus)
8.2.1 Pipeline Progress Tracker
Visual stage DAG (directed acyclic graph) showing all pipeline stages with status indicators
(pending/running/complete/failed). Displays checkpoint data for each stage, estimated completion time,
fallback level indicator (L1–L4 or DLQ), and Resume button for ERROR state projects. Real-time
updates via WebSocket.
8.2.2 GPU Fleet Status
Per-GPU cards: model, total/used VRAM (progress bar), temperature gauge, active job with stage, status
badge, drain toggle. Fleet utilization chart (line graph, last 30 minutes). Queue depth per GPU. Model
residency heatmap (which models are currently loaded on which GPUs). Data sourced from GPU
scheduler ( /api/v1/gpu/utilization ) and Prometheus metrics.
8.2.3 Dead Letter Queue Dashboard
Message table with columns: task name, failure category, error message (truncated), retry count, entered
DLQ at. Filters: category (transient/config/external/resource), date range, task name. Detail modal: full
stack trace, task arguments, resolution history. Actions: Replay, Discard. Failure analytics charts: count by
category (pie), failure rate trend (line graph), top failing tasks (bar chart). Bulk operations: replay all
transient failures, discard all older than N days.
8.2.4 Quality Review Queue
Grid of assets with decision = flagged . Each card: asset thumbnail/preview, quality score, safety
score, per-metric breakdown (CLIP score / SNR / frame consistency), project and scene context. Actions:
Approve (allows pipeline to proceed), Reject (triggers regeneration). Approve/Reject decisions are logged
in audit_log .

46

IVGS v5 Functional Specification

INTERNAL USE ONLY

8.2.5 Composition Timeline Editor
Horizontal

timeline

editor

showing

all

scenes

and

layers.

Color-coded

by

status

(pending/rendering/complete/failed). Zoom and pan controls. Manifest lock status indicator. Failed
segment retry button. Per-segment progress bars. Overall render progress (%) with ETA.
8.2.6 Storage Analytics
Tier usage breakdown (hot/warm/cold/archive): used vs. allocated capacity per tier. Asset count and size
by tier. Deduplication savings (estimated %). Quota utilization per user (top 10 consumers). Upcoming
tier migrations (assets due to transition in next 7 days). Orphan asset report.

8.3 Role-Based Access Control
Table 8-3 Dashboard Feature Access by Role
Feature Area

Admin

Operator

Viewer

Video Gallery

All projects

Own projects

Read-only

New Project / Upload

Yes

Yes

No

Edit Transcripts/Storyboard

Yes

Own projects

No

Global Prompt Management

Yes

No

No

Project/Scene Prompts

Yes

Own projects

No

Prompt Playground

Yes

Yes

No

Node Monitor

Full detail + logs

Status only

No

GPU Fleet Status

Full + drain toggle

Read-only

No

DLQ Dashboard

Full + replay/discard

Read-only

No

Quality Review Queue

Full + approve/reject

Own projects

No

Storage Analytics

Full

Own quota only

No

User Management

Yes

No

No

Backup Management

Yes

No

No

Retention Policies

Yes

No

No

47

IVGS v5 Functional Specification

INTERNAL USE ONLY

9. Prompt Management System
9.1 Three-Tier Jinja2 Hierarchy
Table 9-1 Prompt Inheritance Hierarchy
Tier

Scope

Who Can Edit

Override Behavior

1—

All projects and scenes

Admin only

Base default used when no override

Global
2—

exists
All scenes within a project

Project
3 — Scene

Admin, Operator (own

Replaces global for this project

projects)
Single scene within a

Admin, Operator (own

project

projects)

Replaces project-level for this scene

Resolution order: Scene override → Project override → Global default (first match used).

48

IVGS v5 Functional Specification

INTERNAL USE ONLY

9.2 Prompt Types
Table 9-2 Prompt Types and Pipeline Stages
Prompt Type

master

Pipeline
Stage

All stages

Default Behavior

System-wide instructions: Flesch-Kincaid Grade 8, neutral professional tone,
content simplification rules

transcript_refine

Stage 1

ment
storyboard_gene

aligned to max_runtime_seconds
Stage 2

ration
image_generatio

Stage 3

Stage 3

Short clip 3–8 seconds; motion relevant to narration; no text in video;
CogVideoX/Wan2.1 syntax

Stage 3

ation
tts_voice

Photorealistic or illustrative style; no watermarks; consistent color palette; FLUX.1compatible syntax

n
animation_gener

Generate storyboard JSON: scene_index, narration_text, visual_description,
media_type, duration_seconds

n
video_generatio

Simplify transcript, remove jargon, preserve accuracy, structure into timed scenes

Diagram animations, data visualizations, process flows; Remotion component
specification

Stage 5

Voice style, pace, emphasis (SSML-compatible). Default: neutral professional, 1.0x
speed

talking_head

Stage 6

Lip-sync quality settings, background handling (blur/replace/transparent)

composition

Stages 7–8

Layout rules, talking-head position, lower-third style, caption font and size

translation

Localizati

Translate refined transcript; preserve instructional intent; adapt idioms for target

on

language

9.3 Prompt Versioning
Every edit creates a new version record in the prompts table. Previous versions are retained and never
deleted. Users can view the full version history and roll back with a single click. The is_active = true
flag marks the active version; only one version may be active per prompt_type per scope at any time. All
asset records reference generation_prompt_id for full reproducibility and regeneration traceability.

9.4 Template Variables (Jinja2 Syntax)
The following variables are available in all Jinja2 prompt templates:

49

IVGS v5 Functional Specification

INTERNAL USE ONLY

{{ project_title }}
-- Video title from projects.name
{{ project_description }} -- Project description
{{ target_audience }}
-- Configured audience level
{{ scene_number }}
-- Current scene index
{{ scene_title }}
-- Scene narration_text (first line)
{{ narration_text }}
-- Full scene narration text
{{ visual_description }}
-- Scene visual description
{{ target_language }}
-- BCP-47 language code for localization
{{ max_duration_seconds }} -- From projects.max_runtime_seconds
{{ total_runtime_seconds }} -- Estimated total runtime

9.5 Prompt Library
Administrators can designate frequently used prompt patterns as library templates. Library templates are
tagged (e.g., "healthcare", "technical-training", "compliance") and can be applied as the starting point for
new global or project prompts. Library entries are stored as inactive prompt versions with a library tag
and are not included in the resolution chain until explicitly promoted to active.

10. Digital Asset Management
10.1 SeaweedFS 4-Tier Storage Architecture
Table 10-1 Storage Tier Definitions
Tier

Storage

Access Speed

Duration

Asset Types

Hot

SeaweedFS primary (SSD)

<100ms

0–30

All active assets: images, audio, video

days

clips, final renders

31–90

Recently completed project assets

Warm

SeaweedFS secondary

<500ms

(HDD volumes)
Cold

NAS (rsync from

days
<5 seconds

91–365

Archived project assets, older final

days

renders

Minutes (manual

>365

Long-term retention required assets

restore)

days

SeaweedFS)
Archi
ve

NAS compressed archive

50

IVGS v5 Functional Specification

INTERNAL USE ONLY

10.2 SeaweedFS Directory Structure
/ivgs/uploads/
/ivgs/images/
/ivgs/videos/
/ivgs/audio/
/ivgs/talking-heads/
/ivgs/animations/
/ivgs/drafts/
/ivgs/final/
/ivgs/thumbnails/
/ivgs/captions/

-- Uploaded source files (transcripts, talking head clips)
-- Generated scene images
-- Generated video clips
-- TTS audio files per scene per language
-- Lip-synced talking head renders
-- Remotion and AnimateDiff animation outputs
-- 720p prototype drafts
-- Final 1080p and 4K rendered videos
-- Hero images and project thumbnails
-- SRT and VTT caption files

Naming conventions: Scene images:
TTS

audio:

{project_id}/scenes/{scene_id}/image_{variant}.png .

{project_id}/audio/{scene_id}/{language_code}.wav .

{project_id}/talkinghead/{language_code}.mp4 .

Talking

Final

head:
renders:

{project_id}/renders/{language_code}/final_{resolution}.mp4 .

Captions:

{project_id}/captions/{language_code}.srt .

10.3 Tier Migration and Retention Service
The RetentionService runs daily via Celery Beat. It scans the assets table for assets exceeding tier
duration thresholds, compares against retention_policies , and calls transition_tier(asset_id,
new_tier)

to move data and update storage_tier and tier_transition_at . Assets with

preserve_flag = true are exempt from automatic transitions.

10.4 Deduplication
SHA-256 content hashes ( content_hash on assets) prevent storing duplicate files. Before writing to
SeaweedFS, the upload service checks for an existing asset with the same hash. If found, the new asset
record references the existing SeaweedFS file ( reference_count incremented). Deduplication is
expected to save 30–40% of storage based on typical re-use patterns (same scene image regenerated with
identical parameters, same talking-head clip referenced across language variants).

10.5 Quota Management
Storage quotas are defined in the storage_quotas table per user and per organization. The quota service
performs real-time usage tracking (incrementing current_bytes on upload). New jobs are blocked
when

the

user's

quota

alert_threshold_pct ).

is

exceeded.
Admins

Alerts
can

/api/v1/quotas/{entity_type}/{entity_id} .

51

fire

at

80%

override

utilization

(configurable

via

quotas

via

PUT

IVGS v5 Functional Specification

INTERNAL USE ONLY

10.6 Orphan Cleanup Service
The OrphanCleanupService runs daily via Celery Beat and performs three scans: (1) SeaweedFS
objects without corresponding database records, (2) database asset records referencing non-existent
SeaweedFS files, (3) assets with reference_count = 0 for more than 7 days. Identified orphans are
quarantined for 7 days before deletion. All orphan actions are logged to audit_log .

10.7 Output Formats
Table 10-2 Asset Output Format Specifications
Asset Type

Format

Specification

Scene images

PNG

1024×1024 px (FLUX.1/SDXL output), 72 dpi

Video clips

MP4 H.264

480p or 720p, 24 fps, 3–8 second clips

TTS audio

WAV

48 kHz, 24-bit mono

Talking head

MP4 H.264

Match source clip resolution, 30 fps

Draft render

MP4 H.264

1280×720, CRF 23, 30 fps

Final render 1080p

MP4 H.264

1920×1080, CRF 18, VBV 8 Mbps, AAC 192 kbps

Final render 4K

MP4 H.265

3840×2160, CRF 20, VBV 20 Mbps, AAC 256 kbps

Captions (sidecar)

SRT + VTT

Word-level timestamps from WhisperX

11. Quality Assurance Pipeline
11.1 Automated Quality Validation
Every generated asset is automatically validated by the QualityValidator service before advancing to
the next pipeline stage. Quality scores are stored in asset_quality_scores with a decision:
approved , flagged (requires human review), or rejected (triggers regeneration).

52

IVGS v5 Functional Specification

INTERNAL USE ONLY

Table 11-1 Quality Validation Rules
Asset
Type

Image

Image

Metric

Method

CLIP similarity score vs.

Self-hosted CLIP model

generation prompt

(GPU node)

Resolution, aspect ratio,

PIL + FFprobe

artifact detection

Auto-

Flag

Approve

Range

>0.9

0.75–

Reject

<0.75

0.9
Meets

Minor

spec

Wrong size /
corrupted

Video

Frame consistency score

FFprobe frame analysis

>0.8

0.7–0.8

<0.7

Video

Artifact detection (%)

FFprobe metrics

<1%

1–5%

>5%

20–25

<20 dB

artifacts
Audio

Signal-to-noise ratio (dB)

ffmpeg volumedetect

>25 dB

dB
Audio

Clipping rate (%)

ffmpeg astats

<0.1%

0.1–1%

>1%

Talking

Lip-sync alignment score

LatentSync quality

>0.9

0.85–

<0.85

Head
Caption

Content

metric

0.9

Transcript-to-timeline sync

WhisperX confidence +

accuracy

alignment

Safety classifier score

Self-hosted classifier

>0.95

0.9–

<0.9

0.95

Safety

>0.98

—

<0.95 autoreject

11.2 Corruption Detection
The CorruptionDetector service runs post-generation FFprobe validation on all video and audio
assets. Checks include: codec identification (must match expected format), resolution verification,
duration validation (within 10% of expected), frame count validation, and file truncation detection (last
byte sequence check). SHA-256 checksums are computed and stored; checksums are re-verified
immediately before composition to detect storage corruption.

11.3 Quality Gate Workflow
The quality gate workflow is as follows:
1. Asset generated by pipeline stage.
2. validate_asset_quality_task runs automatically (enqueued by stage completion callback).
3. If approved: asset proceeds to next pipeline stage.

53

IVGS v5 Functional Specification

INTERNAL USE ONLY

4. If flagged: asset added to Quality Review Queue in dashboard; pipeline pauses for that scene until
human decision.
5. If rejected: regeneration queued automatically (max 2 regeneration attempts before escalating to
flagged).
6. If regeneration also fails quality gate: added to DLQ with category external (generation model
quality issue).
Projects cannot advance to composition until all scene assets have decision = approved or explicit
human override.

11.4 Quality Metrics Aggregation
Quality scores are aggregated at the project level for the dashboard Quality Metrics view: average CLIP
score across scenes, audio SNR distribution, lip-sync score, caption alignment accuracy. Trends are
tracked over multiple renders to detect model drift. Alert fires if average project quality score drops below
configurable threshold (default: 0.75).

12. GPU Scheduler Microservice
The GPU Scheduler ( ivgs-scheduler ) is a standalone FastAPI microservice deployed on node-01 at port
8001. It provides VRAM-aware job scheduling, admission control, and load balancing for all GPU pipeline
tasks.

54

IVGS v5 Functional Specification

INTERNAL USE ONLY

12.1 Core Components
Table 12-1 GPU Scheduler Components
Componen

Class

Description

Scheduler

GpuSched

VRAM-aware bin-packing: schedule_job(job_id, model_name,

Engine

uler

vram_requirement, estimated_duration) → returns (node_id,

t

gpu_index) or raises NoCapacityError . Sorts GPUs by available VRAM

descending, assigns first fit.
GPU

GpuRegist

Node registration, heartbeat tracking, dead worker detection (60s stale threshold),

Registry

ry

available node queries, node draining support.

Admission

Admission

4-check validation (see §12.2). Resource reservation with 5-minute TTL. Circuit breaker:

Controller

Controller

reject if error rate >20% in last 10 minutes.

Load

LoadBalan

Weighted random selection. Weight formula: weight = (1 - gpu_util) × (1 -

Balancer

cer

mem_util) × (max_queue - current_queue) . Metrics in Redis time-series.

Imbalance alert if stddev >30%.
Model

ModelCon

Tracks loaded models per GPU. Max 2 concurrent loads per model. Prefers GPUs with

Concurren

currencyM

model already resident (avoids reload). LRU eviction when capacity exceeded.

cy

anager

Manager
Priority

PriorityQu

Priority levels: urgent (0–4h SLA), normal (4–24h), batch (24–72h). Anti-starvation

Queue

eueManag

aging: +1 priority bump per 30 minutes waiting.

Manager

er

55

IVGS v5 Functional Specification

INTERNAL USE ONLY

12.2 Admission Control (4-Check System)
Table 12-2 Admission Control Checks
Che
ck #

1

2

Check Name

Description

Failure Action

Phase Gate

Validates job state machine: job must be in a valid state to advance

Reject with 409

Check

to requested stage. Prevents out-of-order execution.

Conflict

VRAM

Queries gpu_nodes for nodes with sufficient available VRAM.

Reject with

Availability

Available VRAM = total_vram_mb − sum of active reservations.

NoCapacityError;

Check
3

4

queue for retry

Concurrency

Enforces per-node maximum parallel tasks (configurable; default:

Reject; caller retries

Limit Check

1 video gen job per GPU). Prevents VRAM fragmentation.

via backoff

Circuit

If the target GPU has >20% error rate in the past 10 minutes, the

Route to alternative

Breaker

circuit is open. New jobs are rejected and routed to an alternative

GPU; if all open, DLQ

Check

GPU.

Successful admission results in a gpu_reservations record with 5-minute TTL. Workers must call PUT
/heartbeat

within 5 minutes to keep the reservation active; expired reservations are automatically

released.

12.3 GPU Scheduler API
Meth
od
POS

Path

Purpose

/schedule

Schedule a job. Body: {job_id, model_name, vram_requirement_mb,

T

estimated_duration_s, priority} . Returns: {node_id, gpu_index,
reservation_id}

POS

/register

T
PUT

Register a GPU node. Body: {node_hostname, gpu_index, gpu_model,
total_vram_mb, compute_capability}

/heartbeat

Update worker heartbeat. Body: {worker_id, node_hostname, gpu_index,
current_job_id, heartbeat_data}

DEL

/reservati

ETE

ons/{id}

Release a VRAM reservation on job completion

GET

/fleet

Fleet status: all nodes, utilization, queue depths

POS

/drain/{n

Mark node for draining (no new jobs scheduled)

T

ode_id}

56

IVGS v5 Functional Specification

INTERNAL USE ONLY

12.4 Scheduler Metrics
Table 12-3 GPU Scheduler Prometheus Metrics
Metric Name

Type

Description

ivgs_scheduler_queue_depth

Gauge

Queue depth per GPU node and priority level

ivgs_scheduler_wait_time_seconds

Histogram

Time from job submission to scheduling decision

ivgs_scheduler_rejection_total

Counter

Total admission control rejections by reason

ivgs_scheduler_circuit_breaker_state

Gauge

Circuit breaker state per GPU node (0=closed, 1=open)

ivgs_gpu_vram_used_mb

Gauge

Reserved VRAM per GPU node

ivgs_gpu_utilization_pct

Gauge

GPU utilization % per node (from heartbeat data)

13. Monitoring and Alerting
13.1 Prometheus Configuration (REQUIRED)
Prometheus 2.51+ runs on node-01 at port 9090. All metric producers expose /metrics endpoints in
Prometheus text format. Scrape interval: 15 seconds. Retention: 30 days.
Table 13-1 Prometheus Scrape Targets
Target

Endpoint

Metrics

ivgs-api

node-

API request latency, pipeline job counts, DLQ size, quality score

01:8000/metrics

distributions

node-

GPU queue depth, wait time, rejection rate, circuit breaker state

ivgs-scheduler

01:8001/metrics
node-exporter (all nodes)

*:9100/metrics

CPU, RAM, disk I/O, network I/O per node

nvidia-gpu-exporter (02–

*:9400/metrics

GPU utilization %, VRAM used/total, temperature, power draw, clock

06)

speeds

postgres-exporter

node-

Connection pool, query latency, deadlock count, table bloat

01:9187/metrics
redis-exporter

node-

Memory used, keyspace hits/misses, connected clients, queue lengths

01:9121/metrics

57

IVGS v5 Functional Specification

INTERNAL USE ONLY

13.2 Grafana Dashboards (REQUIRED)
Grafana is required in v5 (changed from optional in v3). Two mandatory dashboards must be provisioned
from checked-in JSON files in the ivgs-infra repository.
Table 13-2 Required Grafana Dashboards
Dashboar
d

Key Panels

Pipeline

Job success/fail rate (line graph), average pipeline duration (gauge), stage duration breakdown (bar chart),

Overview

active jobs count (stat), queue depths per queue (gauge), error rate by category (pie chart), DLQ message
count (stat), hourly throughput (line)

GPU

Per-GPU utilization % (time series), VRAM usage % (time series), GPU temperature (time series with

Fleet

threshold lines), job throughput per GPU, queue depth per GPU, model residency heatmap (which models

Utilizatio

loaded on which GPUs)

n

13.3 Alert Rules
Table 13-3 Prometheus Alert Rules
Alert Name

Condition

Duration

Severity

Action

GPUOvertemperature

GPU temperature >85°C

2 min

Critical

Page on-call; consider draining node

WorkerDown

Worker heartbeat missing

5 min

Critical

Auto-reschedule jobs; alert ops

DLQHighCount

DLQ messages >10

5 min

Critical

Alert ops for investigation

JobFailureRateHigh

Job failure rate >10%

15 min

Critical

Investigate pipeline errors

GPUUtilizationLow

Fleet avg GPU util <30%

15 min

Warning

Review queue backlog

RenderQueueBacklog

Pending render segments >20

5 min

Warning

Consider scaling workers

GPUVRAMHigh

VRAM utilization >90%

5 min

Warning

Check for reservation leaks

NodeHighCPU

CPU utilization >85%

5 min

Warning

Identify runaway process

NodeHighRAM

RAM utilization >90%

5 min

Warning

Check for memory leaks

StorageQuotaAlert

User quota >80% full

1 hour

Info

Notify user via dashboard

BackupFailed

Last backup status = failed

—

Critical

Alert ops immediately

58

IVGS v5 Functional Specification

INTERNAL USE ONLY

13.4 Log Aggregation
Structured JSON logging is required on all services. Each log entry must include: timestamp, service
name, node hostname, severity level, job_id (when applicable), trace_id, and message. Optional (but
recommended): Loki + Promtail for centralized log aggregation, with log retention of 30 days hot and 90
days cold. Minimum requirement without Loki: FastAPI node-agent endpoint streaming docker logs
output to the dashboard (via WebSocket).

13.5 Required Monitoring Components
Table 13-4 Monitoring Component Status in v5
Component

Status

Notes

Prometheus 2.51+

REQUIRED

Changed from REQUIRED in v3

nvidia-gpu-exporter

REQUIRED

node-02 through node-06

node-exporter 1.7+

REQUIRED

All nodes

Grafana

REQUIRED

Changed from OPTIONAL in v3; pipeline and GPU dashboards

1.2+

mandatory
Loki + Promtail

RECOMMENDE

Optional but strongly recommended for production

D
Alertmanager

RECOMMENDE

Optional; required if automated alert routing is needed

D

14. Backup and Disaster Recovery

59

IVGS v5 Functional Specification

INTERNAL USE ONLY

14.1 Automated Backup Schedule
Table 14-1 Backup Schedule
Backup

Retentio

Scope

Method

Schedule

Target

Full

PostgreSQL (all

pg_dump → GPG encrypt

Daily at

/mnt/backup/ivgs/d

database

databases)

→ rsync

02:00

b/

WAL

PostgreSQL

PostgreSQL WAL archive

Continuous

/mnt/backup/ivgs/w

archiving

continuous

to NAS

Asset

SeaweedFS volumes

rsync with --link-dest

Daily at

/mnt/backup/ivgs/a

(incremental)

03:00

ssets/

rsync + GPG encrypt

Daily at

/mnt/backup/ivgs/c

04:00

onfig/

Weekly

PBS repository

Type

backup
Config

YAML + .env files

All 6 VMs

Proxmox Backup Server

snapshots

30 days

7 days

al/

backup
VM

n

14 days

90 days

4

(PBS)

snapshot
s

14.2 Backup Verification
Every database backup is automatically verified after completion. Verification restores the pg_dump to a
temporary PostgreSQL instance, runs row count checks against expected values, then destroys the
temporary

instance.

SHA-256

checksums

backup_records.verification_checksum .

are

computed

and

A verification failure triggers the

stored

BackupFailed

Prometheus alert (Critical severity) and sends a dashboard notification.

14.3 Recovery Procedures
Table 14-2 Recovery Objectives
Objective

Target

Notes

RTO (Recovery Time Objective)

4 hours

Time from failure declaration to system restored and accepting jobs

RPO (Recovery Point Objective)

24 hours

Maximum data loss (daily backup cycle + WAL archiving)

Rollback RTO

15 minutes

Application rollback to previous version via RollbackService

Database Restore Procedure
1. Stop ivgs-api and ivgs-workers on all nodes

60

in

IVGS v5 Functional Specification

INTERNAL USE ONLY

2. Decrypt backup: gpg --decrypt backup.sql.gz.gpg | gunzip > restore.sql
3. Drop and recreate target database: dropdb ivgs; createdb ivgs
4. Restore: psql ivgs < restore.sql
5. Apply WAL logs if point-in-time recovery needed
6. Verify row counts match backup record expectations
7. Restart ivgs-api (runs Alembic migrations automatically)
8. Restart ivgs-workers
Application Rollback Procedure (RollbackService)
1. Call create_rollback_point(version_tag) before any deployment (automated by deploynode.sh)
2. On failure, identify last valid rollback point in the dashboard
3. Call rollback_to(rollback_point_id) — this reverts Alembic migrations, restarts containers
with previous image tags, restores config files
4. Target: rollback achievable in under 15 minutes

14.4 Disaster Recovery Testing
Quarterly DR tests are mandatory. Test procedure: simulate node failure, restore from backup to test
environment, validate pipeline execution end-to-end, confirm RTO/RPO objectives are met. Test results
are documented and stored. Failed tests trigger an immediate remediation plan before next scheduled test.

15. Deployment Architecture

61

IVGS v5 Functional Specification

INTERNAL USE ONLY

15.1 Repository Structure
Table 15-1 Repository Layout
Repository /
Directory

Contents

ivgs/ivgs-api

FastAPI backend, all pipeline services, Celery worker tasks, Alembic migrations

ivgs/ivgs-frontend

Next.js 14 dashboard (TypeScript), all UI components and views

ivgs/ivgs-scheduler

GPU scheduler microservice (FastAPI), standalone service

ivgs/ivgs-workers

Specialized GPU worker Dockerfiles (one per worker type)

ivgs/ivgs-infra

Docker Compose per node (6 files), Nginx config, Prometheus rules, Grafana dashboards,
deploy scripts

ivgs/ivgs-models

Model download scripts, vLLM configs, ComfyUI workflow JSONs, model checksums

15.2 Six Docker Compose Files
Each node has a dedicated Docker Compose file in the ivgs-infra repository:
docker-compose.node01.yml — Infrastructure services (see §2.4 for full service list)
docker-compose.node02.yml — vLLM primary, CogVideoX workers
docker-compose.node03.yml — vLLM secondary, CogVideoX workers
docker-compose.node04.yml — Image generation, TTS, talking head
docker-compose.node05.yml — Image fallback, Ollama, FFmpeg utility
docker-compose.node06.yml — Remotion renderer, FFmpeg composition overflow

62

IVGS v5 Functional Specification

INTERNAL USE ONLY

15.3 CI/CD Pipeline
Table 15-2 CI/CD Pipelines
Pipeline

Trigger

Steps

CI — API

Push to any

Lint (ruff) → Unit tests (pytest, 80% coverage) → Build Docker → Push GHCR

branch (ivgsapi)
CI —

Push to any

Frontend

branch (ivgs-

Lint (ESLint) → Type check (tsc) → Build Next.js → Docker → GHCR

frontend)
CI —

Push to any

Workers

branch (ivgs-

Build per-worker Dockerfiles → Push GHCR

workers)
CI —

All branches,

Scan for prohibited env vars (OPENAI_API_KEY etc.) → Scan for prohibited pip

Complianc

all repos

packages (openai, anthropic, elevenlabs) → Scan for prohibited API endpoints →

e Audit

Fail build on any violation

CD —

Push to main

node-01

(ivgs-infra)

CD — GPU

Push to main

nodes

(ivgs-infra)

SSH to node-01 → git pull → docker compose pull → docker compose up -d

node-01 runner SSHes sequentially to node-02–06 → pull → compose up

63

IVGS v5 Functional Specification

INTERNAL USE ONLY

15.4 Deployment Script (deploy-node.sh)
#!/bin/bash
# deploy-node.sh — run on each node during CD
set -e
NODE=$1
# 1. Create rollback point
curl -X POST http://node-01:8001/rollback/create -d "{\"version_tag\":\"$(git rev-parse
--short HEAD)\"}"
# 2. Pull pinned image tags from GHCR
docker compose -f docker-compose.${NODE}.yml pull
# 3. Stop current stack
docker compose -f docker-compose.${NODE}.yml down
# 4. Run Alembic migrations (node-01 only)
if [ "$NODE" = "node01" ]; then
docker compose -f docker-compose.node01.yml run --rm api alembic upgrade head
fi
# 5. Start updated stack
docker compose -f docker-compose.${NODE}.yml up -d
# 6. Health check (retry 3 times, 10s apart)
for i in 1 2 3; do
curl -sf http://localhost:8001/api/v1/health && break || sleep 10
done

15.5 Branch Strategy
Table 15-3 Git Branch Strategy
Branch

Purpose

Protection Rules

main

Production-ready; triggers CD

Require PR, CI pass (including compliance audit), no direct

pipeline

push

develop

Integration branch; triggers CI only

Require CI pass

feature/

Feature branches from develop

No protection; PR into develop

Emergency fixes from main

PR into main with CI pass

*
hotfix/*

64

IVGS v5 Functional Specification

INTERNAL USE ONLY

15.6 Health Checks
All Docker Compose services define health checks. The standard health check calls the service's
/health

HTTP endpoint with interval=30s , timeout=10s , retries=3 . Additional platform-level

checks in deploy-node.sh verify: GPU availability ( nvidia-smi ), database connectivity, Redis
connectivity, and SeaweedFS mount points.

16. Authentication and Authorization
16.1 Authentication System
IVGS uses local PostgreSQL-based authentication. No external auth providers (LDAP, OIDC, OAuth,
Keycloak, NextAuth) are used. This eliminates external service dependencies in the authentication path
and keeps all user data on-premises.
Table 16-1 Authentication Specifications
Component

Specification

Password storage

bcrypt with cost factor 12

Access tokens

JWT, HS256, 1-hour expiration, signed with JWT_SECRET_KEY env var

Refresh tokens

JWT, 7-day expiration, stored in Redis (supports invalidation)

Session storage

Redis-backed (allows instant logout via token blacklisting)

Nginx basic auth

Optional additional LAN-level gate for all services

TLS

Recommended (self-signed CA for LAN); plain HTTP acceptable on fully trusted LAN

16.2 Role-Based Access Control
Table 16-2 RBAC Role Definitions
Role

Permissions

Admi

Full system access: all projects, all monitoring views, user management, global prompt management,

n

retention policies, backup management, configuration

Opera

Create and manage own projects, upload transcripts, edit project/scene prompts, trigger renders, view node

tor

status (no logs), Prompt Playground, limited monitoring (read-only)

View

Read-only access to projects in the gallery, video player, download final renders (if permitted by admin)

er

65

IVGS v5 Functional Specification

INTERNAL USE ONLY

16.3 Security Controls
Rate limiting: Per-user rate limits on API endpoints: 60 requests/minute for content CRUD, 10
requests/minute for job triggers. Per-IP rate limits on /auth/login : 5 attempts/minute (lockout
after 10 consecutive failures).
Audit logging: All state-changing operations (create, update, delete, role changes, prompt edits)
are written to the audit_log table with before/after state, user ID, and client IP.
Session invalidation: Logout immediately blacklists the refresh token in Redis. Password change
invalidates all existing sessions.
Inter-node security: All inter-node communication on dedicated private VLAN (192.168.1.0/24).
UFW firewall rules on each VM restrict inbound ports to those required per node role. Service
ports bound to private VLAN interface only.
Secrets management: No secrets in Docker images or Git repositories. Secrets in root-owned
.env files with Docker Compose secrets: blocks. Rotation procedures documented in

deployment runbook.
LUKS encryption: Optional disk encryption on Proxmox VM volumes for at-rest data protection.
Backup encryption: GPG encryption applied to all backups before off-node transfer to NAS.

17. Localization Support
17.1 Supported Languages
Table 17-1 Supported Languages
Language

BCP-47 Code

TTS Engine

Notes

English (US)

en-US

Coqui XTTS v2 — en

Source / master language

English (UK)

en-GB

Coqui XTTS v2 — en-gb

—

Spanish

es-ES

Coqui XTTS v2 — es

—

French

fr-FR

Coqui XTTS v2 — fr

—

German

de-DE

Coqui XTTS v2 — de

—

Mandarin Chinese

zh-CN

Coqui XTTS v2 — zh-cn

CJK font required for captions (Noto CJK)

Japanese

ja-JP

Coqui XTTS v2 — ja

CJK font for captions

Arabic

ar-SA

Coqui XTTS v2 — ar

RTL caption rendering in FFmpeg

66

IVGS v5 Functional Specification

INTERNAL USE ONLY

17.2 Localization Pipeline
Localization is triggered via POST /api/v1/projects/{id}/languages . The pipeline transitions the
project state to LOCALISATION and runs the following stages, reusing existing assets where possible:
Table 17-2 Localization Stage Execution
Stage

Action

Status

1. Transcript

vLLM translates refined transcript per scene using translation prompt type;

EXEC

Translation

stored in new transcripts records with target language_code

UTE

2. Scene Images

Language-neutral; same SeaweedFS assets referenced

SKIP
(reuse)

3. Animation /

Language-neutral; reuse existing

SKIP

Video Clips
4. TTS Audio

(reuse)
Coqui XTTS v2 generates new audio per scene in target language with appropriate

EXEC

voice pack

UTE

5. Talking Head

LatentSync re-renders against new audio track; new talking head asset stored per

EXEC

Lip-Sync

language

UTE

6. Caption

WhisperX generates word-level SRT for new audio; burned-in captions regenerated

EXEC

Generation

with RTL/CJK rendering as needed

UTE

7. Final

FFmpeg composites new audio, lip-sync, captions with existing scene media; new

EXEC

Composition

1080p+4K MP4 produced

UTE

Completed language variants are stored in language_variants table and available for download from
the Project Detail Languages tab and Video Player language selector.

17.3 Caption Rendering
Burned-in captions: FFmpeg subtitles filter with Noto Sans (Latin/CJK RTL unified). Font size:
36pt at 1080p, 72pt at 4K. Arabic RTL: FFmpeg drawtext with right-to-left text direction; Harfbuzz
shaping required. Sidecar files: SRT (word-level timing from WhisperX) and VTT (for web player)
generated for all languages.

18. Change Control Process
The change control process was established in direct response to the v4 failure (see §1.3). All architectural
amendments require formal process compliance.

67

IVGS v5 Functional Specification

INTERNAL USE ONLY

18.1 Change Review Board
The Change Review Board (CRB) consists of: technical lead, at least one domain stakeholder, and one
developer representative. The CRB meets on-demand when a change request is submitted. Approval
requires unanimous consensus for architectural changes; majority for operational changes.

18.2 Change Request Process
1. Submission: Requester files a formal change request documenting the proposed change, rationale,
and initial impact estimate.
2. Impact Analysis: Technical lead prepares impact analysis covering: compliance (does this violate
the self-hosted mandate?), timeline (effort estimate), resource requirements, rollback plan.
3. CRB Review: CRB reviews request and impact analysis. May request clarification or modification.
4. Approval: CRB decision documented. Approved/rejected/deferred with written rationale.
5. Specification Update: This document updated before any code changes are made. Document
version incremented.
6. Implementation: Feature branch created from develop . CI compliance audit must pass before PR
merge.
7. Audit Trail: Change request, impact analysis, CRB minutes, and approval stored in project
documentation.

18.3 Prohibited Actions (No Approval Can Override)
ABSOLUTE PROHIBITIONS

The following actions cannot be approved by the CRB under any circumstances. Any code implementing these
will be rejected by CI and subject to immediate rollback:
Introduction of any cloud AI API (LLM, image, TTS, video, speech-to-text, talking head)
"Phase N temporary" solutions using prohibited services
Architecture changes bypassing abstraction layer interfaces
Silent deviations from this specification (change must be documented before implementation)
Disabling or bypassing the CI compliance audit

68

IVGS v5 Functional Specification

INTERNAL USE ONLY

18.4 Compliance Audits
Table 18-1 Compliance Audit Schedule
Audit Type

Frequency

Method

CI Compliance

Every commit (automated)

Scan for prohibited env vars, pip packages, API endpoints

Scan
Development Audit

in all code
Weekly during development

Technical lead reviews recent PRs for architectural
compliance

Post-Deployment

Quarterly after production

Manual review of running configuration against this

Audit

deployment

specification

DR Test

Quarterly

Full disaster recovery simulation (see §14.4)

19. Development Standards
19.1 Abstraction Layer Requirements
All AI service calls must go through provider abstraction interfaces. This is the primary technical lesson
from the v4 failure. Interfaces must be defined before implementations.
class LLMProvider(ABC):
def generate(self, prompt: str, params: LLMParams) -> LLMResponse: ...
def stream(self, prompt: str, params: LLMParams) -> Iterator[str]: ...
class ImageProvider(ABC):
def generate(self, prompt: str, params: ImageParams) -> ImageResult: ...
class TTSProvider(ABC):
def synthesize(self, text: str, language: str, params: TTSParams) -> AudioResult:
...
def supported_languages(self) -> list[str]: ...
class VideoProvider(ABC):
def generate(self, prompt: str, params: VideoParams) -> VideoResult: ...
def max_clip_duration_seconds(self) -> float: ...
# v5 Implementations (ONLY self-hosted):
class VLLMProvider(LLMProvider): ...
# → vLLM OpenAI-compatible API
class OllamaProvider(LLMProvider): ... # → Ollama fallback
class FluxProvider(ImageProvider): ... # → ComfyUI + FLUX.1 Dev
class CoquiProvider(TTSProvider): ... # → Coqui XTTS v2
class CogVideoXProvider(VideoProvider): ... # → CogVideoX

69

IVGS v5 Functional Specification

INTERNAL USE ONLY

All pipeline task code calls provider interfaces only. The implementation behind the interface may be
swapped (e.g., new Llama 4 model) by updating the provider class — no task code changes required.

19.2 Code Organization
Table 19-1 Code Organization Standards
Standard

Requirement

Repository structure

Monorepo with 6 sub-repositories (ivgs-api, ivgs-frontend, ivgs-scheduler, ivgs-workers,
ivgs-infra, ivgs-models)

Microservice

Each service has its own Dockerfile; no shared runtime dependencies between services

independence
Shared libraries

Common data models, provider interfaces, and utilities in ivgs/shared/ ; published to
GHCR as a private package

Configuration as code

All configuration in YAML files under version control; no hardcoded values

Python version

Python 3.12+; type annotations required throughout

Linting

ruff (replaces flake8/pylint); configured via pyproject.toml

Formatting

black; line length 100 chars

Type checking

mypy strict mode

19.3 Testing Requirements
Table 19-2 Testing Standards
Test Type

Coverage Requirement

Framework

Unit tests

80% minimum line coverage

pytest + pytest-cov

Integration

All API endpoints covered; all worker task signatures tested

pytest + httpx (async)

Full pipeline execution tested in staging environment weekly

pytest + Playwright (UI)

GPU smoke

Model load, inference (1 sample), teardown tested on each node after

Custom test harness per

tests

deployment

model

Compliance

Automated check for prohibited dependencies

CI step (grep/ast analysis)

tests
End-to-end
tests

tests

70

IVGS v5 Functional Specification

INTERNAL USE ONLY

19.4 Documentation Requirements
API documentation: OpenAPI 3.1 spec auto-generated from FastAPI; served at /api/v1/docs
Architecture Decision Records (ADRs): All significant architectural decisions documented in
ivgs/docs/adr/ . ADR 001 must document the v4 failure and v5 rationale.

Deployment runbooks: Per-node deployment procedures, GPU model download procedures, and
emergency procedures in ivgs-infra/docs/
Troubleshooting guides: Common failure modes (GPU OOM, worker crash, DLQ growth,
SeaweedFS mount failure) with resolution steps
This specification: Updated before any architectural implementation change; the authoritative
reference for all development decisions

19.5 Dependency Management
All Python dependencies pinned with exact versions in requirements.txt or pyproject.toml
All Docker images pinned with SHA digest tags in Docker Compose files (no :latest tags)
Dependency updates require CI compliance audit to confirm no prohibited packages introduced
Dependabot or Renovate configured for automated security update PRs (non-breaking patches
only)
APPENDIX A

Configuration Reference
A.1 Required Configuration Files
File

Location

Purpose

timeout_defaults.yaml

ivgs-api/config/

Per-model timeout values (see §6.2)

retry_policies.yaml

ivgs-api/config/

Per-task-type retry max attempts and backoff

fallback_policies.yaml

ivgs-api/config/

Per-scene-type fallback chains (L1→L4)

gpu_requirements.yaml

ivgs-api/config/

VRAM requirements per model for scheduler

quality_thresholds.yaml

ivgs-api/config/

Quality scoring approve/flag/reject thresholds

prometheus.yml

ivgs-infra/monitoring/

Scrape config, alert rules

grafana-pipeline.json

ivgs-infra/grafana/

Pipeline overview dashboard (provisioned)

grafana-gpu.json

ivgs-infra/grafana/

GPU fleet utilization dashboard (provisioned)

71

IVGS v5 Functional Specification

INTERNAL USE ONLY

A.2 Environment Variable Template (.env)
# === Database ===
DATABASE_URL=postgresql+psycopg://ivgs:SECRET@192.168.1.90:5432/ivgs
# === Redis ===
REDIS_URL=redis://192.168.1.90:6379/0
# === SeaweedFS ===
SEAWEEDFS_MASTER_URL=http://192.168.1.90:9333
SEAWEEDFS_FILER_URL=http://192.168.1.90:8888
# === GPU Scheduler ===
GPU_SCHEDULER_URL=http://192.168.1.90:8001
# === vLLM Endpoints ===
VLLM_PRIMARY_URL=http://192.168.1.91:8000/v1
VLLM_SECONDARY_URL=http://192.168.1.92:8000/v1
VLLM_MIDSIZE_URL=http://192.168.1.93:8000/v1
OLLAMA_URL=http://192.168.1.94:11434
# === ComfyUI Endpoints ===
COMFYUI_PRIMARY_URL=http://192.168.1.93:8188
COMFYUI_FALLBACK_URL=http://192.168.1.94:8188
# === TTS / Talking Head ===
COQUI_TTS_URL=http://192.168.1.93:5002
LATENTSYNC_URL=http://192.168.1.93:7860
# === Composition ===
REMOTION_URL=http://192.168.1.95:3002
# === Auth ===
JWT_SECRET_KEY=CHANGE_ME_STRONG_RANDOM_SECRET_64_CHARS
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
# === Backup ===
BACKUP_NAS_PATH=/mnt/backup/ivgs
BACKUP_GPG_KEY_ID=YOUR_GPG_KEY_ID
# === NFS Shared ===
SHARED_VOLUME_PATH=/mnt/ivgs-shared
# === PROHIBITED — these MUST NOT appear in .env ===
# OPENAI_API_KEY — NEVER
# ANTHROPIC_API_KEY — NEVER
# ELEVENLABS_API_KEY — NEVER
# DID_API_KEY — NEVER

APPENDIX B

72

IVGS v5 Functional Specification

INTERNAL USE ONLY

VRAM Requirements Matrix

73

IVGS v5 Functional Specification

INTERNAL USE ONLY

Table B-1 Model VRAM Requirements
Model

Llama 3.3 70B

VRAM
Required

140 GB total

(BF16)
Qwen2.5 72B

Concurrent

node-02 + node-03

1 active

(TP)
144 GB total

(BF16)
Mistral 24B

Max

Node(s)

Notes

Tensor parallel; occupies both 96 GB
GPUs

node-02 + node-03

1 active

Tensor parallel across node-02/03

(TP)
48 GB

node-04

1 active

Uses full node-04 GPU

5 GB

node-05

2 concurrent

Ollama quantized

24 GB

node-04

1

Remaining 24 GB on node-04 after

(BF16)
Llama 3.2 8B
(Q4)
FLUX.1 Dev

XTTS residency
FLUX.1 Schnell

16 GB

node-04

1

Faster, lower quality variant

SDXL 1.0 /

10 GB

node-05

1

Fallback image generation

16 GB

node-04

1

Requires FLUX.1 not loaded

SD3.5
AnimateDiff

concurrently
CogVideoX 5B

24 GB

node-02 or node-

1 per node

Primary video generation

1 per node

Faster variant for short clips

1 per node

720p video clips

03
CogVideoX 2B

14 GB

node-02 or node03

Wan2.1

16 GB

node-02 or node03

Coqui XTTS v2

16 GB

node-04

1

Typically kept resident on node-04

Kokoro TTS

4 GB

node-04

2 concurrent

English-only fallback

WhisperX large-

8 GB

node-04

1

Run after TTS completes

LatentSync

12 GB

node-04

1

Lip-sync primary

SadTalker

8 GB

node-04

1

Lip-sync fallback

CLIP (quality

2 GB

Any GPU node

4 concurrent

Small model; runs alongside generation

v3

scoring)

74

IVGS v5 Functional Specification

INTERNAL USE ONLY

B.1 Recommended GPU Allocation Strategy
Table B-2 GPU Allocation per Node
Node

Total

Typical Allocation

Available for Additional Jobs

Llama 3.3 70B tensor parallel (70 GB) or

~22 GB free when CogVideoX

CogVideoX 5B (24 GB)

running

Llama 3.3 70B tensor parallel (70 GB) or Wan2.1

~80 GB free for additional video

(16 GB)

tasks

XTTS v2 resident (16 GB) + FLUX.1 Dev (24

~0 GB when all active; scheduling

GB) + LatentSync (12 GB)

prevents overlap

16 GB

SDXL (10 GB) or Ollama (5–8 GB)

~6 GB for utility tasks

node-06 (96

96 GB

CogVideoX 5B (24 GB) or Wan2.1 (16 GB) alongside

~70 GB free for composition and

GB)

Remotion/FFmpeg composition; Llama-3.3-70B-FP8

Remotion tasks when no video job

(failover only, profile-gated, stopped by default)

is running

node-02 (96

VRAM

96 GB

GB)
node-03 (96

96 GB

GB)
node-04 (48

48 GB

GB)
node-05 (16
GB)

APPENDIX C

API Response Schemas
C.1 Pagination Format
All list endpoints return paginated responses in the following format:
{
"data": [...],
"total": 142,
"page": 1,
"per_page": 50,
"pages": 3,
"has_more": true

// Array of resource objects
// Total count across all pages
// Current page (1-indexed)
// Items per page
// Total page count
// Whether additional pages exist

}

75

IVGS v5 Functional Specification

INTERNAL USE ONLY

C.2 Standard Error Response
{
"error": {
"code": "VALIDATION_ERROR",
// Machine-readable error code
"message": "Field 'name' is required", // Human-readable message
"details": [
// Optional: field-level errors
{"field": "name", "issue": "required"}
],
"request_id": "uuid-v4"
// For log correlation
}
}

C.3 Project Resource Schema
{
"id": "uuid-v4",
"name": "Introduction to Machine Learning",
"description": "A comprehensive overview...",
"max_runtime_seconds": 1800,
"state": "STORYBOARD_GENERATION",
"hero_image_url": "/api/v1/assets/uuid/download",
"scene_count": 12,
"total_duration_estimate_seconds": 1650,
"created_at": "2026-05-18T10:00:00Z",
"updated_at": "2026-05-18T10:15:00Z",
"language_variants": [
{"language_code": "en-US", "state": "COMPLETE"},
{"language_code": "es-ES", "state": "PENDING"}
],
"active_job": {
"id": "uuid-v4",
"job_type": "storyboard_generation",
"status": "running",
"started_at": "2026-05-18T10:14:00Z"
}
}

76

IVGS v5 Functional Specification

INTERNAL USE ONLY

C.4 GPU Node Status Schema
{
"node_id": "node-04",
"status": "online",
"gpu_model": "NVIDIA RTX 5000 Pro Blackwell",
"total_vram_mb": 49152,
"used_vram_mb": 28000,
"gpu_utilization_pct": 72.5,
"temperature_c": 65.0,
"power_draw_w": 220,
"power_tdp_w": 350,
"active_jobs": [
{
"job_id": "uuid-v4",
"project_name": "ML Introduction",
"stage": "image_generation",
"started_at": "2026-05-18T10:14:00Z"
}
],
"last_heartbeat_at": "2026-05-18T10:16:45Z"
}

C.5 Error Code Reference
Error Code

HTTP Status

Description

VALIDATION_ERROR

400

Request body or parameters failed validation

AUTHENTICATION_REQUIRED

401

Missing or expired Bearer token

TOKEN_EXPIRED

401

JWT token has expired

PERMISSION_DENIED

403

User role insufficient for this operation

RESOURCE_NOT_FOUND

404

Requested resource ID does not exist

INVALID_STATE_TRANSITION

409

Operation invalid for current project state

QUOTA_EXCEEDED

422

User storage quota exceeded

PIPELINE_BUSY

422

Project already has an active pipeline job

MANIFEST_LOCKED

422

Cannot modify a locked composition manifest

NO_GPU_CAPACITY

503

GPU scheduler: no nodes with sufficient VRAM

INTERNAL_ERROR

500

Unhandled server error (full details in logs)

APPENDIX D

77

IVGS v5 Functional Specification

INTERNAL USE ONLY

Database Migration Strategy
D.1 Migration Tool: Alembic
Database schema versioning uses Alembic (SQLAlchemy migration tool). Migration scripts are stored in
ivgs-api/migrations/versions/ .

Alembic upgrade runs automatically during deployment via

docker compose run --rm api alembic upgrade head in deploy-node.sh (node-01 only).

D.2 Fresh Installation DDL Order
For a clean installation, Alembic migrations run in sequence:
Migration

Tables Created

0001_initial_core

users, projects, transcripts, storyboard_scenes, assets, prompts, render_jobs, language_variants,
audit_log

0002_pipeline_checkpoint

pipeline_checkpoints

s
0003_gpu_registry

gpu_nodes, gpu_reservations

0004_retry_tracking

task_retries; extends render_jobs with retry columns

0005_worker_heartbeats

worker_heartbeats

0006_dead_letter_queue

dead_letter_messages

0007_composition_manife

composition_manifests

sts
0008_quality_scores

asset_quality_scores

0009_render_segments

render_segments

0010_gpu_metrics

gpu_metrics_history (partitioned by day)

0011_retention_policies

retention_policies; extends assets with tier columns

0012_storage_quotas

storage_quotas

0013_backup_records

backup_records

0014_fallback_policies

fallback_policies

D.3 Migration from v4 (If Any Data Exists)
The v4 codebase is non-recoverable. If any production data exists in a v4 PostgreSQL instance:

78

IVGS v5 Functional Specification

INTERNAL USE ONLY

1. Export v4 data using pg_dump --data-only --table=projects --table=transcripts -table=storyboard_scenes --table=assets --table=prompts --table=users -table=render_jobs --table=language_variants (core tables only — exclude v4 cloud-

specific tables)
2. Stand up fresh v5 installation with all 14 Alembic migrations applied
3. Transform and import exported data using the migration script ivgsinfra/scripts/v4_to_v5_migration.py

4. Audit imported data to remove any cloud-generated asset references (assets with cloud-provider
SeaweedFS paths)
5. Verify imported data integrity via API endpoint tests

D.4 Seed Data Requirements
A fresh v5 installation requires the following seed data before first use:
Admin user: One admin account created via ivgs-api/scripts/create_admin.py during
initial setup
Default global prompts: All 10 prompt types seeded with default Jinja2 templates (stored in
ivgs-api/seed/default_prompts/ )

Default retention policies: Three policies seeded: standard (30/90/365 days), long-term
(90/180/730 days), compliance (365/730/indefinite)
Default fallback policies: Four scene types seeded: action, talking_head, broll, title_card
GPU node registration: Five GPU nodes auto-registered via scheduler startup registration calls
APPENDIX E

Glossary
Table E-1 Technical Terms and Acronyms
Term / Acronym

Definition

ADR

Architecture Decision Record — a document capturing a significant architectural decision, its
context, and consequences

Activity

A single unit of work invoked by a workflow. May perform I/O, may fail and be retried
independently, and heartbeats while running. Each IVGS pipeline stage is an activity

Activity

A progress report from a running activity. Distinguishes a slow activity from a stalled one,

heartbeat

replacing statically guessed timeouts

BCP-47

IETF language tag standard used for language codes (e.g., en-US, zh-CN)

Celery

Distributed task queue for Python. Used for pipeline stage execution in v5.0; withdrawn at
M3 cutover in favour of Temporal (AD-05)

79

IVGS v5 Functional Specification

INTERNAL USE ONLY

Celery

Celery's periodic task scheduler; required in v5.0 for DLQ processing, orphan cleanup, and

Beat

retention management. Withdrawn at M3 cutover; replaced by Temporal Schedules

Child

A workflow started by another workflow, with independent retry and history. IVGS uses one

workflow

per render segment

CLIP

Contrastive Language–Image Pretraining — a model that measures semantic similarity between text
prompts and generated images; used for image quality scoring

CogVideo

Open-source video generation model; generates short video clips from text prompts; runs on node-02/03

X
ComfyUI

Node-based UI and API for running diffusion models (FLUX.1, SDXL); deployed on node-04/05

Coqui

Open-source multilingual TTS model supporting 8 languages with voice cloning; primary TTS engine on

XTTS v2

node-04

CRB

Change Review Board — governance body that approves specification amendments

DLQ

Dead Letter Queue — storage for pipeline tasks that exhausted all retry attempts; requires human review
before replay or discard

Event history

The persisted, replayable record of every step in a workflow execution. The recovery
mechanism and the operator's primary diagnostic record

FLUX.1

Black Forest Labs image diffusion model; primary image generation engine; requires 24 GB VRAM

Dev
GPU

ivgs-scheduler microservice providing VRAM-aware job scheduling, admission control, and load

Scheduler

balancing

IOMMU/

Hardware I/O virtualization used for GPU passthrough from Proxmox host to VM with near-native

VFIO

performance

IVGS

Instructional Video Generation System — the platform described in this specification

LatentSyn

Open-source lip-sync model for talking head video generation; primary talking head engine on node-04

c
LLM

Large Language Model — neural network model for text generation; in IVGS v5, all LLMs run locally
via vLLM or Ollama

NAS

Network Attached Storage — the on-premises storage target for cold/archive tier assets and backups

NFS

Network File System — protocol used to share the ivgs-shared volume across all six nodes

Ollama

LLM inference server for smaller models; used as LLM fallback on node-05

PBS

Proxmox Backup Server — VM snapshot backup solution for weekly VM-level recovery

Prometheu

Open-source metrics collection and alerting system; required component on node-01

s
Proxmox

Open-source hypervisor platform used to host all six VMs on the physical cluster hardware

QA

Quality Assurance — automated validation of generated assets against defined quality thresholds

80

IVGS v5 Functional Specification

INTERNAL USE ONLY

RBAC

Role-Based Access Control — permission system with three roles: Admin, Operator, Viewer

Remotion

React-based programmatic video generation framework; used for lower-thirds, animations, and Ken
Burns effects on node-06

Replay

Reconstructing workflow state by re-executing deterministic workflow code against event
history. The reason workflow code must be deterministic and versioned

RPO

Recovery Point Objective — maximum acceptable data loss; v5 target: 24 hours

RTO

Recovery Time Objective — maximum acceptable downtime; v5 target: 4 hours

SadTalker

Open-source talking head model; used as fallback to LatentSync on node-04

SDXL

Stable Diffusion XL — image diffusion model; fallback image generation on node-05

SeaweedFS

Open-source distributed file system used as the binary asset store; deployed in single-node mode on
node-01 with hot/warm tiers

Signal

An asynchronous message delivered to a running workflow. IVGS's two human review gates are
implemented as signals

SNR

Signal-to-Noise Ratio — audio quality metric; IVGS v5 minimum threshold: 20 dB

SSML

Speech Synthesis Markup Language — markup for TTS voice style, pace, and emphasis

TTS

Text-to-Speech — audio synthesis from text input; Coqui XTTS v2 is the primary engine

Temporal

Open-source (MIT) durable execution engine. Persists workflow state and execution history so
long-running, multi-step processes survive process and host failure. IVGS's pipeline
orchestrator from M3 (ADR-005)

Tensor

Technique splitting large model inference across multiple GPUs; used for Llama 3.3 70B across

Parallelism

node-02/03

VLAN

Virtual Local Area Network — dedicated private network (192.168.1.0/24) for inter-node IVGS
communication

vLLM

High-throughput LLM inference engine with OpenAI-compatible API; primary LLM server on
node-02/03/04

VRAM

Video Random Access Memory — GPU memory; IVGS scheduler tracks VRAM availability per
node for bin-packing

Wan2.1

Open-source video generation model; generates 720p clips up to 5 seconds; runs on node-02/03

WhisperX

Enhanced Whisper implementation with word-level timestamp alignment; used for caption
generation on node-04

Workflow

A durable, resumable function defining a job's control flow. Must be deterministic and perform
no I/O directly

APPENDIX F

Compliance Checklist
F.1 Pre-Deployment Verification
The following checklist must be completed before any deployment to production. All items must pass
before proceeding.

81

IVGS v5 Functional Specification

INTERNAL USE ONLY

Table F-1 Pre-Deployment Compliance Checklist
#

Item

Verified By

1

CI compliance audit passes: no prohibited env vars found in any configuration file

CI pipeline

2

CI compliance audit passes: no prohibited pip packages (openai, anthropic,

CI pipeline

Pass/Fai
l

elevenlabs) in requirements.txt or pyproject.toml
3

CI compliance audit passes: no prohibited API endpoint URLs in source code

CI pipeline

4

All unit tests pass with ≥80% coverage

CI pipeline

5

All integration tests pass against staging environment

CI pipeline

6

Alembic migrations applied successfully in staging

Technical lead

7

All six GPU nodes respond to scheduler registration

Technical lead

8

Prometheus scraping all targets (7 targets as per Table 13-1)

Technical lead

9

Both Grafana dashboards provisioned and displaying data

Technical lead

10

Backup system tested: daily backup runs and verification passes

Technical lead

11

Full pipeline smoke test in staging: transcript → final render (English)

Technical lead

12

Localization smoke test: at least one non-English variant completed

Technical lead

13

DLQ system tested: deliberate failure confirmed to route to DLQ

Technical lead

14

Checkpoint resume tested: pipeline resume from mid-stage failure confirmed

Technical lead

15

Specification document updated to reflect any changes since last version

Technical lead

F.2 Prohibited Dependency Scanner
The following grep patterns are run in the CI compliance audit step. Build fails if any match is found:

82

IVGS v5 Functional Specification

INTERNAL USE ONLY

# Prohibited environment variables
grep -rE
"OPENAI_API_KEY|ANTHROPIC_API_KEY|ELEVENLABS_API_KEY|DID_API_KEY|SYNTHESIA_API_KEY" \
--include="*.env*" --include="*.yml" --include="*.yaml" --include="*.py" .
# Prohibited pip packages
grep -rE "^openai|^anthropic|^elevenlabs|^did-client|^synthesia" requirements*.txt
pyproject.toml
# Prohibited API endpoint patterns
grep -rE "api\.openai\.com|api\.anthropic\.com|api\.elevenlabs\.io|api\.d-id\.com" \
--include="*.py" --include="*.ts" --include="*.js" .
# Prohibited import patterns
grep -rE "^import openai|^from openai|^import anthropic|^from anthropic|^import
elevenlabs" \
--include="*.py" .

83

IVGS v5 Functional Specification

INTERNAL USE ONLY

F.3 Configuration Audit Checklist
Table F-2 Post-Deployment Configuration Audit
#

Configuration Item

Expected Value

1

vLLM endpoint in .env

Points to 192.168.1.91:8000 or 192.168.1.92:8000 (not any cloud
URL)

2

ComfyUI endpoint in .env

Points to 192.168.1.93:8188 or 192.168.1.94:8188

3

TTS endpoint in .env

Points to 192.168.1.93:5002 (Coqui XTTS)

4

Talking head endpoint in .env

Points to 192.168.1.93:7860 (LatentSync)

5

No OPENAI_API_KEY in any .env

Key must not exist

file
6

Prompt Playground model list

Lists only vLLM and Ollama models (no cloud providers)

7

Prometheus targets health

All 7 scrape targets in UP state

8

Celery Beat running

Periodic tasks schedule confirmed in Celery Beat logs

9

Grafana dashboards loaded

Both pipeline-overview.json and gpu-utilization.json provisioned

1

SeaweedFS mount

All nodes show /mnt/ivgs-shared mounted and writable

11

Backup NAS mount

node-01 shows /mnt/backup/ivgs mounted and writable

1

GPU scheduler fleet

All 5 GPU nodes registered (GET /fleet returns 5 nodes in online

0

2

status)

End of IVGS v5 Functional Specification — Version 5.0 — May 18, 2026. This document is the authoritative single
source of truth for the IVGS v5 implementation. All implementation must conform to this specification. Amendments
require formal change control approval as described in Section 18.

84

