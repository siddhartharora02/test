# AstraFit — project notes for Claude

Brand assets for the AstraFit fitness app. Lives in the same repo as the house renders but is a
separate project.

## Rules

- **No Blender for AstraFit.** The owner rejected the Blender 3D mascot. Mascot and stickers are
  hand-authored 2D vector art (SVG).
- Mascot first; achievement stickers only after the owner approves the mascot.

## Layout

```
mascot/
  panther.svg         # the mascot (source of truth; edit shapes here)
  render_mascot.py    # SVG -> panther_1024.png / panther_2048.png (transparent), needs `pip install cairosvg`
```

## Mascot v2 — panther (current)

Style follows the owner's reference (Duolingo-like achievement art): flat colours, **no outlines**,
chunky rounded shapes, hard-edged shade shapes on the right side, big expressive eyes with heavy lids,
open grin, exaggerated pose. v1 (outlined cartoon) is in git history.
Chibi black panther flexing one arm, paw on hip. Palette: fur #4B4878 / shade #383660 / light #6B67A3,
muzzle #8C86C6, pupils/brows/nose #1E1C30, eyes gold #FFC93C, AstraFit violet #7B5CFF (headband,
wristband), inner ears #A58BFF, gold star #FFC93C, mouth #7A1E3A, tongue #FF6B8B.
Fur stays violet-indigo (not black) so it reads on the app's dark background.
