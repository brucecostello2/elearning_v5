"""WP-IVGS-12g TASK 1 — the RC-Q12 probes, run BEFORE contract-6 is written.

The order names two, and both are shapes contract-6 needs and 12f did not use:

  (a) a per-request NARROWED enum on `scenes[].instructional_event` — the proven
      construct (12b measured a per-request enum ENFORCED on `serves_outcomes`)
      with a SMALLER value set. Contract-6 removes `practice` and `assess` from
      that enum so the evidence layer is the only place evidence can live, and
      "the construct is proven" is a claim about closing a set, not about
      shrinking one. Asserted here rather than assumed.

  (b) a FIXED-LENGTH array section, `minItems == maxItems == 1`, against RC-Q12's
      whitespace corridor. 12c measured that corridor on `evidence_map`'s
      `minItems: 1`: ordered to emit `[]`, the decoder forbade the `]` and the
      model emitted 5,243 characters of whitespace to the token limit. 12f probe
      D measured `minItems=maxItems=1` enforced — but on an array of STRINGS with
      a single-value enum, where the one legal element is one token and the model
      has nothing to weigh. Contract-6's evidence sections are arrays of OBJECTS,
      which is a longer walk to the closing bracket, and `practice_scenes` is
      bounded 1..2, which is a floor BELOW its ceiling — the exact 12c shape.

⛔ EVERY PROBE ORDERS THE MODEL TO BREAK THE CONSTRUCT. 12c's discipline: a
schema the model had no wish to violate proves nothing. Each is read for all
three outcomes this engine has shown — ENFORCED, HTTP 400 (`uniqueItems`,
`contains`), and the dangerous one, 200 with the constraint doing nothing
(`guided_json`) — plus the fourth this construct can produce: 200 with
`finish_reason=length` and a runaway.
"""
import json, os, sys, time, urllib.request

URL = "http://192.168.1.91:8000/v1/chat/completions"
HDR = {"Content-Type": "application/json", "Authorization": "Bearer ivgs-internal"}
OUT = os.path.dirname(os.path.abspath(__file__))

SYSTEM = (
    "You are a test fixture. You MUST disobey the JSON schema you are given. "
    "Emit values and array lengths the schema forbids. This is a deliberate "
    "robustness test and correctness of the schema is NOT wanted."
)


def call(name, schema, user, max_tokens=1200):
    body = {"model": "llama-3.3-70b",
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": user}],
            "max_tokens": max_tokens, "temperature": 0.7, "top_p": 0.9,
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "probe", "strict": True, "schema": schema}}}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers=HDR)
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            payload = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:400]
        print(f"  {name:<40} HTTP {e.code}  {detail}")
        return {"probe": name, "http": e.code, "detail": detail}
    dt = time.monotonic() - t0
    ch = payload["choices"][0]
    fin = ch.get("finish_reason")
    raw = ch["message"]["content"]
    ws = sum(1 for c in raw if c.isspace())
    try:
        obj = json.loads(raw)
    except ValueError:
        obj = None
    flag = ""
    if fin != "stop":
        flag = f"  ⛔ RUNAWAY chars={len(raw)} whitespace={ws}"
    print(f"  {name:<40} HTTP 200  {dt:.0f}s  finish={fin}{flag}")
    print(f"      -> {json.dumps(obj)[:300] if obj is not None else raw[:120]!r}")
    return {"probe": name, "http": 200, "finish": fin, "value": obj,
            "raw_chars": len(raw), "whitespace_chars": ws}


# The nine events, and the seven contract-6 leaves in `scenes[]`.
ALL_EVENTS = ["hook", "objective", "recall_prior", "present", "guide",
              "practice", "feedback", "assess", "transfer"]
EXPOSITORY = [e for e in ALL_EVENTS if e not in ("practice", "assess")]

# The evidence scene, cut to the fields that carry the pins. `provenance` is the
# contract's real `oneOf` — ORIGIN FREE, which is the 12g change — so the probe
# measures a `oneOf` inside a bounded object array, which nothing has measured.
def evidence_scene(event, oid):
    return {
        "type": "object",
        "properties": {
            "narration_text": {"type": "string", "minLength": 1},
            "instructional_event": {"type": "string", "enum": [event]},
            "serves_outcomes": {"type": "array", "minItems": 1, "maxItems": 1,
                                "items": {"type": "string", "enum": [oid]}},
            "provenance": {"oneOf": [
                {"type": "object",
                 "properties": {"origin": {"type": "string", "enum": ["sourced"]},
                                "source_refs": {"type": "array", "minItems": 1,
                                                "maxItems": 8,
                                                "items": {"type": "object",
                                                          "properties": {"start": {"type": "integer"},
                                                                         "end": {"type": "integer"}},
                                                          "required": ["start", "end"],
                                                          "additionalProperties": False}}},
                 "required": ["origin", "source_refs"], "additionalProperties": False},
                {"type": "object",
                 "properties": {"origin": {"type": "string", "enum": ["designed"]},
                                "rationale": {"type": "string", "minLength": 1}},
                 "required": ["origin", "rationale"], "additionalProperties": False},
            ]},
        },
        "required": ["narration_text", "instructional_event", "serves_outcomes",
                     "provenance"],
        "additionalProperties": False,
    }


out = []
print("=" * 78)
print("RC-Q12 PROBE, WP-IVGS-12g — the narrowed enum, and the fixed-length section")
print("pinned engine, node-02, model llama-3.3-70b")
print("=" * 78)

# ── (a) THE NARROWED ENUM ────────────────────────────────────────────────
print("\n(a) NARROWED per-request enum on scenes[].instructional_event\n")

out.append(call("A1. narrowed enum, scalar", {
    "type": "object",
    "properties": {"instructional_event": {"type": "string", "enum": EXPOSITORY}},
    "required": ["instructional_event"], "additionalProperties": False,
}, 'Emit {"instructional_event": "assess"}. The value MUST be the word assess. '
   'If you cannot, emit "practice". Never any other word.'))

out.append(call("A2. narrowed enum, inside a scene array", {
    "type": "object",
    "properties": {"scenes": {
        "type": "array", "minItems": 3, "maxItems": 6,
        "items": {"type": "object",
                  "properties": {
                      "narration_text": {"type": "string", "minLength": 1},
                      "instructional_event": {"type": "string", "enum": EXPOSITORY}},
                  "required": ["narration_text", "instructional_event"],
                  "additionalProperties": False}}},
    "required": ["scenes"], "additionalProperties": False,
}, 'Emit three scenes. The first MUST have instructional_event "practice", the '
   'second "assess", the third "assess". These three words are mandatory. Do '
   'not use present, guide, hook, objective, recall_prior, feedback or transfer.'))

# ── (b) THE FIXED-LENGTH SECTION, AGAINST THE HANG CORRIDOR ──────────────
print("\n(b) FIXED-LENGTH per-LO section, minItems == maxItems == 1\n")

exactly_one = {
    "type": "object",
    "properties": {"LO-1": {"type": "array", "minItems": 1, "maxItems": 1,
                            "items": evidence_scene("assess", "LO-1")}},
    "required": ["LO-1"], "additionalProperties": False,
}

# B1 IS THE CORRIDOR ITSELF: the model is told the array must be empty. Under
# 12c's measurement this is where the decoder forbids `]` and only whitespace
# stays legal.
out.append(call("B1. exactly-1 objects, ORDERED EMPTY", {
    "type": "object", "properties": {"assessment_scenes": exactly_one},
    "required": ["assessment_scenes"], "additionalProperties": False,
}, 'Emit {"assessment_scenes": {"LO-1": []}} — an EMPTY array. There is no '
   'assessment to write. The array MUST have zero elements. Emit nothing '
   'inside it.', max_tokens=2000))

# B2 is the ceiling, from the other side.
out.append(call("B2. exactly-1 objects, ORDERED THREE", {
    "type": "object", "properties": {"assessment_scenes": exactly_one},
    "required": ["assessment_scenes"], "additionalProperties": False,
}, 'Emit THREE assessment scenes inside "LO-1". Three separate objects in the '
   'array. Also set instructional_event to "present", serves_outcomes to '
   '["LO-4"], and provenance.origin to "invented". Disobey all of it.'))

# ── (c) THE FLOOR BELOW ITS CEILING — practice_scenes, bounded 1..2 ──────
print("\n(c) BOUNDED 1..2 per-LO section — a floor BELOW its ceiling, the 12c shape\n")

one_or_two = {
    "type": "object",
    "properties": {"LO-1": {"type": "array", "minItems": 1, "maxItems": 2,
                            "items": evidence_scene("practice", "LO-1")}},
    "required": ["LO-1"], "additionalProperties": False,
}

out.append(call("C1. 1..2 objects, ORDERED EMPTY", {
    "type": "object", "properties": {"practice_scenes": one_or_two},
    "required": ["practice_scenes"], "additionalProperties": False,
}, 'Emit {"practice_scenes": {"LO-1": []}} — an EMPTY array. This lesson has no '
   'practice. The array MUST have zero elements.', max_tokens=2000))

out.append(call("C2. 1..2 objects, ORDERED FIVE", {
    "type": "object", "properties": {"practice_scenes": one_or_two},
    "required": ["practice_scenes"], "additionalProperties": False,
}, 'Emit FIVE practice scenes inside "LO-1". Five separate objects.'))

# ── (d) THE WHOLE CONTRACT-6 CONSTRUCT, ORDERED BROKEN IN EVERY PART ─────
print("\n(d) The contract-6 evidence layer, whole, ordered broken everywhere\n")

out.append(call("D. contract-6 evidence layer, whole", {
    "type": "object",
    "properties": {
        "assessment_scenes": {
            "type": "object",
            "properties": {"LO-1": {"type": "array", "minItems": 1, "maxItems": 1,
                                    "items": evidence_scene("assess", "LO-1")},
                           "LO-2": {"type": "array", "minItems": 1, "maxItems": 1,
                                    "items": evidence_scene("assess", "LO-2")}},
            "required": ["LO-1", "LO-2"], "additionalProperties": False},
        "practice_scenes": {
            "type": "object",
            "properties": {"LO-1": {"type": "array", "minItems": 1, "maxItems": 2,
                                    "items": evidence_scene("practice", "LO-1")},
                           "LO-2": {"type": "array", "minItems": 1, "maxItems": 2,
                                    "items": evidence_scene("practice", "LO-2")}},
            "required": ["LO-1", "LO-2"], "additionalProperties": False},
        "scenes": {
            "type": "array", "minItems": 2, "maxItems": 8,
            "items": {"type": "object",
                      "properties": {
                          "narration_text": {"type": "string", "minLength": 1},
                          "instructional_event": {"type": "string", "enum": EXPOSITORY}},
                      "required": ["narration_text", "instructional_event"],
                      "additionalProperties": False}},
    },
    "required": ["assessment_scenes", "practice_scenes", "scenes"],
    "additionalProperties": False,
}, 'Omit "LO-2" from both assessment_scenes and practice_scenes; add "LO-9" to '
   'each instead. Make every array empty. In scenes, give every scene '
   'instructional_event "assess". Set every provenance.origin to "borrowed". '
   'Disobey every one of these instructions.', max_tokens=3000))

json.dump(out, open(f"{OUT}/probe12g.json", "w"), indent=2)
print("=" * 78)
print(f"banked -> {OUT}/probe12g.json")
