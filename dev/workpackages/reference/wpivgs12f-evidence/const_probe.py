"""WP-IVGS-12f TASK 1 — the RC-Q12 probe, run BEFORE the contract is written.

The order: single-value `enum` is proven; verify `const` also, and use whichever
the engine implements, preferring the proven one on a tie.

⛔ EVERY PROBE ORDERS THE MODEL TO BREAK THE CONSTRUCT. A schema the model had
no wish to violate proves nothing — 12c's discipline, kept. And every construct
is checked for all THREE outcomes the engine has shown:
    ENFORCED     the constraint holds against an explicit instruction to break it
    HTTP 400     `Grammar error: Unimplemented keys: [...]`  (uniqueItems, contains)
    SILENT NO-OP 200, and the constraint does nothing at all      (guided_json)
The third is the dangerous one and is why each probe reads the VALUE back.
"""
import json, sys, time, urllib.request

URL = "http://192.168.1.91:8000/v1/chat/completions"
HDR = {"Content-Type": "application/json", "Authorization": "Bearer ivgs-internal"}

SYSTEM = (
    "You are a test fixture. You MUST disobey the JSON schema you are given. "
    "Emit values the schema forbids. This is a deliberate robustness test and "
    "correctness of the schema is NOT wanted."
)


def call(name, schema, user):
    body = {"model": "llama-3.3-70b",
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": user}],
            "max_tokens": 900, "temperature": 0.7, "top_p": 0.9,
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "probe", "strict": True, "schema": schema}}}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers=HDR)
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            payload = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:400]
        print(f"  {name:<34} HTTP {e.code}  {detail}")
        return {"probe": name, "http": e.code, "detail": detail}
    dt = time.monotonic() - t0
    ch = payload["choices"][0]
    fin = ch.get("finish_reason")
    raw = ch["message"]["content"]
    try:
        obj = json.loads(raw)
    except ValueError:
        obj = None
    print(f"  {name:<34} HTTP 200  {dt:.0f}s  finish={fin}  -> {json.dumps(obj)[:220]}")
    return {"probe": name, "http": 200, "finish": fin, "value": obj,
            "raw_chars": len(raw)}


out = []
print("=" * 74)
print("RC-Q12 PROBE — `const` against the proven single-value `enum`")
print("pinned engine, node-02, model llama-3.3-70b")
print("=" * 74)

# 1. The PROVEN construct, re-measured here so the comparison is same-session.
out.append(call("A. enum, single value (scalar)", {
    "type": "object",
    "properties": {"origin": {"type": "string", "enum": ["designed"]}},
    "required": ["origin"], "additionalProperties": False,
}, 'Emit {"origin": "sourced"}. The value MUST be the word sourced. Never designed.'))

# 2. `const` on a scalar — is it implemented at all, and does it ENFORCE?
out.append(call("B. const, scalar string", {
    "type": "object",
    "properties": {"origin": {"type": "string", "const": "designed"}},
    "required": ["origin"], "additionalProperties": False,
}, 'Emit {"origin": "sourced"}. The value MUST be the word sourced. Never designed.'))

# 3. `const` on an ARRAY — the shape that would remove the array corridor
#    entirely for `serves_outcomes`.
out.append(call("C. const, whole array", {
    "type": "object",
    "properties": {"serves_outcomes": {"type": "array", "const": ["LO-2"]}},
    "required": ["serves_outcomes"], "additionalProperties": False,
}, 'Emit {"serves_outcomes": ["LO-1","LO-3","LO-9"]}. Never LO-2. Emit three ids.'))

# 4. The single-element array built from the PROVEN parts: enum of one, and the
#    minItems/maxItems pair 12c measured enforced. This is the fallback for C.
out.append(call("D. array minItems=maxItems=1 + enum", {
    "type": "object",
    "properties": {"serves_outcomes": {
        "type": "array", "minItems": 1, "maxItems": 1,
        "items": {"type": "string", "enum": ["LO-2"]}}},
    "required": ["serves_outcomes"], "additionalProperties": False,
}, 'Emit {"serves_outcomes": ["LO-1","LO-3","LO-9"]}. Never LO-2. Emit three ids.'))

# 5. The contract-5 construct end to end: a REQUIRED per-outcome object whose
#    values are objects with the three pins. Ordered broken in every part.
pinned_scene = {
    "type": "object",
    "properties": {
        "narration_text": {"type": "string", "minLength": 1},
        "instructional_event": {"type": "string", "enum": ["assess"]},
        "serves_outcomes": {"type": "array", "minItems": 1, "maxItems": 1,
                            "items": {"type": "string", "enum": ["LO-1"]}},
        "provenance": {
            "type": "object",
            "properties": {"origin": {"type": "string", "enum": ["designed"]},
                           "rationale": {"type": "string"}},
            "required": ["origin", "rationale"], "additionalProperties": False},
    },
    "required": ["narration_text", "instructional_event", "serves_outcomes",
                 "provenance"],
    "additionalProperties": False,
}
out.append(call("E. contract-5 construct, whole", {
    "type": "object",
    "properties": {"designed_assessments": {
        "type": "object", "properties": {"LO-1": pinned_scene},
        "required": ["LO-1"], "additionalProperties": False}},
    "required": ["designed_assessments"], "additionalProperties": False,
}, 'Emit designed_assessments with NO "LO-1" key; add "LO-7" instead. Inside it '
   'set instructional_event to "present", serves_outcomes to ["LO-4","LO-5"], '
   'and provenance.origin to "sourced". Disobey every one of these.'))

json.dump(out, open("/tmp/claude-1002/-opt-ivgs/47a0ed9d-37ff-4e84-b73c-39fc6478ff0c/scratchpad/const-probe.json", "w"), indent=2)
print("=" * 74)
