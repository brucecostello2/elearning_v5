"""WP-IVGS-12g — the CENSUS harness. One question, asked the same way every time.

⛳ THE SAME HARNESS 12f RAN, DELIBERATELY UNCHANGED EXCEPT FOR TWO ADDITIONS —
so a difference between 12f's numbers and 12g's is a difference in the STACK and
not in the measurement. The additions are the two counts contract-6 makes
meaningful: `evidence_in_scenes` (must be 0 — the narrowed enum) and the per-LO
present/absent census for BOTH kinds.

The census RC-Q9e defined: for every scene of every generation, is its origin
`sourced` or `designed`, and what `instructional_event` does it declare? Two
baselines now — 83/83/0/0 under contract-4 (RC-Q9e) and 43/33/10/10 with 6
refusals under contract-5 (RC-Q9f run B).

Renders the two prompts from the SEED FILES and builds the schema from
`design_core.contract` — the same modules the worker and the API import. It runs
against node-02 and writes nothing to the fleet.

Usage:  python3 census12g.py <script.txt> <inputs.json> <label> <n_generations>
"""
import json, os, subprocess, sys, time, urllib.request

#: The tree whose contract and prompts are under measurement. A contract-4 run
#: is reproduced by pointing this at a git worktree of the parent commit; the
#: harness itself never changes between the two, which is the whole point.
TREE = os.environ.get("IVGS_TREE", "/opt/ivgs")
sys.path[:0] = [TREE, f"{TREE}/ivgs-workers", f"{TREE}/ivgs-api"]

from jinja2 import BaseLoader, Environment

from shared.design.evidence import derive_evidence_map
from design_core.contract import (
    CONTRACT_VERSION, design_contract_schema, parse_contract, response_format_for,
)
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

system = env.from_string(open(f"{SEED}/storyboard_design_system.j2").read()).render(
    learning_outcomes=LO, outcomes=PARSED, source_kind="uploaded")
user = env.from_string(open(f"{SEED}/storyboard_generation.j2").read()).render(
    project_title=P["name"], project_description=P["description"],
    target_audience=P["target_audience"], max_duration_seconds=P["max_runtime_seconds"],
    total_runtime_seconds=P["max_runtime_seconds"], combined_transcript=SCRIPT,
    transcript_count=1, target_scene_count=None, language_code=P["language_code"])

SCHEMA = design_contract_schema(outcome_ids=IDS)

# ⛔ THE BUDGET COMES FROM THE RUNNING WORKER, not from a literal and not from
# importing the config here — `WorkerConfig` requires VLLM_PRIMARY_URL and a
# harness that sets it would be reading its own guess back. 12g's first
# acceptance run truncated at a hardcoded 8192 that WAS production's floor;
# asking the container removes the class of error rather than fixing one number.
# `target_scene_count` is None for this project, which is what the operator's
# real job sends, so this is the budget stage 2 actually uses.
MAX_TOKENS = int(subprocess.run(
    ["sudo", "docker", "exec", "ivgs-celery-default", "python", "-c",
     "from config import WorkerConfig;"
     "print(WorkerConfig().storyboard_max_tokens_for(None))"],
    capture_output=True, text=True, check=True).stdout.strip())

print("=" * 74)
print(f"CENSUS {LABEL}   contract {CONTRACT_VERSION}   outcome ids {IDS}")
print(f"script  : {SCRIPT_PATH}  {len(SCRIPT)} chars")
print(f"system={len(system)} chars  user={len(user)} chars")
print(f"property order    : {list(SCHEMA['properties'].keys())}")
print(f"max_tokens        : {MAX_TOKENS}   (from the worker config, not a literal)")
print("=" * 74)


def generate(n):
    body = {"model": "llama-3.3-70b",
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            # ⛔ READ FROM THE WORKER'S OWN CONFIG, never a literal. 12g's first
            # acceptance run truncated at a hardcoded 8192 that WAS production's
            # floor; hardcoding it again would silently under- or over-measure
            # the day the floor moves. `target_scene_count` is None for this
            # project, which is what the operator's real job sends, so this is
            # the budget stage 2 actually uses.
            "max_tokens": MAX_TOKENS, "temperature": 0.3, "top_p": 0.9,
            "response_format": response_format_for(SCHEMA)}
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
    fin = ch.get("finish_reason")
    raw = ch["message"]["content"]
    print(f"--- {LABEL} generation {n}: {dt:.0f}s  finish={fin}  "
          f"prompt_tokens={u.get('prompt_tokens')} completion_tokens={u.get('completion_tokens')}")
    if fin != "stop":
        ws = sum(1 for c in raw if c.isspace())
        print(f"    TRUNCATED - chars={len(raw)} whitespace={ws}")
        return None
    return json.loads(raw)


def flat_scenes(obj):
    """The MERGED sequence the API and the gate consume.

    Under contract-4 this is just `scenes`. Under contract-5 the merge is done
    by `shared.design.merge`, and this harness calls the same function the
    worker's parse calls so the census is over what production stores.
    """
    try:
        from shared.design.merge import merged_scene_sequence
        return merged_scene_sequence(obj)
    except ImportError:
        return list(obj.get("scenes") or [])


def census(n, obj):
    raw_scenes = flat_scenes(obj)
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

    # ⛔ WP-IVGS-12g's two new counts.
    #
    # `evidence_in_scenes` reads the model's OWN `scenes` array, before the
    # merge, and must be 0: the narrowed enum is what kills both the 117/117
    # excerpting contest and RC-Q9f limb 2's duplicate. Counting it after the
    # merge would count the evidence layer's own scenes and always say 6.
    raw_events = [x.get("instructional_event")
                  for x in (obj.get("scenes") or []) if isinstance(x, dict)]
    evidence_in_scenes = sum(1 for e in raw_events if e in ("practice", "assess"))
    # Per-LO presence of BOTH kinds, over the MERGED sequence. Grammar-guaranteed
    # under contract-6 and counted anyway, because that is what a belt is.
    per_lo = {oid: {"practice": 0, "assess": 0} for oid in IDS}
    for s in scenes:
        ev = s["instructional_event"]
        if ev in ("practice", "assess"):
            for oid in (s["serves_outcomes"] or []):
                if oid in per_lo:
                    per_lo[oid][ev] += 1
    both_present = all(v["practice"] >= 1 and v["assess"] >= 1
                       for v in per_lo.values())
    assessed_once = all(v["assess"] == 1 for v in per_lo.values())
    print(f"    ⛔ evidence events INSIDE the model's own scenes[] = "
          f"{evidence_in_scenes}   (contract-6 requires 0)")
    print(f"    per-LO practice AND assess present = {both_present}   "
          f"exactly one assess each = {assessed_once}   {json.dumps(per_lo)}")
    # The evidence scenes' ORIGIN, which contract-6 leaves free.
    ev_origins = [s["scene_origin"] for s in scenes
                  if s["instructional_event"] in ("practice", "assess")]
    print(f"    evidence-scene origins = {ev_origins}")

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
            "practice_scenes": [s for s in scenes
                                if s["instructional_event"] == "practice"],
            "rows": [r.as_dict() for r in rows],
            "assess_scenes": [s for s in scenes if s["instructional_event"] == "assess"]}


def run():
  results, contracts = [], []
  for n in range(1, N + 1):
      obj = generate(n)
      contracts.append(obj)
      results.append(census(n, obj) if obj else {"gen": n, "label": LABEL, "TRUNCATED": True})

  json.dump(contracts, open(f"{OUT}/{LABEL}-contracts.json", "w"), indent=2)
  json.dump(results, open(f"{OUT}/{LABEL}-census.json", "w"), indent=2)

  print("=" * 74)
  print(f"{LABEL} TOTALS vs BOTH baselines")
  print("   contract-4 (RC-Q9e, 6 gens): 83 scenes / 83 sourced / 0 designed / 0 assess")
  print("   contract-5 (RC-Q9f run B, 3 gens): 43 / 33 / 10 / 10, 6 refusals in 6 gens")
  ok = [r for r in results if not r.get("TRUNCATED")]
  print(f"  scenes  {sum(r['scenes'] for r in ok)}   sourced {sum(r['sourced'] for r in ok)}   "
        f"DESIGNED {sum(r['designed'] for r in ok)}   assess {sum(r['assess'] for r in ok)}   "
        f"practice {sum(r['practice'] for r in ok)}")
  print(f"  hard refusals per generation: {[len(r.get('refusals', [])) for r in results]}")
  print(f"  ⛔ evidence events in the model's own scenes[]: "
        f"{[r.get('evidence_in_scenes') for r in ok]}   (contract-6 requires all 0)")
  print(f"  per-LO practice AND assess present: "
        f"{[r.get('both_present') for r in ok]}")
  print(f"  exactly one assess per LO:          "
        f"{[r.get('assessed_once') for r in ok]}")
  print("=" * 74)


if __name__ == "__main__":
    run()
