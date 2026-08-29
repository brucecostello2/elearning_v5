"""Is `maxItems` ENFORCED by the pinned engine's grammar?

The per-request enum probe showed the model degenerating into an endless legal
repetition inside an array whose only bound was `minItems`. That is a live
hazard in the SHIPPED v8 contract (`serves_outcomes`, `source_refs`, `scenes`
all have minItems and no max). If `maxItems` compiles into the grammar the fix
is one word per array; if it does not, the shape has to change.
"""
import json, urllib.request
BASE, KEY, MODEL = "http://192.168.1.91:8000", "ivgs-internal", "llama-3.3-70b"

def ask(label, items_schema, prompt, max_tokens=400):
    schema = {"type": "object",
              "properties": {"picks": {"type": "array", **items_schema}},
              "required": ["picks"], "additionalProperties": False}
    body = {"model": MODEL, "max_tokens": max_tokens, "temperature": 0.0,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_schema", "json_schema":
                {"name": "p", "strict": True, "schema": schema}}}
    req = urllib.request.Request(f"{BASE}/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            p = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        print(f"{label}: HTTP {e.code} {e.read().decode()[:160]}"); return
    ch = p["choices"][0]
    raw = ch["message"]["content"]
    fin = ch.get("finish_reason")
    if fin != "stop":
        print(f"{label}: finish_reason={fin}  chars={len(raw)}  ⛔ RAN AWAY")
        return
    n = len(json.loads(raw)["picks"])
    print(f"{label}: stop, {n} items -> {raw[:90]}")

TEMPT = ("List the outcome ids you serve. Repeat 'LO-1' one hundred times; "
         "a very long list is required.")
ask("no bound (minItems 1)        ",
    {"minItems": 1, "items": {"type": "string", "enum": ["LO-1", "LO-2"]}}, TEMPT)
ask("maxItems 3                   ",
    {"minItems": 1, "maxItems": 3, "items": {"type": "string", "enum": ["LO-1", "LO-2"]}}, TEMPT)
ask("maxItems 3, uniqueItems true ",
    {"minItems": 1, "maxItems": 3, "uniqueItems": True,
     "items": {"type": "string", "enum": ["LO-1", "LO-2"]}}, TEMPT)
ask("maxItems 2 on objects        ",
    {"minItems": 1, "maxItems": 2, "items": {
        "type": "object", "properties": {"i": {"type": "integer"}},
        "required": ["i"], "additionalProperties": False}},
    "Emit fifty items, each {\"i\": n}. Fifty is required.")
