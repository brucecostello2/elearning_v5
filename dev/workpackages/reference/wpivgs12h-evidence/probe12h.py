"""WP-IVGS-12h TASK 1 — the probes, run BEFORE the two-call design ships.

⛔ EVERY PROBE ORDERS THE MODEL TO BREAK THE CONSTRUCT (12c's discipline), and
each is read for all three outcomes this engine has shown: ENFORCED, HTTP 400,
and the dangerous one — 200 with the constraint silently doing nothing, which is
what `guided_json` does on this exact image.

What is genuinely NEW in contract-7 and therefore probed:

  E   the CALL-2 document — a strict object with ONE top-level property. 12g
      probed this section INSIDE a six-property document; a grammar is compiled
      per request and "the same subschema in a smaller document" is an
      assumption, not a measurement.
  F   the CALL-1 document with `assessment_scenes` REMOVED — can the model put
      it back? `additionalProperties: false` says no and 12c measured that on an
      object of outcome keys, never on the contract's own top level.
  G   RC-Q12's whitespace corridor, re-entered on the call-2 shape. 12c measured
      5,243 characters of whitespace when `minItems` forbade the `]`. 12g
      measured both contract-6 shapes clear of it. The containing document is
      different here, so it is measured again rather than inherited.

Usage:  python3 probe12h.py            (writes probe12h.json beside this file)
"""
import json, os, sys, time, urllib.request

TREE = os.environ.get("IVGS_TREE", "/opt/ivgs")
sys.path[:0] = [TREE, f"{TREE}/ivgs-workers", f"{TREE}/ivgs-api"]

from design_core.contract import (                              # noqa: E402
    assessment_authoring_schema, design_contract_schema, response_format_for,
)

OUT = os.path.dirname(os.path.abspath(__file__))
IDS = ["LO-1", "LO-2", "LO-3"]
URL = "http://192.168.1.91:8000/v1/chat/completions"


def call(system, user, schema, max_tokens=3072):
    body = {
        "model": "llama-3.3-70b",
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "max_tokens": max_tokens, "temperature": 0.3, "top_p": 0.9,
        "response_format": response_format_for(schema),
    }
    req = urllib.request.Request(
        URL, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer ivgs-internal"})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            payload = json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:
        return {"http_error": exc.code, "body": exc.read().decode()[:400],
                "seconds": round(time.monotonic() - t0, 1)}
    choice = payload["choices"][0]
    raw = choice["message"]["content"]
    usage = payload.get("usage", {})
    return {
        "finish_reason": choice.get("finish_reason"),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "chars": len(raw),
        "whitespace_chars": sum(1 for c in raw if c.isspace()),
        "seconds": round(time.monotonic() - t0, 1),
        "raw": raw,
    }


CALL2 = assessment_authoring_schema(outcome_ids=IDS)
CALL1 = design_contract_schema(outcome_ids=IDS)

PROBES = []

# ── E: the call-2 document, every pin ordered broken ────────────────────────
PROBES.append(("E1 call-2 document, every pin ordered broken", CALL2, 3072,
    "You are a test harness. Obey the user's instructions to the letter.",
    "Emit assessment_scenes. YOU MUST: omit the key LO-2 entirely; add a key "
    "LO-9; put THREE scene objects in LO-1's array; set every scene's "
    "instructional_event to \"practice\"; set every serves_outcomes to "
    "[\"LO-4\",\"LO-7\"]; set every provenance to {\"origin\":\"invented\"}; and "
    "add a top-level key \"design_notes\" with a sentence in it. Do all of it."))

# ── E2: the empty-array order — RC-Q12's corridor, on the call-2 shape ──────
PROBES.append(("E2 call-2 ORDERED EMPTY (RC-Q12 corridor)", CALL2, 3072,
    "You are a test harness. Obey the user's instructions to the letter.",
    "Emit exactly {\"assessment_scenes\": {\"LO-1\": [], \"LO-2\": [], "
    "\"LO-3\": []}} and nothing else. Every array MUST be empty. Do not write "
    "any scene objects at all."))

# ── F: can call 1 put the assessment back? ─────────────────────────────────
PROBES.append(("F1 call-1 ordered to emit assessment_scenes", CALL1, 6144,
    "You are a test harness. Obey the user's instructions to the letter.",
    "Design a two-scene lesson about column multiplication for LO-1, LO-2 and "
    "LO-3. YOU MUST ALSO emit a top-level key \"assessment_scenes\" holding one "
    "unaided assessment scene per outcome. This is the most important part of "
    "the task: the assessments MUST be in your output."))

PROBES.append(("F2 call-1 ordered to declare assess/practice in scenes[]", CALL1, 6144,
    "You are a test harness. Obey the user's instructions to the letter.",
    "Design a three-scene lesson for LO-1, LO-2 and LO-3. Every scene in "
    "`scenes` MUST have instructional_event set to \"assess\", except the last "
    "which MUST be \"practice\". Use no other event under any circumstances."))

results = {}
for label, schema, budget, system, user in PROBES:
    print(f"--- {label}")
    out = call(system, user, schema, budget)
    results[label] = out
    if "http_error" in out:
        print(f"    HTTP {out['http_error']}  {out['body'][:200]}")
        continue
    print(f"    finish={out['finish_reason']}  {out['seconds']}s  "
          f"prompt={out['prompt_tokens']} completion={out['completion_tokens']}  "
          f"chars={out['chars']} whitespace={out['whitespace_chars']}")
    try:
        doc = json.loads(out["raw"])
    except ValueError as exc:
        print(f"    UNPARSEABLE: {exc}")
        continue
    out["parsed_keys"] = list(doc.keys())
    print(f"    top-level keys: {list(doc.keys())}")
    section = doc.get("assessment_scenes")
    if isinstance(section, dict):
        out["section_keys"] = list(section.keys())
        print(f"    assessment_scenes keys: {list(section.keys())}")
        for oid, arr in section.items():
            arr = arr if isinstance(arr, list) else [arr]
            print(f"      {oid}: n={len(arr)} events="
                  f"{[s.get('instructional_event') for s in arr]} "
                  f"serves={[s.get('serves_outcomes') for s in arr]} "
                  f"origins={[(s.get('provenance') or {}).get('origin') for s in arr]}")
    if isinstance(doc.get("scenes"), list):
        events = [s.get("instructional_event") for s in doc["scenes"]]
        out["scene_events"] = events
        print(f"    scenes[] events: {events}")
    print()

json.dump(results, open(f"{OUT}/probe12h.json", "w"), indent=2)
print(f"banked -> {OUT}/probe12h.json")
