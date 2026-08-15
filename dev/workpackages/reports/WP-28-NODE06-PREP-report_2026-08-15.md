# WP-28-NODE06-PREP - node-06 clone de-duplication and readiness survey

| | |
|---|---|
| **Package** | WP-28-NODE06-PREP (follow-on to WP-25-NODE05-PREP) |
| **Date** | 2026-08-15 |
| **HEAD SHA** | `134c34f40594271594928e6909ed71f54e09a1a6` |
| **Target** | node-06 - the cloned VM, `192.168.1.94` -> now `192.168.1.95` (root SSH, explicitly handed over) |
| **Status** | **CLOSED.** Pass 1 (identity de-duplication + survey) and Pass 2 (full prep sequence) both complete and verified. |
| **node-05** | Shut down throughout. **Not touched.** See section 9 before restarting it. |

## 0. Scope and authority

Operator handed over node-06 for this package. Steps 1-6 (identity
de-duplication) were authorised as one pass and are **executed**. Step 7 (the
readiness survey) was required to be **read-only, stopping with findings** -
and it is: nothing was changed after the reboot except node-01's
`known_hosts`, which step 6 explicitly asked for.

No compose, no workers, no repo edit but this report. node-05 was never
contacted - it is powered off, and `192.168.1.94` was confirmed silent after
the IP move (section 3.4).

---

## 1. Step 0 - identity gate: PASSED

The gate was to distinguish the node-06 VM from node-05's by GPU. Run before
any change:

    index, name, uuid, pci.bus_id, memory.total [MiB], driver_version, vbios_version, compute_cap
    0, NVIDIA GeForce RTX 5080, GPU-49dacec4-c9d8-7109-cffc-9ff262186fe6, 00000000:06:10.0, 16303 MiB, 580.159.03, 98.03.3B.C0.3E, 12.0

    06:10.0 VGA compatible controller [0300]: NVIDIA Corporation Device [10de:2c02] (rev a1)
    06:10.1 Audio device [0403]: NVIDIA Corporation Device [10de:22e9] (rev a1)

**RTX 5080, 16303 MiB -> this is the node-06 VM. Gate passed, proceeded.**

Every GPU identifier differs from node-05's card recorded in WP-25:

| | node-05 (WP-25) | This VM |
|---|---|---|
| Name | `NVIDIA RTX PRO 5000 Blackwell` | `NVIDIA GeForce RTX 5080` |
| VRAM | 48935 MiB | **16303 MiB** |
| PCI ID | `10de:2bb3` | `10de:2c02` |
| GPU UUID | `GPU-a6b392e0-...` | `GPU-49dacec4-...` |
| VBIOS | 98.02.92.00.01 | 98.03.3B.C0.3E |

There was no ambiguity: had this reported the PRO 5000 / 48 GB I would have
stopped without touching anything.

---

## 2. GPU recorded verbatim

From `nvidia-smi --query-gpu=... --format=csv` and `nvidia-smi -q`, exactly as
printed:

    0, NVIDIA GeForce RTX 5080, GPU-49dacec4-c9d8-7109-cffc-9ff262186fe6, 00000000:06:10.0, 16303 MiB, 580.159.03, 98.03.3B.C0.3E, 12.0

    CUDA Version                                           : 13.0
        Product Name                                       : NVIDIA GeForce RTX 5080
        Product Brand                                      : GeForce
        Product Architecture                               : Blackwell
        Persistence Mode                                   : Disabled
        GPU UUID                                           : GPU-49dacec4-c9d8-7109-cffc-9ff262186fe6

    memory.total [MiB], power.max_limit [W], ecc.mode.current
    16303 MiB, 400.00 W, [N/A]

| Attribute | Value |
|---|---|
| Product name | `NVIDIA GeForce RTX 5080` |
| Product brand | **`GeForce`** (consumer, not professional) |
| VRAM total | **16303 MiB** (~15.9 GiB) |
| Driver | 580.159.03 (UNIX Open Kernel Module) |
| CUDA | 13.0 |
| Compute capability | 12.0 (sm_120, Blackwell) |
| PCI / bus | `10de:2c02` (audio `10de:22e9`) at `00000000:06:10.0` |
| Power cap | 400 W |
| ECC | **`[N/A]`** - GeForce silicon has no ECC at all |

Note the ECC distinction against node-05: node-05's PRO card reported ECC
`Disabled` (present, switched off); this reports `[N/A]` (absent). That is a
hardware capability difference, not a setting.

---

## 3. Steps 1-6 - executed and verified

`/etc/hostname`, `/etc/hosts` and `/etc/netplan/50-cloud-init.yaml` were each
backed up to `*.bak-wp28` before edit.

### 3.1 Step 1 - hostname

| | Before | After |
|---|---|---|
| `/etc/hostname` | `node-05` | `node-06` |
| `/etc/hosts` `127.0.1.1` | `node-05` | `node-06` |
| `hostnamectl --static` | node-05 | `node-06` |

The cluster map block in `/etc/hosts` already carried correct entries for all
six nodes including `192.168.1.95 node-06`; only the `127.0.1.1` self-line was
wrong. Left the map untouched.

### 3.2 Step 2 - machine-id (clone hygiene, S-10 class)

| | Value |
|---|---|
| Before | `0709f3cf570343478247dfc3e51fbbbc` - **identical to node-05's, recorded in WP-25 pass 1 L4** |
| After | `ff4e418e66ba45b0bf2c44cd37ad6810` |

`/var/lib/dbus/machine-id` is a symlink to `/etc/machine-id` and was confirmed
intact after regeneration, so both identities moved together.

### 3.3 Step 3 - SSH host keys (clone hygiene, S-10 class)

All three key pairs were removed and regenerated with `ssh-keygen -A`.

**Before** (these are node-05's live keys - it is powered off and still has
them):

    256  SHA256:0uo6ry7LALvKDStzIAihu2YCh6KyCuCS8SrQDSX+xqo  root@rtx6000  (ECDSA)
    256  SHA256:EMvMt4cKvf8qT0tB4+i24UZVKeENEBmbuqdAZb/C1fA  root@rtx6000  (ED25519)
    3072 SHA256:lyzPfOY9AlHBVQ5wVWwHcvHnGF0Gi8HWfobG7asT/Qs  root@rtx6000  (RSA)

**After:**

    256  SHA256:/Rj57Gp/rWPVv50keFgSyDVs9cWhHGHFync7iTWDqNk  root@node-06  (ECDSA)
    256  SHA256:BiuLtiMzxJ/9sEVSsoEQtqGlquDeN4B4X4TkmBw4r/A  root@node-06  (ED25519)
    3072 SHA256:n/NaPewTr10gXk/XrlUyQx6qH8vQ9tKdyR4BN2iu438  root@node-06  (RSA)

**A finding wider than this package.** The old keys are dated `Mar 1 00:13` and
carry the comment **`root@rtx6000`** - a hostname that is neither node-05 nor
node-06. These keys predate node-05's own build (its filesystem is dated
Jun 6). They came from an older golden image, which means **any other node
built from that same image is very likely presenting the identical SSH host
keys**. Shared host keys defeat host authentication fleet-wide: a client that
trusts one node silently trusts every sibling. I have not checked nodes
02/03/04 - out of scope, and I will not connect to them without a hand-over.
Raised as **N-1** in section 8.

### 3.4 Steps 4-5 - static IP .94 -> .95, and reboot

`50-cloud-init.yaml` changed to `addresses: [192.168.1.95/24]`; file mode `600`
preserved. Validated **before** committing to a reboot:

- `netplan generate` -> rc=0
- rendered `/run/systemd/network/*.network` -> `Address=192.168.1.95/24`,
  `Gateway=192.168.1.1`
- `.95` pinged first and was **silent** - no address conflict
- cloud-init is `status: disabled` with `preserve_hostname: true`
  (`/etc/cloud/cloud.cfg.d/99-installer.cfg:6`), so it will not overwrite
  either the hostname or the netplan file on boot

Rebooted. boot_id `957ef4d5-d12e-46a1-afcd-711475ae4616` ->
`c8562193-1195-4b7d-9659-238b8fc24ae5` - a real reboot, not a reconnect.

**Post-reboot gate - all confirmed:**

| Check | Result |
|---|---|
| Answers at `192.168.1.95` | **YES** - 4th retry |
| `hostname` / `hostnamectl --static` / `/etc/hostname` | `node-06` on all three |
| `/etc/hosts` `127.0.1.1` | `node-06` |
| machine-id | `ff4e418e66ba45b0bf2c44cd37ad6810` (new) |
| Interface | `enp6s18  UP  192.168.1.95/24`; default via `192.168.1.1` |
| Host keys | the three new `root@node-06` fingerprints, unchanged across the reboot |
| `systemctl --failed` | **empty** |
| GPU | `NVIDIA GeForce RTX 5080, 16303 MiB` |
| **`192.168.1.94`** | **silent** - address released, as expected with node-05 off |
| From node-01 | `getent hosts node-06` -> `192.168.1.95`; `curl node-06:9100/metrics` -> **HTTP 200, 75278 bytes** |

### 3.5 Step 6 - node-01 `known_hosts`

The host-key regeneration broke my own session mid-pass, exactly as it should:
`REMOTE HOST IDENTIFICATION HAS CHANGED`. The offered ED25519 fingerprint was
`SHA256:BiuLtiMzxJ/9sEVSsoEQtqGlquDeN4B4X4TkmBw4r/A`, which **matches the key I
had just generated** - verified rather than blindly accepted, then cleared.

Final state of `/home/dev/.ssh/known_hosts`:

| Address | State |
|---|---|
| `192.168.1.95` | **Present** - all three node-06 keys; each verified against the live host; `ssh -o StrictHostKeyChecking=yes root@192.168.1.95` connects with **no prompt** |
| `192.168.1.94` | **Absent** - deliberately |

`.94` was left absent on purpose. node-05 still holds the original
`root@rtx6000` keys, which are no longer in `known_hosts`; leaving a stale or
wrong entry there would either block the operator's first connect or, worse,
train them to ignore a mismatch warning. It will be accepted fresh on first
connect after node-05 restarts - and section 9 records the exact fingerprints
to check it against, so that acceptance can be verified rather than assumed.

`ssh-keygen -R` left a backup at `/home/dev/.ssh/known_hosts.old` (pre-existing
behaviour, not cleaned up).

---

## 4. Step 7 - readiness survey (read-only)

### 4.1 The headline: this clone does NOT carry WP-25's work

I expected to find node-05's WP-25 configuration inherited and needing
adjustment. It is **not there**. The clone was taken from a **pre-WP-25
baseline**, not from node-05's current state:

| WP-25 artefact on node-05 | Present on node-06? |
|---|---|
| `/mnt/ivgs-shared` NFS mount | **NO** - directory does not exist, no fstab line |
| `/mnt/models` NFS mount | **NO** - empty local dir, no fstab line |
| `/data/ffmpeg-tmp` 40 GiB capped volume | **NO** - `/data` does not exist |
| `/data/models`, `/data/comfyui-output` | **NO** |
| Removal of the dead `/dev/sdb1` fstab line | **NO** - the dead line is back |
| `/etc/fstab.bak-wp25-20260815` | **NO** |

Its `/etc/fstab` is the original three-line install plus
`/dev/sdb1 /opt/factory ext4 defaults,nofail 0 2`, and `mount | grep -E "nfs|loop"`
returns nothing. Filesystem dates are `Jun 6 21:44-21:52` throughout.

**Consequence: node-06 needs the entire node-05 prep sequence run from
scratch** - it is not a matter of adjusting inherited settings. What it did
inherit from node-05 was purely *identity* (hostname, machine-id, host keys,
IP), all now fixed.

### 4.2 node-05 leftovers the clone inherited - complete list

| # | Leftover | State |
|---|---|---|
| 1 | Hostname `node-05` (`/etc/hostname`, `/etc/hosts` `127.0.1.1`) | **FIXED** (3.1) |
| 2 | machine-id `0709f3cf...` shared with node-05 | **FIXED** (3.2) |
| 3 | SSH host keys shared with node-05 (`root@rtx6000`) | **FIXED** (3.3) |
| 4 | Static IP `192.168.1.94` | **FIXED** (3.4) |
| 5 | Dead fstab entry `/dev/sdb1 -> /opt/factory` (no `sdb`; `/opt/factory` absent) | **STILL PRESENT** - same defect WP-25 removed from node-05 |
| 6 | `/mnt/{shared,datasets,models}` - empty dirs from the golden image, not the IVGS layout | **STILL PRESENT** |
| 7 | `default-runtime: nvidia` in `/etc/docker/daemon.json` | **STILL PRESENT** - identical to node-05, same O-3 concern |
| 8 | Bare-metal `node_exporter` v1.8.2 on `:9100`, unit `node_exporter.service` enabled | **STILL PRESENT** - same :9100 compose collision as node-05 (D-3) |
| 9 | Cached image `nvidia/cuda:12.8.0-base-ubuntu24.04` | **STILL PRESENT** - harmless, useful for the toolkit probe |
| 10 | No GHCR credentials (`/root/.docker/config.json` absent) | **STILL PRESENT** |
| 11 | My own `*.bak-wp28` backups | Created by me this pass; `/etc/hostname.bak-wp28`, `/etc/hosts.bak-wp28`, `/etc/netplan/50-cloud-init.yaml.bak-wp28` still contain the string `node-05` **by design** - they are the rollback path |

Checked and **clean**: no root crontab; no `.env.node0*` or `docker-compose*node0*`
anywhere on the filesystem; no IVGS repo clone (`/opt` holds only `containerd`);
`/root/.ssh/authorized_keys` has 1 key; no containers (`docker ps -a` empty);
no `HostKey` overrides in `sshd_config`; no failed systemd units.

### 4.3 Hardware and platform survey

| Item | Observed |
|---|---|
| OS / kernel | Ubuntu 24.04.4 LTS, 6.8.0-124-generic, x86_64 |
| Virtualisation | `qemu`; QEMU Standard PC (Q35 + ICH9, 2009) |
| CPU | 12 vCPU, AMD Ryzen 9 8945HX |
| RAM | 47 GiB, no swap |
| Disk | **one** 200 GB virtual disk; `/` = 194 G, 37 G used, **148 G avail**. No `sdb`, no NVMe. |
| GPU | RTX 5080 16303 MiB - section 2 |
| Driver | `nvidia-driver-580-open` / `nvidia-dkms-580-open` 580.159.03 |
| Container toolkit | `nvidia-container-toolkit` 1.19.1; `nvidia` runtime registered, **default runtime** |
| Docker | 29.5.3 active; Compose v5.1.4 |
| node-exporter | v1.8.2 active + enabled; local scrape 200; **from node-01: HTTP 200, 75278 bytes** |
| NFS client | `nfs-common` present; `showmount -e 192.168.1.90` sees both exports |
| NFS mounts | **none** |
| Network | `enp6s18` 192.168.1.95/24, default via .1; ufw active; clock synced UTC |
| MAC | `bc:24:11:07:50:f7` (distinct from node-05's - separate VM, not a NIC clash) |

### 4.4 Verified live vs inferred

**Verified live:** everything in sections 1-4.3 - GPU identifiers, all identity
values before and after, netplan render, reboot boot_id change, `.94` silent,
`.95` reachable and strict-SSH clean, node-exporter scraped from node-01,
absence of `/data` and of NFS mounts, absence of the WP-25 artefacts.

**NOT verified:**
- **Container toolkit function on node-06.** Packages are present and the
  runtime is registered, but I did **not** run `docker run --gpus all` - that
  creates a container, and step 7 was read-only. Unproven, exactly as it was
  on node-05 before WP-25 pass 2.
- **Any GPU compute.** The card is enumerated, never exercised.
- **NFS mount behaviour.** `showmount` proves reachability, not a working
  mount.
- Other nodes' SSH host keys (N-1) - not checked, out of scope.

---

## 5. The finding that matters most: node-06's card contradicts every document

`nvidia-smi` reports a **GeForce RTX 5080, 16303 MiB**. The repo says:

| Source | Claim |
|---|---|
| `README.md:24` | "NVIDIA RTX 6000 Blackwell \| 96 GB \| CogVideoX 5B / Wan2.1 (second video node), Remotion renderer, primary FFmpeg compositor, Llama-3.3-70B-FP8 (failover only)" |
| `README.md:37` | "8 \| 24 GB \| 200 GB SSD \| 1 TB NVMe \| RTX 6000 Blackwell 96 GB (#3)" |
| `dev/CLAUDE.md:24` | "Card swapped to RTX 6000 96 GB - now CUDA, not Intel." |
| `IVGS_v5_Master_Sequence_Plan_to_Production.md:25,127,197` | "node-06's card was physically swapped to an RTX 6000 96 GB", making it "a second CUDA video node, primary compositor, and on-demand LLM failover" |

**16 GB against a documented 96 GB - a 6x shortfall.** This is not a
documentation typo; node-06's entire M4 role was assigned *because of* the
96 GB figure:

- **Llama-3.3-70B-FP8 failover** needs roughly 70 GB of weights. It cannot
  load. Not "slower" - it will not fit.
- **CogVideoX 5B / Wan2.1 as a second video node** at 1080p is well beyond
  16 GB for any useful resolution/length.
- **Primary FFmpeg compositor + Remotion** is largely CPU/IO work and would
  still be fine.
- The **`profile-gated stopped fp8-70B failover worker`** in the AD-02 Draft-3
  compose rewrite (`Master_Sequence_Plan:127`) is unbuildable on this card.

Combined with WP-25, the fleet's two documented GPU assignments are both wrong,
and they look transposed:

| Node | Documented | Actual |
|---|---|---|
| node-05 | RTX 5080 16 GB | **RTX PRO 5000 Blackwell 48935 MiB** |
| node-06 | RTX 6000 Blackwell 96 GB | **GeForce RTX 5080 16303 MiB** |

node-05 was documented with a 5080; a 5080 is what is physically in node-06.
The RTX 6000 96 GB described for node-06 is **not present in either VM I have
been given access to**. Whether it exists elsewhere in the fleet, is unassigned
on a host, or was never fitted, I cannot determine from inside these guests -
that needs the Proxmox host.

A secondary point worth stating: node-06's card is **GeForce**-brand, not
professional. No ECC (`[N/A]`), and NVIDIA's GeForce driver licence terms
restrict datacenter deployment. That is an operator/licensing judgement, not a
technical blocker, but it should be a conscious choice.

I have made no repo edits for any of this. Per the operator's standing
instruction, it goes to the fleet-hardware errata package alongside WP-25's
O-1..O-4.

---

## 6. Files touched

**On node-06** (`192.168.1.95`):

| Path | Change | Rollback |
|---|---|---|
| `/etc/hostname` | `node-05` -> `node-06` | `/etc/hostname.bak-wp28` |
| `/etc/hosts` | `127.0.1.1` line -> `node-06` | `/etc/hosts.bak-wp28` |
| `/etc/machine-id` | regenerated | n/a - deliberate |
| `/etc/ssh/ssh_host_{rsa,ecdsa,ed25519}_key{,.pub}` | regenerated | n/a - deliberate |
| `/etc/netplan/50-cloud-init.yaml` | `.94/24` -> `.95/24` | `/etc/netplan/50-cloud-init.yaml.bak-wp28` |

**On node-01:** `/home/dev/.ssh/known_hosts` - `.94` and `.95` entries removed,
`.95` re-added with node-06's real keys. Backup at `known_hosts.old`.

**In the repo:** this report only. Nothing staged, committed or pushed.

**On node-05:** nothing. It was powered off for the entire package.

---

## 7. What remains for M4 on node-06

Nothing below has been done - step 7 was read-only and I am stopping here.

| # | Item | Status |
|---|---|---|
| 1 | Identity de-duplicated (hostname / machine-id / host keys / IP) | **DONE** |
| 2 | Driver >= 570.x, CUDA >= 12.4 | **DONE** - 580.159.03 / CUDA 13.0 |
| 3 | Docker + Compose | **DONE** - 29.5.3 / v5.1.4 |
| 4 | node-exporter running + scrapeable from node-01 | **DONE** - 200 / 75278 B |
| 5 | Container toolkit proven end-to-end (`--gpus all`) | **NOT DONE** - needs approval |
| 6 | `/mnt/ivgs-shared` + `/mnt/models` mounted | **NOT DONE** |
| 7 | Dead `/dev/sdb1` fstab line removed | **NOT DONE** |
| 8 | `/data/{models,comfyui-output,ffmpeg-tmp}` + scratch cap | **NOT DONE** |
| 9 | Reboot-persistence proof of new mounts | **NOT DONE** |
| 10 | node-06 as a Prometheus target (`:9100`, `:9400`) | **NOT DONE** - repo edit, errata package |
| 11 | `.env.node06` on the node | **NOT DONE** - carries a secret, operator |
| 12 | GHCR pull path | **NOT DONE** |
| 13 | node-06's role re-scoped for 16 GB | **NOT DONE** - section 5, blocking |
| 14 | Worker deploy | **OUT OF SCOPE** |

Proposed next pass, on your approval - the WP-25 sequence, unchanged except
sizing: mount both NFS shares (`soft`+`nofail`, as D-2); remove the dead fstab
line; create `/data/*` with a capped `ffmpeg-tmp` volume (**smaller than
node-05's 40 GiB** - node-06's compositor role needs scratch more than weights,
so I would propose a split once you have decided section 5); prove the toolkit
with `docker run --gpus all`; reboot; re-verify. Using `mkfs.ext4 -E nodiscard`
this time - see WP-25 section 11.4.

---

## 8. Decisions requested

| ID | Decision | Why |
|---|---|---|
| **N-1** | **Audit SSH host keys across nodes 02/03/04.** The keys removed here were `root@rtx6000`, dated Mar 1, predating node-05's own build - a golden-image artefact. Siblings from that image are probably presenting identical keys. | Section 3.3. Shared host keys mean trusting one node silently trusts all. S-10 class, fleet-wide. Needs a hand-over; I have touched nothing outside node-06. |
| **N-2** | **Where is the RTX 6000 Blackwell 96 GB, and what is node-06's real role at 16 GB?** | Section 5. Blocks M4 planning for node-06: the 70B failover and second-video-node roles are not achievable on this card. Compositor/Remotion still is. |
| **N-3** | Accept a **GeForce**-brand card in the fleet (no ECC, GeForce driver licence terms)? | Section 2. Operator/licensing call. |
| **N-4** | Approve the next pass (item list in section 7), and set the `/data` split given N-2's answer | Sizing depends on whether node-06 hosts weights at all. |
| **N-5** | Confirm `.94` should stay absent from `known_hosts` | Section 3.5. My recommendation: yes - verify against the fingerprints in section 9 on first connect rather than pre-trusting. |

Carried forward unchanged from WP-25 and applying equally here: **O-3**
(`default-runtime: nvidia`, no VRAM partitioning) and the node-exporter
compose-exclusion note (**D-3**) - node-06's compose must also never be brought
up with a bare `up`, or it will collide on `:9100`.

---

## 9. Before you restart node-05 - please read

**`192.168.1.95` is live and confirmed as node-06.** Verified from node-01:
`getent hosts node-06` -> `192.168.1.95`; SSH strict-mode connect returns
`node-06`; `curl http://192.168.1.95:9100/metrics` -> HTTP 200. `192.168.1.94`
is silent and free. **node-05 is clear to restart.**

Two things to expect when it comes back:

1. **You will get a host-key prompt for `192.168.1.94`.** That is correct and
   expected - I removed the stale entry. node-05 still has its original keys.
   Verify against these before accepting:

       256  SHA256:0uo6ry7LALvKDStzIAihu2YCh6KyCuCS8SrQDSX+xqo  (ECDSA)
       256  SHA256:EMvMt4cKvf8qT0tB4+i24UZVKeENEBmbuqdAZb/C1fA  (ED25519)
       3072 SHA256:lyzPfOY9AlHBVQ5wVWwHcvHnGF0Gi8HWfobG7asT/Qs  (RSA)

   If a connect to `.94` presents `/Rj57Gp/...`, `BiuLtiMzxJ/...` or
   `n/NaPewTr...` instead, **stop** - that is node-06 answering on the wrong
   address, meaning the netplan change did not stick on the right VM.

2. **node-05 and node-06 will briefly share those old host keys** until node-05
   is itself re-keyed - node-05 keeps the `root@rtx6000` set. This is N-1.
   node-06 no longer shares them.

---

## 10. Exit gate

**Steps 0-6: MET.** Identity gate passed on the GPU before any change. Hostname,
machine-id, SSH host keys and static IP all changed and verified after a real
reboot (boot_id changed), with no failed units. node-06 answers at
`192.168.1.95`, `.94` is released, and node-01's `known_hosts` is clean for both
addresses with a strict-mode connect proven.

**Step 7: MET, and STOPPED as instructed.** Survey is read-only and complete;
node-05 leftovers enumerated in 4.2; the significant finding is that this clone
predates WP-25 entirely (4.1), so node-06 needs the full prep sequence rather
than adjustment.

**Not done, deliberately:** the container-toolkit `--gpus all` proof, the NFS
mounts, `/data`, and the fstab cleanup - all of which would have been changes
past the stop point.

**Blocking for M4:** N-2. node-06 is documented as a 96 GB node and is a 16 GB
node; its assigned roles cannot all be met on the hardware present.

---
---

# PASS 2 - fleet key audit and full prep sequence

| | |
|---|---|
| **Pass 2 date** | 2026-08-15 |
| **Operator decisions** | **N-3 ACCEPTED** - GeForce-brand card is fine for node-06's composition role on an internal system. **N-1 authorised** as a read-only `ssh-keyscan` from node-01. **N-4 approved** - full prep sequence, WP-25 shape, closing reboot pre-authorised. |
| **Scope-outs (unchanged)** | No `compose up`, no workers, no repo edits beyond this report. Honoured. |
| **node-05** | Restarted and re-verified by the operator. Read-only checks only from node-01; never logged into. |

## 11. N-3 recorded

The operator accepts a **GeForce**-brand card on node-06 for its composition
role on an internal system. The two technical consequences stand and are
recorded rather than treated as blockers:

- **No ECC.** `ecc.mode.current` = `[N/A]` - the silicon has none, so this is
  not a setting that can be turned on. Uncorrected VRAM errors will be silent.
  For composition/encode work this is a low-consequence risk; it would not be
  for long-running training.
- **GeForce driver licence terms** restrict datacenter deployment. Operator's
  judgement, made knowingly, on an internal system.

## 12. N-1 - fleet SSH host-key audit (read-only, no logins)

Method: `ssh-keyscan -t rsa,ecdsa,ed25519` from node-01 against the four
addresses named (`.91`, `.92`, `.93`, `.96`), plus `.94` and `.95` as controls.
`ssh-keyscan` does not authenticate and does not open a session - nothing was
logged into. 18 keys collected across 6 addresses, fingerprinted and compared
pairwise.

### 12.1 Result: no sharing. My pass-1 concern does not reproduce.

**Every one of the 18 host keys is unique across all six addresses.** No
fingerprint appears on more than one host.

| Address | Node | ED25519 fingerprint | Verdict |
|---|---|---|---|
| 192.168.1.91 | node-02 | `m/KDNTWki9ojxjIR+g6+ejWv1T8+qY+ClJvou8GnMKU` | unique |
| 192.168.1.92 | node-03 | `Ef2RD8iFIl9a6QcjsZZXXKY18D2KC15whxVATuwdDN8` | unique |
| 192.168.1.93 | node-04 | `kNX/ug+E8HyxK+Q3IIv9iKS9qGmNhDWqNd5tJQciKvU` | unique |
| 192.168.1.96 | node-07 | `zBVXnTf1vVIbOdrc0+Po2rMCatix2N6h8tR8NfVKDZg` | unique |
| 192.168.1.94 | node-05 | `EMvMt4cKvf8qT0tB4+i24UZVKeENEBmbuqdAZb/C1fA` | **the old golden-image key** |
| 192.168.1.95 | node-06 | `BiuLtiMzxJ/9sEVSsoEQtqGlquDeN4B4X4TkmBw4r/A` | re-keyed this package |

The three `root@rtx6000` golden-image keys appear on **`192.168.1.94` only**:

    0uo6ry7LALvKDStzIAihu2YCh6KyCuCS8SrQDSX+xqo (ECDSA)  -> 192.168.1.94 only
    EMvMt4cKvf8qT0tB4+i24UZVKeENEBmbuqdAZb/C1fA (ED25519) -> 192.168.1.94 only
    lyzPfOY9AlHBVQ5wVWwHcvHnGF0Gi8HWfobG7asT/Qs (RSA)     -> 192.168.1.94 only

**Correcting my pass 1.** Section 3.3 said siblings from that image were "very
likely" presenting identical keys. They are not. The duplication was confined
to node-05 and the clone taken from it, and regenerating the clone's keys
resolved it. **No fleet-wide remediation is needed.** Nodes 02/03/04/07 were
each keyed independently at build.

Two incidental confirmations: `.94` returning exactly the three fingerprints
predicted in section 9 confirms node-05 restarted correctly as itself; `.95`
returning the new set confirms node-06 is the re-keyed machine. The two are now
unambiguously distinguishable over SSH.

### 12.2 Residual, for the record

node-05 still carries host keys generated for a machine called `rtx6000` in
March, ahead of its own June build. Nothing is broken and nothing is shared, so
this is cosmetic/provenance rather than a security defect. Re-keying node-05 is
a separate decision and was not taken.

## 13. Pass 2 - the full prep sequence

Same shape as WP-25, same decisions (D-2 `soft`+`nofail`, D-3 host exporter),
sized for node-06's role. `/etc/fstab` backed up to
`/etc/fstab.bak-wp28-20260815` before edit.

### 13.1 Container toolkit proven end-to-end

    docker run --rm --gpus all nvidia/cuda:12.8.0-base-ubuntu24.04 nvidia-smi
    -> rc=0; "NVIDIA GeForce RTX 5080", 2MiB / 16303MiB, Driver 580.159.03, CUDA 13.0

    ... ls /dev/nvidia*  -> nvidia-modeset, nvidia-uvm, nvidia-uvm-tools, nvidia0, nvidiactl
    ... nvidia-smi --query-gpu=name,memory.total -> "NVIDIA GeForce RTX 5080, 16303 MiB"

A CUDA 12.8 image again ran correctly against the CUDA 13.0 driver, so existing
worker images need no rebuild for this card either.

**O-3 confirmed present on node-06.** A run *without* `--gpus all` also saw the
GPU (`NVIDIA GeForce RTX 5080`), same `default-runtime: nvidia` +
`NVIDIA_VISIBLE_DEVICES=all` combination as node-05. Left as found.

### 13.2 NFS mounts (D-2 `soft`+`nofail`) and dead fstab line removed

Created `/mnt/ivgs-shared`; removed `/dev/sdb1 -> /opt/factory` (leftover #5
from 4.2); added the two NFS lines identical to node-05's.

| Gate | Result |
|---|---|
| `/mnt/ivgs-shared` | MOUNTED - `192.168.1.90:/mnt/ivgs-shared nfs4` |
| `/mnt/models` | MOUNTED - `192.168.1.90:/mnt/models nfs4` |
| Negotiated options | `nfs4 (rw,...,vers=4.2,soft,proto=tcp,timeo=100,retrans=3,...,_netdev)` - `soft` honoured |
| **Identity check inside the mount** | `clientaddr=192.168.1.95` - proves node-06 is the client, not node-05 |
| **Cross-node write probe** | node-06 wrote `1786795902501055672`; **node-01 read the identical value**; probe deleted |

### 13.3 `/data` provisioned, scratch cap sized for a compositor

Created `/data/models`, `/data/models/ollama`, `/data/comfyui-output`,
`/data/remotion`, `/data/ffmpeg-tmp`.

**Scratch cap: 80 GiB - double node-05's 40 GiB.** Reasoning, since I was asked
to propose it: node-06's viable role on a 16 GB card is compositor + Remotion
(section 5), which is scratch-hungry and weights-light - the inverse of
node-05. Intermediate 1080p segments, frame sequences and Remotion renders are
the bulk consumer; model weights largely cannot live here anyway. 80 GiB of the
148 GiB free goes to scratch, leaving **68 GiB** for `/data/models`,
`/data/comfyui-output` and `/data/remotion`. Resizable at any time (unmount,
`fallocate` larger, `resize2fs`). If N-2 resolves toward node-06 hosting real
weights after all, this split should be revisited.

**WP-25's mkfs lesson applied.** Used `mkfs.ext4 -q -m 0 -E nodiscard`. The
image measured **80G apparent / 81G actual immediately** after mkfs - no
hole-punching, no second `fallocate` pass needed. The defect from WP-25 section
11.4 did not recur.

**Cap proof:**

| Test | Result |
|---|---|
| `fallocate -l 85G` inside the volume | **fails** - `No space left on device` |
| `fallocate -l 70G` | succeeds, rc=0 |
| Root while scratch 90% full | `194G / 117G used / 68G avail` - **unchanged** |
| At rest | `/dev/loop0 ext4 79G 24K 79G 1% /data/ffmpeg-tmp` |

### 13.4 node-exporter policy (D-3) - checked, unchanged

Survey found the host binary already present. Confirmed still v1.8.2, `active`,
`enabled`, unit `/etc/systemd/system/node_exporter.service` binding `:9100`.
**Nothing installed, nothing changed** - same policy as node-05.

> **M4 deploy note for node-06.** `docker-compose.node06.yml:142-151` defines a
> `node-exporter` service (`prom/node-exporter:v1.8.1`) on `0.0.0.0:9100`. It
> **must not** be brought up - the host binary owns that port. Name services
> explicitly on the compose invocation; never a bare `up`. Identical constraint
> to node-05.

### 13.5 Closing reboot (pre-authorised) - everything returned unaided

boot_id `c8562193-1195-4b7d-9659-238b8fc24ae5` ->
`961e979f-5fba-487e-8bf6-c69fc2104d7f`. Back on the 2nd retry.

| Check | Result |
|---|---|
| Identity held | `hostname` = `node-06`, `192.168.1.95/24` |
| `/mnt/ivgs-shared` | MOUNTED - nfs4 |
| `/mnt/models` | MOUNTED - nfs4 |
| `/data/ffmpeg-tmp` | MOUNTED - `/dev/loop0` ext4 |
| systemd mount units | `mnt-ivgs\x2dshared.mount`, `mnt-models.mount`, `data-ffmpeg\x2dtmp.mount` - all `loaded active mounted` |
| `systemctl --failed` | **empty** |
| `node_exporter` | `active` / `enabled` |
| `docker` | `activating` when first polled, **`active`** once settled |
| GPU | `NVIDIA GeForce RTX 5080, 16303 MiB, 580.159.03` |
| **Toolkit after reboot** | `--gpus all` -> `NVIDIA GeForce RTX 5080, 16303 MiB` |
| **Cap after reboot** | `fallocate -l 85G` -> `No space left on device` |
| **Cross-node probe** | node-06 wrote `1786795950246738755`; **node-01 read the identical value**; deleted |
| **Scrape from node-01** | `curl http://node-06:9100/metrics` -> **HTTP 200, 84347 bytes** |
| Containers left behind | `docker ps -aq` -> **0** |
| **node-05 unaffected** | `curl http://192.168.1.94:9100/metrics` -> HTTP 200 |

## 14. Verification - observed vs not

**Observed live:** the full key audit (12); toolkit end-to-end before and after
reboot (13.1, 13.5); both NFS mounts with `soft` honoured, `clientaddr=.95`,
and cross-node write probes read back byte-identical on node-01 on both sides
of the reboot (13.2, 13.5); `-E nodiscard` producing a genuinely allocated
image on the first attempt (13.3); the cap rejecting 85 GiB and accepting
70 GiB with root free space unmoved (13.3); all three mounts returning as clean
systemd mount units with no failed units (13.5); node-05 still serving on `.94`.

**NOT verified:**
- **Any GPU compute.** The card is enumerated and reachable from a container;
  no CUDA kernel, model load or encode was run. Whether 16 GB suffices for the
  real composition workload is untested - and is the substance of N-2.
- **NFS behaviour during a node-01 outage.** `soft` chosen; not simulated.
- **80 GiB being the right cap.** A judgement call (13.3), not measured against
  a real composition job.
- **`ivgs-workers` image pull** - no GHCR credentials.
- **Nothing about compose or workers** - scope-out honoured.

## 15. Files touched (pass 2)

**On node-06** (`192.168.1.95`):

| Path | Change | Rollback |
|---|---|---|
| `/etc/fstab` | 2 NFS lines + 1 loop line added; dead `/dev/sdb1` line removed | `/etc/fstab.bak-wp28-20260815` |
| `/etc/fstab.bak-wp28-20260815` | created | - |
| `/mnt/ivgs-shared` | created, now an NFS mountpoint | `umount`, `rmdir` |
| `/mnt/models` | pre-existing empty dir, now an NFS mountpoint | `umount` |
| `/data/{models,models/ollama,comfyui-output,remotion,ffmpeg-tmp}` | created | `rm -rf /data` |
| `/data/ffmpeg-tmp.img` | 80 GiB ext4 image created | `umount`, `rm` |

**On node-01:** nothing written. `ssh-keyscan` output and comparison files were
written to the session scratchpad, outside the repo.

**On node-05:** nothing. Two read-only HTTP scrapes of `:9100` and one
`ssh-keyscan`; never logged into.

**In the repo:** this report only. Nothing staged, committed, pushed or
deployed. No container persists.

## 16. M4 readiness - node-06 final

| # | Item | Status |
|---|---|---|
| 1 | Identity de-duplicated | **DONE** (pass 1) |
| 2 | Driver >= 570.x / CUDA >= 12.4 | **DONE** - 580.159.03 / 13.0 |
| 3 | Docker + Compose | **DONE** - 29.5.3 / v5.1.4 |
| 4 | node-exporter running + scrapeable | **DONE** - 200 / 84347 B |
| 5 | Toolkit proven `--gpus all` | **DONE** - before and after reboot |
| 6 | Both NFS shares mounted | **DONE** - cross-node probes |
| 7 | Dead `/dev/sdb1` fstab line removed | **DONE** |
| 8 | `/data` + enforced scratch cap | **DONE** - 80 GiB, proven |
| 9 | Reboot persistence | **DONE** - clean mount units, no failures |
| 10 | Fleet SSH key audit (N-1) | **DONE** - no sharing found |
| 11 | GeForce card accepted (N-3) | **DONE** - recorded, 11 |
| 12 | Prometheus targets `:9100`/`:9400` | **NOT DONE** - repo edit, errata package |
| 13 | `.env.node06` on the node | **NOT DONE** - carries a secret, operator |
| 14 | GHCR pull path | **NOT DONE** - M4 deploy |
| 15 | **node-06's role re-scoped for 16 GB** | **NOT DONE - N-2, blocking** |
| 16 | Worker deploy | **OUT OF SCOPE** |

## 17. Package verdict - CLOSED

node-06 is prepared to the same standard as node-05, and the clone's identity
collision is fully resolved. Confirmed by observation:

- Distinct hostname, machine-id, SSH host keys and IP; `.95` live, `.94`
  correctly back to node-05.
- **N-1 answered: no SSH host-key sharing anywhere in the fleet.** The
  duplication was confined to node-05 and its clone and is resolved. My pass-1
  speculation that siblings were affected was wrong.
- **N-3 recorded**: GeForce card accepted for the composition role; no ECC and
  the licence terms noted.
- GPU: **`NVIDIA GeForce RTX 5080`, 16303 MiB, driver 580.159.03, CUDA 13.0,
  compute 12.0, ECC `[N/A]`** - recorded verbatim.
- Container toolkit functional end-to-end, before and after a reboot.
- Both NFS shares mounted `soft`+`nofail`, proven by cross-node write probes.
- 80 GiB compositor-sized scratch cap, proven to reject an over-size allocation
  while leaving root untouched; `-E nodiscard` avoided WP-25's sparse-image
  defect.
- All three mounts survive a reboot as clean systemd mount units.

**Handed forward, unresolved by design:**

- **N-2 remains blocking for M4 planning** - node-06 is documented at 96 GB and
  is a 16 GB node. The 70B failover and second-video-node roles are not
  achievable on this card; compositor + Remotion are. To the fleet-hardware
  errata package with WP-25's O-1..O-4 and the README/Prometheus corrections.
- **O-3** applies to node-06 exactly as to node-05.
- **D-3 compose-exclusion note** applies to node-06's compose invocation.
- `.env.node06` and the GHCR pull path remain M4-deploy operator actions.
- node-05's own host keys still carry the `rtx6000` provenance (12.2) - a
  separate decision, not taken.
- No GPU compute was exercised on either node.
