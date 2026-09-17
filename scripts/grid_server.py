"""Token-protected loopback review for keyframe-grid projects."""
import hashlib,json,mimetypes,secrets
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs
from core import safe_path,write_json
from review import locked
import grid_workflow as grid
WEB=Path(__file__).resolve().parents[1]/'assets/grid-review'

def view(root):
    state=json.loads((root/'grid-workflow.json').read_text(encoding='utf-8'))
    rows={}
    for stage,row in state['stages'].items():
        rows[stage]={**row,'artifacts':[]}
        if 'items' in row:
            from grid_items import condition
            rows[stage]['item_status']={key:condition(root,state,stage+'/'+key) for key in row['items']}
        for name in row['files']:
            try:
                p=safe_path(root,name); entry={'path':name,'exists':p.is_file()}
                if p.suffix.lower() in ('.txt','.md','.json') and p.stat().st_size<=500000:entry['text']=p.read_text(encoding='utf-8')
                rows[stage]['artifacts'].append(entry)
            except (OSError,ValueError,UnicodeError):rows[stage]['artifacts'].append({'path':name,'exists':False})
    result={'name':state['name'],'stages':rows,'status':grid.status(root,state)}
    hashes={}
    for key,row in state['stages'].items():
        try:hashes[key]=grid.fingerprint(root,row['files'])
        except (ValueError,OSError):hashes[key]=None
    result['revision']=hashlib.sha256(json.dumps([state,hashes],sort_keys=True).encode()).hexdigest()
    return result

def make_server(root,port=0,token=None):
    root=Path(root).resolve(); token=token or secrets.token_urlsafe(32)
    if json.loads((root/'grid-workflow.json').read_text(encoding='utf-8')).get('workflow')!='keyframe-grid-v1':raise ValueError('Wrong workflow')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def send(self,data,mime='application/json',status=200):
            if not isinstance(data,bytes):data=json.dumps(data,ensure_ascii=False).encode()
            self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers();self.wfile.write(data)
        def auth(self,query=False):
            host='127.0.0.1:'+str(self.server.server_port)
            if self.headers.get('Host')!=host or self.headers.get('Origin', 'http://'+host)!='http://'+host:raise PermissionError('Invalid origin')
            supplied=self.headers.get('X-Review-Token','')
            if query:supplied=parse_qs(urlsplit(self.path).query).get('token',[supplied])[0]
            if not secrets.compare_digest(supplied,token):raise PermissionError('请使用启动时的完整审核链接')
        def do_GET(self):
            try:
                path=urlsplit(self.path).path
                if path in ('/','/app.js','/style.css'):
                    name={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}[path]
                    self.send((WEB/name).read_bytes(),{'index.html':'text/html; charset=utf-8','app.js':'text/javascript; charset=utf-8','style.css':'text/css; charset=utf-8'}[name]);return
                self.auth(query=path=='/api/file')
                with locked(root):
                    if path=='/api/state':self.send(view(root));return
                    if path=='/api/validate':
                        from grid_delivery import inspect
                        report=inspect(root);report.pop('compiled',None)
                        self.send(report);return
                    if path=='/api/file':
                        name=parse_qs(urlsplit(self.path).query).get('path',[''])[0]
                        state=json.loads((root/'grid-workflow.json').read_text(encoding='utf-8'))
                        if name not in {f for row in state['stages'].values() for f in row['files']}:raise ValueError('File not registered')
                        p=safe_path(root,name);mime=mimetypes.guess_type(name)[0] or 'application/octet-stream'
                        if p.suffix.lower() not in ('.png','.jpg','.jpeg','.webp'):mime='text/plain; charset=utf-8' if p.suffix.lower() in ('.md','.txt','.json') else 'application/octet-stream'
                        self.send(p.read_bytes(),mime);return
                self.send({'error':'Not found'},status=404)
            except PermissionError as e:self.send({'error':str(e)},status=403)
            except (OSError,ValueError,KeyError) as e:self.send({'error':str(e)},status=409)
        def do_POST(self):
            try:
                self.auth()
                if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('JSON required')
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=1024*1024:raise ValueError('Invalid payload size')
                data=json.loads(self.rfile.read(size));path=urlsplit(self.path).path
                fields={'/api/confirm':{'revision','stage'},'/api/edit':{'revision','stage','file','text'},'/api/feedback':{'revision','stage','text'},'/api/confirm-item':{'revision','stage','item'},'/api/feedback-item':{'revision','stage','item','text'}}
                if not isinstance(data,dict) or path not in fields or set(data)!=fields[path]:raise ValueError('Unexpected request fields')
                with locked(root):
                    if data.get('revision')!=view(root)['revision']:raise ValueError('页面已有更新，请保留编辑并刷新后合并')
                    if not isinstance(data,dict):raise ValueError('Object required')
                    stage=data['stage']
                    if stage not in grid.STAGES:raise ValueError('Invalid stage')
                    if path in ('/api/confirm-item','/api/feedback-item'):
                        from grid_items import change
                        command='confirm-item' if path=='/api/confirm-item' else 'feedback-item'
                        change(root,command,stage,data['item'],evidence=('用户在审核网页确认当前项：'+data['item']) if command=='confirm-item' else data['text'],_locked=True)
                    elif path=='/api/confirm':grid._run(root,'confirm',stage,evidence='用户在审核网页确认当前版本：'+stage)
                    elif path=='/api/edit':
                        if stage!='director':raise ValueError('仅中文导演稿可直接编辑；其他阶段请提交修改意见')
                        state=json.loads((root/'grid-workflow.json').read_text(encoding='utf-8'));name=data['file']
                        if name not in state['stages']['director']['files'] or Path(name).suffix.lower() not in ('.md','.txt'):raise ValueError('Not an editable director file')
                        if not isinstance(data['text'],str) or not data['text'].strip():raise ValueError('导演稿不能为空')
                        p=safe_path(root,name)
                        state.setdefault('history',[]).append({'command':'web_edit','file':name,'previous_text':p.read_text(encoding='utf-8')})
                        write_json(root/'grid-workflow.json',state)
                        p.write_text(data['text'],encoding='utf-8')
                        grid._run(root,'register','director',state['stages']['director']['files'])
                    elif path=='/api/feedback':
                        if not isinstance(data.get('text'),str) or not data['text'].strip():raise ValueError('修改意见不能为空')
                        state=json.loads((root/'grid-workflow.json').read_text(encoding='utf-8'));row=state['stages'][stage]
                        if 'items' in row:raise ValueError('逐项模式请对具体人物或任务提交修改意见')
                        state.setdefault('history',[]).append({'command':'feedback','stage':stage,'text':data['text'],'previous_approval':row.get('approval')})
                        row['feedback']=data['text'];row['needs_revision']=True
                        for key in grid.STAGES[grid.STAGES.index(stage):]:
                            if key in state['stages']:state['stages'][key]['approval']=None
                        write_json(root/'grid-workflow.json',state);grid.page(root,state)
                    else:raise ValueError('Unknown action')
                    self.send(view(root))
            except PermissionError as e:self.send({'error':str(e)},status=403)
            except (OSError,ValueError,KeyError,TypeError) as e:self.send({'error':str(e)},status=409)
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler);server.daemon_threads=True;server.review_token=token;return server

def serve(root,port=0):
    server=make_server(root,port)
    print(json.dumps({'url':f'http://127.0.0.1:{server.server_port}/#token={server.review_token}'},ensure_ascii=False),flush=True)
    try:server.serve_forever()
    finally:server.server_close()
