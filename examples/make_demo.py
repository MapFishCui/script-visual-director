"""Create a planning-only demonstration; intentionally generates no AI assets."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from core import write_json
from schema import new_version
from svd import init_project, spatial_command


def example_layout():
    def box(key, label, kind, center, size, solid=True, rotation=0):
        return {"id": key, "label": label, "kind": kind, "center": center, "size": size,
                "rotation": rotation, "solid": solid, "source": {"basis": "proposed", "text": "用于检验空间关系的设计布局"}}
    def camera(key, shot, position, target):
        return {"id": key, "shot": shot, "position": position, "target": target,
                "yfov": 55, "aspect": 16/9, "path": [], "source": {"basis": "proposed", "text": "服务于进入空间或发现信封"}}
    return {"schema_version": 1, "id": "LOC_001", "version": 1, "name": "回家发现一封信 · 客厅布局",
            "units": "m", "extent": [7, 5], "height": 2.8,
            "assumptions": ["房间尺寸、陈设和机位为设计假设，非剧本事实。", "图中门板为打开状态，墙体已为入口留洞。"],
            "boxes": [
                box("W1", "左侧墙", "wall", [.08, 2.5, 1.4], [.16, 5, 2.8]),
                box("W2", "后侧墙", "wall", [3.5, 4.92, 1.4], [7, .16, 2.8]),
                box("W3", "右侧墙", "wall", [6.92, 2.5, 1.4], [.16, 5, 2.8]),
                box("W4", "入口左墙段", "wall", [.8, .08, 1.4], [1.6, .16, 2.8]),
                box("W5", "入口右墙段", "wall", [4.7, .08, 1.4], [4.6, .16, 2.8]),
                box("DOOR", "入口门板（打开）", "door", [1.65, .53, 1.05], [.06, .9, 2.1]),
                box("TABLE", "放置信封的桌子", "furniture", [4.4, 2.8, .4], [1.4, .9, .8]),
                box("SOFA", "沙发", "furniture", [1.3, 3.8, .45], [1.8, .8, .9]),
                box("LETTER", "无字信封", "prop", [4.4, 2.8, .815], [.22, .11, .03], False)
            ],
            "cameras": [camera("CAM_001", "SHOT_001", [5.8, 1.2, 1.5], [2.1, 1, 1.2]),
                        camera("CAM_002", "SHOT_002", [4.4, 1.4, 1.5], [4.4, 2.8, .83])],
            "paths": [{"id": "PATH_001", "actor": "CHAR_001", "shot": "SHOT_001",
                       "points": [[2.1, .25, 0], [2.5, 1.8, 0], [3.5, 2, 0]], "clearance": .22,
                       "source": {"basis": "proposed", "text": "进入房间后走近桌子，避免不可信的远距离读信"}}]}


def make_demo(root):
    root = Path(root)
    source = Path(__file__).with_name("script.md")
    init_project(root, source, "回家发现一封信 · 规划示例")
    documents = [{"path": "source.md", "role": "source"}]
    texts = {
        "analysis/narrative-analysis.md": ("analysis", "# 节拍与紧张度\n\nBEAT_001：回家与进入空间，紧张度 1/5，日常动作。\n\nBEAT_002：注意到桌上的信，紧张度 2/5；只是未知信息引发好奇，不增加危险。原文明示有信，疑惑为合理推断，屋内布局为设计建议。\n"),
        "analysis/character-analysis.md": ("analysis", "# 角色心理\n\nCHAR_001：刚回家，随后想确认桌上物件。短暂停顿和目光转移为表演建议；不推断寄信人、恐惧或创伤背景。\n"),
        "analysis/camera-plan.md": ("analysis", "# 文字分镜\n\nSHOT_001 / BEAT_001：中广景，固定机位 CAM_001，女人进门、走近桌子；保持入口与桌子关系。\n\nSHOT_002 / BEAT_002：CAM_002 提供桌面与信封的空间参考，成片中的具体特写由下游设计。信封文字未知，采用无字外观；拿取前保持密封。时长暂定。\n\n本示例只检验规划与导出，不包含 AI 图片、完整视频任务或用户确认。\n"),
        "visual-guide.md": ("visual-guide", "# 视觉方案\n\n建议自然写实、普通现代居室，最终画风和角色形象等待代表样图确认。布局尺寸为假设。\n"),
        "handoff.md": ("handoff", "# 交接状态\n\n规划示例，尚未调用生图工具。角色、场景、道具均为待生成。平面图与白模属于规划资料。MiniMax-H3 目标部署与实际导入未验证。\n")}
    for path, (role, text) in texts.items():
        dest = root / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        documents.append({"path": path, "role": role})
    assets = []
    for key, kind, name, shots in [("CHAR_001", "character", "回家的女人", ["SHOT_001"]),
                                   ("LOC_REF", "scene", "客厅参考图", ["SHOT_001", "SHOT_002"]),
                                   ("PROP_001", "prop", "无字信封", ["SHOT_002"])]:
        version = new_version(approval=kind == "character")
        version.update(production="prompt_ready", prompt=f"自然写实的{name}独立参考图。按剧本和已确认基准设计，保持标识清晰。")
        if kind == "scene":
            version["dependencies"] = [{"kind": "layout", "id": "LOC_001", "version": 1}]
        assets.append({"id": key, "type": kind, "name": name, "description": name,
                       "sources": [{"basis": "explicit", "text": "女人回家，发现桌上有一封信。"}],
                       "shots": shots, "current_version": 1, "versions": [version]})
    write_json(root / "manifest.json", {"schema_version": 1, "name": "回家发现一封信 · 规划示例", "documents": documents,
        "shots": [{"id": "SHOT_001", "beat": "BEAT_001", "purpose": "交代回家与空间", "description": "进入后走近桌子",
                   "assets": ["CHAR_001", "LOC_REF"], "layout": {"id": "LOC_001", "version": 1}, "camera": "CAM_001", "continuity": "保持入口与桌子位置"},
                  {"id": "SHOT_002", "beat": "BEAT_002", "purpose": "展示发现的信封", "description": "信封细节需要独立资产",
                   "assets": ["LOC_REF", "PROP_001"], "layout": {"id": "LOC_001", "version": 1}, "camera": "CAM_002", "continuity": "信封保持密封，文字未知"}],
        "assets": assets, "layouts": [], "gates": []})
    path = "spatial/LOC_001/layout-v001.json"
    write_json(root / path, example_layout())
    spatial_command(root, path, "render-layout", None)
    spatial_command(root, path, "blockout", None)
    return root


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: .venv/bin/python examples/make_demo.py NEW_DEMO_DIRECTORY")
    print(make_demo(sys.argv[1]).resolve())
