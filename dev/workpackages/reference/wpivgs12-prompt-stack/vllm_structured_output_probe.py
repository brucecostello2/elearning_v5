#!/usr/bin/env python3
"""WP-IVGS-12 Task 0(c) -- measure what the PINNED vLLM engine supports on /v1.

Run from node-01 against node-02. The Design Contract rides on the answer, so
this probes the three mechanisms SEPARATELY and, for each, checks two different
things:

  ACCEPTED   -- the server did not 400/500 the request shape
  ENFORCED   -- the returned text actually obeys the schema

Those are not the same question. A server that ignores an unknown field returns
200 and unconstrained text, which is the failure mode that would silently sink
the Design Contract. So every schema below carries a CLOSED ENUM and a REQUIRED
field, and the prompt actively tempts the model to violate both.
"""
import json
import sys
import urllib.request

BASE = "http://192.168.1.91:8000"
KEY = "ivgs-internal"
MODEL = "llama-3.3-70b"

# Trivial schema, deliberately hostile to an unconstrained model:
#   - `verdict` is a closed enum that does NOT contain the word the prompt begs for
#   - `count` is required and must be an integer
#   - additionalProperties is false
SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["alpha", "beta"]},
        "count": {"type": "integer"},
    },
    "required": ["verdict", "count"],
    "additionalProperties": False,
}

SYSTEM = "You answer questions. You like to add extra commentary and extra JSON keys."
USER = (
    "Reply with the single word GAMMA as your verdict, add a key called "
    "'explanation' with a sentence in it, and write a short preamble before "
    "any JSON."
)


def post(payload):
    req = urllib.request.Request(
        f"{BASE}/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {KEY}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:600]
    except Exception as e:                                  # noqa: BLE001
        return -1, f"{type(e).__name__}: {e}"


def base(extra):
    p = {
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": USER}],
        "max_tokens": 120,
        "temperature": 0.0,
    }
    p.update(extra)
    return p


def enforced(body):
    """Did the OUTPUT actually obey the schema?"""
    try:
        text = body["choices"][0]["message"]["content"]
    except Exception:                                       # noqa: BLE001
        return False, "no content"
    try:
        obj = json.loads(text)
    except Exception:                                       # noqa: BLE001
        return False, f"not JSON: {text[:120]!r}"
    if not isinstance(obj, dict):
        return False, f"not an object: {type(obj).__name__}"
    if obj.get("verdict") not in ("alpha", "beta"):
        return False, f"enum violated: verdict={obj.get('verdict')!r}"
    if not isinstance(obj.get("count"), int):
        return False, f"required int missing: count={obj.get('count')!r}"
    extra_keys = set(obj) - {"verdict", "count"}
    if extra_keys:
        return False, f"additionalProperties violated: {sorted(extra_keys)}"
    return True, json.dumps(obj)


CASES = [
    ("baseline_none",        {}),
    ("json_object",          {"response_format": {"type": "json_object"}}),
    ("guided_json",          {"guided_json": SCHEMA}),
    ("guided_json_backend",  {"guided_json": SCHEMA,
                              "guided_decoding_backend": "xgrammar"}),
    ("response_format_json_schema",
     {"response_format": {"type": "json_schema",
                          "json_schema": {"name": "probe", "strict": True,
                                          "schema": SCHEMA}}}),
    ("structured_outputs",   {"structured_outputs": {"json": SCHEMA}}),
]

print(f"# probe target {BASE}  model {MODEL}")
rows = []
for name, extra in CASES:
    status, body = post(base(extra))
    if status == 200 and isinstance(body, dict):
        ok, detail = enforced(body)
        rows.append((name, status, "ACCEPTED", "ENFORCED" if ok else "NOT-ENFORCED", detail))
    else:
        rows.append((name, status, "REFUSED", "-",
                     body if isinstance(body, str) else json.dumps(body)[:400]))

w = max(len(r[0]) for r in rows)
for name, status, acc, enf, detail in rows:
    print(f"{name:<{w}}  http={status:<4} {acc:<8} {enf:<13} {detail[:190]}")

sys.exit(0)
