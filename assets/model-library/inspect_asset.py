"""Inspect or preview third-party assets without executing embedded text scripts."""
import argparse,json,sys,math
from pathlib import Path
import bpy
from mathutils import Vector
p=argparse.ArgumentParser();p.add_argument('--request',required=True);a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);request=json.loads(Path(a.request).read_text());out=Path(request['output']);out.mkdir(parents=True,exist_ok=True)
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
source=Path(request['file']);collections=[]
if source.suffix.lower()=='.blend':
 with bpy.data.libraries.load(str(source),link=False) as (available,loaded):
  collections=list(available.collections)
  chosen=request.get('collection')
  if not chosen:
   (out/'inspection.json').write_text(json.dumps({'collections':collections,'status':'choose_collection','approved':False},indent=2));sys.exit(0)
  if chosen not in collections:raise ValueError('Unknown collection: '+chosen)
  loaded.collections=[chosen]
 for collection in loaded.collections:bpy.context.scene.collection.children.link(collection)
elif source.suffix.lower() in ('.glb','.gltf'):bpy.ops.import_scene.gltf(filepath=str(source))
else:raise ValueError('Inspection supports blend collections and glTF/GLB')
objects=list(bpy.context.scene.objects);rigs=[o for o in objects if o.type=='ARMATURE']
for rig in rigs:
 for name,data in request.get('pose',{}).items():
  if name not in rig.pose.bones:raise ValueError('Unknown pose bone '+name)
  b=rig.pose.bones[name]
  if 'rotation' in data:b.rotation_mode='XYZ';b.rotation_euler=[math.radians(v) for v in data['rotation']]
  if 'location' in data:b.location=data['location']
bpy.context.view_layer.update()
scene=bpy.context.scene
mat=bpy.data.materials.new('SVD blue preview');mat.use_nodes=True;mat.diffuse_color=(.035,.24,.75,1);shader=mat.node_tree.nodes.get('Principled BSDF');shader.inputs['Base Color'].default_value=mat.diffuse_color;shader.inputs['Roughness'].default_value=.75
for o in objects:
 if o.type=='MESH':
  o.data.materials.clear();o.data.materials.append(mat)
  for polygon in o.data.polygons:polygon.material_index=0
# Renderable geometry only; rig widgets are usually hidden through their collection.
visible=[o for o in objects if o.type=='MESH' and not o.hide_render and not o.hide_get()]
if not visible:raise ValueError('No visible meshes in collection')
deps=bpy.context.evaluated_depsgraph_get();coords=[o.evaluated_get(deps).matrix_world@Vector(c) for o in visible for c in o.evaluated_get(deps).bound_box]
low=Vector([min(v[i] for v in coords) for i in range(3)]);high=Vector([max(v[i] for v in coords) for i in range(3)]);center=(low+high)/2;size=high-low;radius=max(size)*.85
bpy.ops.object.camera_add(location=center+Vector((radius,-radius*2,.3*radius)));camera=bpy.context.object;camera.rotation_euler=(center-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.type='ORTHO';camera.data.ortho_scale=max(size)*1.3;scene.camera=camera
bpy.ops.object.light_add(type='AREA',location=center+Vector((radius,-radius,radius*2)));bpy.context.object.data.energy=1000;bpy.context.object.data.size=radius*2
scene.render.engine='CYCLES';scene.cycles.samples=12;scene.render.resolution_x=640;scene.render.resolution_y=800;scene.render.resolution_percentage=100
missing=[im.filepath for im in bpy.data.images if im.source=='FILE' and not im.packed_file and im.filepath and not Path(bpy.path.abspath(im.filepath)).exists()]
invalid=[]
for ob in objects:
 if ob.animation_data:
  for driver in ob.animation_data.drivers:
   if not driver.driver.is_valid:invalid.append({'object':ob.name,'path':driver.data_path,'expression':driver.driver.expression})
report={'status':'inspected_needs_visual_review','file':str(source),'collection':request.get('collection'),'collections':collections,'bounds':{'min':list(low),'max':list(high)},'rigs':[{'name':r.name,'bones':[b.name for b in r.pose.bones]} for r in rigs],'missing_images':missing,'invalid_drivers':invalid,'embedded_scripts':[t.name for t in bpy.data.texts],'autoexec_enabled':bpy.context.preferences.filepaths.use_scripts_auto_execute,'approved':False,'limitations':['Pose and deformation require visual review.','No collision or rig controller compatibility certification.']}
(out/'inspection.json').write_text(json.dumps(report,indent=2));bpy.ops.wm.save_as_mainfile(filepath=str(out/'preview.blend'));scene.render.filepath=str(out/'preview.png');bpy.ops.render.render(write_still=True)
