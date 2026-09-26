# House renders — project notes for Claude

Photorealistic Blender (Cycles) renders of rooms in the house, built entirely from Python
scripts plus free CC0 assets. The first room is the **first-floor home office**.

## Layout

```
scripts/
  office_scene.py   # builds the office + renders views. CONFIG block (feet) at the top.
  office_lib.py     # geometry / material / generated-image / asset-import helpers
  fetch_assets.py   # downloads + caches Poly Haven and ambientCG assets into assets/
assets/             # git-ignored download cache (~600 MB). Safe to delete; re-fetched on next run.
renders/            # final renders (committed). renders/previews/ = low-res checks.
```

## Setup (headless Linux; Blender 5.x)

```bash
apt-get install -y libx11-6 libxi6 libxxf86vm1 libxfixes3 libxrender1 libxkbcommon0 libsm6 libgl1 libegl1 xz-utils
# latest stable 5.x from https://download.blender.org/release/ (currently 5.2.2 LTS)
cd /opt && curl -LO https://download.blender.org/release/Blender5.2/blender-5.2.2-linux-x64.tar.xz
tar -xJf blender-5.2.2-linux-x64.tar.xz && ln -sf /opt/blender-5.2.2-linux-x64/blender /usr/local/bin/blender
blender -b --version
```

On macOS use the Blender app binary instead of `blender`:
`/Applications/Blender.app/Contents/MacOS/Blender -b -P scripts/office_scene.py -- ...`.
Assets download automatically on the first run (urllib, falling back to `curl`).

## Commands

```bash
# quick composition check: 640x400, 32 samples -> renders/previews/
blender -b -P scripts/office_scene.py -- --view all --quality preview
blender -b -P scripts/office_scene.py -- --view desk --quality preview       # one view
# larger check without a full final: --res 1280x800 --samples 48 --out /tmp/check
# finals: 1920x1200, 256 samples, adaptive + OIDN -> renders/  (≈20-45 min per view on 4 CPU cores)
nohup blender -b -P scripts/office_scene.py -- --view all --quality final > renders/final.log 2>&1 &
grep '\[render\]' renders/final.log          # poll; per-view times also go to renders/render_times.json
# inspect the scene interactively
blender -b -P scripts/office_scene.py -- --save-blend assets/office.blend --no-render
```

Views: `entrance` (from the passage toward desk + window), `desk` (from the desk chair toward the
storage wall = video-call backdrop), `cutaway` (high 3/4 view, ceiling + south & west walls hidden).

## Workflow rules

- All dimensions live in the CONFIG block at the top of `office_scene.py`, **in feet**.
- Always render previews first, look at them, fix problems, then run finals.
- Long renders go in the background with `nohup` and get polled (tool calls time out).
- Commit scripts, `CLAUDE.md` and `renders/` (PNGs + `render_times.json`); never `assets/` or `*.log`.

## Coordinate system

Origin = south-west **inner** corner of the office at finished floor level.
+X = east (window wall), +Y = north (desk wall), +Z = up. Scripts work in feet and convert to metres.

## Office spec (from the architect's plan)

| Item | Spec |
|---|---|
| Inner size | 16'-1½" S→N × 12'-0" E→W, ceiling 10'-0" |
| East wall (front) | 9" thick. Window 6'-0" wide starting 7'-9" from the south inner wall, sill 3'-0", lintel 7'-0". Morning sun. |
| South wall | 9", solid |
| North wall | 4.5", solid, **dark slate accent paint** (other walls warm white) |
| West wall | 4.5" partition to the pantry |
| Entry | 5'-0" wide passage at the SW corner, ~4'-5" long, to a 3'-6" door into the lobby; leaf swings into the passage |
| Desk | 7'-0" × 2'-6" on the north wall, 2'-6" → 9'-6" from the east wall. Dual 27" monitors on an arm, laptop, keyboard, desk lamp, 2 ergonomic chairs, mobile pedestal |
| Storage wall | South wall, 1'-6" → 10'-0" from the east wall. White closed cabinets to 2'-9" with oak top; open oak shelves above to 8'-5" with books/decor (video-call backdrop) |
| Round table | 3'-0" dia, 3 chairs, centre 5'-2" from the south wall and 4'-3" from the east wall, rug below, pendant above |
| West wall | Whiteboard + split AC |
| Other | Two plants, wood-look plank floor tiles, 4" skirting, Indian modular switchboards, cables, everyday objects |

### Interpretations (confirm with the owner if they matter)

- The passage runs **west** from the room's SW corner (through the west-wall line, y = 0…5'), with the
  lobby door centred in its far end wall. The door is modelled closed.
- The window is a white UPVC 2-sash slider with a granite sill; a concrete *chajja* (sunshade) sits
  outside above the lintel.
- Plants: one tall plant in the NE corner by the window, one by the entry corner (SW) next to the storage wall.
- Extras not in the plan: framed print on the east wall south of the window, wall clock on the slate
  wall, LED strips under the shelves, curtain rod with two sheer panels pulled to the sides.

## Lighting / look

- HDRI: Poly Haven `belfast_farmhouse` (4K). At load time the sun is **extracted** from the HDRI
  (pixels > `HDRI_CLAMP`), its energy/colour/direction become a **sun lamp**, and the HDRI is rotated
  so the sun sits at `SUN_AZIMUTH` (95° = just south of east). Elevation (21.6°) comes from the HDRI.
- Area light portal over the window; 6 recessed downlights (3500 K); pendant bulb (3000 K);
  under-shelf LED area lights (3000 K). Monitors/laptop are emissive image textures generated in numpy.
- Cycles CPU, adaptive sampling, OIDN (albedo+normal), AgX + "Medium High Contrast".
  Exposure and white balance are per view (`exposure`, `wb` in `VIEWS`).
- Cameras: 24 mm, 4'-3" high, perfectly level with lens shift for framing (vertical lines stay vertical).
  The cutaway uses a flat backdrop for camera rays only and hides walls with `visible_camera=False`, so
  lighting is unchanged.

## Assets (all CC0)

Poly Haven: HDRI `belfast_farmhouse`; textures `laminate_floor_02`, `oak_veneer_01`, `rough_linen`;
models `potted_plant_01/02/04`, `desk_lamp_arm_01`, `modern_ceiling_lamp_01`, `decorative_book_set_01`,
`book_encyclopedia_set_01`, `ceramic_vase_01`, `brass_vase_03`, `carved_wooden_elephant`,
`standing_picture_frame_02`, `office_notepads`, `stationery_supplies`, `wall_clock`, `round_spectacles`
(`dining_chair_02` is downloaded but unused — replaced by a lighter procedural oak chair).
ambientCG: `Carpet016` (rug), `PaintedPlaster017` (walls/ceiling), `Metal032` (brushed metal), `Fabric031` (upholstery).
Procedural: architecture, desk, pedestal, monitors + arm, keyboard, mouse, laptop, ergonomic mesh chairs,
dining chairs, storage wall, round table, rug, whiteboard (+ drawing), split AC, switchboards, curtains, cables, mug.

## Gotchas learned

- Poly Haven `.blend` files reference textures relatively; `office_lib.append_objects` re-points them.
- The rigged desk lamp: parent only objects without `CHILD_OF` constraints to the placement empty.
- `modern_ceiling_lamp_01`: shade occupies the bottom ~0.38 m; stretch only verts above +0.45 m for the rod.
- Blender 5.x white balance: tint default is +10 (magenta once temperature is lowered); we use −6.
- AgX pushes strong 3000 K light toward salmon/pink on white walls — keep lamps ~3500 K and set WB per view.

## Render log

See `renders/render_times.json` for the latest timings per view.
