"""Blender execution of compiled scene plans. Never substitutes unsupported actions."""
import argparse, json, math, sys
from pathlib import Path
import bpy
from mathutils import Vector, Euler
sys.path.insert(0,str(Path(__file__).resolve().parent))
from component_kit import build, check_scene


def owner(obj):
    while obj.parent:obj=obj.parent
    return obj

class SnowAdapter:
    controls={'hand.':'IK-MSTR-Wrist.','foot.':'IK-MSTR-Foot.'}
    def __init__(self,root):
        self.root=root
        rigs=[o for o in bpy.context.scene.objects if o.type=='ARMATURE' and owner(o)==root]
        if len(rigs)!=1:raise ValueError('Snow adapter requires one rig per actor')
        self.rig=rigs[0];self.rest={b.name:b.matrix_basis.copy() for b in self.rig.pose.bones}
        if self.rig.animation_data:
            self.rig.animation_data.action=None
            for track in list(self.rig.animation_data.nla_tracks):self.rig.animation_data.nla_tracks.remove(track)
        for side in ('L','R'):
            for name in ('IK-MSTR-Wrist.','IK-MSTR-Foot.','IK-POLE-UpperArm.','IK-POLE-Thigh.','IK-Thigh.','IK-Foot.','DEF-Wrist.'):
                if name+side not in self.rig.pose.bones:raise ValueError('Snow control missing: '+name+side)
        p=self.rig.pose.bones['Properties']
        for side in ('left','right'):
            for part in ('upperarm','thigh'):
                name='ik_'+side+'_'+part
                if name not in p:raise ValueError('Snow IK property missing')
                p[name]=1;p['ik_stretch_'+side+'_'+part]=0
        self.rig.update_tag();bpy.context.view_layer.update()
        self.targets={}
    def apply(self,sample,frame,contacts,anchors):
        for b in self.rig.pose.bones:b.matrix_basis=self.rest[b.name].copy()
        self.root.location=sample['position'];self.root.rotation_mode='QUATERNION';self.root.rotation_quaternion=Euler([math.radians(x) for x in sample['rotation']]).to_quaternion()
        bpy.context.view_layer.update();self.targets={}
        for eff,t in sample['targets'].items():
            side=eff[-1];kind=eff.split('.')[0]+'.';control=self.controls[kind]+side;pole=('IK-POLE-UpperArm.' if kind=='hand.' else 'IK-POLE-Thigh.')+side
            world=self.root.matrix_world;pos=world@Vector(t['position']);q=world.to_quaternion()@Euler([math.radians(x) for x in t['rotation']]).to_quaternion()
            for c in contacts:
                if c['effector']==eff and c['start_frame']<=frame<c['end_frame']:
                    anchor=anchors[c['anchor']];m=anchor['object'].matrix_world;pos=m@Vector(anchor['offset']);q=m.to_quaternion()@Euler([math.radians(x) for x in anchor['rotation']]).to_quaternion()
            self.targets[eff]=pos.copy()
            for name,point,rotation in ((pole,world@Vector(t['pole']),q),(control,pos,q)):
                b=self.rig.pose.bones[name];mat=rotation.to_matrix().to_4x4();mat.translation=point;b.matrix=self.rig.matrix_world.inverted()@mat
                b.rotation_mode='QUATERNION';b.keyframe_insert('location',frame=frame);b.keyframe_insert('rotation_quaternion',frame=frame)
                bpy.context.view_layer.update()
        self.root.keyframe_insert('location',frame=frame);self.root.keyframe_insert('rotation_quaternion',frame=frame)
    def inspect(self,frame):
        findings=[];r=self.rig;m=r.matrix_world;front=self.root.matrix_world.to_quaternion()@Vector((0,-1,0))
        for side in ('L','R'):
            thigh=r.pose.bones['IK-Thigh.'+side];hip=m@thigh.head;knee=m@thigh.tail;ankle=m@r.pose.bones['IK-Foot.'+side].head
            axis=ankle-hip
            if axis.length<1e-6:findings.append({'kind':'collapsed_leg','side':side});continue
            projection=hip+axis*((knee-hip).dot(axis)/axis.length_squared);bend=knee-projection
            if bend.length>.015 and bend.dot(front)<-.008:findings.append({'kind':'reversed_knee_plane','side':side,'error_m':round(-bend.dot(front),4)})
            flex=(knee-hip).angle(ankle-knee,0)
            if flex>math.radians(155):findings.append({'kind':'knee_overflex','side':side})
        for eff,target in self.targets.items():
            actual=m@r.pose.bones[('DEF-Wrist.' if eff.startswith('hand') else 'IK-Foot.')+eff[-1]].head
            error=(actual-target).length
            if error>.035:findings.append({'kind':'unreachable_effector','effector':eff,'error_m':round(error,4)})
        for d in r.animation_data.drivers if r.animation_data else []:
            if not d.driver.is_valid:findings.append({'kind':'invalid_driver','path':d.data_path})
        return [{**f,'actor':self.root.name,'frame':frame} for f in findings]


def interpolate(samples,t):
    if t<=samples[0]['time']:return samples[0]
    if t>=samples[-1]['time']:return samples[-1]
    a,b=next((a,b) for a,b in zip(samples,samples[1:]) if a['time']<=t<=b['time']);u=(t-a['time'])/(b['time']-a['time'])
    def vec(a,b):return list(Vector(a).lerp(Vector(b),u))
    def rot(a,b):
        q=Euler([math.radians(x) for x in a]).to_quaternion().slerp(Euler([math.radians(x) for x in b]).to_quaternion(),u)
        return [math.degrees(x) for x in q.to_euler()]
    return {'position':vec(a['position'],b['position']),'rotation':rot(a['rotation'],b['rotation']),'targets':{k:{n:(rot if n=='rotation' else vec)(a['targets'][k][n],b['targets'][k][n]) for n in ('position','rotation','pole')} for k in a['targets']}}


def run(plan,out,render=False):
    for c in plan['scene']['components']:
        if c['type']=='asset':c['file']=str((out/c['file']).resolve())
    model=build(plan['scene']);scene=bpy.context.scene;objects=model['objects'];frames=scene.frame_end;fps=plan['fps']
    adapters={a['id']:SnowAdapter(objects[a['id']]) for a in plan['actors']}
    anchors={a['id']:{**a,'object':objects[a['object']]} for a in plan.get('anchors',[])}
    saved={};starts={};camera_origins={};camera=scene.camera;findings=[]
    for frame in range(1,frames+1):
        scene.frame_set(frame)
        # Stage 1: all props, so moving anchors are evaluated before character constraints.
        for a in plan['actions']:
            if a['kind']!='object_motion' or not a['start_frame']<=frame<=a['end_frame']:continue
            o=objects[a['object']]
            if a['id'] not in starts:starts[a['id']]=(o.location.copy(),o.rotation_euler.z)
            pos,angle=starts[a['id']];u=(frame-a['start_frame'])/max(1,a['end_frame']-a['start_frame'])
            o.location=pos.lerp(Vector(a.get('end_position',pos)),u);o.rotation_euler.z=angle+(math.radians(a['end_angle'])-angle)*u if 'end_angle' in a else angle
            o.keyframe_insert('location',frame=frame);o.keyframe_insert('rotation_euler',frame=frame)
        bpy.context.view_layer.update()
        for a in plan['actions']:
            if a['object'] not in adapters or not a['start_frame']<=frame<=a['end_frame']:continue
            aid=a['object']
            if a['kind']=='rig_pose':saved[aid]=interpolate(a['samples'],(frame-a['start_frame'])/max(1,a['end_frame']-a['start_frame'])*a['duration'])
            if aid not in saved:raise ValueError('Actor has no explicit starting pose')
            adapters[aid].apply(saved[aid],frame,[c for c in plan.get('contacts',[]) if c['actor']==aid],anchors)
        bpy.context.view_layer.update()
        c=next(c for c in reversed(plan['cameras']) if c['start_frame']<=frame<=c['end_frame'])
        target=objects[c['target']].matrix_world@Vector(c['target_offset']);position=target+Vector(c['offset'])
        if c['id'] not in camera_origins:camera_origins[c['id']]=(position.copy(),target.copy())
        if not c['follow']:position,target=camera_origins[c['id']]
        camera.location=position;camera.rotation_mode='QUATERNION';camera.rotation_quaternion=(target-position).to_track_quat('-Z','Y');camera.data.lens=c['lens']
        for prop in ('location','rotation_quaternion'):camera.keyframe_insert(prop,frame=frame)
        camera.data.keyframe_insert('lens',frame=frame)
    base_report=check_scene(model);collider_names=[o.name for o in model['colliders']]
    findings.extend(base_report['findings'])
    scene.frame_set(1);bpy.ops.wm.save_as_mainfile(filepath=str(out/'scene.blend'))
    # Reload from disk to check actual animation playback, including rig drivers.
    bpy.ops.wm.open_mainfile(filepath=str(out/'scene.blend'),use_scripts=False);scene=bpy.context.scene;camera=scene.camera
    # Read-only adapter handles: do not clear saved animation.
    for aid,a in adapters.items():a.root=bpy.data.objects[aid];a.rig=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE' and owner(o)==a.root)
    saved={}
    for frame in range(1,frames+1):
        scene.frame_set(frame)
        for aid,a in adapters.items():
            a.targets={}
            for action in plan['actions']:
                if action['object']==aid and action['kind']=='rig_pose' and action['start_frame']<=frame:saved[aid]=interpolate(action['samples'],(frame-action['start_frame'])/max(1,action['end_frame']-action['start_frame'])*action['duration'])
            if aid in saved:
                for eff,t in saved[aid]['targets'].items():a.targets[eff]=a.root.matrix_world@Vector(t['position'])
            for c in plan.get('contacts',[]):
                if c['actor']==aid and c['start_frame']<=frame<c['end_frame']:
                    anchor=anchors[c['anchor']];parent=bpy.data.objects[next(x['object'] for x in plan['anchors'] if x['id']==c['anchor'])]
                    a.targets[c['effector']]=parent.matrix_world@Vector(anchor['offset'])
            findings+=a.inspect(frame)
        c=next(c for c in reversed(plan['cameras']) if c['start_frame']<=frame<=c['end_frame'])
        target=bpy.data.objects[c['target']].matrix_world@Vector(c['target_offset'])
        delta=target-camera.location
        if delta.length>1e-5:
            hit,loc,normal,index,ob,matrix=scene.ray_cast(bpy.context.evaluated_depsgraph_get(),camera.location,delta.normalized(),distance=delta.length-.01)
            if hit and owner(ob).name!=c['target']:findings.append({'kind':'camera_target_occluded','camera':c['id'],'frame':frame,'object':ob.name})
        for name in collider_names:
            ob=bpy.data.objects[name];point=ob.matrix_world.inverted()@camera.location
            if all(min(v[i] for v in ob.bound_box)<point[i]<max(v[i] for v in ob.bound_box) for i in range(3)):findings.append({'kind':'camera_inside_collider','camera':c['id'],'object':name,'frame':frame})
        from bpy_extras.object_utils import world_to_camera_view
        v=world_to_camera_view(scene,camera,target)
        if v.z<=0 or not (0<=v.x<=1 and 0<=v.y<=1):findings.append({'kind':'camera_target_out_of_frame','camera':c['id'],'frame':frame})
    # Deduplicate by category/object, retaining first occurrence and count.
    grouped={}
    for f in findings:
        key=(f['kind'],f.get('actor'),f.get('side'),f.get('effector'),f.get('camera'))
        if key not in grouped:grouped[key]={**f,'occurrences':1}
        else:grouped[key]['occurrences']+=1
    report={'status':'failed' if findings else 'partial','findings':list(grouped.values()),'frames':frames,'scope':'Reloaded animation: Snow IK reach, calibrated forward knee plane, excessive knee flexion, driver validity; camera target projection, view-ray occlusion and box-proxy camera collision; existing component collision checks. Full mesh collisions, self-collision, foot rolling, physical balance and performance naturalness remain unverified.','approved':False,'reference_eligibility':{'spatial':'unreviewed','camera':'unreviewed','motion':'unreviewed'}}
    (out/'execution-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    for frame in sorted({1,frames//2,frames}):
        scene.frame_set(frame);scene.render.filepath=str(out/f'diagnostic-{frame:06}.png');bpy.ops.render.render(write_still=True)
    if render and not findings:
        (out/'frames').mkdir()
        for frame in range(1,frames+1):
            scene.frame_set(frame);scene.render.filepath=str(out/'frames'/f'{frame:06}.png');bpy.ops.render.render(write_still=True)
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--plan',required=True);parser.add_argument('--out',required=True);parser.add_argument('--render',action='store_true')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);run(json.loads(Path(args.plan).read_text()),Path(args.out),args.render)
