"""Import a project-pinned model; external scripts remain disabled by the launcher."""
from pathlib import Path
import math
import bpy
from mathutils import Vector

def imported(c,material,empty,box):
    source=Path(c['file'])
    before=set(bpy.data.objects)
    if source.suffix.lower()=='.blend':
        with bpy.data.libraries.load(str(source),link=False) as (available,loaded):
            if c.get('collection') not in available.collections:raise ValueError('Select an existing model collection')
            loaded.collections=[c['collection']]
        for collection in loaded.collections:bpy.context.scene.collection.children.link(collection)
    elif source.suffix.lower() in ('.glb','.gltf'):bpy.ops.import_scene.gltf(filepath=str(source))
    else:raise ValueError('Asset components support blend/glb/gltf only')
    objects=set(bpy.data.objects)-before;rigs={o.name:o for o in objects if o.type=='ARMATURE'}
    # Object names may acquire Blender suffixes with multiple instances. Match original rig prefixes.
    root=empty(c['id']);scale=c.get('scale',1)
    for o in objects:
        if o.parent not in objects:
            world=o.matrix_world.copy();o.parent=root;o.matrix_world=world
        if o.type=='MESH':
            o.data.materials.clear();o.data.materials.append(material)
            for polygon in o.data.polygons:polygon.material_index=0
    root.location=c['position'];root.rotation_euler.z=math.radians(c.get('rotation_z',0));root.scale=(scale,)*3
    for k in c.get('keys',[]):
        if 'position' in k:root.location=k['position'];root.keyframe_insert('location',frame=k['frame'])
        if 'angle' in k:root.rotation_euler.z=math.radians(c.get('rotation_z',0)+k['angle']);root.keyframe_insert('rotation_euler',frame=k['frame'])
    for k in c.get('pose_keys',[]):
        candidates=[r for name,r in rigs.items() if name==k['rig'] or name.startswith(k['rig']+'.')]
        if len(candidates)!=1:raise ValueError('Ambiguous or missing imported rig: '+k['rig'])
        rig=candidates[0]
        if k['bone'] not in rig.pose.bones:raise ValueError('Missing control bone '+k['bone'])
        b=rig.pose.bones[k['bone']]
        if 'rotation' in k:b.rotation_mode='XYZ';b.rotation_euler=[math.radians(x) for x in k['rotation']];b.keyframe_insert('rotation_euler',frame=k['frame'])
        if 'location' in k:b.location=k['location'];b.keyframe_insert('location',frame=k['frame'])
        for prop,value in k.get('properties',{}).items():
            if prop not in b:raise ValueError('Missing rig property '+prop)
            b[prop]=value;b.keyframe_insert('['+repr(prop).replace("'",'"')+']',frame=k['frame'])
    colliders=[]
    for i,proxy in enumerate(c.get('collision_boxes',[])):
        o=box(c['id']+'/collision'+str(i),proxy['position'],proxy['size'],material,root)
        o.hide_render=True;o.hide_set(True);colliders.append(o)
    return root,colliders,{'id':c['id'],'rigs':list(rigs),'scope':'Imported rig pose/deformation and mesh collisions require visual review; only supplied collision boxes are checked.'}
