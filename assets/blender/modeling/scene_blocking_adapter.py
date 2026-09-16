"""Bridge the scene executor into the existing blocking runner and review lifecycle."""
import argparse,json,shutil,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from scene_executor import run
p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--smoke',action='store_true');p.add_argument('--render',action='store_true')
a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);base=Path(__file__).resolve().parent;out=Path(a.out);out.mkdir(parents=True,exist_ok=False)
plan=json.loads((base/'execution-plan.json').read_text())
for c in plan['scene']['components']:
    if c['type']=='asset':c['file']=str((base/c['file']).resolve())
report=run(plan,out,a.render);shutil.copy2(out/'scene.blend',out/'critical-previs.blend')
(out/'model-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
if report['status']=='failed':raise RuntimeError('场面执行检查失败，查看 execution-report.json')
comparison=out/'comparison';comparison.mkdir();frames=plan['scene']['frames']
selected=range(1,frames+1) if a.render else sorted({1,frames//2,frames})
for f in selected:shutil.copy2(out/'frames'/f'{f:06}.png' if a.render else out/f'diagnostic-{f:06}.png',comparison/f'{f:06}.png')
(out/'frame-map.json').write_text(json.dumps([{'frame':f,'beat':'scene','original_time':(f-1)/plan['fps']} for f in range(1,frames+1)]))
(out/'render-report.json').write_text(json.dumps({'status':'video_rendered_awaiting_review' if a.render else 'smoke_frames_rendered_awaiting_review','geometry_status':report['status'],'rendered_frames':list(selected),'video':None}))
