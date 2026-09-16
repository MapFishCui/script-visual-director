"""Versioned Blender component scenes; building never grants production approval."""
from pathlib import Path
import shutil
import uuid

from jsonschema import Draft202012Validator
from core import read_json, write_json, safe_path, load_project
import previs

KIT = Path(__file__).resolve().parents[1]/'assets/blender/modeling'
VEC={'type':'array','items':{'type':'number'},'minItems':3,'maxItems':3}
POS={'type':'number','exclusiveMinimum':0}
ID={'type':'string','pattern':'^[A-Za-z][A-Za-z0-9_-]*$'}
EFF={'enum':['hand.L','hand.R','foot.L','foot.R']}

def obj(props,required):return {'type':'object','properties':props,'required':required,'additionalProperties':False}
def arr(item):return {'type':'array','items':item}
KEY=obj({'frame':{'type':'integer','minimum':1},'position':VEC,'angle':{'type':'number'},
         'targets':{'type':'object','propertyNames':{'enum':[x+y for x in ('hand.','foot.') for y in ('L','R','L/pole','R/pole')]},'additionalProperties':VEC}},['frame'])
BASE={'id':ID,'position':VEC,'rotation_z':{'type':'number'},'keys':arr(KEY)}
STRUCT={**BASE,'physics':{'enum':['none','static','dynamic','kinematic']},'mass':POS,'category':{'enum':['structure','prop']}}
variants=[]
for typ,extra,required in [
 ('box',{'size':{'type':'array','items':POS,'minItems':3,'maxItems':3}},['size']),
 ('wall_opening',{'width':POS,'height':POS,'thickness':POS,'opening':obj({'width':POS,'height':POS,'offset':{'type':'number'}},['width','height'])},['width','height','thickness','opening']),
 ('stairs',{'steps':{'type':'integer','minimum':1,'maximum':100},'width':POS,'rise':POS,'tread':POS},['steps','width','rise','tread']),
 ('door',{'width':POS,'height':POS,'thickness':POS,'angle':{'type':'number'}},['width','height','thickness']),
 ('actor',{'height':{'type':'number','minimum':.5,'maximum':3},'pole_angles':{'type':'object','propertyNames':EFF,'additionalProperties':{'type':'number'}}},[]),
 ('anchor',{},[])]:
    variants.append(obj({**(BASE if typ in ('actor','anchor') else STRUCT),'type':{'const':typ},**extra},['id','type','position']+required))
POSEKEY=obj({'frame':{'type':'integer','minimum':1},'rig':{'type':'string','minLength':1},'bone':{'type':'string','minLength':1},'rotation':VEC,'location':VEC,'properties':{'type':'object','propertyNames':{'pattern':'^[A-Za-z0-9_ .-]+$'},'additionalProperties':{'type':'number'}}},['frame','rig','bone'])
variants.append(obj({**BASE,'type':{'const':'asset'},'asset_key':{'type':'string'},'model':{'type':'string'},'collection':{'type':'string'},'category':{'enum':['actor','prop','structure']},'scale':POS,'pose_keys':arr(POSEKEY),'collision_boxes':arr(obj({'position':VEC,'size':{'type':'array','items':POS,'minItems':3,'maxItems':3}},['position','size']))},['id','type','position','asset_key','model','category']))
CONTACT=obj({'actor':ID,'effector':EFF,'target':ID,'start':{'type':'integer','minimum':1},'end':{'type':'integer','minimum':1},'tolerance':POS},['actor','effector','target','start','end'])
ATTACH=obj({'actor':ID,'effector':EFF,'object':ID,'offset':VEC},['actor','effector','object'])
ALLOW=obj({'actor':ID,'part':{'enum':['torso','head','upper_arm.L','upper_arm.R','forearm.L','forearm.R','thigh.L','thigh.R','shin.L','shin.R']},'object':ID,'start':{'type':'integer','minimum':1},'end':{'type':'integer','minimum':1},'max_penetration':{'type':'number','minimum':0,'maximum':.05}},['actor','part','object','start','end','max_penetration'])
SPEC=obj({'schema_version':{'const':1},'fps':{'type':'integer','minimum':1,'maximum':60},'frames':{'type':'integer','minimum':1,'maximum':10000},
 'substeps':{'type':'integer','minimum':1,'maximum':16},'collision_tolerance':{'type':'number','minimum':0,'maximum':.05},'ik_tolerance':POS,
 'components':{'type':'array','items':{'oneOf':variants},'minItems':1,'maxItems':500},'contacts':arr(CONTACT),'attachments':arr(ATTACH),'allowed_contacts':arr(ALLOW),
 'preview':obj({'position':VEC,'target':VEC,'width':{'type':'integer','minimum':64,'maximum':2048},'height':{'type':'integer','minimum':64,'maximum':2048},'frame':{'type':'integer','minimum':1}},[]),
 'beats':arr(obj({'id':ID,'duration':POS,'action':{'type':'string','minLength':1},'start_state':{'type':'string','minLength':1},'end_state':{'type':'string','minLength':1}},['id','duration','action','start_state','end_state']))},['schema_version','components'])


def validate(spec):
    errors=list(Draft202012Validator(SPEC).iter_errors(spec))
    if errors:raise ValueError('; '.join('/'.join(map(str,e.path))+': '+e.message for e in errors[:4]))
    rows=spec['components'];table={c['id']:c for c in rows};frames=spec.get('frames',1)
    if len(table)!=len(rows):raise ValueError('组件编号重复')
    actors={c['id'] for c in rows if c['type']=='actor'}
    for c in rows:
        if c['type']=='wall_opening':
            o=c['opening']
            if o['height']>c['height'] or o['width']+2*abs(o.get('offset',0))>c['width']:raise ValueError('洞口超出墙体')
        if any(k['frame']>frames for k in c.get('pose_keys',[])):raise ValueError('骨骼关键帧超出场景范围')
        keys=c.get('keys',[])
        if any(k['frame']>frames for k in keys) or len({k['frame'] for k in keys})!=len(keys):raise ValueError('关键帧重复或超出场景范围')
        if c['type']!='actor' and any('targets' in k for k in keys):raise ValueError('只有人物有 IK 控制目标')
        if c['type']=='anchor' and keys:raise ValueError('当前 anchor 为静态接触点，不接受未实现的动画')
        if c.get('physics') in ('static','dynamic') and keys:raise ValueError('动画驱动物体请用 kinematic；不要混用物理与导演驱动')
        if c.get('physics')=='dynamic' and c['type']!='box':raise ValueError('首版动态刚体仅支持独立 box 物件')
    attached={}
    for a in spec.get('attachments',[]):
        if a['actor'] not in actors or a['object'] not in table or table[a['object']]['type']!='box':raise ValueError('持物绑定需要有效人物与 box 道具')
        if a['object'] in attached:raise ValueError('道具不能被重复绑定')
        if table[a['object']].get('physics','none')!='none' or table[a['object']].get('keys'):raise ValueError('持物由手部驱动，不能同时启用刚体或物体关键帧')
        attached[a['object']]=a
    for c in spec.get('contacts',[]):
        if c['actor'] not in actors or c['target'] not in table:raise ValueError('接触引用不存在')
        if c['target'] in attached or table[c['target']]['type']!='anchor':raise ValueError('接触目标须为独立 anchor，避免持物与 IK 循环依赖')
    contacts=spec.get('contacts',[])
    for i,c in enumerate(contacts):
        for other in contacts[:i]:
            if (c['actor'],c['effector'])==(other['actor'],other['effector']) and max(c['start'],other['start'])<=min(c['end'],other['end']):
                raise ValueError('同一肢端的接触时间不能重叠')
    for c in spec.get('contacts',[])+spec.get('allowed_contacts',[]):
        if c['start']>c['end'] or c['end']>frames:raise ValueError('接触时间范围无效')
    for c in spec.get('allowed_contacts',[]):
        if c['actor'] not in actors or c['object'] not in table:raise ValueError('接触例外引用不存在')
    if spec.get('preview',{}).get('frame',1)>frames:raise ValueError('预览帧超出场景范围')
    if len({b['id'] for b in spec.get('beats',[])})!=len(spec.get('beats',[])):raise ValueError('动作段编号重复')
    if any(abs(b['duration']*spec.get('fps',12)-round(b['duration']*spec.get('fps',12)))>1e-6 for b in spec.get('beats',[])):raise ValueError('动作段必须落在整数帧')
    if 'beats' in spec and abs(sum(b['duration'] for b in spec['beats'])*spec.get('fps',12)-frames)>1e-6:raise ValueError('整场动作段时长与帧数不一致')
    return spec


def materialize(spec,project,out):
    import copy,model_library
    spec=copy.deepcopy(spec);project=Path(project).resolve();out=Path(out).resolve()
    rows=[c for c in spec['components'] if c['type']=='asset']
    if not rows:return spec
    model_library.check_project(project);lock=read_json(project/'model-assets.lock.json')
    for c in rows:
        entry=next((e for e in lock['assets'] if e['key']==c['asset_key']),None)
        if not entry or c['model'] not in entry['files']:raise ValueError('模型必须先 library-pin 到当前项目')
        source=model_library.relative(project,entry['directory']);dest=out/entry['directory']
        if not dest.exists():dest.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(source,dest)
        c['file']=(Path(entry['directory'])/'files'/c['model']).as_posix()
    shutil.copy2(project/'model-assets.lock.json',out/'model-assets.lock.json')
    credits=project/'MODEL-ASSET-CREDITS.txt'
    if credits.exists():shutil.copy2(credits,out/credits.name)
    return spec


def build_scene(spec_path,output,explicit=None):
    spec=validate(read_json(spec_path));out=Path(output).resolve()
    if out.exists():raise ValueError('输出目录已存在，请使用新目录保留旧版')
    out.mkdir(parents=True);spec=materialize(spec,Path(spec_path).resolve().parent,out);write_json(out/'scene-spec.json',spec)
    for file in KIT.glob('*.py'):shutil.copy2(file,out/file.name)
    binary=previs.blender_path(explicit)
    previs.invoke(binary,out/'build_scene.py',['--spec',str(out/'scene-spec.json'),'--out',str(out)],out/'build.log')
    report=read_json(out/'model-check.json')
    return {'status':report['status'],'scene':str(out/'scene.blend'),'preview':str(out/'preview.png'),'report':str(out/'model-check.json'),'approved':False}


def bind_blocking(root,spec_relative,layout_relative):
    """Copy a versioned kit and spec into a project-owned Blender adapter, then bind normally."""
    import review
    state=review.load_state(root);previs.require_layout(root,state,phase='blocking')
    if state['blocking']['required'] is not True:raise ValueError('先记录用户生成整场白模的选择')
    spec=validate(read_json(safe_path(root,spec_relative)))
    if not spec.get('beats'):raise ValueError('用于整场预演的组件场景需要 beats')
    source=safe_path(root,layout_relative)
    if layout_relative not in {l['path'] for l in load_project(root)['layouts']}:raise ValueError('布局尚未登记')
    base=safe_path(root,'blocking/adapters/components-'+uuid.uuid4().hex[:10]);base.mkdir(parents=True)
    spec=materialize(spec,root,base)
    write_json(base/'scene-spec.json',spec);shutil.copy2(source,base/'layout.json')
    for file in KIT.glob('*.py'):shutil.copy2(file,base/file.name)
    from layout import load_layout,layout_fingerprint
    clips=[];elapsed=0
    for beat in spec['beats']:
        clips.append({'beat':beat['id'],'duration':beat['duration'],'original_start':elapsed});elapsed+=beat['duration']
    job={'fps':spec.get('fps',12),'beats':spec['beats'],'clips':clips,'source_layout':layout_relative,
         'layout_fingerprint':layout_fingerprint(load_layout(source)), 'input_sha256':{p.relative_to(base).as_posix():previs.sha(p) for p in base.rglob('*') if p.is_file()}}
    write_json(base/'job.json',job)
    return previs.bind(root,(base/'blocking_adapter.py').relative_to(Path(root).resolve()).as_posix(),
                       {'required_beats':[b['id'] for b in spec['beats']],'reason':'组件场景中登记的完整调度'},phase='blocking')
