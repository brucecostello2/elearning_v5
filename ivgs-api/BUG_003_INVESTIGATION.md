# BUG-003 Investigation: scene_count References Audit

**Date:** 2026-05-27
**Operator Request:** Audit whether scene_count is referenced downstream before applying fix.

## 1. Pydantic Response Models (app/api/v1/manifests.py)
```
app/api/v1/manifests.py:57:    scene_count: int
app/api/v1/manifests.py:100:                "scene_count, created_at, locked_at "
app/api/v1/manifests.py:121:        scene_count=row.scene_count,
app/api/v1/manifests.py:227:            "(id, job_id, status, timeline_json, total_duration_ms, scene_count, created_at) "
app/api/v1/manifests.py:229:            ":scene_count, :created_at)"
app/api/v1/manifests.py:236:            "scene_count": len(scenes),
app/api/v1/manifests.py:248:        scene_count=len(scenes),
app/schemas/project.py:83:    Includes computed fields: scene_count, total_duration_estimate_seconds,
app/schemas/project.py:93:    scene_count: int = 0
app/services/project_service.py:315:        scene_count = len(project.scenes) if project.scenes else 0
app/services/project_service.py:367:            scene_count=scene_count,
```

## 2. Schemas Directory
```
```

## 3. Models Directory
```
No matches in app/models/
```

## 4. Services Directory
```
```

## 5. Tests Directory
```
tests/test_projects.py:37:        assert data["scene_count"] == 0
tests/test_bug_003_manifest_field_names.py:6:  - SQL references ``scene_count`` → column does not exist
tests/test_bug_003_manifest_field_names.py:23:    reason="BUG-003: manifests.py uses timeline_json/scene_count/created_at — columns don't exist",
tests/test_bug_003_manifest_field_names.py:95:    reason="BUG-003: manifest/generate INSERT uses timeline_json/scene_count/created_at",
tests/test_bug_003_manifest_field_names.py:105:    ``scene_count`` — columns that don't exist.
tests/test_bug_003_manifest_field_names.py:158:        "BUG-003: INSERT references timeline_json/scene_count/created_at."
```

## 6. Frontend Check
Frontend not found in workspace.

## 7. Analysis & Recommendation


### Findings

**scene_count references breakdown:**

| Location | Context | Related to composition_manifests? |
|----------|---------|-----------------------------------|
| `app/api/v1/manifests.py` (7 refs) | ManifestResponse Pydantic model + raw SQL | ✅ YES — this is the bug |
| `app/schemas/project.py` (2 refs) | ProjectResponse.scene_count computed field | ❌ NO — different feature (project scene count) |
| `app/services/project_service.py` (2 refs) | Computes len(project.scenes) | ❌ NO — different feature |
| `tests/test_projects.py` (1 ref) | Asserts project response has scene_count | ❌ NO — tests ProjectResponse |

### Conclusion

`scene_count` in the `ManifestResponse` Pydantic schema (`manifests.py:57`) is **only consumed within manifests.py itself**. It is NOT referenced by:
- Other API endpoints
- Services
- Models
- The project response `scene_count` is a different, unrelated computed field

**Frontend:** Not available in workspace for verification, but since `ManifestResponse` is the sole API contract, the field name matters for frontend consumers.

### Recommendation

**Preserve the `scene_count` field in `ManifestResponse`** to maintain API contract stability, but **compute it from the timeline JSON** instead of a non-existent DB column:

```python
# In ManifestResponse construction:
scene_count = len(timeline.get("scenes", [])) if isinstance(timeline, dict) else 0
```

This approach:
1. Keeps the API response shape unchanged (frontend-safe)
2. Removes dependency on non-existent `scene_count` column
3. Computes from actual data (timeline JSON)

---
**Investigation complete. Recommendation: Compute scene_count from timeline JSON.**
