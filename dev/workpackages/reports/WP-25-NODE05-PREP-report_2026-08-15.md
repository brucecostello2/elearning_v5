# WP-25-NODE05-PREP - node-05 M4 readiness survey

| | |
|---|---|
| **Package** | WP-25-NODE05-PREP (Tier B, Track P) |
| **Date** | 2026-08-15 |
| **HEAD SHA** | `134c34f40594271594928e6909ed71f54e09a1a6` |
| **Target** | node-05 / 192.168.1.94 (root SSH, explicitly handed over by the operator) |
| **Status** | **CLOSED.** Pass 1 findings below unchanged as the record. Operator approved the plan, resolved D-1, and authorised the reboot; changes applied to node-05 only. No repo file touched except this report. |

## 0. Authority and scope note

CLAUDE.md section 1 and WP-QUEUE common rule 5 forbid running commands on any
node other than node-01 "unless explicitly handed over". The operator handed
node-05 over in the kickoff for this package. Every command run against
192.168.1.94 in this pass was **read-only** (`cat`, `ls`, `lspci`, `dmesg`,
`systemctl status`, `docker info`, `showmount`, `curl`). Nothing was installed,
started, stopped, mounted or written.

Commands were also run **on node-01**, all read-only (`exportfs`, `showmount`,
`curl`, `getent`, repo `grep`). No container on node-01 was touched, and the
repo working tree was not modified - WP-03 is running concurrently on
nodes 01/02/03/04.

---

## 1. Headline verdict

**node-05 cannot host the M4 GPU workload in its current form, and the blocker
is not fixable from inside the guest.**

node-05 is a QEMU/KVM virtual machine with **no GPU attached**. There is no
RTX 5080 on its PCI bus, no VFIO passthrough, and no IOMMU group. The NVIDIA
driver stack is fully installed and the kernel module loads, then immediately
unloads because it finds no hardware.

Everything else on the box is in better shape than the documentation implies:
Docker, the NVIDIA Container Toolkit and node-exporter are already installed
and running. The remaining work is small, and all of it is blocked behind, or
independent of, the GPU passthrough decision.

---

## 2. Evidence basis

### 2.1 Verified live on node-05

| # | Finding | Evidence |
|---|---|---|
| L1 | Host is reachable; SSH as root works | `ping` 0% loss; `ssh root@192.168.1.94 'hostname'` -> `node-05`, `uid=0(root)` |
| L2 | Freshly booted this morning | `who -b` -> `system boot 2026-08-15 11:09`; uptime 11 min at survey start |
| L3 | Ubuntu 24.04.4 LTS, kernel 6.8.0-124-generic, x86_64 | `/etc/os-release`, `uname -r` |
| L4 | **It is a VM, not bare metal** | `systemd-detect-virt` -> `qemu`; `hostnamectl` -> `Chassis: vm`, `Hardware Vendor: QEMU`, `Hardware Model: Standard PC (Q35 + ICH9, 2009)` |
| L5 | **No NVIDIA GPU on the PCI bus** | `lspci -nn` full listing: the only display device is `00:01.0 VGA compatible controller [0300]: Device [1234:1111]` - the QEMU/Bochs emulated VGA. Every other device is virtio, ICH9 or a QEMU PCIe root port. No `10de:` vendor ID anywhere. |
| L6 | **The driver confirms it at boot** | `dmesg`: `NVRM: No NVIDIA GPU found.` - repeated 6 times as the module loads and unloads on each probe |
| L7 | No passthrough plumbing in the guest | `lsmod \| grep vfio` -> no vfio; `ls /sys/class/iommu` -> empty |
| L8 | `nvidia-smi` present but non-functional | `/usr/bin/nvidia-smi` exists; running it -> `NVIDIA-SMI has failed because it couldn't communicate with the NVIDIA driver` |
| L9 | Driver **580.159.03** installed, open-kernel variant | `dpkg -l`: `nvidia-driver-580-open`, `nvidia-dkms-580-open`, `nvidia-utils-580`, `libnvidia-compute-580`, all `580.159.03-0ubuntu0.24.04.1`, from the `graphics-drivers` PPA |
| L10 | 12 vCPU, 47 GiB RAM, no swap | `nproc` -> 12; `free -h` -> `47Gi` total, `46Gi` available; `Swap: 0B` |
| L11 | CPU model is AMD Ryzen 9 8945HX (host CPU exposed to guest) | `/proc/cpuinfo` |
| L12 | **One 200 GB virtual disk only. No second disk.** | `lsblk`: `sda 200G` -> `/boot/efi`, `/boot`, LVM `ubuntu--vg-ubuntu--lv 196.9G` on `/`. No `sdb`, no NVMe. |
| L13 | Root filesystem: 194 G total, 37 G used, **149 G available** | `df -hT` |
| L14 | An fstab entry points at a disk that does not exist | `/etc/fstab`: `/dev/sdb1 /opt/factory ext4 defaults,nofail 0 2`. `sdb` absent; `/opt/factory` does not exist. Harmless today only because of `nofail`. |
| L15 | **Docker 29.5.3 installed, active, enabled** | `docker --version`; `systemctl is-active docker` -> `active`; `is-enabled` -> `enabled` |
| L16 | Docker Compose v5.1.4 (plugin) | `docker compose version` |
| L17 | Storage driver `overlayfs`, cgroup v2 / systemd driver | `docker info` |
| L18 | **NVIDIA Container Toolkit 1.19.1 installed** | `nvidia-ctk --version` -> `1.19.1`; packages `nvidia-container-toolkit`, `nvidia-container-toolkit-base`, `libnvidia-container1`, `libnvidia-container-tools` all `1.19.1-1` |
| L19 | `nvidia` runtime registered **and set as the Docker default runtime** | `docker info` -> `Runtimes: io.containerd.runc.v2 nvidia runc`, `Default Runtime: nvidia`. `/etc/docker/daemon.json` sets `"default-runtime": "nvidia"`. |
| L20 | No containers exist on the box | `docker ps -a` -> header only |
| L21 | One image cached: `nvidia/cuda:12.8.0-base-ubuntu24.04` | `docker images` |
| L22 | **No GHCR credentials** | `/root/.docker/config.json` does not exist |
| L23 | **No NFS mounts at all** | `mount \| grep -Ei "nfs\|cifs"` -> nothing. `/etc/fstab` has no NFS line. |
| L24 | **`/mnt/ivgs-shared` does not exist** | `ls /mnt/ivgs-shared` -> `No such file or directory`. `/mnt` contains only `datasets`, `models`, `shared`. |
| L25 | `/mnt/models` exists but is an empty local directory (not a mount) | `ls -la /mnt/models` -> `.` and `..` only, dated Jun 6 21:52 |
| L26 | NFS **client** support is present | `nfs-common 1:2.6.4-3ubuntu5.1` installed; `/usr/sbin/mount.nfs`, `/usr/sbin/showmount` present; `rpcbind` listening on :111 |
| L27 | **node-01's exports are visible and reachable from node-05** | From node-05: `showmount -e 192.168.1.90` -> `/mnt/models` and `/mnt/ivgs-shared`, both `192.168.1.0/24`. `rpcinfo -t 192.168.1.90 nfs 3` -> `program 100003 version 3 ready and waiting`. |
| L28 | **node-exporter is already installed and running - bare metal, not a container** | `/usr/local/bin/node_exporter`, version **1.8.2**; unit `/etc/systemd/system/node_exporter.service`, `enabled`, `active (running) since 2026-08-15 11:09:10`, PID 1139 |
| L29 | It is serving metrics on all interfaces | `ss -ltnp` -> `LISTEN *:9100 node_exporter`; `curl localhost:9100/metrics \| wc -l` -> **1361** lines |
| L30 | **It is already scrapeable from node-01** | From node-01: `curl http://192.168.1.94:9100/metrics` -> **HTTP 200, 74536 bytes** |
| L31 | ufw active, LAN allowed | `ufw status` -> `active`, `Anywhere ALLOW 192.168.1.0/24`; iptables INPUT policy DROP with ufw chains |
| L32 | Networking correct: `enp6s18` 192.168.1.94/24, default via .1 | `ip -4 -br addr`, `ip route` |
| L33 | Clock synchronised, UTC | `timedatectl` -> `System clock synchronized: yes`, `Etc/UTC` |
| L34 | Unprivileged `ivgs` user exists (uid 1001) | `getent passwd ivgs` |
| L35 | apt sources already include docker, nvidia libnvidia-container (stable + experimental), graphics-drivers PPA, nodesource | `/etc/apt/sources.list.d/` |
| L36 | No IVGS repo clone on the node | `/opt` contains only `containerd` |

### 2.2 Verified live on node-01 (read-only)

| # | Finding | Evidence |
|---|---|---|
| N1 | node-01 **is** an NFS server and both exports are live | `systemctl is-active nfs-server nfs-kernel-server` -> `active active`; `showmount -e 192.168.1.90` lists both |
| N2 | Export options | `/etc/exports`: `/mnt/ivgs-shared 192.168.1.0/24(rw,sync,no_subtree_check,no_root_squash)` and the same for `/mnt/models` |
| N3 | Both export roots exist on node-01 | `ls -la /mnt` -> `ivgs-shared` (owner `node_exporter:systemd-journal`), `models` (owner `ivgs:ivgs`) |
| N4 | node-05 resolves by name on node-01 | `/etc/hosts:14` -> `192.168.1.94 node-05`; `getent hosts node-05` resolves |

### 2.3 Inferred from reading committed code (NOT verified live)

| # | Finding | Citation |
|---|---|---|
| R1 | The driver floor for M4 is driver >= 570.x and CUDA >= 12.4 (Blackwell) | `docs/ivgs_v5_functional_spec.md:1457`; `README.md:26`; `docs/IVGS_v5_Functional_Spec_Amendment_v5.1.md:91` |
| R2 | node-05's intended role: ComfyUI SDXL/SD3.5 fallback, Ollama small-LLM fallback, FFmpeg composition overflow, utility | `README.md:23,47`; `ivgs-infra/docker-compose.node05.yml:6-17`; `ivgs-workers/celery_app.py:20`; `ivgs-api/app/core/node_registry.py:38` |
| R3 | Compose for node-05 defines 6 services: comfyui (:8188), ollama (:11434), ffmpeg-worker, celery-worker, node-exporter (:9100), nvidia-gpu-exporter (:9400) | `ivgs-infra/docker-compose.node05.yml:12-17` |
| R4 | 4 of 6 services request GPUs via `deploy.resources.reservations.devices` (`x-gpu-resources` anchor) | `ivgs-infra/docker-compose.node05.yml:36-43` |
| R5 | Compose expects these host paths: `/data/models`, `/data/comfyui-output`, `/data/models/ollama`, `/data/ffmpeg-tmp`, `/mnt/ivgs-shared` | `docker-compose.node05.yml:66-69, 92-93, 122-123, 156-157` |
| R6 | Compose **does not** bind-mount `/mnt/models` on node-05 - it uses a local `/data/models` for weights | same lines as R5; contrast `README.md:23` and `RECOVERY.md:23` |
| R7 | Compose deploys node-exporter **as a container** binding `0.0.0.0:9100` | `docker-compose.node05.yml:171-180` |
| R8 | Prometheus scrapes only `node-01:9100` for node-exporter; the `nvidia-gpu-exporter` job targets only `node-02:9400` | `ivgs-infra/monitoring/prometheus/prometheus.yml:95-101, 145-151` |
| R9 | `.env.node05` does not exist in the repo (per-node env files are not committed) | `ls ivgs-infra/.env.node05` -> not found; `ivgs-infra/` listing |
| R10 | Node-05 compose pulls `ghcr.io/brucecostello2/ivgs-workers:comfyui-${IVGS_WORKERS_TAG}` | `docker-compose.node05.yml:55` |
| R11 | The Master Plan still records node-05 as OFFLINE and not started (WS-F) | `IVGS_v5_Master_Sequence_Plan_to_Production.md:25,63,127` |

---

## 3. Findings

### F1 (BLOCKER, host-side) - There is no RTX 5080 attached to node-05

node-05 is a QEMU guest (L4). Its entire PCI bus is emulated (L5): the only
display adapter is the Bochs VGA device `1234:1111`. `dmesg` records
`NVRM: No NVIDIA GPU found.` on every module probe (L6), and there is no vfio
module or IOMMU group inside the guest (L7).

The RTX 5080 is either not in this Proxmox host, not bound to `vfio-pci`, or
not added to this VM's hardware. **All three fixes are host-side actions on the
Proxmox hypervisor, which is outside this package's scope and outside my
node-05 hand-over.** This is an operator action.

Consequence for M4: 4 of the 6 node-05 compose services request GPU
reservations (R4). With no GPU, `comfyui`, `ollama` and `nvidia-gpu-exporter`
cannot start, and the `gpu_image` / `llm_inference_fallback` queues cannot be
served. Only `ffmpeg-worker` (CPU composition) and `node-exporter` would run.

### F2 - Driver 580.159.03 **satisfies** the M4 floor, and is the correct variant

The floor is >= 570.x / CUDA >= 12.4 (R1). Installed is 580.159.03 (L9), which
clears it. It is the `-open` kernel-module variant, which is the correct - and
for Blackwell the only supported - choice. The DKMS source package is present,
so it will rebuild across kernel updates.

This cannot be confirmed end-to-end until a GPU exists: `nvidia-smi` reports no
device (L8), so the reported CUDA runtime version, the actual GPU model and the
VRAM figure are all **unverified**. Do not record "RTX 5080 16 GB confirmed"
anywhere until F1 is resolved and `nvidia-smi` prints a device.

### F3 - Hardware does not match the documented spec

| Attribute | `README.md:36` claims | Actually observed | Delta |
|---|---|---|---|
| vCPU | 8 | 12 (L10) | better |
| RAM | 24 GB | 47 GiB (L10) | better |
| System disk | 200 GB SSD | 200 GB virtual disk (L12) | matches |
| Second disk | **1 TB NVMe** | **absent** (L12) | **missing** |
| GPU | RTX 5080 16 GB | **none** (L5) | **missing** |

The missing 1 TB NVMe matters directly: compose puts all model weights and
scratch on `/data/...` (R5), which the README implies was the NVMe. With no
second disk, `/data` would land on the 149 GB free on root (L13). SDXL +
SD3.5 + a quantised Llama 3.2 8B plus ComfyUI output and ffmpeg scratch will
fit in 149 GB but with thin margin and no isolation - a runaway ffmpeg temp
file would fill `/` and take the node down.

`README.md` needs correcting either way. That is a repo edit and therefore
**out of this package's scope**; I am recording it, not doing it.

### F4 - node-exporter is viable **and already running**, but it collides with compose

The brief asked me to verify node-exporter viability. It is better than viable:
a bare-metal node_exporter v1.8.2 is installed, enabled, running, and already
returns 200 / 74 KB of metrics when scraped from node-01 (L28-L30). ufw already
permits the LAN (L31). Nothing needs installing.

Two consequences that need an operator decision:

1. **Port collision at M4.** `docker-compose.node05.yml:171-180` deploys
   `prom/node-exporter:v1.8.1` bound to `0.0.0.0:9100` (R7). The host binary
   already owns :9100 (L29). `docker compose up` will fail to bind. Either the
   host unit is masked at deploy time, or the `node-exporter` service is
   omitted from the node-05 `up` invocation. Note the host binary is v1.8.2,
   *newer* than the v1.8.1 pinned in compose.
2. **Nothing scrapes it.** Prometheus has one node-exporter target,
   `node-01:9100` (R8). node-05 will not appear in Grafana until a target is
   added. That is a repo edit to `ivgs-infra/monitoring/prometheus/prometheus.yml`
   - **out of scope here**, and it collides with WP-24, which is also working
   on node status. Flagging for sequencing, not doing it.

### F5 - NFS: both exports are ready and reachable; node-05 has simply never mounted them

This is the cleanest item. node-01 exports `/mnt/ivgs-shared` and `/mnt/models`
rw to the whole LAN (N1, N2). From node-05, `showmount` sees both and NFSv3 is
answering (L27). The client tooling is installed (L26).

But node-05 has zero NFS mounts, no fstab entries, and `/mnt/ivgs-shared` does
not even exist as a directory (L23, L24). `/mnt/models` exists but is an empty
local dir, which is a trap: mounting over it is fine, but if the mount silently
fails, writes land on the root filesystem instead and look successful.

Note `no_root_squash` on both exports (N2): node-05 root will be node-01 root
on those shares. That is the existing fleet posture, not something I changed,
but it is worth the operator seeing it written down.

Also note **R6**: the node-05 compose does not actually mount `/mnt/models` -
it uses a local `/data/models`. So `/mnt/models` on node-05 is needed for
operator/recovery use (`RECOVERY.md:23,44`), not by the compose stack. Worth
confirming which you intend before M4, because it decides whether weights on
node-05 are shared-from-node-01 or local-and-separately-fetched.

### F6 - `default-runtime: nvidia` on a GPU-less box

`/etc/docker/daemon.json` sets the NVIDIA runtime as the *default* for every
container (L19). On a machine with no GPU this is at best pointless and at
worst a footgun: every unrelated container is routed through
`nvidia-container-runtime`. It has not caused a failure yet because no
container has been run (L20). Recommend leaving it as-is if the GPU is coming,
but it should be a conscious choice rather than an accident.

### F7 - Smaller gaps

- **No GHCR credentials** (L22). `docker-compose.node05.yml:55` pulls from
  `ghcr.io/brucecostello2/...` (R10). Either `docker login ghcr.io` or the
  `docker save`/`docker load` artifact route per `RECOVERY.md` is required
  before M4.
- **No `.env.node05`** anywhere - not in the repo (R9), and no repo clone on
  node-05 at all (L36). Must be created on the node at M4. It carries
  `IVGS_WORKERS_TAG`, `POSTGRES_PASSWORD`, `NODE_01_IP`.
- **Dead fstab entry** `/dev/sdb1 -> /opt/factory` for a disk that does not
  exist (L14). Survives boot only because of `nofail`. Should be removed or the
  disk attached.
- **No swap** (L10). With 47 GiB that is defensible; noting it, not proposing
  a change.
- `/mnt/shared` and `/mnt/datasets` exist on node-05 and are unrelated to the
  IVGS layout (L24) - leftovers from a previous build. Not touching them.

---

## 4. Proposed install plan (NOT executed - awaiting approval)

Everything below is read-write on node-05 only. Nothing here deploys a worker,
runs compose, or edits a repo file. Steps 1-3 are independent of the GPU and
can proceed now; step 4 cannot start until F1 is resolved by the operator.

### Step 1 - Mount the two NFS shares, permanently and safely

Rationale: this is the one item that is fully unblocked, fully reversible, and
required by every later step.

1. `mkdir -p /mnt/ivgs-shared` (`/mnt/models` already exists, empty).
2. Add to `/etc/fstab`, using `nofail` so a node-01 outage cannot block
   node-05's boot, and `soft,timeo`/`retrans` so a hung server surfaces as an
   I/O error rather than a D-state hang:

       192.168.1.90:/mnt/ivgs-shared  /mnt/ivgs-shared  nfs  defaults,nofail,_netdev,soft,timeo=100,retrans=3  0 0
       192.168.1.90:/mnt/models       /mnt/models       nfs  defaults,nofail,_netdev,soft,timeo=100,retrans=3  0 0

   **Decision D-2 below**: `soft` vs `hard`. I have proposed `soft`; the
   backups to `.7` use a hard mount, so this is a deliberate divergence I want
   confirmed.
3. `systemctl daemon-reload && mount -a`.
4. **Gate (artifact-checked, not exit-code-checked):** `mountpoint -q` on both;
   `stat -f -c %T` reports `nfs`; write `/mnt/ivgs-shared/.node05-probe`, read
   it back **from node-01**, then delete it. An exit code of 0 from `mount -a`
   proves nothing on its own.
5. Rollback: remove both fstab lines, `umount` both.

### Step 2 - Remove the dead fstab entry

Delete the `/dev/sdb1 /opt/factory` line (F7). One line, reversible, keeps
`mount -a` honest so a future real failure is not lost in pre-existing noise.
Skip this if the 1 TB NVMe from F3 is about to be attached as `sdb`.

### Step 3 - Decide and settle node-exporter (no install needed)

Nothing to install (F4). What is needed is the collision decision, D-3 below.
My recommendation: **keep the host binary, drop `node-exporter` from node-05's
compose `up` list.** It is already newer (1.8.2 vs 1.8.1), already running,
already reachable, and a host-level exporter reports host metrics more
faithfully than a containerised one with `--path.rootfs` remapping. If you
prefer compose-uniformity across the fleet instead, I will
`systemctl disable --now node_exporter` at M4 deploy time.

The Prometheus scrape target for `node-05:9100` (F4.2) is a **repo edit and is
out of scope** - I will not make it. It needs sequencing against WP-24.

### Step 4 - GPU verification (BLOCKED on F1)

Cannot start until the operator attaches the RTX 5080 to the VM on the Proxmox
host. When that is done, the verification I would run - all read-only:

1. `lspci -nn | grep -i nvidia` shows a `10de:` device.
2. `nvidia-smi` prints the device, the driver version and total VRAM. Record
   the **actual** model and VRAM against `README.md:36`'s claim (F3).
3. `nvidia-smi` reports CUDA >= 12.4 (R1).
4. Toolkit end-to-end, using the image already cached (L21):
   `docker run --rm --gpus all nvidia/cuda:12.8.0-base-ubuntu24.04 nvidia-smi`.
   **This is the only real proof the container toolkit works**; everything in
   L18/L19 is package presence, not function.

Note for when it happens: a 16 GB RTX 5080 against `docker-compose.node05.yml`,
which gives all four GPU services `count: all` (R4), means ComfyUI, Ollama and
the exporter all see the same card with no VRAM partitioning. That is an M4
design question, not a prep question - raising it, not solving it.

### What I am deliberately NOT proposing

- No `docker compose up`, no worker deploy, no image pull (scope OUT).
- No repo edits beyond this report - specifically **not** the `README.md:36`
  correction (F3) and **not** the Prometheus target (F4.2), both of which are
  genuinely needed but belong to another package.
- No change to `/etc/docker/daemon.json` (F6) without a decision.
- No `docker login` on node-05 - that writes a credential; operator's call.
- Nothing on any other node.

---

## 5. Decisions requested

| ID | Decision | Why it matters | My recommendation |
|---|---|---|---|
| **D-1** | **Attach the RTX 5080 to node-05 on the Proxmox host** (or tell me node-05 is intentionally CPU-only for M4) | F1. Hard blocker; host-side, outside my hand-over. Decides whether 4 of 6 compose services can ever start | Attach it, then I re-run step 4. If node-05 is meant to be CPU-only, `README.md:23,36,47` and `docker-compose.node05.yml` all need rewriting and WS-F needs re-planning |
| **D-2** | NFS `soft` vs `hard` mount for the two shares | F5 / step 1. `hard` hangs processes indefinitely if node-01 goes away; `soft` risks silent short reads | `soft` with `nofail`, as proposed - node-05 is a fallback node and must not wedge when the hub blips |
| **D-3** | node-exporter: keep the host binary, or switch to the compose container | F4.1. They collide on :9100 | Keep the host binary (v1.8.2, running, scrapeable); omit `node-exporter` from node-05's compose invocation |
| **D-4** | Is `/mnt/models` on node-05 meant to be the NFS share, or the local `/data/models` compose actually uses? | F5 / R6. Decides whether node-05 shares node-01's weights or needs its own copy - and with no 1 TB NVMe (F3) a local copy has to fit in 149 GB | Mount the NFS share for recovery/operator use as proposed, and separately resolve whether `/data/models` should be repointed at it before M4 |
| **D-5** | The missing 1 TB NVMe (F3) - attach it, or accept `/data` on root? | 149 GB free, shared with `/`, no isolation. An ffmpeg scratch runaway fills `/` | Attach it if it exists. If not, accept for M4 but put `/data/ffmpeg-tmp` under a quota |
| **D-6** | Who corrects `README.md:36` and adds the Prometheus node-05 target? | Both are needed for M4, both are repo edits, both are outside this package | Assign to a follow-up package sequenced against WP-24 |

---

## 6. What remains for M4 on node-05

| # | Item | State | Blocked by |
|---|---|---|---|
| 1 | GPU physically attached and visible | **NOT DONE** | D-1, Proxmox host |
| 2 | `nvidia-smi` reports a device + CUDA >= 12.4 | **NOT DONE** | item 1 |
| 3 | Container toolkit proven end-to-end (`--gpus all`) | **NOT DONE** | item 1 |
| 4 | NVIDIA driver >= 570.x | **DONE** - 580.159.03 open (L9) | - |
| 5 | Docker installed, active, enabled | **DONE** - 29.5.3 (L15) | - |
| 6 | Docker Compose plugin | **DONE** - v5.1.4 (L16) | - |
| 7 | NVIDIA Container Toolkit installed + runtime registered | **DONE (packages)** - 1.19.1 (L18, L19); function unproven | item 1 for proof |
| 8 | `/mnt/ivgs-shared` mounted | **NOT DONE** - does not exist (L24) | approval only |
| 9 | `/mnt/models` mounted | **NOT DONE** - empty local dir (L25) | approval only, D-4 |
| 10 | node-exporter running and scrapeable | **DONE** - v1.8.2, HTTP 200 from node-01 (L28-L30) | - |
| 11 | node-05 registered as a Prometheus target | **NOT DONE** (R8) | D-6, repo edit, out of scope |
| 12 | `/data/{models,comfyui-output,ffmpeg-tmp}` provisioned | **NOT DONE** (R5) | D-5 |
| 13 | 1 TB NVMe present | **NOT DONE** - no `sdb` (L12) | D-5 |
| 14 | `.env.node05` present on node | **NOT DONE** (R9, L36) | M4 deploy |
| 15 | GHCR pull path (login or `docker load`) | **NOT DONE** (L22) | M4 deploy |
| 16 | Networking, DNS, firewall, clock | **DONE** (L31-L33, N4) | - |
| 17 | Worker deploy | **OUT OF SCOPE** by the brief | - |

---

## 7. Documentation discrepancies found (recorded, not fixed)

| Document | Claim | Reality |
|---|---|---|
| `dev/CLAUDE.md:23` | node-05 OFFLINE | Powered on, SSH-reachable, booted 2026-08-15 11:09 (L1, L2). *Accurate in spirit - no IVGS services run - but "OFFLINE" reads as unreachable.* |
| `IVGS_v5_Master_Sequence_Plan_to_Production.md:25` | "node-05 and node-06 remain OFFLINE" | Same as above for node-05. node-06 not checked (out of scope). |
| `README.md:36` | 8 vCPU, 24 GB RAM, 1 TB NVMe, RTX 5080 16 GB | 12 vCPU, 47 GiB RAM, **no NVMe**, **no GPU** (L5, L10, L12) |
| `README.md:23,47` | node-05 runs ComfyUI/Ollama/nvidia-gpu-exporter | Impossible in current state (F1) |
| `README.md:218` | "`/mnt/ivgs-shared` mounted on all nodes" | Not mounted, not even present, on node-05 (L24) |
| `docs/.../WP-15 report:207` | "node-02 through node-05 use IOMMU/VFIO passthrough" | No VFIO or IOMMU inside node-05's guest (L7) |

No new swallowed-failure instances were found in this package (no application
code was read), so `reports/WP-00-SWALLOWED-FAILURES_2026-08-14.md` is
unchanged.

---

## 8. Files touched

| File | Change |
|---|---|
| `dev/workpackages/reports/WP-25-NODE05-PREP-report_2026-08-15.md` | created (this file) |

Nothing else. No file on node-05 was modified. No container anywhere was
started, stopped or recreated. Nothing staged, committed or pushed.

---

## 9. Pass 1 exit gate

**MET - and STOPPED as instructed.**

Survey complete with live evidence for every claim; install plan written and
not executed; six decisions raised. Pass 2 will not begin until the operator
approves the plan in section 4 and answers D-1 through D-5.

The critical path is **D-1**: without a GPU attached to the VM, steps 1-3
still leave node-05 unable to serve any of its four GPU roles, and M4's
node-05 leg cannot close.

---
---

# PASS 2 - execution and verification

| | |
|---|---|
| **Pass 2 date** | 2026-08-15 |
| **Operator decisions received** | D-1 resolved operator-side (GPU passed through on the Proxmox host, VM stop/started). D-2 `soft`+`nofail`. D-3 keep host binary, omit from compose. D-4 mount both, record the weights question. D-5 no NVMe, accept `/data` on root **with** the quota. D-6 follow-up package. |
| **Authorised** | Steps 1-4 including the `--gpus all` toolkit proof. Explicitly still forbidden: `compose up`, worker deploy. Neither was done. |

## 10. Step 4 FIRST - GPU verification (run before anything else, as instructed)

D-1 is **confirmed resolved**. The VM rebooted at 11:27 (pass 1 saw a
11:09 boot), and an NVIDIA device is now on the guest PCI bus.

### 10.1 The card is NOT what the documentation claims - recorded verbatim

The operator flagged mid-pass that the physical card is an RTX 5000 Blackwell
48 GB rather than the RTX 5080 in the docs, and asked that whatever
`nvidia-smi` prints be recorded verbatim. It is reproduced exactly:

    index, name, uuid, pci.bus_id, memory.total [MiB], driver_version, vbios_version, compute_cap, ecc.mode.current
    0, NVIDIA RTX PRO 5000 Blackwell, GPU-a6b392e0-8419-7e25-641b-8dae89f10433, 00000000:06:10.0, 48935 MiB, 580.159.03, 98.02.92.00.01, 12.0, Disabled

And from `nvidia-smi -q`, verbatim:

    CUDA Version                                           : 13.0
        Product Name                                       : NVIDIA RTX PRO 5000 Blackwell
        Product Brand                                      : NVIDIA RTX
        Product Architecture                               : Blackwell
        Persistence Mode                                   : Disabled
            Total                                          : 48935 MiB

Note the exact product string is **"NVIDIA RTX PRO 5000 Blackwell"** - it
carries `PRO`, which the operator's message did not. `nvidia-smi`'s own table
view truncates it to `NVIDIA RTX PRO 5000 Blac...`, so the full string above
(from `--query-gpu=name`) is the one to use in documentation.

| Attribute | Value (as reported by the hardware) |
|---|---|
| Product name | `NVIDIA RTX PRO 5000 Blackwell` |
| VRAM total | **48935 MiB** (~47.8 GiB) |
| Driver | 580.159.03 (UNIX **Open** Kernel Module) |
| CUDA version | **13.0** |
| Compute capability | **12.0** (sm_120, Blackwell) |
| PCI ID / bus | `10de:2bb3` (audio fn `10de:22e8`) at `00000000:06:10.0` |
| Subsystem | `10de:204d` |
| VBIOS | 98.02.92.00.01 |
| GPU UUID | `GPU-a6b392e0-8419-7e25-641b-8dae89f10433` |
| ECC | Disabled |
| Persistence mode | Disabled |
| Power cap | 300 W (idle 15 W, 35 C at survey) |

### 10.2 Step 4 checks - all four passed

| Check | Result | Evidence |
|---|---|---|
| 4.1 `lspci` shows a `10de:` device | **PASS** | `06:10.0 VGA compatible controller [0300]: NVIDIA Corporation Device [10de:2bb3] (rev a1)` |
| 4.2 `nvidia-smi` prints device, driver, VRAM | **PASS** | table above; kernel modules `nvidia`, `nvidia_uvm`, `nvidia_drm`, `nvidia_modeset` all loaded; `dmesg` -> `NVRM: loading NVIDIA UNIX Open Kernel Module ... 580.159.03` with no `No NVIDIA GPU found` after the reboot |
| 4.3 CUDA >= 12.4 (`docs/ivgs_v5_functional_spec.md:1457`) | **PASS** - 13.0 | `nvidia-smi -q` |
| 4.4 **Container toolkit end-to-end** | **PASS** | see 10.3 |

### 10.3 The toolkit proof - this is the one that actually matters

Pass 1 could only confirm package presence. Now proven functional:

    docker run --rm --gpus all nvidia/cuda:12.8.0-base-ubuntu24.04 nvidia-smi
    -> rc=0, prints "NVIDIA RTX PRO 5000 Blac..." / 48935MiB / Driver 580.159.03 / CUDA 13.0

    docker run --rm --gpus all nvidia/cuda:12.8.0-base-ubuntu24.04 ls /dev/nvidia*
    -> /dev/nvidia-modeset  /dev/nvidia-uvm  /dev/nvidia-uvm-tools  /dev/nvidia0  /dev/nvidiactl
    -> nvidia-smi --query-gpu=name,memory.total -> "NVIDIA RTX PRO 5000 Blackwell, 48935 MiB"

Two things this also settles:

- **CUDA 12.x images work on the 13.0 driver.** The image is CUDA 12.8 and ran
  correctly against a CUDA 13.0 driver. Backward compatibility holds, so the
  existing worker images do not need rebuilding for this card. Observed, not
  assumed.
- **F6 is now a live behaviour, not a theoretical one.** A third run
  *without* `--gpus all` also saw the GPU:

      docker run --rm nvidia/cuda:12.8.0-base-ubuntu24.04 nvidia-smi --query-gpu=name --format=csv,noheader
      -> NVIDIA RTX PRO 5000 Blackwell

  This is `default-runtime: nvidia` in `/etc/docker/daemon.json` combined with
  `NVIDIA_VISIBLE_DEVICES=all` baked into CUDA base images. Every container on
  node-05 descended from a CUDA base image gets the full GPU whether or not it
  asks. Left as found per pass 1 - flagging that it makes the `x-gpu-resources`
  reservations in `docker-compose.node05.yml:36-43` largely decorative on this
  node, and there is no VRAM partitioning between comfyui, ollama and the
  exporter. **Recorded as an open M4 decision (O-2 below); not changed.**

### 10.4 Planning consequence - node-05 is a far bigger node than M4 assumes

`README.md:23,36` budgets node-05 at **16 GB** VRAM and scopes it to "SDXL /
SD3.5 fallback" and "Ollama small models". The card is **48935 MiB - roughly
3x** that. `ivgs-workers/configs/media_generation.yml:50-51` and the
`image_generation_fallback` / `llm_inference_fallback` queue design were all
sized against the 16 GB figure.

This is a planning input, not a defect, and re-scoping node-05's role is well
outside this package. Recorded as **O-1** below.

---

## 11. Steps 1-3 and 5 - what was changed on node-05

All changes are on node-05 only. `/etc/fstab` was backed up to
`/etc/fstab.bak-wp25-20260815` before the first edit.

### 11.1 Step 1 - NFS mounts (D-2: `soft` + `nofail`, as approved)

Created `/mnt/ivgs-shared`; added two fstab lines exactly as proposed in
section 4; `systemctl daemon-reload` + `mount -a` (rc=0).

**Gate - artifact-checked, not exit-code-checked:**

| Gate | Result |
|---|---|
| `mountpoint -q /mnt/ivgs-shared` | IS a mountpoint |
| `mountpoint -q /mnt/models` | IS a mountpoint |
| `stat -f -c %T` both | `nfs` |
| Negotiated options | `nfs4 (rw,relatime,vers=4.2,...,soft,proto=tcp,timeo=100,retrans=3,...,_netdev)` - `soft` confirmed honoured, D-2 as decided |
| Capacity visible | both `489G` total, `254G` avail (node-01's backing store) |
| **Cross-node write probe** | node-05 wrote `1786794433` to `/mnt/ivgs-shared/.wp25-node05-probe`; **node-01 read back the identical value**; probe then deleted and confirmed absent from both nodes |
| Real content visible | `/mnt/models` shows `cogvideox-5b` from node-01 |

The probe is the actual proof - `mount -a` returning 0 would have proven
nothing on its own.

One incidental note: the probe could not be deleted *from node-01* (permission
denied - it was root-owned via `no_root_squash`, and node-01's shell user is
not in `/mnt/ivgs-shared`'s owning group). It was removed from node-05. Worth
knowing operationally: files node-05 writes to the share are root-owned and
not removable by an ordinary node-01 user.

### 11.2 Step 2 - dead fstab entry removed

`/dev/sdb1 /opt/factory ext4 defaults,nofail 0 2` deleted (referenced a disk
that does not exist - pass 1 L14). Per D-5 no NVMe is coming, so the entry had
no future use.

### 11.3 Step 3 - node-exporter (D-3: keep host binary)

**Nothing installed, nothing changed.** Per D-3 the host binary stays and
`node-exporter` is to be **omitted from node-05's compose invocation** at M4.

Recording the operational consequence explicitly, since D-3 asked for it:

> **M4 deploy note for node-05.** `docker-compose.node05.yml:171-180` defines a
> `node-exporter` service (`prom/node-exporter:v1.8.1`) bound to
> `0.0.0.0:9100`. It **must not** be brought up on node-05 - the host binary
> `/usr/local/bin/node_exporter` v1.8.2 (systemd unit `node_exporter.service`,
> enabled) already owns :9100 and `up` would fail to bind. Name the services
> explicitly on the compose invocation, e.g. `comfyui ollama ffmpeg-worker
> celery-worker nvidia-gpu-exporter`, and never a bare `up`.

Still healthy after all of this pass's changes: `systemctl is-active` ->
`active`; localhost scrape HTTP 200; **from node-01, `curl http://node-05:9100/metrics` -> HTTP 200, 83704 bytes**.

`http://node-05:9400/metrics` returns nothing (connection refused) - expected,
the `nvidia-gpu-exporter` is a compose service and deploying it is out of
scope. GPU telemetry therefore does **not** flow yet.

### 11.4 Step 5 (D-5) - `/data` on root, with an enforced scratch cap

Created `/data/models`, `/data/models/ollama`, `/data/comfyui-output`,
`/data/ffmpeg-tmp` (the paths `docker-compose.node05.yml:66-69,92-93,156-157`
expects). All root-owned; the workers run as root (`C_FORCE_ROOT: "1"`).

Scratch cap implemented as a fixed-size loop-backed ext4 volume:

    /data/ffmpeg-tmp.img  (40 GiB)  ->  /data/ffmpeg-tmp  ext4  loop,nofail,noatime  0 0

**A mistake I made and corrected, because it matters.** My first attempt ran
`fallocate -l 40G` and then `mkfs.ext4`. `mkfs.ext4` issues discard on the
device by default, which punched holes straight back through the
preallocation: the image was 40 GiB apparent but only **262 MiB** actually
allocated (`du --apparent-size` 40G vs `du` 262M; `stat` blocks=535816).
The 40 GiB ceiling still held, but the space was *not* reserved - so weights
growing in `/data/models` could have starved the scratch volume and produced
confusing backing-store I/O errors rather than a clean ENOSPC. I unmounted,
re-ran `fallocate -l 40G` to fill the holes (non-destructive - it allocates
uninitialised extents without touching existing data), and remounted. The
filesystem survived intact. **For future use: `mkfs.ext4 -E nodiscard`.**

**Gate - the cap is proven in both directions, on the corrected volume:**

| Test | Result |
|---|---|
| `fallocate -l 45G` inside the volume | **fails** - `No space left on device`, rc=1. A runaway cannot exceed 40 GiB. |
| `fallocate -l 30G` inside the volume | succeeds, rc=0. Normal scratch use is unimpeded. |
| Root free while scratch is 77% full | `194G / 77G used / 109G avail` - **unchanged**. Scratch use cannot move root's free space. |
| Space actually reserved | root went `149G avail` -> `109G avail` on reallocation; `du` now reports 41G actual |
| Volume state at rest | `/dev/loop0 ext4 40G 24K 40G 1% /data/ffmpeg-tmp` |

Final disk layout on node-05:

    /dev/mapper/ubuntu--vg-ubuntu--lv ext4  194G   77G  109G  42% /
    /dev/loop0                        ext4   40G   24K   40G   1% /data/ffmpeg-tmp
    192.168.1.90:/mnt/ivgs-shared     nfs4  489G  214G  254G  46% /mnt/ivgs-shared
    192.168.1.90:/mnt/models          nfs4  489G  214G  254G  46% /mnt/models

109 GiB remains on root for `/data/models` and `/data/comfyui-output`. The
40 GiB scratch size is a judgement call, not a derived figure - it is roughly
half the free space after weights, and it is trivially resizable (unmount,
`fallocate` larger, `resize2fs`). Say the word if you want it different.

---

## 12. Verification - observed live vs NOT verified

### 12.1 Observed live (I watched the artifact, not just an exit code)

- GPU present on PCI, `nvidia-smi` output, model/VRAM/CUDA/compute-cap - 10.1.
- `--gpus all` container reaching the GPU, `/dev/nvidia*` nodes inside the
  container, CUDA 12.8 image on a 13.0 driver - 10.3.
- GPU visible to a container *without* `--gpus` - 10.3.
- Both NFS shares mounted as `nfs4` with `soft` honoured; **cross-node write
  probe read back byte-identical on node-01** - 11.1.
- Scratch cap rejecting 45 GiB with ENOSPC and accepting 30 GiB; root free
  space unmoved while the scratch volume was 77% full - 11.4.
- Sparse-image defect and its correction (`du` 262M -> 41G) - 11.4.
- node-exporter scrapeable from node-01 after all changes: HTTP 200, 83704
  bytes - 11.3.
- `/etc/fstab` final content, backup file present - 11.

### 12.2 NOT verified - stated plainly

- **Reboot persistence.** The fstab entries (2 NFS + 1 loop) have been proven
  by `mount -a`, not by an actual boot. `mount -a` does not exercise systemd
  unit ordering, and `_netdev`/`nofail` behaviour at boot is precisely the
  class of thing that only fails at boot. **I did not reboot node-05 - that is
  a disruptive action you did not authorise, and you had just brought the VM
  up.** Recommend a single reboot as the closing gate; I will run it and
  re-check all three mounts plus node_exporter on your word.
- **Any GPU compute.** `nvidia-smi` enumerates the card; no CUDA kernel, no
  model load, no inference was run. Capability beyond enumeration is unproven.
- **48935 MiB usable under load.** Reported total only; never allocated.
- **ComfyUI / Ollama / any worker.** Not deployed, not started - scope OUT.
- **GPU telemetry.** `nvidia-gpu-exporter` not deployed; :9400 refused.
- **NFS behaviour under node-01 failure.** `soft` was chosen (D-2) but a
  node-01 outage was not simulated.
- **`ivgs-workers` image pull.** No GHCR credentials on node-05 (pass 1 L22);
  untested.

---

## 13. Files touched (pass 2)

**On node-05** (no repo file, no other node):

| Path | Change | Reversible via |
|---|---|---|
| `/etc/fstab` | 2 NFS lines + 1 loop line added; dead `/dev/sdb1` line removed | `cp /etc/fstab.bak-wp25-20260815 /etc/fstab` |
| `/etc/fstab.bak-wp25-20260815` | created (backup) | - |
| `/mnt/ivgs-shared` | directory created, now an NFS mountpoint | `umount`, `rmdir` |
| `/mnt/models` | pre-existing empty dir, now an NFS mountpoint | `umount` |
| `/data/models`, `/data/models/ollama`, `/data/comfyui-output`, `/data/ffmpeg-tmp` | directories created | `rm -rf /data` |
| `/data/ffmpeg-tmp.img` | 40 GiB ext4 image created | `umount`, `rm` |

**In the repo:** this report only.

Nothing staged, committed, pushed or deployed. No container was created except
three `--rm` throwaway `nvidia/cuda` probes, all of which exited and removed
themselves (`docker ps -a` is empty of them). No node other than node-05 was
modified; the node-01 commands were reads plus the one probe-file read.

---

## 14. M4 readiness - updated

| # | Item | Pass 1 | Now |
|---|---|---|---|
| 1 | GPU attached and visible | NOT DONE | **DONE** - `10de:2bb3` at `06:10.0` |
| 2 | `nvidia-smi` reports device + CUDA >= 12.4 | NOT DONE | **DONE** - CUDA 13.0, 48935 MiB |
| 3 | Container toolkit proven end-to-end | NOT DONE | **DONE** - `--gpus all` reaches the GPU |
| 4 | Driver >= 570.x | DONE | DONE - 580.159.03 open |
| 5 | Docker active + enabled | DONE | DONE - 29.5.3 |
| 6 | Compose plugin | DONE | DONE - v5.1.4 |
| 7 | Toolkit installed | DONE (packages) | **DONE (functional)** |
| 8 | `/mnt/ivgs-shared` mounted | NOT DONE | **DONE** - nfs4, cross-node probe |
| 9 | `/mnt/models` mounted | NOT DONE | **DONE** - nfs4, `cogvideox-5b` visible |
| 10 | node-exporter running + scrapeable | DONE | DONE - 200 / 83704 B from node-01 |
| 11 | node-05 a Prometheus target | NOT DONE | **STILL NOT DONE** - repo edit, D-6 follow-up |
| 12 | `/data/{models,comfyui-output,ffmpeg-tmp}` provisioned | NOT DONE | **DONE** - with 40 GiB enforced scratch cap |
| 13 | 1 TB NVMe | NOT DONE | **WON'T DO** - D-5, accepted on root |
| 14 | `.env.node05` on node | NOT DONE | **STILL NOT DONE** - M4 deploy |
| 15 | GHCR pull path | NOT DONE | **STILL NOT DONE** - M4 deploy |
| 16 | Network / DNS / firewall / clock | DONE | DONE |
| 17 | Worker deploy | OUT OF SCOPE | OUT OF SCOPE - not done |
| 18 | Reboot-persistence proof | - | **NOT DONE** - awaiting your go-ahead |

### What remains for M4 on node-05

1. **Reboot to prove the three fstab mounts survive a boot** (12.2) - one
   command, needs your say-so.
2. **`.env.node05`** created on the node (`IVGS_WORKERS_TAG`,
   `POSTGRES_PASSWORD`, `NODE_01_IP`). Carries a secret - operator action.
3. **Image path**: `docker login ghcr.io` on node-05, or the `docker save` /
   `docker load` artifact route per `RECOVERY.md`.
4. **Prometheus target** for `node-05:9100`, plus `node-05:9400` once the GPU
   exporter is up - repo edit, D-6 follow-up, sequenced against WP-24.
5. **`README.md:23,36,47` correction** - now needs the *48 GB RTX PRO 5000
   Blackwell*, not merely a 5080 fix. D-6 follow-up.
6. Compose invocation for node-05 must name services explicitly and **exclude
   `node-exporter`** (11.3).
7. The open decisions below.

### Open decisions recorded for M4 (not acted on)

| ID | Decision | Why |
|---|---|---|
| **O-1** | Re-scope node-05's role for **48 GB**, not 16 GB | 10.4. `README.md:23`, `ivgs-workers/configs/media_generation.yml:50-51` and the fallback-queue sizing all assume 16 GB. node-05 can now hold far more than SDXL/SD3.5 + a small Ollama model. |
| **O-2** | Weights: `/data/models` (local, on the 109 GiB root) vs `/mnt/models` (NFS from node-01) | D-4, pass 1 F5/R6, as you asked me to record. Compose bind-mounts `/data/models` and never `/mnt/models`. Both now exist on node-05. **Nothing was repointed.** With no NVMe (D-5) the local copy competes with everything else on root. |
| **O-3** | `default-runtime: nvidia` + no VRAM partitioning | 10.3. Every CUDA-derived container gets the whole 48 GB card whether or not it requests it; the compose GPU reservations are effectively decorative here. |
| **O-4** | 40 GiB scratch size | 11.4. A judgement call, easily resized. |

---

## 15. Exit gate

**MET, with one gap named.**

Steps 1-4 plus the D-5 quota executed and gated on artifacts rather than exit
codes. The GPU is confirmed as a **NVIDIA RTX PRO 5000 Blackwell, 48935 MiB,
driver 580.159.03, CUDA 13.0, compute 12.0** - recorded verbatim, and
materially different from the documented RTX 5080 16 GB. The container toolkit
is proven functional end-to-end. Both NFS shares are mounted and proven by a
cross-node write probe. The scratch cap is proven to reject an over-size
allocation while leaving root untouched. No compose was run and no worker was
deployed.

The one gap is deliberate and not papered over: **reboot persistence of the
three new fstab mounts is unproven**, because rebooting node-05 was not
authorised. That is the last thing standing between this node and a clean
"prepared" verdict.

*(Gap closed in section 16 below - the operator authorised the reboot and it
passed. The paragraph above is left as written to preserve the record of what
was and was not known at the end of pass 2.)*

---
---

# PASS 2 ADDENDUM - reboot persistence gate (operator-authorised)

The operator authorised the reboot that section 12.2 flagged as the one
unverified item. It was run, and it passed.

## 16. Reboot verification

### 16.1 The reboot was real, not a reconnect

| | |
|---|---|
| boot_id **before** | `07ac9085-0e04-44e5-b74a-e2cd49ed731c` (boot 11:27) |
| boot_id **after** | `7c121069-99f7-437f-ab35-7a4018332dd4` (boot 11:53) |
| Recovery | SSH answered on the 3rd retry; `uptime` -> `up 0 min` |

The boot ID changing is the proof - an unchanged ID would have meant the box
never went down.

Pre-reboot state was re-confirmed first: all three targets reported
`is a mountpoint` with the correct sources. (An earlier `findmnt` call of mine
returned nothing for the three paths; that was my invocation form - `findmnt`
does not take multiple targets that way - not a state problem. Re-checked one
at a time and via `mountpoint`/`df` before proceeding.)

### 16.2 Everything came back unaided - nothing was mounted or started by hand

| Check | Result |
|---|---|
| `/mnt/ivgs-shared` | **MOUNTED** - `192.168.1.90:/mnt/ivgs-shared nfs4` |
| `/mnt/models` | **MOUNTED** - `192.168.1.90:/mnt/models nfs4` |
| `/data/ffmpeg-tmp` | **MOUNTED** - `/dev/loop0 ext4` |
| systemd mount units | `mnt-ivgs\x2dshared.mount`, `mnt-models.mount`, `data-ffmpeg\x2dtmp.mount` - all `loaded active mounted` |
| `systemctl --failed` | **empty** - no failed units |
| `node_exporter` | `active`, `enabled`; local scrape HTTP 200 |
| `docker` | `active`, `enabled` |
| GPU | `NVIDIA RTX PRO 5000 Blackwell, 48935 MiB, 580.159.03` |

The three mounts becoming proper systemd `.mount` units with none in a failed
state is the specific thing `mount -a` could not have shown, and it is what
`_netdev` / `nofail` ordering had to get right.

### 16.3 Function re-proven after the reboot, not just presence

| Check | Result |
|---|---|
| Container toolkit | `docker run --rm --gpus all nvidia/cuda:12.8.0-base-ubuntu24.04 nvidia-smi --query-gpu=name,memory.total` -> `NVIDIA RTX PRO 5000 Blackwell, 48935 MiB`, rc=0 |
| Scratch cap still enforced | `fallocate -l 45G` -> `No space left on device`, rc=1; root unchanged at `109G` avail |
| **Cross-node NFS round trip** | node-05 wrote `1786794859643295703`; **node-01 read the identical value**; probe deleted, confirmed absent from both |
| **Scrape from node-01** | `curl http://node-05:9100/metrics` -> **HTTP 200, 84327 bytes** |
| Containers left behind | `docker ps -a` -> **0** (the `--rm` probes cleaned themselves up) |

### 16.4 Readiness table - final

Item 18 ("Reboot-persistence proof") in section 14 moves from **NOT DONE** to
**DONE**. Items 11, 14 and 15 (Prometheus target, `.env.node05`, GHCR pull
path) remain NOT DONE and are M4-deploy or follow-up-package work, as recorded.
Item 17 (worker deploy) remains correctly OUT OF SCOPE - no compose was ever
run and no worker was ever deployed.

## 17. Package verdict - CLOSED

**Exit gate MET in full. No gaps outstanding within this package's scope.**

node-05 is prepared for M4 to the boundary the brief drew. Confirmed by
observation, not inference:

- GPU present and enumerated - **`NVIDIA RTX PRO 5000 Blackwell`, 48935 MiB,
  driver 580.159.03, CUDA 13.0, compute 12.0** - recorded verbatim and
  materially different from the documented "RTX 5080 16 GB".
- NVIDIA Container Toolkit proven functional end-to-end, before and after a
  reboot.
- Both NFS shares mounted, `soft`+`nofail` per D-2, proven by cross-node write
  probes on both sides of the reboot.
- `/data` provisioned with a 40 GiB scratch volume whose cap is proven to
  reject an over-size allocation while leaving root untouched.
- node-exporter running, enabled, and scrapeable from node-01 - host binary
  retained per D-3, with the compose-exclusion note recorded at 11.3.
- All three fstab mounts survive a real reboot as clean systemd mount units,
  with no failed units.

**Handed forward, unresolved by design:**

- **O-1 through O-4** (section 14) stay open as M4 decisions. Per the operator,
  the fleet-hardware errata package will pick them up together with the
  `README.md:23,36,47` corrections and the Prometheus `node-05:9100` /
  `node-05:9400` targets (D-6). Nothing in the repo was edited for any of them.
- `.env.node05` and the GHCR pull path remain M4-deploy operator actions.
- No GPU *compute* was ever exercised - the card is enumerated, not benchmarked.

**Scope discipline:** no `compose up`, no worker, no repo edit but this report,
nothing touched on any node other than node-05, and nothing staged, committed
or pushed. The concurrent WP-03 work on nodes 01/02/03/04 was not disturbed;
node-01 was read-only apart from reading back two probe files on the NFS share.
