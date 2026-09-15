"""Local, immutable series asset snapshots and explicit per-episode version pins."""
import copy
from contextlib import ExitStack, contextmanager
import hashlib
from pathlib import Path
import re
import uuid

from PIL import Image
from core import (blockers, current, finished, indexed, load_project, read_json,
                  safe_path, write_json)
from schema import MANIFEST, check
import review

INDEX='library.json'
PREFIX='series/inheritance/'


def identifier(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*',value):
        raise ValueError('编号须以英文字母开头，仅含字母、数字、下划线或短横线')
    return value


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


@contextmanager
def locks(*roots):
    with ExitStack() as stack:
        for root in sorted({str(Path(p).resolve()) for p in roots}):
            stack.enter_context(review.locked(root))
        yield


def initialize(root,name):
    root=Path(root).resolve()
    if not isinstance(name,str) or not name.strip(): raise ValueError('需要剧集名称')
    if root.exists() and any(root.iterdir()): raise ValueError('共享库须使用空目录，不能覆盖制作项目')
    root.mkdir(parents=True,exist_ok=True)
    data={'schema_version':1,'id':str(uuid.uuid4()),'name':name,'assets':[]}
    write_json(root/INDEX,data)
    return data


def load(root):
    data=read_json(safe_path(root,INDEX))
    if data.get('schema_version')!=1 or not data.get('id') or not data.get('name'):
        raise ValueError('共享库格式无效')
    indexed(data['assets'])
    return data


def publish(project,library,episode,asset_ids):
    identifier(episode)
    if not asset_ids or len(set(asset_ids))!=len(asset_ids): raise ValueError('选择非空且不重复的入库资产')
    if Path(project).resolve()==Path(library).resolve(): raise ValueError('共享库与单集项目必须分开')
    with locks(project,library):
        m=load_project(project); data=load(library)
        assets,layouts,gates=[indexed(m[k]) for k in ('assets','layouts','gates')]
        by_id=indexed(data['assets']); writes={}; output=[]
        for aid in asset_ids:
            identifier(aid)
            if aid not in assets: raise ValueError('未知资产：'+aid)
            asset=assets[aid];v=current(asset)
            if not finished(v) or blockers(asset,assets,layouts,gates):
                raise ValueError(aid+' 尚未完成检查、必要用户确认或依赖验证，不能入库')
            file=safe_path(project,v['file']);raw=file.read_bytes()
            with Image.open(file) as image: image.verify()
            record=by_id.get(aid)
            if record and record['type']!=asset['type']: raise ValueError('共享编号的资产类型冲突：'+aid)
            snapshot={'source_episode':episode,'source_project_name':m['name'],
                      'asset':copy.deepcopy(asset),'source_version':v['version'],'sha256':sha(raw)}
            proof=review.digest(snapshot)
            existing=next((x for x in record['versions'] if x['fingerprint']==proof),None) if record else None
            if existing:
                stored=safe_path(library,existing['file'])
                if sha(stored.read_bytes())!=existing['sha256']: raise ValueError('共享库文件已改变：'+aid)
                output.append({'id':aid,'version':existing['version'],'reused_snapshot':True});continue
            version=max((x['version'] for x in record['versions']),default=0)+1 if record else 1
            rel=f'assets/{aid}/v{version:03d}{file.suffix.lower()}'
            target=safe_path(library,rel)
            if target.exists(): raise ValueError('入库路径已存在，拒绝覆盖：'+rel)
            entry={'version':version,'file':rel,'sha256':sha(raw),'fingerprint':proof,
                   'source_episode':episode,'source_asset_version':v['version'],'snapshot':snapshot}
            if record is None:
                record={'id':aid,'name':asset['name'],'type':asset['type'],'versions':[]}
                data['assets'].append(record);by_id[aid]=record
            record['versions'].append(entry);writes[rel]=raw
            output.append({'id':aid,'version':version,'reused_snapshot':False})
        # Index is the commit point: no partially published batch is discoverable.
        for rel,raw in writes.items():
            target=safe_path(library,rel);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        write_json(safe_path(library,INDEX),data)
    return {'library':data['name'],'episode':episode,'published':output}


def records(project):
    m=load_project(project); batches=[]
    for doc in m['documents']:
        if doc['path'].startswith(PREFIX) and doc['path'].endswith('.json'):
            batch=read_json(safe_path(project,doc['path']))
            if batch.get('type')!='series_inheritance': raise ValueError('继承记录格式无效')
            batches.append(batch)
    return batches


def inherit(project,library,plan):
    if set(plan)!={'episode','items'} or not isinstance(plan['items'],list) or not plan['items']:
        raise ValueError('继承方案需要 episode 与非空 items')
    identifier(plan['episode'])
    with locks(project,library):
        m=load_project(project);data=load(library);batches=records(project)
        if any(b['library_id']!=data['id'] or b['episode']!=plan['episode'] for b in batches):
            raise ValueError('本集已绑定另一共享库或集号，不能静默更换')
        assets=indexed(m['assets']);shots=indexed(m['shots']);layouts=indexed(m['layouts']);shared=indexed(data['assets'])
        batch_id=uuid.uuid4().hex;rows=[];writes={};seen=set()
        initialized=safe_path(project,review.STATE).exists()
        for item in plan['items']:
            required={'source_id','version','target_id','shots','mode','continuity_note'}
            if not required<=set(item) or set(item)-required-{'layout'}: raise ValueError('继承项字段错误')
            aid=identifier(item['source_id']);tid=identifier(item['target_id'])
            if tid in seen: raise ValueError('本次目标资产编号重复')
            seen.add(tid)
            if type(item['version']) is not int or item['version']<1: raise ValueError('必须锁定确切共享版本，不接受latest')
            if item['mode'] not in ('reuse','reference') or not isinstance(item['continuity_note'],str) or not item['continuity_note'].strip():
                raise ValueError('选择 reuse/reference 并说明本集连续性依据')
            if not isinstance(item['shots'],list) or not item['shots'] or len(set(item['shots']))!=len(item['shots']) or any(s not in shots for s in item['shots']):
                raise ValueError('必须关联本集真实且不重复的镜号')
            record=shared.get(aid)
            entry=next((v for v in record['versions'] if v['version']==item['version']),None) if record else None
            if entry is None: raise ValueError('共享资产版本不存在：'+aid)
            if review.digest(entry['snapshot'])!=entry['fingerprint']: raise ValueError('共享版本记录已改变')
            raw=safe_path(library,entry['file']).read_bytes()
            if sha(raw)!=entry['sha256']: raise ValueError('共享库图片已改变：'+aid)
            with Image.open(safe_path(library,entry['file'])) as image: image.verify()
            old=assets.get(tid)
            if old:
                ov=current(old)
                if ov['file'] or ov['production'] not in ('planned','prompt_ready') or old['shots']!=item['shots']:
                    raise ValueError('只可填充同镜号的待生成资产，不能覆盖已有图片／版本：'+tid)
                if old['type']!=record['type']: raise ValueError('目标资产类型不符')
            if initialized and (old is None or any(tid not in shots[s]['assets'] for s in item['shots'])):
                raise ValueError('已开启审核：先在本集声明待生成资产及镜号引用，再继承；不覆盖审核分镜')
            source_asset=entry['snapshot']['asset'];source_v=next(v for v in source_asset['versions'] if v['version']==entry['source_asset_version'])
            v=copy.deepcopy(source_v);v['version']=current(old)['version'] if old else 1
            v['dependencies']=copy.deepcopy(current(old)['dependencies']) if old else []
            v['gates']=copy.deepcopy(current(old)['gates']) if old else []
            if record['type']=='scene':
                layout=item.get('layout')
                if not isinstance(layout,dict) or set(layout)!={'id','version'} or layout['id'] not in layouts or layouts[layout['id']]['version']!=layout['version']:
                    raise ValueError('场景继承必须绑定本集确切布局版本')
                from layout import load_layout
                geometry=load_layout(safe_path(project,layouts[layout['id']]['path']))
                if geometry['id']!=layout['id'] or geometry['version']!=layout['version']: raise ValueError('本集布局文件与登记版本不符')
                if any(shots[s]['layout']!=layout for s in item['shots']): raise ValueError('场景引用镜头与本集布局不一致')
                v['dependencies']=[d for d in v['dependencies'] if d['kind']!='layout']+[dict(layout,kind='layout')]
            pending=item['mode']=='reference' or record['type']=='scene'
            if pending:
                v['review']={'status':'pending','note':'继承候选，待核对本集造型／物品状态／布局与机位'}
                v['approval']={'status':'pending','evidence':''}
            else:
                v['review']['note']+='；同图跨集复用：'+item['continuity_note']
            suffix=Path(entry['file']).suffix
            rel=f'series/images/{batch_id}/{tid}{suffix}'
            v.update(file=rel,validity='current',production='generated',note='继承共享资产确切版本；'+item['continuity_note'])
            target=copy.deepcopy(old or source_asset)
            target.update(id=tid,shots=item['shots'],current_version=v['version'])
            if old: target['versions']=[v if x['version']==v['version'] else x for x in target['versions']]
            else: target['versions']=[v]
            target['sources'].append({'basis':'explicit','text':f"继承 {data['name']} / {aid}@{item['version']}，来源{entry['source_episode']}；{item['continuity_note']}"})
            if old: m['assets'][m['assets'].index(old)]=target
            else:
                m['assets'].append(target)
                for sid in item['shots']:
                    if tid not in shots[sid]['assets']: shots[sid]['assets'].append(tid)
            rows.append({'asset_id':tid,'asset_version':v['version'],'library_asset':aid,'library_version':item['version'],
                'source_episode':entry['source_episode'],'source_asset_version':entry['source_asset_version'],
                'file':rel,'sha256':entry['sha256'],'mode':item['mode'],'continuity_note':item['continuity_note'],
                'source_snapshot':entry['snapshot'],'pending_episode_review':pending})
            writes[rel]=raw
        batch={'type':'series_inheritance','schema_version':1,'library_id':data['id'],'library_name':data['name'],
               'episode':plan['episode'],'items':rows}
        path=f'{PREFIX}{batch_id}.json';m['documents'].append({'path':path,'role':'handoff'})
        check(m,MANIFEST)
        for rel,raw in writes.items():
            target=safe_path(project,rel);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        write_json(safe_path(project,path),batch)
        # Manifest commits assets and registered provenance together. No external links.
        write_json(Path(project)/'manifest.json',m)
    return {'episode':plan['episode'],'inherited':[r['asset_id'] for r in rows],
            'needs_review':[r['asset_id'] for r in rows if r['pending_episode_review']]}


def verify(project):
    errors=[]
    try:
        assets=indexed(load_project(project)['assets'])
        for batch in records(project):
            for row in batch['items']:
                a=assets.get(row['asset_id']);v=next((v for v in a['versions'] if v['version']==row['asset_version']),None) if a else None
                if not v or v['file']!=row['file']: errors.append('继承资产版本／文件关联已改变：'+row['asset_id']);continue
                if sha(safe_path(project,row['file']).read_bytes())!=row['sha256']: errors.append('继承图片内容已改变：'+row['asset_id'])
    except (ValueError,OSError,KeyError,TypeError) as exc: errors.append('继承记录无法验证：'+str(exc))
    return {'ok':not errors,'errors':errors}


def view(project):
    batches=records(project)
    if not batches: return None
    return {'name':batches[0]['library_name'],'episode':batches[0]['episode'],
            'items':[{k:v for k,v in row.items() if k!='source_snapshot'} for b in batches for row in b['items']],
            'verification':verify(project)}


def catalog(library):
    data=load(library)
    return {'id':data['id'],'name':data['name'],'assets':[{'id':a['id'],'name':a['name'],'type':a['type'],
        'versions':[{k:v[k] for k in ('version','file','sha256','source_episode','source_asset_version')} for v in a['versions']]} for a in data['assets']]}
