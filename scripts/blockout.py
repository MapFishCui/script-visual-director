"""Real, portable glTF geometry and deterministic camera previews; no image generation."""
from __future__ import annotations

import base64
import math
from pathlib import Path
import struct

from PIL import Image, ImageDraw, ImageFont
from core import write_json
from layout import font_path, spatial_checks, layout_fingerprint


def sub(a, b):
    return [x-y for x, y in zip(a, b)]


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def unit(a):
    length = math.sqrt(dot(a, a))
    if length < 1e-9:
        raise ValueError("Degenerate camera axis")
    return [x/length for x in a]


def world(p):
    # Layout: x right, y up on plan, z height. glTF: right-handed Y up.
    return [p[0], p[2], -p[1]]


def camera_axes(cam):
    pos = world(cam["position"])
    forward = unit(sub(world(cam["target"]), pos))
    up = [0, 1, 0] if abs(forward[1]) < .999 else [0, 0, 1]
    right = unit(cross(forward, up))
    up = unit(cross(right, forward))
    return pos, right, up, forward


VERTICES = [(-.5, -.5, -.5), (.5, -.5, -.5), (.5, .5, -.5), (-.5, .5, -.5),
            (-.5, -.5, .5), (.5, -.5, .5), (.5, .5, .5), (-.5, .5, .5)]
FACES = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 4, 7, 3), (1, 2, 6, 5), (0, 1, 5, 4), (3, 7, 6, 2)]


def box_vertices(box):
    angle = math.radians(box["rotation"])
    c, s = math.cos(angle), math.sin(angle)
    vertices = []
    for vx, vy, vz in VERTICES:
        x, y, z = vx*box["size"][0], vy*box["size"][1], vz*box["size"][2]
        vertices.append(world([box["center"][0]+x*c-y*s, box["center"][1]+x*s+y*c, box["center"][2]+z]))
    return vertices


def clip_near(poly, near=.05):
    out = []
    for a, b in zip(poly, poly[1:]+poly[:1]):
        inside_a, inside_b = a[2] >= near, b[2] >= near
        if inside_a:
            out.append(a)
        if inside_a != inside_b:
            t = (near-a[2])/(b[2]-a[2])
            out.append([a[i]+t*(b[i]-a[i]) for i in range(3)])
    return out


def render_preview(boxes, camera, output, font=None):
    width = 720
    height = max(240, min(1000, round(width/camera["aspect"])))
    image = Image.new("RGB", (width, height), "#e8edf2")
    pixels = image.load()
    depth = [float("inf")] * (width*height)
    pos, right, up, forward = camera_axes(camera)
    focal = height/(2*math.tan(math.radians(camera["yfov"])/2))

    def raster(triangle, shade):
        pts = [(width/2+focal*p[0]/p[2], height/2-focal*p[1]/p[2], p[2]) for p in triangle]
        a, b, c = pts
        den = (b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
        if abs(den) < 1e-8:
            return
        x0, x1 = max(0, math.floor(min(p[0] for p in pts))), min(width-1, math.ceil(max(p[0] for p in pts)))
        y0, y1 = max(0, math.floor(min(p[1] for p in pts))), min(height-1, math.ceil(max(p[1] for p in pts)))
        for y in range(y0, y1+1):
            for x in range(x0, x1+1):
                aa = ((b[1]-c[1])*(x+.5-c[0])+(c[0]-b[0])*(y+.5-c[1]))/den
                bb = ((c[1]-a[1])*(x+.5-c[0])+(a[0]-c[0])*(y+.5-c[1]))/den
                cc = 1-aa-bb
                if min(aa, bb, cc) >= -1e-8:
                    z = 1/(aa/a[2]+bb/b[2]+cc/c[2])
                    index = y*width+x
                    if z < depth[index]:
                        depth[index] = z
                        pixels[x, y] = shade
    for box in boxes:
        vertices = box_vertices(box)
        view = [[dot(sub(v, pos), right), dot(sub(v, pos), up), dot(sub(v, pos), forward)] for v in vertices]
        for face in FACES:
            normal = unit(cross(sub(vertices[face[1]], vertices[face[0]]), sub(vertices[face[2]], vertices[face[0]])))
            brightness = int(160+65*abs(dot(normal, unit([.4, 1, .3]))))
            shade = (brightness, brightness, brightness)
            poly = clip_near([view[i] for i in face])
            for i in range(1, len(poly)-1):
                raster([poly[0], poly[i], poly[i+1]], shade)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width, 38), fill="#23334a")
    draw.text((12, 8), f"{camera['id']} · {camera['shot']} · 几何预览 / 待人工检查", font=ImageFont.truetype(font_path(font), 16), fill="white")
    image.save(output)


def build_blockout(data, out, font=None):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    dest = out / "scene.gltf"
    if dest.exists():
        raise ValueError("Blockout already exists; use a new versioned output directory")
    # Use explicit mesh vertices per object. No binary sidecar or external URL required.
    floor = {"id": "FLOOR", "label": "floor", "kind": "floor", "center": [data["extent"][0]/2, data["extent"][1]/2, -.06],
             "size": [data["extent"][0], data["extent"][1], .1], "rotation": 0}
    boxes = [floor]+data["boxes"]
    blob, accessors, views, meshes, nodes = bytearray(), [], [], [], []
    def accessor(values, components, component_type, kind):
        offset = len(blob)
        fmt = "f" if component_type == 5126 else "H"
        flat = [v for row in values for v in row] if components > 1 else values
        blob.extend(struct.pack("<"+fmt*len(flat), *flat))
        length = len(blob)-offset
        while len(blob) % 4:
            blob.append(0)
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": length, "target": 34962 if components > 1 else 34963})
        acc = {"bufferView": len(views)-1, "componentType": component_type, "count": len(values), "type": kind}
        if components > 1:
            acc.update(min=[min(row[i] for row in values) for i in range(components)], max=[max(row[i] for row in values) for i in range(components)])
        accessors.append(acc)
        return len(accessors)-1
    for box in boxes:
        vertices = box_vertices(box)
        positions, normals, indices = [], [], []
        for face in FACES:
            # Layout-to-glTF transform has determinant +1, so preserve winding.
            normal = unit(cross(sub(vertices[face[1]], vertices[face[0]]), sub(vertices[face[2]], vertices[face[0]])))
            start = len(positions)
            positions.extend(vertices[i] for i in face)
            normals.extend([normal]*4)
            indices.extend([start, start+1, start+2, start, start+2, start+3])
        p = accessor(positions, 3, 5126, "VEC3")
        n = accessor(normals, 3, 5126, "VEC3")
        idx = accessor(indices, 1, 5123, "SCALAR")
        meshes.append({"name": box["id"], "primitives": [{"attributes": {"POSITION": p, "NORMAL": n}, "indices": idx, "material": 0}]})
        nodes.append({"name": box["id"]+" "+box["label"], "mesh": len(meshes)-1, "extras": {"layout_box": box}})
    cameras = []
    for camera in data["cameras"]:
        pos, right, up, forward = camera_axes(camera)
        matrix = right+[0]+up+[0]+[-v for v in forward]+[0]+pos+[1]
        cameras.append({"name": camera["id"], "type": "perspective", "perspective": {"yfov": math.radians(camera["yfov"]), "aspectRatio": camera["aspect"], "znear": .05}})
        nodes.append({"name": camera["id"], "camera": len(cameras)-1, "matrix": matrix,
                      "extras": {"shot": camera["shot"], "path_layout_coordinates": camera["path"]}})
    model = {"asset": {"version": "2.0", "generator": "script-visual-director"}, "scene": 0,
             "scenes": [{"nodes": list(range(len(nodes)))}], "nodes": nodes, "meshes": meshes,
             "materials": [{"name": "White blockout", "doubleSided": True, "pbrMetallicRoughness": {"baseColorFactor": [.8, .8, .8, 1], "metallicFactor": 0, "roughnessFactor": .9}}],
             "buffers": [{"byteLength": len(blob), "uri": "data:application/octet-stream;base64,"+base64.b64encode(blob).decode()}],
             "bufferViews": views, "accessors": accessors,
             "extras": {"layout_id": data["id"], "layout_version": data["version"], "fingerprint": layout_fingerprint(data), "units": "m", "coordinate_mapping": "layout(x,y,z) -> glTF(x,z,-y)", "review_status": "pending"}}
    if cameras:
        model["cameras"] = cameras
    write_json(dest, model)
    files = [str(dest)]
    for camera in data["cameras"]:
        target = out / f"{camera['id']}.png"
        render_preview(boxes, camera, target, font)
        files.append(str(target))
    report = spatial_checks(data)
    report["scope"] += " 白模为长方体近似；预览采用 CPU 深度缓冲，运镜路径保存为元数据而非动画。"
    write_json(out / "blockout-check.json", report)
    files.append(str(out / "blockout-check.json"))
    return {"files": files, "checks": report}
