# Turntable / animation renders of NinjaCharacter.blend (Cycles CPU). Lighting (render only, nothing is
# baked into the asset) mimics the concept art: warm key from the front-left, cool blue rim from behind.
#   blender -b assets-src/ninja/NinjaCharacter.blend -P assets-src/ninja/render_ninja.py -- --out DIR [--views a,b] [--anim] [--samples N]
import bpy, math, os, sys
from mathutils import Vector
argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
def arg(k, d):
    return argv[argv.index(k) + 1] if k in argv else d
OUT = arg('--out', '/workspace/artifacts/ninja')
VIEWS = arg('--views', 'front,back,left,right,top,gameplay_angle').split(',')
SAMPLES = int(arg('--samples', '48'))
RES = int(arg('--res', '900'))
os.makedirs(OUT, exist_ok=True)
sc = bpy.context.scene
sc.render.engine = 'CYCLES'
sc.cycles.device = 'CPU'
sc.cycles.samples = SAMPLES
sc.cycles.use_denoising = True
sc.render.resolution_x = sc.render.resolution_y = RES
sc.render.film_transparent = False
sc.view_settings.view_transform = 'AgX'
world = bpy.data.worlds.new('W'); sc.world = world; world.use_nodes = True
world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.42, 0.44, 0.47, 1)
world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.05
sc.render.film_transparent = '--opaque' not in argv   # transparent like the references
def light(name, typ, loc, energy, size=1.0, color=(1, 1, 1)):
    l = bpy.data.lights.new(name, typ); l.energy = energy; l.color = color
    if typ == 'AREA': l.size = size
    o = bpy.data.objects.new(name, l); sc.collection.objects.link(o)
    o.location = loc
    d = Vector((0, 0, 0.5)) - Vector(loc)
    o.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    return o
light('Key', 'AREA', (-1.6, -2.2, 2.2), 120, 1.5, (1.0, 0.8, 0.6))       # warm key
light('Fill', 'AREA', (2.2, -1.2, 1.0), 15, 2.0, (0.85, 0.9, 1.0))
light('Rim', 'AREA', (1.6, 2.3, 1.6), 170, 1.0, (0.5, 0.68, 1.0))         # cool rim
light('Rim2', 'AREA', (-2.0, 1.8, 1.3), 130, 1.0, (1.0, 0.68, 0.4))       # warm kicker from behind (as in the back views)
# ground disc (render only; not part of the asset)
bpy.ops.mesh.primitive_circle_add(vertices=64, radius=0.9, fill_type='NGON', location=(0, 0, 0))
g = bpy.context.active_object; g.name = '_RenderGround'
gm = bpy.data.materials.new('_ground'); gm.use_nodes = True
gm.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.5, 0.5, 0.52, 1)
gm.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = 0.9
g.data.materials.append(gm)
cam_d = bpy.data.cameras.new('Cam'); cam = bpy.data.objects.new('Cam', cam_d); sc.collection.objects.link(cam); sc.camera = cam
cam_d.lens = 85
target = Vector((0, 0, 0.5))
VIEW_POS = {'front': (0, -3.2, 0.55), 'back': (0, 3.2, 0.55), 'left': (3.2, 0, 0.55), 'right': (-3.2, 0, 0.55),
            'top': (0.0, -0.02, 3.4), 'gameplay_angle': (0.0, 2.6, 1.55), 'three_quarter': (2.0, -2.4, 1.0),
            'back_34': (-1.0, 2.7, 1.25), 'front_34': (-2.2, -2.3, 0.9), 'side_r': (-3.2, 0.4, 0.8)}
def aim(pos, tgt=target, lens=85):
    cam.location = pos
    cam.rotation_euler = (tgt - Vector(pos)).to_track_quat('-Z', 'Y').to_euler()
    cam_d.lens = lens
rig = bpy.data.objects['Ninja_Rig']
def set_action(name, frame):
    rig.animation_data.action = bpy.data.actions[name]
    sc.frame_set(frame)
acc = arg('--acc', '')
for o in bpy.data.objects:
    if o.name.startswith('Acc_'):
        show = (acc == 'dagger' and 'Dagger' in o.name) or (acc == 'handprop' and 'HandProp' in o.name)
        o.hide_render = not show; o.hide_set(not show)
pose = arg('--pose', 'Idle:0').split(':')
if '--noground' in argv:
    g.hide_render = True
if '--anim' not in argv:
    set_action(pose[0], int(pose[1]))
    for v in VIEWS:
        if not v:
            continue
        aim(VIEW_POS[v], target if v != 'top' else Vector((0, 0, 0.3)))
        sc.render.filepath = os.path.join(OUT, v + '.png')
        bpy.ops.render.render(write_still=True)
        print('[render]', sc.render.filepath)
else:
    sc.render.resolution_x = sc.render.resolution_y = int(arg('--res', '360'))
    aim(VIEW_POS[arg('--animview', 'three_quarter')], Vector((0, 0, 0.45)), 70)
    for name in ('Idle', 'Run', 'Jump', 'Fall', 'Land', 'Slide'):
        a = bpy.data.actions[name]
        end = int(a.frame_range[1])
        for i in range(6):
            f = round(end * i / 6) if name in ('Idle', 'Run', 'Fall', 'Slide') else round(end * i / 5)
            set_action(name, f)
            sc.render.filepath = os.path.join(OUT, 'anim_%s_%02d.png' % (name, i))
            bpy.ops.render.render(write_still=True)
            print('[render]', sc.render.filepath, f)
