# WP-IVGS-10 — the v7 fixture

**Banked 2026-08-29 from project `5d58f2f5-88b9-439e-aea5-beaede42b694`
("WP-IVGS-10 v7 acceptance"), the first storyboard ever authored under prompt
v7. The project itself was DELETED through the WP-59 flow after this bank was
taken; these files are what remains of it, deliberately.**

Same brief and same source script as the operator's `9c29b1d1`, so the two are
comparable: *"A short instructional video for a 9 year old girl who struggles to
understand the concept of multiplying two numbers…"*, 300 s, three stated
learning outcomes, and the identical 3,172-byte transcript
(`sha256 3ea4eb8a…`).

## `storyboard-v7.json`

Twelve scenes as they stood at approval — after four declarations and six
descriptions were answered AT THE GATE by the package author standing in for
the reviewer (see the report §8; RC-P1 blocks their transport from Stage 2), and
after `_author_missing_motion_specs` authored the six motion templates from the
narrations.

Classified by `app/services/storyboard_completeness.py`: **12 DEPICTS, 0 GENERIC,
0 DELEGATES-TO-WRONG-MEDIUM.**

## `frames/`

⚠ **Every frame is taken from the SCENE'S OWN ASSET, never from a timestamp in
the composed draft.** WP-IVGS-09f measured the composed timeline drifting from
the manifest's nominal milliseconds — a sample at the stated offset landed in a
neighbouring scene. The asset is the exact artefact; the manifest offset is not.

| file | scene | what it shows |
|---|---|---|
| `scene2-last.png` | 2 `motion_graphics` | `23 × 14`, red carry **1**, answer row holding **2** only — the row deliberately INCOMPLETE (`phase: start`) |
| `scene3-last.png` | 3 `motion_graphics` | the same page finished at **92** (`phase: complete`) |
| `scene5-last.png` | 5 `motion_graphics` | the tens row at **230** |
| `scene6-last.png` | 6 `motion_graphics` | **92 + 230 = 322**, carry 1 |
| `scene8-last.png` | 8 `motion_graphics` | `32 × 21` tens row at **640** |
| `scene9-last.png` | 9 `motion_graphics` | **32 + 640 = 672** |
| `img0.png` | 0 `image` | ✅ an EMPTY ruled page. **No digits.** |
| `img1.png` | 1 `image` | ⛔ the model drew **"23 = 14"** and **"-- = 14"** |
| `img7.png` | 7 `image` | ⛔ two sheets of invented arithmetic |
| `img10.png` | 10 `image` | ⛔ a page of invented arithmetic |
| `img11.png` | 11 `image` | ⛔ the description's OWN VOCABULARY printed as headings — *"Partial product rows"*, *"Full Answer row:"* — over nine rows of garbage |
| `img4-mid.png` | 4 `video_clip` | ⛔ a flat blank field. Measured stddev **0.45–0.53** across five sample points against **95.8** for `img0` — a "successful" render containing nothing |

**⛔ Scenes 2 and 3 are the whole of RC-O10, closed.** Before `phase` existed
both carried `(23, 14, step 0)` and rendered the identical animation. They are
now two different pictures, and `scene3`'s FIRST frame is `scene2`'s LAST frame:
the second scene opens on exactly the page the first closed on.

**⛔ And the image frames are the package's most important negative result.**
Four of five image scenes attempted digits from descriptions that contained
none. The one that did not — `img0` — is the one whose surface was described as
EMPTY. See the report §9.
