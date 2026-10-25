import bpy, sys, math
from mathutils import Vector
argv=sys.argv[sys.argv.index('--')+1:]
glb,texp,prefix,angles=argv[0],argv[1],argv[2],[float(a) for a in argv[3].split(',')]
res=int(argv[4]) if len(argv)>4 else 512
zoom=float(argv[5]) if len(argv)>5 else 1.0
zc=float(argv[6]) if len(argv)>6 else 0.0
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)
objs=[o for o in bpy.context.scene.objects if o.type=='MESH']
if texp!='-':
    img=bpy.data.images.load(texp)
    for o in objs:
        for m in o.data.materials:
            for n in m.node_tree.nodes:
                if n.type=='TEX_IMAGE' and n.image and 'base' in n.image.name.lower(): n.image=img
mn=Vector((1e9,)*3); mx=Vector((-1e9,)*3)
for o in objs:
    for c in o.bound_box:
        w=o.matrix_world@Vector(c); mn=Vector(map(min,mn,w)); mx=Vector(map(max,mx,w))
ctr=(mn+mx)/2; h=mx.z-mn.z; ctr.z+=zc*h
sc=bpy.context.scene; sc.render.engine='CYCLES'; sc.cycles.samples=32
sc.render.resolution_x=sc.render.resolution_y=res
w=bpy.data.worlds.new('w'); sc.world=w; w.use_nodes=True; w.node_tree.nodes['Background'].inputs[0].default_value=(0.55,0.55,0.55,1)
sun=bpy.data.objects.new('sun',bpy.data.lights.new('sun','SUN')); sun.data.energy=3; sc.collection.objects.link(sun)
cam=bpy.data.objects.new('cam',bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera=cam
cam.data.type='ORTHO'; cam.data.ortho_scale=h*1.15/zoom
for a in angles:
    t=math.radians(a)
    cam.location=ctr+Vector((3*math.sin(t),-3*math.cos(t),0.15*h))
    cam.rotation_euler=(ctr-cam.location).to_track_quat('-Z','Y').to_euler()
    sun.rotation_euler=(math.radians(45),0,t+math.radians(30))
    sc.render.filepath=f'{prefix}_{int(a):03d}.png'; bpy.ops.render.render(write_still=True)
