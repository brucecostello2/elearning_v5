"use client";

import React, { useMemo, useRef } from "react";
import { useAssets } from "@/hooks/useAssets";
import type { Asset } from "@/types/api";
import { assetMediaKind } from "@/lib/media";
import { useAssetObjectUrl, useInView } from "@/hooks/useAssetMedia";

/**
 * The generated image for a storyboard scene.
 *
 * WP-40 addendum. `SceneCard` and `SceneEditModal` rendered
 * `<img src={scene.thumbnail_url}>`. **`thumbnail_url` does not exist
 * anywhere in `ivgs-api`** — a grep of the whole API tree for the identifier
 * returns nothing, and the live scenes payload has exactly nine keys:
 * created_at, duration_seconds, id, media_type, narration_text, project_id,
 * scene_index, updated_at, visual_description. Both sites were `&&`-guarded,
 * so they degraded to an emoji rather than crashing — but they could never
 * have shown a picture, on any project, ever.
 *
 * A scene thumbnail IS derivable, and from real data: `assets.scene_id` is
 * populated on all 36 scene-scoped assets of project c12fa967 (16 images, 18
 * audio, 2 video). The scene's image asset is the thumbnail.
 *
 * The asset list is fetched through `useAssets`, which shares one SWR key per
 * project — eighteen cards cost one request, not eighteen. The bytes are then
 * fetched per card, but only once the card scrolls into view, because there is
 * no thumbnail route and each image is the ~600 KB original.
 */

interface SceneThumbnailProps {
  projectId: string;
  sceneId: string;
  sceneIndex: number;
  /** Rendered when the scene has no image asset, or its bytes fail to load. */
  fallback: React.ReactNode;
  className?: string;
}

export default function SceneThumbnail({
  projectId,
  sceneId,
  sceneIndex,
  fallback,
  className = "w-full h-full object-cover",
}: SceneThumbnailProps): React.ReactElement {
  const containerRef = useRef<HTMLDivElement>(null);
  const inView = useInView(containerRef);
  const { assets } = useAssets(projectId);

  /**
   * The scene's image. Preferred over its video: a still is what a card
   * wants, and a video asset would download megabytes to show one frame.
   */
  const image = useMemo<Asset | null>(() => {
    if (!Array.isArray(assets)) return null;
    return (
      assets.find(
        (a: Asset) => a.scene_id === sceneId && assetMediaKind(a) === "image",
      ) ?? null
    );
  }, [assets, sceneId]);

  const { url, error } = useAssetObjectUrl(image?.id, Boolean(image) && inView);

  return (
    <div ref={containerRef} className="w-full h-full">
      {url && !error ? (
        <img
          src={url}
          alt={`Scene ${sceneIndex + 1}`}
          className={className}
        />
      ) : (
        <div className="w-full h-full flex items-center justify-center">
          {fallback}
        </div>
      )}
    </div>
  );
}
