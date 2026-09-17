"""Character bundles in the shared series library for grid projects."""
import copy
import hashlib
from pathlib import Path

from PIL import Image
from core import read_json, safe_path, write_json
import grid_workflow as grid
from grid_delivery import load_plan, VIEWS, identifier
from review import digest


def publish(project, library, episode, asset_ids):
    import series
    from grid_items import condition
    identifier(episode)
    if not asset_ids or len(set(asset_ids)) != len(asset_ids):
        raise ValueError('选择非空且不重复的人物编号')
    if Path(project).resolve() == Path(library).resolve():
        raise ValueError('共享库与项目必须分开')
    with series.locks(project, library):
        state = read_json(Path(project) / 'grid-workflow.json')
        plan = load_plan(project)
        if 'grid-delivery.json' not in state['stages'].get('director', {}).get('files', []):
            raise ValueError('请把交付清单登记到导演稿阶段')
        chars = {c['id']: c for c in plan['characters']}
        data = series.load(library)
        records = {r['id']: r for r in data['assets']}
        writes, output = {}, []
        for cid in asset_ids:
            identifier(cid)
            c = chars[cid]
            ref = 'characters/' + cid if 'items' in state['stages'].get('characters', {}) else 'characters'
            if condition(project, state, ref) != 'confirmed' or grid.status(project, state)['director'] != 'confirmed':
                raise ValueError(cid + ' 当前人物版本尚未确认')
            if type(c['version']) is not int or c['version'] < 1 or set(c['views']) != set(VIEWS) or len(set(c['views'].values())) != 5:
                raise ValueError('需要完整四视图与合图及确切版本')
            paths = {**c['views'], 'source': c['source']}
            row = state['stages']['characters']
            registered = row['items'][cid]['files'] if 'items' in row else row['files']
            if not set(paths.values()) <= set(registered):
                raise ValueError(cid + ' 存在未登记的人物素材')
            raw = {k: safe_path(project, name).read_bytes() for k, name in paths.items()}
            for key in VIEWS:
                with Image.open(safe_path(project, paths[key])) as image:
                    image.verify()
            if not raw['source'].decode('utf-8').strip():
                raise ValueError('人物来源记录不能为空')
            snapshot = {'kind': 'grid-character', 'source_episode': episode, 'character': copy.deepcopy(c),
                        'approval': copy.deepcopy(row['items'][cid] if 'items' in row else row),
                        'hashes': {k: hashlib.sha256(b).hexdigest() for k, b in raw.items()}}
            proof = digest(snapshot)
            record = records.get(cid)
            if record and record['type'] != 'character':
                raise ValueError('共享编号类型冲突：' + cid)
            existing = next((v for v in record['versions'] if v['fingerprint'] == proof), None) if record else None
            if existing:
                _read_bundle(library, existing)
                output.append({'id': cid, 'version': existing['version'], 'reused_snapshot': True})
                continue
            version = max((v['version'] for v in record['versions']), default=0) + 1 if record else 1
            files = {}
            for key, content in raw.items():
                rel = f'assets/{cid}/v{version:03d}/{key}' + Path(paths[key]).suffix.lower()
                if safe_path(library, rel).exists():
                    raise ValueError('共享版本文件已存在，拒绝覆盖')
                files[key] = rel; writes[rel] = content
            entry = {'version': version, 'file': files['sheet'], 'files': files, 'sha256': snapshot['hashes']['sheet'],
                     'fingerprint': proof, 'source_episode': episode, 'source_asset_version': c['version'], 'snapshot': snapshot}
            if record is None:
                record = {'id': cid, 'name': c.get('name', cid), 'type': 'character', 'versions': []}
                data['assets'].append(record); records[cid] = record
            record['versions'].append(entry)
            output.append({'id': cid, 'version': version, 'reused_snapshot': False})
        for rel, raw in writes.items():
            path = safe_path(library, rel); path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as stream:
                stream.write(raw)
        write_json(safe_path(library, series.INDEX), data)
    return {'library': data['name'], 'episode': episode, 'published': output}


def _read_bundle(library, entry):
    snapshot = entry['snapshot']
    if snapshot.get('kind') != 'grid-character':
        raise ValueError('此版本是旧流程单图；新流程需完整人物四视图与合图版本')
    if digest(snapshot) != entry['fingerprint']:
        raise ValueError('共享人物来源记录已改变')
    raw = {k: safe_path(library, name).read_bytes() for k, name in entry['files'].items()}
    if {k: hashlib.sha256(b).hexdigest() for k, b in raw.items()} != snapshot['hashes']:
        raise ValueError('共享人物文件已改变')
    return raw


def inherit(project, library, plan):
    import series
    import grid_items
    if set(plan) != {'episode', 'items'} or not isinstance(plan['items'], list) or not plan['items']:
        raise ValueError('继承方案需要 episode 与非空 items')
    identifier(plan['episode'])
    with series.locks(project, library):
        state = read_json(Path(project) / 'grid-workflow.json')
        if grid.status(project, state)['director'] != 'confirmed':
            raise ValueError('请先确认本集导演稿与交付清单')
        if state['stages'].get('characters', {}).get('files') and 'items' not in state['stages']['characters']:
            raise ValueError('自动继承用于人物逐项模式；整体登记的项目请手动登记')
        if 'grid-delivery.json' not in state['stages'].get('director', {}).get('files', []):
            raise ValueError('请把交付清单登记到导演稿阶段')
        characters = {c['id']: c for c in load_plan(project)['characters']}
        data = series.load(library); shared = {r['id']: r for r in data['assets']}
        writes, registrations, seen = {}, [], set()
        for item in plan['items']:
            if set(item) != {'source_id', 'version', 'target_id', 'continuity_note'}:
                raise ValueError('九宫格继承项需要 source_id/version/target_id/continuity_note')
            cid = identifier(item['target_id']); identifier(item['source_id'])
            if cid in seen or cid not in characters:
                raise ValueError('目标人物重复或不在本集清单中')
            seen.add(cid)
            if type(item['version']) is not int or item['version'] < 1 or not isinstance(item['continuity_note'], str) or not item['continuity_note'].strip():
                raise ValueError('需要确切共享版本与本集连续性说明')
            if cid in state['stages'].get('characters', {}).get('items', {}):
                raise ValueError('目标人物已有登记，不能覆盖')
            source = shared[item['source_id']]
            entry = next((v for v in source['versions'] if v['version'] == item['version']), None)
            if entry is None:
                raise ValueError('共享版本不存在')
            raw = _read_bundle(library, entry)
            c = characters[cid]
            if set(c['views']) != set(VIEWS):
                raise ValueError('本集清单须声明四视图和合图路径')
            paths = {**c['views'], 'source': c['source']}
            provenance = {'kind': 'grid-inheritance', 'library_id': data['id'], 'episode': plan['episode'],
                          'source_id': item['source_id'], 'library_version': entry['version'], 'continuity_note': item['continuity_note'],
                          'source_snapshot': entry['snapshot'], 'source_text': raw['source'].decode('utf-8'),
                          'files': {paths[k]: entry['snapshot']['hashes'][k] for k in VIEWS}}
            import json
            raw['source'] = (json.dumps(provenance, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
            for key, name in paths.items():
                if safe_path(project, name).exists() or name in writes:
                    raise ValueError('继承目标已存在或路径重复，拒绝覆盖：' + name)
                writes[name] = raw[key]
            registrations.append((cid, list(paths.values())))
        # Validate the whole batch before creating files or registering any character.
        for name, raw in writes.items():
            path = safe_path(project, name); path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as stream:
                stream.write(raw)
        for cid, files in registrations:
            grid_items.change(project, 'register-item', 'characters', cid, files, _locked=True)
    return {'episode': plan['episode'], 'inherited': [c for c, _ in registrations], 'needs_review': [c for c, _ in registrations]}


def verify(project):
    errors = []
    try:
        for c in load_plan(project)['characters']:
            source = safe_path(project, c['source'])
            if not source.is_file():
                continue
            text = source.read_text(encoding='utf-8')
            import json
            try:
                record = json.loads(text)
            except ValueError:
                continue
            if not isinstance(record, dict) or record.get('kind') != 'grid-inheritance':
                continue
            for name, proof in record['files'].items():
                if hashlib.sha256(safe_path(project, name).read_bytes()).hexdigest() != proof:
                    errors.append('继承文件已改变：' + name)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(str(exc))
    return {'ok': not errors, 'errors': errors}
