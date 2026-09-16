"""Pack four checked character views without resizing; no image generation."""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageOps


def compose(front, back, left, head, output):
    paths = [Path(x).resolve() for x in (front, back, left, head)]
    out = Path(output).resolve()
    meta = out.with_suffix('.json')
    if out.suffix.lower() != '.png':
        raise ValueError('Output must be PNG')
    if out.exists() or meta.exists():
        raise ValueError('Use a new output version; output already exists')
    views = []
    for p in paths:
        with Image.open(p) as im:
            if im.mode not in ('RGB', 'RGBA', 'L', 'LA', 'P', '1'):
                raise ValueError('Provide 8-bit RGB/RGBA or grayscale input: ' + str(p))
            views.append(ImageOps.exif_transpose(im).convert('RGBA'))
    cw = max(im.width for im in views)
    ch = max(im.height for im in views)
    canvas = Image.new('RGBA', (2*cw, 2*ch), (255, 255, 255, 255))
    entries = []
    for i, (p, im, name) in enumerate(zip(paths, views, ['body_front', 'body_back', 'body_left', 'head_closeup'])):
        x = (i % 2)*cw + (cw-im.width)//2
        y = (i // 2)*ch + (ch-im.height)//2
        canvas.paste(im, (x,y))
        entries.append({'view':name, 'source':str(p), 'sha256':hashlib.sha256(p.read_bytes()).hexdigest(), 'box':[x,y,x+im.width,y+im.height], 'size':list(im.size)})
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('xb') as f:
        canvas.save(f, format='PNG')
    result = {'image':out.name, 'size':list(canvas.size), 'layout':'front,back / left,head', 'resized':False, 'views':entries, 'visual_review':'pending', 'target_h3_validated':False}
    with meta.open('x') as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('front','back','left','head','output'):
        parser.add_argument('--'+name, required=True)
    print(json.dumps(compose(**vars(parser.parse_args())),ensure_ascii=False))
