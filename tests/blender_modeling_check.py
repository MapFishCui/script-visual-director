import sys,json,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'assets/blender/modeling'))
from component_kit import build,check_scene
import bpy
base={'schema_version':1,'frames':3,'components':[{'id':'person','type':'actor','position':[0,0,0]}]}
def check(s):return check_scene(build(s))
assert check(base)['status']=='passed'
s=copy.deepcopy(base);s['components'].append({'id':'wall','type':'box','position':[0,0,1.2],'size':[1,.3,2]})
r=check(s);assert any(x['kind']=='environment_intersection' for x in r['findings'])
s=copy.deepcopy(base);s['components'].append({'id':'grip','type':'anchor','position':[4,0,1]});s['contacts']=[{'actor':'person','effector':'hand.R','target':'grip','start':1,'end':3}]
r=check(s);assert {'contact_lost','ik_target_unreached'} <= {x['kind'] for x in r['findings']}
s=copy.deepcopy(base);s['components'][0]['keys']=[{'frame':1,'position':[0,0,0]},{'frame':3,'position':[.02,0,0]}];s['components'].append({'id':'grip','type':'anchor','position':[.4,-.04,.94]});s['contacts']=[{'actor':'person','effector':'hand.R','target':'grip','start':1,'end':3}]
s['components'].append({'id':'held','type':'box','position':[0,0,0],'size':[.03,.03,.03]});s['attachments']=[{'actor':'person','effector':'hand.L','object':'held','offset':[0,.12,0]}]
m=build(s);r=check_scene(m);assert r['status']=='passed',r
for f in (1,3):
 bpy.context.scene.frame_set(f);deps=bpy.context.evaluated_depsgraph_get();o=m['objects']['held'].evaluated_get(deps);end=m['actors']['person']['endpoints']['hand.L'].evaluated_get(deps)
 assert abs((o.matrix_world.translation-end.matrix_world.translation).length-.12)<1e-4
print('BLENDER_COMPONENT_TESTS_PASSED: default rig, collision rejection, unreachable contact rejection, moving root contact, held prop')

s=copy.deepcopy(base);s['frames']=24;s['components']=[{'id':'floor','type':'box','position':[0,0,-.1],'size':[4,4,.2],'physics':'static'},{'id':'falling','type':'box','position':[0,0,1],'size':[.2,.2,.2],'physics':'dynamic'}]
m=build(s)
def height(frame):
 bpy.context.scene.frame_set(frame);return m['colliders'][1].evaluated_get(bpy.context.evaluated_depsgraph_get()).matrix_world.translation.z
z=height(24);assert .05<z<.3,z
height(1);assert abs(height(24)-z)<1e-4
print('BLENDER_RIGID_CACHE_PASSED')

# Feet follow actual ankles in position, but not the shin IK twist.
from mathutils import Vector
s=copy.deepcopy(base);s['components'][0]['rotation_z']=60
s['components'][0]['keys']=[{'frame':1,'angle':0},{'frame':3,'angle':30,'targets':{'foot.L':[-.105,-.12,.15]}}]
m=build(s)
for frame in (1,2,3):
 bpy.context.scene.frame_set(frame);deps=bpy.context.evaluated_depsgraph_get()
 root=m['actors']['person']['root'].evaluated_get(deps)
 forward=root.matrix_world.to_quaternion()@Vector((0,-1,0))
 for side in ('L','R'):
  toe=bpy.data.objects['person/foot.'+side+'/toe'].evaluated_get(deps).matrix_world.translation
  heel=bpy.data.objects['person/foot.'+side+'/heel'].evaluated_get(deps).matrix_world.translation
  delta=toe-heel
  assert delta.normalized().dot(forward)>.99,(frame,side,delta)
  foot=m['actors']['person']['endpoints']['foot.'+side].evaluated_get(deps)
  rig=m['actors']['person']['rig'].evaluated_get(deps)
  assert (foot.matrix_world.translation-rig.matrix_world@rig.pose.bones['shin.'+side].tail).length<1e-5
print('BLENDER_FOOT_ORIENTATION_PASSED')
