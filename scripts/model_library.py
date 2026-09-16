"""Immutable local 3D asset cache, with explicit provenance and portable project locks."""
import hashlib,json,os,re,shutil,tempfile,urllib.request,urllib.parse,zipfile,stat
from pathlib import Path,PurePosixPath
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1]
CATALOG=ROOT/'assets/model-library/catalog.json'
FORMATS={'.blend','.glb','.gltf','.obj','.fbx'}

def digest(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for data in iter(lambda:f.read(1024*1024),b''):h.update(data)
    return h.hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def write(p,value):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_name(p.name+'.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(tmp,p)
def cache_root(value=None):return Path(value or os.environ.get('SVD_MODEL_CACHE') or ROOT/'.model-cache').resolve()
def ident(s):
    if not isinstance(s,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,95}',s) or '..' in s:raise ValueError('Invalid asset id/version')
    return s

def relative(root,path):
    if not isinstance(path,str) or '\\' in path or PurePosixPath(path).is_absolute() or '..' in PurePosixPath(path).parts or ':' in path:raise ValueError('Unsafe asset path')
    p=(Path(root)/path).resolve()
    if not p.is_relative_to(Path(root).resolve()):raise ValueError('Asset path escapes root')
    return p

def definition(d):
    required=('id','version','title','author','source_url','download_url','license','license_url','attribution')
    if any(not isinstance(d.get(k),str) or not d[k].strip() for k in required):raise ValueError('Asset requires provenance, version, license and attribution')
    ident(d['id']);ident(d['version'])
    if d['license'] not in ('CC0-1.0','CC-BY-4.0'):raise ValueError('Automatic acquisition supports verified CC0 / CC-BY 4.0 only; other licenses need a reviewed adapter')
    for k in ('source_url','download_url','license_url'):
        if not d[k].startswith('https://'):raise ValueError('Asset URLs must use HTTPS')
    return d

def definitions():return read(CATALOG)['assets']
def resolve(asset,descriptor=None):
    if descriptor:
        d=definition(read(descriptor))
        if d['id']!=asset:raise ValueError('Descriptor id mismatch')
        return d
    candidates=[x for x in definitions() if x['id']==asset]
    if len(candidates)!=1:raise ValueError('Asset not found in catalog; provide --descriptor with verified source metadata')
    return definition(candidates[0])

def verify(folder):
    folder=Path(folder);m=read(folder/'asset.json')
    if not m.get('files'):raise ValueError('Asset cache contains no files')
    for name,h in m['files'].items():
        p=relative(folder/'files',name)
        if not p.is_file() or digest(p)!=h:raise ValueError('Asset missing or changed: '+name)
    return m

def unpack(archive,dest):
    with zipfile.ZipFile(archive) as z:
        if len(z.infolist())>10000 or sum(i.file_size for i in z.infolist())>4*1024**3:raise ValueError('Archive exceeds extraction limits')
        names=set()
        for info in z.infolist():
            target=relative(dest,info.filename)
            if stat.S_ISLNK(info.external_attr>>16):raise ValueError('Asset archive symlinks are not accepted')
            if info.is_dir():continue
            if info.filename in names:raise ValueError('Duplicate archive entry')
            names.add(info.filename);target.parent.mkdir(parents=True,exist_ok=True)
            with z.open(info) as source,target.open('wb') as output:shutil.copyfileobj(source,output)

def fetch(asset,cache=None,descriptor=None):
    d=resolve(asset,descriptor);base=cache_root(cache);dest=base/d['id']/d['version']
    if dest.exists():
        m=verify(dest)
        if m['definition']!=d:raise ValueError('Version already exists with different metadata; assign a new version')
        return {'reused':True,'directory':str(dest),'status':m['status']}
    dest.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.download-',dir=dest.parent) as tmp:
        stage=Path(tmp);archive=stage/'download';h=hashlib.sha256();total=0
        request=urllib.request.Request(d['download_url'],headers={'User-Agent':'script-visual-director/1.0'})
        with urllib.request.urlopen(request,timeout=60) as source,archive.open('wb') as target:
            if not source.url.startswith('https://'):raise ValueError('Download redirected away from HTTPS')
            resolved=source.url
            for chunk in iter(lambda:source.read(1024*1024),b''):
                total+=len(chunk)
                if total>1024**3:raise ValueError('Download exceeds 1 GiB limit')
                h.update(chunk);target.write(chunk)
        actual=h.hexdigest()
        if d.get('sha256') and d['sha256']!=actual:raise ValueError('Download checksum mismatch')
        files=stage/'files';files.mkdir()
        if zipfile.is_zipfile(archive):unpack(archive,files)
        else:
            suffix=Path(urllib.parse.urlparse(d['download_url']).path).suffix.lower()
            if suffix not in FORMATS:raise ValueError('Expected model or ZIP archive, not an HTML/login page')
            shutil.copy2(archive,files/('model'+suffix))
        manifest={p.relative_to(files).as_posix():digest(p) for p in sorted(files.rglob('*')) if p.is_file()}
        models=[n for n in manifest if Path(n).suffix.lower() in FORMATS]
        if not models:raise ValueError('Download has no recognized model files')
        archive.unlink()
        write(stage/'asset.json',{'schema_version':1,'definition':d,'download_sha256':actual,'resolved_url':resolved,'downloaded_at':datetime.now(timezone.utc).isoformat(),'files':manifest,'models':models,'status':'downloaded_unverified'})
        if dest.exists():raise ValueError('Another download created this version; rerun to verify it')
        os.rename(stage,dest)
    return {'reused':False,'directory':str(dest),'status':'downloaded_unverified','models':models}

def inventory(cache=None):
    root=cache_root(cache);rows=[]
    for p in sorted(root.glob('*/*/asset.json')):
        try:
            m=verify(p.parent);rows.append({'id':m['definition']['id'],'version':m['definition']['version'],'status':m['status'],'models':m['models']})
        except (ValueError,OSError) as exc:rows.append({'path':str(p),'status':'invalid','error':str(exc)})
    return {'cache':str(root),'assets':rows,'catalog':[{'id':d['id'],'version':d['version'],'title':d['title']} for d in definitions()]}

def pin(project,asset,version,cache=None):
    project=Path(project).resolve();ident(asset);ident(version);source=cache_root(cache)/asset/version;m=verify(source)
    lockpath=project/'model-assets.lock.json';lock=read(lockpath) if lockpath.exists() else {'schema_version':1,'assets':[]}
    key=asset+'@'+version;existing=next((x for x in lock['assets'] if x['key']==key),None)
    dest=project/'model-assets'/asset/version
    if existing:
        current=verify(dest)
        if current['files']!=existing['files'] or current['definition']!=existing['definition']:raise ValueError('Pinned asset changed')
        return existing
    if dest.exists():raise ValueError('Unregistered asset directory exists')
    dest.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(source,dest)
    entry={'key':key,'directory':dest.relative_to(project).as_posix(),'definition':m['definition'],'files':m['files'],'download_sha256':m['download_sha256'],'status':'downloaded_unverified'}
    lock['assets'].append(entry);write(lockpath,lock)
    credits='\n\n'.join(x['definition']['attribution']+'\nSource: '+x['definition']['source_url']+'\nLicense: '+x['definition']['license_url'] for x in lock['assets'])
    (project/'MODEL-ASSET-CREDITS.txt').write_text(credits+'\n',encoding='utf-8')
    return entry

def check_project(project):
    project=Path(project).resolve();lock=read(project/'model-assets.lock.json')
    for entry in lock['assets']:
        m=verify(relative(project,entry['directory']))
        if m['files']!=entry['files'] or m['definition']!=entry['definition']:raise ValueError('Pinned asset differs from lock: '+entry['key'])
    return {'valid':True,'assets':len(lock['assets']),'approved':False}

def restore(project,cache=None):
    project=Path(project).resolve();lock=read(project/'model-assets.lock.json')
    for e in lock['assets']:
        d=e['definition'];dest=relative(project,e['directory'])
        if dest.exists():
            m=verify(dest)
            if m['files']!=e['files']:raise ValueError('Existing locked asset modified')
            continue
        with tempfile.TemporaryDirectory() as tmp:
            descriptor=Path(tmp)/'source.json';write(descriptor,d);fetch(d['id'],cache,descriptor)
        source=cache_root(cache)/d['id']/d['version'];m=verify(source)
        if m['files']!=e['files'] or m['download_sha256']!=e['download_sha256']:raise ValueError('Remote version changed; refusing to replace locked asset')
        dest.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(source,dest)
    return check_project(project)

def inspect_model(project,key,model,output,collection=None,explicit=None,pose_file=None):
    import previs,subprocess
    project=Path(project).resolve();check_project(project)
    lock=read(project/'model-assets.lock.json');entry=next((x for x in lock['assets'] if x['key']==key),None)
    if not entry or model not in entry['files']:raise ValueError('Model must be a file from a project lock')
    out=Path(output).resolve()
    if out.exists():raise ValueError('Use a new inspection output directory')
    out.mkdir(parents=True);source=relative(project,entry['directory'])/'files'/model
    request={'file':str(source),'output':str(out),'collection':collection,'pose':read(pose_file) if pose_file else {}}
    write(out/'request.json',request)
    binary=previs.blender_path(explicit)
    with (out/'blender.log').open('w') as log:
        p=subprocess.run([binary,'--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(ROOT/'assets/model-library/inspect_asset.py'),'--','--request',str(out/'request.json')],stdout=log,stderr=subprocess.STDOUT)
    if p.returncode:raise ValueError('Blender inspection failed; see '+str(out/'blender.log'))
    return read(out/'inspection.json')

def bundle(project,output):
    project=Path(project).resolve();check_project(project);out=Path(output).resolve()
    if out.exists():raise ValueError('Bundle output already exists')
    out.parent.mkdir(parents=True,exist_ok=True);lock=read(project/'model-assets.lock.json')
    with zipfile.ZipFile(out,'x',compression=zipfile.ZIP_DEFLATED) as z:
        z.write(project/'model-assets.lock.json','model-assets.lock.json')
        credits=project/'MODEL-ASSET-CREDITS.txt'
        if credits.exists():z.write(credits,credits.name)
        for entry in lock['assets']:
            folder=relative(project,entry['directory'])
            z.write(folder/'asset.json',entry['directory']+'/asset.json')
            for name in entry['files']:z.write(relative(folder/'files',name),entry['directory']+'/files/'+name)
    return {'bundle':str(out),'assets':len(lock['assets']),'note':'Unpack into a new project directory; run library-check. Does not grant asset approval.'}
