# Ninja player character

**Current asset (v4 = v3 pipeline + fixes):** the in-game `src/assets/models/ninja.glb` is the scanned-from-references model built by
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
