"use client";

import React from "react";
import { useParams } from "next/navigation";
import Link from "next/link";

import ProjectModelsPanel from "@/components/models/ProjectModelsPanel";

/**
 * WP-66 Task 3 — the Models tab.
 *
 * The middle of a capability whose two ends were already complete. Models are
 * certified in MBCP and land in IVGS as CANDIDATE rows; an admin approves them
 * and (WP-65) fetches their weights; and dispatch resolves a per-scene or
 * per-project selection at render time. There was no way for a user to make
 * that selection: `grep -rn "selections" ivgs-frontend/src` returned a preset
 * type and an unrelated storyboard handler.
 *
 * READ-ONLY FOR VIEWERS BY CONSTRUCTION, not by a role check here: every write
 * this page can make goes through `PUT /projects/{id}/model-selections`, which
 * is behind `require_operator_or_admin`. A viewer sees the bindings and their
 * provenance and gets a 422/403 from the API if they somehow post — the same
 * arrangement the Model Store admin page uses.
 */
export default function ProjectModelsPage(): React.ReactElement {
  const params = useParams();
  const projectId = params.id as string;

  return (
    <div className="space-y-4">
      <ProjectModelsPanel projectId={projectId} />

      <div className="rounded-md border border-gray-200 dark:border-gray-700 p-3 text-xs text-gray-600 dark:text-gray-400">
        A model that is certified but cannot yet run is listed here and
        disabled, with the reason — there are three different ones and they need
        three different actions. An admin resolves them from{" "}
        <Link
          href="/admin/models"
          className="text-blue-600 dark:text-blue-400 hover:underline"
        >
          Admin → Models
        </Link>
        .
      </div>
    </div>
  );
}
