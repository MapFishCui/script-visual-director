import argparse,json,sys
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent))
from component_kit import build,check_scene
args=argparse.ArgumentParser();args.add_argument('--spec',required=True);args.add_argument('--out',required=True)
a=args.parse_args(sys.argv[sys.argv.index('--')+1:]);out=Path(a.out);spec=json.loads(Path(a.spec).read_text())

if any(c.get('type') == 'actor' for c in spec['components']):
    raise ValueError('人物必须使用官网成品模型，禁止组件人物')
for component in spec['components']:
    if component['type']=='asset':component['file']=str((Path(__file__).resolve().parent/component['file']).resolve())
model=build(spec);report=check_scene(model)
(out/'model-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
bpy.context.scene.frame_set(spec.get('preview',{}).get('frame',1))
bpy.ops.wm.save_as_mainfile(filepath=str(out/'scene.blend'))
bpy.context.scene.render.filepath=str(out/'preview.png');bpy.ops.render.render(write_still=True)
print('MODEL_CHECK',report['status'],len(report['findings']))
