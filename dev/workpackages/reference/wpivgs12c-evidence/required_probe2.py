"""WP-IVGS-12c probe, second half. P3 came back a HANG, not a verdict.

`minItems: 1` + `maxItems: 4` on an integer array, with the prompt ordering an
empty array, produced `finish_reason=length` and 5,243 characters of WHITESPACE.
maxItems bounds the ELEMENTS; it does not bound the whitespace the grammar
still permits between `[` and the first element. So when the model's intent is
"nothing goes here", the decoder offers it an infinite legal corridor and it
takes it — RC-Q12's runaway in a shape `maxItems` does not close.

That matters because "the model wants to leave this outcome unassessed" is
EXACTLY the RC-Q9b behaviour the structure is meant to catch. So:

  P3b  is the hang caused by the ORDER, or by the shape? Same schema, neutral
       prompt. If a normal design run survives, the hazard is conditional.
  P3c  the honest middle: no order to emit [], but a lesson premise under which
       one outcome genuinely has no assessment. This is the production case.
  P5   the alternative structure — a REQUIRED SCALAR integer instead of a
       1..n array. An integer has no empty form either, so does it hang the
       same way, or does the model just pick a scene?
"""
import json, sys, time, urllib.request

BASE, KEY, MODEL = "http://192.168.1.91:8000", "ivgs-internal", "llama-3.3-70b"
IDS = ["LO-1", "LO-2", "LO-3"]


def call(label, schema, prompt, *, max_tokens=1500):
    body = {"model": MODEL, "max_tokens": max_tokens, "temperature": 0.0,
            "messages": [{"role": "system", "content": "You design lessons."},
                         {"role": "user", "content": prompt}],
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "probe", "strict": True, "schema": schema}}}
    req = urllib.request.Request(
        f"{BASE}/v1/chat/completions", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {KEY}"})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            payload = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        print(f"{label}\n   HTTP {e.code} REFUSED  {e.read().decode()[:300]}\n")
        return None
    dt = time.monotonic() - t0
    ch = payload["choices"][0]
    raw = ch["message"]["content"]
    if ch.get("finish_reason") != "stop":
        ws = sum(1 for c in raw if c.isspace())
        print(f"{label}\n   ⛔ finish_reason={ch.get('finish_reason')} in {dt:.0f}s  "
              f"chars={len(raw)}  whitespace={ws} ({100*ws//max(1,len(raw))}%)")
        print(f"   RAW HEAD: {raw[:120]!r}\n")
        return None
    print(f"{label}\n   200 in {dt:.0f}s  completion_tokens="
          f"{payload.get('usage',{}).get('completion_tokens')}")
    try:
        return json.loads(raw)
    except ValueError:
        print(f"   UNPARSEABLE: {raw[:200]!r}\n")
        return None


def bounded_array_schema():
    return {
        "type": "object",
        "properties": {
            "evidence_map": {
                "type": "object",
                "properties": {oid: {"type": "array", "minItems": 1, "maxItems": 4,
                                     "items": {"type": "integer", "minimum": 0}}
                               for oid in IDS},
                "required": list(IDS), "additionalProperties": False},
            "design_notes": {"type": "string"},
        },
        "required": ["evidence_map", "design_notes"], "additionalProperties": False,
    }


NEUTRAL = (
    "Design a lesson with 5 scenes, numbered 0 to 4, on 2-digit multiplication.\n"
    "LO-1 is computing the product. LO-2 is explaining the placeholder zero. "
    "LO-3 is checking your own work.\n"
    "In `evidence_map`, name for each outcome the scene indices that ASSESS it. "
    "Put one sentence in `design_notes`."
)

UNASSESSABLE = (
    "Design a lesson with 5 scenes, numbered 0 to 4, on 2-digit multiplication.\n"
    "LO-1 is computing the product. LO-2 is explaining the placeholder zero. "
    "LO-3 is checking your own work.\n"
    "⛔ This lesson is a DEMONSTRATION ONLY. Every one of the 5 scenes simply "
    "presents content. There is no practice item, no check, no quiz and no "
    "moment where the learner does anything at all. NOTHING in this lesson "
    "assesses LO-2 or LO-3; they are only explained.\n"
    "In `evidence_map`, name for each outcome the scene indices that ASSESS it, "
    "honestly. Put one sentence in `design_notes`."
)

print("=" * 72)
print("P3b  the SAME bounded 1..4 schema, a NEUTRAL prompt")
print("=" * 72)
got = call("\n[P3b] minItems=1 maxItems=4, nothing asks for an empty array",
           bounded_array_schema(), NEUTRAL)
if got:
    print(f"   evidence_map = {json.dumps(got.get('evidence_map'))}\n")

print("=" * 72)
print("P3c  the PRODUCTION case: the model's honest answer IS empty")
print("=" * 72)
got = call("\n[P3c] minItems=1 maxItems=4, a lesson that genuinely assesses nothing",
           bounded_array_schema(), UNASSESSABLE)
if got:
    print(f"   evidence_map = {json.dumps(got.get('evidence_map'))}")
    print(f"   design_notes = {str(got.get('design_notes'))[:100]!r}\n")

print("=" * 72)
print("P5  the alternative: a REQUIRED SCALAR integer, no array to leave empty")
print("=" * 72)
scalar = {
    "type": "object",
    "properties": {
        "evidence_map": {
            "type": "object",
            "properties": {
                oid: {"type": "object",
                      "properties": {
                          "assessed_by_scene": {"type": "integer", "minimum": 0},
                          "also_assessed_by": {"type": "array", "maxItems": 3,
                                               "items": {"type": "integer", "minimum": 0}}},
                      "required": ["assessed_by_scene", "also_assessed_by"],
                      "additionalProperties": False}
                for oid in IDS},
            "required": list(IDS), "additionalProperties": False},
        "design_notes": {"type": "string"},
    },
    "required": ["evidence_map", "design_notes"], "additionalProperties": False,
}
got = call("\n[P5] required scalar `assessed_by_scene`, same unassessable lesson",
           scalar, UNASSESSABLE)
if got:
    print(f"   evidence_map = {json.dumps(got.get('evidence_map'))}")
    print(f"   design_notes = {str(got.get('design_notes'))[:100]!r}\n")
