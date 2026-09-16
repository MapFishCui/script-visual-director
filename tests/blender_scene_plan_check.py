import bpy,sys,json,math,argparse,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'assets/blender/modeling'))
parser=argparse.ArgumentParser();parser.add_argument('--model',required=True);parser.add_argument('--out',required=True);args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
from component_kit import build
from scene_executor import SnowAdapter
base=Path(args.out).resolve();base.mkdir(parents=True,exist_ok=False)
spec={'schema_version':1,'components':[{'id':'person','type':'asset','category':'actor','position':[0,0,0],'file':str(Path(args.model).resolve()),'collection':'CH-snow'}]}
m=build(spec);a=SnowAdapter(m['objects']['person']);r=a.rig;targets={}
for eff,prefix,pole in [('hand.L','IK-MSTR-Wrist.L','IK-POLE-UpperArm.L'),('hand.R','IK-MSTR-Wrist.R','IK-POLE-UpperArm.R'),('foot.L','IK-MSTR-Foot.L','IK-POLE-Thigh.L'),('foot.R','IK-MSTR-Foot.R','IK-POLE-Thigh.R')]:
 b=r.pose.bones[prefix];position=list(r.matrix_world@b.head)
 # Lower the pelvis while leaving feet on their initial support plane.
 if eff.startswith('foot'):position[2]+=.10
 targets[eff]={'position':position,'rotation':[math.degrees(v) for v in b.matrix.to_euler()],'pole':list(r.matrix_world@r.pose.bones[pole].head)}
sample={'time':0,'position':[0,0,-.10],'rotation':[0,0,0],'targets':targets}
component={'id':'person','type':'asset','category':'actor','position':[0,0,0],'asset_key':'blender-snow@3','model':'snow_v03.blend','collection':'CH-snow'}
p={'schema_version':1,'fps':12,'duration':1,'scene':{'schema_version':1,'preview':{'width':480,'height':360},'components':[component]},'actors':[{'id':'person','adapter':'snow-v3'}],'actions':[{'id':'pose','object':'person','kind':'rig_pose','intent':'绑定诊断：屈膝方向，不是自然表演示范','origin':'explicit','start':{'at':0},'duration':1,'samples':[sample,{**sample,'time':1}]}],'cameras':[{'id':'side','target':'person','target_offset':[0,0,1],'offset':[3,-4,1],'lens':65,'follow':False,'start':{'at':0},'duration':1}]}
from scene_executor import run
p['scene']['fps']=12;p['scene']['frames']=12;p['scene']['components'][0]['file']=str(Path(args.model).resolve())
for action in p['actions']:action['start_frame']=1;action['end_frame']=12
for camera in p['cameras']:camera['start_frame']=1;camera['end_frame']=12
# Rotate the whole character to prove the knee test is body-relative.
for sample in p['actions'][0]['samples']:sample['rotation']=[0,0,90]
normal=base/'normal';normal.mkdir();report=run(copy.deepcopy(p),normal)
assert not report['findings'],report
for sample in p['actions'][0]['samples']:
 for eff in ('foot.L','foot.R'):sample['targets'][eff]['pole'][1]=2
bad=base/'reversed';bad.mkdir();report=run(copy.deepcopy(p),bad)
assert report['status']=='failed' and {x.get('side') for x in report['findings'] if x['kind']=='reversed_knee_plane'}=={'L','R'},report
print('SCENE_EXECUTOR_REGRESSION_OK')
