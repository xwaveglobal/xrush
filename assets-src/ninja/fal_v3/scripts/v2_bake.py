import bpy, sys, os
argv=sys.argv[sys.argv.index('--')+1:]
src,W,dst,fmt=argv[0],argv[1],argv[2],argv[3]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
lo=[o for o in bpy.context.scene.objects if o.type=='MESH'][0]; lo.name='Ninja'
himg=bpy.data.images.load(W+'height_v2.png'); himg.colorspace_settings.name='Non-Color'
htex=bpy.data.textures.new('h','IMAGE'); htex.image=himg; htex.extension='EXTEND'
# low: mild real displacement (strap/belt slightly raised)
bpy.ops.object.select_all(action='DESELECT'); bpy.context.view_layer.objects.active=lo; lo.select_set(True)
dl=lo.modifiers.new('disp','DISPLACE'); dl.texture=htex; dl.texture_coords='UV'; dl.strength=0.003; dl.mid_level=0.0
bpy.ops.object.modifier_apply(modifier='disp')
# also smooth-shade hi for clean bake
for o in (lo,):
    for p in o.data.polygons: p.use_smooth=True
# material
mat=lo.data.materials[0]; nt=mat.node_tree; N=nt.nodes; Lk=nt.links
bsdf=[n for n in N if n.type=='BSDF_PRINCIPLED'][0]
for n in list(N):
    if n.type in ('TEX_IMAGE','SEPARATE_COLOR','NORMAL_MAP'): N.remove(n)
bc=N.new('ShaderNodeTexImage'); bc.image=bpy.data.images.load(W+'basecolor_v2.png'); bc.image.alpha_mode='STRAIGHT'
Lk.new(bc.outputs['Color'],bsdf.inputs['Base Color']); Lk.new(bc.outputs['Alpha'],bsdf.inputs['Alpha'])
mr=N.new('ShaderNodeTexImage'); mr.image=bpy.data.images.load(W+'mr_v2.png'); mr.image.colorspace_settings.name='Non-Color'
sep=N.new('ShaderNodeSeparateColor'); Lk.new(mr.outputs['Color'],sep.inputs['Color'])
Lk.new(sep.outputs['Green'],bsdf.inputs['Roughness']); Lk.new(sep.outputs['Blue'],bsdf.inputs['Metallic'])
mat.blend_method='CLIP' if hasattr(mat,'blend_method') else None
try: mat.alpha_threshold=0.5
except: pass
mat.use_backface_culling=False
# normal bake: bump from height map baked to tangent-space normal map (no ray casting artefacts)
hn=N.new('ShaderNodeTexImage'); hn.image=himg; hn.interpolation='Cubic'
bump=N.new('ShaderNodeBump'); bump.inputs['Strength'].default_value=1.0; bump.inputs['Distance'].default_value=0.0035
Lk.new(hn.outputs['Color'],bump.inputs['Height']); Lk.new(bump.outputs['Normal'],bsdf.inputs['Normal'])
nimg=bpy.data.images.new('ninja_normal',2048,2048); nimg.colorspace_settings.name='Non-Color'
nn=N.new('ShaderNodeTexImage'); nn.image=nimg; N.active=nn
sc=bpy.context.scene; sc.render.engine='CYCLES'; sc.cycles.samples=1; sc.cycles.device='CPU'
bpy.ops.object.select_all(action='DESELECT'); lo.select_set(True); bpy.context.view_layer.objects.active=lo
sc.render.bake.use_selected_to_active=False; sc.render.bake.margin=8
bpy.ops.object.bake(type='NORMAL',normal_space='TANGENT')
nimg.filepath_raw=W+'normal_v2.png'; nimg.file_format='PNG'; nimg.save()
N.remove(bump); N.remove(hn)
nimg2=bpy.data.images.load(W+'normal_v2.png'); nimg2.colorspace_settings.name='Non-Color'; nn.image=nimg2
nm=N.new('ShaderNodeNormalMap'); Lk.new(nn.outputs['Color'],nm.inputs['Color']); Lk.new(nm.outputs['Normal'],bsdf.inputs['Normal'])
print('TRIS',sum(len(p.vertices)-2 for p in lo.data.polygons))
bpy.ops.wm.save_as_mainfile(filepath=W+'NinjaCharacter_v2.blend')
bpy.ops.object.select_all(action='DESELECT'); lo.select_set(True)
bpy.ops.export_scene.gltf(filepath=dst,export_format='GLB',use_selection=True,export_image_format=fmt,export_image_quality=90)
