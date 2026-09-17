"""Independent keyframe-grid workflow. Does not migrate legacy review projects."""
import copy
from datetime import datetime, timezone
import argparse
import hashlib
import html
import json
from pathlib import Path
from core import write_json, safe_path

STAGES = ('director', 'characters', 'grids', 'prompts')

def fingerprint(root, files):
    return {name: hashlib.sha256(safe_path(root, name).read_bytes()).hexdigest() for name in files}

def status(root, state):
    ready = True
    result = {}
    for stage in STAGES:
        row = state['stages'].get(stage)
        current = False
        if row:
            try: current = row['hashes'] == fingerprint(root, row['files'])
            except (OSError, ValueError): pass
        approved = bool(ready and current and not row.get('needs_revision') and row.get('approval')) if row else False
        result[stage] = 'confirmed' if approved else 'stale' if row and not current else 'waiting_upstream' if not ready else 'needs_revision' if row and row.get('needs_revision') else 'awaiting_confirmation' if row else 'pending'
        ready = approved
    return result

def page(root, state):
    labels = dict(zip(STAGES, ['中文导演稿', '人物四视图与合图', '逐段九宫格关键画面', '系统提示词与中文对照']))
    states = {'confirmed':'已确认','stale':'文件已变，需重新登记','waiting_upstream':'等待上游确认','awaiting_confirmation':'待确认','pending':'待制作','needs_revision':'待修改'}
    rows = []
    for stage, value in status(root, state).items():
        links=[]
        for name in state['stages'].get(stage, {}).get('files', []):
            from urllib.parse import quote
            url=quote(name, safe='/')
            link='<a href="'+url+'">'+html.escape(name)+'</a>'
            if Path(name).suffix.lower() in ('.png','.jpg','.jpeg','.webp'):
                link+='<br><img loading="lazy" src="'+url+'">'
            links.append(link)
        rows.append('<section><h2>'+labels[stage]+' · '+states[value]+'</h2>'+ '<br>'.join(links)+'</section>')
    (root/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>关键画面制作进度</title><style>body{max-width:1000px;margin:32px auto;font:16px/1.7 sans-serif;padding:20px}section{border-top:1px solid #ddd;padding:20px 0}img{max-width:100%;max-height:650px}a{overflow-wrap:anywhere}</style><h1>'+html.escape(state['name'])+'</h1><p>九宫格为完整剧情关键画面；人物图为身份参考。平面图与白模按需辅助。确认请回当前对话；页面不会调用模型。</p>'+''.join(rows), encoding='utf-8')

def _run(root, command, stage=None, files=None, evidence=None):
    root=Path(root).resolve(); path=root/'grid-workflow.json'
    if command=='init':
        if root.exists() and any(root.iterdir()): raise ValueError('Use a new empty project directory; legacy projects are not migrated')
        root.mkdir(parents=True, exist_ok=True)
        state={'workflow':'keyframe-grid-v1','name':root.name,'stages':{}}
    else:
        state=json.loads(path.read_text())
        if state.get('workflow')!='keyframe-grid-v1': raise ValueError('Wrong workflow')
        previous = copy.deepcopy(state['stages'])
        if command in ('register','confirm'):
            index=STAGES.index(stage)
            if any(status(root,state)[s]!='confirmed' for s in STAGES[:index]): raise ValueError('Confirm current upstream versions first')
            if command=='register':
                if not files or len(set(files))!=len(files): raise ValueError('Provide unique real files')
                if any(Path(f).is_absolute() or f in ('index.html','grid-workflow.json') for f in files): raise ValueError('Use project-relative artifact paths')
                reserved = {path.resolve(), (root/'index.html').resolve()}
                if any(safe_path(root,f) in reserved for f in files):
                    raise ValueError('Workflow state and page cannot be stage artifacts')
                hashes=fingerprint(root,files)
                state['stages'][stage]={'files':files,'hashes':hashes,'approval':None}
            else:
                if not evidence or not evidence.strip(): raise ValueError('Actual user confirmation evidence required')
                row=state['stages'].get(stage)
                if not row or row['hashes']!=fingerprint(root,row['files']): raise ValueError('Register current artifacts before confirming')
                if row.get('needs_revision'): raise ValueError('请先处理修改意见并重新登记，不能确认待修改版本')
                if row.get('approval'):
                    page(root, state)
                    return {'workflow':state['workflow'],'stages':status(root,state),'page':str(root/'index.html'),'target_h3_validated':False}
                row['approval']=evidence.strip()
            for downstream in STAGES[index+1:]:
                if downstream in state['stages']: state['stages'][downstream]['approval']=None
        elif command!='status': raise ValueError('Unknown command')
        if command != 'status':
            state.setdefault('history', []).append({'at':datetime.now(timezone.utc).isoformat(), 'command':command, 'stage':stage, 'previous_stages':previous})
    if command!='status': write_json(path,state)
    page(root,state)
    return {'workflow':state['workflow'],'stages':status(root,state),'page':str(root/'index.html'),'target_h3_validated':False}

def run(root, command, stage=None, files=None, evidence=None):
    if command == 'init':
        return _run(root, command, stage, files, evidence)
    from review import locked
    if not (Path(root)/'grid-workflow.json').is_file():
        raise ValueError('Project not initialized')
    with locked(root):
        return _run(root, command, stage, files, evidence)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['init','register','confirm','status','serve']);p.add_argument('project')
    p.add_argument('--stage',choices=STAGES);p.add_argument('--files',nargs='+');p.add_argument('--evidence');p.add_argument('--port',type=int,default=0)
    a=p.parse_args()
    if a.command in ('register','confirm') and not a.stage:p.error('--stage required')
    if a.command=='serve':
        from grid_server import serve
        serve(a.project,a.port)
        raise SystemExit(0)
    print(json.dumps(run(a.project,a.command,a.stage,a.files,a.evidence),ensure_ascii=False,indent=2))
