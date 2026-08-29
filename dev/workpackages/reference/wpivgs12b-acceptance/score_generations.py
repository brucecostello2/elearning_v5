import json, sys
sys.path[:0] = ["/opt/ivgs", "/opt/ivgs/ivgs-api"]
from app.services.design_review import review, split
from shared.design.outcomes import parse_outcomes
S = "/tmp/claude-1002/-opt-ivgs/c0814adf-2083-48e5-a7df-dc442a59aff6/scratchpad"
briefs = json.load(open(f"{S}/briefs.json"))
script = open(f"{S}/script.txt").read()
LO = json.load(open(f"{S}/create.json"))["learning_outcomes"]
parsed = parse_outcomes(LO)
print(f"operator wrote {len(parsed)} outcomes: {[o['id'] for o in parsed]}\n")
for n, b in enumerate(briefs, 1):
    rc = b["raw_contract"] or {}
    notes = rc.get("outcome_notes") or {}
    outcomes = [{"id": o["id"], "text": o["text"],
                 "bloom_level": (notes.get(o["id"]) or {}).get("bloom_level"),
                 "measurable": bool((notes.get(o["id"]) or {}).get("measurable", True)),
                 "proposed_refinement": (notes.get(o["id"]) or {}).get("proposed_refinement")}
                for o in parsed]
    scenes = []
    for s in rc.get("scenes", []):
        prov = s.get("provenance") or {}
        o = prov.get("origin")
        scenes.append({"scene_index": s.get("scene_index"),
            "serves_outcomes": s.get("serves_outcomes"),
            "instructional_event": s.get("instructional_event"),
            "bloom_level": s.get("bloom_level"), "scene_origin": o,
            "source_refs": prov.get("source_refs") if o == "sourced" else None,
            "rewrite_of": prov.get("rewrite_of"), "media_type": s.get("media_type"),
            "media_rationale": s.get("media_rationale"),
            "generation_params": s.get("generation_params"),
            "narration_text": s.get("narration_text")})
    f, rows = review(scenes=scenes, outcomes=outcomes,
                     evidence_map=rc.get("evidence_map", {}),
                     dropped_beats=rc.get("dropped_beats", []),
                     source_text=script, learning_outcomes=LO)
    ref, flg = split(f)
    mt = {}
    for s in scenes: mt[s["media_type"]] = mt.get(s["media_type"], 0) + 1
    ids = sorted({o for s in scenes for o in (s["serves_outcomes"] or [])})
    print(f"--- generation {n} ({b['created_at'][:19]}) ---")
    print(f"  scenes={len(scenes)} notes={len(notes)} dropped={len(rc.get('dropped_beats',[]))} "
          f"sourced={sum(1 for s in scenes if s['scene_origin']=='sourced')} "
          f"rewrites={sum(1 for s in scenes if s['rewrite_of'])}")
    print(f"  ids cited: {ids}   invented: {[i for i in ids if i not in [o['id'] for o in parsed]] or 'NONE'}")
    print(f"  events: {[s['instructional_event'] for s in scenes]}")
    print(f"  media : {mt}")
    print(f"  HARD REFUSALS = {len(ref)}   flags = {len(flg)}")
    for x in ref:
        who = f"scene {x.scene_index}" if x.scene_index is not None else (f"outcome {x.outcome_id}" if x.outcome_id else "design")
        print(f"     REFUSE {who:<14} {x.code}")
    for x in flg[:5]:
        who = f"scene {x.scene_index}" if x.scene_index is not None else (f"outcome {x.outcome_id}" if x.outcome_id else "design")
        print(f"     flag   {who:<14} {x.code}")
    for r in rows:
        print(f"     {r.outcome_id}: served={r.served_by} assessed={r.assessed_by}")
    print()
