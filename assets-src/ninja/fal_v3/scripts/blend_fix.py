import bpy, sys
argv=sys.argv[sys.argv.index('--')+1:]
src,texp,dst,target=argv[0],argv[1],argv[2],int(argv[3])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
o=[o for o in bpy.context.scene.objects if o.type=='MESH'][0]
img=bpy.data.images.load(texp); img.name='ninja_basecolor'
for m in o.data.materials:
    for n in m.node_tree.nodes:
        if n.type=='TEX_IMAGE': n.image=img
tris=sum(len(p.vertices)-2 for p in o.data.polygons)
bpy.context.view_layer.objects.active=o; o.select_set(True)
mod=o.modifiers.new('dec','DECIMATE'); mod.decimate_type='COLLAPSE'; mod.ratio=target/tris; mod.use_collapse_triangulate=True
bpy.ops.object.modifier_apply(modifier='dec')
print('TRIS_OUT',sum(len(p.vertices)-2 for p in o.data.polygons))
bpy.ops.export_scene.gltf(filepath=dst,export_format='GLB',use_selection=True,export_image_format='JPEG',export_jpeg_quality=92,export_apply=True)
