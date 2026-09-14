import base64
import copy
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
from PIL import Image
from blockout import build_blockout, camera_axes, dot, sub, world
from core import (approve_gate, current, load_project, mark, package, queue, register, revise,
                  safe_path, validate_project, write_json)
from layout import load_layout, render_layout, segment_box, spatial_checks
from make_demo import example_layout
from schema import LAYOUT, check, new_version
from svd import init_project, spatial_command


class ProjectCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "project"
        script = self.base / "script.md"
        script.write_text("父母和儿子在家。", encoding="utf-8")
        init_project(self.root, script, "test")
        self.picture = self.base / "synthetic-test-only.png"
        Image.new("RGB", (32, 32), "white").save(self.picture)
        data = load_project(self.root)
        for role in ("analysis", "visual-guide", "handoff"):
            path = f"{role}.md"
            (self.root / path).write_text("Synthetic test fixture", encoding="utf-8")
            data["documents"].append({"role": role, "path": path})
        data["shots"] = [{"id": "S1", "beat": "B1", "purpose": "family", "description": "family",
                          "assets": ["DAD", "MOM", "SON"], "layout": None, "camera": None, "continuity": "same scene"}]
        for key in ("DAD", "MOM", "SON"):
            v = new_version(approval=True)
            v.update(prompt=f"TEST ONLY {key}", production="prompt_ready")
            if key == "SON":
                v["dependencies"] = [{"kind": "asset", "id": p, "version": 1} for p in ("DAD", "MOM")]
                v["gates"] = ["PARENTS"]
            data["assets"].append({"id": key, "type": "character", "name": key, "description": "test",
                                   "sources": [{"basis": "explicit", "text": "family"}], "shots": ["S1"], "current_version": 1, "versions": [v]})
        data["gates"] = [{"id": "PARENTS", "refs": [{"id": p, "version": 1} for p in ("DAD", "MOM")], "status": "pending", "evidence": ""}]
        write_json(self.root / "manifest.json", data)

    def finish(self, key):
        register(self.root, key, self.picture, "synthetic-test")
        mark(self.root, key, "passed", "Synthetic fixture checked")
        mark(self.root, key, "approved", "Synthetic test user approval", approval=True)

    def all_done(self):
        self.finish("DAD"); self.finish("MOM")
        approve_gate(self.root, "PARENTS", "Synthetic test family confirmation")
        self.finish("SON")

    def test_parent_gate_blocks_child_until_both_confirmed(self):
        self.assertFalse(next(x for x in queue(self.root) if x["id"] == "SON")["ready"])
        with self.assertRaises(ValueError):
            register(self.root, "SON", self.picture, "test")
        self.finish("DAD")
        with self.assertRaises(ValueError):
            approve_gate(self.root, "PARENTS", "test")
        self.finish("MOM")
        self.assertFalse(next(x for x in queue(self.root) if x["id"] == "SON")["ready"])
        approve_gate(self.root, "PARENTS", "test")
        self.assertTrue(next(x for x in queue(self.root) if x["id"] == "SON")["ready"])

    def test_revision_preserves_old_file_invalidates_family(self):
        self.all_done()
        old = current(load_project(self.root)["assets"][0])["file"]
        digest = (self.root / old).read_bytes()
        result = revise(self.root, "DAD", "new hair")
        self.assertEqual(result["affected"], ["DAD", "SON"])
        data = load_project(self.root)
        self.assertEqual(current(data["assets"][2])["validity"], "stale")
        self.assertEqual(data["gates"][0]["status"], "pending")
        self.assertEqual((self.root / old).read_bytes(), digest)
        self.assertFalse(validate_project(self.root, strict=True)["ok"])

    def test_portable_archive_roundtrip_and_no_unlisted_files(self):
        self.all_done()
        (self.root / "unlisted.txt").write_text("not part of deliverables")
        dest = self.base / "assets.zip"
        package(self.root, dest)
        with zipfile.ZipFile(dest) as archive:
            self.assertNotIn("project-assets/unlisted.txt", archive.namelist())
            archive.extractall(self.base / "copied")
            delivery = json.loads(archive.read("project-assets/delivery.json"))
            self.assertEqual(delivery["status"], "complete")
            self.assertFalse(delivery["target_h3_validated"])
        self.assertTrue(validate_project(self.base / "copied/project-assets", strict=True)["ok"])

    def test_incomplete_archive_requires_explicit_draft(self):
        with self.assertRaises(ValueError):
            package(self.root, self.base / "fail.zip")
        package(self.root, self.base / "draft.zip", draft=True)
        with zipfile.ZipFile(self.base / "draft.zip") as z:
            self.assertEqual(json.loads(z.read("project-assets/delivery.json"))["status"], "draft")

    def test_missing_file_and_unsafe_paths_rejected_even_in_draft(self):
        for path in ("../outside", "/etc/passwd", "C:/file", "a\\b", "a/../b"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                safe_path(self.root, path)
        (self.root / "escape").symlink_to(self.base)
        with self.assertRaises(ValueError):
            safe_path(self.root, "escape/script.md")
        self.finish("DAD")
        path = current(load_project(self.root)["assets"][0])["file"]
        (self.root / path).unlink()
        self.assertFalse(validate_project(self.root)["ok"])

    def test_unknown_and_cyclic_dependencies_rejected(self):
        data = load_project(self.root)
        current(data["assets"][0])["dependencies"] = [{"kind": "asset", "id": "SON", "version": 1}]
        write_json(self.root / "manifest.json", data)
        self.assertIn("Cyclic", " ".join(validate_project(self.root)["errors"]))

    def test_rejected_review_cannot_be_approved_or_replaced(self):
        register(self.root, "DAD", self.picture, "test")
        mark(self.root, "DAD", "needs_revision", "test mismatch")
        with self.assertRaises(ValueError):
            mark(self.root, "DAD", "approved", "test", approval=True)
        with self.assertRaises(ValueError):
            register(self.root, "DAD", self.picture, "test")

    def test_gate_self_dependency_is_rejected(self):
        data = load_project(self.root)
        current(data["assets"][0])["gates"] = ["PARENTS"]
        write_json(self.root / "manifest.json", data)
        self.assertIn("Cyclic", " ".join(validate_project(self.root)["errors"]))

    def test_layout_edit_without_version_detected(self):
        lay = example_layout()
        for camera in lay["cameras"]:
            camera["shot"] = "S1"
        for path in lay["paths"]:
            path["shot"] = "S1"
        relative = "spatial/LOC_001/layout-v001.json"
        write_json(self.root / relative, lay)
        spatial_command(self.root, relative, "render-layout", None)
        lay["boxes"][6]["center"][0] += .2
        write_json(self.root / relative, lay)
        self.assertIn("without regeneration", " ".join(validate_project(self.root)["errors"]))

    def test_layout_revision_invalidates_indirect_asset_dependencies(self):
        lay = example_layout()
        for camera in lay["cameras"]:
            camera["shot"] = "S1"
        for path in lay["paths"]:
            path["shot"] = "S1"
        relative = "spatial/LOC_001/layout-v001.json"
        write_json(self.root / relative, lay)
        spatial_command(self.root, relative, "render-layout", None)
        data = load_project(self.root)
        current(data["assets"][0])["dependencies"] = [{"kind": "layout", "id": "LOC_001", "version": 1}]
        write_json(self.root / "manifest.json", data)
        lay["version"] = 2
        lay["boxes"][6]["center"][0] += .2
        relative = "spatial/LOC_001/layout-v002.json"
        write_json(self.root / relative, lay)
        spatial_command(self.root, relative, "render-layout", None)
        data = load_project(self.root)
        self.assertEqual(current(data["assets"][0])["validity"], "stale")
        self.assertEqual(current(data["assets"][2])["validity"], "stale")


class SpatialCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.layout = example_layout()

    def test_continuous_path_collision_detects_thin_and_rotated_obstacles(self):
        box = {"center": [2, 2, 1], "size": [.05, 2, 2], "rotation": 35}
        self.assertIsNotNone(segment_box([0, 2, 1], [4, 2, 1], box))
        self.assertIsNone(segment_box([0, 2, 3], [4, 2, 3], box))

    def test_layout_geometry_and_serialization(self):
        check(self.layout, LAYOUT)
        result = spatial_checks(self.layout)
        self.assertEqual(result["geometry_status"], "passed", result["issues"])
        self.layout["paths"][0]["points"] = [[3, 2.8, 0], [6, 2.8, 0]]
        self.assertTrue(any(i.get("obstacle") == "TABLE" for i in spatial_checks(self.layout)["issues"]))

    def test_same_version_edit_rejected_and_svg_png_exist(self):
        result = render_layout(self.layout, self.root / "render")
        self.assertTrue(all(Path(p).is_file() for p in result["files"]))
        import xml.etree.ElementTree as ET
        ET.parse(self.root / "render/floor-plan.svg")
        with Image.open(self.root / "render/floor-plan.png") as image:
            self.assertGreater(image.size[0], 500)
        self.layout["boxes"][0]["center"][0] += .1
        with self.assertRaises(ValueError):
            render_layout(self.layout, self.root / "render")

    def test_gltf_contains_meshes_cameras_valid_buffers_and_directions(self):
        build_blockout(self.layout, self.root / "blockout")
        model = json.loads((self.root / "blockout/scene.gltf").read_text())
        self.assertEqual(len(model["meshes"]), len(self.layout["boxes"])+1)
        self.assertEqual(len(model["cameras"]), 2)
        blob = base64.b64decode(model["buffers"][0]["uri"].split(",", 1)[1])
        self.assertEqual(len(blob), model["buffers"][0]["byteLength"])
        for view in model["bufferViews"]:
            self.assertEqual(view["byteOffset"] % 4, 0)
            self.assertLessEqual(view["byteOffset"]+view["byteLength"], len(blob))
        for node in model["nodes"]:
            if "camera" in node:
                cam = self.layout["cameras"][node["camera"]]
                pos, right, up, forward = camera_axes(cam)
                self.assertAlmostEqual(dot(right, up), 0)
                self.assertGreater(dot(sub(world(cam["target"]), pos), forward), 0)
                self.assertEqual(node["matrix"][12:15], pos)
                self.assertEqual(node["matrix"][8:11], [-x for x in forward])
        with Image.open(self.root / "blockout/CAM_002.png") as image:
            self.assertGreater(len(image.getcolors(image.width*image.height)), 10)

    def test_degenerate_camera_and_unknown_fields_fail(self):
        self.layout["cameras"][0]["target"] = self.layout["cameras"][0]["position"]
        write_json(self.root / "bad.json", self.layout)
        with self.assertRaises(ValueError):
            load_layout(self.root / "bad.json")
        self.layout["unknown_field"] = True
        with self.assertRaises(ValueError):
            check(self.layout, LAYOUT)


if __name__ == "__main__":
    unittest.main()
