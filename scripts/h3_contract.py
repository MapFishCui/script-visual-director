"""Local routing/validation derived from official H3 guidance, not a hosted IR client."""
import math,re

ROLES={
 'image':{'first_frame','last_frame','appearance','environment','style','composition'},
 'video':{'motion','expression','camera','rhythm','environment','appearance','source_edit','source_continue'},
 'audio':{'voice','delivery','sound_style','copy_audio'},
}


def route(media):
    """Input rows describe intended use, never infer it from filenames or white-model color."""
    if not isinstance(media,list):raise ValueError('media 必须是素材列表')
    counts={k:0 for k in ROLES};totals={'video':0,'audio':0};labels=set();roles=[];warnings=[]
    for row in media:
        if not isinstance(row,dict) or set(row)-{'label','type','roles','duration','previs','approved_roles'}:raise ValueError('素材用途记录含未知字段')
        kind=row.get('type');rr=row.get('roles')
        if kind not in ROLES or not isinstance(rr,list) or not rr or any(r not in ROLES[kind] for r in rr) or len(set(rr))!=len(rr):raise ValueError('须明确素材类型及兼容的用途')
        label=row.get('label','');prefix={'image':'Picture','video':'Video','audio':'Audio'}[kind]
        if not re.fullmatch('<'+prefix+r' [1-9]\d*>',label) or label in labels:raise ValueError('素材标签类型不符或重复')
        labels.add(label);counts[kind]+=1;roles+=rr
        if kind in totals:
            d=row.get('duration')
            if type(d) not in (int,float) or not math.isfinite(d) or not 2<=d<=15:raise ValueError('参考音视频单个时长须2–15秒')
            totals[kind]+=d
        if 'previs' in row and type(row['previs']) is not bool:raise ValueError('previs 必须是布尔值')
        if row.get('previs'):
            approved=row.get('approved_roles',[])
            if not isinstance(approved,list) or any(r not in ROLES[kind] for r in approved):raise ValueError('approved_roles 无效')
            if set(rr)-set(approved):raise ValueError('预演未按本次参考用途审阅：'+label)
            warnings.append(label+' 的用途声明不是硬隔离开关，仍需核对体型、姿态或表演是否意外被参考。')
    if counts['image']>9 or counts['video']>3 or counts['audio']>3 or len(media)>12 or any(t>15 for t in totals.values()):raise ValueError('H3参考输入超过数量或音视频总时长限制')
    if roles.count('first_frame')>1 or roles.count('last_frame')>1:raise ValueError('首帧或尾帧存在多个来源')
    if roles.count('source_edit')+roles.count('source_continue')>1:raise ValueError('原视频编辑/续写来源存在歧义，先明确任务')
    full=any(r not in ('first_frame','last_frame') for r in roles)
    mode='Ref2VA' if full else 'FL2VA' if 'first_frame' in roles and 'last_frame' in roles else 'I2VA' if 'first_frame' in roles else 'L2VA' if 'last_frame' in roles else 'T2VA'
    tasks=[]
    if mode=='Ref2VA':
        if 'source_edit' in roles:tasks.append('video editing')
        if 'source_continue' in roles:tasks.append('video continuation')
        if any(r in ('first_frame','last_frame') for r in roles):tasks.append('keyframe completion')
        if any(r in ('appearance','environment','style','composition','motion','expression','camera','rhythm') for r in roles):tasks.append('reference generation')
        if 'copy_audio' in roles:tasks.append('audio reuse')
        if any(r in ('voice','delivery','sound_style') for r in roles):tasks.append('audio reference')
    return {'mode':mode,'task_types':tasks,'labels':sorted(labels),'warnings':warnings,'compiler_supported':mode=='Ref2VA','target_h3_validated':False}


def reference_errors(sections):
    errors=[];token=r'<(?:Subject|Picture|Video|Audio) [1-9]\d*>'
    # A mention inside another subject's line is not an independent definition.
    definitions=re.findall(r'^\s*('+token+r')\s+[^\n]+',sections['subject_definitions'],re.M)
    if len(definitions)!=len(set(definitions)):errors.append('H3参考标签被重复定义')
    subjects={x for x in definitions if x.startswith('<Subject ')}
    all_subjects=set(re.findall(r'<Subject \d+>','\n'.join(sections.values())))
    if all_subjects-subjects:errors.append('H3存在未独立定义的主体引用：'+', '.join(sorted(all_subjects-subjects)))
    lines=sections['retention_analysis'].splitlines();retained={}
    for line in lines:
        m=re.match(r'\s*('+token+r')(?:\s*\([^\n]*?\))?\s*:\s*([a-z_]+)\s*-\s*\S',line)
        if not m:
            if re.match(r'\s*'+token,line):errors.append('H3保留说明须包含有效关系标记及说明')
            continue
        label,relationship=m.groups()
        if label in retained:errors.append('H3保留说明重复：'+label)
        retained[label]=relationship
        allowed={'fully_copy','partially_copy','reference','weak_reference'} if label.startswith('<Audio ') else {'fully_preserved','partially_preserved','attribute_transfer','weak_reference'}
        if relationship not in allowed:errors.append('H3保留关系与素材类型不符：'+label)
        if label not in definitions:errors.append('H3保留说明的标签未独立定义：'+label)
    missing=set(definitions)-set(retained)
    if missing:errors.append('H3参考缺少保留说明：'+', '.join(sorted(missing)))
    m=re.match(r'^\[([^\]]+)\]',sections['summary'])
    allowed={'reference generation','video editing','video continuation','keyframe completion','audio reuse','audio reference'}
    tasks=[x.strip() for x in m.group(1).split('+')] if m else []
    if not tasks or any(x not in allowed for x in tasks) or len(tasks)!=len(set(tasks)):errors.append('H3 summary 缺少有效任务类型前缀')
    if re.search(r'\(S\d+\)',sections['retention_analysis']):errors.append('H3发声者编号不写入 retention_analysis')
    if any('<d>' in sections[k] for k in ('overall_soundscape','non_diegetic_music')):errors.append('H3完整台词只写入逐镜正文，不放入整体声音章节')
    return errors
