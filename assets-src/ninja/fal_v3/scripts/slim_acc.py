import bpy
bpy.ops.wm.open_mainfile(filepath='/workspace/free3d/v3/accessories_src.blend')
keep={'Acc_Dagger','Acc_HandProp','Ninja_Rig'}
for o in list(bpy.data.objects):
    if o.name not in keep: bpy.data.objects.remove(o)
for a in list(bpy.data.actions): bpy.data.actions.remove(a)
r=bpy.data.objects['Ninja_Rig']; r.animation_data_clear()
bpy.data.orphans_purge(do_recursive=True)
for m in bpy.data.meshes: print('mesh',m.name,len(m.vertices),[x.name for x in m.materials])
for i in bpy.data.images: print('img',i.name,i.size[:])
bpy.ops.file.pack_all()
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath='/workspace/xrush/assets-src/ninja/fal_v3/accessories.blend',compress=True)
