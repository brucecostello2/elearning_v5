"""WP-IVGS-12h TASK 2 — the near-duplicate belt, run against 12g's BANKED bytes.

⛔ THIS IS PART OF THE ACCEPTANCE, NOT A DEVELOPMENT AID. The order requires the
belt be proven RED on the duplicates 12g quoted before a GREEN result on a fresh
generation means anything: a check that refuses nothing is indistinguishable from
a check that is not wired in.

It reads `../wpivgs12g-evidence/*-contracts.json` — the raw model emissions, not
a summary of them — and classifies every outcome-pair with
`shared.design.duplication`, the SAME module the API gate imports.

Usage:  python3 calibrate12h.py            # prints the table, exits non-zero on
                                           # any row that moves class
"""
import json, os, sys

TREE = os.environ.get("IVGS_TREE", "/opt/ivgs")
sys.path[:0] = [TREE]

from shared.design.duplication import (            # noqa: E402
    NEAR_DUPLICATE_CONTAINMENT, NO_FRESH_AXIS_CONTAINMENT,
    containment, duplication_verdict,
)

HERE = os.path.dirname(os.path.abspath(__file__))
BANK = os.path.join(os.path.dirname(HERE), "wpivgs12g-evidence")

SOURCES = (
    ("OP-runB", "ACCEPT-contract6-runB-contracts.json"),
    ("OP-runA", "ACCEPT-contract6-contracts.json"),
    ("B2",      "B2-contract6-contracts.json"),
)

#: ⛔ THE EXPECTED CLASSIFICATION, WRITTEN FROM 12g's OWN QUOTES AND ITS OWN
#: ⛳ B2 READING — not from what this belt happens to output. Keyed
#: (source, generation, outcome) -> (practice-limb verdict, worked-example-limb
#: verdict). `True` means DUPLICATE.
#:
#: The operator's script: 12g.9 quotes 9 pairs as ⛔ IDENTICAL and 2 more as the
#: same sentence with a "Let's practice" prefix. All 11 must refuse.
#: ⚠ 12g's prose says "11 of 15 verbatim identical, the other four are the same
#: sentence with a 'Let's practice' prefix", which does not survive its own
#: bytes: the count of 11 is right, its composition is 9 verbatim + 2 prefixed,
#: and the other FOUR are the LO-1 pairs, which genuinely differ. Corrected here
#: against the bank rather than repeated.
#:
#: B2: 12g.10 says only the non-computational LO-3 collapses. On the PRACTICE
#: limb that is exactly right. ⛔ On the WORKED-EXAMPLE limb it is not: B2's
#: LO-1 assessment is byte-identical to its own `guide` scene 17.
EXPECTED = {
    ("OP-runB", 1, "LO-1"): (True,  False),   # limb B: same 43x25, cont 0.64
    ("OP-runB", 1, "LO-2"): (True,  False),
    ("OP-runB", 1, "LO-3"): (True,  False),
    ("OP-runB", 2, "LO-1"): (True,  False),
    ("OP-runB", 2, "LO-2"): (True,  False),
    ("OP-runB", 2, "LO-3"): (True,  False),
    ("OP-runB", 3, "LO-1"): (False, False),
    ("OP-runB", 3, "LO-2"): (True,  False),   # "Let's practice ..." prefix
    ("OP-runB", 3, "LO-3"): (True,  False),   # "Let's practice ..." prefix
    ("OP-runA", 2, "LO-1"): (False, False),
    ("OP-runA", 2, "LO-2"): (True,  False),
    ("OP-runA", 2, "LO-3"): (True,  False),
    ("OP-runA", 3, "LO-1"): (False, False),
    ("OP-runA", 3, "LO-2"): (True,  False),
    ("OP-runA", 3, "LO-3"): (True,  False),
    ("B2",      1, "LO-1"): (False, True),    # ⛔ 12g called this one clean
    ("B2",      1, "LO-2"): (False, False),
    ("B2",      1, "LO-3"): (True,  True),
}


def pairs():
    for label, filename in SOURCES:
        path = os.path.join(BANK, filename)
        for gen, obj in enumerate(json.load(open(path)), 1):
            if not obj:
                continue                      # run A gen 1 truncated: no document
            assessments = obj.get("assessment_scenes") or {}
            practices = obj.get("practice_scenes") or {}
            expo = [s for s in (obj.get("scenes") or []) if isinstance(s, dict)]
            for oid in assessments:
                entry = assessments[oid]
                scene = entry[0] if isinstance(entry, list) else entry
                worked = [
                    s.get("narration_text") for s in expo
                    if s.get("instructional_event") in ("present", "guide")
                    and oid in (s.get("serves_outcomes") or [])
                ]
                yield (label, gen, oid, scene.get("narration_text"),
                       [s.get("narration_text") for s in (practices.get(oid) or [])],
                       worked)


def main():
    print("=" * 78)
    print("WP-IVGS-12h — the near-duplicate belt against 12g's banked emissions")
    print(f"  limb A  containment >= {NEAR_DUPLICATE_CONTAINMENT}")
    print(f"  limb B  numerals equal AND containment >= {NO_FRESH_AXIS_CONTAINMENT}")
    print("=" * 78)
    print(f"{'source':<9}{'gen':<5}{'LO':<6}{'practice':>26}{'worked example':>26}")
    failures, refuse_p, pass_p = [], 0, 0
    for label, gen, oid, assess, practice, worked in pairs():
        pv = [duplication_verdict(assess, x) for x in practice]
        wv = [duplication_verdict(assess, x) for x in worked]
        pdup = any(v["duplicate"] for v in pv)
        wdup = any(v["duplicate"] for v in wv)
        pbest = max([v["containment"] for v in pv] or [0.0])
        wbest = max([v["containment"] for v in wv] or [0.0])
        plimb = next((v["limb"] for v in pv if v["duplicate"]), "-")
        wlimb = next((v["limb"] for v in wv if v["duplicate"]), "-")
        refuse_p += pdup
        pass_p += (not pdup)
        mark = lambda d: "REFUSE" if d else "pass  "
        print(f"{label:<9}{gen:<5}{oid:<6}"
              f"{mark(pdup)+f' {pbest:.3f} {plimb:<13}':>26}"
              f"{mark(wdup)+f' {wbest:.3f} {wlimb:<13}':>26}")
        want = EXPECTED.get((label, gen, oid))
        if want is None:
            failures.append(f"{label} g{gen} {oid}: not in EXPECTED")
        elif (pdup, wdup) != want:
            failures.append(
                f"{label} g{gen} {oid}: got {(pdup, wdup)}, expected {want} "
                f"(practice containment {pbest:.3f}, worked {wbest:.3f})"
            )
    print("=" * 78)
    print(f"practice limb: {refuse_p} REFUSE / {pass_p} pass, of {refuse_p + pass_p}")
    print("the two classes, practice limb, SPLIT BY LIMB — and they must be:")
    limb_a, limb_b, clean = [], [], []
    for _l, _g, _o, a, p, _w in pairs():
        best = max([containment(a, x) for x in p] or [0.0])
        limbs = {v["limb"] for v in (duplication_verdict(a, x) for x in p)}
        if "restates" in limbs:
            limb_a.append(best)
        elif "no_fresh_axis" in limbs:
            limb_b.append(best)
        else:
            clean.append(best)
    r3 = lambda xs: [round(x, 3) for x in sorted(xs)]
    print(f"  limb A REFUSE (restates)      : {r3(limb_a)}")
    print(f"  limb B REFUSE (no fresh axis) : {r3(limb_b)}")
    print(f"  pass                          : {r3(clean)}")
    # ⛔ THE MARGIN CLAIM IS LIMB A's ALONE AND IS STATED THAT WAY. limb B
    # deliberately refuses BELOW the pass class's ceiling — that is what a
    # second limb IS — so a single "refuse floors at X" line over both limbs
    # would read as a separation that does not exist.
    if limb_a and clean:
        print(f"  ⛳ LIMB A MARGIN: pass tops out at {max(clean):.3f}, limb A "
              f"floors at {min(limb_a):.3f}; threshold "
              f"{NEAR_DUPLICATE_CONTAINMENT} sits between them")
    if limb_b:
        print(f"  ⚠ LIMB B has no counter-example to separate FROM: every "
              f"equal-numeral pair in the bank is a duplicate. Its floor "
              f"{NO_FRESH_AXIS_CONTAINMENT} sits below the lowest it must "
              f"catch ({min(limb_b):.3f}) and is the WIDER of the two claims.")
    print("=" * 78)
    if failures:
        print("⛔ CALIBRATION FAILED — a row moved class:")
        for f in failures:
            print("   " + f)
        return 1
    print("⛳ CALIBRATION HELD — every banked row classifies as 12g's quotes say")
    return 0


if __name__ == "__main__":
    sys.exit(main())
