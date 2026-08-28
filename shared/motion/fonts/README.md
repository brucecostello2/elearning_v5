# Vendored fonts — WP-IVGS-09 Task 1(b)

**Why these bytes are in the repository.** `shared/motion/raster.py` is the
motion renderer's reference implementation, and its whole contract is that the
same parameters give the same pixels. A font resolved from
`/usr/share/fonts/...` makes that contract depend on which packages happen to
be installed on whichever host runs the code — which is not determinism, it is
a coincidence that has held so far. WP-68 §5 measured the coincidence failing:
the rasteriser **refused inside the production image** because `fonts-dejavu-core`
is not installed there.

So the typeface travels with the code.

| file | sha256 | provenance |
|---|---|---|
| `DejaVuSans-Bold.ttf` | `5c1247acef7f2b8522a31742c76d6adcb5569bacc0be7ceaa4dc39dd252ce895` | Debian/Ubuntu `fonts-dejavu-core`, `/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf`, file date 2023-08-10, copied from node-01 on 2026-08-28 |

**Licence:** Bitstream Vera Fonts Licence (see `LICENSE-DejaVu.txt`, the
Debian `copyright` file verbatim). It permits redistribution, including inside
a container image, provided the notice travels with it — which is why the
licence file sits beside the font rather than being referenced from elsewhere.

**Pinned, not discovered.** `raster.FONT_PATH` names this file by absolute path
computed from `__file__`. `raster.FONT_FALLBACK` names the *same typeface* at
its system location. It used to name `DejaVuSans.ttf` — the REGULAR weight —
which meant the "fallback" silently changed every glyph on the frame while the
module's own docstring said a renderer that substitutes fonts is not
deterministic. Corrected by WP-IVGS-09.

Do not add a second face here without a reason written down. Two faces is two
answers to "what does this template look like".

## ⚠ Measured 2026-08-28: the system copy is the same face and different bytes

Inside `ivgs-motion-renderer`, `ffmpeg` pulls `fontconfig-config`, which pulls
`fonts-dejavu-core` — so a second `DejaVuSans-Bold.ttf` is present at
`/usr/share/fonts/truetype/dejavu/` whether or not anyone asked for it. Its
hash is **`0d977336a6d5fba34eab8e3199eb218327161b5143749f802982c2bc34df0c96`**
(Debian bookworm) against the vendored **`5c1247ac…`** (Ubuntu noble).

Same typeface, different build. Two builds of one face can differ in hinting,
and hinting is pixels — so this is the argument for vendoring, not against it.
`FONT_PATH` names the in-repo file by absolute path and wins; `/healthz` hashes
**both** candidates so a substitution is visible on a surface rather than
inferred from a changed digest three stages downstream.
