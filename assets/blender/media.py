"""Run inside a fresh background Blender process; encode PNGs or inspect a movie."""
import json
from pathlib import Path
import sys


def process(request):
    import bpy
    if request['mode'] == 'batch':
        for item in request['items']:
            bpy.ops.wm.read_factory_settings(use_empty=True)
            process(item)
        Path(request['report']).write_text(json.dumps({'status':'encoded', 'count':len(request['items'])}), encoding='utf-8')
        return
    if request['mode']=='encode':
        directory=Path(request['directory']);output=Path(request['output'])
        if output.exists():raise ValueError('Refusing to overwrite video')
        paths=[directory/f'{i:06d}.png' for i in range(request.get('frame_start',1),request.get('frame_start',1)+request['frames'])]
        if any(not p.is_file() for p in paths):raise ValueError('Incomplete PNG sequence')
        image=bpy.data.images.load(str(paths[0]),check_existing=False)
        width,height=image.size[:];bpy.data.images.remove(image)
        scene=bpy.context.scene
        scene.render.resolution_x=width;scene.render.resolution_y=height;scene.render.resolution_percentage=100
        scene.render.fps=request['fps'];scene.frame_start=1;scene.frame_end=len(paths)
        scene.render.use_sequencer=True
        editor=scene.sequence_editor_create()
        strips=getattr(editor,'strips',None)
        if strips is None:strips=editor.sequences
        strip=strips.new_image('Comparison',str(paths[0]),channel=1,frame_start=1)
        for path in paths[1:]:strip.elements.append(path.name)
        strip.frame_final_duration=len(paths)
        # Blender 5.x splits media type from image/video format; older releases use FFMPEG.
        media_owner=next((owner for owner in (scene.render,scene.render.image_settings) if hasattr(owner,'media_type')),None)
        if media_owner is not None:
            media_owner.media_type='VIDEO'
        else:
            scene.render.image_settings.file_format='FFMPEG'
        scene.render.ffmpeg.format='MPEG4';scene.render.ffmpeg.codec='H264'
        scene.render.ffmpeg.constant_rate_factor='MEDIUM'
        scene.render.filepath=str(output)
        bpy.ops.render.render(animation=True,scene=scene.name)
        if not output.is_file() or output.stat().st_size<32:raise ValueError('Blender did not produce the requested MP4')
        clip=bpy.data.movieclips.load(str(output),check_existing=False)
        result={'status':'encoded','video':str(output),'frames':clip.frame_duration,'size':list(clip.size),'fps':clip.fps,'decoded':True}
        if result['frames'] != len(paths) or result['size'] != [width,height] or abs(result['fps']-request['fps']) > .01:
            raise ValueError('Encoded movie metadata differs from input frames')
    elif request['mode']=='inspect':
        clip=bpy.data.movieclips.load(request['video'],check_existing=False)
        result={'frames':clip.frame_duration,'size':list(clip.size),'fps':clip.fps,'status':'decoded_metadata'}
        if not all(result['size']) or result['frames']<1:raise ValueError('Movie decoder could not read the video')
    else:raise ValueError('Unknown media mode')
    result['blender_version']=bpy.app.version_string
    Path(request['report']).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')


def execute():
    args=sys.argv[sys.argv.index('--')+1:]
    process(json.loads(Path(args[0]).read_text(encoding='utf-8')))


if __name__=='__main__':execute()
