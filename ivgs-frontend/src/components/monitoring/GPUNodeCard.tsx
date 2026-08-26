"use client";

import React, { useCallback, useMemo } from "react";
import LoadingSpinner from "@/components/LoadingSpinner";
import type { GPUNode } from "@/types/monitoring";

/**
 * GPU Fleet Status - Per-GPU Node Card (spec section 8.2.2)
 *
 * Displays GPU metrics for a single node:
 * - GPU model name and compute capability
 * - VRAM usage: total/used (progress bar, color-coded by utilization)
 *   - Green: <70%, Amber: 70-90%, Red: >90%
 * - Temperature gauge per spec section 8.1.5:
 *   - Green: <70 C, Amber: 70-85 C, Red: >85 C
 * - GPU utilization percentage with visual indicator
 * - Power draw vs TDP (when TDP known)
 * - Active job: job ID, project name, pipeline stage
 * - Node status badge: online / offline / draining
 * - Drain toggle button (admin only per spec 5.2.1)
 *
 * Field naming matches backend GpuNodeResponse exactly per
 * IVGS v5 Functional Specification Appendix C.4 and GPU Fleet Monitoring
 * Spec v1.1 section 6.0 (defect #6/#7 resolution).
 *
 * CPU, RAM, and queue-depth metrics are not surfaced because the backend
 * does not collect them per spec 4.2 Table 19.
 *
 * active_job fields not on backend ActiveJobSummary (model_name, progress)
 * are not surfaced. Per-job progress lives on RenderJob, not on the GPU
 * snapshot - separate change request to add to ActiveJobSummary if needed.
 *
 * Data sourced from:
 * - GET /api/v1/gpu/nodes (snapshot, this card)
 * - GET /api/v1/gpu/utilization/history (time-series, sibling chart)
 */

interface GPUNodeCardProps {
  /** GPU node data from the fleet status API */
  node: GPUNode;
  /** Human-readable GPU label (e.g., "NVIDIA RTX 5000 Pro Blackwell (48 GB)") */
  gpuLabel: string;
  /** Whether the current user is admin (for drain toggle) */
  isAdmin: boolean;
  /** Whether a drain toggle is in progress for this node */
  isDraining: boolean;
  /**
   * Callback to toggle drain mode on this node.
   * Receives node.id (UUID) - backend drain endpoint takes UUID.
   */
  onDrainToggle: (nodeId: string) => void;
}

/**
 * Temperature color thresholds per spec section 8.1.5:
 * green <70 C, amber 70-85 C, red >85 C
 */
const getTemperatureColor = (tempC: number): string => {
  if (tempC >= 85) return "text-red-600";
  if (tempC >= 70) return "text-amber-500";
  return "text-green-600";
};

const getTemperatureBarColor = (tempC: number): string => {
  if (tempC >= 85) return "bg-red-500";
  if (tempC >= 70) return "bg-amber-500";
  return "bg-green-500";
};

/**
 * VRAM utilization color thresholds:
 * Green <70%, Amber 70-90%, Red >90% (per Table 13-3 GPUVRAMHigh)
 */
const getVRAMColor = (percent: number): string => {
  if (percent >= 90) return "bg-red-500";
  if (percent >= 70) return "bg-amber-500";
  return "bg-blue-500";
};

/**
 * Node status badge colors. Keys are lowercase per backend convention.
 */
const STATUS_BADGE_STYLES: Record<string, string> = {
  online: "bg-green-100 text-green-800",
  offline: "bg-red-100 text-red-800",
  draining: "bg-amber-100 text-amber-800",
};

export default function GPUNodeCard({
  node,
  gpuLabel,
  isAdmin,
  isDraining,
  onDrainToggle,
}: GPUNodeCardProps): React.ReactElement {
  // ── Computed Metrics ────────────────────────────────────────────────

  /** VRAM utilization percentage (null-safe for unknown total) */
  const vramPercent = useMemo((): number => {
    if (!node.total_vram_mb || node.total_vram_mb === 0) return 0;
    return Math.round((node.used_vram_mb / node.total_vram_mb) * 100);
  }, [node.total_vram_mb, node.used_vram_mb]);

  /**
   * WP-62 Task 1. Physical VRAM as a percentage of the card, for the bar.
   * Separate from `vramPercent`, which is the scheduler's reservation as a
   * percentage of the same card. Two ratios of two different numerators over
   * one denominator; collapsing them is the defect this card has carried.
   */
  const devicePercent = useMemo((): number => {
    if (!node.total_vram_mb || node.total_vram_mb === 0) return 0;
    if (typeof node.device_used_vram_mb !== "number") return 0;
    return Math.round((node.device_used_vram_mb / node.total_vram_mb) * 100);
  }, [node.total_vram_mb, node.device_used_vram_mb]);

  /** Power draw percentage vs TDP. 0 when either side is unknown; the caller
   *  only renders it when `power_draw_w` is a real reading (WP-60 Task 2a). */
  const powerPercent = useMemo((): number => {
    if (!node.power_tdp_w || node.power_tdp_w === 0) return 0;
    if (typeof node.power_draw_w !== "number") return 0;
    return Math.round((node.power_draw_w / node.power_tdp_w) * 100);
  }, [node.power_draw_w, node.power_tdp_w]);

  const statusLabel =
    node.status.charAt(0).toUpperCase() + node.status.slice(1);

  /**
   * WP-61 Task 8. The three device readings below are Prometheus telemetry,
   * and this card now says so rather than implying the scheduler measured them.
   *
   * The three tooltips it replaces each said a version of "the scheduler
   * registry holds no reading; its heartbeats carry one only when nvidia-smi
   * succeeds on the node". That was accurate about the mechanism and useless
   * as guidance, because nvidia-smi can NEVER succeed there — the workers
   * image does not contain it (proven 2026-08-26). A reader was being sent to
   * check a condition that is structurally unreachable.
   *
   * The reason now comes from the API (`telemetry_reason`), which derives it
   * per node from what is actually true of that node — no GPU at all, node
   * offline, or reachable-but-not-scraped. One source, one wording, no
   * hardcoded explanation to go stale on this page.
   */
  const telemetryTitle =
    node.telemetry_reason ??
    "No device telemetry for this node, and the API gave no reason.";

  /** First active job (UI displays one at a time per spec section 8.2.2) */
  const activeJob =
    node.active_jobs && node.active_jobs.length > 0
      ? node.active_jobs[0]
      : null;

  /**
   * Format VRAM values to GB with one decimal place.
   */
  const formatVRAM = useCallback((mb: number): string => {
    return `${(mb / 1024).toFixed(1)} GB`;
  }, []);

  // ── Render ──────────────────────────────────────────────────────────

  return (
    <div
      className={`bg-white dark:bg-gray-900 rounded-lg border overflow-hidden transition-shadow
        hover:shadow-md ${
          node.status === "offline"
            ? "border-red-200 dark:border-red-800 opacity-75"
            : node.status === "draining"
            ? "border-amber-200 dark:border-amber-800"
            : "border-gray-200 dark:border-gray-800"
        }`}
    >
      {/* ── Card Header ──────────────────────────────────────────── */}
      <div className="px-4 py-3 bg-gray-50 dark:bg-gray-950 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          {/* Status dot */}
          <div
            className={`h-2.5 w-2.5 rounded-full ${
              node.status === "online"
                ? "bg-green-500"
                : node.status === "draining"
                ? "bg-amber-500 animate-pulse"
                : "bg-red-500"
            }`}
          />
          <div>
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              {node.node_hostname}
            </h3>
            <p className="text-xs text-gray-500 dark:text-gray-400">{gpuLabel}</p>
            {/* WP-62 Task 1. WHAT THIS NODE IS FOR. A non-scheduler GPU node
                has no active jobs and no reservation, so without its role the
                card is four readings and a blank space that reads as idle.
                node-05 is not idle; it is holding 27B of FP8 weights. */}
            {node.role && (
              <p className="mt-0.5 text-[10px] leading-tight text-gray-500 dark:text-gray-400">
                {node.role}
              </p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* Status badge */}
          <span
            className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs
              font-medium ${
                STATUS_BADGE_STYLES[node.status] || "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400"
              }`}
          >
            {statusLabel}
          </span>
          {/* WP-62 Task 1. NOT A SCHEDULER WORKER, said on the card.
              node-05 and node-06 each carry a GPU and run no Celery worker, so
              the scheduler places nothing on them and they hold no reservation.
              Saying so is what stops "0.0 GB reserved / no active jobs" being
              read as a node sitting doing nothing. */}
          {!node.in_scheduler && (
            <span
              className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700 dark:bg-slate-800 dark:text-slate-300"
              title="This machine carries a GPU and is not in the scheduler's fleet: it runs no Celery worker, so the scheduler places no pipeline work on it and holds no VRAM reservation for it. Its readings below are device telemetry from Prometheus, the same source every other card here uses."
            >
              Not a scheduler worker
            </span>
          )}
          {/* Drain toggle - admin only, and only where draining means anything.
              WP-62 Task 1: `supports_drain` is false for a GPU node the
              scheduler does not schedule to. Drawing the button there would be
              a control with nothing behind it - an operator would believe they
              had stopped work reaching a node that never received any. The
              server refuses it too (409 DRAIN_NOT_APPLICABLE); this is so the
              action is never offered. */}
          {isAdmin && node.supports_drain && (node.total_vram_mb ?? 0) > 0 && (
            <button
              type="button"
              onClick={() => onDrainToggle(node.id)}
              disabled={isDraining}
              className={`px-2 py-1 text-xs font-medium rounded transition-colors
                ${
                  node.status === "draining"
                    ? "bg-green-50 dark:bg-green-900/40 text-green-700 dark:text-green-300 border border-green-200 dark:border-green-800 hover:bg-green-100 dark:hover:bg-green-900/50"
                    : "bg-amber-50 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800 hover:bg-amber-100 dark:hover:bg-amber-900/50"
                }
                disabled:opacity-50 disabled:cursor-not-allowed`}
              title={
                node.status === "draining"
                  ? "Click to undrain (resume scheduling)"
                  : "Click to drain (stop scheduling new jobs)"
              }
            >
              {isDraining ? (
                <LoadingSpinner size="sm" />
              ) : node.status === "draining" ? (
                "Undrain"
              ) : (
                "Drain"
              )}
            </button>
          )}
        </div>
      </div>

      {/* ── Card Body ────────────────────────────────────────────── */}
      <div className="p-4 space-y-3">
        {/* ── Physical VRAM, from the device ───────────────────────
            WP-62 Task 1, RULED. THE CARD LEADS WITH WHAT THE GPU HOLDS.

            Until this package the only VRAM figure on this card was the
            scheduler's reservation, and the operator's complaint about it was
            the same complaint three times: the page called itself GPU Fleet
            Status and showed a number no GPU had produced. WP-60 correctly
            RELABELLED it; the number still was not a device reading, because
            the source could not produce one.

            The device figure comes from `nvidia_smi_memory_used_bytes` in
            Prometheus — the identical series Node Monitor reads, which is why
            the two pages now agree instead of showing 0.0 GB and 86.4 GB for
            the same card at the same moment.

            THE COLOUR RULE IS NOT THE SCHEDULER'S. A worker at 90% VRAM is
            near its admission ceiling and amber/red says something useful. An
            LLM node at 90% is a model resident in memory doing exactly what it
            was started to do: node-05 idles at 42.7 GB of 47.8 because vLLM
            pre-allocates its KV cache at `--gpu-memory-utilization 0.90`.
            Painting that red would train the operator to ignore the colour. A
            non-scheduler node's physical VRAM is drawn neutral and captioned
            as a steady state. */}
        {(node.total_vram_mb ?? 0) > 0 && (
          <div>
            <div className="flex items-center justify-between mb-1">
              <span
                className="text-xs font-medium text-gray-600 dark:text-gray-400"
                title="Physical VRAM in use on the card, read from nvidia-gpu-exporter via Prometheus - the same series Node Monitor reads. This is the device, not an allocation the scheduler is tracking."
              >
                VRAM on the device
              </span>
              {typeof node.device_used_vram_mb === "number" ? (
                <span className="text-xs text-gray-500 dark:text-gray-400">
                  {formatVRAM(node.device_used_vram_mb)} /{" "}
                  {formatVRAM(node.total_vram_mb!)}
                </span>
              ) : (
                <span
                  className="text-xs text-gray-400 dark:text-gray-500"
                  title={telemetryTitle}
                >
                  not reported
                </span>
              )}
            </div>
            {typeof node.device_used_vram_mb === "number" && (
              <>
                <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                  <div
                    className={`h-2 rounded-full transition-all duration-300 ${
                      node.in_scheduler
                        ? getVRAMColor(devicePercent)
                        : "bg-slate-400 dark:bg-slate-500"
                    }`}
                    style={{ width: `${Math.min(devicePercent, 100)}%` }}
                  />
                </div>
                <p className="mt-0.5 text-right text-xs text-gray-500 dark:text-gray-400">
                  {devicePercent}%
                  {!node.in_scheduler && devicePercent >= 70 && (
                    <span
                      className="ml-1 text-gray-400 dark:text-gray-500"
                      title="A model server holds its weights and its KV cache resident for as long as it is serving. High VRAM here is the steady state, not pressure."
                    >
                      — resident model, steady state
                    </span>
                  )}
                </p>
              </>
            )}
          </div>
        )}

        {/* ── Scheduler reservation — scheduler workers only ────────
            WP-60 Task 2(b). THE LABEL SAID "VRAM". THE NUMBER IS A
            RESERVATION. `used_vram_mb` is seeded to 0 at registration and
            moved only by the scheduler's own acquire/release; nothing has ever
            read it off the card.

            WP-62 Task 1: it is now shown ONLY for nodes the scheduler places
            work on. A "0.0 GB reserved" row on node-05 would be true and
            meaningless — there is no reservation because there is no
            scheduling, not because the node is free. */}
        {node.in_scheduler && (node.total_vram_mb ?? 0) > 0 && (
          <div>
            <div className="flex items-center justify-between mb-1">
              <span
                className="text-xs font-medium text-gray-600 dark:text-gray-400"
                title="VRAM the scheduler has reserved for admitted jobs. Its own accounting, and legitimately a different number from the device reading above - measured 2026-08-26, node-02 held 88494 MiB on the card with 0 MB reserved."
              >
                VRAM reserved by scheduler
              </span>
              <span className="text-xs text-gray-500 dark:text-gray-400">
                {formatVRAM(node.reserved_vram_mb ?? node.used_vram_mb)} /{" "}
                {formatVRAM(node.total_vram_mb!)}
              </span>
            </div>
            <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
              <div
                className={`h-2 rounded-full transition-all duration-300 ${getVRAMColor(
                  vramPercent
                )}`}
                style={{ width: `${Math.min(vramPercent, 100)}%` }}
              />
            </div>
            <p className="mt-0.5 text-right text-xs text-gray-500 dark:text-gray-400">
              {vramPercent}%
            </p>
          </div>
        )}

        {/* GPU Utilization */}
        {(node.total_vram_mb ?? 0) > 0 && (
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-gray-600 dark:text-gray-400">
              GPU Utilization
            </span>
            {/* WP-60 Task 2(a): null is "nothing measured", which is not 0%.
                A bar drawn at zero asserts an idle GPU.
                WP-61 Task 8: the reading itself now comes from Prometheus, and
                this field was never populated on this route at all -- the fleet
                response constructor simply omitted `gpu_utilization_pct`, so
                the schema default supplied null and the card has said "not
                reported" since WP-60 regardless of what the registry held. */}
            {typeof node.gpu_utilization_pct === "number" ? (
              <div className="flex items-center gap-2">
                <div className="w-20 bg-gray-200 dark:bg-gray-700 rounded-full h-1.5">
                  <div
                    className="bg-blue-500 h-1.5 rounded-full transition-all duration-300"
                    style={{
                      width: `${Math.min(node.gpu_utilization_pct, 100)}%`,
                    }}
                  />
                </div>
                <span className="text-xs font-mono text-gray-700 dark:text-gray-300 w-10 text-right">
                  {node.gpu_utilization_pct.toFixed(0)}%
                </span>
              </div>
            ) : (
              <span
                className="text-xs text-gray-400 dark:text-gray-500"
                title={telemetryTitle}
              >
                not reported
              </span>
            )}
          </div>
        )}

        {/* Temperature */}
        {(node.total_vram_mb ?? 0) > 0 && (
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-gray-600 dark:text-gray-400">
              Temperature
            </span>
            {/* WP-60 Task 2(a). "0 C" WAS NOT A COLD GPU, IT WAS A DEFAULT.
                WP-61 Task 8 supplies the reading the registry could never
                carry: the heartbeat sender reads temperature by shelling out
                to `nvidia-smi` inside the worker container, and the workers
                image has no such binary. WP-60's closing line here -- "until a
                heartbeat from a rebuilt worker lands" -- described a wait that
                would never end. The number comes from Prometheus now. */}
            {typeof node.temperature_c === "number" ? (
              <div className="flex items-center gap-2">
                <div className="w-20 bg-gray-200 dark:bg-gray-700 rounded-full h-1.5">
                  <div
                    className={`h-1.5 rounded-full transition-all duration-300 ${getTemperatureBarColor(
                      node.temperature_c
                    )}`}
                    style={{
                      width: `${Math.min(node.temperature_c, 100)}%`,
                    }}
                  />
                </div>
                <span
                  className={`text-xs font-mono w-12 text-right font-medium ${getTemperatureColor(
                    node.temperature_c
                  )}`}
                >
                  {node.temperature_c.toFixed(0)} C
                </span>
              </div>
            ) : (
              <span
                className="text-xs text-gray-400 dark:text-gray-500"
                title={telemetryTitle}
              >
                not reported
              </span>
            )}
          </div>
        )}

        {/* Power Draw - shows draw alone if TDP not known */}
        {(node.total_vram_mb ?? 0) > 0 && (
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-gray-600 dark:text-gray-400">Power</span>
            {/* WP-60 Task 2(a): same family as temperature -- the schema
                default supplied "0 W" for a figure nothing measured. WP-61
                Task 8: same source as temperature now,
                `nvidia_smi_power_draw_watts` from Prometheus. */}
            {typeof node.power_draw_w === "number" ? (
              <span className="text-xs text-gray-500 dark:text-gray-400">
                {node.power_tdp_w
                  ? `${node.power_draw_w.toFixed(0)}W / ${node.power_tdp_w}W TDP (${powerPercent}%)`
                  : `${node.power_draw_w.toFixed(0)}W`}
              </span>
            ) : (
              <span
                className="text-xs text-gray-400 dark:text-gray-500"
                title={telemetryTitle}
              >
                not reported
              </span>
            )}
          </div>
        )}

        {/* WP-61 Task 8. WHICH SOURCE these three readings came from, printed
            once rather than implied three times. The card carries two kinds of
            number and they are not interchangeable: VRAM above is the
            SCHEDULER'S RESERVATION ACCOUNTING (WP-60 Task 2b) and the three
            readings above are the DEVICE, read from Prometheus. Node-02 showed
            "0.0 GB / 95.6 GB" here while Node Monitor showed 86.4 GB on the
            same machine at the same moment, and neither surface was lying —
            neither said what it was counting. */}
        {(node.total_vram_mb ?? 0) > 0 && (
          <p className="pt-1 text-[10px] leading-tight text-gray-400 dark:text-gray-500">
            {node.telemetry_source
              ? `Device VRAM, utilisation, temperature and power: ${node.telemetry_source}.`
              : "No device telemetry for this node."}
            {node.in_scheduler
              ? " The reservation figure is the scheduler's own accounting and is a different number."
              : " This node is not in the scheduler's fleet, so it holds no reservation."}
          </p>
        )}

        {/* WP-62 Task 1. A non-scheduler GPU node has no active jobs to show
            and never will. Saying that is not the same as showing nothing:
            an empty Active Job section on a card beside three that have one
            reads as "this node is free". */}
        {!node.in_scheduler && (
          <div className="pt-2 border-t border-gray-100 dark:border-gray-800">
            <p className="text-[10px] leading-tight text-gray-500 dark:text-gray-400">
              No pipeline jobs are placed here. This machine serves its model
              directly and takes no work from the GPU scheduler.
            </p>
          </div>
        )}

        {/* Active Job */}
        {activeJob && (
          <div className="pt-2 border-t border-gray-100 dark:border-gray-800">
            <p className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
              Active Job
            </p>
            <div className="bg-gray-50 dark:bg-gray-950 rounded p-2">
              <p className="text-xs text-gray-900 dark:text-gray-100 font-mono">
                {activeJob.job_id.slice(0, 12)}…
              </p>
              <p className="text-[10px] text-gray-500 dark:text-gray-400 mt-0.5">
                {activeJob.project_name ?? "—"}
                {activeJob.stage && ` • ${activeJob.stage}`}
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
