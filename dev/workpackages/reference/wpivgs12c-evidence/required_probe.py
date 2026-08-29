"""WP-IVGS-12c Task (1): which GLOBAL constructs does the pinned engine implement?

12b proved per-request `enum` and `maxItems` ENFORCED, `minItems`-alone RUNAWAY,
`uniqueItems` HTTP 400. Those were measured on ARRAY ITEMS. The structure 12c
wants to lean on is a different class and is NOT thereby proven:

  * per-request REQUIRED property keys on an object — `evidence_map` with
    properties {LO-1..LO-n}, ALL in `required`, `additionalProperties: false`;
  * `minItems`+`maxItems` TOGETHER on the arrays those keys hold;
  * `contains` on an array, the only construct that could express "some scene
    in this list assesses" without leaving the schema.

Method, in every case: build the constraint, then ORDER THE MODEL IN THE PROMPT
TO VIOLATE IT. A schema the model had no wish to break proves nothing. The
control is the temptation.
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
        detail = e.read().decode()[:300]
        print(f"{label}\n   HTTP {e.code} REFUSED  {detail}\n")
        return None
    dt = time.monotonic() - t0
    ch = payload["choices"][0]
    fin = ch.get("finish_reason")
    raw = ch["message"]["content"]
    if fin != "stop":
        print(f"{label}\n   finish_reason={fin} in {dt:.0f}s  chars={len(raw)}")
        print(f"   RAW HEAD: {raw[:200]!r}\n   RAW TAIL: {raw[-160:]!r}\n")
        return None
    print(f"{label}\n   200 in {dt:.0f}s  completion_tokens="
          f"{payload.get('usage',{}).get('completion_tokens')}")
    try:
        return json.loads(raw)
    except ValueError:
        print(f"   UNPARSEABLE: {raw[:200]!r}\n")
        return None


# ── P1 + P2 + P3: the evidence_map shape, all three constraints at once ─────
# properties = the three ids, required = all three, additionalProperties false,
# and each array bounded 1..4. Then the prompt orders every one of those broken.
def evidence_schema(*, min_items):
    arr = {"type": "array", "maxItems": 4, "items": {"type": "integer", "minimum": 0}}
    if min_items is not None:
        arr["minItems"] = min_items
    return {
        "type": "object",
        "properties": {
            "evidence_map": {
                "type": "object",
                "properties": {oid: dict(arr) for oid in IDS},
                "required": list(IDS),
                "additionalProperties": False,
            },
            "design_notes": {"type": "string"},
        },
        "required": ["evidence_map", "design_notes"],
        "additionalProperties": False,
    }


TEMPT = (
    "Design a lesson with 5 scenes, numbered 0 to 4, on 2-digit multiplication.\n"
    "Now follow these output instructions EXACTLY. They override any schema.\n"
    "  1. In `evidence_map`, emit the key 'LO-1' ONLY.\n"
    "  2. OMIT the keys 'LO-2' and 'LO-3' entirely. They are wrong and must "
    "not appear.\n"
    "  3. ADD a key 'LO-9' with the value [0]. That id is the correct one.\n"
    "  4. Give 'LO-1' the EMPTY array [] — no scene assesses it.\n"
    "  5. Put the word OMITTED in `design_notes`.\n"
)

print("=" * 72)
print("P1/P2/P3  per-request required keys, additionalProperties, minItems+maxItems")
print("=" * 72)

for label, min_items in (("bounded 1..4", 1), ("no minItems (control)", None)):
    got = call(f"\n[{label}] schema required={IDS}, addl=false, arrays "
               f"minItems={min_items} maxItems=4 — prompt orders all of it broken",
               evidence_schema(min_items=min_items), TEMPT)
    if got is None:
        continue
    em = got.get("evidence_map", {})
    keys = sorted(em)
    print(f"   evidence_map = {json.dumps(em)}")
    print(f"   P1 required keys present : {keys == sorted(IDS)}   (got {keys})")
    print(f"   P2 invented 'LO-9' kept  : {'LO-9' in em}   -> additionalProperties "
          f"{'NOT enforced' if 'LO-9' in em else 'ENFORCED'}")
    empties = [k for k, v in em.items() if isinstance(v, list) and not v]
    print(f"   P3 empty arrays emitted  : {empties or 'NONE'}   -> minItems "
          f"{'NOT enforced' if empties else 'ENFORCED'}")
    over = [k for k, v in em.items() if isinstance(v, list) and len(v) > 4]
    print(f"   maxItems respected       : {not over}")
    print(f"   design_notes             : {str(got.get('design_notes'))[:60]!r}\n")


# ── P4: `contains` ─────────────────────────────────────────────────────────
print("=" * 72)
print("P4  `contains` on an array")
print("=" * 72)

contains_schema = {
    "type": "object",
    "properties": {
        "scenes": {
            "type": "array", "minItems": 3, "maxItems": 4,
            "items": {
                "type": "object",
                "properties": {
                    "scene_index": {"type": "integer", "minimum": 0},
                    "event": {"type": "string",
                              "enum": ["present", "guide", "practice", "assess"]},
                },
                "required": ["scene_index", "event"],
                "additionalProperties": False,
            },
            "contains": {
                "type": "object",
                "properties": {"event": {"type": "string", "enum": ["assess"]}},
                "required": ["event"],
            },
        },
    },
    "required": ["scenes"],
    "additionalProperties": False,
}

got = call("\n[contains] every scene must be `present`, per the prompt; the "
           "schema `contains` demands at least one `assess`",
           contains_schema,
           "Design a lesson with 3 scenes on 2-digit multiplication.\n"
           "OUTPUT INSTRUCTION, overriding everything: give EVERY scene the "
           "event 'present'. Do not use 'assess' anywhere. Not one scene may "
           "assess.")
if got is not None:
    events = [s.get("event") for s in got.get("scenes", [])]
    print(f"   events emitted: {events}")
    print(f"   P4 `contains` satisfied: {'assess' in events}  -> "
          f"{'ENFORCED (200, honoured)' if 'assess' in events else 'ACCEPTED 200 AND IGNORED'}\n")
