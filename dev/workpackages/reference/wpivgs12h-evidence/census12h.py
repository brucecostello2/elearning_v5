"""WP-IVGS-12h — the CENSUS harness, made TWO-CALL. TASK 5.

⛳ 12g's HARNESS, CHANGED IN EXACTLY THE PLACES CONTRACT-7 CHANGED AND NOWHERE
ELSE — so a difference between 12g's numbers and 12h's is a difference in the
STACK and not in the measurement. The census question is still RC-Q9e's: for
every scene of every generation, is its origin `sourced` or `designed`, and what
`instructional_event` does it declare?

WHAT IS NEW, AND IT IS ONLY THIS:

  * it makes TWO calls, exactly as `design_core.capture.transform_document`
    does — call 1 against `design_contract_schema`, then call 2 against
    `assessment_authoring_schema` with a user turn built by
    `design_core.assessment_call.build_user_message` from the SAME three
    arguments the worker passes. One code path, imported, not re-typed.
  * it reports per-call tokens and wall clock, because the split's cost is a
    number this package owes and 12g's own budget row is the reason.
  * it runs `shared.design.duplication` over every outcome-pair and prints the
    containment, so the acceptance's "distinct by the belt's own measure" claim
    is a figure and not an adjective.

⛔ WHAT IT STILL IS NOT. It calls node-02 directly with the seed-rendered
prompts. It is NOT the Celery task, NOT `task_prerun`, NOT the document
transform, NOT the capture observer and NOT the scene rows — the largest gap in
this lineage, §12g.13 item 2, unchanged and re-declared.

Usage:  python3 census12h.py <script.txt> <inputs.json> <label> <n_generations>
"""
import json, os, subprocess, sys, time, urllib.request

TREE = os.environ.get("IVGS_TREE", "/opt/ivgs")
sys.path[:0] = [TREE, f"{TREE}/ivgs-workers", f"{TREE}/ivgs-api"]

from jinja2 import BaseLoader, Environment

from shared.design.evidence import derive_evidence_map
from shared.design.duplication import (
    NEAR_DUPLICATE_CONTAINMENT, duplication_verdict,
)
from shared.design.merge import merged_scene_sequence
from design_core.contract import (
    CONTRACT_VERSION, assessment_authoring_schema, design_contract_schema,
    practice_summary, response_format_for,
)
from design_core.assessment_call import build_user_message
from shared.design.outcomes import parse_outcomes
from app.services.design_review import review, split

SEED = f"{TREE}/ivgs-api/seed/default_prompts"
OUT = os.path.dirname(os.path.abspath(__file__))
env = Environment(loader=BaseLoader(), keep_trailing_newline=True)

SCRIPT_PATH, INPUTS_PATH, LABEL, N = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
SCRIPT = open(SCRIPT_PATH).read()
P = json.load(open(INPUTS_PATH))
LO = P["learning_outcomes"]
PARSED = parse_outcomes(LO)
IDS = [o["id"] for o in PARSED]

system1 = env.from_string(open(f"{SEED}/storyboard_design_system.j2").read()).render(
    learning_outcomes=LO, outcomes=PARSED, source_kind="uploaded")
user1 = env.from_string(open(f"{SEED}/storyboard_generation.j2").read()).render(
    project_title=P["name"], project_description=P["description"],
    target_audience=P["target_audience"], max_duration_seconds=P["max_runtime_seconds"],
    total_runtime_seconds=P["max_runtime_seconds"], combined_transcript=SCRIPT,
    transcript_count=1, target_scene_count=None, language_code=P["language_code"])
# ⛔ THE CALL-2 SYSTEM PROMPT IS RENDERED FROM THE SEED FILE LIKE THE OTHERS, and
# it takes no variables at all — the publisher's gate refuses one that does.
system2 = env.from_string(open(f"{SEED}/assessment_authoring_system.j2").read()).render()

SCHEMA1 = design_contract_schema(outcome_ids=IDS)
SCHEMA2 = assessment_authoring_schema(outcome_ids=IDS)

# ⛔ BOTH BUDGETS COME FROM THE RUNNING WORKER, not from literals. 12g's first
# acceptance run truncated at a hardcoded 8192 that WAS production's floor;
# asking the container removes the class of error rather than fixing one number.
_probe = subprocess.run(
    ["sudo", "docker", "exec", "ivgs-celery-default", "python", "-c",
     "from config import WorkerConfig;c=WorkerConfig();"
     "print(c.storyboard_max_tokens_for(None));"
     "print(c.vllm.storyboard_call2_max_tokens);"
     "print(';'.join(str(x) for x in c.storyboard_call_timeouts()))"],
    capture_output=True, text=True, check=True).stdout.split()
MAX1, MAX2 = int(_probe[0]), int(_probe[1])
T1, T2 = (float(x) for x in _probe[2].split(";"))

print("=" * 78)
print(f"CENSUS {LABEL}   contract {CONTRACT_VERSION}   outcome ids {IDS}")
print(f"script   : {SCRIPT_PATH}  {len(SCRIPT)} chars")
print(f"call 1   : system={len(system1)} user={len(user1)} chars  "
      f"max_tokens={MAX1}  client timeout={T1}s")
print(f"call 2   : system={len(system2)} chars  max_tokens={MAX2}  "
      f"client timeout={T2}s")
print(f"call-1 property order : {list(SCHEMA1['properties'].keys())}")
print(f"call-2 property order : {list(SCHEMA2['properties'].keys())}")
print(f"near-duplicate threshold (limb A) : {NEAR_DUPLICATE_CONTAINMENT}")
print("=" * 78)


def engine(system, user, schema, max_tokens, name):
    body = {"model": "llama-3.3-70b",
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "max_tokens": max_tokens, "temperature": 0.3, "top_p": 0.9,
            "response_format": response_format_for(schema, name=name)}
    req = urllib.request.Request(
        "http://192.168.1.91:8000/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer ivgs-internal"})
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=1200) as r:
        payload = json.loads(r.read().decode())
    dt = time.monotonic() - t0
    ch = payload["choices"][0]
    u = payload.get("usage", {})
    return ch.get("finish_reason"), ch["message"]["content"], u, dt


def generate(n):
    """The two calls, in the order and with the inputs the worker uses."""
    fin1, raw1, u1, dt1 = engine(system1, user1, SCHEMA1, MAX1,
                                 "ivgs_design_contract")
    print(f"--- {LABEL} gen {n} CALL 1: {dt1:.0f}s  finish={fin1}  "
          f"prompt_tokens={u1.get('prompt_tokens')} "
          f"completion_tokens={u1.get('completion_tokens')}")
    if fin1 != "stop":
        ws = sum(1 for c in raw1 if c.isspace())
        print(f"    ⛔ CALL 1 TRUNCATED - chars={len(raw1)} whitespace={ws}")
        return None, {"call1": {"seconds": dt1, "usage": u1, "finish": fin1}}
    doc = json.loads(raw1)

    # ⛳ THE SPLIT ITSELF: call 2's user turn is built by the WORKER'S function,
    # from the outcomes, the plan and a code-built summary. Nothing else is in
    # scope here, which is the property the whole package rests on.
    summary = practice_summary(doc, IDS)
    user2 = build_user_message(
        outcomes=PARSED, assessment_plan=doc.get("assessment_plan") or {},
        summary=summary)
    fin2, raw2, u2, dt2 = engine(system2, user2, SCHEMA2, MAX2,
                                 "ivgs_assessment_authoring")
    print(f"--- {LABEL} gen {n} CALL 2: {dt2:.0f}s  finish={fin2}  "
          f"prompt_tokens={u2.get('prompt_tokens')} "
          f"completion_tokens={u2.get('completion_tokens')}  "
          f"user={len(user2)} chars")
    print(f"    numbers already used, handed to call 2: "
          f"{summary.get('numbers_already_used')}")
    if fin2 != "stop":
        print(f"    ⛔ CALL 2 TRUNCATED - chars={len(raw2)}")
        return None, {"call1": {"seconds": dt1, "usage": u1, "finish": fin1},
                      "call2": {"seconds": dt2, "usage": u2, "finish": fin2}}
    section = json.loads(raw2).get("assessment_scenes")
    doc["assessment_scenes"] = section
    timing = {
        "call1": {"seconds": round(dt1, 1), "usage": u1, "finish": fin1},
        "call2": {"seconds": round(dt2, 1), "usage": u2, "finish": fin2,
                  "user_chars": len(user2)},
        "total_seconds": round(dt1 + dt2, 1),
        "summary_given_to_call2": summary,
    }
    print(f"    ⛳ TWO-CALL TOTAL: {dt1 + dt2:.0f}s   "
          f"input {u1.get('prompt_tokens')} + {u2.get('prompt_tokens')}   "
          f"output {u1.get('completion_tokens')} + {u2.get('completion_tokens')}")
    return doc, timing


def duplication_rows(obj):
    """Every outcome-pair, scored by the gate's own module. TASK 2's number."""
    rows = []
    A = obj.get("assessment_scenes") or {}
    Pr = obj.get("practice_scenes") or {}
    expo = [s for s in (obj.get("scenes") or []) if isinstance(s, dict)]
    for oid in IDS:
        entry = A.get(oid)
        if not entry:
            continue
        scene = entry[0] if isinstance(entry, list) else entry
        a = scene.get("narration_text")
        prac = [s.get("narration_text") for s in (Pr.get(oid) or [])]
        work = [s.get("narration_text") for s in expo
                if s.get("instructional_event") in ("present", "guide")
                and oid in (s.get("serves_outcomes") or [])]
        pv = [duplication_verdict(a, x) for x in prac]
        wv = [duplication_verdict(a, x) for x in work]
        rows.append({
            "outcome_id": oid,
            "assessment": a,
            "practices": prac,
            "practice_containment": max([v["containment"] for v in pv] or [0.0]),
            "practice_duplicate": any(v["duplicate"] for v in pv),
            "worked_containment": max([v["containment"] for v in wv] or [0.0]),
            "worked_duplicate": any(v["duplicate"] for v in wv),
        })
    return rows


def census(n, obj, timing):
    raw_scenes = merged_scene_sequence(obj)
    notes = obj.get("outcome_notes") or {}
    outcomes = [{"id": o["id"], "text": o["text"],
                 "bloom_level": (notes.get(o["id"]) or {}).get("bloom_level"),
                 "measurable": bool((notes.get(o["id"]) or {}).get("measurable", True)),
                 "proposed_refinement": (notes.get(o["id"]) or {}).get("proposed_refinement")}
                for o in PARSED]
    scenes = []
    for i, s in enumerate(raw_scenes):
        prov = s.get("provenance") or {}
        o = prov.get("origin")
        scenes.append({
            "scene_index": s.get("scene_index", i),
            "serves_outcomes": s.get("serves_outcomes"),
            "instructional_event": s.get("instructional_event"),
            "bloom_level": s.get("bloom_level"), "scene_origin": o,
            "source_refs": prov.get("source_refs") if o == "sourced" else None,
            "designed_rationale": prov.get("rationale") if o == "designed" else None,
            "rewrite_of": prov.get("rewrite_of"), "media_type": s.get("media_type"),
            "media_rationale": s.get("media_rationale"),
            "generation_params": s.get("generation_params"),
            "duration_seconds": s.get("duration_seconds"),
            "visual_description": s.get("visual_description"),
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
    events = [s["instructional_event"] for s in scenes]

    n_sourced = sum(1 for s in scenes if s["scene_origin"] == "sourced")
    n_designed = sum(1 for s in scenes if s["scene_origin"] == "designed")
    n_assess = sum(1 for e in events if e == "assess")
    n_practice = sum(1 for e in events if e == "practice")

    raw_events = [x.get("instructional_event")
                  for x in (obj.get("scenes") or []) if isinstance(x, dict)]
    evidence_in_scenes = sum(1 for e in raw_events if e in ("practice", "assess"))
    per_lo = {oid: {"practice": 0, "assess": 0} for oid in IDS}
    for s in scenes:
        ev = s["instructional_event"]
        if ev in ("practice", "assess"):
            for oid in (s["serves_outcomes"] or []):
                if oid in per_lo:
                    per_lo[oid][ev] += 1
    both_present = all(v["practice"] >= 1 and v["assess"] >= 1 for v in per_lo.values())
    assessed_once = all(v["assess"] == 1 for v in per_lo.values())
    print(f"    ⛔ evidence events INSIDE the model's own call-1 scenes[] = "
          f"{evidence_in_scenes}   (contract-7 requires 0)")
    print(f"    per-LO practice AND assess present = {both_present}   "
          f"exactly one assess each = {assessed_once}   {json.dumps(per_lo)}")
    ev_origins = [s["scene_origin"] for s in scenes
                  if s["instructional_event"] in ("practice", "assess")]
    print(f"    evidence-scene origins = {ev_origins}")

    dup = duplication_rows(obj)
    print(f"    ⛳ THE BELT — assessment vs its own practice, and vs the worked examples")
    for d in dup:
        print(f"       {d['outcome_id']}: practice containment "
              f"{d['practice_containment']:.3f} "
              f"{'⛔ DUPLICATE' if d['practice_duplicate'] else 'distinct'}   "
              f"worked-example containment {d['worked_containment']:.3f} "
              f"{'⛔ DUPLICATE' if d['worked_duplicate'] else 'distinct'}")

    print(f"    THE CENSUS  scenes={len(scenes)}  sourced={n_sourced}  "
          f"DESIGNED={n_designed}  assess={n_assess}  practice={n_practice}")
    print(f"    outcome text VERBATIM  : {all(r.text == p['text'] for r, p in zip(rows, PARSED))}")
    print(f"    ids cited: {cited}   INVENTED: {invented or 'NONE'}")
    print(f"    dropped_beats={len(obj.get('dropped_beats', []))}")
    print(f"    assessment_plan: " + json.dumps({k: v.get("evidence_kind") for k, v in plan.items()}))
    print(f"    DERIVED evidence_map: {json.dumps(em)}")
    print(f"    events: {events}")
    for s in scenes:
        if s["instructional_event"] in ("assess", "practice") or s["scene_origin"] == "designed":
            print(f"    >> scene {s['scene_index']} [{s['instructional_event']}] "
                  f"origin={s['scene_origin']} serves={s['serves_outcomes']} "
                  f"media={s['media_type']} {s['duration_seconds']}s")
            print(f"       source_refs: {json.dumps(s['source_refs'])}")
            if s["designed_rationale"]:
                print(f"       rationale  : {s['designed_rationale']}")
            print(f"       NARRATION  : {s['narration_text']}")
            print(f"       visual     : {str(s['visual_description'])[:220]}")
    print(f"    HARD REFUSALS = {len(ref)}    flags = {len(flg)}")
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
    return {"gen": n, "label": LABEL, "scenes": len(scenes),
            "sourced": n_sourced, "designed": n_designed,
            "assess": n_assess, "practice": n_practice,
            "dropped": len(obj.get("dropped_beats", [])),
            "invented": invented, "evidence_map": em, "plan": plan,
            "events": events, "refusals": [x.code for x in ref],
            "flags": [x.code for x in flg],
            "verbatim": all(r.text == p["text"] for r, p in zip(rows, PARSED)),
            "evidence_in_scenes": evidence_in_scenes,
            "per_lo": per_lo, "both_present": both_present,
            "assessed_once": assessed_once, "evidence_origins": ev_origins,
            "duplication": dup, "timing": timing,
            "practice_scenes": [s for s in scenes if s["instructional_event"] == "practice"],
            "rows": [r.as_dict() for r in rows],
            "assess_scenes": [s for s in scenes if s["instructional_event"] == "assess"]}


def run():
    results, contracts = [], []
    for n in range(1, N + 1):
        obj, timing = generate(n)
        contracts.append(obj)
        results.append(census(n, obj, timing) if obj
                       else {"gen": n, "label": LABEL, "TRUNCATED": True,
                             "timing": timing})

    json.dump(contracts, open(f"{OUT}/{LABEL}-contracts.json", "w"), indent=2)
    json.dump(results, open(f"{OUT}/{LABEL}-census.json", "w"), indent=2)

    ok = [r for r in results if not r.get("TRUNCATED")]
    print("=" * 78)
    print(f"{LABEL} TOTALS vs THE THREE BASELINES")
    print("   contract-4 (RC-Q9e, 6 gens): 83 scenes / 83 sourced / 0 designed / 0 assess")
    print("   contract-5 (RC-Q9f run B, 3 gens): 43 / 33 / 10 / 10, 6 refusals in 6 gens")
    print("   contract-6 (12g run B, 3 gens): 138 / 127 / 11 / 9, 9 practice, 0 refusals")
    print(f"  scenes  {sum(r['scenes'] for r in ok)}   sourced {sum(r['sourced'] for r in ok)}   "
          f"DESIGNED {sum(r['designed'] for r in ok)}   assess {sum(r['assess'] for r in ok)}   "
          f"practice {sum(r['practice'] for r in ok)}")
    print(f"  hard refusals per generation: {[len(r.get('refusals', [])) for r in results]}")
    print(f"  ⛔ evidence events in call 1's own scenes[]: "
          f"{[r.get('evidence_in_scenes') for r in ok]}   (contract-7 requires all 0)")
    print(f"  per-LO practice AND assess present: {[r.get('both_present') for r in ok]}")
    print(f"  exactly one assess per LO:          {[r.get('assessed_once') for r in ok]}")
    print("  ⛳ THE BELT, every outcome-pair, every generation:")
    for r in ok:
        for d in r["duplication"]:
            print(f"     gen {r['gen']} {d['outcome_id']}: practice "
                  f"{d['practice_containment']:.3f} "
                  f"{'DUPLICATE' if d['practice_duplicate'] else 'distinct'}, "
                  f"worked {d['worked_containment']:.3f} "
                  f"{'DUPLICATE' if d['worked_duplicate'] else 'distinct'}")
    print("  ⛔ THE TWO-CALL COST, per generation:")
    for r in results:
        t = r.get("timing") or {}
        c1, c2 = t.get("call1") or {}, t.get("call2") or {}
        print(f"     gen {r['gen']}: call1 {c1.get('seconds')}s "
              f"({(c1.get('usage') or {}).get('prompt_tokens')} in / "
              f"{(c1.get('usage') or {}).get('completion_tokens')} out)   "
              f"call2 {c2.get('seconds')}s "
              f"({(c2.get('usage') or {}).get('prompt_tokens')} in / "
              f"{(c2.get('usage') or {}).get('completion_tokens')} out)   "
              f"TOTAL {t.get('total_seconds')}s")
    print("=" * 78)


if __name__ == "__main__":
    run()
