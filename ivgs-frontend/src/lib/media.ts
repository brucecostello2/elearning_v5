/**
 * Asset media derivation (WP-40 Task 1).
 *
 * WHY THIS EXISTS. `AssetBrowser` built its `<img>` from
 * `asset.thumbnail_url || asset.url`. Neither field exists on the wire.
 *
 * `GET /api/v1/projects/{id}/assets` is `PaginatedResponse[AssetResponse]`
 * (assets.py:38) and `AssetResponse` (schemas/asset.py:27) sends exactly:
 *
 *   id, project_id, scene_id, asset_type, seaweedfs_fid, seaweedfs_path,
 *   mime_type, file_size_bytes, duration_seconds, language_code,
 *   generation_prompt_id, storage_tier, preserve_flag, content_hash,
 *   reference_count, created_at
 *
 * There is no `url`, no `thumbnail_url`, no `filename`, no `scene_label`,
 * no `generation_prompt` and no `quality_score`. The frontend's
 * `AssetResponse` interface declared five of those as optional and two as
 * required, so TypeScript never objected -- and `<img src={undefined}>`
 * renders an element with no `src` attribute, which issues no request at
 * all. That is the observed "Img: 0 of 121 requests" over 40 real assets:
 * not a failed load, an absent one.
 *
 * Same family as WP-35 (under-unwrapped envelope) and WP-38 (over-unwrapped
 * bare array): a type asserting a shape the wire does not have.
 *
 * Everything a card needs is DERIVABLE from what the API does send, which is
 * what this module does. The bytes come from the existing proxy route
 * `GET /api/v1/assets/{id}/download` (assets.py:128) -- verified live on
 * 2026-08-23: http 200, `content-type: image/png`, 641217 bytes.
 */

/** The fields of an asset this module needs. Structural, so both the full
 *  `AssetResponse` and a trimmed test fixture satisfy it. */
export interface MediaAssetLike {
  id: string;
  asset_type?: string | null;
  mime_type?: string | null;
  seaweedfs_path?: string | null;
  seaweedfs_fid?: string | null;
  file_size_bytes?: number | null;
  duration_seconds?: number | null;
  language_code?: string | null;
  created_at?: string | null;
}

/** How a card should present an asset, regardless of its `asset_type` label. */
export type MediaKind = "image" | "video" | "audio" | "other";

/** Extensions we can classify when `mime_type` is absent. */
const EXT_KIND: Record<string, MediaKind> = {
  png: "image", jpg: "image", jpeg: "image", gif: "image",
  webp: "image", bmp: "image", svg: "image",
  mp4: "video", mov: "video", webm: "video", mkv: "video", avi: "video",
  wav: "audio", mp3: "audio", flac: "audio", ogg: "audio", m4a: "audio",
};

/**
 * The route that serves an asset's bytes.
 *
 * Note the path: `/api/v1/assets/{id}/...`, NOT
 * `/api/v1/projects/{pid}/assets/{id}/...`. The asset-scoped router is
 * mounted at `/assets` (assets.py:33); only the LIST and UPLOAD routes are
 * project-scoped. `useAssets.regenerateAsset` had this wrong too.
 */
export function assetDownloadPath(assetId: string): string {
  return `/api/v1/assets/${assetId}/download`;
}

/** Filename from the SeaweedFS path, else a stable synthetic one. */
export function assetFilename(asset: MediaAssetLike | null | undefined): string {
  if (!asset) return "asset";
  const path = asset.seaweedfs_path;
  if (typeof path === "string" && path.length > 0) {
    const base = path.split("/").filter(Boolean).pop();
    if (base) return base;
  }
  const kind = asset.asset_type || "asset";
  const short = typeof asset.id === "string" ? asset.id.slice(0, 8) : "unknown";
  return `${kind}-${short}`;
}

/** Lowercase file extension of the stored object, or "" if undeterminable. */
export function assetExtension(asset: MediaAssetLike | null | undefined): string {
  const name = assetFilename(asset);
  const idx = name.lastIndexOf(".");
  if (idx <= 0 || idx === name.length - 1) return "";
  return name.slice(idx + 1).toLowerCase();
}

/**
 * How to render this asset.
 *
 * `mime_type` first because it is what the server actually stored and what
 * the download proxy will echo back. `asset_type` is a pipeline role, not a
 * media type -- the live project has `final_render`, `talking_head`,
 * `reference_clip` and `document` alongside `image`/`video`/`audio`, and the
 * card previously fell through to a bare "Asset" box for all four.
 */
export function assetMediaKind(asset: MediaAssetLike | null | undefined): MediaKind {
  if (!asset) return "other";

  const mime = typeof asset.mime_type === "string" ? asset.mime_type.toLowerCase() : "";
  if (mime.startsWith("image/")) return "image";
  if (mime.startsWith("video/")) return "video";
  if (mime.startsWith("audio/")) return "audio";

  const ext = assetExtension(asset);
  if (ext && EXT_KIND[ext]) return EXT_KIND[ext] as MediaKind;

  const type = typeof asset.asset_type === "string" ? asset.asset_type.toLowerCase() : "";
  if (type === "image" || type === "thumbnail") return "image";
  if (type === "audio") return "audio";
  if (
    type === "video" || type === "animation" || type === "talking_head" ||
    type === "final_render" || type === "draft" || type === "render" ||
    type === "reference_clip"
  ) {
    return "video";
  }

  return "other";
}

/** Human label for the asset's pipeline role ("final_render" -> "Final render"). */
export function assetTypeLabel(asset: MediaAssetLike | null | undefined): string {
  const type = asset?.asset_type;
  if (typeof type !== "string" || type.length === 0) return "Asset";
  const spaced = type.replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** Byte count as a short human string. Returns "—" when unknown. */
export function formatBytes(bytes: number | null | undefined): string {
  if (typeof bytes !== "number" || !Number.isFinite(bytes) || bytes < 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[unit]}`;
}

/**
 * Free-text haystack for the assets-page search box.
 *
 * The old filter searched `filename`, `scene_label` and `generation_prompt`
 * -- all three undefined -- so typing anything at all emptied the grid.
 */
export function assetSearchText(asset: MediaAssetLike | null | undefined): string {
  if (!asset) return "";
  return [
    assetFilename(asset),
    asset.asset_type ?? "",
    asset.mime_type ?? "",
    asset.language_code ?? "",
    asset.seaweedfs_path ?? "",
    asset.id ?? "",
  ]
    .join(" ")
    .toLowerCase();
}
