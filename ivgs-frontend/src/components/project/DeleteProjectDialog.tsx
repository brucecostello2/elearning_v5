"use client";

import React, { useCallback, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import {
  useProjectDeletion,
  type DeletionCategory,
  type DeletionResult,
} from "@/hooks/useProjectDeletion";
import { formatBytes } from "@/lib/media";

/**
 * Delete a project — WP-59, the operator's UX specification, implemented as
 * written.
 *
 * THE FRICTION IS THE FEATURE. This dialog is deliberately slow to get through
 * and every step of the slowness has a job:
 *
 *   Stage 1  Every category of material the deletion will destroy, with its
 *            real count for THIS project, read from the server. Nothing is
 *            pre-selected. The reader has to go through the list one item at a
 *            time, which is the only way they will notice the one they wanted
 *            to keep.
 *   Stage 2  Unreachable until every category is ticked. It restates the name
 *            and the totals, says plainly that this is permanent and not
 *            undoable from the GUI, and requires the project's exact name to
 *            be typed before the Delete action is enabled.
 *
 * The point is stated to the reader in stage 1, not just implied by the
 * mechanism: a user who sees something they want to keep should STOP, leave,
 * save it, and come back. The dialog says that in those words.
 *
 * IT MAKES NO BACKUP PROMISE (Task 5). A deleted project does remain inside
 * existing snapshots for as long as their retention rules keep them -- but
 * extracting ONE project from a whole-volume asset snapshot or a whole-cluster
 * dump is not a supported operation on this system today. Saying "it's in the
 * backups" would be a promise nobody can keep at the moment it is needed, so
 * this dialog does not say it. What recovery would actually involve is written
 * down in the WP-59 report, where it belongs.
 *
 * GUI ONLY (Task 5.5). No step of this flow asks the operator to run anything
 * in a terminal.
 */

interface DeleteProjectDialogProps {
  projectId: string;
  projectName: string;
  /** Admin only. The caller must not mount this for anyone else. */
  canDelete: boolean;
}

type Stage = "closed" | "categories" | "confirm" | "done";

export default function DeleteProjectDialog({
  projectId,
  projectName,
  canDelete,
}: DeleteProjectDialogProps): React.ReactElement | null {
  const router = useRouter();
  const [stage, setStage] = useState<Stage>("closed");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [typedName, setTypedName] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DeletionResult | null>(null);
  const [cancellingId, setCancellingId] = useState<string | null>(null);

  const open = stage !== "closed";
  const { preview, isLoading, error: previewError, cancelJob } =
    useProjectDeletion(projectId, open);
  const { deleteProject } = useProjectDeletion(projectId, false);

  const categories: DeletionCategory[] = useMemo(
    () => preview?.categories ?? [],
    [preview],
  );

  /* EVERY category must be selected, including the empty ones. A category
     showing 0 is still a category the reader is being asked to look at and
     accept -- skipping the zeroes would let the flow be completed without
     reading, which is the one thing this dialog exists to prevent. */
  const allSelected =
    categories.length > 0 && categories.every((c) => selected.has(c.key));

  const blocked =
    !!preview && (preview.blocking_jobs.length > 0 || !preview.deletable);

  const close = useCallback(() => {
    setStage("closed");
    setSelected(new Set());
    setTypedName("");
    setError(null);
    setResult(null);
  }, []);

  const toggle = useCallback((key: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const onCancelJob = useCallback(
    async (jobId: string) => {
      setCancellingId(jobId);
      setError(null);
      try {
        await cancelJob(jobId);
      } catch (err: unknown) {
        /* api-client already flattened the server's envelope into
           `Error.message` (lib/errors.ts). Rendering it verbatim is the WP-43
           rule: the server's sentence is more useful than anything written
           here. */
        setError(
          err instanceof Error && err.message
            ? err.message
            : "The cancel request was refused and the server gave no reason.",
        );
      } finally {
        setCancellingId(null);
      }
    },
    [cancelJob],
  );

  const onDelete = useCallback(async () => {
    setIsSubmitting(true);
    setError(null);
    try {
      const outcome = await deleteProject(typedName);
      setResult(outcome);
      setStage("done");
    } catch (err: unknown) {
      /* The server's own sentence, verbatim (WP-43). A 409 here says exactly
         which of the three refusals fired -- name mismatch, non-terminal jobs,
         or a GPU reservation the scheduler still holds -- and nothing this
         side could write would be truer than that. */
      setError(
        err instanceof Error && err.message
          ? err.message
          : "The deletion was refused and the server gave no reason.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }, [deleteProject, typedName]);

  if (!canDelete) return null;

  return (
    <>
      <button
        type="button"
        onClick={() => setStage("categories")}
        className="rounded-lg border border-red-300 bg-white px-4 py-2 text-sm font-medium text-red-700 transition-colors hover:bg-red-50 dark:border-red-800 dark:bg-transparent dark:text-red-400 dark:hover:bg-red-900/30"
      >
        Delete project
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 px-4 py-10"
          role="dialog"
          aria-modal="true"
          aria-label={`Delete ${projectName}`}
        >
          <div className="w-full max-w-2xl rounded-xl border border-gray-200 bg-white p-6 shadow-xl dark:border-gray-700 dark:bg-gray-900">
            {stage === "categories" && (
              <CategoryStage
                projectName={projectName}
                categories={categories}
                selected={selected}
                toggle={toggle}
                allSelected={allSelected}
                isLoading={isLoading}
                previewError={
                  previewError ? String(previewError.message ?? previewError) : null
                }
                preview={preview}
                blocked={blocked}
                cancellingId={cancellingId}
                onCancelJob={onCancelJob}
                error={error}
                onNext={() => setStage("confirm")}
                onClose={close}
              />
            )}

            {stage === "confirm" && preview && (
              <ConfirmStage
                preview={preview}
                typedName={typedName}
                setTypedName={setTypedName}
                isSubmitting={isSubmitting}
                error={error}
                onBack={() => setStage("categories")}
                onDelete={onDelete}
                onClose={close}
              />
            )}

            {stage === "done" && result && (
              <DoneStage
                result={result}
                onClose={() => {
                  close();
                  router.push("/projects");
                }}
              />
            )}
          </div>
        </div>
      )}
    </>
  );
}

/* ------------------------------------------------------------------------ */
/* Stage 1 — every category, nothing pre-selected                            */
/* ------------------------------------------------------------------------ */

function CategoryStage({
  projectName,
  categories,
  selected,
  toggle,
  allSelected,
  isLoading,
  previewError,
  preview,
  blocked,
  cancellingId,
  onCancelJob,
  error,
  onNext,
  onClose,
}: {
  projectName: string;
  categories: DeletionCategory[];
  selected: Set<string>;
  toggle: (key: string) => void;
  allSelected: boolean;
  isLoading: boolean;
  previewError: string | null;
  preview: ReturnType<typeof useProjectDeletion>["preview"];
  blocked: boolean;
  cancellingId: string | null;
  onCancelJob: (jobId: string) => Promise<void>;
  error: string | null;
  onNext: () => void;
  onClose: () => void;
}): React.ReactElement {
  const remaining = categories.filter((c) => !selected.has(c.key)).length;

  return (
    <>
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
        Delete “{projectName}” — what this will destroy
      </h3>

      {/* THE POINT OF THE FRICTION, said in plain words rather than implied by
          the mechanism. */}
      <div className="mt-3 rounded-lg border border-amber-300 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-900/20">
        <p className="text-sm text-amber-900 dark:text-amber-200">
          Below is everything this project holds. Read each line and tick it to
          confirm you are willing to lose it.{" "}
          <strong>
            If you see something here you want to keep, stop. Close this dialog,
            go and save that material somewhere outside this project, and come
            back afterwards.
          </strong>{" "}
          That is what this list is for — there is no way to get any of it back
          once the deletion runs.
        </p>
      </div>

      {isLoading && !preview && (
        <p className="mt-6 text-sm text-gray-500 dark:text-gray-400">
          Counting what this project holds…
        </p>
      )}

      {previewError && (
        <div className="mt-4 rounded-lg border border-red-200 bg-red-100 p-3 dark:border-red-700 dark:bg-red-900/30">
          <p className="text-sm text-red-700 dark:text-red-300">{previewError}</p>
        </div>
      )}

      {/* Task 3: running work is cancelled for real, or deletion refuses. */}
      {preview && preview.blocking_jobs.length > 0 && (
        <div className="mt-5 rounded-lg border border-red-300 bg-red-50 p-4 dark:border-red-800 dark:bg-red-900/20">
          <p className="text-sm font-semibold text-red-800 dark:text-red-300">
            This project cannot be deleted while work is still running.
          </p>
          <p className="mt-1 text-xs text-red-700 dark:text-red-400">
            {preview.blocking_jobs.length} job
            {preview.blocking_jobs.length === 1 ? " is" : "s are"} still pending
            or running. Cancelling stops the work on the GPU and releases its
            reservation; deletion becomes available once every job has finished
            or been cancelled.
          </p>
          <ul className="mt-3 space-y-2">
            {preview.blocking_jobs.map((job) => (
              <li
                key={job.id || job.job_type}
                className="flex items-center justify-between gap-3 rounded border border-red-200 bg-white px-3 py-2 dark:border-red-800 dark:bg-gray-900"
              >
                <span className="min-w-0">
                  <span className="block truncate text-sm text-gray-900 dark:text-white">
                    {job.job_type}{" "}
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      {job.status}
                    </span>
                  </span>
                  <span className="block truncate font-mono text-xs text-gray-500 dark:text-gray-400">
                    {job.id || job.note || "—"}
                  </span>
                </span>
                {job.id && (
                  <button
                    type="button"
                    onClick={() => onCancelJob(job.id)}
                    disabled={cancellingId === job.id}
                    className="shrink-0 rounded border border-red-400 px-3 py-1 text-xs font-medium text-red-700 hover:bg-red-100 disabled:opacity-50 dark:text-red-300 dark:hover:bg-red-900/40"
                  >
                    {cancellingId === job.id ? "Cancelling…" : "Cancel job"}
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* A GPU reservation the SCHEDULER still holds, or a registry that could
          not be read at all. Both block, and they say which. */}
      {preview && preview.gpu_reservations_held.length > 0 && (
        <div className="mt-4 rounded-lg border border-red-300 bg-red-50 p-4 dark:border-red-800 dark:bg-red-900/20">
          <p className="text-sm font-semibold text-red-800 dark:text-red-300">
            The GPU scheduler still holds{" "}
            {preview.gpu_reservations_held.length} reservation
            {preview.gpu_reservations_held.length === 1 ? "" : "s"} for this
            project.
          </p>
          <ul className="mt-2 space-y-1 font-mono text-xs text-red-700 dark:text-red-400">
            {preview.gpu_reservations_held.map((r) => (
              <li key={r.reservation_id}>
                {r.node_id} · {r.vram_mb} MB · job {r.job_id.slice(0, 8)} ·
                expires {r.expires_at || "—"}
              </li>
            ))}
          </ul>
        </div>
      )}

      {preview?.scheduler_registry_error && (
        <div className="mt-4 rounded-lg border border-red-300 bg-red-50 p-4 dark:border-red-800 dark:bg-red-900/20">
          <p className="text-sm text-red-800 dark:text-red-300">
            The GPU scheduler’s reservation registry could not be read, so it is
            not known whether this project still holds a reservation. Deletion
            refuses rather than assume it does not.
          </p>
          <p className="mt-1 font-mono text-xs text-red-700 dark:text-red-400">
            {preview.scheduler_registry_error}
          </p>
        </div>
      )}

      {preview && categories.length > 0 && (
        <ul className="mt-5 space-y-2">
          {categories.map((c) => (
            <li key={c.key}>
              <label
                className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors ${
                  selected.has(c.key)
                    ? "border-red-500 bg-red-50 dark:bg-red-900/20"
                    : "border-gray-200 hover:border-gray-300 dark:border-gray-700 dark:hover:border-gray-600"
                }`}
              >
                <input
                  type="checkbox"
                  checked={selected.has(c.key)}
                  onChange={() => toggle(c.key)}
                  className="mt-1"
                  aria-label={`${c.label}: ${c.count}`}
                />
                <span className="min-w-0 flex-1">
                  <span className="flex items-baseline justify-between gap-3">
                    <span className="text-sm font-medium text-gray-900 dark:text-white">
                      {c.label}
                    </span>
                    <span className="shrink-0 font-mono text-sm text-gray-900 dark:text-white">
                      {c.count}
                    </span>
                  </span>
                  <span className="mt-0.5 block text-xs text-gray-500 dark:text-gray-400">
                    {c.detail}
                  </span>
                  {Object.keys(c.breakdown).length > 0 && (
                    <span className="mt-1 block font-mono text-xs text-gray-500 dark:text-gray-400">
                      {Object.entries(c.breakdown)
                        .map(([k, v]) => `${k}: ${v}`)
                        .join("  ·  ")}
                    </span>
                  )}
                </span>
              </label>
            </li>
          ))}
        </ul>
      )}

      {preview?.redis_registry_error && (
        <p className="mt-3 text-xs text-amber-700 dark:text-amber-400">
          The pipeline scratch-state count could not be taken
          ({preview.redis_registry_error}), so it is shown as 0 rather than
          measured. It does not block the deletion: those keys are per-job
          scratch and are inert once the job records are gone.
        </p>
      )}

      {error && (
        <div className="mt-4 rounded-lg border border-red-200 bg-red-100 p-3 dark:border-red-700 dark:bg-red-900/30">
          <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
        </div>
      )}

      <div className="mt-6 flex items-center justify-between gap-3">
        <p className="text-xs text-gray-500 dark:text-gray-400">
          {allSelected
            ? "All categories confirmed."
            : `${remaining} categor${remaining === 1 ? "y" : "ies"} left to confirm.`}
        </p>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-800"
          >
            Keep this project
          </button>
          <button
            type="button"
            onClick={onNext}
            /* The gate. Not merely styled as disabled -- the confirmation
               stage is unreachable until every line has been read and
               ticked, and until nothing is still running. */
            disabled={!allSelected || blocked}
            className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Continue
          </button>
        </div>
      </div>
    </>
  );
}

/* ------------------------------------------------------------------------ */
/* Stage 2 — restate, warn, and require the name typed out                   */
/* ------------------------------------------------------------------------ */

function ConfirmStage({
  preview,
  typedName,
  setTypedName,
  isSubmitting,
  error,
  onBack,
  onDelete,
  onClose,
}: {
  preview: NonNullable<ReturnType<typeof useProjectDeletion>["preview"]>;
  typedName: string;
  setTypedName: (v: string) => void;
  isSubmitting: boolean;
  error: string | null;
  onBack: () => void;
  onDelete: () => Promise<void>;
  onClose: () => void;
}): React.ReactElement {
  /* Exact match, no trimming and no case folding. The name is the thing being
     confirmed; accepting a near-miss would confirm something else. */
  const nameMatches = typedName === preview.project_name;

  const nonEmpty = preview.categories.filter((c) => c.count > 0);

  return (
    <>
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
        Permanently delete “{preview.project_name}”?
      </h3>

      <div className="mt-3 rounded-lg border border-red-300 bg-red-50 p-4 dark:border-red-800 dark:bg-red-900/20">
        <p className="text-sm font-semibold text-red-900 dark:text-red-200">
          This is permanent. It cannot be undone from this interface, and there
          is no “restore project” action anywhere in the application.
        </p>
        <p className="mt-2 text-sm text-red-800 dark:text-red-300">
          Once you press Delete, the material listed below is destroyed:
          {" "}
          {preview.total_rows.toLocaleString()} database record
          {preview.total_rows === 1 ? "" : "s"} and{" "}
          {formatBytes(preview.total_bytes)} of stored files.
        </p>
      </div>

      <dl className="mt-4 max-h-56 space-y-1 overflow-y-auto rounded-lg border border-gray-200 p-3 dark:border-gray-700">
        {nonEmpty.length === 0 && (
          <p className="text-sm text-gray-500 dark:text-gray-400">
            This project holds no material in any category. Deleting it removes
            the project record itself.
          </p>
        )}
        {nonEmpty.map((c) => (
          <div key={c.key} className="flex justify-between gap-4 text-sm">
            <dt className="text-gray-600 dark:text-gray-300">{c.label}</dt>
            <dd className="font-mono text-gray-900 dark:text-white">{c.count}</dd>
          </div>
        ))}
      </dl>

      <label className="mt-5 block">
        <span className="text-sm text-gray-700 dark:text-gray-300">
          Type the project name exactly to enable deletion:{" "}
          <span className="font-mono font-semibold text-gray-900 dark:text-white">
            {preview.project_name}
          </span>
        </span>
        <input
          type="text"
          value={typedName}
          onChange={(e) => setTypedName(e.target.value)}
          autoComplete="off"
          spellCheck={false}
          className="mt-2 w-full rounded-lg border border-gray-300 px-3 py-2 font-mono text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
          placeholder="Project name"
          aria-label="Type the project name to confirm deletion"
        />
      </label>

      {error && (
        <div className="mt-4 rounded-lg border border-red-200 bg-red-100 p-3 dark:border-red-700 dark:bg-red-900/30">
          <p className="text-xs font-medium uppercase tracking-wide text-red-700 dark:text-red-300">
            The server refused this
          </p>
          <p className="mt-1 text-sm text-red-600 dark:text-red-400">{error}</p>
        </div>
      )}

      <div className="mt-6 flex items-center justify-end gap-3">
        <button
          type="button"
          onClick={onBack}
          disabled={isSubmitting}
          className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 disabled:opacity-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-800"
        >
          Back
        </button>
        <button
          type="button"
          onClick={onClose}
          disabled={isSubmitting}
          className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 disabled:opacity-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-800"
        >
          Keep this project
        </button>
        <button
          type="button"
          onClick={onDelete}
          disabled={!nameMatches || isSubmitting}
          className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {isSubmitting ? "Deleting…" : "Delete permanently"}
        </button>
      </div>
    </>
  );
}

/* ------------------------------------------------------------------------ */
/* Stage 3 — what was actually destroyed                                     */
/* ------------------------------------------------------------------------ */

function DoneStage({
  result,
  onClose,
}: {
  result: DeletionResult;
  onClose: () => void;
}): React.ReactElement {
  return (
    <>
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
        “{result.project_name}” has been deleted
      </h3>
      {/* The destruction, not a status code (WP-45's lesson). These are the
          rows the server actually removed, read back from the same transaction
          that removed them. */}
      <dl className="mt-4 space-y-1">
        <Row label="Database records removed" value={result.total_rows_deleted} />
        <Row label="Stored files deleted" value={result.files_deleted} />
        <Row
          label="Stored files preserved (shared or in the library)"
          value={result.files_preserved}
        />
        <Row label="Pipeline scratch keys cleared" value={result.redis_keys_deleted} />
      </dl>
      <p className="mt-4 text-xs text-gray-500 dark:text-gray-400">
        An audit record of this deletion — who, when, and the count of every
        category — was written before the deletion began and survives it:{" "}
        <span className="font-mono">{result.audit_id}</span>
      </p>
      {result.files_preserved > 0 && (
        <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
          Files shared with the asset library, or with a project that still
          exists, were deliberately left in place.
        </p>
      )}
      {/* Reported, never hidden. An unconfirmed delete is not counted as a
          delete above, so this is the only place the operator learns that some
          bytes outlived their records. */}
      {result.files_failed.length > 0 && (
        <div className="mt-3 rounded-lg border border-amber-300 bg-amber-50 p-3 dark:border-amber-800 dark:bg-amber-900/20">
          <p className="text-sm text-amber-900 dark:text-amber-200">
            {result.files_failed.length} stored file
            {result.files_failed.length === 1 ? "" : "s"} could not be confirmed
            deleted. The project records are gone, so those bytes are now
            unreferenced and will be swept as orphans. They are recorded in the
            audit entry above.
          </p>
        </div>
      )}
      <div className="mt-6 flex justify-end">
        <button
          type="button"
          onClick={onClose}
          className="rounded-lg bg-gray-800 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700 dark:bg-gray-700 dark:hover:bg-gray-600"
        >
          Back to projects
        </button>
      </div>
    </>
  );
}

function Row({
  label,
  value,
}: {
  label: string;
  value: number;
}): React.ReactElement {
  return (
    <div className="flex justify-between gap-4 text-sm">
      <dt className="text-gray-600 dark:text-gray-300">{label}</dt>
      <dd className="font-mono text-gray-900 dark:text-white">{value}</dd>
    </div>
  );
}
