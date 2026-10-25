# Ninja player character

**Current asset (v6 = v3 pipeline + v4/v5/v6 fixes):** the in-game `src/assets/models/ninja.glb` is the scanned-from-references model built by
`build_ninja_v3.py` (see "v3 pipeline" below). The older fully procedural build (`build_ninja.py`, described
after it) is kept as a fallback and as the source of the optional accessory meshes.

## v3 pipeline (fal image-to-3D → Blender texture fix → rig)

```
blender -b --factory-startup -P assets-src/ninja/build_ninja_v3.py      # → NinjaCharacter.blend (packed) + src/assets/models/ninja.glb
blender -b assets-src/ninja/NinjaCharacter.blend -P assets-src/ninja/render_ninja.py -- --out OUT --anim [--animview side_r]
```

Inputs, all in `fal_v3/`: `ninja_v2_textured.glb` (the decimated, back-repaired fal model, 29,997 tris, own UVs),
`basecolor_v3.webp` (fixed albedo), `emit_v3.png` (eye-white emission mask), `accessories.blend` (`Acc_Dagger`,
`Acc_HandProp` + their leather textures + the old `Ninja_Rig`, copied from the procedural build).

How the inputs were made (one-off; scripts in `fal_v3/scripts/`, paths inside are the workstation's):

1. **Clean views** — `fal-ai/nano-banana-pro/edit` turned the user's reference art into clean front / back /
   left / right views of the same character on a plain background (plus one extra pass for the back/belt view).
   The exact prompt text was not archived with these files.
2. **3D** — `tripo3d/tripo/v2.5/multiview-to-3d` with the four views, `texture: "HD"`, `pbr: false`,
   `texture_alignment: "geometry"`, `face_limit: 40000`, `seed`/`texture_seed: 7`.
3. **Blender clean-up** — `fix_back.py` / `blend_fix.py` (back repair), `v2_dec.py` (decimate to ~30k tris),
   `v2_proc.py` / `v2_bake.py` / `v2_maps.py` (back hole texture repair, normal + metal-rough maps).
4. **v3 texture fix** — `texpos.py` rasterises per-texel 3D position + normal from the UVs; `v3_tex.py` edits the
   albedo in 1 mm projection grids: removes the light-brown streak on both hood sides (median + normalized
   convolution fill), repaints the eyes (white whites, black pupils, catch-light, dark rim) and the black mask
   band, cleans the nose/chin, desaturates the orange skin ~30 %; writes the basecolor + eye emission mask.
   `swap_render.py` renders a GLB with a swapped basecolor for compares.
5. **Rig** (`build_ninja_v3.py`) — same bone names / clips as the procedural rig (so `NinjaRig.ts` is unchanged)
   plus three 3-bone cape chains; heat weights on the body, edge-relaxed, arms kept off the spine; the cape
   (flood-filled separate sheet + top band) is weighted only to the cape chains / trunk, hood + head rigid on
   `head`. Poses are re-targeted from the procedural rig's keyed poses. Export: WebP textures (q90),
   `Ninja_Fal` alpha MASK 0.5, double-sided, eye whites emissive 0.45.

fal cost for the whole v3 asset: about **$1.15** (Nano Banana Pro edits + Tripo multiview HD runs).

### v4 fixes (same pipeline, no extra fal spend)
- **Texture** — `fal_v3/scripts/v4_tex.py` (from `basecolor_v3` + the v2 normal map, using `texpos`):
  hood back seam/crease and streak leftovers removed (kNN cloth colour + high-pass detail + soft fold shading),
  normal map flattened on the seam (`normal_v4.webp`), exposed skin cut to the nose/cheek band and made more
  neutral, chin + scarf-top wraps continued from the scarf → `basecolor_v4.webp`.
- **Hood sculpt** — `hood_sculpt()` in `build_ninja_v3.py`: masked Taubin smoothing of the back ridge / crown,
  back bulge flattened ~22 %, tip pulled back and slightly down; the hood stays 100 % on the head bone.
- **Cape** — `CAPE_MOTION` / `cape_keys()`: the cape bones are keyed every 2 frames procedurally; it hangs down and
  trails back (total lift ≈ 30° Run, 40–54° Jump/Fall, settling to ≈ 5° in Land), the side chains swing inward as
  they lift (`CAPE_IN`), so from behind it stays about shoulder wide (no "wings"). `fal_v3/scripts/measure.py`
  prints the cape width per clip.
- **Weights** — extra local relaxation (edge + spatial) at the stretch hot spots (`HOT`: collar/shoulder join,
  chest strap buckle, cape hem corners).
Size: 29,997 tris body (+1,100 hand prop / +332 dagger, hidden by default), GLB ≈ 2.2 MB.

### v5 hood rebuild (no extra fal spend)
- **Geometry** — `hood_sculpt()` v5 in `build_ninja_v3.py`: 14 small open scan cracks around the hood are closed first
  (`holes_fill`, ≤8-edge loops); then every outward-facing hood shell vertex outside the face-opening cone is slid along
  its ray from the head centre onto an analytic gumdrop (`HOOD`: piecewise super-ellipsoid, p = 2.1, with a soft tip
  ~32° behind the vertical and a slight droop), Taubin-smoothed (extra passes on the brim, open borders pinned),
  re-projected, and six shallow cloth folds (≤ ~14 mm) are pressed in from the tip towards the back/sides.
  Topology and UVs are unchanged; the hood is weighted 100 % to the head bone (weights are computed after the sculpt).
  `--no-sculpt` builds the raw scan for comparison.
- **Texture** — `fal_v3/scripts/v5_tex.py RAW.npz FINAL.npz basecolor_v4.png normal_v4.png OUTDIR` (npz = vertex
  positions/faces/loop UVs dumped from a `--no-sculpt` and a normal build): hood albedo darkened to near-black charcoal
  with the fold cavities of the new geometry baked in as soft shading, faint front-crown strip removed, Tripo noise in
  the normal map flattened on the hood → `basecolor_v5.webp`, `normal_v5.webp` (build defaults).
Size: 30,036 tris body (+39 from the closed cracks), GLB ≈ 2.2 MB.

### v6 hood cloth folds (no extra fal spend)
- **Hood density** — the scan's hood triangles (14–25 mm) were too coarse to carry folds: micro-edges < 3.2 mm are
  collapsed, hood edges > 14 mm are split once, and the tris are paid back by collapse-decimating the lower front body
  (z < 0.52, y < 0.02; cape excluded) to a fixed budget (`--tri-budget`, default 30,500; `--no-subdiv` to skip).
- **Fold field** — `fal_v3/hood_folds.py` (shared by the build and the texture bake): 7 long main folds radiating from
  the tip down the back/sides, 4 soft creases by the face opening, 7 short bunching pleats where the hood meets the
  scarf, plus two shallow horizontal sags. Each fold is a Gaussian groove around a great-circle arc with tapered ends.
  The build presses the low-passed field in along the normals (max ≈ 21 mm, deep folds ≈ 8–20 mm) on top of the v5
  gumdrop, then Taubin-smooths and runs an untangle pass (flipped / badly bent faces), and resets the hood's custom
  split normals to smooth normals. Silhouette stays the v5 gumdrop; the hood is still 100 % on the head bone (the
  shoulder exclusion now only applies below z 0.66 so the widest hood sides stay head-rigid).
- **Texture** — `blender -b NinjaCharacter.blend -P fal_v3/scripts/dump_ao.py -- final_ao.npz` (mesh + 48-ray AO), then
  `python fal_v3/scripts/v6_tex.py final_ao.npz basecolor_v4.png normal_v4.png OUTDIR` (v4 webps as PNG): per-texel raster of the final
  mesh; near-black albedo with baked AO, sharp crease/cavity darkening, ridge lift and a faint weave; tangent-space
  normal map from the crease + weave/slub height field (face creases are mostly texture) → `basecolor_v6.webp`,
  `normal_v6.webp` (build defaults).
Size: 30,500 tris body (lower front body ≈ 18 % decimated to pay for the hood), GLB ≈ 2.25 MB.

## Procedural build (v1, fallback)

Chibi ninja that replaces the XWAVE X1's look in the game (`RENDER.player` in `src/config.ts`;
`'car'` or `?player=car` brings the X1 back unchanged).

| file | purpose |
| --- | --- |
| `build_ninja.py` | builds everything from code: meshes + UVs, generated PBR textures, materials, armature + skin weights, the six actions; saves `NinjaCharacter.blend` (textures packed) and exports `src/assets/models/ninja.glb` |
| `render_ninja.py` | Cycles renders of the .blend (front / back / left / right / top / gameplay_angle, animation frames, accessories) |
| `NinjaCharacter.blend` | the source scene (Blender 4.2 LTS) |

```
blender -b --factory-startup -P assets-src/ninja/build_ninja.py
blender -b assets-src/ninja/NinjaCharacter.blend -P assets-src/ninja/render_ninja.py -- --out OUT_DIR
blender -b assets-src/ninja/NinjaCharacter.blend -P assets-src/ninja/render_ninja.py -- --out OUT_DIR --anim
```

Objects: `Ninja_Body`, `Ninja_Face` (black mask, peach skin only at nose / mouth), `Ninja_Eyes`, `Ninja_Hood`
(big gumdrop hood, flat stitched seam, creases, scuffs), `Ninja_Cowl` (shoulder shawl under the hood),
`Ninja_Cape` (left shoulder → back, saw-tooth hem, round holes), `Ninja_Clothing` (belt, diagonal strap + back
buckle, pouches, leg wraps, cuffs / forearm guards), `Ninja_Tunic`, `Ninja_Gloves`, `Ninja_Boots` (layered soles),
plus the optional `Acc_Dagger` (right hand) and `Acc_HandProp` (right hand, a foam hand on a stick with a
cheeky face on its back) — hidden by default, tagged with the custom property / glTF extra `optional_accessory`;
`RENDER.ninja.accessory` (or `?ninjaacc=dagger|handprop`) shows at most one.

Rig `Ninja_Rig`: root, hips, spine, chest, neck, head, upper_arm / forearm / hand .L/.R, thigh / shin / foot .L/.R,
cape_C1-3 / cape_L1-3 / cape_R1-3. Actions (30 fps, in place, no root motion, feet grounded per key):
Idle 0-48, Run 0-16, Jump 0-18, Fall 0-24, Land 0-20, Slide 0-16.

Budget: about 24.4k triangles with an accessory (22.9k without). Colours: cloth ≈ #2a2526 (warm charcoal),
leather ≈ #3b2a20, darker soles; woven / embossed fabric in the normal + roughness maps, no baked light.
Renders: warm key + cool rim; views include `back_34` (rear 3/4, use `--pose Run:4 --acc handprop`) and
`front_34`; `--noground` hides the ground disc.

Game side: `src/render/car/NinjaRig.ts` (GLTFLoader, wrapper node turned 180° and scaled, AnimationMixer,
state → clip), hooked into `src/render/car/MeshCar.ts`.
`RENDER.ninja.scale` (2.6 for v3; 2.2 for the procedural v1) makes it about as big on screen as the X1; `bright` / `env` lift its own materials on
the night road. With the ninja the car-only flight jets (`Vehicle.ts`) and nitro flames (`MeshCar.ts`) are off.
