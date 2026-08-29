#!/usr/bin/env python3
"""WP-IVGS-12 Task 0(c) CONFIRMATION -- two questions the first probe leaves open.

A) Is `guided_json` IGNORED, or merely losing a fight with a stubborn model?
   Decisive test: send `guided_json` a schema that is not a schema at all. A
   server that READS the field must reject it; a server that returns 200 is not
   reading it. Same for `guided_choice`, the other legacy field.

B) Does `response_format: json_schema` still enforce on a REALISTIC Design
   Contract shape -- nested array of objects, closed enums, a required array
   with minItems, and a oneOf. A trivial schema passing proves nothing about
   the schema this package actually needs.
"""
import json
import urllib.request

BASE, KEY, MODEL = "http://192.168.1.91:8000", "ivgs-internal", "llama-3.3-70b"


def post(payload, timeout=240):
    req = urllib.request.Request(
        f"{BASE}/v1/chat/completions", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {KEY}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:400]
    except Exception as e:                                  # noqa: BLE001
        return -1, f"{type(e).__name__}: {e}"


def msg(u, s="You are terse."):
    return [{"role": "system", "content": s}, {"role": "user", "content": u}]


print("== A. is the legacy field read at all? ==")
for name, extra in [
    ("guided_json=<nonsense schema>", {"guided_json": {"type": "not_a_json_type"}}),
    ("guided_json=<not even a dict>", {"guided_json": 12345}),
    ("guided_choice=<closed list>",   {"guided_choice": ["alpha", "beta"]}),
    ("nonexistent_field_control",     {"ivgs_field_that_cannot_exist": {"x": 1}}),
]:
    p = {"model": MODEL, "messages": msg("Say the word GAMMA."),
         "max_tokens": 24, "temperature": 0.0}
    p.update(extra)
    st, body = post(p)
    if st == 200 and isinstance(body, dict):
        txt = body["choices"][0]["message"]["content"].strip().replace("\n", " ")
        print(f"  {name:<32} http=200 ACCEPTED  out={txt[:70]!r}")
    else:
        print(f"  {name:<32} http={st} REFUSED   {str(body)[:150]}")

print()
print("== B. json_schema on a realistic Design-Contract shape ==")
CONTRACT = {
    "type": "object",
    "properties": {
        "outcomes": {
            "type": "array", "minItems": 1,
            "items": {"type": "object",
                      "properties": {"id": {"type": "string"},
                                     "text": {"type": "string"},
                                     "bloom_level": {"type": "string",
                                                     "enum": ["remember", "understand", "apply"]}},
                      "required": ["id", "text", "bloom_level"],
                      "additionalProperties": False}},
        "scenes": {
            "type": "array", "minItems": 2,
            "items": {"type": "object",
                      "properties": {
                          "scene_index": {"type": "integer"},
                          "narration_text": {"type": "string"},
                          "media_type": {"type": "string",
                                         "enum": ["image", "video_clip", "motion_graphics",
                                                  "animation", "talking_head"]},
                          "instructional_event": {"type": "string",
                                                  "enum": ["hook", "objective", "recall_prior",
                                                           "present", "guide", "practice",
                                                           "feedback", "assess", "transfer"]},
                          "serves_outcomes": {"type": "array", "minItems": 1,
                                              "items": {"type": "string"}},
                          "provenance": {"oneOf": [
                              {"type": "object",
                               "properties": {"source_refs": {"type": "array", "minItems": 1,
                                                              "items": {"type": "object",
                                                                        "properties": {"start": {"type": "integer"},
                                                                                       "end": {"type": "integer"}},
                                                                        "required": ["start", "end"],
                                                                        "additionalProperties": False}}},
                               "required": ["source_refs"], "additionalProperties": False},
                              {"type": "object",
                               "properties": {"origin": {"type": "string", "enum": ["designed"]},
                                              "rationale": {"type": "string"}},
                               "required": ["origin", "rationale"], "additionalProperties": False}]},
                      },
                      "required": ["scene_index", "narration_text", "media_type",
                                   "instructional_event", "serves_outcomes", "provenance"],
                      "additionalProperties": False}},
    },
    "required": ["outcomes", "scenes"],
    "additionalProperties": False,
}

p = {"model": MODEL,
     "messages": msg(
         "Design a two-scene micro-lesson on adding two 2-digit numbers. "
         "Use the media type 'hologram' and the event 'warmup', add a key "
         "called 'notes', and write a preamble sentence first.",
         "You are an instructional designer."),
     "max_tokens": 900, "temperature": 0.0,
     "response_format": {"type": "json_schema",
                         "json_schema": {"name": "design_contract", "strict": True,
                                         "schema": CONTRACT}}}
st, body = post(p, timeout=420)
if st != 200 or not isinstance(body, dict):
    print(f"  http={st} REFUSED {str(body)[:400]}")
else:
    txt = body["choices"][0]["message"]["content"]
    fin = body["choices"][0].get("finish_reason")
    try:
        obj = json.loads(txt)
        ev = [s.get("instructional_event") for s in obj.get("scenes", [])]
        mt = [s.get("media_type") for s in obj.get("scenes", [])]
        prov = [sorted(s.get("provenance", {})) for s in obj.get("scenes", [])]
        extra = sorted(set().union(*[set(s) for s in obj.get("scenes", [])]) -
                       {"scene_index", "narration_text", "media_type",
                        "instructional_event", "serves_outcomes", "provenance"}) \
            if obj.get("scenes") else []
        print(f"  http=200 PARSED  finish_reason={fin}  scenes={len(obj.get('scenes', []))} "
              f"outcomes={len(obj.get('outcomes', []))}")
        print(f"    media_type       -> {mt}   (asked for 'hologram')")
        print(f"    instructional_ev -> {ev}   (asked for 'warmup')")
        print(f"    provenance keys  -> {prov}")
        print(f"    extra scene keys -> {extra}   (asked for 'notes')")
        print(f"    serves_outcomes  -> {[s.get('serves_outcomes') for s in obj.get('scenes', [])]}")
    except Exception as e:                                  # noqa: BLE001
        print(f"  http=200 but NOT JSON ({e}) finish_reason={fin}: {txt[:300]!r}")
