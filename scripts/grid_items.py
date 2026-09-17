"""Optional per-character/task approvals, with content-bound dependencies."""
import copy
import hashlib
import json
from pathlib import Path

from core import read_json, write_json, safe_path
from review import locked, now
import grid_workflow as grid


def signature(row):
    value = {k: row.get(k) for k in ('files', 'hashes', 'version', 'dependencies')}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def record(state, ref):
    stage, _, item = ref.partition('/')
    row = state['stages'].get(stage)
    return row.get('items', {}).get(item) if item and row else row


def condition(root, state, ref, seen=None):
    seen = set(seen or ())
    if ref in seen:
        return 'waiting_upstream'
    seen.add(ref)
    row = record(state, ref)
    if not row:
        return 'pending'
    if 'items' in row:
        values = [condition(root, state, ref + '/' + key, seen) for key in row['items']]
        for status in ('stale', 'waiting_upstream', 'needs_revision', 'awaiting_confirmation', 'pending'):
            if status in values:
                return status
        return 'confirmed' if values else 'pending'
    try:
        if row['hashes'] != grid.fingerprint(root, row['files']):
            return 'stale'
    except (ValueError, OSError):
        return 'stale'
    for dep, proof in row.get('dependencies', {}).items():
        other = record(state, dep)
        if not other or signature(other) != proof:
            return 'stale'
        if condition(root, state, dep, seen) != 'confirmed':
            return 'waiting_upstream'
    if row.get('needs_revision'):
        return 'needs_revision'
    return 'confirmed' if row.get('approval') else 'awaiting_confirmation'


def aggregate(row):
    row['files'] = sorted({p for item in row['items'].values() for p in item['files']})
    row['hashes'] = {p: h for item in row['items'].values() for p, h in item['hashes'].items()}
    row['approval'] = None
    row.pop('needs_revision', None)
    row.pop('feedback', None)


def change(root, command, stage, item, files=None, depends=None, evidence=None, _locked=False):
    from contextlib import nullcontext
    from grid_delivery import identifier
    identifier(item)
    if stage not in ('characters', 'grids', 'prompts'):
        raise ValueError('逐项操作仅用于人物、九宫格和提示词')
    root = Path(root).resolve()
    with (nullcontext() if _locked else locked(root)):
        state = read_json(root / 'grid-workflow.json')
        if state.get('workflow') != 'keyframe-grid-v1':
            raise ValueError('需要九宫格项目')
        previous = copy.deepcopy(state['stages'])
        row = state['stages'].setdefault(stage, {'files': [], 'hashes': {}, 'approval': None})
        if command == 'register-item':
            if not files or len(files) != len(set(files)):
                raise ValueError('需要非空且不重复的真实文件')
            if any(safe_path(root, p) in {root / 'grid-workflow.json', root / 'index.html'} for p in files):
                raise ValueError('状态文件和页面不能登记为素材')
            dependencies = ['director']
            if stage == 'characters':
                if depends:
                    raise ValueError('人物项不接受额外依赖')
            elif stage == 'grids':
                if not depends:
                    raise ValueError('九宫格需声明所用人物项；无人物使用 NONE 项')
                dependencies += ['characters/' + identifier(d) for d in depends]
            else:
                if depends and depends != [item]:
                    raise ValueError('提示词依赖同编号九宫格')
                dependencies += ['grids/' + item]
            if any(condition(root, state, ref) != 'confirmed' for ref in dependencies):
                raise ValueError('请先确认当前项的实际依赖')
            if 'items' not in row and row['files']:
                raise ValueError('阶段已有整体登记；请使用新项目逐项模式，不静默丢弃旧确认')
            items = row.setdefault('items', {})
            for key, other in items.items():
                if key != item and set(other['files']) & set(files):
                    raise ValueError('不同项不能共同拥有文件；通过依赖引用共享素材')
            items[item] = {'files': files, 'hashes': grid.fingerprint(root, files), 'version': items.get(item, {}).get('version', 0) + 1,
                           'dependencies': {ref: signature(record(state, ref)) for ref in dependencies}, 'approval': None}
        elif command in ('confirm-item', 'feedback-item'):
            if not isinstance(evidence, str) or not evidence.strip():
                raise ValueError('需要真实确认依据或修改意见')
            value = row.get('items', {}).get(item)
            if value is None:
                raise ValueError('项目尚未登记此项')
            if command == 'confirm-item':
                status = condition(root, state, stage + '/' + item)
                if status not in ('confirmed', 'awaiting_confirmation'):
                    raise ValueError('当前项不可确认：' + status)
                if status == 'confirmed':
                    return state
                value['approval'] = evidence.strip()
            else:
                value.update(approval=None, needs_revision=True, feedback=evidence.strip())
        else:
            raise ValueError('未知逐项操作')
        aggregate(row)
        state.setdefault('history', []).append({'at': now(), 'command': command, 'stage': stage, 'item': item, 'previous_stages': previous})
        write_json(root / 'grid-workflow.json', state)
        grid.page(root, state)
        return state
