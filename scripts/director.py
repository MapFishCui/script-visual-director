"""Director completeness checks and revision-bound editorial review; no model calls."""
from __future__ import annotations

import copy
import re

from core import indexed, safe_path

VERSION = 2
CHECKS = ('narrative', 'character', 'performance', 'pacing', 'continuity', 'adaptation', 'standards')
LABELS = {'purpose': '叙事目的', 'description': '画面描述', 'framing': '景别与机位',
          'action': '动作起止', 'camera': '运镜', 'dialogue': '台词与文字',
          'continuity': '镜头衔接', 'psychology': '人物心理', 'performance': '可见表演',
          'delivery': '逐句台词语气', 'rhythm': '节奏安排'}


def inspect(shot):
    """Only objective omissions block here. Semantic hints require editorial judgment."""
    zh = shot['zh']
    errors = [f'缺少{label}' for key, label in LABELS.items() if not zh.get(key, '').strip()]
    if zh.get('duration') is None:
        errors.append('缺少时长提案')
    warnings = []
    if re.search(r'或|待选|二选一|\bor\b', zh.get('camera', ''), re.I):
        warnings.append('运镜可能含未定选项；确认一种方案，或在导演检查中解释此提示为何不适用。')
    if re.search(r'遵循.*(?:camera-plan|spatial-plan)', zh.get('continuity', ''), re.I):
        warnings.append('衔接仅指向外部文档，需核对本镜起止状态与相邻镜头。')
    if re.search(r'时长.{0,8}待|朗读.{0,6}待|未.{0,3}(?:估时|核对)', zh.get('rhythm', '')):
        warnings.append('节奏仍有待办，须说明台词、反应与阅读时间是否足够。')
    findings = []
    # These are explicit local wording rules, not a claim to validate all H3 semantics.
    vague = {'留足后退空间': '写出取景范围，以及人物后退后是否仍在画内。',
             '留足边缘': '说明完整物件及哪些边缘需要出现在画面内。',
             '留一拍': '写出停顿动作或已确定的时长。',
             '视线将回': '写出开始低头、转头等可见动作。',
             '承载时间证据': '写明时钟位置、数字及是否清晰可读。',
             '保留视线空间': '写出人物面向哪里，以及画面包括什么。',
             '接受事实': '心理判断移至内部依据；正文写人物的动作和声音。',
             '相容的视线轴': '明确摄影机在柜台哪一侧、人物面向谁。'}
    for field in ('description', 'camera', 'action'):
        for phrase, suggestion in vague.items():
            if phrase in zh.get(field, ''):
                findings.append({'rule': 'plain-language', 'field': field,
                                 'excerpt': zh[field], 'suggestion': suggestion})
    translated = shot.get('target', {}).get('translation_zh', '')
    camera, action = translated.find('镜头运动：'), translated.find('人物运动：')
    if camera >= 0 and action >= 0 and camera > action:
        findings.append({'rule': 'camera-before-action', 'field': 'translation_zh',
                         'excerpt': translated, 'suggestion': '中文对照先写镜头，再写动作，并核对系统原文相同关系。'})
    for finding in findings:
        errors.append('规范待修订 [' + finding['rule'] + ']：' + finding['suggestion'])
    return {'errors': errors, 'warnings': warnings, 'findings': findings}


def signature(state):
    import review
    context = {'version': VERSION, 'system': state['system'],
               'shots': [[s['id'], s['revision'], s['zh'], s['target']] for s in state['shots']]}
    if state.get('workflow') == 'layout-first-v1': context['spatial_context'] = review.spatial_context(state)
    return review.digest(context)


def ready(state, shot, context_hash=None, analysis_hash=None):
    rec = shot.get('director_review') or {}
    if analysis_hash is None:
        analysis_hash = (state['stages']['analysis'] or {}).get('fingerprint')
    checks = rec.get('checks', {})
    return bool(not inspect(shot)['errors'] and rec.get('version') == VERSION
                and rec.get('context_hash') == (context_hash or signature(state))
                and rec.get('analysis_hash') == analysis_hash and analysis_hash
                and rec.get('sequence_note', '').strip()
                and set(checks) == set(CHECKS)
                and checks.get('standards', {}).get('status') == 'pass'
                and all(c.get('status') in ('pass', 'not_applicable') and c.get('note', '').strip()
                        for c in checks.values()))


def report(root, state=None):
    import review
    state = state or review.load_state(root)
    context_hash = signature(state)
    analysis_hash = review.proof(root, state, 'analysis')
    rows = []
    for shot in state['shots']:
        row = {'id': shot['id'], **inspect(shot)}
        row['ready'] = ready(state, shot, context_hash, analysis_hash)
        rec = shot.get('director_review')
        row['review_status'] = ('missing' if not rec else 'stale' if
            rec.get('context_hash') != context_hash or rec.get('analysis_hash') != analysis_hash
            else 'passed' if row['ready'] else 'needs_revision')
        row['review'] = rec
        rows.append(row)
    return {'project_revision': state['revision'], 'context_hash': context_hash, 'analysis_hash': analysis_hash,
            'ready': all(r['ready'] for r in rows), 'shots': rows,
            'scope': '七项人工审阅：叙事、人物、表演语气、节奏、连续性、目标适配、写作规范。自动检查仅覆盖字段和已知违规表述；通过不代表H3推理或空间执行验证。',
            'context': [{'id': s['id'], 'zh': s['zh'], 'target': s['target']} for s in state['shots']],
            'system': state['system'],
            'analysis': [{'path': p, 'text': safe_path(root, p).read_text(encoding='utf-8')}
                         for p in dict.fromkeys([d['path'] for d in review.load_project(root)['documents']
                                                if d['role'] == 'source'] + state['analysis_files'])]}


def apply(root, packet):
    import review
    with review.locked(root):
        state = review.load_state(root)
        if set(packet) != {'project_revision', 'context_hash', 'analysis_hash', 'sequence_note', 'shots'}:
            raise ValueError('导演检查需要项目版本、上下文指纹、分析指纹、全段节奏说明与逐镜检查')
        review.expected(state, packet['project_revision'])
        if packet['context_hash'] != signature(state) or packet['analysis_hash'] != review.proof(root, state, 'analysis'):
            raise ValueError('导演检查已过期：剧情或分镜上下文发生变化，请重新检查')
        if not isinstance(packet['sequence_note'], str) or not packet['sequence_note'].strip():
            raise ValueError('需要全段节奏与人物变化的具体检查说明')
        updates = packet['shots']
        if not isinstance(updates, list) or not updates or any(not isinstance(u, dict) for u in updates):
            raise ValueError('需要非空逐镜检查列表')
        if len({u.get('id') for u in updates}) != len(updates):
            raise ValueError('镜头检查不可重复')
        table = indexed(state['shots'])
        for u in updates:
            if set(u) != {'id', 'checks'} or u['id'] not in table or not isinstance(u['checks'], dict) or set(u['checks']) != set(CHECKS):
                raise ValueError('逐镜检查需要有效镜号及全部七项检查')
            for c in u['checks'].values():
                if not isinstance(c, dict) or set(c) != {'status', 'note'} or c['status'] not in ('pass', 'revise', 'not_applicable') or not isinstance(c['note'], str) or not c['note'].strip():
                    raise ValueError('每项检查需要 pass/revise/not_applicable 和具体依据')
            if u['checks']['standards']['status'] == 'not_applicable':
                raise ValueError('写作规范必须实际检查，不能标记不适用')
            if not review.is_synced(state, table[u['id']]):
                raise ValueError('先同步当前中文、系统原文和中文对照，再做导演检查')
            if inspect(table[u['id']])['errors'] and all(c['status'] != 'revise' for c in u['checks'].values()):
                raise ValueError('导演稿字段未完整或规范未通过，不能记录为通过')
        for u in updates:
            shot = table[u['id']]
            shot['history'].append({'at': review.now(), 'event': 'director_review',
                                    'snapshot': copy.deepcopy({k: shot.get(k) for k in ('revision', 'zh', 'target', 'approval', 'director_review')})})
            shot['director_review'] = {'version': VERSION, 'context_hash': packet['context_hash'],
                'analysis_hash': packet['analysis_hash'], 'sequence_note': packet['sequence_note'],
                'checks': copy.deepcopy(u['checks']), 'at': review.now()}
            shot['approval'] = None
        if state.get('workflow') != 'layout-first-v1': state['stages']['layout'] = None
        state['stages']['previs'] = None
        review.record(state, 'director_review', [u['id'] for u in updates])
        review.save(root, state)
        return state
