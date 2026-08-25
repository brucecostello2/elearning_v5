-- =====================================================================
-- WP-44-QUALITY — corrective SQL: teach the LIVE storyboard prompt the
-- rules this week's runs paid for.
--
-- HELD FOR THE OPERATOR. NOT EXECUTED. Authored 2026-08-26 by the
-- WP-44-QUALITY session.
--
-- node-01 (192.168.1.90), container ivgs-postgres, database `ivgs`.
-- =====================================================================
--
-- WHY THIS FILE EXISTS AT ALL
-- ---------------------------
-- WP-44 Task 4 corrects the storyboard templates. Two of the three live in
-- git and ship with an image:
--   ivgs-workers/prompts/stage2_system.j2   (worker-side system prompt)
--   ivgs-workers/prompts/stage2_user.j2     (worker-side user prompt)
-- The third is a ROW IN THE DATABASE. Stage 2 fetches the active global
-- `storyboard_generation` prompt from the API, and that row is what the model
-- actually receives. Correcting the seed FILE does not change it:
-- `seed_prompts.py` skips any type that already has an active global prompt
-- (seed_prompts.py:52-62). The row must be corrected explicitly.
--
-- This is the same situation, and the same remedy, as
-- `WP-IVGS-0-F6-corrective-prompts.sql` — which is how the currently active
-- v2 row came to exist.
--
-- WHAT IT CORRECTS (the four rules, and what each one cost)
-- --------------------------------------------------------
-- (a) NO TEXT IN THE VISUAL. The v2 row says only "Visual descriptions should
--     be detailed enough for AI image generation". The reference project's
--     scene 0 asked for "a whiteboard with a multiplication problem written on
--     it, such as 23 x 14" and FLUX produced a whiteboard reading "2? x
--     23.14"; scene 2 asked for calculations "appearing on screen" and got
--     "12 + 44 = 67 + 5" and "3 + 4 = 7 = 8". Sixteen images, none salvageable
--     by regeneration.
-- (b) media_type "animation" ONLY for scenes containing a character. The v2
--     row says the opposite in as many words: 'Use "animation" for data
--     visualizations, flowcharts, and step-by-step processes'. Eleven of the
--     reference project's eighteen scenes were typed `animation` on that
--     instruction, and every one of them is an equation card with no subject
--     in it. WP-44 Task 5 now refuses those scenes by name
--     (WanAnimateInputError), so leaving this row as it is converts sixteen
--     bad images into eleven failed scenes.
-- (c) Narration self-consistency. The reference storyboard's own narration
--     reads "we should add 92 and 230 ... but that was also incorrect" and
--     "this gives us 260, but we wrote it as 640 in the previous step, which
--     is incorrect" — a script arguing with a draft the audience never saw.
-- (d) Durations must sum to the runtime. The reference project's target is
--     300 s; its eighteen scenes sum to 190 s (63%). The v2 row's only
--     instruction is a parenthetical "(sum should approximate total runtime)".
--
-- WHAT WAS MEASURED (read-only, 2026-08-26, on the live database)
-- ---------------------------------------------------------------
--   prompt_type = 'storyboard_generation':
--     63835b0d-c2ba-4e81-8786-a810aa884348  v1  active=false
--     19c8197a-7809-4777-92cd-ea684edee3cf  v2  active=TRUE   md5 03b91dd5…
--   No project-level or scene-level storyboard overrides exist (0 rows).
--   prompt_type = 'animation_generation': 1 active global row.
--
-- APPROACH
-- --------
-- A new version is INSERTED and the current one deactivated — what
-- PromptService.create_prompt does. Nothing is deleted and nothing is
-- overwritten, so the existing restore-version path is the rollback.
--
-- Section A  — storyboard_generation v3. This is the one Stage 2 consumes.
-- Section B  — animation_generation v2. OPTIONAL; no worker fetches this type
--              today, but the Prompts UI displays it to operators and the v1
--              text teaches exactly the rejected idea of what "animation" is
--              ("animated diagram or visualization … Remotion component
--              specification format").
-- Section C  — verification. Read-only.
--
-- The md5 guards mean this file is safe to run exactly once against the state
-- that was measured, and refuse to run against anything else. The whole file
-- is one transaction: any guard failure aborts it and nothing changes.
--
-- HOW TO RUN (operator, node-01)
-- ------------------------------
--   Back up first, then:
--     docker exec -i ivgs-postgres psql -U ivgs -d ivgs -v ON_ERROR_STOP=1 \
--       < /opt/ivgs/dev/workpackages/WP-44-storyboard-prompt-v3.sql
--
--   To run Section A only, delete Section B before running.
--
-- ROLLBACK
-- --------
--   UPDATE prompts SET is_active = false
--    WHERE prompt_type = 'storyboard_generation' AND version = 3;
--   UPDATE prompts SET is_active = true
--    WHERE id = '19c8197a-7809-4777-92cd-ea684edee3cf';
--   (and the mirror of that for Section B if it was run)
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- GUARDS — abort unless the database is in exactly the measured state.
-- ---------------------------------------------------------------------

DO $guard$
DECLARE
    n integer;
BEGIN
    SELECT count(*) INTO n
    FROM prompts
    WHERE id = '19c8197a-7809-4777-92cd-ea684edee3cf'
      AND prompt_type = 'storyboard_generation'
      AND is_active
      AND version = 2
      AND md5(prompt_text) = '03b91dd57e98c75477bf44efdae1f73e';
    IF n <> 1 THEN
        RAISE EXCEPTION
            'GUARD FAILED: the active storyboard_generation prompt is not the '
            'v2 row measured on 2026-08-26. Someone has edited it, or a newer '
            'version exists. Re-inspect before correcting anything.';
    END IF;

    SELECT count(*) INTO n
    FROM prompts
    WHERE prompt_type = 'storyboard_generation'
      AND (project_id IS NOT NULL OR scene_id IS NOT NULL);
    IF n <> 0 THEN
        RAISE EXCEPTION
            'GUARD FAILED: % project/scene-level storyboard override(s) now '
            'exist. They carry the same defects and this file does not '
            'address them. Inspect them first.', n;
    END IF;

    SELECT count(*) INTO n
    FROM prompts
    WHERE prompt_type = 'storyboard_generation' AND version >= 3;
    IF n <> 0 THEN
        RAISE EXCEPTION
            'GUARD FAILED: a storyboard_generation v3 or later already exists. '
            'This file has probably already been run.';
    END IF;
END $guard$;

-- =====================================================================
-- SECTION A — storyboard_generation v3  (the row Stage 2 consumes)
-- =====================================================================

UPDATE prompts
   SET is_active = false
 WHERE prompt_type = 'storyboard_generation'
   AND project_id IS NULL
   AND scene_id IS NULL
   AND is_active;

INSERT INTO prompts (
    project_id, scene_id, prompt_type, prompt_text, version,
    is_active, is_library_template, created_by, change_note
) VALUES (
    NULL, NULL, 'storyboard_generation',
$IVGSWP44$You are a storyboard designer converting a refined transcript into a visual storyboard.

Project: {{ project_title }}
Total Runtime Target: {{ max_duration_seconds | default(1800) }} seconds

INSTRUCTIONS:
Generate a JSON array of scene objects from the transcript. Each scene must include:
- "scene_index": Sequential integer starting from 1
- "narration_text": The narration spoken during this scene
- "visual_description": Detailed description of the visual to be generated
- "media_type": One of "image", "video_clip", or "animation"
- "duration_seconds": Duration for this scene

RULE 1 — NO TEXT IN THE VISUAL. Absolute.
"visual_description" must NEVER request on-screen text, numbers, equations,
labels, captions, titles, handwriting or writing of any kind. Image models
cannot spell or do arithmetic; they produce text-shaped marks. A real run of
this pipeline asked for "a whiteboard with a multiplication problem written on
it, such as 23 x 14" and got a whiteboard reading "2? x 23.14"; another asked
for calculations "appearing on screen" and got "12 + 44 = 67 + 5". Every
equation, number, label and caption is rendered by the COMPOSITION OVERLAY in a
later stage, with a real font. Describe only the imagery that sits beneath the
overlay, and leave clear space where the overlay will go.
  - WRONG: "a whiteboard with 23 x 14 written on it"
  - WRONG: "the equation appears on screen step by step"
  - RIGHT: "a teacher beside a clean, empty whiteboard, gesturing to its blank
    left-hand side, warm classroom light"

RULE 2 — media_type
- "image": the default. Static concepts, diagrams, portraits, backgrounds that
  will carry an overlay, summaries, establishing shots.
- "video_clip": real-world action, process, demonstration, movement.
- "animation": ONLY for a scene whose visual contains a character or person to
  animate. The animation branch is pose reenactment (Wan2.2-Animate): it
  transfers a driving video's motion onto the subject of the scene's still. A
  still with no person in it does not produce a moving diagram — the model
  invents a human body, and the pipeline now refuses the scene by name
  ("reference image contains no person to animate"). Motion of equations,
  charts, flowcharts or "steps appearing on screen" is therefore NOT
  "animation": map those scenes to "image". There is no motion-graphics
  pathway in this pipeline yet; until there is, that motion belongs to the
  composition overlay on top of a still.

RULE 3 — narration must be self-consistent
The narration is spoken aloud in order as one continuous script.
- Verify every arithmetic statement before writing it.
- NEVER narrate your own errors and never correct yourself mid-script. A real
  run produced "we should add 92 and 230 ... but that was also incorrect" and
  "this gives us 260, but we wrote it as 640 in the previous step, which is
  incorrect". The audience never saw the draft being argued with.
- If an earlier scene is wrong, GO BACK AND FIX IT. Emit one clean script.
- Later scenes must not contradict earlier ones: same quantities, same worked
  example, same result.

RULE 4 — durations must sum to the runtime
Sum your "duration_seconds" values before emitting. They must total
approximately {{ max_duration_seconds | default(1800) }} seconds, within 10%.
Adjust the scene count or the per-scene lengths until they do. Pace narration
at ~150 words per minute so each scene's duration matches its own narration.

Visual guidelines:
- Visual descriptions should be detailed enough for AI image generation
- Maintain visual consistency across scenes (style, color palette)
- Name subject, setting, style, composition, palette and key details
- Contain no text of any kind (RULE 1)

TRANSCRIPT:
{{ combined_transcript }}

OUTPUT: JSON array of scene objects.
$IVGSWP44$,
    3, true, false, 'wp-44-quality',
    'WP-44-QUALITY: four rules the first e2e run paid for. (a) visual_description '
    'must never request on-screen text, numbers or equations - FLUX rendered '
    '"23 x 14" as "2? x 23.14" across sixteen images; equations belong to the '
    'composition overlay. (b) media_type animation ONLY for scenes containing a '
    'character - v2 told the model the opposite ("use animation for data '
    'visualizations, flowcharts"), which typed eleven equation cards as '
    'animation; Wan2.2-Animate is pose reenactment and hallucinates a body when '
    'the reference has no subject, and WP-44 Task 5 now refuses those scenes by '
    'name. (c) narration self-consistency - the reference storyboard narrated '
    'its own errors ("but that was also incorrect"). (d) scene durations must '
    'sum to the project runtime within 10% - the reference project summed to '
    '190s against a 300s target. Matches ivgs-api/seed/default_prompts/'
    'storyboard_generation.j2 at WP-44.'
);

-- =====================================================================
-- SECTION B — animation_generation v2  (OPTIONAL; unconsumed today)
--
-- Delete this section if you want Section A only.
-- =====================================================================

DO $guardb$
DECLARE
    n integer;
BEGIN
    SELECT count(*) INTO n
    FROM prompts
    WHERE prompt_type = 'animation_generation'
      AND project_id IS NULL AND scene_id IS NULL AND is_active;
    IF n <> 1 THEN
        RAISE EXCEPTION
            'GUARD FAILED (Section B): expected exactly 1 active global '
            'animation_generation prompt, found %.', n;
    END IF;
END $guardb$;

UPDATE prompts
   SET is_active = false
 WHERE prompt_type = 'animation_generation'
   AND project_id IS NULL
   AND scene_id IS NULL
   AND is_active;

INSERT INTO prompts (
    project_id, scene_id, prompt_type, prompt_text, version,
    is_active, is_library_template, created_by, change_note
) VALUES (
    NULL, NULL, 'animation_generation',
$IVGSWP44$Generate a character animation for an instructional video scene.

Scene {{ scene_number }}: {{ scene_title | default("") }}
Visual Description: {{ visual_description }}
Target Duration: {{ duration_seconds | default(5) }} seconds

WHAT THIS BRANCH IS (WP-44). The animation branch is served by Wan2.2-Animate,
a POSE REENACTMENT model. It takes the still already generated for this scene
plus a driving video, and transfers the driver's motion onto the SUBJECT of
that still. It is not a motion-graphics renderer and it has no prompt-only
mode.

Consequences, which this template previously got wrong:
- This branch requires a CHARACTER OR PERSON in the scene's still. With no
  subject present the model does not decline — it invents a human body. The
  pipeline refuses such a scene by name before rendering
  ("reference image contains no person to animate").
- Animated diagrams, data visualisations, process flows, charts and
  "steps appearing on screen" are NOT this branch. There is no motion-graphics
  pathway in IVGS yet. Those scenes belong to media_type "image", with the
  motion supplied by the composition overlay.
- There is no Remotion component in this pipeline. An earlier version of this
  template asked for "Remotion component specification format"; nothing
  consumes that, and it taught the storyboard the wrong idea of what
  "animation" means.

Requirements:
- A human figure, character or creature that is visibly the subject
- Natural, plausible body and facial motion consistent with the narration
- Clean, professional style suitable for educational content
- Consistent with the scene's still: same subject, same setting, same palette
- No on-screen text, numbers, equations or labels — those are overlaid later
$IVGSWP44$,
    (SELECT COALESCE(MAX(version), 0) + 1 FROM prompts
      WHERE prompt_type = 'animation_generation'),
    true, false, 'wp-44-quality',
    'WP-44-QUALITY: the v1 text described this branch as "an animated diagram '
    'or visualization ... Remotion component specification format". IVGS has no '
    'Remotion renderer and the animation branch is Wan2.2-Animate pose '
    'reenactment, which needs a character in the reference still. Corrected to '
    'describe what the branch actually is. Matches ivgs-api/seed/default_prompts/'
    'animation_generation.j2 at WP-44.'
);

-- =====================================================================
-- SECTION C — verification (read-only)
-- =====================================================================

SELECT prompt_type, version, is_active, created_by,
       md5(prompt_text) AS md5, length(prompt_text) AS len
  FROM prompts
 WHERE prompt_type IN ('storyboard_generation', 'animation_generation')
 ORDER BY prompt_type, version;

-- Expected after Section A + B:
--   animation_generation   v1  f
--   animation_generation   v2  t   md5 d8f8b018c51931cc7caa0b1df140b9f8
--   storyboard_generation  v1  f
--   storyboard_generation  v2  f
--   storyboard_generation  v3  t   md5 8b120d1ff6f84f8286bf16d6022041a0

-- Exactly one active global row per type:
SELECT prompt_type, count(*) AS active_global
  FROM prompts
 WHERE is_active AND project_id IS NULL AND scene_id IS NULL
   AND prompt_type IN ('storyboard_generation', 'animation_generation')
 GROUP BY prompt_type;

COMMIT;
