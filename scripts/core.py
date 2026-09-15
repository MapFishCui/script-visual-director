from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
import zipfile

from PIL import Image
from schema import MANIFEST, LAYOUT, check, new_version


def read_json(path):
    with Path(path).open(encoding="utf-8") as stream:
        return json.load(stream, parse_constant=lambda s: (_ for _ in ()).throw(ValueError(f"Non-finite JSON: {s}")))


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(prefix=".svd-", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def safe_path(root, relative):
    """Portable relative paths only; resolve symlinks before containment checks."""
    if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative:
        raise ValueError(f"Invalid portable path: {relative!r}")
    rel = PurePosixPath(relative)
    if rel.is_absolute() or ".." in rel.parts or rel.as_posix() != relative:
        raise ValueError(f"Invalid relative path: {relative!r}")
    root = Path(root).resolve()
    result = (root / relative).resolve()
    if result == root or root not in result.parents:
        raise ValueError(f"Path escapes project: {relative}")
    return result


def load_project(root):
    data = read_json(Path(root) / "manifest.json")
    check(data, MANIFEST)
    return data


def indexed(items):
    result = {}
    for item in items:
        if item["id"] in result:
            raise ValueError(f"Duplicate id: {item['id']}")
        result[item["id"]] = item
    return result


def current(asset):
    versions = {v["version"]: v for v in asset["versions"]}
    if len(versions) != len(asset["versions"]):
        raise ValueError(f"Duplicate versions: {asset['id']}")
    if asset["current_version"] not in versions:
        raise ValueError(f"Missing current version: {asset['id']}")
    return versions[asset["current_version"]]


def gate_ready(gate, assets):
    if gate["status"] != "approved" or not gate["evidence"].strip():
        return False
    for ref in gate["refs"]:
        a = assets.get(ref["id"])
        if not a or a["current_version"] != ref["version"]:
            return False
        v = current(a)
        if not finished(v):
            return False
    return True


def finished(version):
    return (version["production"] == "generated" and bool(version["file"])
            and version["validity"] == "current" and version["review"]["status"] == "passed"
            and version["approval"]["status"] in ("not_required", "approved")
            and (version["approval"]["status"] != "approved" or bool(version["approval"]["evidence"].strip())))


def blockers(asset, assets, layouts, gates, seen=None):
    seen = set() if seen is None else set(seen)
    if asset["id"] in seen:
        return [f"Cyclic generation dependency: {asset['id']}"]
    seen.add(asset["id"])
    v = current(asset)
    reasons = []
    for dep in v["dependencies"]:
        if dep["kind"] == "asset":
            other = assets.get(dep["id"])
            if not other or other["current_version"] != dep["version"] or not finished(current(other)):
                reasons.append(f"asset dependency {dep['id']}@{dep['version']} not ready/current")
            elif blockers(other, assets, layouts, gates, seen):
                reasons.append(f"asset dependency {dep['id']} has unresolved ancestors")
        else:
            other = layouts.get(dep["id"])
            if (not other or other["version"] != dep["version"] or other["review"]["status"] != "passed"
                    or (other["blockout_required"] and other["blockout_review"]["status"] != "passed")):
                reasons.append(f"layout dependency {dep['id']}@{dep['version']} not reviewed/current")
    for key in v["gates"]:
        if key not in gates or not gate_ready(gates[key], assets):
            reasons.append(f"confirmation gate {key} pending/stale")
        elif any(blockers(assets[r["id"]], assets, layouts, gates, seen) for r in gates[key]["refs"]):
            reasons.append(f"confirmation gate {key} has unresolved ancestors")
    return reasons


def validate_project(root, strict=False):
    from layout import load_layout, layout_fingerprint
    root = Path(root)
    errors, pending = [], []
    try:
        data = load_project(root)
        assets, shots, layouts, gates = [indexed(data[k]) for k in ("assets", "shots", "layouts", "gates")]
        for asset in assets.values():
            current(asset)
    except (ValueError, OSError) as exc:
        return {"ok": False, "errors": [str(exc)], "pending": []}
    paths = {}

    def file_check(path, label, image=False):
        try:
            target = safe_path(root, path)
            if not target.is_file():
                raise ValueError(f"Missing file: {path}")
            if image:
                if path in paths:
                    raise ValueError(f"Image path reused by {paths[path]} and {label}: {path}")
                with Image.open(target) as pic:
                    pic.verify()
                paths[path] = label
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            errors.append(str(exc))

    for doc in data["documents"]:
        file_check(doc["path"], doc["role"])
    if not assets or not shots:
        pending.append("Project needs nonempty shots and assets")
    for key in ("source", "analysis", "visual-guide", "handoff"):
        if not any(d["role"] == key for d in data["documents"]):
            pending.append(f"Missing document role: {key}")
    for rec in layouts.values():
        try:
            lay = load_layout(safe_path(root, rec["path"]))
            if (lay["id"], lay["version"]) != (rec["id"], rec["version"]):
                errors.append(f"Layout id/version mismatch: {rec['id']}")
            cams = indexed(lay["cameras"])
            for shot in shots.values():
                if shot["layout"] and shot["layout"]["id"] == rec["id"]:
                    if shot["camera"] not in cams or cams[shot["camera"]]["shot"] != shot["id"]:
                        errors.append(f"Unknown or wrong-shot camera: {shot['id']}")
            for cam in lay["cameras"]:
                if cam["shot"] not in shots:
                    errors.append(f"Unknown shot for camera: {cam['id']}")
            for output in rec["outputs"]:
                file_check(output, rec["id"])
            markers = [p for p in rec["outputs"] if p.endswith("/render-record.json")]
            if len(markers) != 1:
                pending.append(f"Missing unique layout render record: {rec['id']}")
            else:
                marker = read_json(safe_path(root, markers[0]))
                if marker.get("fingerprint") != layout_fingerprint(lay):
                    errors.append(f"Layout edited without regeneration: {rec['id']}")
            models = [p for p in rec["outputs"] if p.endswith("/scene.gltf")]
            if rec["blockout_required"] and not models:
                pending.append(f"Required blockout file missing: {rec['id']}")
            for path in models:
                model = read_json(safe_path(root, path))
                if model.get("extras", {}).get("fingerprint") != layout_fingerprint(lay):
                    errors.append(f"Blockout/layout mismatch: {rec['id']}")
            for field in ("review", "blockout_review"):
                if rec[field]["status"] == "passed" and not rec[field]["note"].strip():
                    errors.append(f"Layout review without evidence: {rec['id']} {field}")
            if rec["review"]["status"] != "passed":
                pending.append(f"Layout review pending: {rec['id']}")
            if rec["blockout_required"] and rec["blockout_review"]["status"] != "passed":
                pending.append(f"Blockout review pending: {rec['id']}")
        except (ValueError, OSError) as exc:
            errors.append(str(exc))
    for shot in shots.values():
        for key in shot["assets"]:
            if key not in assets:
                errors.append(f"Unknown asset {key} in {shot['id']}")
            elif shot["id"] not in assets[key]["shots"]:
                errors.append(f"Nonreciprocal shot/asset: {shot['id']} / {key}")
        ref = shot["layout"]
        if ref and (ref["id"] not in layouts or layouts[ref["id"]]["version"] != ref["version"]):
            errors.append(f"Stale/unknown layout in {shot['id']}")
        if not ref and shot["camera"]:
            errors.append(f"Camera without layout in {shot['id']}")
    graph = {}
    for asset in assets.values():
        v = current(asset)
        graph[asset["id"]] = [d["id"] for d in v["dependencies"] if d["kind"] == "asset"]
        graph[asset["id"]] += [r["id"] for key in v["gates"] if key in gates for r in gates[key]["refs"]]
        for sid in asset["shots"]:
            if sid not in shots or asset["id"] not in shots[sid]["assets"]:
                errors.append(f"Unknown/nonreciprocal shot {sid} in {asset['id']}")
        for version in asset["versions"]:
            label = f"{asset['id']}@{version['version']}"
            if version["file"]:
                file_check(version["file"], label, image=True)
            if version["production"] == "generated" and not version["file"]:
                errors.append(f"Generated without file: {label}")
            if version["production"] == "generated" and (not version["tool"].strip() or not version["prompt"].strip()):
                errors.append(f"Generated without prompt/tool record: {label}")
            if version["file"] and version["production"] != "generated":
                errors.append(f"File attached to ungenerated version: {label}")
            if version["approval"]["status"] == "approved" and not version["approval"]["evidence"].strip():
                errors.append(f"Approval without user evidence: {label}")
            if version["review"]["status"] == "passed" and not version["review"]["note"].strip():
                errors.append(f"Review without note: {label}")
        for dep in v["dependencies"]:
            table = assets if dep["kind"] == "asset" else layouts
            if dep["id"] not in table:
                errors.append(f"Unknown dependency {dep['id']} in {asset['id']}")
            elif dep["kind"] == "asset" and not any(vv["version"] == dep["version"] for vv in table[dep["id"]]["versions"]):
                errors.append(f"Unknown dependency version {dep['id']}@{dep['version']}")
        for key in v["gates"]:
            if key not in gates:
                errors.append(f"Unknown gate {key} in {asset['id']}")
        reasons = blockers(asset, assets, layouts, gates)
        if reasons:
            pending.extend(f"{asset['id']}: {s}" for s in reasons)
        if not finished(v):
            pending.append(f"Asset not complete/current: {asset['id']}")
    visiting, visited = set(), set()

    def walk(key):
        if key in visiting:
            raise ValueError(f"Cyclic asset dependency: {key}")
        if key in visited:
            return
        visiting.add(key)
        for dep in graph.get(key, []):
            walk(dep)
        visiting.remove(key)
        visited.add(key)
    try:
        for key in graph:
            walk(key)
    except ValueError as exc:
        errors.append(str(exc))
    for gate in gates.values():
        for ref in gate["refs"]:
            if ref["id"] not in assets:
                errors.append(f"Unknown gate asset: {ref['id']}")
        if not gate_ready(gate, assets):
            pending.append(f"Gate pending/stale: {gate['id']}")
    try:
        from review import blockers as review_blockers
        pending.extend('Review workflow: ' + reason for reason in review_blockers(root))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        errors.append('Review workflow: ' + str(exc))
    from series import verify as verify_inheritance
    errors.extend(verify_inheritance(root)['errors'])
    return {"ok": not errors and (not strict or not pending), "errors": errors, "pending": sorted(set(pending))}


def queue(root):
    report = validate_project(root)
    if report["errors"]:
        raise ValueError("\n".join(report["errors"]))
    data = load_project(root)
    assets, layouts, gates = [indexed(data[k]) for k in ("assets", "layouts", "gates")]
    from review import blockers as review_blockers
    workflow_reasons = review_blockers(root)
    rows = []
    for asset in assets.values():
        v = current(asset)
        reasons = blockers(asset, assets, layouts, gates) + list(workflow_reasons)
        if v["validity"] != "current":
            reasons.append("Revise stale asset before generating")
        if not v["prompt"].strip():
            reasons.append("Prompt missing")
        if v["production"] == "generated":
            reasons.append("Already generated; review or revise, do not overwrite")
        rows.append({"id": asset["id"], "version": v["version"], "ready": not reasons,
                     "blocked_by": reasons, "prompt": v["prompt"], "dependencies": v["dependencies"]})
    return rows


def register(root, key, source, tool):
    row = next((x for x in queue(root) if x["id"] == key), None)
    if not row or not row["ready"]:
        raise ValueError(f"Asset not ready: {row or key}")
    with Image.open(source) as image:
        image.verify()
        formats = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}
        suffix = formats.get(image.format)
    if not suffix:
        raise ValueError("Reference assets must be PNG/JPEG/WebP")
    data = load_project(root)
    asset = indexed(data["assets"])[key]
    v = current(asset)
    folder = {"character": "characters", "scene": "scenes", "prop": "props"}[asset["type"]]
    relative = f"{folder}/{key}/v{v['version']:03d}{suffix}"
    dest = safe_path(root, relative)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("xb") as target:
        target.write(Path(source).read_bytes())
    v.update(file=relative, production="generated", tool=tool)
    write_json(Path(root) / "manifest.json", data)
    return relative


def mark(root, key, status, note, approval=False):
    data = load_project(root)
    v = current(indexed(data["assets"])[key])
    if v["production"] != "generated" or not v["file"] or v["validity"] != "current":
        raise ValueError("Only generated, current assets can be reviewed/approved")
    if not note.strip():
        raise ValueError("Review/approval evidence required")
    if approval and v["review"]["status"] != "passed":
        raise ValueError("Review image before user approval")
    v["approval" if approval else "review"] = {"status": status, "evidence" if approval else "note": note}
    write_json(Path(root) / "manifest.json", data)


def approve_gate(root, key, evidence):
    data = load_project(root)
    gate = indexed(data["gates"])[key]
    gate.update(status="approved", evidence=evidence)
    if not gate_ready(gate, indexed(data["assets"])):
        raise ValueError("Gate requires current, reviewed, approved referenced assets and user evidence")
    write_json(Path(root) / "manifest.json", data)


def revise(root, key, reason):
    data = load_project(root)
    assets = indexed(data["assets"])
    asset = assets[key]
    old = current(asset)
    number = max(v["version"] for v in asset["versions"]) + 1
    new = new_version(number, old["approval"]["status"] != "not_required")
    for field in ("prompt", "dependencies", "gates"):
        new[field] = copy.deepcopy(old[field])
    new["note"] = reason
    old["validity"] = "superseded"
    asset["versions"].append(new)
    asset["current_version"] = number
    stale = {key}
    changed = True
    while changed:
        changed = False
        for other in assets.values():
            if other["id"] not in stale and any(d["kind"] == "asset" and d["id"] in stale for d in current(other)["dependencies"]):
                current(other)["validity"] = "stale"
                stale.add(other["id"])
                changed = True
    for gate in data["gates"]:
        if any(r["id"] in stale for r in gate["refs"]):
            gate.update(status="pending", evidence="")
    write_json(Path(root) / "manifest.json", data)
    return {"new_version": number, "affected": sorted(stale)}


def package(root, output, draft=False):
    root, output = Path(root).resolve(), Path(output).resolve()
    report = validate_project(root, strict=not draft)
    if not report["ok"]:
        raise ValueError(json.dumps(report, ensure_ascii=False, indent=2))
    if output.exists():
        raise ValueError("Archive already exists; choose a new versioned path")
    data = load_project(root)
    files = {"manifest.json"}
    files.update(d["path"] for d in data["documents"])
    for rec in data["layouts"]:
        files.add(rec["path"])
        files.update(rec["outputs"])
    for a in data["assets"]:
        files.update(v["file"] for v in a["versions"] if v["file"])
    if "delivery.json" in files:
        raise ValueError("delivery.json is reserved for the generated delivery report")
    content = {}
    for relative in sorted(files):
        path = safe_path(root, relative)
        if path == output or any(p.startswith(".") for p in PurePosixPath(relative).parts):
            raise ValueError(f"Unsupported package path: {relative}")
        content[relative] = path.read_bytes()
    delivery = {"status": "draft" if draft else "complete", "target_h3_validated": False,
                "pending": report["pending"], "sha256": {k: hashlib.sha256(v).hexdigest() for k, v in content.items()}}
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative, payload in content.items():
            archive.writestr(f"project-assets/{relative}", payload)
        archive.writestr("project-assets/delivery.json", json.dumps(delivery, ensure_ascii=False, indent=2))
    return {"archive": str(output), "files": len(content) + 1, "status": delivery["status"]}
