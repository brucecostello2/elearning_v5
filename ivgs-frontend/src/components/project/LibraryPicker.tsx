"use client";

import React, { useMemo, useState } from "react";
import { referenceLibraryAsset, useLibraryAssets } from "@/hooks/useLibrary";
import { KIND_TO_ASSET_TYPE, type LibraryAsset } from "@/types/library";

/**
 * Select-from-library, the other half of AD-09.11's "each media input becomes
 * select-from-library or upload".
 *
 * REFERENCE, DON'T COPY. Choosing an asset here calls
 * `POST /projects/{id}/library-reference`, which creates a project asset row
 * pointing at the SAME stored object. No bytes are read or re-uploaded, so
 * selecting a 2 GB reference clip is instant and costs no storage — and
 * replacing that clip later across a course becomes a reference change rather
 * than a re-upload (AD-09.8 fork depth).
 *
 * The asset-type dropdown is driven by `KIND_TO_ASSET_TYPE`, which mirrors the
 * server's own map. `library_asset_kind` and `assets.asset_type` are DIFFERENT
 * vocabularies; offering a combination the server refuses would be a 400 the
 * operator could not have predicted from the UI.
 */
export default function LibraryPicker({
  projectId,
  onReferenced,
}: {
  projectId: string;
  onReferenced?: (message: string) => void;
}): React.ReactElement {
  const { assets, isLoading } = useLibraryAssets();
  const [selectedId, setSelectedId] = useState("");
  const [assetType, setAssetType] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const selected: LibraryAsset | undefined = useMemo(
    () => (assets ?? []).find((a) => a.id === selectedId),
    [assets, selectedId],
  );

  const allowedTypes = selected ? KIND_TO_ASSET_TYPE[selected.kind] : [];

  async function submit() {
    if (!selected || !assetType) return;
    setBusy(true);
    setError("");
    try {
      await referenceLibraryAsset(projectId, {
        library_asset_id: selected.id,
        asset_type: assetType,
      });
      onReferenced?.(
        `"${selected.name}" is now available in this project. No copy was made — the project references the library entry.`,
      );
      setSelectedId("");
      setAssetType("");
    } catch (e) {
      setError(e instanceof Error && e.message ? e.message : "The reference failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-xl border border-gray-300 bg-gray-100 p-6 dark:border-gray-700 dark:bg-gray-800">
      <h3 className="mb-1 text-sm font-semibold text-gray-900 dark:text-white">
        Use from the library
      </h3>
      <p className="mb-4 text-xs text-gray-500 dark:text-gray-400">
        Referencing does not copy the file. The project points at the library
        entry, so replacing it later is one change rather than a re-upload.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <select
          className="rounded-md border border-gray-400 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
          value={selectedId}
          onChange={(e) => {
            setSelectedId(e.target.value);
            setAssetType("");
          }}
          disabled={isLoading}
          aria-label="Library asset"
        >
          <option value="">
            {isLoading ? "Loading library…" : "— choose a library asset —"}
          </option>
          {(assets ?? []).map((a) => (
            <option key={a.id} value={a.id}>
              {a.name} ({a.kind.replace(/_/g, " ")})
            </option>
          ))}
        </select>

        <select
          className="rounded-md border border-gray-400 bg-white px-3 py-2 text-sm text-gray-900 disabled:opacity-50 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
          value={assetType}
          onChange={(e) => setAssetType(e.target.value)}
          disabled={!selected}
          aria-label="Use as asset type"
        >
          <option value="">— use as —</option>
          {allowedTypes.map((t) => (
            <option key={t} value={t}>
              {t.replace(/_/g, " ")}
            </option>
          ))}
        </select>

        <button
          type="button"
          className="rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          onClick={submit}
          disabled={busy || !selected || !assetType}
        >
          {busy ? "Linking…" : "Use in this project"}
        </button>
      </div>

      {(assets ?? []).length === 0 && !isLoading && (
        <p className="mt-3 text-xs text-gray-500 dark:text-gray-400">
          The library is empty. Upload brand media once from the Library page
          and it becomes available to every project.
        </p>
      )}
      {error && (
        <p className="mt-3 text-sm text-red-500" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
