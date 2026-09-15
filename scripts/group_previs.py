"""Assemble available contiguous shots into group previews without changing timing."""
from pathlib import Path
import datetime
import uuid
import groups
import previs
import previs_export
import review
from core import read_json, safe_path, write_json


def plan_proof(root):
    state = groups.load(root)
    return review.digest({**({'director_groups': [{'id':g['id'],'tasks':g['tasks']} for g in state['director_groups']]} if state.get('director_groups') else {}), 'source': groups.fingerprint(root),
                          'groups': [{'id': g['id'], 'shots': g['shots']} for g in state['groups']]})


def verify(root, index):
    root = Path(root).resolve()
    data = read_json(index)
    if data['plan_proof'] != plan_proof(root): raise ValueError('分组预演已因分镜或分组改变而失效')
    bundle = previs_export.checked_bundle(root, safe_path(root, data['source_run']))
    if bundle != data['source_bundle']: raise ValueError('分组预演使用的逐镜来源已改变')
    for path, expected in data['sha256'].items():
        if previs.sha(safe_path(root, path)) != expected: raise ValueError('分组预演文件已改变')
    return data


def build(root, source_index, explicit=None):
    root = Path(root).resolve(); state = groups.load(root)
    if state['storyboard_fingerprint'] != groups.fingerprint(root): raise ValueError('先更新过期分组')
    violations = groups.plan_limits(root, state)
    if violations: raise ValueError('; '.join(violations))
    proof = plan_proof(root)
    source = read_json(safe_path(root, source_index))
    folder = safe_path(root, source['source_run'])
    bundle = previs_export.checked_bundle(root, folder)
    if bundle['index'] != source_index: raise ValueError('必须使用当前逐镜导出')
    clips = {s['shot']: s for s in source['shots']}
    dest = safe_path(root, 'previs/groups/' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S_') + uuid.uuid4().hex[:8])
    dest.mkdir(parents=True)
    items = []; rows = []; missing = []
    timeline=[dict(g,level='task') for g in groups.schedule(root,state)]+[dict(g,level='director') for g in groups.director_schedule(root,state)]
    for group in timeline:
        absent = [sid for sid in group['shots'] if sid not in clips]
        if absent:
            missing.append({'id': group['id'], 'level':group['level'], 'missing_shots': absent}); continue
        selected = [clips[s] for s in group['shots']]
        start = selected[0]['frame_start']; count = sum(s['frames'] for s in selected)
        if selected[-1]['frame_start'] + selected[-1]['frames'] != start + count:
            raise ValueError('组内逐镜源帧不连续，拒绝拼入额外镜头')
        base = safe_path(dest, group['id']); base.mkdir()
        row = {'id': group['id'], 'level': group['level'], 'input_candidate':group['level']=='task', 'shots': group['shots'], 'seconds': count/source['fps'],
               'review': group['id'] + '/review.mp4', 'reference': group['id'] + '/reference.mp4'}
        for kind, filename in [('comparison', 'review'), ('camera', 'reference')]:
            items.append({'mode': 'encode', 'directory': str(folder/'output'/kind), 'frame_start': start,
                          'frames': count, 'fps': source['fps'], 'output': str(base/(filename+'.mp4')),
                          'report': str(base/(filename+'.metadata.json'))})
        rows.append(row)
    if items:
        request = dest/'request.json'
        write_json(request, {'mode':'batch', 'items':items, 'report':str(dest/'batch.json')})
        previs.invoke(previs.blender_path(explicit), previs.MEDIA, [str(request)], dest/'encode.log')
    hashes = {}
    for item in items:
        meta = read_json(item['report']); kind = 'camera' if 'reference' in item['output'] else 'comparison'
        if (meta.get('decoded') is not True or meta['frames'] != item['frames'] or
                meta['size'] != source['sizes'][kind] or abs(meta['fps']-source['fps']) > .01):
            raise ValueError('分组预演实际解码校验失败')
        for name in ('output','report'):
            path = Path(item[name]); hashes[path.relative_to(root).as_posix()] = previs.sha(path)
    data = {'type':'group_previs', 'status':'generated_pending_review', 'plan_proof':proof,
            'source_run':source['source_run'], 'source_bundle':bundle,
            'groups':rows, 'missing_groups':missing, 'sha256':hashes, 'target_validated':False}
    index = dest/'index.json'; write_json(index,data)
    with review.locked(root):
        verify(root,index)
        lines = ['# 视频段与导演组预演', '', '任务预演用于逐次参考；导演组合并预演用于整体节奏审阅，不作为单次H3输入。待人工检查；未补造缺失镜头，未做模型推理。', '']
        for row in rows:
            lines.append(f"- {row['id']} · {row['level']} · {row['seconds']:g}秒 · {'、'.join(row['shots'])}：[审核版]({row['review']}) / [纯摄影机参考候选]({row['reference']})")
        for row in missing: lines.append(f"- {row['id']} 未生成：缺少 {'、'.join(row['missing_shots'])}")
        doc=dest/'README.md'; doc.write_text('\n'.join(lines)+'\n', encoding='utf-8')
        previs.documents(root,[index,doc]+[safe_path(root,p) for p in hashes])
        s=review.load_state(root); review.record(s,'group_previs_exported',{'index':index.relative_to(root).as_posix()}); review.save(root,s)
    return {'index':index.relative_to(root).as_posix(),'generated_groups':sum(g['level']=='task' for g in rows),'generated_director_groups':sum(g['level']=='director' for g in rows),'missing_groups':missing}
