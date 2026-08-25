"use client";

import React, { useMemo, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { useActors, useLibraryAssets, usePresets } from "@/hooks/useLibrary";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorBoundary from "@/components/ErrorBoundary";
import AssetUploader from "@/components/AssetUploader";
import {
  LIBRARY_ASSET_KINDS,
  LOGO_POLICIES,
  PRESENTER_ORIENTATIONS,
  type Actor,
  type LibraryAsset,
  type LibraryAssetKind,
  type Preset,
  type PresetPayload,
} from "@/types/library";

/**
 * Content Library — AD-09.4 (assets, actors) and AD-09.5 (presets).
 *
 * AD-09.15 CRITERION 7: all operations available in the GUI, no CLI step.
 * Everything the API exposes for these three entities is reachable from this
 * page — upload, edit, supersede, promote, create an actor, retire an actor,
 * create a preset, revise it into a new version, and inspect every version.
 *
 * WHAT THIS PAGE DELIBERATELY DOES NOT OFFER, and why the absence is the
 * honest choice rather than an omission: nothing that would render a control
 * with no effect behind it. Per-scene presenter toggles and the logo overlay
 * are NOT here, because WP-56 Task 3 stopped on the finding that the render
 * chain feeding them is broken at three of its four links. A preset's branding
 * block IS here — the operator needs somewhere to record those decisions — and
 * it carries a standing banner saying it is recorded, not rendered. Shipping
 * the control without the banner would be a ninth instance of the AD-09.3 stub
 * family: a green surface over an empty action.
 */

const inputCls =
  "w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:border-blue-500 focus:outline-none";
const labelCls = "block text-sm font-medium text-gray-300 mb-1";
const btnPrimary =
  "inline-flex items-center rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50";
const btnSubtle =
  "inline-flex items-center rounded-md border border-gray-600 bg-gray-800 px-3 py-2 text-sm font-medium text-gray-200 hover:bg-gray-700 disabled:opacity-50";
const cardCls = "rounded-lg border border-gray-800 bg-gray-900 p-4";

/**
 * Surface a caught error verbatim.
 *
 * `ApiRequestError` carries the API's own message (api-client.ts runs the body
 * through `apiErrorMessage` before throwing), so the operator sees the reason
 * the server gave -- "A library 'logo' cannot be referenced as asset_type
 * 'audio'" -- rather than a generic failure string. Every 400 this page can
 * provoke is operator-actionable and states what to do instead.
 */
function errText(e: unknown, fallback = "The request failed."): string {
  return e instanceof Error && e.message ? e.message : fallback;
}

type Tab = "assets" | "actors" | "presets";

function humanBytes(n: number | null): string {
  if (n === null || n === undefined) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

/** The standing warning on everything branding-shaped. See the module note. */
function RecordedNotRenderedBanner(): React.ReactElement {
  return (
    <div className="rounded-md border border-amber-800 bg-amber-950/40 p-3 text-sm text-amber-200">
      <strong className="font-semibold">Recorded, not rendered.</strong> These
      values are stored on the preset and returned by the API, but no render
      path reads them yet — a logo set here will not appear in a rendered
      course. WP-56 Task 3 stopped on the per-scene presenter and logo overlay
      chain; see the WP-56 report. Set them if you want the decision recorded;
      do not expect them in output.
    </div>
  );
}

export default function LibraryPage(): React.ReactElement {
  const { user } = useAuth();
  const [tab, setTab] = useState<Tab>("assets");
  const isAdmin = user?.role === "admin";
  const canWrite = user?.role === "admin" || user?.role === "operator";

  return (
    <ErrorBoundary>
      <div className="mx-auto max-w-6xl px-6 py-8">
        <header className="mb-6">
          <h1 className="text-2xl font-semibold text-gray-100">Content Library</h1>
          <p className="mt-1 text-sm text-gray-400">
            Reusable assets, presenter identities and production presets
            (AD-09.4, AD-09.5). Assets are referenced into projects, never
            copied, so replacing one is a reference change rather than a
            re-upload.
          </p>
        </header>

        <nav className="mb-6 flex gap-2 border-b border-gray-800">
          {(["assets", "actors", "presets"] as Tab[]).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={`px-4 py-2 text-sm font-medium capitalize ${
                tab === t
                  ? "border-b-2 border-blue-500 text-blue-400"
                  : "text-gray-400 hover:text-gray-200"
              }`}
            >
              {t}
            </button>
          ))}
        </nav>

        {tab === "assets" && <AssetsTab canWrite={canWrite} isAdmin={isAdmin} />}
        {tab === "actors" && <ActorsTab canWrite={canWrite} />}
        {tab === "presets" && <PresetsTab canWrite={canWrite} />}
      </div>
    </ErrorBoundary>
  );
}

/* ======================================================================== */
/* Assets                                                                    */
/* ======================================================================== */

function AssetsTab({
  canWrite,
  isAdmin,
}: {
  canWrite: boolean;
  isAdmin: boolean;
}): React.ReactElement {
  const [kindFilter, setKindFilter] = useState<string>("");
  const { assets, isLoading, error, uploadAsset, supersedeAsset, promoteAsset } =
    useLibraryAssets(kindFilter || undefined);

  const [file, setFile] = useState<File | null>(null);
  const [kind, setKind] = useState<LibraryAssetKind>("logo");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [tagsText, setTagsText] = useState("");
  const [ownerScope, setOwnerScope] = useState<"user" | "global">("user");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string>("");
  const [formError, setFormError] = useState<string>("");
  const [supersedeFor, setSupersedeFor] = useState<LibraryAsset | null>(null);

  async function submitUpload(e: React.FormEvent) {
    e.preventDefault();
    if (!file) {
      setFormError("Choose a file first.");
      return;
    }
    setBusy(true);
    setFormError("");
    setNotice("");
    try {
      const tags = tagsText
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);
      const result = await uploadAsset({
        file,
        kind,
        name: name.trim() || file.name,
        description: description.trim() || undefined,
        tags,
        ownerScope,
      });
      /* The dedup answer is the whole reason `was_deduplicated` exists — a
         dedup hit and a fresh upload are otherwise identical replies, and the
         operator cannot tell whether the library grew. */
      setNotice(
        result.was_deduplicated
          ? `Those exact bytes were already in the ${ownerScope} library as "${result.name}". Nothing was uploaded; the existing entry is selected.`
          : `Uploaded "${result.name}" (${humanBytes(result.file_size_bytes)}).`,
      );
      setFile(null);
      setName("");
      setDescription("");
      setTagsText("");
    } catch (err) {
      setFormError(errText(err));
    } finally {
      setBusy(false);
    }
  }

  const candidates = useMemo(
    () =>
      (assets ?? []).filter(
        (a) => supersedeFor && a.kind === supersedeFor.kind && a.id !== supersedeFor.id,
      ),
    [assets, supersedeFor],
  );

  return (
    <div className="space-y-6">
      {canWrite && (
        <form onSubmit={submitUpload} className={cardCls}>
          <h2 className="mb-4 text-lg font-medium text-gray-100">
            Upload to the library
          </h2>
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <label className={labelCls} htmlFor="lib-kind">
                Kind
              </label>
              <select
                id="lib-kind"
                className={inputCls}
                value={kind}
                onChange={(e) => setKind(e.target.value as LibraryAssetKind)}
              >
                {LIBRARY_ASSET_KINDS.map((k) => (
                  <option key={k} value={k}>
                    {k.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
              {kind === "font" && (
                <p className="mt-1 text-xs text-amber-300">
                  Fonts are stored but not yet provisioned to the compositor
                  node (AD-09.14 open question 6). A font in the library that is
                  not on the node falls back silently at render time.
                </p>
              )}
            </div>
            <div>
              <label className={labelCls} htmlFor="lib-scope">
                Scope
              </label>
              <select
                id="lib-scope"
                className={inputCls}
                value={ownerScope}
                onChange={(e) => setOwnerScope(e.target.value as "user" | "global")}
              >
                <option value="user">user — yours</option>
                <option value="global" disabled={!isAdmin}>
                  global — shared{isAdmin ? "" : " (admin only)"}
                </option>
              </select>
            </div>
            <div>
              <label className={labelCls} htmlFor="lib-name">
                Name
              </label>
              <input
                id="lib-name"
                className={inputCls}
                value={name}
                placeholder={file?.name ?? "Acme mark"}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <div>
              <label className={labelCls} htmlFor="lib-tags">
                Tags (comma separated)
              </label>
              <input
                id="lib-tags"
                className={inputCls}
                value={tagsText}
                placeholder="brand, 2026"
                onChange={(e) => setTagsText(e.target.value)}
              />
            </div>
            <div className="md:col-span-2">
              <label className={labelCls} htmlFor="lib-desc">
                Description
              </label>
              <input
                id="lib-desc"
                className={inputCls}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
            <div className="md:col-span-2">
              <AssetUploader
                onFileSelect={(files) => {
                  const list = Array.from(files as FileList);
                  setFile(list[0] ?? null);
                }}
                selectedFile={file}
                onRemove={() => setFile(null)}
                isUploading={busy}
              />
            </div>
          </div>
          {formError && (
            <p className="mt-3 text-sm text-red-400" role="alert">
              {formError}
            </p>
          )}
          {notice && <p className="mt-3 text-sm text-green-400">{notice}</p>}
          <div className="mt-4">
            <button type="submit" className={btnPrimary} disabled={busy || !file}>
              {busy ? "Uploading…" : "Upload"}
            </button>
          </div>
        </form>
      )}

      <div className={cardCls}>
        <div className="mb-4 flex items-center justify-between gap-4">
          <h2 className="text-lg font-medium text-gray-100">Library</h2>
          <select
            className={`${inputCls} w-auto`}
            value={kindFilter}
            onChange={(e) => setKindFilter(e.target.value)}
            aria-label="Filter by kind"
          >
            <option value="">All kinds</option>
            {LIBRARY_ASSET_KINDS.map((k) => (
              <option key={k} value={k}>
                {k.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </div>

        {isLoading && <LoadingSpinner size="md" label="Loading library..." />}
        {error && (
          <p className="text-sm text-red-400" role="alert">
            {errText(error)}
          </p>
        )}
        {assets && assets.length === 0 && (
          <p className="text-sm text-gray-400">
            Nothing here yet. Upload brand media, reference clips or music beds
            once and reuse them across every course.
          </p>
        )}

        {assets && assets.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-gray-400">
                <tr>
                  <th className="py-2 pr-4">Name</th>
                  <th className="py-2 pr-4">Kind</th>
                  <th className="py-2 pr-4">Scope</th>
                  <th className="py-2 pr-4">Size</th>
                  <th className="py-2 pr-4">Tags</th>
                  <th className="py-2 pr-4">Actions</th>
                </tr>
              </thead>
              <tbody className="text-gray-200">
                {assets.map((a) => (
                  <tr key={a.id} className="border-t border-gray-800">
                    <td className="py-2 pr-4">{a.name}</td>
                    <td className="py-2 pr-4">{a.kind.replace(/_/g, " ")}</td>
                    <td className="py-2 pr-4">{a.owner_scope}</td>
                    <td className="py-2 pr-4">{humanBytes(a.file_size_bytes)}</td>
                    <td className="py-2 pr-4">{(a.tags ?? []).join(", ") || "—"}</td>
                    <td className="py-2 pr-4">
                      <div className="flex gap-2">
                        {canWrite && (
                          <button
                            type="button"
                            className={btnSubtle}
                            onClick={() => setSupersedeFor(a)}
                          >
                            Replace
                          </button>
                        )}
                        {isAdmin && a.owner_scope === "user" && (
                          <button
                            type="button"
                            className={btnSubtle}
                            onClick={async () => {
                              setFormError("");
                              try {
                                await promoteAsset(a.id);
                                setNotice(`"${a.name}" promoted to the global library.`);
                              } catch (err) {
                                setFormError(errText(err));
                              }
                            }}
                          >
                            Promote to global
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {supersedeFor && (
        <div className={cardCls}>
          <h3 className="mb-2 text-base font-medium text-gray-100">
            Replace &ldquo;{supersedeFor.name}&rdquo;
          </h3>
          <p className="mb-3 text-sm text-gray-400">
            The old asset is retired, not deleted — every project already built
            from it keeps resolving. Pick the {supersedeFor.kind.replace(/_/g, " ")}{" "}
            that supersedes it.
          </p>
          {candidates.length === 0 ? (
            <p className="text-sm text-amber-300">
              No other {supersedeFor.kind.replace(/_/g, " ")} in the library to
              replace it with. Upload the replacement first.
            </p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {candidates.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  className={btnSubtle}
                  onClick={async () => {
                    setFormError("");
                    try {
                      await supersedeAsset(supersedeFor.id, c.id);
                      setNotice(
                        `"${supersedeFor.name}" retired in favour of "${c.name}".`,
                      );
                      setSupersedeFor(null);
                    } catch (err) {
                      setFormError(errText(err));
                    }
                  }}
                >
                  {c.name}
                </button>
              ))}
            </div>
          )}
          <div className="mt-4">
            <button
              type="button"
              className={btnSubtle}
              onClick={() => setSupersedeFor(null)}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/* ======================================================================== */
/* Actors                                                                    */
/* ======================================================================== */

function ActorsTab({ canWrite }: { canWrite: boolean }): React.ReactElement {
  const [includeInactive, setIncludeInactive] = useState(false);
  const { actors, isLoading, error, createActor, updateActor } =
    useActors(includeInactive);
  const { assets } = useLibraryAssets();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [clipId, setClipId] = useState("");
  const [imageId, setImageId] = useState("");
  const [orientation, setOrientation] = useState<"landscape" | "portrait">(
    "landscape",
  );
  const [voiceText, setVoiceText] = useState("{}");
  const [bindingsText, setBindingsText] = useState("{}");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState("");
  const [notice, setNotice] = useState("");

  const clips = (assets ?? []).filter(
    (a) => a.kind === "reference_clip" || a.kind === "video_clip",
  );
  const images = (assets ?? []).filter(
    (a) => a.kind === "reference_image" || a.kind === "logo",
  );

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setFormError("");
    setNotice("");
    try {
      let voice: Record<string, unknown> | null = null;
      let bindings: Record<string, unknown> | null = null;
      try {
        voice = voiceText.trim() && voiceText.trim() !== "{}" ? JSON.parse(voiceText) : null;
        bindings =
          bindingsText.trim() && bindingsText.trim() !== "{}"
            ? JSON.parse(bindingsText)
            : null;
      } catch {
        setFormError("Voice profile and engine bindings must be valid JSON objects.");
        setBusy(false);
        return;
      }
      const created = await createActor({
        name: name.trim(),
        description: description.trim() || null,
        reference_clip_id: clipId || null,
        reference_image_id: imageId || null,
        voice_profile: voice,
        engine_bindings: bindings,
        default_orientation: orientation,
      });
      setNotice(`Actor "${created.name}" created.`);
      setName("");
      setDescription("");
      setClipId("");
      setImageId("");
      setVoiceText("{}");
      setBindingsText("{}");
    } catch (err) {
      setFormError(errText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      {canWrite && (
        <form onSubmit={submit} className={cardCls}>
          <h2 className="mb-2 text-lg font-medium text-gray-100">Create an actor</h2>
          <p className="mb-4 text-sm text-gray-400">
            A presenter identity: reference media plus the voice and per-engine
            parameters that reproduce it. An actor is only reproducible on the
            engine it was established against — changing that engine is an
            identity change, not a setting.
          </p>
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <label className={labelCls} htmlFor="actor-name">
                Name
              </label>
              <input
                id="actor-name"
                className={inputCls}
                value={name}
                placeholder="Sarah — corporate"
                onChange={(e) => setName(e.target.value)}
                required
              />
            </div>
            <div>
              <label className={labelCls} htmlFor="actor-orientation">
                Default orientation
              </label>
              <select
                id="actor-orientation"
                className={inputCls}
                value={orientation}
                onChange={(e) =>
                  setOrientation(e.target.value as "landscape" | "portrait")
                }
              >
                {PRESENTER_ORIENTATIONS.map((o) => (
                  <option key={o} value={o}>
                    {o}
                  </option>
                ))}
              </select>
              <p className="mt-1 text-xs text-gray-500">
                Orientation is not a crop — a portrait presenter must be
                rendered portrait by the engine (AD-09.9).
              </p>
            </div>
            <div>
              <label className={labelCls} htmlFor="actor-clip">
                Reference clip
              </label>
              <select
                id="actor-clip"
                className={inputCls}
                value={clipId}
                onChange={(e) => setClipId(e.target.value)}
              >
                <option value="">— none —</option>
                {clips.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className={labelCls} htmlFor="actor-image">
                Reference image
              </label>
              <select
                id="actor-image"
                className={inputCls}
                value={imageId}
                onChange={(e) => setImageId(e.target.value)}
              >
                <option value="">— none —</option>
                {images.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="md:col-span-2">
              <label className={labelCls} htmlFor="actor-desc">
                Description
              </label>
              <input
                id="actor-desc"
                className={inputCls}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
            <div>
              <label className={labelCls} htmlFor="actor-voice">
                Voice profile (JSON)
              </label>
              <textarea
                id="actor-voice"
                className={`${inputCls} font-mono`}
                rows={4}
                value={voiceText}
                onChange={(e) => setVoiceText(e.target.value)}
              />
            </div>
            <div>
              <label className={labelCls} htmlFor="actor-bindings">
                Engine bindings (JSON)
              </label>
              <textarea
                id="actor-bindings"
                className={`${inputCls} font-mono`}
                rows={4}
                value={bindingsText}
                onChange={(e) => setBindingsText(e.target.value)}
              />
              <p className="mt-1 text-xs text-amber-300">
                Awaiting the operator. The MagiHuman parameter set that keeps an
                actor and voice consistent is not recorded anywhere in this
                system (AD-09.14 open question 1). This field stores whatever
                you enter, keyed by engine, and nothing validates or reads it
                yet.
              </p>
            </div>
          </div>
          {formError && (
            <p className="mt-3 text-sm text-red-400" role="alert">
              {formError}
            </p>
          )}
          {notice && <p className="mt-3 text-sm text-green-400">{notice}</p>}
          <div className="mt-4">
            <button type="submit" className={btnPrimary} disabled={busy}>
              {busy ? "Creating…" : "Create actor"}
            </button>
          </div>
        </form>
      )}

      <div className={cardCls}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-medium text-gray-100">Actors</h2>
          <label className="flex items-center gap-2 text-sm text-gray-400">
            <input
              type="checkbox"
              checked={includeInactive}
              onChange={(e) => setIncludeInactive(e.target.checked)}
            />
            Show retired
          </label>
        </div>
        {isLoading && <LoadingSpinner size="md" label="Loading actors..." />}
        {error && (
          <p className="text-sm text-red-400" role="alert">
            {errText(error)}
          </p>
        )}
        {actors && actors.length === 0 && (
          <p className="text-sm text-gray-400">
            No actors yet. Create one so the same presenter and voice can be
            reused across courses.
          </p>
        )}
        {actors && actors.length > 0 && (
          <ul className="divide-y divide-gray-800">
            {actors.map((a: Actor) => (
              <li key={a.id} className="flex items-center justify-between py-3">
                <div>
                  <p className="text-sm font-medium text-gray-100">
                    {a.name}
                    {!a.is_active && (
                      <span className="ml-2 rounded bg-gray-700 px-2 py-0.5 text-xs text-gray-300">
                        retired
                      </span>
                    )}
                  </p>
                  <p className="text-xs text-gray-500">
                    {a.default_orientation}
                    {a.reference_clip_id ? " · reference clip bound" : " · no reference clip"}
                    {a.engine_bindings ? " · engine bindings recorded" : " · no engine bindings"}
                  </p>
                </div>
                {canWrite && a.is_active && (
                  <button
                    type="button"
                    className={btnSubtle}
                    onClick={() => updateActor(a.id, { is_active: false })}
                  >
                    Retire
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

/* ======================================================================== */
/* Presets                                                                   */
/* ======================================================================== */

function PresetsTab({ canWrite }: { canWrite: boolean }): React.ReactElement {
  const { presets, isLoading, error, createPreset, revisePreset, listVersions } =
    usePresets(true);
  const { actors } = useActors();
  const { assets } = useLibraryAssets("logo");

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [actorId, setActorId] = useState("");
  const [runtime, setRuntime] = useState("");
  const [audience, setAudience] = useState("");
  const [logoId, setLogoId] = useState("");
  const [logoPolicy, setLogoPolicy] = useState("");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState("");
  const [notice, setNotice] = useState("");
  const [reviseOf, setReviseOf] = useState<Preset | null>(null);
  const [versions, setVersions] = useState<Preset[] | null>(null);

  function buildPayload(): PresetPayload {
    const payload: PresetPayload = {};
    if (actorId) payload.actor_id = actorId;
    if (runtime.trim()) payload.max_runtime_seconds = Number(runtime);
    if (audience.trim()) payload.target_audience = audience.trim();
    if (logoId || logoPolicy) {
      payload.branding = {
        ...(logoId ? { logo_library_asset_id: logoId } : {}),
        ...(logoPolicy ? { logo_policy: logoPolicy as never } : {}),
      };
    }
    return payload;
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setFormError("");
    setNotice("");
    try {
      const payload = buildPayload();
      if (reviseOf) {
        const next = await revisePreset(reviseOf.name, {
          description: description.trim() || undefined,
          payload,
        });
        setNotice(
          `"${next.name}" is now version ${next.version}. Version ${
            next.version - 1
          } stays readable — projects created from it keep their provenance.`,
        );
        setReviseOf(null);
      } else {
        const created = await createPreset({
          name: name.trim(),
          description: description.trim() || undefined,
          payload,
        });
        setNotice(`Preset "${created.name}" created at version 1.`);
      }
      setName("");
      setDescription("");
      setActorId("");
      setRuntime("");
      setAudience("");
      setLogoId("");
      setLogoPolicy("");
    } catch (err) {
      setFormError(errText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      {canWrite && (
        <form onSubmit={submit} className={cardCls}>
          <h2 className="mb-2 text-lg font-medium text-gray-100">
            {reviseOf ? `Revise "${reviseOf.name}"` : "Create a preset"}
          </h2>
          <p className="mb-4 text-sm text-gray-400">
            Presets are defaults, not constraints. Applying one writes concrete
            values into a project; editing the preset afterwards never changes a
            project that already used it. Editing creates a new{" "}
            <strong>version</strong> rather than overwriting the old one.
          </p>
          <div className="grid gap-4 md:grid-cols-2">
            {!reviseOf && (
              <div>
                <label className={labelCls} htmlFor="preset-name">
                  Name
                </label>
                <input
                  id="preset-name"
                  className={inputCls}
                  value={name}
                  placeholder="Corporate 2026"
                  onChange={(e) => setName(e.target.value)}
                  required
                />
              </div>
            )}
            <div>
              <label className={labelCls} htmlFor="preset-actor">
                Actor
              </label>
              <select
                id="preset-actor"
                className={inputCls}
                value={actorId}
                onChange={(e) => setActorId(e.target.value)}
              >
                <option value="">— none —</option>
                {(actors ?? []).map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className={labelCls} htmlFor="preset-runtime">
                Max runtime (seconds)
              </label>
              <input
                id="preset-runtime"
                className={inputCls}
                type="number"
                min={1}
                value={runtime}
                onChange={(e) => setRuntime(e.target.value)}
              />
            </div>
            <div>
              <label className={labelCls} htmlFor="preset-audience">
                Target audience
              </label>
              <input
                id="preset-audience"
                className={inputCls}
                value={audience}
                onChange={(e) => setAudience(e.target.value)}
              />
            </div>
            <div className="md:col-span-2">
              <label className={labelCls} htmlFor="preset-desc">
                Description
              </label>
              <input
                id="preset-desc"
                className={inputCls}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
          </div>

          <fieldset className="mt-6 space-y-3 rounded-md border border-gray-800 p-4">
            <legend className="px-2 text-sm font-medium text-gray-300">
              Branding
            </legend>
            <RecordedNotRenderedBanner />
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <label className={labelCls} htmlFor="preset-logo">
                  Logo
                </label>
                <select
                  id="preset-logo"
                  className={inputCls}
                  value={logoId}
                  onChange={(e) => setLogoId(e.target.value)}
                >
                  <option value="">— none —</option>
                  {(assets ?? []).map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className={labelCls} htmlFor="preset-logo-policy">
                  Logo policy
                </label>
                <select
                  id="preset-logo-policy"
                  className={inputCls}
                  value={logoPolicy}
                  onChange={(e) => setLogoPolicy(e.target.value)}
                >
                  <option value="">— unset —</option>
                  {LOGO_POLICIES.map((p) => (
                    <option key={p} value={p}>
                      {p.replace(/_/g, " ")}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </fieldset>

          {formError && (
            <p className="mt-3 text-sm text-red-400" role="alert">
              {formError}
            </p>
          )}
          {notice && <p className="mt-3 text-sm text-green-400">{notice}</p>}
          <div className="mt-4 flex gap-2">
            <button type="submit" className={btnPrimary} disabled={busy}>
              {busy ? "Saving…" : reviseOf ? "Create next version" : "Create preset"}
            </button>
            {reviseOf && (
              <button
                type="button"
                className={btnSubtle}
                onClick={() => setReviseOf(null)}
              >
                Cancel
              </button>
            )}
          </div>
        </form>
      )}

      <div className={cardCls}>
        <h2 className="mb-4 text-lg font-medium text-gray-100">Presets</h2>
        {isLoading && <LoadingSpinner size="md" label="Loading presets..." />}
        {error && (
          <p className="text-sm text-red-400" role="alert">
            {errText(error)}
          </p>
        )}
        {presets && presets.length === 0 && (
          <p className="text-sm text-gray-400">
            No presets yet. A preset bundles the actor, model choices and media
            defaults a course should start from.
          </p>
        )}
        {presets && presets.length > 0 && (
          <ul className="divide-y divide-gray-800">
            {presets.map((p) => (
              <li key={p.id} className="py-3">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-gray-100">
                      {p.name}{" "}
                      <span className="text-xs text-gray-500">v{p.version}</span>
                    </p>
                    <p className="text-xs text-gray-500">
                      {p.description || "No description"}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      className={btnSubtle}
                      onClick={async () => {
                        setVersions(await listVersions(p.name));
                      }}
                    >
                      History
                    </button>
                    {canWrite && (
                      <button
                        type="button"
                        className={btnSubtle}
                        onClick={() => {
                          setReviseOf(p);
                          setDescription(p.description ?? "");
                          setActorId(p.payload.actor_id ?? "");
                          setRuntime(
                            p.payload.max_runtime_seconds != null
                              ? String(p.payload.max_runtime_seconds)
                              : "",
                          );
                          setAudience(p.payload.target_audience ?? "");
                          setLogoId(p.payload.branding?.logo_library_asset_id ?? "");
                          setLogoPolicy(p.payload.branding?.logo_policy ?? "");
                        }}
                      >
                        Revise
                      </button>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {versions && (
        <div className={cardCls}>
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-base font-medium text-gray-100">
              Version history — {versions[0]?.name}
            </h3>
            <button
              type="button"
              className={btnSubtle}
              onClick={() => setVersions(null)}
            >
              Close
            </button>
          </div>
          <ul className="divide-y divide-gray-800 text-sm">
            {versions.map((v) => (
              <li key={v.id} className="flex items-center justify-between py-2">
                <span className="text-gray-200">
                  v{v.version}
                  {v.is_active && (
                    <span className="ml-2 rounded bg-green-900/50 px-2 py-0.5 text-xs text-green-300">
                      current
                    </span>
                  )}
                </span>
                <span className="text-xs text-gray-500">
                  {new Date(v.created_at).toLocaleString()}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
