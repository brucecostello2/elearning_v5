-- WP-33-MODELSTORE-PREP - Model Store binding validation
--
-- READ-ONLY. Contains no INSERT, UPDATE or DELETE. Safe to run at any time.
--
-- Run it on node-01 with:
--   docker exec -i ivgs-postgres psql -U ivgs -d ivgs -X -P pager=off \
--     -f - < dev/workpackages/reference/wp33-validate-binding.sql
--
-- It replicates the get_binding default-fallback predicate from
-- shared/providers/factory.py:173-183 exactly:
--     Model.stage    == stage
--     Model.tier     IN (tier, 'both')
--     Model.is_default IS TRUE
--     Model.state    == 'approved'
--     Model.enabled  IS TRUE
--   -> first row, else SelectionError
--
-- TWO MODES.
--   Query A ("as-is") reports what get_binding resolves to RIGHT NOW.
--   Query B ("projected") applies the WP-33-POPULATION-CHECKLIST changes
--     in memory only and reports what it WOULD resolve to afterwards.
-- After executing the checklist for real, Query A should print the same
-- result Query B prints today.
--
-- 'candidates_matching' must be 1 for a stage to be unambiguous: the real
-- query is LIMIT 1 with no ORDER BY, so 2+ matches would resolve
-- nondeterministically.

SET default_transaction_read_only = on;

\echo ''
\echo '=== QUERY A - as the store stands now ==='

WITH stages(s) AS (VALUES ('transcript_refinement'),('storyboard_generation'),
                          ('image_generation'),('video_generation'),
                          ('animation_generation'),('voiceover_tts'),
                          ('talking_head'),('composition'),('translation')),
     tiers(t)  AS (VALUES ('prototype'),('production'))
SELECT st.s AS stage, ti.t AS tier,
       COALESCE((SELECT m.name FROM models m
                 WHERE m.stage::text = st.s
                   AND m.tier::text IN (ti.t,'both')
                   AND m.is_default IS TRUE
                   AND m.state::text = 'approved'
                   AND m.enabled IS TRUE
                 LIMIT 1), '-- SelectionError --') AS resolves_to,
       (SELECT count(*) FROM models m
         WHERE m.stage::text = st.s AND m.tier::text IN (ti.t,'both')
           AND m.is_default IS TRUE AND m.state::text = 'approved'
           AND m.enabled IS TRUE) AS candidates_matching
FROM stages st CROSS JOIN tiers ti
ORDER BY st.s, ti.t DESC;

\echo ''
\echo '=== QUERY B - projected, after WP-33-POPULATION-CHECKLIST ==='
\echo '=== (in memory only - changes nothing) ==='

WITH projected AS (
    SELECT m.name,
           m.stage::text AS stage,
           m.tier::text  AS tier,
           CASE WHEN m.name IN ('XTTS-v2','CogVideoX-5b')
                THEN 'approved' ELSE m.state::text END AS state,
           CASE WHEN m.name IN ('XTTS-v2','CogVideoX-5b')
                THEN TRUE ELSE m.is_default END        AS is_default,
           m.enabled
    FROM models m
    UNION ALL
    -- AMENDED 2026-08-23 by WP-34-DEPLOY-BATCH R7.3.
    -- Was mistral-24b-transcript / mistral-24b-storyboard. node-02 came back at
    -- 01:23:23Z on 2026-08-23 and its vLLM serves llama-3.3-70b -- verified live
    -- from inside the node-02 and node-04 workers (HTTP 200,
    -- models=[llama-3.3-70b]). The mistral-24b rows were the interim answer to
    -- node-02 being dead; they are no longer the plan. Per finding F-6 each row
    -- still needs default_params.engine_model = the SERVED name, 'llama-3.3-70b'
    -- (the store's existing 'Llama-3.3-70B-Instruct' row is on stage
    -- 'translation' and cannot serve stage 1 or 2 -- AD-01.5.2 is one row per
    -- stage -- so these are new rows, not a promotion).
    SELECT * FROM (VALUES
        ('llama-3.3-70b-transcript','transcript_refinement','both','approved',TRUE,TRUE),
        ('llama-3.3-70b-storyboard','storyboard_generation','both','approved',TRUE,TRUE),
        ('flux1-schnell',           'image_generation',     'both','approved',TRUE,TRUE)
    ) AS v(name,stage,tier,state,is_default,enabled)
),
stages(s) AS (VALUES ('transcript_refinement'),('storyboard_generation'),
                     ('image_generation'),('video_generation'),
                     ('animation_generation'),('voiceover_tts'),
                     ('talking_head'),('composition'),('translation')),
tiers(t)  AS (VALUES ('prototype'),('production'))
SELECT st.s AS stage, ti.t AS tier,
       COALESCE((SELECT p.name FROM projected p
                 WHERE p.stage = st.s
                   AND p.tier IN (ti.t,'both')
                   AND p.is_default IS TRUE
                   AND p.state = 'approved'
                   AND p.enabled IS TRUE
                 LIMIT 1), '-- SelectionError --') AS resolves_to,
       (SELECT count(*) FROM projected p
         WHERE p.stage = st.s AND p.tier IN (ti.t,'both')
           AND p.is_default IS TRUE AND p.state = 'approved'
           AND p.enabled IS TRUE) AS candidates_matching
FROM stages st CROSS JOIN tiers ti
ORDER BY st.s, ti.t DESC;

\echo ''
\echo 'animation_generation, composition and translation are EXPECTED to show'
\echo 'SelectionError in both queries - no task binds them. See the WP-33 report.'
