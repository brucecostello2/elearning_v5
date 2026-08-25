/**
 * AD-09 production content library types — MIRROR of
 * ivgs-api/app/schemas/library.py. Nothing here is aspirational.
 *
 * THE WP-40/43 RULE, APPLIED. That defect family — a type declaring a field the
 * API never sends, so a component reads `undefined` and renders a blank where a
 * value belongs — reached thirteen instances. The rule taken from it: a field
 * exists in this file only if the API demonstrably populates it, verified
 * against a live response, not against the addendum.
 *
 * DELIBERATELY ABSENT, so reaching for one is a COMPILE ERROR rather than a
 * blank box in front of the operator:
 *
 *   - `preset_drift`            AD-09.14 Q8 is UNRULED; nothing computes it.
 *   - presenter_* scene fields  WP-56 Task 3 stopped; see the WP-56 report.
 *   - `logo_enabled` on scenes  same.
 *   - intro/outro templates     AD-09 sequencing item 5, out of scope.
 *   - courses / fork depth      AD-09 sequencing item 7, out of scope.
 */

export const LIBRARY_ASSET_KINDS = [
  "logo",
  "video_clip",
  "audio_clip",
  "music_bed",
  "reference_clip",
  "reference_image",
  "font",
  "document",
] as const;
export type LibraryAssetKind = (typeof LIBRARY_ASSET_KINDS)[number];

export const OWNER_SCOPES = ["global", "user"] as const;
export type OwnerScope = (typeof OWNER_SCOPES)[number];

export const PRESENTER_ORIENTATIONS = ["landscape", "portrait"] as const;
export type PresenterOrientation = (typeof PRESENTER_ORIENTATIONS)[number];

export const LOGO_POLICIES = ["always", "never", "per_scene"] as const;
export type LogoPolicy = (typeof LOGO_POLICIES)[number];

/** Which project-side `assets.asset_type` each library kind may be referenced
 *  as. Mirrors KIND_TO_ASSET_TYPE in app/services/library_service.py. The two
 *  vocabularies are DIFFERENT; the picker uses this so the operator is never
 *  offered a combination the API will refuse. */
export const KIND_TO_ASSET_TYPE: Record<LibraryAssetKind, readonly string[]> = {
  logo: ["image"],
  video_clip: ["video"],
  audio_clip: ["audio"],
  music_bed: ["audio"],
  reference_clip: ["reference_clip", "video", "talking_head"],
  reference_image: ["image"],
  font: ["document"],
  document: ["document"],
};

export interface LibraryAsset {
  id: string;
  kind: LibraryAssetKind;
  name: string;
  description: string | null;
  seaweedfs_fid: string | null;
  seaweedfs_path: string | null;
  mime_type: string | null;
  file_size_bytes: number | null;
  duration_seconds: number | null;
  content_hash: string | null;
  tags: string[] | null;
  owner_scope: OwnerScope;
  created_by: string | null;
  /** Non-null means RETIRED in favour of that asset. Library assets are never
   *  hard-deleted while referenced (AD-09.4.2). */
  superseded_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface LibraryAssetUploadResult extends LibraryAsset {
  /** True when these exact bytes were already in this scope. Without it a
   *  dedup hit and a fresh upload are indistinguishable replies. */
  was_deduplicated: boolean;
}

export interface Actor {
  id: string;
  name: string;
  description: string | null;
  reference_clip_id: string | null;
  reference_image_id: string | null;
  voice_profile: Record<string, unknown> | null;
  /** ⚠ AD-09.14 open question 1 is OPEN. The MagiHuman parameter set that
   *  reproduces an identity is operator knowledge recorded nowhere in the
   *  repository. Opaque, per-engine, unvalidated on both sides. */
  engine_bindings: Record<string, unknown> | null;
  default_orientation: PresenterOrientation;
  /** The AD-01 model this identity was established against. Changing it is an
   *  IDENTITY CHANGE (AD-09.4.3) and the UI must say so. */
  certified_model_id: string | null;
  owner_scope: OwnerScope;
  is_active: boolean;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface ActorCreatePayload {
  name: string;
  description?: string | null;
  reference_clip_id?: string | null;
  reference_image_id?: string | null;
  voice_profile?: Record<string, unknown> | null;
  engine_bindings?: Record<string, unknown> | null;
  default_orientation?: PresenterOrientation;
  certified_model_id?: string | null;
  owner_scope?: OwnerScope;
}

export type ActorUpdatePayload = Partial<ActorCreatePayload> & {
  is_active?: boolean;
};

export interface PresetModelSelection {
  stage: string;
  tier: string;
  model_id: string;
}

export interface PresetMediaDefaults {
  media_type?: string | null;
  resolution_tier?: string | null;
  framerate?: number | null;
}

/** ⚠ RECORDED, NOT RENDERED. Every field here is stored and returned, and
 *  NOTHING in the render path reads any of it — WP-56 Task 3 stopped on the
 *  finding that the presenter/logo overlay chain is broken at three of its four
 *  links. The preset editor labels this block; do not remove that label until
 *  the render path lands. */
export interface PresetBranding {
  logo_library_asset_id?: string | null;
  logo_policy?: LogoPolicy | null;
  brand_colours?: Record<string, string> | null;
  typography?: Record<string, unknown> | null;
}

export interface PresetPayload {
  actor_id?: string | null;
  model_selections?: PresetModelSelection[];
  media_defaults?: PresetMediaDefaults | null;
  branding?: PresetBranding | null;
  max_runtime_seconds?: number | null;
  target_audience?: string | null;
}

export interface Preset {
  id: string;
  name: string;
  description: string | null;
  version: number;
  payload: PresetPayload;
  is_active: boolean;
  owner_scope: OwnerScope;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

/** Itemised on purpose. A preset apply that reports plain success while
 *  silently skipping half the bundle is the AD-09.3 stub family. */
export interface PresetApplyResult {
  project_id: string;
  preset_id: string;
  preset_version: number;
  applied: string[];
  recorded_not_applied: string[];
}

export interface LibraryReferencePayload {
  library_asset_id: string;
  asset_type: string;
  scene_id?: string | null;
  language_code?: string | null;
}
