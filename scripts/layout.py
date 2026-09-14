from __future__ import annotations

import math
import os
import hashlib
import json
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw, ImageFont
from core import indexed, read_json, write_json
from schema import LAYOUT, check


def load_layout(path):
    data = read_json(path)
    check(data, LAYOUT)
    ids = [x for key in ("boxes", "cameras", "paths") for x in data[key]]
    indexed(ids)
    for camera in data["cameras"]:
        if math.dist(camera["position"], camera["target"]) < 1e-6:
            raise ValueError(f"Camera position equals target: {camera['id']}")
    return data


def layout_fingerprint(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def corners(box):
    cx, cy, _ = box["center"]
    w, d, _ = box["size"]
    angle = math.radians(box["rotation"])
    c, s = math.cos(angle), math.sin(angle)
    return [(cx + x*c - y*s, cy + x*s + y*c) for x, y in [(-w/2, -d/2), (w/2, -d/2), (w/2, d/2), (-w/2, d/2)]]


def segment_box(a, b, box, radius=0, above=0, below=0):
    """Continuous segment/rotated-box intersection, returning entering t or None."""
    angle = math.radians(-box["rotation"])
    c, s = math.cos(angle), math.sin(angle)
    def local(p):
        x, y, z = [p[i]-box["center"][i] for i in range(3)]
        return (x*c-y*s, x*s+y*c, z)
    start, end = local(a), local(b)
    half = [v/2 for v in box["size"]]
    lo = [-half[0]-radius, -half[1]-radius, -half[2]-above]
    hi = [half[0]+radius, half[1]+radius, half[2]+below]
    enter, leave = 0., 1.
    for axis in range(3):
        delta = end[axis] - start[axis]
        if abs(delta) < 1e-10:
            if start[axis] < lo[axis] or start[axis] > hi[axis]:
                return None
        else:
            t1, t2 = (lo[axis]-start[axis])/delta, (hi[axis]-start[axis])/delta
            enter, leave = max(enter, min(t1, t2)), min(leave, max(t1, t2))
            if enter > leave:
                return None
    return enter


def spatial_checks(data):
    issues = []
    solids = [b for b in data["boxes"] if b["solid"] and b["kind"] != "actor"]
    paths = [(p["id"], p["points"], p["clearance"], 1.7, 0, p["actor"]) for p in data["paths"]]
    for cam in data["cameras"]:
        points = [cam["position"]] + cam["path"]
        if len(points) == 1:
            points.append(points[0])
        paths.append((cam["id"], points, .08, .08, .08, None))
        hits = [(b["id"], segment_box(cam["position"], cam["target"], b)) for b in solids]
        hits = [(key, t) for key, t in hits if t is not None and t < .995]
        if hits:
            key, _ = min(hits, key=lambda x: x[1])
            issues.append({"kind": "sightline", "id": cam["id"], "obstacle": key,
                           "note": "目标点前存在实体；人工检查是否为预期遮挡。"})
    for key, points, radius, above, below, actor in paths:
        for a, b in zip(points, points[1:]):
            if any(p[0] < 0 or p[1] < 0 or p[0] > data["extent"][0] or p[1] > data["extent"][1] for p in (a, b)):
                issues.append({"kind": "outside_extent", "id": key, "note": "路径超出布局范围，需核对相邻空间。"})
            for box in solids:
                if box["id"] != actor and segment_box(a, b, box, radius, above, below) is not None:
                    issues.append({"kind": "collision", "id": key, "obstacle": box["id"], "note": "路径与占位实体相交。"})
    unique = {str(sorted(x.items())): x for x in issues}
    return {"layout_id": data["id"], "layout_version": data["version"],
            "geometry_status": "needs_revision" if unique else "passed", "review_status": "pending",
            "scope": "旋转长方体碰撞、路径范围、机位至目标点的线段遮挡；不判断叙事、画面可读性和真实物体形状。",
            "assumptions": ["人物路径按脚底位置、身高 1.7m 检查；水平余量取各路径 clearance。", "摄像机半径按 0.08m 检查。"],
            "issues": list(unique.values())}


def font_path(explicit=None):
    candidates = [explicit, os.environ.get("SVD_FONT"), "/System/Library/Fonts/STHeiti Medium.ttc",
                  "/System/Library/Fonts/PingFang.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                  "C:/Windows/Fonts/msyh.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise ValueError("No suitable font found; set SVD_FONT or pass --font with a CJK-capable font")


class Canvas:
    """Draw the same primitives to editable SVG and raster PNG."""
    def __init__(self, width, height, font=None):
        self.width, self.height = width, height
        self.font = font_path(font)
        self.image = Image.new("RGB", (width, height), "#f6f8fb")
        self.draw = ImageDraw.Draw(self.image)
        self.svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
                    '<rect width="100%" height="100%" fill="#f6f8fb"/>']

    def polygon(self, points, fill, stroke="#23334a", width=2):
        self.draw.polygon(points, fill=fill)
        if stroke:
            self.draw.line(points+[points[0]], fill=stroke, width=width)
        coords = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
        self.svg.append(f'<polygon points="{coords}" fill="{fill}" stroke="{stroke or "none"}" stroke-width="{width}"/>')

    def line(self, points, color, width=2):
        if len(points) < 2:
            return
        self.draw.line(points, fill=color, width=width)
        coords = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
        self.svg.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="{width}"/>')

    def arrow(self, a, b, color, width=3):
        self.line([a, b], color, width)
        angle = math.atan2(b[1]-a[1], b[0]-a[0])
        pts = [b]+[(b[0]-12*math.cos(angle+off), b[1]-12*math.sin(angle+off)) for off in (-.45, .45)]
        self.polygon(pts, color, color, 1)

    def circle(self, center, radius, color):
        x, y = center
        self.draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=color)
        self.svg.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{radius}" fill="{color}"/>')

    def text(self, pos, value, size=16, color="#23334a"):
        self.draw.text(pos, str(value), font=ImageFont.truetype(self.font, size), fill=color)
        x, y = pos
        self.svg.append(f'<text x="{x:.2f}" y="{y+size:.2f}" font-family="Noto Sans CJK SC,Heiti SC,Microsoft YaHei,sans-serif" font-size="{size}" fill="{color}">{escape(str(value))}</text>')

    def save(self, stem):
        stem = Path(stem)
        stem.parent.mkdir(parents=True, exist_ok=True)
        stem.with_suffix(".svg").write_text("\n".join(self.svg+["</svg>"]), encoding="utf-8")
        self.image.save(stem.with_suffix(".png"))


COLORS = {"wall": "#475569", "furniture": "#d9e2ec", "prop": "#ffdf88", "door": "#c3eadb",
          "window": "#a9dff3", "actor": "#f7bfa1", "light": "#fff2b4"}


def render_layout(data, out, font=None):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    # Content fingerprint detects edits made without incrementing the layout version.
    fingerprint = layout_fingerprint(data)
    marker = out / "render-record.json"
    if marker.exists() and read_json(marker).get("fingerprint") != fingerprint:
        raise ValueError("Output belongs to another layout; use a new versioned output directory")
    files = []
    for camera in [None]+data["cameras"]:
        canvas = Canvas(1280, max(960, 320+len(data["boxes"])*49), font)
        canvas.text((40, 26), data["name"], 30)
        subtitle = f"{data['id']} · v{data['version']} · 单位 m · " + (f"{camera['shot']} / {camera['id']}" if camera else "基础布局")
        canvas.text((42, 72), subtitle, 17, "#60738a")
        scale = min(820/data["extent"][0], 680/data["extent"][1])
        origin = (76, 816)
        def xy(point):
            return origin[0]+point[0]*scale, origin[1]-point[1]*scale
        w, d = data["extent"]
        canvas.polygon([xy((0, 0)), xy((w, 0)), xy((w, d)), xy((0, d))], "#ffffff", "#c3cfdf")
        for x in range(int(w)+1):
            canvas.line([xy((x, 0)), xy((x, d))], "#e8eef4", 1)
            canvas.text((xy((x, 0))[0]-5, 828), str(x), 13, "#6a7d93")
        for y in range(int(d)+1):
            canvas.line([xy((0, y)), xy((w, y))], "#e8eef4", 1)
            canvas.text((42, xy((0, y))[1]-9), str(y), 13, "#6a7d93")
        for box in sorted(data["boxes"], key=lambda b: b["center"][2]):
            points = [xy(p) for p in corners(box)]
            canvas.polygon(points, COLORS[box["kind"]], "#60738a", 2)
            p = xy(box["center"])
            if box["size"][0]*scale > 55 and box["size"][1]*scale > 20:
                canvas.text((min(q[0] for q in points)+8, min(q[1] for q in points)+6), box["id"], 13)
        if camera:
            pos, target = xy(camera["position"]), xy(camera["target"])
            canvas.arrow(pos, target, "#2070b4", 3)
            canvas.circle(pos, 5, "#2070b4")
            canvas.text((pos[0]+10, pos[1]-25), camera["id"], 16, "#2070b4")
            route = [pos]+[xy(p) for p in camera["path"]]
            for a, b in zip(route, route[1:]):
                canvas.arrow(a, b, "#8756bb", 3)
            for path in data["paths"]:
                if path["shot"] == camera["shot"]:
                    route = [xy(p) for p in path["points"]]
                    for a, b in zip(route, route[1:]):
                        canvas.arrow(a, b, "#c36924", 4)
                    canvas.circle(route[0], 5, "#c36924")
                    canvas.text((route[0][0]+10, route[0][1]-20), path["actor"]+" 起点", 13, "#a75316")
                    canvas.text((route[-1][0]+10, route[-1][1]-15), "终点", 13, "#a75316")
        canvas.text((966, 142), "图例 / 场景对象", 20)
        y = 183
        for box in data["boxes"]:
            canvas.polygon([(967, y+3), (981, y+3), (981, y+17), (967, y+17)], COLORS[box["kind"]], None)
            canvas.text((991, y), box["id"], 15)
            canvas.text((991, y+21), box["label"], 14, "#60738a")
            y += 49
        canvas.text((966, max(y+10, 725)), "蓝：机位朝向  紫：运镜", 14)
        canvas.text((966, max(y+34, 749)), "橙：人物移动", 14)
        if camera:
            canvas.text((966, max(y+60, 775)), f"机位高度 {camera['position'][2]:g} m", 14)
            canvas.text((966, max(y+84, 799)), f"竖直视场 {camera['yfov']:g}°", 14)
        canvas.text((42, canvas.height-55), "影视空间规划 · 尺寸为设计假设时须人工核对 · 非建筑施工图", 16, "#60738a")
        stem = out / ("floor-plan" if camera is None else f"camera-overlays/{camera['id']}")
        canvas.save(stem)
        files += [str(stem.with_suffix(ext)) for ext in (".svg", ".png")]
    report = spatial_checks(data)
    write_json(out / "spatial-check.json", report)
    write_json(marker, {"fingerprint": fingerprint, "id": data["id"], "version": data["version"]})
    files += [str(out / "spatial-check.json"), str(marker)]
    return {"files": files, "checks": report}
