"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import useSWR from "swr";
import { apiClient } from "@/lib/api-client";
import { unwrapList } from "@/lib/unwrap";
import {
  assetDownloadPath,
  assetFilename,
  assetThumbnailPath,
  type MediaAssetLike,
} from "@/lib/media";

/**
 * Authenticated media loading for asset cards (WP-40 Task 1).
 *
 * The only route that serves asset bytes is
 * `GET /api/v1/assets/{id}/download` (assets.py:128), and it sits behind
 * `Depends(get_service_or_user)`. A browser will not attach an Authorization
 * header to `<img src>`, `<video src>` or `<a download>`, so the bytes have
 * to be fetched by script and handed to the element as an object URL. That
 * is the whole mechanism here.
 *
 * There is NO thumbnail route on this API, so an image card shows the
 * full-size original. To keep that honest, `useAssetObjectUrl` only fetches
 * when told to, and `AssetThumbnail` (AssetBrowser.tsx) only tells it to
 * once the card scrolls into view. Video and audio are never fetched for a
 * card at all -- they load on demand when the operator opens the preview.
 */

interface AssetObjectUrl {
  /** Object URL for the fetched bytes, or null while absent. */
  url: string | null;
  isLoading: boolean;
  error: string | null;
}

/**
 * Fetch an asset's bytes and expose them as an object URL.
 *
 * `enabled` gates the request entirely: nothing is fetched until it is true.
 * The URL is revoked on unmount and whenever the asset changes, so a long
 * scroll through the grid does not leak blobs.
 */
export function useAssetObjectUrl(
  assetId: string | null | undefined,
  enabled: boolean,
  /**
   * WP-45 Task 6(b). When set, fetch the width-limited thumbnail instead of the
   * full-size original. Card grids pass a width; anything that shows the asset
   * itself (the preview modal, the download) must not, because a thumbnail is
   * not the asset.
   */
  thumbnailWidth?: number,
): AssetObjectUrl {
  const [url, setUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const currentUrl = useRef<string | null>(null);

  useEffect(() => {
    if (!assetId || !enabled) return;

    let cancelled = false;
    setIsLoading(true);
    setError(null);

    const path =
      typeof thumbnailWidth === "number"
        ? assetThumbnailPath(assetId, thumbnailWidth)
        : assetDownloadPath(assetId);

    apiClient
      .blob(path)
      .then(({ blob }) => {
        if (cancelled) return;
        const objectUrl = URL.createObjectURL(blob);
        currentUrl.current = objectUrl;
        setUrl(objectUrl);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Could not load media");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
      if (currentUrl.current) {
        URL.revokeObjectURL(currentUrl.current);
        currentUrl.current = null;
      }
      setUrl(null);
    };
  }, [assetId, enabled, thumbnailWidth]);

  return { url, isLoading, error };
}

/**
 * Download an asset to the operator's machine.
 *
 * The proxy already sets `Content-Disposition: attachment`, but a plain
 * `<a href>` cannot reach it without a token, so the bytes are fetched here
 * and saved through a transient object URL. The filename comes from the
 * server's own Content-Disposition when present, else from the SeaweedFS
 * path.
 */
export function useAssetDownload(): {
  download: (asset: MediaAssetLike) => Promise<void>;
  downloadingId: string | null;
  error: string | null;
} {
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const download = useCallback(async (asset: MediaAssetLike): Promise<void> => {
    if (!asset?.id) return;
    setDownloadingId(asset.id);
    setError(null);
    try {
      const { blob, filename } = await apiClient.blob(assetDownloadPath(asset.id));
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = filename || assetFilename(asset);
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      /* Give the browser a tick to start the save before revoking. */
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 10_000);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Download failed");
    } finally {
      setDownloadingId(null);
    }
  }, []);

  return { download, downloadingId, error };
}

/**
 * True once the element has scrolled into (or near) the viewport.
 *
 * Without this, opening the Media Assets tab on the live project would pull
 * 16 full-size PNGs plus everything else in one burst. With it, the grid
 * fetches only what the operator can actually see.
 */
export function useInView<T extends Element>(
  ref: React.RefObject<T>,
  rootMargin = "200px",
): boolean {
  const [inView, setInView] = useState<boolean>(false);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    if (typeof IntersectionObserver === "undefined") {
      /* Old browser or a test environment: degrade to eager loading. */
      setInView(true);
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setInView(true);
            observer.disconnect();
          }
        }
      },
      { rootMargin },
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, [ref, rootMargin]);

  return inView;
}

/**
 * Map of `scene_id` -> `scene_index` for a project.
 *
 * WP-40 addendum. Asset cards need this to be distinguishable from one
 * another: every image asset of project c12fa967 has the SeaweedFS path
 * `/ivgs/images/{pid}/image.png`, so sixteen cards would all read
 * "image.png". `scene_id` is populated on all 36 scene-scoped assets, and
 * `scene_index` is what an operator actually recognises.
 *
 * Shares the SWR key `/api/v1/projects/{id}/scenes` with `useStoryboard`, so
 * on the storyboard page this costs no extra request. The route is a BARE
 * ARRAY (WP-38), hence `unwrapList`.
 */
export function useSceneIndexMap(
  projectId: string | null | undefined,
): Map<string, number> {
  const { data } = useSWR<{ id: string; scene_index: number }[]>(
    projectId ? `/api/v1/projects/${projectId}/scenes` : null,
    async (url: string) => {
      const response = await apiClient.get<unknown>(url);
      return unwrapList<{ id: string; scene_index: number }>(response.data);
    },
    { revalidateOnFocus: false, dedupingInterval: 30_000 },
  );

  return useMemo(() => {
    const map = new Map<string, number>();
    for (const scene of data ?? []) {
      if (scene && typeof scene.id === "string" && typeof scene.scene_index === "number") {
        map.set(scene.id, scene.scene_index);
      }
    }
    return map;
  }, [data]);
}
