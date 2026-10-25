import bpy, sys
argv=sys.argv[sys.argv.index('--')+1:]
src,dst,target=argv[0],argv[1],int(argv[2])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
o=[o for o in bpy.context.scene.objects if o.type=='MESH'][0]
for im in bpy.data.images:
    if im.size[0]>2048: im.scale(2048,2048)
tris=sum(len(p.vertices)-2 for p in o.data.polygons)
bpy.context.view_layer.objects.active=o; o.select_set(True)
m=o.modifiers.new('dec','DECIMATE'); m.ratio=target/tris; m.use_collapse_triangulate=True
bpy.ops.object.modifier_apply(modifier='dec')
print('TRIS_OUT',sum(len(p.vertices)-2 for p in o.data.polygons))
bpy.ops.export_scene.gltf(filepath=dst,export_format='GLB',use_selection=True,export_image_format='AUTO')
