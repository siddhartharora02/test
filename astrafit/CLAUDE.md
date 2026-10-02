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

## Mascot v1 — panther

Chibi black panther, front-facing, flexing one arm, other paw on hip.
Palette: fur #1D1A2E→#3A3555 (blue-black, never pure black), muzzle #5E5788, outline #14111F (9–10 px),
eyes gold #FFD23F, AstraFit violet #7B5CFF (headband, wristband, inner ears), gold star #F4B12A–#FFE68A.
Panther cues: faint rosette rings, cheek tufts, small rounded ears, almond eyes under determined brows, tiny fang.
