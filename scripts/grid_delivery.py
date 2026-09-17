"""Validate and export keyframe-grid projects without legacy layout gates."""
import hashlib
import math
import os
from pathlib import Path
import tempfile
import zipfile

from PIL import Image
from core import read_json, safe_path
import grid_workflow as grid
import h3
from group_package import aligned_frames, encode_json, SOURCE
from review import locked

PLAN = 'grid-delivery.json'
VIEWS = ('front', 'back', 'left', 'head', 'sheet')


def identifier(value):
    import re
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*', value):
        raise ValueError('编号须以英文字母开头，仅含字母、数字、下划线或短横线')
    return value


def load_plan(root):
    plan = read_json(safe_path(root, PLAN))
    if not isinstance(plan, dict) or plan.get('schema_version') != 1:
        raise ValueError('grid-delivery.json schema_version 必须为 1')
    for key in ('characters', 'tasks'):
        rows = plan.get(key)
        if not isinstance(rows, list) or (key == 'tasks' and not rows):
            raise ValueError(key + ' 必须为列表，tasks 不可为空')
        ids = [identifier(row['id']) for row in rows]
        if len(ids) != len(set(ids)):
            raise ValueError(key + ' 编号重复')
    return plan


def inspect(root):
    """Caller holds project lock. Confirmation and delivery completeness stay separate."""
    root = Path(root).resolve()
    errors, pending, files, compiled = [], [], set(), {}
    try:
        state = read_json(root / 'grid-workflow.json')
        if state.get('workflow') != 'keyframe-grid-v1':
            raise ValueError('需要九宫格项目')
        plan = load_plan(root)
        statuses = grid.status(root, state)
        pending.extend(f'{s}: {v}' for s, v in statuses.items() if v != 'confirmed')
        registered = {s: set(row['files']) for s, row in state['stages'].items()}

        def artifact(name, stage, image=False, text=False):
            path = safe_path(root, name)
            if name not in registered.get(stage, set()):
                raise ValueError(f'{stage} 尚未登记 {name}')
            if not path.is_file():
                raise ValueError('文件缺失：' + name)
            if image:
                if path.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp'):
                    raise ValueError('图片后缀不支持：' + name)
                with Image.open(path) as im:
                    im.verify()
            if text and not path.read_text(encoding='utf-8').strip():
                raise ValueError('文本为空：' + name)
            files.add(name)
            return path

        artifact(PLAN, 'director')
        artifact(plan['director'], 'director', text=True)
        characters = {c['id']: c for c in plan['characters']}
        if not characters:
            artifact(plan['no_characters'], 'characters', text=True)
        for c in characters.values():
            if type(c['version']) is not int or c['version'] < 1 or set(c['views']) != set(VIEWS):
                raise ValueError(c['id'] + ' 需要正整数版本和 front/back/left/head/sheet 五张图片')
            if len(set(c['views'].values())) != 5:
                raise ValueError(c['id'] + ' 四视图和合图须分别保存')
            for path in c['views'].values():
                artifact(path, 'characters', image=True)
            artifact(c['source'], 'characters', text=True)
        for task in plan['tasks']:
            tid = task['id']
            duration = task['duration']
            if type(duration) not in (int, float) or not math.isfinite(duration) or not 4 <= duration <= 15:
                raise ValueError(tid + ' 时长须为 4–15 秒有限数')
            if not isinstance(task['characters'], dict):
                raise ValueError(tid + ' characters 须为编号到确切版本的对象')
            for cid, version in task['characters'].items():
                if cid not in characters or type(version) is not int or version != characters[cid]['version']:
                    raise ValueError(tid + ' 人物版本不匹配：' + cid)
            artifact(task['grid'], 'grids', image=True)
            panel_map = read_json(artifact(task['panel_map'], 'grids'))
            if panel_map['task_id'] != tid or panel_map['duration'] != duration or panel_map['characters'] != task['characters']:
                raise ValueError(tid + ' panel-map 任务、时长或人物版本不匹配')
            panels = panel_map['panels']
            if not isinstance(panels, list) or any(type(p['panel']) is not int for p in panels) or [p['panel'] for p in panels] != list(range(1, 10)):
                raise ValueError(tid + ' panel-map 必须按顺序覆盖九格 1–9')
            spec = read_json(artifact(task['prompt_spec'], 'prompts'))
            refs = task['references']
            if not isinstance(refs, list) or not 1 <= len(refs) <= 9:
                raise ValueError(tid + ' 图片槽位须为 1–9 个')
            labels = [f'<Picture {i}>' for i in range(1, len(refs) + 1)]
            if [r['label'] for r in refs] != labels or spec.get('labels') != labels:
                raise ValueError(tid + ' 图片槽位必须连续且与编译输入一致')
            expected = {task['grid']} | {characters[c]['views']['sheet'] for c in task['characters']}
            if {r['path'] for r in refs} != expected or len(refs) != len(expected):
                raise ValueError(tid + ' 必须准确绑定本段九宫格和所用人物合图')
            media = [{'label': r['label'], 'type': 'image', 'roles': r['roles']} for r in refs]
            if any(set(r['roles']) & {'first_frame', 'last_frame'} for r in refs):
                raise ValueError(tid + ' 合图不能放入首尾帧槽')
            if spec.get('media') != media:
                raise ValueError(tid + ' 编译素材用途与槽位清单不一致')
            bilingual = list(spec['sections'].values())
            for shot in spec['shots']:
                bilingual.extend([shot['camera'], shot['scene']])
                bilingual.extend(a['delivery'] if 'text' in a else a for a in shot['action'])
            if any(not isinstance(v, dict) or any(not isinstance(v.get(lang), str) or not v[lang].strip() for lang in ('en', 'zh')) for v in bilingual):
                raise ValueError(tid + ' 提示词每个创作字段都需要非空原文与中文对照')
            result = h3.compile_task(spec)
            if not math.isclose(result['duration'], duration, abs_tol=1e-6):
                raise ValueError(tid + ' 编译时长与任务时长不符')
            saved = read_json(artifact(task['prompt'], 'prompts'))
            if any(saved.get(k) != result[k] for k in ('text', 'translation_zh', 'duration')):
                raise ValueError(tid + ' 提示词或中文对照已过期，请重新编译并登记')
            shots = spec['shots']
            shot_ids = [s.get('id', 'S' + str(i + 1)) for i, s in enumerate(shots)]
            if len(set(shot_ids)) != len(shot_ids):
                raise ValueError(tid + ' 镜号重复')
            starts = []; cursor = 0
            for shot in shots:
                starts.append(cursor); cursor += shot['duration']
            previous = -1
            for i, panel in enumerate(panels):
                t = panel['time_seconds']
                if type(t) not in (int, float) or not math.isfinite(t) or not 0 <= t <= duration or t < previous:
                    raise ValueError(tid + ' 九格时间必须有序且在任务时长内')
                if i and t == previous and panels[i - 1]['transition'] != 'hold':
                    raise ValueError(tid + ' 重复时间须明确 hold')
                if panel['shot_id'] not in shot_ids or panel['transition'] not in ('continuous', 'cut', 'hold') or not isinstance(panel['description'], str) or not panel['description'].strip():
                    raise ValueError(tid + ' 九格镜号、连接方式或画面描述无效')
                si = shot_ids.index(panel['shot_id'])
                if t < starts[si] or t > starts[si] + shots[si]['duration']:
                    raise ValueError(tid + ' 九格时刻不在所关联镜头范围内')
                if i and panel['shot_id'] != panels[i - 1]['shot_id']:
                    if panels[i - 1]['transition'] != 'cut' or not math.isclose(t, starts[si], abs_tol=1e-6):
                        raise ValueError(tid + ' 切镜须标记 cut 且对齐提示词切点')
                previous = t
            if set(p['shot_id'] for p in panels) != set(shot_ids):
                raise ValueError(tid + ' 九格未覆盖任务内全部镜头')
            compiled[tid] = result
        # Export all registered originals, not an arbitrary recursive directory walk.
        for stage, names in registered.items():
            for name in names:
                artifact(name, stage)
        import grid_series
        inherited = grid_series.verify(root)
        if inherited['errors']:
            raise ValueError('; '.join(inherited['errors']))
        for stage in ('characters', 'grids', 'prompts'):
            items = state['stages'].get(stage, {}).get('items')
            if items is not None:
                expected_ids = set(characters) if stage == 'characters' else {t['id'] for t in plan['tasks']}
                if not characters and stage == 'characters':
                    expected_ids = {'NONE'}
                if set(items) != expected_ids:
                    raise ValueError(stage + ' 逐项登记须与交付清单一致')
                for key, item in items.items():
                    if stage == 'characters':
                        required = set(characters[key]['views'].values()) | {characters[key]['source']} if characters else {plan['no_characters']}
                        dependencies = {'director'}
                    else:
                        task = next(t for t in plan['tasks'] if t['id'] == key)
                        required = {task['grid'], task['panel_map']} if stage == 'grids' else {task['prompt_spec'], task['prompt']}
                        if stage == 'grids':
                            dependencies = {'director'} | ({'characters/' + c for c in task['characters']} if task['characters'] else {'characters/NONE'})
                        else:
                            dependencies = {'director', 'grids/' + key}
                    if not required <= set(item['files']) or set(item['dependencies']) != dependencies:
                        raise ValueError(stage + '/' + key + ' 素材归属或依赖与交付清单不一致')
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        errors.append(str(exc))
    return {'ok': not errors and not pending, 'errors': errors, 'pending': pending,
            'target_h3_validated': False, 'files': sorted(files), 'compiled': compiled}


def validate(root):
    with locked(root):
        result = inspect(root)
    return {k: v for k, v in result.items() if k != 'compiled'}


def package(root, output, adapter='generic', draft=False):
    root, output = Path(root).resolve(), Path(output).resolve()
    if adapter not in ('generic', 'aimixer-h3'):
        raise ValueError('未知交付适配器')
    if output.exists() or not output.name.endswith('.mmxpack.zip' if adapter == 'aimixer-h3' else '.zip'):
        raise ValueError('使用未占用的 ZIP 路径；导演台包须以 .mmxpack.zip 结尾')
    with locked(root):
        report = inspect(root)
        if report['errors'] or (report['pending'] and not draft):
            raise ValueError('; '.join(report['errors'] + report['pending']))
        plan = load_plan(root)
        originals = {name: safe_path(root, name).read_bytes() for name in report['files']}
        originals['grid-workflow.json'] = (root / 'grid-workflow.json').read_bytes()
        snapshot_state = read_json(root / 'grid-workflow.json')
        for row in snapshot_state['stages'].values():
            if any(hashlib.sha256(originals[name]).hexdigest() != proof for name, proof in row['hashes'].items()):
                raise ValueError('登记素材已改变，请重新登记后导出')
        files = {'project/' + name: raw for name, raw in originals.items()}
        bindings, timing = [], []; cursor = 0
        for number, task in enumerate(plan['tasks'], 1):
            refs = []
            for slot, ref in enumerate(task['references']):
                dest = f'asset_groups/{number:04d}/Picture{slot + 1}' + Path(ref['path']).suffix.lower()
                files[dest] = originals[ref['path']]
                refs.append({'index': slot, 'imageFile': dest, 'fileName': Path(dest).name, 'type': 'input', 'subfolder': str(Path(dest).parent)})
                bindings.append({'task': task['id'], **ref, 'pack_path': dest, 'sha256': hashlib.sha256(files[dest]).hexdigest()})
            compiled = report['compiled'][task['id']]
            frames = aligned_frames(task['duration'])
            timing.append({'id': task['id'], 'requested_seconds': task['duration'], 'model_frames': frames, 'model_seconds': frames / 24})
            files[f"tasks/{task['id']}.md"] = (compiled['text'] + '\n\n## 中文对照\n\n' + compiled['translation_zh']).encode('utf-8')
            if adapter == 'aimixer-h3':
                files[f'asset_groups/{number:04d}/group.json'] = encode_json({'id': task['id'], 'prompt': compiled['text'], 'negativePrompt': '', 'durationSec': task['duration'], 'frameCount': frames, 'length': frames, 'start': cursor, 'taskType': 'r2v', 'refs': refs, 'refVideos': [], 'refAudios': [], 'continuityFromPrev': False})
            cursor += frames
        if adapter == 'aimixer-h3':
            files['pack.json'] = encode_json({'format': 'minimax-h3-director-pack', 'formatVersion': 1, 'taskType': 'r2v', 'widgets': {}, 'output': {'mode': 'fixed', 'width': 864, 'height': 480, 'frameRate': 24, 'exportMode': 'all', 'audioMode': 'generate', 'refImageSize': 'match', 'continuityEnabled': False}})
            files['shared_params/shared_params.json'] = encode_json({'commonEnabled': False, 'commonCollapsed': False, 'prompt': '', 'refs': [], 'refAudios': [], 'refVideos': []})
        files['extra/bindings.json'] = encode_json(bindings)
        files['README.md'] = ('# 九宫格交付\n\n' + ('阶段草稿，未完成用户确认。\n' if draft else '材料与确认检查通过，等待目标环境导入实测。\n') +
            'project/ 为可恢复制作目录。各任务含人物合图、九宫格、提示词和中文对照。\n' +
            'AIMixer 包按任务顺序全部导出；通用包按清单手动导入。模型帧对齐会改变尾部时长，请核对 extra/delivery.json。\n' +
            '九宫格不保证精确锁帧；尚未生成或验证目标视频。\n').encode('utf-8')
        files['extra/delivery.json'] = encode_json({'status': 'draft' if draft else 'ready_for_import_test', 'adapter': adapter, 'adapter_source': SOURCE if adapter == 'aimixer-h3' else None, 'target_h3_validated': False, 'pending': report['pending'], 'timing': timing, 'sha256': {n: hashlib.sha256(b).hexdigest() for n, b in files.items()}})
        output.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix='.svd-', dir=output.parent); os.close(fd)
        try:
            with zipfile.ZipFile(temp, 'w', zipfile.ZIP_DEFLATED) as archive:
                for name, raw in files.items():
                    archive.writestr(name, raw)
            with zipfile.ZipFile(temp) as archive:
                if archive.testzip():
                    raise ValueError('压缩包校验失败')
            if any(safe_path(root, name).read_bytes() != raw for name, raw in originals.items()):
                raise ValueError('导出期间文件已改变')
            # Exclusive publish: never replace an existing delivery even in a race.
            os.link(temp, output)
        finally:
            Path(temp).unlink(missing_ok=True)
    return {'path': str(output), 'status': 'draft' if draft else 'ready_for_import_test', 'tasks': len(plan['tasks']), 'target_h3_validated': False}
