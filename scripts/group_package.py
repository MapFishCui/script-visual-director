"""Export portable plans or AIMixer r2v director packs; never runs a model."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import zipfile

from core import safe_path, validate_project
import groups
import review

UPSTREAM = '52f8fb7b8d8eb6bebf33ebb534827efa8f95484c'
SOURCE = 'https://github.com/AIMixer/ComfyUI_MiniMaxH3_Director/blob/' + UPSTREAM + '/director/pack.py'


def aligned_frames(seconds):
    count = max(5, round(seconds * 24))
    # AIMixer r2v minimum is checked against the same 17k+5 grid.
    return count + (5 - count % 17) % 17


def encode_json(data):
    return (json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()


def package(root, output, draft=False):
    root = Path(root).resolve(); output = Path(output).resolve()
    if output.exists(): raise ValueError('文件已存在，请使用新的导出版本路径')
    with review.locked(root):
        data = groups.load(root)
        report = groups.readiness(root)
        project = validate_project(root, strict=False)
        if project['errors']: raise ValueError('项目存在结构或文件错误：' + str(project['errors']))
        pending = report['pending'] + project['pending']
        if pending and not draft: raise ValueError('正式导出被阻止：' + '; '.join(pending))
        adapter = data['adapter']
        if adapter == 'aimixer-h3' and not output.name.endswith('.mmxpack.zip'):
            raise ValueError('AIMixer 导演包应使用 .mmxpack.zip 后缀')
        if adapter == 'generic' and output.suffix != '.zip': raise ValueError('通用分组包应使用 .zip 后缀')
        files = {}; bindings = []; shared = []
        cursor = 0; durations = []
        for number, group in enumerate(report['groups'], 1):
            prompt = data['compiled'].get(group['id'], {}).get('text', '')
            refs = {'image': [], 'video': []}; seconds = []
            for ref in group['slots']:
                limit = 9 if ref['kind'] == 'image' else 3
                if ref['slot'] > limit and adapter == 'aimixer-h3':
                    raise ValueError('素材数量超出 AIMixer/H3 上限，草稿也不能生成无效槽位')
                binding = {k: ref[k] for k in ('key', 'kind', 'label', 'slot', 'shared')}
                binding.update(group=group['id'], source=ref.get('resolved'))
                bindings.append(binding)
                if not ref['resolved']: continue
                resolved = ref['resolved']; source = safe_path(root, resolved['path'])
                suffix = source.suffix.lower()
                if suffix not in ({'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tif', '.tiff'} if ref['kind'] == 'image' else {'.mp4', '.mov', '.webm'}):
                    raise ValueError('导演包不支持此素材后缀：' + suffix)
                directory = 'shared_params' if ref['shared'] else f'asset_groups/{number:04d}'
                stem = 'Picture' if ref['kind'] == 'image' else 'Video'
                dest = f"{directory}/{stem}{ref['slot']}{suffix}"
                raw = source.read_bytes()
                if hashlib.sha256(raw).hexdigest() != resolved['sha256']:
                    raise ValueError('导出时素材已改变')
                files[dest] = raw
                binding['pack_path'] = dest
                field = 'imageFile' if ref['kind'] == 'image' else 'videoFile'
                value = {'index': ref['slot'] - 1, field: dest, 'fileName': Path(dest).name,
                         'type': 'input', 'subfolder': directory}
                if ref['shared']:
                    if not any(r['index'] == value['index'] for r in shared): shared.append(value)
                else:
                    refs[ref['kind']].append(value)
                if ref['kind'] == 'video': seconds.append(resolved['seconds'])
            if adapter == 'aimixer-h3' and (any(not 2 <= s <= 15 for s in seconds) or sum(seconds) > 15 + 1e-6):
                raise ValueError('参考视频时长超限，请重新分组或细分；不通过加速来绕过')
            count = aligned_frames(group['duration']) if adapter == 'aimixer-h3' else round(group['duration'] * 24)
            durations.append({'id': group['id'], 'requested_seconds': group['duration'],
                              'model_frames': count, 'model_seconds': count / 24,
                              'tail_seconds': count / 24 - group['duration']})
            if adapter == 'aimixer-h3':
                native = {'id': group['id'], 'prompt': prompt, 'negativePrompt': '',
                          'durationSec': group['duration'], 'frameCount': count, 'length': count,
                          'start': cursor, 'taskType': 'r2v', 'refs': refs['image'], 'refVideos': refs['video'],
                          'refAudios': [], 'continuityFromPrev': False}
                files[f'asset_groups/{number:04d}/group.json'] = encode_json(native)
            cursor += count
        if adapter == 'aimixer-h3':
            files['pack.json'] = encode_json({'format': 'minimax-h3-director-pack', 'formatVersion': 1,
                'taskType': 'r2v', 'widgets': {}, 'output': {'mode': 'fixed', 'width': 864, 'height': 480,
                    'frameRate': 24, 'exportMode': 'all', 'audioMode': 'generate', 'refImageSize': 'match',
                    'continuityEnabled': False, 'continuityOverlapFrames': 22, 'continuityMode': 'guide',
                    'continuityRedraw': .10}})
            files['shared_params/shared_params.json'] = encode_json({'commonEnabled': bool(shared),
                'commonCollapsed': False, 'prompt': '', 'refs': shared, 'refAudios': [], 'refVideos': []})
        files['extra/groups.json'] = encode_json(data)
        files['extra/shot_map.json'] = encode_json([{
            'id': g['id'], 'shots': [{k: c[k] for k in ('shot', 'local_start', 'duration', 'original_start')} for c in g['cuts']],
            'title': g['title'], 'intent_zh': g['intent_zh'], 'continuity_in': g['continuity_in'],
            'continuity_out': g['continuity_out'], 'translation_zh': data['compiled'].get(g['id'], {}).get('translation_zh', '')
        } for g in report['groups']])
        files['extra/bindings.json'] = encode_json(bindings)
        files['extra/delivery.json'] = encode_json({'status': 'draft' if draft else 'ready_for_import_test',
            'target_h3_validated': False, 'adapter': adapter, 'adapter_source': SOURCE if adapter == 'aimixer-h3' else None,
            'pending': pending, 'timing': durations,
            'notes': ['组内切镜使用原定时长；模型按17k+5帧对齐可能增加尾部，未将预演加速。',
                      '输出画布使用导演台默认864×480，可在导入后调整；实际部署须复核。',
                      '段间引导默认关闭；用户按连续动作需要在导演台开启。',
                      'r2v音视频采样由目标系统执行，本skill没有生成配音或最终视频。'],
            'sha256': {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}})
        output.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(prefix='.svd-group-', dir=output.parent)
        os.close(handle)
        try:
            with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
                for name, raw in files.items(): archive.writestr(name, raw)
            with zipfile.ZipFile(temporary) as archive:
                if archive.testzip() is not None: raise ValueError('压缩包校验失败')
            # Re-resolve bound inputs before publishing, including video/source fingerprints.
            for g in report['groups']:
                for ref in g['slots']:
                    if ref['resolved'] and groups.resolve(root, ref) != ref['resolved']:
                        raise ValueError('导出期间素材依赖已改变')
            if output.exists(): raise ValueError('输出路径已被占用')
            os.replace(temporary, output)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)
    return {'path': str(output), 'status': 'draft' if draft else 'ready_for_import_test',
            'groups': len(report['groups']), 'pending': pending, 'target_h3_validated': False}
