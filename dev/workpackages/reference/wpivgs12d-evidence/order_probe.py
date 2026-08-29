"""WP-IVGS-12d Task 1: does SCHEMA DECLARATION ORDER bind GENERATION ORDER?

Everything in 12d rests on this. `assessment_plan` is only Foundation §1's
sequence if the model must emit it BEFORE it has written a scene; if the decoder
lets the model choose, the plan is a post-hoc rationalisation of scenes it has
already designed and 12d is theatre.

12c observed the emission order matching the `properties` dict on three real
contracts — but that is an OBSERVATION with two candidate causes (the grammar,
or the model simply preferring to write scenes first) and it did not separate
them. This separates them, with the 12c method: build the constraint, then
ORDER THE MODEL IN THE PROMPT TO VIOLATE IT, in BOTH directions, so a "pass"
cannot be the model's own preference wearing the grammar's coat.

  A  properties [plan, scenes]  + prompt demands SCENES first
  B  properties [scenes, plan]  + prompt demands PLAN   first
  C  properties [scenes, plan]  but required [plan, scenes] — which list rules?

A and B must disagree with the prompt in OPPOSITE directions. If both follow
the schema, declaration order binds and the model's preference is not the cause.
"""
import json, time, urllib.request

BASE, KEY, MODEL = "http://192.168.1.91:8000", "ivgs-internal", "llama-3.3-70b"
IDS = ["LO-1", "LO-2", "LO-3"]

PLAN = {
    "type": "object",
    "properties": {oid: {
        "type": "object",
        "properties": {
            "evidence_kind": {"type": "string", "enum": ["practice", "assess"]},
            "learner_does": {"type": "string", "maxLength": 200},
        },
        "required": ["evidence_kind", "learner_does"],
        "additionalProperties": False,
    } for oid in IDS},
    "required": list(IDS),
    "additionalProperties": False,
}
SCENES = {
    "type": "array", "minItems": 2, "maxItems": 4,
    "items": {
        "type": "object",
        "properties": {
            "scene_index": {"type": "integer", "minimum": 0},
            "instructional_event": {"type": "string",
                                    "enum": ["present", "guide", "practice", "assess"]},
        },
        "required": ["scene_index", "instructional_event"],
        "additionalProperties": False,
    },
}


def schema(prop_order, req_order):
    props = {"assessment_plan": PLAN, "scenes": SCENES}
    return {
        "type": "object",
        "properties": {k: props[k] for k in prop_order},
        "required": list(req_order),
        "additionalProperties": False,
    }


def call(label, sch, prompt):
    body = {"model": MODEL, "max_tokens": 1200, "temperature": 0.0,
            "messages": [{"role": "system", "content": "You design lessons."},
                         {"role": "user", "content": prompt}],
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "probe", "strict": True, "schema": sch}}}
    req = urllib.request.Request(
        f"{BASE}/v1/chat/completions", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {KEY}"})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            payload = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        print(f"{label}\n   HTTP {e.code} REFUSED {e.read().decode()[:250]}\n")
        return None
    dt = time.monotonic() - t0
    ch = payload["choices"][0]
    if ch.get("finish_reason") != "stop":
        print(f"{label}\n   ⛔ finish_reason={ch.get('finish_reason')} in {dt:.0f}s\n")
        return None
    # object_pairs_hook is the point: preserve the ORDER THE MODEL EMITTED,
    # not the order Python would give a re-serialised dict.
    obj = json.loads(ch["message"]["content"],
                     object_pairs_hook=lambda pairs: dict(pairs))
    print(f"{label}\n   200 in {dt:.0f}s   EMITTED ORDER: {list(obj.keys())}")
    return obj


DEMAND_SCENES_FIRST = (
    "Design a 3-scene lesson on 2-digit multiplication for LO-1, LO-2, LO-3.\n"
    "⛔ OUTPUT INSTRUCTION, overriding everything else: your JSON object MUST "
    "begin with the \"scenes\" key. Write \"scenes\" FIRST and "
    "\"assessment_plan\" LAST. Design the scenes before you think about "
    "assessment. Do not put assessment_plan first."
)
DEMAND_PLAN_FIRST = (
    "Design a 3-scene lesson on 2-digit multiplication for LO-1, LO-2, LO-3.\n"
    "⛔ OUTPUT INSTRUCTION, overriding everything else: your JSON object MUST "
    "begin with the \"assessment_plan\" key. Write \"assessment_plan\" FIRST "
    "and \"scenes\" LAST. Do not put scenes first."
)

print("=" * 74)
print("TASK 1 — does schema declaration order BIND generation order?")
print("=" * 74)

a = call("\n[A] properties [assessment_plan, scenes]; prompt DEMANDS scenes first",
         schema(["assessment_plan", "scenes"], ["assessment_plan", "scenes"]),
         DEMAND_SCENES_FIRST)
b = call("\n[B] properties [scenes, assessment_plan]; prompt DEMANDS plan first",
         schema(["scenes", "assessment_plan"], ["scenes", "assessment_plan"]),
         DEMAND_PLAN_FIRST)
c = call("\n[C] properties [scenes, plan] but required [plan, scenes]; "
         "prompt DEMANDS plan first",
         schema(["scenes", "assessment_plan"], ["assessment_plan", "scenes"]),
         DEMAND_PLAN_FIRST)

print("\n" + "=" * 74)
print("VERDICT")
print("=" * 74)
ok_a = a is not None and list(a.keys())[0] == "assessment_plan"
ok_b = b is not None and list(b.keys())[0] == "scenes"
print(f"  A schema wins over a scenes-first order : {ok_a}")
print(f"  B schema wins over a plan-first order   : {ok_b}")
if c is not None:
    ruler = "properties" if list(c.keys())[0] == "scenes" else "required"
    print(f"  C the controlling list is              : {ruler.upper()}")
print()
if ok_a and ok_b:
    print("  ✅ DECLARATION ORDER BINDS, IN BOTH DIRECTIONS, AGAINST THE PROMPT.")
    print("     `assessment_plan` declared first is emitted before any scene")
    print("     exists — Foundation §1's sequence, enforced by the decoder.")
else:
    print("  ⛔ ORDER IS NOT ENFORCEABLE. Task 1 says STOP and report:")
    print("     the fallback is a two-call design and needs the operator's ruling.")
