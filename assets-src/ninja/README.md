# Ninja player character

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
`RENDER.ninja.scale` (2.2) makes it about as big on screen as the X1; `bright` / `env` lift its own materials on
the night road. With the ninja the car-only flight jets (`Vehicle.ts`) and nitro flames (`MeshCar.ts`) are off.
