"""WP-IVGS-12d Task 4: the acceptance criterion, FOURTH attempt.

Three consecutive generations, the SAME script (the operator's 3,172-byte
multiplication lesson, md5 f65f340c…), the SAME three ABCD outcomes, the SAME
production parameters. Scored on each generation's own emitted contract, for
the reason WP-IVGS-12 §9.4 gives.

⚠ WHAT THIS HARNESS IS AND IS NOT. It renders the two prompts from the SEED
FILES and builds the schema from `design_core.contract`, which is exactly what
production does — the user template was verified byte-identical to the active
DB row `storyboard_generation` v9, and the system template is byte-identical to
what the publisher would publish as v3. The schema and the scoring are the same
modules the worker and the API import. What it does NOT exercise is the capture
observer and the storage round-trip, neither of which WP-IVGS-12c touched.

It runs against node-02 and writes nothing to the fleet.
"""
import json, sys, time, urllib.request
sys.path[:0] = ["/opt/ivgs", "/opt/ivgs/ivgs-workers", "/opt/ivgs/ivgs-api"]

from jinja2 import BaseLoader, Environment

from shared.design.evidence import derive_evidence_map
from design_core.contract import (
    CONTRACT_VERSION, design_contract_schema, parse_contract, response_format_for,
)
from shared.design.outcomes import parse_outcomes
from app.services.design_review import review, split

S = "/tmp/claude-1002/-opt-ivgs/d584836b-23c9-472d-8ee5-45ceb1eb6186/scratchpad"
SEED = "/opt/ivgs/ivgs-api/seed/default_prompts"
env = Environment(loader=BaseLoader(), keep_trailing_newline=True)

SCRIPT = open(f"{S}/script.txt").read()
P = json.load(open(f"{S}/create.json"))
LO = P["learning_outcomes"]
PARSED = parse_outcomes(LO)

system = env.from_string(open(f"{SEED}/storyboard_design_system.j2").read()).render(
    learning_outcomes=LO, outcomes=PARSED, source_kind="uploaded")
# The nine names `_render_user_prompt` fixes inside the frozen stage body.
user = env.from_string(open(f"{SEED}/storyboard_generation.j2").read()).render(
    project_title=P["name"], project_description=P["description"],
    target_audience=P["target_audience"], max_duration_seconds=300,
    total_runtime_seconds=300, combined_transcript=SCRIPT, transcript_count=1,
    target_scene_count=None, language_code="en-US")

IDS = [o["id"] for o in PARSED]
SCHEMA = design_contract_schema(outcome_ids=IDS)

print(f"contract {CONTRACT_VERSION}   outcome ids {IDS}")
print(f"system={len(system)} chars  user={len(user)} chars  script md5-len={len(SCRIPT)}")
print(f"property order    : {list(SCHEMA['properties'].keys())}")
print(f"plan entry shape  : {json.dumps(SCHEMA['properties']['assessment_plan']['properties'][IDS[0]]['required'])}")
print(f"evidence_map in schema: {'evidence_map' in SCHEMA['properties']}\n")


def generate(n):
    body = {"model": "llama-3.3-70b",
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "max_tokens": 8192, "temperature": 0.3, "top_p": 0.9,
            "response_format": response_format_for(SCHEMA)}
    req = urllib.request.Request(
        "http://192.168.1.91:8000/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer ivgs-internal"})
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=900) as r:
        payload = json.loads(r.read().decode())
    dt = time.monotonic() - t0
    ch = payload["choices"][0]
    u = payload.get("usage", {})
    fin = ch.get("finish_reason")
    raw = ch["message"]["content"]
    print(f"--- generation {n}: {dt:.0f}s  finish={fin}  "
          f"prompt_tokens={u.get('prompt_tokens')} completion_tokens={u.get('completion_tokens')}")
    if fin != "stop":
        # ⛔ The whitespace corridor the minItems probe found. WP-37 raises here
        # in production; the harness reports it rather than pretending.
        ws = sum(1 for c in raw if c.isspace())
        print(f"    ⛔ TRUNCATED — chars={len(raw)} whitespace={ws}")
        return None
    return json.loads(raw)


def score(n, obj):
    payload = parse_contract(obj)
    assert payload is not None, "parse_contract returned None — not a design contract"
    notes = obj.get("outcome_notes") or {}
    # Exactly what `DesignBriefService._outcomes_from_the_project` builds.
    outcomes = [{"id": o["id"], "text": o["text"],
                 "bloom_level": (notes.get(o["id"]) or {}).get("bloom_level"),
                 "measurable": bool((notes.get(o["id"]) or {}).get("measurable", True)),
                 "proposed_refinement": (notes.get(o["id"]) or {}).get("proposed_refinement")}
                for o in PARSED]
    scenes = []
    for s in obj.get("scenes", []):
        prov = s.get("provenance") or {}
        o = prov.get("origin")
        scenes.append({
            "scene_index": s.get("scene_index"),
            "serves_outcomes": s.get("serves_outcomes"),
            "instructional_event": s.get("instructional_event"),
            "bloom_level": s.get("bloom_level"), "scene_origin": o,
            "source_refs": prov.get("source_refs") if o == "sourced" else None,
            "rewrite_of": prov.get("rewrite_of"), "media_type": s.get("media_type"),
            "media_rationale": s.get("media_rationale"),
            "generation_params": s.get("generation_params"),
            "narration_text": s.get("narration_text")})
    findings, rows = review(scenes=scenes, outcomes=outcomes,
                            assessment_plan=obj.get("assessment_plan", {}),
                            dropped_beats=obj.get("dropped_beats", []),
                            source_text=SCRIPT, learning_outcomes=LO)
    ref, flg = split(findings)
    cited = sorted({o for s in scenes for o in (s["serves_outcomes"] or [])})
    invented = [i for i in cited if i not in IDS]
    em = derive_evidence_map(scenes, IDS)
    plan = obj.get("assessment_plan") or {}
    mt = {}
    for s in scenes:
        mt[s["media_type"]] = mt.get(s["media_type"], 0) + 1
    print(f"    scenes={len(scenes)} notes={len(notes)} "
          f"dropped_beats={len(obj.get('dropped_beats',[]))} "
          f"sourced={sum(1 for s in scenes if s['scene_origin']=='sourced')} "
          f"rewrites={sum(1 for s in scenes if s['rewrite_of'])}")
    print(f"    outcome text VERBATIM  : {all(r.text == p['text'] for r, p in zip(rows, PARSED))}")
    print(f"    ids cited: {cited}   INVENTED: {invented or 'NONE'}")
    print(f"    assessment_plan: " + json.dumps(
        {k: v.get("evidence_kind") for k, v in plan.items()}))
    for k, v in plan.items():
        print(f"        {k} {v.get('evidence_kind')}: {str(v.get('learner_does'))[:88]}")
    print(f"    DERIVED evidence_map: {json.dumps(em)}")
    print(f"    outcomes with no evidence : {[k for k,v in em.items() if not v] or 'NONE'}")
    print(f"    events: {[s['instructional_event'] for s in scenes]}")
    print(f"    media : {mt}")
    print(f"    ⛔ HARD REFUSALS = {len(ref)}    flags = {len(flg)}")
    for x in ref:
        who = (f"scene {x.scene_index}" if x.scene_index is not None
               else (f"outcome {x.outcome_id}" if x.outcome_id else "design"))
        print(f"        REFUSE {who:<14} {x.code}")
    for x in flg:
        who = (f"scene {x.scene_index}" if x.scene_index is not None
               else (f"outcome {x.outcome_id}" if x.outcome_id else "design"))
        print(f"        flag   {who:<14} {x.code}")
    for r in rows:
        print(f"        {r.outcome_id}: served={r.served_by} assessed={r.assessed_by}")
    print()
    return {"gen": n, "scenes": len(scenes), "notes": len(notes),
            "dropped": len(obj.get("dropped_beats", [])),
            "sourced": sum(1 for s in scenes if s["scene_origin"] == "sourced"),
            "rewrites": sum(1 for s in scenes if s["rewrite_of"]),
            "invented": invented, "evidence_map": em, "plan": plan,
            "events": [s["instructional_event"] for s in scenes],
            "media": mt, "refusals": [x.code for x in ref],
            "flags": [x.code for x in flg],
            "rows": [r.as_dict() for r in rows]}


results, contracts = [], []
for n in (1, 2, 3):
    obj = generate(n)
    contracts.append(obj)
    results.append(score(n, obj) if obj else {"gen": n, "TRUNCATED": True})

json.dump(contracts, open(f"{S}/12d-contracts.json", "w"), indent=2)
json.dump(results, open(f"{S}/12d-results.json", "w"), indent=2)

print("=" * 72)
print("ACCEPTANCE — the Task-7 criterion")
print("=" * 72)
ok_ref = all(not r.get("refusals") and not r.get("TRUNCATED") for r in results)
ok_ids = all(not r.get("invented") and not r.get("TRUNCATED") for r in results)
ok_ev = all(not [k for k, v in (r.get("evidence_map") or {}).items() if not v]
            and not r.get("TRUNCATED") for r in results)
ok_plan = all(len(r.get("plan") or {}) == len(IDS) and not r.get("TRUNCATED")
              for r in results)
ok_realized = all("PLAN_ENTRY_UNREALIZED" not in (r.get("refusals") or [])
                  and not r.get("TRUNCATED") for r in results)
ok_sa = all(all(x["served"] and x["assessed"] for x in r.get("rows", []))
            and not r.get("TRUNCATED") for r in results)
print(f"  zero hard refusals, all three      : {ok_ref}  ({[len(r.get('refusals',[])) for r in results]})")
print(f"  no invented ids, all three         : {ok_ids}")
print(f"  every outcome has derived evidence : {ok_ev}")
print(f"  plan carries one entry per outcome : {ok_plan}")
print(f"  every plan entry REALIZED 3/3      : {ok_realized}")
print(f"  every outcome served AND assessed  : {ok_sa}")
print(f"  dropped_beats per generation       : {[r.get('dropped') for r in results]}")
print(f"  scenes per generation              : {[r.get('scenes') for r in results]}")
