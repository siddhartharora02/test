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

## Mascot v3 — panther (current)

Style follows the owner's reference: Dribbble "Fox App Mascot and Logo Design" (Manu) — soft geometric
flat shapes, **no outlines, no gradients**, 3 tones of one fur hue (base / limbs+ears / tail), a lighter
cheek band with a wavy bottom edge that flares to cheek points, lighter round belly patch, big round eyes
(cream sclera, here a gold iris, dark pupil, one big + one small highlight), tiny nose, small open "D" mouth.
v1 (outlined cartoon) and v2 (Duolingo-like) are in git history.
Palette: fur #4B4787, limbs/legs #3B3870, tail/creases #2C2959, cheek band + belly #8580CC,
rosette spots #3F3B78, inner ears #B9A6FF, AstraFit violet #7B5CFF (sweatband, wristband), star #FFC93C,
sclera #FFFBF2, iris #FFC23C, pupils/nose #2B1E3A, mouth #9E1C2B, tongue #F2585B.
