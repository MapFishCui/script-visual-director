"""Compile director-authored scene plans. No keyword-to-animation substitution."""
import copy, hashlib, html, json, math, shutil
from pathlib import Path
from jsonschema import Draft202012Validator
from core import read_json, write_json, safe_path
import modeling, previs

V=modeling.VEC; ID=modeling.ID; obj=modeling.obj; arr=modeling.arr
NUM={'type':'number'}; POS=modeling.POS
START={'oneOf':[obj({'at':{'type':'number','minimum':0}},['at']),obj({'after':ID,'offset':{'type':'number','minimum':0}},['after'])]}
TARGET=obj({'position':V,'rotation':V,'pole':V},['position','rotation','pole'])
SAMPLE=obj({'time':{'type':'number','minimum':0},'position':V,'rotation':V,'targets':{'type':'object','propertyNames':modeling.EFF,'additionalProperties':TARGET}},['time','position','rotation','targets'])
ACTION=obj({'id':ID,'object':ID,'kind':{'type':'string'},'intent':{'type':'string','minLength':1},'start':START,'duration':POS,'origin':{'enum':['explicit','inferred','proposed']},'from_state':{'type':'string'},'to_state':{'type':'string'},'samples':arr(SAMPLE),'end_position':V,'end_angle':NUM},['id','object','kind','intent','start','duration','origin'])
CAM=obj({'id':ID,'target':ID,'offset':V,'target_offset':V,'lens':{'type':'number','minimum':12,'maximum':200},'follow':{'type':'boolean'},'start':START,'duration':POS},['id','target','offset','target_offset','lens','follow','start','duration'])
CONTACT=obj({'actor':ID,'effector':modeling.EFF,'anchor':ID,'start':START,'duration':POS},['actor','effector','anchor','start','duration'])
PLAN=obj({'schema_version':{'const':1},'fps':{'type':'integer','minimum':1,'maximum':60},'duration':POS,'scene':modeling.SPEC,'actors':arr(obj({'id':ID,'adapter':{'enum':['snow-v3']}},['id','adapter'])),'anchors':arr(obj({'id':ID,'object':ID,'offset':V,'rotation':V},['id','object','offset','rotation'])),'actions':arr(ACTION),'cameras':arr(CAM),'contacts':arr(CONTACT)},['schema_version','fps','duration','scene','actors','actions','cameras'])
SUPPORTED={'hold','object_motion','rig_pose'}

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()

def compile_plan(plan):
    # Reject NaN/Infinity even when a permissive JSON reader accepts them.
    digest(plan)
    errors=list(Draft202012Validator(PLAN).iter_errors(plan))
    if errors:raise ValueError('; '.join(str(list(e.path))+': '+e.message for e in errors[:3]))
    p=copy.deepcopy(plan);fps=p['fps'];duration=p['duration'];frames=round(duration*fps)
    if frames<2 or frames>10000 or abs(frames-duration*fps)>1e-6:raise ValueError('时长须对应 2–10000 个整数帧')
    scene=p['scene'];scene['fps']=fps;scene['frames']=frames;modeling.validate(scene)
    objects={c['id']:c for c in scene['components']}
    def unique(rows,label):
        ids=[r['id'] for r in rows]
        if len(ids)!=len(set(ids)):raise ValueError(label+'编号重复')
        return {r['id']:r for r in rows}
    actors=unique(p['actors'],'角色');actions=unique(p['actions'],'行动');unique(p['cameras'],'摄影机');anchors=unique(p.get('anchors',[]),'锚点')
    for a in actors.values():
        c=objects.get(a['id'],{})
        if c.get('type')!='asset' or c.get('category')!='actor':raise ValueError('角色适配器需要已锁定的 asset 人物')
        if c.get('asset_key')!='blender-snow@3' or c.get('collection')!='CH-snow':raise ValueError('snow-v3 只适配已锁定 Snow v3 / CH-snow')
        if c.get('keys') or c.get('pose_keys'):raise ValueError('人物动画由 ActionPlan 唯一驱动，不能叠加组件关键帧')
    for a in anchors.values():
        if a['object'] not in objects:raise ValueError('锚点父物体不存在')
    resolved={};visiting=set()
    def time(start):
        if 'at' in start:return start['at']
        if start['after'] not in actions:raise ValueError('时间依赖不存在：'+start['after'])
        return resolve(start['after'])[1]+start.get('offset',0)
    def resolve(aid):
        if aid in resolved:return resolved[aid]
        if aid in visiting:raise ValueError('行动时间依赖成环')
        visiting.add(aid);a=actions[aid];t=time(a['start']);resolved[aid]=(t,t+a['duration']);visiting.remove(aid);return resolved[aid]
    def interval(row,t):
        end=t+row['duration']
        if t<0 or end>duration+1e-6:raise ValueError('事件超出总时长')
        if any(abs(v*fps-round(v*fps))>1e-6 for v in (t,end)):raise ValueError('事件时间须对齐帧率')
        row['start_frame']=1+round(t*fps);row['end_frame']=min(frames,1+round(end*fps));return t,end
    findings=[];per_object={}
    for c in objects.values():
        if (c['type']=='actor' or c.get('category')=='actor') and c['id'] not in actors:
            findings.append({'kind':'unadapted_actor','object':c['id'],'message':'人物没有可执行的成熟绑定适配，不使用默认代理姿态替代。'})
    for aid,a in actions.items():
        if a['object'] not in objects:raise ValueError('行动对象不存在：'+a['object'])
        t,end=resolve(aid);interval(a,t);c=objects[a['object']]
        per_object.setdefault(a['object'],[]).append((t,end,a))
        if a['kind'] not in SUPPORTED:findings.append({'kind':'unsupported_action','action':aid,'requested':a['kind'],'message':'没有可执行动作；须提供适配后的姿态轨迹或另行制作，不生成替代动画。'});continue
        if a['kind']=='hold' and any(k in a for k in ('samples','end_position','end_angle')):raise ValueError('hold 不接受未执行的运动参数')
        if a['kind']=='object_motion':
            if c['type'] in ('actor','anchor') or c.get('category')=='actor':raise ValueError('不能用物体平移代替人物动作')
            if c.get('keys') or c.get('physics') in ('static','dynamic'):raise ValueError('物件有冲突的动画/物理驱动')
            if 'end_position' not in a and 'end_angle' not in a:raise ValueError('object_motion 缺少目标')
            if 'samples' in a:raise ValueError('object_motion 不接受人物轨迹')
        if a['kind']=='rig_pose':
            if a['object'] not in actors:raise ValueError('rig_pose 缺少角色适配器')
            if 'end_position' in a or 'end_angle' in a:raise ValueError('rig_pose 的位置由 samples 唯一确定')
            samples=a.get('samples',[])
            if len(samples)<2 or samples[0]['time']!=0 or abs(samples[-1]['time']-a['duration'])>1e-6:raise ValueError('姿态轨迹必须覆盖动作起止')
            if any(x['time']>=y['time'] for x,y in zip(samples,samples[1:])):raise ValueError('姿态采样时间必须递增')
            for sample in samples:
                if abs(sample['time']*fps-round(sample['time']*fps))>1e-6:raise ValueError('姿态采样须对齐帧率')
                if set(sample['targets'])!={'hand.L','hand.R','foot.L','foot.R'}:raise ValueError('每个姿态须明确四肢目标及 pole')
    for oid,rows in per_object.items():
        rows.sort(key=lambda x:x[0])
        for prev,nxt in zip(rows,rows[1:]):
            if nxt[0]<prev[1]-1e-6:raise ValueError('同一对象的行动重叠：'+oid)
            if prev[2].get('to_state') and nxt[2].get('from_state') and prev[2]['to_state']!=nxt[2]['from_state']:raise ValueError('动作起止状态不匹配：'+oid)
            if prev[2]['kind']==nxt[2]['kind']=='rig_pose':
                a,b=prev[2]['samples'][-1],nxt[2]['samples'][0]
                if any(a[k]!=b[k] for k in ('position','rotation','targets')):raise ValueError('姿态衔接不连续：须提供过渡动作 '+oid)
    for oid in actors:
        rows=per_object.get(oid,[])
        if not rows or rows[0][0]!=0 or abs(rows[-1][1]-duration)>1e-6 or any(abs(a[1]-b[0])>1e-6 for a,b in zip(rows,rows[1:])):raise ValueError('人物时间轴须明确覆盖全段，停留用 hold：'+oid)
        if rows[0][2]['kind']=='hold':findings.append({'kind':'unposed_actor','object':oid,'message':'初始 hold 没有已定义姿态，不能把模型默认站姿当表演。'})
    for c in p['cameras']:
        if c['target'] not in objects:raise ValueError('摄影目标不存在')
        interval(c,time(c['start']))
        if sum(v*v for v in c['offset'])<.01:raise ValueError('摄影机与观察目标过近')
    cameras=sorted(p['cameras'],key=lambda c:c['start_frame'])
    if not cameras or cameras[0]['start_frame']!=1 or cameras[-1]['end_frame']!=frames or any(a['end_frame']!=b['start_frame'] for a,b in zip(cameras,cameras[1:])):raise ValueError('摄影机时间轴须连续、无重叠地覆盖全段')
    for c in p.get('contacts',[]):
        if c['actor'] not in actors or c['anchor'] not in anchors:raise ValueError('接触引用不存在')
        if anchors[c['anchor']]['object'] in actors:raise ValueError('当前接触目标仅支持非人物物件，避免角色间循环控制')
        interval(c,time(c['start']))
    for i,c in enumerate(p.get('contacts',[])):
        for b in p.get('contacts',[])[:i]:
            if (c['actor'],c['effector'])==(b['actor'],b['effector']) and max(c['start_frame'],b['start_frame'])<min(c['end_frame'],b['end_frame']):raise ValueError('同一肢端接触区间重叠')
    p['actions']=sorted(actions.values(),key=lambda a:a['start_frame']);p['cameras']=cameras
    hashes={'scene':digest(scene),'animation':digest([scene,p['actors'],p['actions'],p.get('anchors',[]),p.get('contacts',[])]),'camera':digest(cameras)}
    return {'status':'blocked' if findings else 'compiled','plan':p,'findings':findings,'fingerprints':hashes,'approved':False,'reference_eligibility':{'spatial':'unreviewed','camera':'unreviewed','motion':'unreviewed'}}

def changes(old,new):
    keys=[k for k in ('scene','animation','camera') if old['fingerprints'][k]!=new['fingerprints'][k]]
    stages=set(keys)
    if 'scene' in stages:stages.update(('animation','camera'))
    if 'animation' in stages:stages.add('camera')
    if stages:stages.update(('checks','render','review'))
    return {'changed':keys,'invalidate':sorted(stages),'automatic_partial_rebuild':False}

def compile_file(source,output):
    result=compile_plan(read_json(source));write_json(output,result);return {'status':result['status'],'report':str(output),'findings':result['findings']}

def review_page(out,report):
    esc=lambda x:html.escape(str(x))
    diagnostics=''.join('<figure><img src="'+esc(p.name)+'"><figcaption>'+esc(p.stem)+'</figcaption></figure>' for p in sorted(out.glob('diagnostic-*.png')))
    video='<video controls src="preview.mp4"></video>' if (out/'preview.mp4').exists() else ''
    rows=''.join('<li>'+esc(json.dumps(f,ensure_ascii=False))+'</li>' for f in report.get('findings',[]))
    (out/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>场面预演审阅</title><style>body{max-width:1100px;margin:35px auto;font:16px/1.7 system-ui;padding:20px}img,video{max-width:100%}figure{display:inline-block;width:44%;vertical-align:top}pre{white-space:pre-wrap}</style><h1>场面预演 · '+esc(report['status'])+'</h1><p>空间、运镜、动作参考均待人工审阅。程序检查不代表自然表演合格，也不会自动授权上传 H3。</p>'+video+'<h2>问题与未验证范围</h2><ul>'+rows+'</ul><p>'+esc(report.get('scope',''))+'</p>'+diagnostics+'<p><a href="execution-report.json">执行检查</a> · <a href="compiled-plan.json">场面计划</a></p>',encoding='utf-8')

def build(source,output,explicit=None,render=False):
    result=compile_plan(read_json(source));out=Path(output).resolve()
    if out.exists():raise ValueError('输出目录已存在，使用新版本目录')
    out.mkdir(parents=True);write_json(out/'compiled-plan.json',result)
    if result['status']=='blocked':
        report={'status':'blocked','findings':result['findings']};write_json(out/'execution-report.json',report);review_page(out,report);return report
    p=result['plan'];p['scene']=modeling.materialize(p['scene'],Path(source).resolve().parent,out)
    write_json(out/'execution-plan.json',p)
    for f in modeling.KIT.glob('*.py'):shutil.copy2(f,out/f.name)
    binary=previs.blender_path(explicit)
    try:
        previs.invoke(binary,out/'scene_executor.py',['--plan',str(out/'execution-plan.json'),'--out',str(out)]+(['--render'] if render else []),out/'build.log')
        report=read_json(out/'execution-report.json')
        if render and report['status']!='failed':
            request={'mode':'encode','directory':str(out/'frames'),'fps':p['fps'],'frames':p['scene']['frames'],'output':str(out/'preview.mp4'),'report':str(out/'video-check.json')}
            write_json(out/'encode.json',request);previs.invoke(binary,modeling.KIT.parent/'media.py',[str(out/'encode.json')],out/'encode.log')
    except Exception as exc:
        report={'status':'failed','findings':[{'kind':'execution_error','message':str(exc)}]};write_json(out/'execution-report.json',report)
    review_page(out,report);return {**report,'review_page':str(out/'index.html'),'approved':False}


def bind(root,plan_relative,layout_relative):
    """Bind the same executor to existing blocking review, preserving layout approval gates."""
    import uuid, review
    from layout import load_layout,layout_fingerprint
    from core import load_project
    root=Path(root).resolve();state=review.load_state(root);previs.require_layout(root,state,phase='blocking')
    if state['blocking']['required'] is not True:raise ValueError('先记录用户选择生成整场白模')
    result=compile_plan(read_json(safe_path(root,plan_relative)))
    if result['status']=='blocked':raise ValueError('场面计划存在未解决动作：'+str(result['findings']))
    if layout_relative not in {x['path'] for x in load_project(root)['layouts']}:raise ValueError('布局尚未登记')
    source=safe_path(root,layout_relative);base=root/'blocking'/'adapters'/('scene-'+uuid.uuid4().hex[:10]);base.mkdir(parents=True)
    write_json(base/'compiled-plan.json',result);p=result['plan'];p['scene']=modeling.materialize(p['scene'],root,base);write_json(base/'execution-plan.json',p)
    shutil.copy2(source,base/'layout.json')
    for f in modeling.KIT.glob('*.py'):shutil.copy2(f,base/f.name)
    beat={'id':'scene','duration':p['duration'],'action':'执行场面计划中并行及顺序行动','start_state':'计划初始状态','end_state':'计划结束状态'}
    job={'fps':p['fps'],'beats':[beat],'clips':[{'beat':'scene','duration':p['duration'],'original_start':0}],'source_layout':layout_relative,'layout_fingerprint':layout_fingerprint(load_layout(source)),'input_sha256':{f.relative_to(base).as_posix():previs.sha(f) for f in base.rglob('*') if f.is_file()}}
    write_json(base/'job.json',job)
    return previs.bind(root,(base/'scene_blocking_adapter.py').relative_to(root).as_posix(),{'required_beats':['scene'],'reason':'统一场面计划执行；动作自然性与参考用途须独立审阅'},phase='blocking')
