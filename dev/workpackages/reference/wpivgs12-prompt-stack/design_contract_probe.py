#!/usr/bin/env python3
"""WP-IVGS-12 Task 4 — does the REAL Design Contract schema constrain the pinned engine?

Probe 0(c) proved `response_format: json_schema` enforces on a hand-built
skeleton. That is not the same claim as "it enforces on OUR schema": the real
one is 6.9 kB, closes five enums, carries a `oneOf` provenance, and uses
nullable types for the optional members. A grammar can be accepted and still be
too large, and a nullable enum is exactly the construct a JSON-Schema-to-grammar
compiler is most likely to reject.

Run from node-01 against node-02.
"""
import json
import sys
import time
import urllib.request

sys.path.insert(0, "/opt/ivgs")
sys.path.insert(0, "/opt/ivgs/ivgs-workers")
from design_core.contract import design_contract_schema, response_format_for  # noqa: E402

BASE, KEY, MODEL = "http://192.168.1.91:8000", "ivgs-internal", "llama-3.3-70b"

SCRIPT = (
    "Let's learn how to multiply two-digit numbers. This might seem tricky, but "
    "we'll break it down. Take 23 times 14. Write 23 above 14, lining up the "
    "ones. First multiply 4 by 3, which is 12 — write the 2, carry the 1. Then "
    "4 times 2 is 8, plus the carried 1 makes 9. So the first row is 92. Now the "
    "tens digit: put a zero as a placeholder, then 1 times 3 is 3, and 1 times 2 "
    "is 2, giving 230. Add 92 and 230 and you get 322. Let's try another: 32 "
    "times 21. You do the first row this time."
)
OUTCOMES = (
    "LO-1: Given two 2-digit numbers, the learner will compute their product "
    "using the standard column algorithm with correct partial products and carries.\n"
    "LO-2: The learner will explain why a placeholder zero is written in the second row."
)

SYSTEM = (
    "You are an instructional designer executing backward design. Design an "
    "event arc that serves the stated outcomes. Every scene declares which "
    "outcomes it serves, the Gagné event it performs, and either the script "
    "spans it works from or that it was designed. Emit the design contract."
    f"\n\nLEARNING OUTCOMES (authored by the course owner):\n{OUTCOMES}"
)
USER = (
    "Audience: 9-year-olds. Design the lesson from this script. Character "
    "offsets in `source_refs` are into the script exactly as given.\n\n"
    f"SCRIPT (character offsets start at 0):\n{SCRIPT}"
)


def probe(label, schema, max_tokens=3500):
    body = {
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": USER}],
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "response_format": response_format_for(schema),
    }
    req = urllib.request.Request(
        f"{BASE}/v1/chat/completions", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {KEY}"})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            payload = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        print(f"{label}: HTTP {e.code} REFUSED\n  {e.read().decode()[:500]}")
        return None
    except Exception as e:                                   # noqa: BLE001
        print(f"{label}: {type(e).__name__}: {e}")
        return None
    dt = time.monotonic() - t0
    ch = payload["choices"][0]
    txt = ch["message"]["content"]
    print(f"{label}: HTTP 200 in {dt:.1f}s finish_reason={ch.get('finish_reason')} "
          f"completion_tokens={payload.get('usage', {}).get('completion_tokens')}")
    try:
        obj = json.loads(txt)
    except Exception as e:                                   # noqa: BLE001
        print(f"  ⛔ NOT JSON: {e}\n  {txt[:400]!r}")
        return None
    return obj


def report(obj):
    scenes = obj.get("scenes", [])
    print(f"  outcomes={len(obj.get('outcomes', []))} scenes={len(scenes)} "
          f"dropped_beats={len(obj.get('dropped_beats', []))} "
          f"evidence_map keys={sorted(obj.get('evidence_map', {}))}")
    print(f"  events   : {[s.get('instructional_event') for s in scenes]}")
    print(f"  media    : {[s.get('media_type') for s in scenes]}")
    print(f"  serves   : {[s.get('serves_outcomes') for s in scenes]}")
    print(f"  origins  : {[(s.get('provenance') or {}).get('origin') for s in scenes]}")
    rew = sum(1 for s in scenes if (s.get('provenance') or {}).get('rewrite_of'))
    print(f"  rewrites marked: {rew}")
    for o in obj.get("outcomes", []):
        print(f"  outcome {o.get('id')}: measurable={o.get('measurable')} "
              f"bloom={o.get('bloom_level')} refinement={'yes' if o.get('proposed_refinement') else 'no'}")
    # schema conformance spot-checks the grammar should have made impossible
    from shared.models.enums import INSTRUCTIONAL_EVENTS, BLOOM_LEVELS, MEDIA_TYPES
    bad = [s.get("instructional_event") for s in scenes
           if s.get("instructional_event") not in INSTRUCTIONAL_EVENTS]
    bad += [s.get("bloom_level") for s in scenes if s.get("bloom_level") not in BLOOM_LEVELS]
    bad += [s.get("media_type") for s in scenes if s.get("media_type") not in MEDIA_TYPES]
    nos = [s.get("scene_index") for s in scenes if not s.get("serves_outcomes")]
    extra = set()
    for s in scenes:
        extra |= set(s) - {
            "scene_index", "narration_text", "visual_description", "media_type",
            "duration_seconds", "media_rationale", "text_carried_by",
            "generation_params", "instructional_event", "bloom_level",
            "serves_outcomes", "provenance", "signal_spec"}
    print(f"  ⛳ enum violations={[b for b in bad if b is not None]} "
          f"scenes with no serves_outcomes={nos} extra keys={sorted(extra)}")


if __name__ == "__main__":
    obj = probe("full Design Contract schema", design_contract_schema())
    if obj:
        report(obj)
        out = "/opt/ivgs/dev/workpackages/reference/wpivgs12-prompt-stack/design-contract-probe-emission.json"
        with open(out, "w") as f:
            json.dump(obj, f, indent=2)
        print(f"  emission banked at {out}")
