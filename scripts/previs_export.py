"""Lossless frame selection for per-shot review/reference MP4s; never grants approval."""
from pathlib import Path
import datetime
import uuid

from core import read_json, safe_path, write_json


def plan(root, relative):
    import previs
    from PIL import Image
    root = Path(root).resolve()
    job = previs.fresh_job(root)
    folder = safe_path(root, relative)
    run = read_json(folder / 'run.json')
    if run['job'] != job or run['mode'] != 'render' or run.get('status') == 'failed':
        raise ValueError('逐镜导出需要当前任务的完整渲染结果；不能使用 smoke 或过期运行')
    output = folder / 'output'
    total = round(sum(c['duration'] for c in job['clips']) * job['fps'])
    report = read_json(output / 'render-report.json')
    mapping = read_json(output / 'frame-map.json')
    if report.get('rendered_frames') != list(range(1, total + 1)) or len(mapping) != total:
        raise ValueError('逐镜导出源帧不完整')
    clips = []
    cursor = 1
    for clip in job['clips']:
        count = round(clip['duration'] * job['fps'])
        for offset in range(count):
            frame = mapping[cursor + offset - 1]
            if (frame['frame'] != cursor + offset or frame['shot'] != clip['shot'] or
                    abs(frame['original_time'] - clip['original_start'] - offset / job['fps']) > 1e-5):
                raise ValueError('逐镜导出的镜号／时间不一致')
        clips.append(dict(clip, frame_start=cursor, frames=count))
        cursor += count
    if [c['original_start'] for c in clips] != sorted(c['original_start'] for c in clips):
        raise ValueError('串联版必须按原分镜顺序排列')
    sizes = {}
    sources = {}
    for kind in ('comparison', 'camera'):
        size = None
        for number in range(1, total + 1):
            path = safe_path(output, f'{kind}/{number:06d}.png')
            with Image.open(path) as image:
                if size is not None and image.size != size:
                    raise ValueError('预演帧尺寸不一致：' + kind)
                size = image.size
                image.verify()
            sources[path.relative_to(root).as_posix()] = previs.sha(path)
        if min(size) < 2 or size[0] % 2 or size[1] % 2:
            raise ValueError('H.264 帧宽高必须为正偶数：' + kind)
        sizes[kind] = list(size)
    for path in (folder / 'run.json', output / 'frame-map.json', output / 'render-report.json'):
        sources[path.relative_to(root).as_posix()] = previs.sha(path)
    return job, clips, sizes, sources


def export_shots(root, relative, explicit=None):
    import previs
    import review
    root = Path(root).resolve()
    job, clips, sizes, sources = plan(root, relative)
    folder = safe_path(root, relative)
    export_id = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8]
    dest = folder / 'exports' / export_id
    dest.mkdir(parents=True)
    items = []
    shots = []
    state = review.load_state(root)
    all_shots = [s['id'] for s in state['shots']]
    descriptions = {s['id']: s['zh'] for s in state['shots']}
    for clip in clips:
        sid = clip['shot']
        base = safe_path(dest, 'shots/' + sid)
        base.mkdir(parents=True)
        entry = dict(clip, files={}, continuity={
            'director_note': descriptions[sid].get('continuity', ''),
            'start_state': clip.get('start_state'), 'end_state': clip.get('end_state'),
            'status': 'pending_visual_review',
            'first_camera_frame': (folder / 'output/camera' / f"{clip['frame_start']:06d}.png").relative_to(root).as_posix(),
            'last_camera_frame': (folder / 'output/camera' / f"{clip['frame_start']+clip['frames']-1:06d}.png").relative_to(root).as_posix(),
        })
        for kind, filename in (('comparison', 'review.mp4'), ('camera', 'reference.mp4')):
            target = base / filename
            entry['files'][kind] = target.relative_to(dest).as_posix()
            items.append({'mode': 'encode', 'directory': str(folder / 'output' / kind),
                          'frame_start': clip['frame_start'], 'frames': clip['frames'], 'fps': job['fps'],
                          'output': str(target), 'report': str(target.with_suffix('.metadata.json'))})
        shots.append(entry)
    timeline = {}
    total = sum(c['frames'] for c in clips)
    for kind, filename in (('comparison', 'timeline-review.mp4'), ('camera', 'timeline-reference.mp4')):
        timeline[kind] = filename
        target = dest / filename
        items.append({'mode': 'encode', 'directory': str(folder / 'output' / kind),
                      'frames': total, 'fps': job['fps'], 'output': str(target),
                      'report': str(target.with_suffix('.metadata.json'))})
    request = dest / 'encode-request.json'
    write_json(request, {'mode': 'batch', 'items': items, 'report': str(dest / 'batch-report.json')})
    previs.invoke(previs.blender_path(explicit), previs.MEDIA, [str(request)], dest / 'encode.log')
    outputs = {}
    for item in items:
        path = Path(item['output'])
        meta = read_json(item['report'])
        kind = 'camera' if 'reference' in path.name else 'comparison'
        if (meta.get('frames') != item['frames'] or meta.get('size') != sizes[kind] or
                abs(meta.get('fps', 0) - job['fps']) > .01 or meta.get('decoded') is not True or
                path.stat().st_size < 32):
            raise ValueError('逐镜视频实际解码校验失败：' + str(path))
        outputs[path.relative_to(root).as_posix()] = previs.sha(path)
        outputs[Path(item['report']).relative_to(root).as_posix()] = previs.sha(item['report'])
    # A cut preserves original frame selection; a gap must not masquerade as an adjacent shot.
    boundaries = []
    for left, right in zip(clips, clips[1:]):
        gap = right['original_start'] - (left['original_start'] + left['duration'])
        boundaries.append({'from': left['shot'], 'to': right['shot'], 'omitted_seconds': gap,
                           'type': 'adjacent' if abs(gap) < 1e-6 else 'excerpt_gap',
                           'status': 'pending_visual_review'})
    manifest = {'schema_version': 1, 'status': 'generated_pending_review', 'approvals_granted': False,
                'target_validated': False, 'job_sha256': previs.sha(safe_path(root, previs.JOB)),
                'source_run': relative, 'fps': job['fps'], 'sizes': sizes, 'shots': shots,
                'timeline': timeline, 'boundaries': boundaries,
                'missing_storyboard_shots': [sid for sid in all_shots if sid not in {c['shot'] for c in clips}],
                'source_sha256': sources, 'output_sha256': outputs}
    index = dest / 'index.json'
    write_json(index, manifest)
    lines = ['# 逐镜预演', '', '**待人工检查与确认；模型实际导入尚未验证。**', '',
             f"覆盖 {len(clips)}/{len(all_shots)} 镜，合计 {total/job['fps']:g} 秒。保持原帧率与时长；未压缩时间。", '',
             '| 镜号 | 原片起点（秒） | 时长（秒） | 审核版 | 纯摄影机参考候选 |',
             '|---|---:|---:|---|---|']
    for shot in shots:
        lines.append(f"| {shot['shot']} | {shot['original_start']:g} | {shot['duration']:g} | "
                     f"[查看]({shot['files']['comparison']}) | [查看]({shot['files']['camera']}) |")
    lines += ['', '[串联审核版](timeline-review.mp4) · [串联纯摄影机版](timeline-reference.mp4)', '',
              '串联版用于整体检查，不能据此声称满足某一模型的单次输入限制。',
              '逐镜共用已渲染的场景时间线；检查人物位置、持物、门状态、动作接续、轴线和视线。',
              '首末诊断帧与导演连续性要求记录在 index.json 中，不是 AI 分镜首尾帧资产。',
              '镜间省略和未覆盖镜头见 index.json；导出不会补造缺失镜头或授予批准。', '']
    (dest / 'README.md').write_text('\n'.join(lines), encoding='utf-8')
    with review.locked(root):
        if previs.fresh_job(root) != job or any(previs.sha(safe_path(root, p)) != h for p, h in sources.items()):
            raise ValueError('导出期间输入已改变，结果不能登记')
        pointer = {'index': index.relative_to(root).as_posix(), 'sha256': previs.sha(index),
                   'status': 'generated_pending_review'}
        write_json(folder / 'shot-export.json', pointer)
        previs.documents(root, [index, dest / 'README.md', folder / 'shot-export.json'] +
                         [safe_path(root, p) for p in outputs] +
                         [safe_path(root, shot['continuity'][key]) for shot in shots
                          for key in ('first_camera_frame', 'last_camera_frame')])
        # The review stage stays pending until the new delivery has actually been inspected.
        s = review.load_state(root)
        s['stages']['previs'] = None
        s['previs']['files'] = []
        review.record(s, 'previs_shots_exported', pointer)
        review.save(root, s)
    return {'index': index.relative_to(root).as_posix(), 'shots': len(shots),
            'missing_shots': manifest['missing_storyboard_shots'], 'status': manifest['status']}


def checked_bundle(root, folder):
    """Verify source/output identity again before a parent previs review can pass."""
    import previs
    root = Path(root).resolve()
    pointer = read_json(Path(folder) / 'shot-export.json')
    index = safe_path(root, pointer['index'])
    if previs.sha(index) != pointer['sha256']:
        raise ValueError('逐镜索引已变更')
    data = read_json(index)
    if data['job_sha256'] != previs.sha(safe_path(root, previs.JOB)):
        raise ValueError('逐镜导出已过期')
    for path, expected in {**data['source_sha256'], **data['output_sha256']}.items():
        if previs.sha(safe_path(root, path)) != expected:
            raise ValueError('逐镜视频或源帧已改变：' + path)
    return {'index': pointer['index'], 'index_sha256': pointer['sha256'],
            'files_sha256': data['output_sha256']}
