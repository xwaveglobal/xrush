# head close-ups of a built NinjaCharacter.blend in rest pose (Blender axes: faces -Y)
import bpy, sys, math
from mathutils import Vector
argv=sys.argv[sys.argv.index('--')+1:]
prefix=argv[0]; angles=[float(a) for a in argv[1].split(',')]; res=int(argv[2]) if len(argv)>2 else 600
pose=argv[3] if len(argv)>3 else 'REST'
sc=bpy.context.scene
rig=bpy.data.objects['Ninja_Rig']
if pose=='REST': rig.data.pose_position='REST'
else:
    a,f=pose.split(':'); rig.animation_data.action=bpy.data.actions[a]; sc.frame_set(int(f))
for o in list(sc.objects):
    if o.type=='MESH' and o.name!='Ninja_Body': o.hide_render=True
    if o.type in ('CAMERA','LIGHT'): bpy.data.objects.remove(o)
import os
if os.environ.get('CLAY'):
    cm=bpy.data.materials.new('clay'); cm.use_nodes=True
    b=cm.node_tree.nodes['Principled BSDF']; b.inputs['Base Color'].default_value=(0.6,0.6,0.62,1); b.inputs['Roughness'].default_value=0.6
    ob=bpy.data.objects['Ninja_Body']; ob.data.materials.clear(); ob.data.materials.append(cm)
if os.environ.get('NONRM'):
    for m in bpy.data.materials:
        if m.use_nodes:
            for n in m.node_tree.nodes:
                if n.type=='NORMAL_MAP':
                    for l in list(n.outputs[0].links): m.node_tree.links.remove(l)
sc.render.engine='CYCLES'; sc.cycles.samples=32; sc.render.resolution_x=sc.render.resolution_y=res
sc.render.film_transparent=False
w=bpy.data.worlds.new('w'); sc.world=w; w.use_nodes=True; w.node_tree.nodes['Background'].inputs[0].default_value=(0.55,0.55,0.55,1)
sun=bpy.data.objects.new('sun',bpy.data.lights.new('sun','SUN')); sun.data.energy=3; sc.collection.objects.link(sun)
cam=bpy.data.objects.new('cam',bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera=cam
cam.data.type='ORTHO'; zc=float(argv[4]) if len(argv)>4 else 0.78; cam.data.ortho_scale=float(argv[5]) if len(argv)>5 else 0.55
ctr=Vector((0,0,zc))
for a in angles:   # same convention as swap_render: 90 = front, 270 = back
    t=math.radians(a)
    d=Vector((-math.cos(t+math.pi/2)*0+math.sin(t)*0, 0,0))
    # front (90) = camera at -Y; back (270) = +Y; 0 = character's left (+X)
    cam.location=ctr+Vector((3*math.cos(t-math.pi/2+math.pi/2)*0+3*math.sin(t-math.pi/2+math.pi/2)*0,0,0))
    cam.location=ctr+Vector((3*math.cos(t),-3*math.sin(t),0.3))
    cam.rotation_euler=(ctr-cam.location).to_track_quat('-Z','Y').to_euler()
    sun.rotation_euler=(math.radians(45),0,math.radians(a+120))
    sc.render.filepath=f'{prefix}_{int(a):03d}.png'; bpy.ops.render.render(write_still=True)
