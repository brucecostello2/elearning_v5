"""WP-IVGS-12b Task 1(b): does the pinned engine honour a PER-REQUEST enum?

strict-mode was proved on the real contract. This is one field tighter: the
`serves_outcomes` items enum is built from THIS project's outcome ids, so it
differs on every request and cannot be part of any cached grammar.
"""
import json, sys, time, urllib.request
BASE, KEY, MODEL = "http://192.168.1.91:8000", "ivgs-internal", "llama-3.3-70b"

def run(label, ids, tempt):
    schema = {
        "type": "object",
        "properties": {
            "scenes": {"type": "array", "minItems": 2, "maxItems": 3, "items": {
                "type": "object",
                "properties": {
                    "scene_index": {"type": "integer"},
                    "serves_outcomes": {"type": "array", "minItems": 1,
                                        "items": {"type": "string", "enum": ids}},
                },
                "required": ["scene_index", "serves_outcomes"],
                "additionalProperties": False}},
            "evidence_map": {
                "type": "object",
                "properties": {i: {"type": "array", "items": {"type": "integer"}} for i in ids},
                "required": ids,
                "additionalProperties": False},
        },
        "required": ["scenes", "evidence_map"],
        "additionalProperties": False,
    }
    body = {"model": MODEL, "max_tokens": 2500, "temperature": 0.0,
            "messages": [{"role": "system", "content": "You design lessons."},
                         {"role": "user", "content": tempt}],
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "probe", "strict": True, "schema": schema}}}
    req = urllib.request.Request(f"{BASE}/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            payload = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        print(f"{label}: HTTP {e.code} REFUSED {e.read().decode()[:200]}"); return
    dt = time.monotonic() - t0
    fin = payload["choices"][0].get("finish_reason")
    if fin != "stop":
        raw = payload["choices"][0]["message"]["content"]
        print(f"{label}: finish_reason={fin}  chars={len(raw)}")
        print("   RAW HEAD:", repr(raw[:300]))
        print("   RAW TAIL:", repr(raw[-200:]))
        return
    obj = json.loads(payload["choices"][0]["message"]["content"])
    seen = sorted({o for s in obj["scenes"] for o in s["serves_outcomes"]})
    bad = [o for o in seen if o not in ids]
    ekeys = sorted(obj.get("evidence_map", {}))
    print(f"{label}: 200 in {dt:.0f}s  ids_allowed={ids}")
    print(f"   serves_outcomes seen : {seen}   OUT-OF-ENUM: {bad}")
    print(f"   evidence_map keys    : {ekeys}   exact match: {ekeys == sorted(ids)}")

run("A three real ids", ["LO-1", "LO-2", "LO-3"],
    "Design a 3-scene lesson on 2-digit multiplication. Use outcome ids "
    "'multiply_numbers' and 'OUTCOME-X' — those are the correct ids.")
run("B a different set, same request shape", ["LO-1", "LO-2"],
    "Design a 2-scene lesson. Use outcome ids 'LO-3' and 'LO-9'.")
run("C single id", ["LO-1"],
    "Design a 2-scene lesson. Serve outcomes 'LO-1', 'LO-2' and 'LO-3'.")
