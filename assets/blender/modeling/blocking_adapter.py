"""Project-owned adapter. Component validation failure stops production rendering."""
import argparse,json,sys
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent))
from component_kit import build,check_scene
p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--smoke',action='store_true');p.add_argument('--render',action='store_true')
a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);base=Path(__file__).resolve().parent;out=Path(a.out)
out.mkdir(parents=True,exist_ok=False);spec=json.loads((base/'scene-spec.json').read_text());
for component in spec['components']:
    if component['type']=='asset':component['file']=str((Path(__file__).resolve().parent/component['file']).resolve())
model=build(spec)
checks=check_scene(model);(out/'model-check.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2))
bpy.context.scene.frame_set(1);bpy.ops.wm.save_as_mainfile(filepath=str(out/'critical-previs.blend'))
if checks['status'] not in ('passed','partial'):raise RuntimeError('组件几何检查失败；查看 model-check.json，修订动作或明确限定的接触容差')
frames=spec['frames'];fps=spec.get('fps',12);mapping=[];cursor=0
for beat in spec['beats']:
    for _ in range(round(beat['duration']*fps)):
        cursor+=1;mapping.append({'frame':cursor,'beat':beat['id'],'original_time':(cursor-1)/fps})
(out/'frame-map.json').write_text(json.dumps(mapping))
selected=list(range(1,frames+1)) if a.render else sorted({1,(frames+1)//2,frames}) if a.smoke else []
if selected:(out/'comparison').mkdir()
for frame in selected:
    bpy.context.scene.frame_set(frame);bpy.context.scene.render.filepath=str(out/'comparison'/f'{frame:06d}.png');bpy.ops.render.render(write_still=True)
report={'geometry_status':checks['status'],'imported_assets':checks.get('imported_assets',[]),'status':'video_rendered_awaiting_review' if a.render else 'smoke_frames_rendered_awaiting_review' if a.smoke else 'blend_built','rendered_frames':selected,'video':None}
(out/'render-report.json').write_text(json.dumps(report))
