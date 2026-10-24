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

Objects: `Ninja_Body`, `Ninja_Face`, `Ninja_Eyes`, `Ninja_Hood`, `Ninja_Cape`, `Ninja_Clothing`, `Ninja_Tunic`,
`Ninja_Gloves`, `Ninja_Boots`, plus the optional `Acc_Dagger` (right hand) and `Acc_HandProp` (left hand,
a throwing star) — hidden by default, tagged with the custom property / glTF extra `optional_accessory`;
`RENDER.ninja.accessory` (or `?ninjaacc=dagger|handprop`) shows at most one.

Rig `Ninja_Rig`: root, hips, spine, chest, neck, head, upper_arm / forearm / hand .L/.R, thigh / shin / foot .L/.R,
cape_C1-3 / cape_L1-3 / cape_R1-3. Actions (30 fps, in place, no root motion, feet grounded per key):
Idle 0-48, Run 0-16, Jump 0-18, Fall 0-24, Land 0-20, Slide 0-16.

Game side: `src/render/car/NinjaRig.ts` (GLTFLoader, wrapper node turned 180° and scaled, AnimationMixer,
state → clip), hooked into `src/render/car/MeshCar.ts`.
