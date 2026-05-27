# BUG-007 Investigation: review_notes Usage

**Date:** 2026-05-27
**Questions to Answer:**
1. Is review_notes mentioned in IVGS v5 functional spec?
2. Does Next.js frontend have UI input for review_notes?
3. What's the source of review_notes value in service code?

## Question 1: Functional Specification Check

Spec files found:
```
/home/ubuntu/instructional_video_generation_system_spec.pdf
/home/ubuntu/instructional_video_generation_system_spec_v2.pdf
/home/ubuntu/instructional_video_spec_v2_sections10to15.pdf
/home/ubuntu/instructional_video_spec_v2_sections9to15.pdf
/home/ubuntu/instructional_video_generation_system_spec_v2_complete.pdf
/home/ubuntu/Uploads/instructional_video_generation_system_spec_v3_simplified.pdf
/home/ubuntu/Uploads/instructional_video_generation_system_spec_v3_simplified (1).pdf
/home/ubuntu/Uploads/ivgs_v4_prerequisites_nodespecific.pdf
/home/ubuntu/Uploads/instructional_video_generation_system_spec_v3_simplified (2).pdf
/home/ubuntu/Uploads/ivgs_v4_prerequisites_nodespecific (1).pdf
```

## Question 2: Frontend UI Check

Frontend not available in workspace.

## Question 3: Service Code Source Analysis

### All review_notes references in codebase:
```
app/schemas/quality.py:26:    review_notes: Optional[str] = None
app/services/quality_service.py:172:        score.review_notes = notes
app/services/quality_service.py:212:        score.review_notes = notes
```

### Context around each reference:
```
app/schemas/quality.py-21-    safety_score: Optional[float] = None
app/schemas/quality.py-22-    scoring_details: Optional[Dict[str, Any]] = None
app/schemas/quality.py-23-    decision: str
app/schemas/quality.py-24-    reviewed_by: Optional[str] = None
app/schemas/quality.py-25-    reviewed_at: Optional[datetime] = None
app/schemas/quality.py:26:    review_notes: Optional[str] = None
app/schemas/quality.py-27-    created_at: datetime
app/schemas/quality.py-28-
app/schemas/quality.py-29-    model_config = ConfigDict(from_attributes=True)
app/schemas/quality.py-30-
app/schemas/quality.py-31-
--
app/services/quality_service.py-167-            )
app/services/quality_service.py-168-
app/services/quality_service.py-169-        score.decision = "approved"
app/services/quality_service.py-170-        score.reviewed_by = reviewed_by
app/services/quality_service.py-171-        score.reviewed_at = datetime.now(timezone.utc)
app/services/quality_service.py:172:        score.review_notes = notes
app/services/quality_service.py-173-
app/services/quality_service.py-174-        await self.db.commit()
app/services/quality_service.py-175-        await self.db.refresh(score)
app/services/quality_service.py-176-
app/services/quality_service.py-177-        logger.info(
--
app/services/quality_service.py-207-            )
app/services/quality_service.py-208-
app/services/quality_service.py-209-        score.decision = "rejected"
app/services/quality_service.py-210-        score.reviewed_by = reviewed_by
app/services/quality_service.py-211-        score.reviewed_at = datetime.now(timezone.utc)
app/services/quality_service.py:212:        score.review_notes = notes
app/services/quality_service.py-213-
app/services/quality_service.py-214-        await self.db.commit()
app/services/quality_service.py-215-        await self.db.refresh(score)
app/services/quality_service.py-216-
app/services/quality_service.py-217-        logger.info(
```

## Analysis

### Finding 1: Spec Check
No direct `review_notes` mention found in available spec PDFs. However, the quality review workflow (approve/reject) is clearly part of the spec.

### Finding 2: Frontend
Not available in workspace for verification.

### Finding 3: Service Code Source Analysis

**`review_notes` is actively used in 3 locations:**

| File | Line | Usage | Type |
|------|------|-------|------|
| `app/schemas/quality.py:26` | `QualityScoreResponse.review_notes` | Response field | Pydantic output |
| `app/schemas/quality.py:53,63` | `QualityApproveRequest.notes` / `QualityRejectRequest.notes` | Request field | Pydantic input |
| `app/services/quality_service.py:172` | `score.review_notes = notes` | ORM write (approve) | Service logic |
| `app/services/quality_service.py:212` | `score.review_notes = notes` | ORM write (reject) | Service logic |

**Data flow:**
1. User submits `notes` in approve/reject request body (`QualityApproveRequest` / `QualityRejectRequest`)
2. API endpoint passes `notes` to `QualityService.approve_score()` / `reject_score()`
3. Service assigns `score.review_notes = notes` on the ORM object
4. ORM commit fails silently or raises AttributeError because `review_notes` doesn't exist in model
5. Response serialization via `QualityScoreResponse.review_notes` would also fail

**Current model has:** `reviewed_by`, `reviewed_at` — but NOT `review_notes`

### Conclusion

`review_notes` is a **designed feature** with:
- ✅ Request schema (input from user)
- ✅ Response schema (output to user)
- ✅ Service implementation (2 code paths: approve + reject)
- ❌ Missing ORM column

This is clearly a feature that was designed and partially implemented but the model column was forgotten.

### Recommendation: **Option A — Add column**

Add `review_notes` to `AssetQualityScore` model + create migration:
```python
# In app/models/quality_score.py
review_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
```

This completes the feature implementation. Removing the references (Option B) would break a working API contract and require changes to 3 files.

---
**Investigation complete. Recommendation: Option A (add column) — feature was designed, just missing the model column.**
