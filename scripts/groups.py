"""Portable generation groups. Editorial grouping and translation remain Codex work."""
import copy
import math
from pathlib import Path
import re

from jsonschema import validate as schema_validate, ValidationError
from core import current, finished, load_project, read_json, safe_path, write_json
import review

STATE = 'groups/state.json'
REF = {'type': 'object', 'additionalProperties': False,
       'required': ['key', 'kind'], 'properties': {
           'key': {'type': 'string', 'pattern': '^[A-Za-z][A-Za-z0-9_-]*$'},
           'kind': {'enum': ['image', 'video']}, 'asset': {'type': 'string'},
           'version': {'type': 'integer', 'minimum': 1}, 'index': {'type': 'string'},
           'item': {'type': 'string'}}}
GROUP = {'type': 'object', 'additionalProperties': False,
         'required': ['id', 'title', 'shots', 'intent_zh', 'continuity_in', 'continuity_out', 'references'],
         'properties': {
             'id': {'type': 'string', 'pattern': '^G[A-Za-z0-9_-]+$'},
             **{k: {'type': 'string', 'minLength': 1} for k in ('title', 'intent_zh', 'continuity_in', 'continuity_out')},
             'shots': {'type': 'array', 'minItems': 1, 'uniqueItems': True, 'items': {'type': 'string'}},
             'references': {'type': 'array', 'items': REF}}}
PLAN = {'type': 'object', 'additionalProperties': False,
        'required': ['revision', 'project_revision', 'adapter', 'shared_references', 'groups'],
        'properties': {'revision': {'type': 'integer', 'minimum': 0},
                       'project_revision': {'type': 'integer', 'minimum': 0},
                       'adapter': {'enum': ['generic', 'aimixer-h3']},
                       'shared_references': {'type': 'array', 'items': REF},
                       'groups': {'type': 'array', 'minItems': 1, 'items': GROUP}}}


def fingerprint(root):
    s = review.load_state(root)
    return review.digest({'system': s['system'], 'analysis': review.proof(root, s, 'analysis'),
                          'shots': [[q['id'], q['zh'], q['target']] for q in s['shots']]})


def load(root):
    return read_json(safe_path(root, STATE))


def content(state):
    return {k: state[k] for k in ('adapter', 'shared_references', 'groups', 'storyboard_fingerprint', 'compiled')}


def validate_plan(root, packet):
    try:
        schema_validate(packet, PLAN)
    except ValidationError as exc:
        raise ValueError('分组结构错误：' + exc.message) from exc
    state = review.load_state(root)
    flat = [sid for g in packet['groups'] for sid in g['shots']]
    if flat != [q['id'] for q in state['shots']]:
        raise ValueError('分组必须按原顺序连续覆盖全部镜头，不能漏镜、重复或跨镜重排')
    if len({g['id'] for g in packet['groups']}) != len(packet['groups']):
        raise ValueError('分组编号重复')
    for g in packet['groups']:
        refs = packet['shared_references'] + g['references']
        if len({r['key'] for r in refs}) != len(refs):
            raise ValueError('公共与组内素材 key 不得重复')
        for ref in refs:
            fields = {'key', 'kind', 'asset', 'version'} if ref['kind'] == 'image' else {'key', 'kind', 'index', 'item'}
            if set(ref) != fields:
                raise ValueError('图片引用需要 asset/version，预演视频需要 index/item')
            if ref['kind'] == 'video':
                safe_path(root, ref['index'])
    if any(r['kind'] != 'image' for r in packet['shared_references']):
        raise ValueError('当前公共素材只支持图片；预演视频按组绑定')


def persist(root, data, event):
    path = safe_path(root, STATE)
    if path.exists():
        old = load(root)
        history = safe_path(root, f"groups/history/v{old['revision']:04d}.json")
        write_json(history, old)
    write_json(path, data)
    m = load_project(root)
    paths = [STATE]
    if path.exists() and 'old' in locals():
        paths.append(history.relative_to(Path(root).resolve()).as_posix())
    for rel in paths:
        if not any(d['path'] == rel for d in m['documents']):
            m['documents'].append({'path': rel, 'role': 'handoff'})
    write_json(Path(root) / 'manifest.json', m)
    s = review.load_state(root)
    review.record(s, event, {'groups_revision': data['revision']})
    review.save(root, s)


def apply(root, packet):
    with review.locked(root):
        validate_plan(root, packet)
        review.expected(review.load_state(root), packet['project_revision'])
        old = load(root) if safe_path(root, STATE).exists() else None
        if packet['revision'] != (old['revision'] if old else 0):
            raise ValueError('分组版本冲突，请重新读取')
        data = {k: copy.deepcopy(packet[k]) for k in ('adapter', 'shared_references', 'groups')}
        data.update(schema_version=1, revision=packet['revision'] + 1,
                    storyboard_fingerprint=fingerprint(root), compiled={}, approval=None)
        persist(root, data, 'groups_plan_saved')
    return view(root)


def schedule(root, data):
    source = review.load_state(root)
    shots = {s['id']: s for s in source['shots']}
    original = {}; cursor = 0
    for s in source['shots']:
        duration = s['zh']['duration']
        if type(duration) not in (float, int) or not math.isfinite(duration) or duration <= 0:
            raise ValueError('分组需要完整、有效的分镜时长')
        original[s['id']] = cursor; cursor += duration
    result = []
    for g in data['groups']:
        local = 0; cuts = []
        for sid in g['shots']:
            q = shots[sid]
            cuts.append({'shot': sid, 'local_start': local, 'duration': q['zh']['duration'],
                         'original_start': original[sid], 'zh': q['zh'], 'target': q['target']})
            local += q['zh']['duration']
        result.append(dict(g, duration=local, cuts=cuts))
    return result


def slots(data, group):
    count = {'image': 0, 'video': 0}; result = []
    for common, refs in ((True, data['shared_references']), (False, group['references'])):
        for r in refs:
            count[r['kind']] += 1
            label = ('Picture' if r['kind'] == 'image' else 'Video') + ' ' + str(count[r['kind']])
            result.append(dict(r, slot=count[r['kind']], label='<' + label + '>', shared=common))
    return result


def request(root):
    data = load(root)
    return {'revision': data['revision'], 'project_revision': review.load_state(root)['revision'],
            'storyboard_fingerprint': fingerprint(root), 'adapter': data['adapter'],
            'groups': [dict(g, reference_slots=slots(data, g), previous=data['compiled'].get(g['id']))
                       for g in schedule(root, data)],
            'instructions': '按组内零起点与切镜时刻编译完整提示词及中文对照；保持台词、语气和衔接。素材未就绪是待绑定稿。'}


def timecode(seconds):
    milliseconds = round(seconds * 1000)
    minutes, rem = divmod(milliseconds, 60000)
    return f'{minutes:02d}:{rem//1000:02d}.{rem%1000:03d}'


def sync(root, packet):
    with review.locked(root):
        data = load(root)
        if set(packet) != {'revision', 'project_revision', 'storyboard_fingerprint', 'groups'}:
            raise ValueError('分组同步字段错误')
        review.expected(review.load_state(root), packet['project_revision'])
        if packet['revision'] != data['revision'] or packet['storyboard_fingerprint'] != fingerprint(root):
            raise ValueError('分组或分镜已改变，拒绝过期同步')
        # Refreshing a plan after source changes requires an explicit plan edit first.
        if data['storyboard_fingerprint'] != fingerprint(root):
            raise ValueError('原分镜已改变，请先重新保存分组方案')
        expected = {g['id']: g for g in schedule(root, data)}
        if len(packet['groups']) != len(expected) or {g['id'] for g in packet['groups']} != set(expected):
            raise ValueError('同步必须覆盖当前全部分组')
        compiled = {}
        for g in packet['groups']:
            if set(g) != {'id', 'text', 'translation_zh', 'check_note'} or any(not isinstance(g[k], str) or not g[k].strip() for k in ('text', 'translation_zh', 'check_note')):
                raise ValueError('每组需要完整原文、中文对照与实际检查说明')
            if data['adapter'] == 'aimixer-h3':
                for section in ('subject_definitions:', 'summary:', 'retention_analysis:', 'detailed_description:', 'overall_soundscape:', 'non_diegetic_music:'):
                    if section not in g['text']:
                        raise ValueError('H3 完整提示词缺少 ' + section)
                group = expected[g['id']]
                markers = re.findall(r'\[Shot (\d+)\]', g['text'])
                if markers != [str(i + 1) for i in range(len(group['cuts']))]:
                    raise ValueError('组内 Shot 编号必须从1顺序排列且与镜头数一致')
                for i, cut in enumerate(group['cuts'][1:], 2):
                    if f"[Shot {i}] At {timecode(cut['local_start'])}," not in g['text']:
                        raise ValueError('组内切镜时刻不符，不能沿用整集时间')
                valid = {r['label'] for r in slots(data, group)}
                used = set(re.findall(r'<(?:Picture|Video|Audio) \d+>', g['text']))
                if used - valid:
                    raise ValueError('提示词引用未绑定槽位：' + ', '.join(sorted(used - valid)))
            compiled[g['id']] = {k: g[k] for k in ('text', 'translation_zh', 'check_note')}
        data.update(compiled=compiled, revision=data['revision'] + 1, approval=None)
        persist(root, data, 'groups_synced')
    return view(root)


def planning_pending(root, data):
    result = []
    if data['storyboard_fingerprint'] != fingerprint(root): result.append('原分镜已改变，分组需复核并重新同步')
    if set(data['compiled']) != {g['id'] for g in data['groups']}: result.append('分组提示词与中文对照待同步')
    return result


def approved(root, data):
    return (not planning_pending(root, data) and bool(data['approval']) and
            data['approval']['fingerprint'] == review.digest(content(data)) and bool(data['approval']['evidence'].strip()))


def confirm(root, revision, project_revision, evidence):
    with review.locked(root):
        data = load(root)
        review.expected(review.load_state(root), project_revision)
        if data['revision'] != revision: raise ValueError('分组版本冲突')
        if not evidence.strip() or planning_pending(root, data): raise ValueError('分组尚未同步或缺少真实确认依据')
        s = review.load_state(root)
        if not all(review.is_approved(s, q) for q in s['shots']): raise ValueError('先确认各镜当前版本')
        data['approval'] = {'evidence': evidence, 'fingerprint': review.digest(content(data)), 'at': review.now()}
        data['revision'] += 1
        persist(root, data, 'groups_confirmed')
    return view(root)


def resolve(root, ref):
    """Return real, current files with provenance; draft callers retain unresolved slots."""
    import previs
    if ref['kind'] == 'image':
        assets = {a['id']: a for a in load_project(root)['assets']}
        asset = assets.get(ref['asset'])
        if not asset or asset['current_version'] != ref['version']:
            raise ValueError('资产不存在或版本已改变：' + ref['key'])
        v = current(asset)
        if not finished(v): raise ValueError('资产尚未完成检查与确认：' + ref['key'])
        path = safe_path(root, v['file'])
        from PIL import Image
        with Image.open(path) as im: im.verify()
        return {'path': v['file'], 'sha256': previs.sha(path)}
    index = safe_path(root, ref['index'])
    data = read_json(index)
    if data.get('type') == 'group_previs':
        from group_previs import verify
        verify(root, index)
        item = next((g for g in data['groups'] if g['id'] == ref['item']), None)
        if not item: raise ValueError('分组预演镜号缺失')
        path = safe_path(index.parent, item['reference'])
        return {'path': path.relative_to(Path(root).resolve()).as_posix(), 'sha256': previs.sha(path), 'seconds': item['seconds']}
    from previs_export import checked_bundle
    bundle = checked_bundle(root, safe_path(root, data['source_run']))
    if bundle['index'] != ref['index']: raise ValueError('预演引用不是当前导出版本')
    item = next((s for s in data['shots'] if s['shot'] == ref['item']), None)
    if not item: raise ValueError('逐镜预演镜号缺失')
    path = safe_path(index.parent, item['files']['camera'])
    return {'path': path.relative_to(Path(root).resolve()).as_posix(), 'sha256': previs.sha(path), 'seconds': item['duration']}


def view(root):
    if not safe_path(root, STATE).exists(): return None
    data = load(root)
    pending = planning_pending(root, data)
    try: timeline = schedule(root, data)
    except (ValueError, KeyError):
        timeline = []; pending.append('旧分组无法对应当前镜头，请重新保存方案')
    return dict(data, approved=approved(root, data), pending=pending, schedule=timeline)


def readiness(root):
    data = load(root)
    pending = planning_pending(root, data)
    if not approved(root, data): pending.append('分组待用户确认')
    rows = []
    for g in schedule(root, data):
        refs = []
        for ref in slots(data, g):
            try: refs.append(dict(ref, resolved=resolve(root, ref)))
            except (ValueError, OSError, KeyError) as exc:
                pending.append(g['id'] + ': ' + str(exc)); refs.append(dict(ref, resolved=None))
        if data['adapter'] == 'aimixer-h3':
            images = [r for r in refs if r['kind'] == 'image']; videos = [r for r in refs if r['kind'] == 'video']
            if not refs: pending.append(g['id'] + ': r2v 至少需要一项真实参考素材')
            if len(images) > 9 or len(videos) > 3 or len(refs) > 12: pending.append(g['id'] + ': 超出 H3 参考数量上限')
            seconds = [r['resolved']['seconds'] for r in videos if r['resolved']]
            if any(not 2 <= sec <= 15 for sec in seconds) or sum(seconds) > 15 + 1e-6:
                pending.append(g['id'] + ': 参考视频单段须2–15秒且合计不超过15秒')
        rows.append(dict(g, slots=refs))
    return {'ready': not pending, 'pending': pending, 'groups': rows, 'adapter': data['adapter']}
