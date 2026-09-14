"""Local Blender orchestration; project-owned scripts supply the actual choreography."""
from __future__ import annotations
import datetime
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import uuid

from core import load_project, read_json, safe_path, write_json

JOB = 'previs/local-job.json'
CHOICE = 'previs/choice.json'
CHECK = 'previs/local-review.json'
MEDIA = Path(__file__).resolve().parents[1] / 'assets' / 'blender' / 'media.py'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def blender_path(explicit=None):
    candidates = [explicit] if explicit else [shutil.which('blender'),
        '/Applications/Blender.app/Contents/MacOS/Blender',
        str(Path.home() / 'Applications/Blender.app/Contents/MacOS/Blender')]
    if not explicit and os.name == 'nt':
        candidates += [str(p) for p in sorted(Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')).glob('Blender Foundation/Blender*/blender.exe'), reverse=True)]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    raise ValueError('未找到 Blender；安装完成后重试，或用 --blender 指定可执行文件路径。')


def doctor(explicit=None):
    try:
        binary = blender_path(explicit)
    except ValueError as exc:
        return {'available': False, 'message': str(exc), 'installed_by_skill': False}
    try:
        p = subprocess.run([binary, '--version'], capture_output=True, text=True, timeout=20)
    except subprocess.TimeoutExpired as exc:
        raise ValueError('Blender 版本检测超时') from exc
    if p.returncode:
        raise ValueError('Blender 无法启动：' + p.stderr[-1000:])
    return {'available': True, 'executable': binary, 'version': p.stdout.splitlines()[0],
            'external_ffmpeg': shutil.which('ffmpeg'), 'encoding': 'Blender 内置视频编码；实际兼容性以 smoke/render 为准'}


def documents(root, paths):
    m = load_project(root)
    for path in paths:
        rel = Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
        if not any(d['path'] == rel for d in m['documents']):
            m['documents'].append({'path': rel, 'role': 'handoff'})
    write_json(Path(root) / 'manifest.json', m)


def require_layout(root, state):
    import review
    review.require_phase(root, 'blockout')
    if not review.stage_ready(root, state, 'layout'):
        raise ValueError('请先确认当前布局')


def choose(root, choice, revision, evidence):
    import review
    if choice not in ('generate', 'skip') or not evidence.strip():
        raise ValueError('需要 generate/skip 和真实用户选择依据')
    with review.locked(root):
        s = review.load_state(root); review.expected(s, revision); require_layout(root, s)
        m = load_project(root)
        previous = read_json(safe_path(root, CHOICE)) if safe_path(root, CHOICE).exists() else {}
        recommended = previous.get('recommended_blockouts', {})
        for lay in m['layouts']:
            key = lay['id'] + '@' + str(lay['version'])
            recommended.setdefault(key, lay['blockout_required'])
            lay['blockout_required'] = recommended[key] if choice == 'generate' else False
        # Preserve pending review records and old files; skipping is never recorded as a pass.
        write_json(Path(root) / 'manifest.json', m)
        s['previs'] = {'required': choice == 'generate', 'reason': evidence, 'files': []}
        s['stages']['previs'] = None
        decision = {'choice': choice, 'evidence': evidence, 'recommended_blockouts': recommended,
                    'layout_proof': review.proof(root, s, 'layout'), 'at': review.now()}
        write_json(safe_path(root, CHOICE), decision)
        documents(root, [safe_path(root, CHOICE)])
        if choice == 'skip':
            s['stages']['previs'] = {'fingerprint': review.proof(root, s, 'previs'), 'evidence': evidence, 'at': review.now()}
        review.record(s, 'previs_choice', decision); review.save(root, s)
        return s


def bind(root, script, coverage):
    """Bind a reviewed, project-authored adapter and its input files to approved context."""
    import review
    root = Path(root).resolve()
    with review.locked(root):
        s = review.load_state(root); require_layout(root, s)
        if s['previs']['required'] is not True:
            raise ValueError('用户尚未选择生成预演；不要替用户取消跳过决定')
        entry = safe_path(root, script)
        if entry.suffix != '.py' or not entry.is_file(): raise ValueError('需要项目内实际编写并检查过的 Blender Python 脚本')
        job = read_json(entry.parent / 'job.json')
        required = coverage.get('required_shots')
        if not isinstance(required, list) or not required or not coverage.get('reason', '').strip():
            raise ValueError('覆盖范围需要 required_shots 和 reason')
        shots = {q['id']: q for q in s['shots']}
        if len(set(required)) != len(required) or set(required)-shots.keys(): raise ValueError('覆盖范围镜号无效')
        fps = job.get('fps')
        if type(fps) is not int or not 1 <= fps <= 60: raise ValueError('fps 必须是 1–60 的整数')
        clips = job.get('clips', [])
        if not clips or len({c['shot'] for c in clips}) != len(clips): raise ValueError('片段镜号不能为空或重复')
        starts = {}; elapsed = 0
        for shot in s['shots']:
            starts[shot['id']] = elapsed
            duration = shot['zh']['duration']
            if not isinstance(duration, (int,float)) or duration <= 0: raise ValueError('分镜必须有已确认时长')
            elapsed += duration
        for clip in clips:
            sid = clip['shot']
            if sid not in shots or clip['duration'] != shots[sid]['zh']['duration'] or abs(clip['original_start']-starts[sid]) > 1e-6:
                raise ValueError('预演片段时间必须与已确认分镜一致：'+sid)
            if abs(clip['duration']*fps-round(clip['duration']*fps)) > 1e-6: raise ValueError('镜头时长必须落在整数帧上')
        inputs = {}
        for rel, expected in job.get('input_sha256', {}).items():
            path = safe_path(entry.parent, rel)
            if sha(path) != expected: raise ValueError('预演输入已变更：'+rel)
            inputs[path.relative_to(root).as_posix()] = expected
        for path in (entry, entry.parent / 'job.json'):
            inputs[path.relative_to(root).as_posix()] = sha(path)
        if not job.get('input_sha256'): raise ValueError('job.json 需要登记所有脚本依赖与布局的 input_sha256')
        from layout import load_layout, layout_fingerprint
        source = job.get('source_layout')
        if source not in {lay['path'] for lay in load_project(root)['layouts']}: raise ValueError('job.source_layout 必须指向当前登记布局')
        original = safe_path(root, source)
        if job.get('layout_fingerprint') != layout_fingerprint(load_layout(original)):
            raise ValueError('预演使用的布局版本与当前布局不符')
        if not any(expected == sha(original) for expected in inputs.values()):
            raise ValueError('必须将实际使用的布局副本纳入输入指纹，且与原布局一致')
        if job.get('delivery') not in (None, 'per_shot_v1'):
            raise ValueError('未知预演交付协议')
        if [c['original_start'] for c in clips] != sorted(c['original_start'] for c in clips):
            raise ValueError('预演片段必须按分镜顺序排列')
        snapshot = {'script': script, 'inputs': inputs, 'clips': clips, 'fps': fps,
                    'coverage': coverage, 'layout_proof': review.proof(root, s, 'layout'), 'bound_at': review.now()}
        if job.get('delivery'):
            snapshot['delivery'] = job['delivery']
        write_json(safe_path(root, JOB), snapshot)
        s['previs']['files'] = []; s['stages']['previs'] = None
        documents(root, [safe_path(root, JOB)] + [safe_path(root, f) for f in inputs])
        review.record(s, 'previs_bound', {'script':script, 'coverage':coverage}); review.save(root, s)
        return {'bound': script, 'missing_shots': sorted(set(required)-{c['shot'] for c in clips})}


def fresh_job(root):
    import review
    s = review.load_state(root); require_layout(root, s)
    if s['previs']['required'] is not True: raise ValueError('当前未选择生成预演')
    job = read_json(safe_path(root, JOB))
    if job['layout_proof'] != review.proof(root, s, 'layout'): raise ValueError('分镜或布局已改变，须重新编写并绑定预演')
    for rel, expected in job['inputs'].items():
        if sha(safe_path(root, rel)) != expected: raise ValueError('预演脚本或输入已改变，须重新绑定：'+rel)
    return job


def invoke(binary, script, args, log):
    cmd = [binary, '--background', '--factory-startup', '--python-exit-code', '1', '--python', str(script), '--'] + args
    # Run foreground in the CLI's tool session; caller can cancel that session. Never detach a job.
    with Path(log).open('w', encoding='utf-8') as stream:
        p = subprocess.run(cmd, stdout=stream, stderr=subprocess.STDOUT)
    if p.returncode: raise ValueError('Blender 执行失败；日志：'+str(log))


def run(root, mode='smoke', explicit=None):
    if mode not in ('build','smoke','render'): raise ValueError('无效运行模式')
    root = Path(root).resolve(); job = fresh_job(root); binary = blender_path(explicit)
    run_id = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8]
    out = safe_path(root, 'previs/runs/' + run_id); out.mkdir(parents=True)
    record = {'mode': mode, 'status': 'running', 'job': job, 'blender': binary, 'approvals_granted': False}
    write_json(out / 'run.json', record)
    write_json(safe_path(root,'previs/local-run.json'),{'run':out.relative_to(root).as_posix(),'status':'running','mode':mode})
    try:
        invoke(binary, safe_path(root, job['script']), (['--'+mode] if mode != 'build' else []) + ['--out', str(out/'output')], out/'blender.log')
        result = read_json(out/'output/render-report.json')
        if mode == 'render' and not result.get('video'):
            encode = {'mode':'encode', 'directory':str(out/'output/comparison'), 'fps':job['fps'],
                      'frames':round(sum(c['duration'] for c in job['clips'])*job['fps']),
                      'output':str(out/'output/critical-comparison.mp4'), 'report':str(out/'media.json')}
            write_json(out/'media-request.json', encode)
            invoke(binary, MEDIA, [str(out/'media-request.json')], out/'encode.log')
            result.update(video='critical-comparison.mp4',status='video_rendered_awaiting_review')
            write_json(out/'output/render-report.json',result)
        record['status'] = result['status']
        write_json(out / 'run.json', record)
        if mode == 'render' and job.get('delivery') == 'per_shot_v1':
            import previs_export
            previs_export.export_shots(root, out.relative_to(root).as_posix(), explicit)
    except (ValueError,OSError) as exc:
        record.update(status='failed',error=str(exc)); write_json(out/'run.json', record)
        write_json(safe_path(root,'previs/local-run.json'),{'run':out.relative_to(root).as_posix(),'status':'failed','mode':mode})
        raise
    write_json(out/'run.json', record)
    write_json(safe_path(root,'previs/local-run.json'),{'run':out.relative_to(root).as_posix(),'status':record['status'],'mode':mode})
    # Running does not mark the visual review passed or grant a user approval.
    return {'run':out.relative_to(root).as_posix(), 'status':record['status'], 'next':'检查实际对照视频后使用 previs-check；smoke/build 不能代替完整视频。'}


def check_run(root, relative, note, reject=False, explicit=None):
    import review
    from PIL import Image
    if not note.strip(): raise ValueError('需要实际观看视频后的检查说明')
    root = Path(root).resolve(); job = fresh_job(root); folder = safe_path(root,relative)
    run_record = read_json(folder/'run.json')
    if run_record['job'] != job or run_record['mode'] != 'render': raise ValueError('只接受当前绑定任务的完整渲染结果')
    result = read_json(folder/'output/render-report.json')
    total = round(sum(c['duration'] for c in job['clips'])*job['fps'])
    if result.get('rendered_frames') != list(range(1,total+1)): raise ValueError('帧序列不完整')
    frames = read_json(folder/'output/frame-map.json')
    if len(frames) != total: raise ValueError('缺少逐帧时间对照')
    cursor = 0
    for clip in job['clips']:
        for i in range(round(clip['duration']*job['fps'])):
            record = frames[cursor]; cursor += 1
            if record['frame'] != cursor or record['shot'] != clip['shot'] or abs(record['original_time']-(clip['original_start']+i/job['fps'])) > 1e-5:
                raise ValueError('原片时间／镜号对照错误')
    size = None
    for i in range(1,total+1):
        with Image.open(folder/'output/comparison'/f'{i:06d}.png') as im:
            if size is not None and size != im.size: raise ValueError('对照帧尺寸不一致')
            size = im.size; im.verify()
    video = safe_path(folder/'output',result.get('video',''))
    if video.suffix.lower() not in ('.mp4','.mov','.webm') or video.stat().st_size < 32: raise ValueError('缺少真实视频')
    request = {'mode':'inspect','video':str(video),'report':str(folder/'video-inspect.json')}
    write_json(folder/'inspect-request.json',request)
    invoke(blender_path(explicit), MEDIA, [str(folder/'inspect-request.json')], folder/'inspect.log')
    decoded = read_json(folder/'video-inspect.json')
    if decoded['frames'] != total or decoded['size'] != list(size) or abs(decoded['fps']-job['fps']) > .01:
        raise ValueError('实际视频帧数／尺寸／帧率与对照序列不符')
    bundle = None
    if job.get('delivery') == 'per_shot_v1' or (folder / 'shot-export.json').exists():
        import previs_export
        bundle = previs_export.checked_bundle(root, folder)
    missing = sorted(set(job['coverage']['required_shots'])-{c['shot'] for c in job['clips']})
    rec = {'status':'needs_revision' if reject else ('partial' if missing else 'passed'), 'note':note,
           'missing_shots':missing,'job_sha256':sha(safe_path(root,JOB)), 'layout_proof':job['layout_proof'],
           'video':video.relative_to(root).as_posix(),'video_sha256':sha(video),'at':review.now()}
    if bundle:
        rec['shot_export'] = bundle
    with review.locked(root):
        if fresh_job(root) != job: raise ValueError('检查期间项目已改变')
        s=review.load_state(root); write_json(safe_path(root,CHECK),rec)
        s['stages']['previs']=None
        s['previs']['files']=[rec['video']] if rec['status']=='passed' else []
        documents(root,[video,safe_path(root,CHECK),folder/'run.json',folder/'output/frame-map.json',folder/'output/render-report.json',folder/'output/critical-previs.blend'])
        review.record(s,'previs_checked',rec);review.save(root,s)
    return rec


def confirmation_check(root):
    """Managed local jobs require actual checked outputs; legacy external videos stay compatible."""
    if not safe_path(root,JOB).exists(): return
    job=fresh_job(root)
    if not safe_path(root,CHECK).exists(): raise ValueError('本地预演尚未经过实际视频检查')
    rec=read_json(safe_path(root,CHECK))
    if rec['status']!='passed' or rec['job_sha256']!=sha(safe_path(root,JOB)) or rec['layout_proof']!=job['layout_proof']:
        raise ValueError('预演检查未通过、范围不完整或已过期')
    bundle = rec.get('shot_export')
    if job.get('delivery') == 'per_shot_v1' and not bundle:
        raise ValueError('缺少逐镜交付检查')
    if bundle:
        import previs_export
        source_folder = safe_path(root, rec['video']).parent.parent
        if previs_export.checked_bundle(root, source_folder) != bundle:
            raise ValueError('逐镜交付已改变，需要重新检查')
    if sha(safe_path(root,rec['video']))!=rec['video_sha256']: raise ValueError('预演视频已变更，需要重新检查')
    import review
    if review.load_state(root)['previs']['files'] != [rec['video']]: raise ValueError('确认视频与已检查的视频不一致')
