"""Deterministic Ref2VA framing; prose and translation remain director-authored.

Official contract: MiniMaxAI/MiniMax-H3 docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md.
This checks syntax, never cinematic quality or actual inference fidelity.
"""
import argparse
import json
import math
import re
from pathlib import Path

SECTIONS = ('subject_definitions', 'summary', 'retention_analysis',
            'detailed_description', 'overall_soundscape', 'non_diegetic_music')
HEADER = re.compile(r'^(' + '|'.join(SECTIONS) + r'):\s*', re.M)
SHOT = re.compile(r'\[Shot (\d+)\]')
REF = re.compile(r'<(?:Picture|Video|Audio) \d+>')


def is_h3(system):
    return 'h3' in (system.get('name', '') + ' ' + system.get('mode', '')).lower()


def timecode(seconds):
    ms = round(seconds * 1000)
    return f'{ms//60000:02d}:{ms//1000%60:02d}.{ms%1000:03d}'


def validate(text, cuts, labels=()):
    errors = []
    headers = list(HEADER.finditer(text))
    if [h.group(1) for h in headers] != list(SECTIONS):
        return ['H3六部分必须按官方顺序出现一次']
    sections = {h.group(1): text[h.end():headers[i+1].start() if i+1<len(headers) else len(text)].strip()
                for i,h in enumerate(headers)}
    if text[:headers[0].start()].strip() or any(not v for v in sections.values()):
        errors.append('H3章节不能为空或含未知前缀')
    body = sections['detailed_description']
    marks = list(SHOT.finditer(body))
    if [int(m.group(1)) for m in marks] != list(range(1,len(cuts)+1)):
        errors.append('H3正文镜号必须从1连续覆盖任务内镜头')
    for i,m in enumerate(marks):
        if i >= len(cuts): break
        tail = body[m.end():]
        if i == 0 and re.match(r'\s*At\s+\d', tail):
            errors.append('H3首镜不得带切点')
        elif i and not tail.startswith(' At '+timecode(cuts[i]['local_start'])+','):
            errors.append('H3切镜时刻必须匹配任务内时间')
    used = set(REF.findall(text))
    if used-set(labels): errors.append('H3存在未绑定槽位：'+', '.join(sorted(used-set(labels))))
    subjects = set(re.findall(r'<Subject \d+>', sections['subject_definitions']))
    if set(re.findall(r'<Subject \d+>',text))-subjects:
        errors.append('H3存在未定义人物引用')
    if text.count('<d>') != text.count('</d>'):
        errors.append('H3对白标签未闭合')
    for line in re.findall(r'<d>(.*?)</d>',text,re.S):
        if not re.fullmatch(r'\[[A-Za-z][A-Za-z -]*\]\s+[^<>]+',line):
            errors.append('H3对白必须包含语言标记和纯台词')
    stripped = re.sub(r'<d>.*?</d>|<Subject \d+>|<(?:Picture|Video|Audio) \d+>|<scenetrans>|<cutoff>', '',text,flags=re.S)
    if re.search(r'<[^>]*>',stripped): errors.append('H3含未知控制标签')
    # These are local clarity rules, NOT claims about official forbidden words.
    if 'the following view' in text.lower() or '切到以下画面' in text:
        errors.append('本地直白表达检查：切镜后直接描述具体取景，不用“以下画面”套话')
    return errors


def compile_task(spec):
    """Input: bilingual sections plus shots {duration,camera,scene,action}.
    action entries are bilingual prose or typed dialogue {speaker,language,text,
    delivery,voiceover}; quoted dialogue has a single canonical source string.
    """
    if spec.get('mode') != 'Ref2VA': raise ValueError('当前确定性编译器仅支持Ref2VA')
    shots = spec['shots']
    if not shots: raise ValueError('镜头不能为空')
    cuts=[]; cursor=0; en=[]; zh=[]
    for i,s in enumerate(shots):
        d=s['duration']
        if type(d) not in (int,float) or not math.isfinite(d) or d<=0: raise ValueError('镜头时长必须为正有限数')
        cuts.append({'local_start':cursor,'duration':d})
        prefix=f'[Shot {i+1}] '+('' if i==0 else 'At '+timecode(cursor)+', ')
        e=prefix+('' if i==0 else 'the camera cuts to ')+s['camera']['en']+' '+s['scene']['en']
        z=prefix+('' if i==0 else '镜头切到')+s['camera']['zh']+' '+s['scene']['zh']
        for a in s['action']:
            if 'text' not in a:
                e+=' '+a['en']; z+=' '+a['zh']; continue
            if re.search(r'[<>]',a['text']) or not a['text'].strip(): raise ValueError('台词不得包含控制标签或为空')
            if not re.fullmatch(r'S[1-9]\d*',a['speaker']): raise ValueError('发声者编号无效')
            if not re.fullmatch(r'[A-Za-z][A-Za-z -]*',a['language']): raise ValueError('语言标记无效')
            tag='<d>['+a['language']+'] '+a['text']+'</d>'
            voice=a.get('voiceover',False)
            e+=' '+a['delivery']['en']+' ('+a['speaker']+') '+('says in an off-screen voiceover: ' if voice else 'says: ')+tag
            if voice:e+=' while the corresponding on-screen character’s lips remain completely closed.'
            z+=' '+a['delivery']['zh']+'（'+a['speaker']+'）'+('内心／画外旁白：' if voice else '说：')+tag
            if voice:z+='画内对应人物嘴唇保持闭合。'
        en.append(e);zh.append(z);cursor+=d
    if not 4<=cursor<=15:raise ValueError('H3单任务时长须4–15秒；导演组合并时长不受此限制')
    result={}
    for key,lang,parts in [('text','en',en),('translation_zh','zh',zh)]:
        result[key]='\n\n'.join(k+':\n'+ ('\n'.join(parts) if k=='detailed_description' else spec['sections'][k][lang]) for k in SECTIONS)
    errors=validate(result['text'],cuts,spec.get('labels',[]))
    if errors:raise ValueError('; '.join(errors))
    result.update(duration=cursor,syntax_validated=True,target_h3_validated=False)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('input');p.add_argument('output');a=p.parse_args()
    try:
        result=compile_task(json.loads(Path(a.input).read_text()))
        Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    except (ValueError,KeyError,TypeError,OSError) as e:
        p.exit(2,str(e)+'\n')

if __name__=='__main__':main()
