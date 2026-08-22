-- =====================================================================
-- WP-IVGS-0 finding F6 — corrective SQL for the live `ivgs` database
--
-- HELD FOR THE OPERATOR. NOT EXECUTED. Authored 2026-08-22 by the
-- WP-IVGS-0 session under the operator ruling of the same day.
--
-- node-01 (192.168.1.90), container ivgs-postgres, database `ivgs`.
-- =====================================================================
--
-- WHY
-- ---
-- The two seeded prompts that Stage 1 and Stage 2 actually fetch bind
-- {{ narration_text }}. The workers bind `transcript_text` (Stage 1,
-- stage1_transcript._render_user_prompt) and `combined_transcript`
-- (Stage 2, stage2_storyboard._render_user_prompt). Jinja renders an
-- unbound name as EMPTY, so with these rows active the transcript never
-- reaches the model — the pipeline runs and produces confident nonsense
-- from nothing.
--
-- IVGS-0.4 fixed WHICH prompt Stage 1 receives. This fixes what that
-- prompt renders to. Both are needed.
--
-- The seed FILES are already corrected in git (commit for finding F6).
-- Re-running `python -m app.scripts.seed_prompts` will NOT repair these
-- rows: seed_prompts.py skips any type that already has an active global
-- prompt (seed_prompts.py:52-62). The database must be corrected
-- explicitly, which is what this file does.
--
-- WHAT WAS MEASURED (read-only, 2026-08-22)
-- -----------------------------------------
--   prompts: 10 rows, one active GLOBAL per type.
--   No project-level or scene-level overrides exist anywhere.
--   Three rows contain the literal {{ narration_text }}:
--     transcript_refinement  6a922c1e-e256-4eee-910c-0a1173827f46  v1
--     storyboard_generation  63835b0d-c2ba-4e81-8786-a810aa884348  v1
--     translation            (LEAVE ALONE — see below)
--   Both target rows are md5-identical to the pre-fix seed files and
--   were created by `system` at 2026-05-23 15:42:45+00. They are
--   untouched seed data: no operator has hand-edited them.
--
--   translation is NOT corrected. narration_text is that template's own
--   correct variable (it is the text being translated). No worker fetches
--   it today; when one does, it brings its own bind context.
--
-- APPROACH
-- --------
-- A new version (v2) is inserted and v1 is deactivated — the same thing
-- PromptService.create_prompt does (prompt_service.py:162-223). This
-- preserves the audit history the `version` column exists for, and lets
-- you roll back through the existing restore-version path rather than
-- through a database edit. Section B is an in-place UPDATE alternative if
-- you would rather not add rows; run ONE of A or B, not both.
--
-- The md5 guard means this file is safe to run exactly once against the
-- state that was measured, and refuses to run against anything else.
--
-- HOW TO RUN (operator, node-01)
-- ------------------------------
--   Take a backup first, then:
--     docker exec -i ivgs-postgres psql -U ivgs -d ivgs -v ON_ERROR_STOP=1 \
--       < /opt/ivgs/dev/workpackages/WP-IVGS-0-F6-corrective-prompts.sql
--
--   The whole file is one transaction. Any guard failure aborts it and
--   nothing changes. Section C verifies and is read-only.
--
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- GUARDS — abort unless the database is in exactly the measured state.
-- ---------------------------------------------------------------------

DO $$
DECLARE
    n integer;
BEGIN
    -- The two target rows must still be the untouched seed text.
    SELECT count(*) INTO n
    FROM prompts
    WHERE id = '6a922c1e-e256-4eee-910c-0a1173827f46'
      AND prompt_type = 'transcript_refinement'
      AND is_active
      AND md5(prompt_text) = '20d0983d0bd3e550a02209d7b4388af7';
    IF n <> 1 THEN
        RAISE EXCEPTION
            'GUARD FAILED: the active transcript_refinement prompt is not '
            'the untouched seed row measured on 2026-08-22. Someone has '
            'edited it. Re-inspect before correcting anything.';
    END IF;

    SELECT count(*) INTO n
    FROM prompts
    WHERE id = '63835b0d-c2ba-4e81-8786-a810aa884348'
      AND prompt_type = 'storyboard_generation'
      AND is_active
      AND md5(prompt_text) = '397998b23f3dd3754c6127e0d8ea8e70';
    IF n <> 1 THEN
        RAISE EXCEPTION
            'GUARD FAILED: the active storyboard_generation prompt is not '
            'the untouched seed row measured on 2026-08-22.';
    END IF;

    -- No project- or scene-level overrides were present when this was
    -- authored. If any exist now they may carry the same defect and this
    -- file does not address them.
    SELECT count(*) INTO n
    FROM prompts
    WHERE prompt_type IN ('transcript_refinement', 'storyboard_generation')
      AND (project_id IS NOT NULL OR scene_id IS NOT NULL);
    IF n <> 0 THEN
        RAISE EXCEPTION
            'GUARD FAILED: % project/scene-level override(s) now exist for '
            'the two affected types. They may carry the same {{ narration_text }} '
            'defect. Inspect them before running this.', n;
    END IF;
END $$;

-- =====================================================================
-- SECTION A — new version, old version deactivated (RECOMMENDED)
-- =====================================================================

UPDATE prompts
   SET is_active = false
 WHERE id IN (
     '6a922c1e-e256-4eee-910c-0a1173827f46',
     '63835b0d-c2ba-4e81-8786-a810aa884348'
 );

INSERT INTO prompts (
    project_id, scene_id, prompt_type, prompt_text,
    version, is_active, is_library_template, created_by, change_note
)
SELECT
    NULL, NULL, p.prompt_type,
    replace(
        p.prompt_text,
        '{{ narration_text }}',
        CASE p.prompt_type::text
            WHEN 'transcript_refinement' THEN '{{ transcript_text }}'
            WHEN 'storyboard_generation' THEN '{{ combined_transcript }}'
        END
    ),
    (SELECT coalesce(max(version), 0) + 1
       FROM prompts q
      WHERE q.prompt_type = p.prompt_type
        AND q.project_id IS NULL
        AND q.scene_id IS NULL),
    true,
    p.is_library_template,
    'WP-IVGS-0 F6',
    'WP-IVGS-0 finding F6: bind the variable the worker actually passes. '
    'Stage 1 binds transcript_text and Stage 2 binds combined_transcript; '
    '{{ narration_text }} rendered empty, so the transcript never reached '
    'the model. Text is otherwise byte-identical to v1.'
FROM prompts p
WHERE p.id IN (
    '6a922c1e-e256-4eee-910c-0a1173827f46',
    '63835b0d-c2ba-4e81-8786-a810aa884348'
);

-- =====================================================================
-- SECTION B — in-place UPDATE (ALTERNATIVE; do NOT run with Section A)
-- =====================================================================
-- Keeps the row count and the version numbers, loses the before-text.
-- Uncomment only if you have deliberately chosen this over Section A.
--
-- UPDATE prompts
--    SET prompt_text = replace(prompt_text, '{{ narration_text }}',
--                              '{{ transcript_text }}')
--  WHERE id = '6a922c1e-e256-4eee-910c-0a1173827f46';
--
-- UPDATE prompts
--    SET prompt_text = replace(prompt_text, '{{ narration_text }}',
--                              '{{ combined_transcript }}')
--  WHERE id = '63835b0d-c2ba-4e81-8786-a810aa884348';

-- =====================================================================
-- SECTION C — post-conditions. Aborts the transaction if wrong.
-- =====================================================================

DO $$
DECLARE
    n integer;
BEGIN
    -- Exactly one active global prompt per affected type, and neither
    -- carries the old variable.
    SELECT count(*) INTO n
    FROM prompts
    WHERE prompt_type IN ('transcript_refinement', 'storyboard_generation')
      AND is_active
      AND project_id IS NULL AND scene_id IS NULL;
    IF n <> 2 THEN
        RAISE EXCEPTION 'POST-CHECK FAILED: expected 2 active globals, got %', n;
    END IF;

    SELECT count(*) INTO n
    FROM prompts
    WHERE prompt_type IN ('transcript_refinement', 'storyboard_generation')
      AND is_active
      AND prompt_text LIKE '%{{ narration_text }}%';
    IF n <> 0 THEN
        RAISE EXCEPTION
            'POST-CHECK FAILED: % active prompt(s) still bind narration_text', n;
    END IF;

    SELECT count(*) INTO n
    FROM prompts
    WHERE is_active
      AND ((prompt_type = 'transcript_refinement'
            AND prompt_text LIKE '%{{ transcript_text }}%')
        OR (prompt_type = 'storyboard_generation'
            AND prompt_text LIKE '%{{ combined_transcript }}%'));
    IF n <> 2 THEN
        RAISE EXCEPTION
            'POST-CHECK FAILED: expected 2 corrected prompts, got %', n;
    END IF;

    -- translation must be untouched.
    SELECT count(*) INTO n
    FROM prompts
    WHERE prompt_type = 'translation'
      AND prompt_text LIKE '%{{ narration_text }}%';
    IF n <> 1 THEN
        RAISE EXCEPTION
            'POST-CHECK FAILED: the translation prompt was modified. '
            'It must not be — narration_text is its own correct variable.';
    END IF;

    RAISE NOTICE 'WP-IVGS-0 F6: post-checks passed.';
END $$;

-- Review this before committing. Expect two v1 rows inactive and two v2
-- rows active, with the corrected variable names.
SELECT prompt_type, version, is_active, created_by,
       substring(prompt_text from '\{\{ [a-z_]*transcript[a-z_]* \}\}')
           AS bound_variable
  FROM prompts
 WHERE prompt_type IN ('transcript_refinement', 'storyboard_generation')
 ORDER BY prompt_type, version;

COMMIT;

-- =====================================================================
-- AFTER RUNNING
-- =====================================================================
-- Nothing needs restarting: prompts are read per job, not cached at
-- worker start. The next pipeline run picks up v2.
--
-- To confirm end to end, trigger one project and check that the Stage 1
-- request body carries the transcript text rather than an empty
-- "INPUT TRANSCRIPT:" block.
-- =====================================================================
