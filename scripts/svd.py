#!/usr/bin/env python3
"""CLI for deterministic work; narrative analysis and image generation run in Assistant."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from core import (approve_gate, current, indexed, load_project, mark, package, queue,
                  read_json, register, revise, safe_path, validate_project, write_json)
from layout import load_layout, render_layout, spatial_checks
from blockout import build_blockout


def init_project(root, source, name):
    root = Path(root)
    if root.exists() and any(root.iterdir()):
        raise ValueError("Initialize into an empty or new project directory")
    text = Path(source).read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError("Script is empty")
    root.mkdir(parents=True, exist_ok=True)
    (root / "source.md").write_text(text, encoding="utf-8")
    write_json(root / "manifest.json", {"schema_version": 1, "name": name,
               "documents": [{"path": "source.md", "role": "source"}],
               "shots": [], "assets": [], "layouts": [], "gates": []})
    return {"project": str(root.resolve()), "next": "Assistant: analyze source, write documents, shots and planned assets per references/asset-schema.md"}


def spatial_command(root, path, mode, font):
    from review import require_phase
    require_phase(root, mode)
    root = Path(root).resolve()
    data = load_project(root)
    lay = load_layout(safe_path(root, path))
    record = next((r for r in data["layouts"] if r["id"] == lay["id"]), None)
    if record and record["version"] > lay["version"]:
        raise ValueError("Cannot regress layout version")
    out = safe_path(root, f"spatial/{lay['id']}/v{lay['version']:03d}")
    if mode == "blockout":
        if not record or record["version"] != lay["version"] or record["path"] != path:
            raise ValueError("Render/register this layout version first")
        result = build_blockout(lay, out / "blockout", font)
        record["blockout_review"] = {"status": "pending", "note": ""}
    else:
        result = render_layout(lay, out, font)
        if record and record["version"] != lay["version"]:
            stale = set()
            for asset in data["assets"]:
                if any(d["kind"] == "layout" and d["id"] == lay["id"] for d in current(asset)["dependencies"]):
                    current(asset)["validity"] = "stale"
                    stale.add(asset["id"])
            changed = True
            while changed:
                changed = False
                for asset in data["assets"]:
                    if asset["id"] not in stale and any(d["kind"] == "asset" and d["id"] in stale for d in current(asset)["dependencies"]):
                        current(asset)["validity"] = "stale"
                        stale.add(asset["id"])
                        changed = True
            for gate in data["gates"]:
                if any(r["id"] in stale for r in gate["refs"]):
                    gate.update(status="pending", evidence="")
            record.update(version=lay["version"], path=path, outputs=[], review={"status": "pending", "note": ""},
                          blockout_review={"status": "pending", "note": ""})
        if not record:
            record = {"id": lay["id"], "version": lay["version"], "path": path, "outputs": [],
                      "review": {"status": "pending", "note": ""}, "blockout_required": False,
                      "blockout_review": {"status": "pending", "note": ""}}
            data["layouts"].append(record)
    record["outputs"] = sorted(set(record["outputs"]+[Path(p).relative_to(root).as_posix() for p in result["files"]]))
    write_json(root / "manifest.json", data)
    return result


def review_layout(root, key, note, blockout=False):
    data = load_project(root)
    record = indexed(data["layouts"])[key]
    if not note.strip():
        raise ValueError("Visual review note required")
    if blockout and not any(p.endswith("scene.gltf") for p in record["outputs"]):
        raise ValueError("No blockout generated")
    # Geometry issues are advisory: reviewer may deliberately accept occlusion, with evidence.
    record["blockout_review" if blockout else "review"] = {"status": "passed", "note": note}
    write_json(Path(root) / "manifest.json", data)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    cmd = commands.add_parser("init", help="Create an asset project, not a new skill")
    cmd.add_argument("project"); cmd.add_argument("--script", required=True); cmd.add_argument("--name", required=True)
    for name in ("validate", "queue"):
        cmd = commands.add_parser(name); cmd.add_argument("project")
        if name == "validate":
            cmd.add_argument("--strict", action="store_true")
    for name in ("render-layout", "blockout"):
        cmd = commands.add_parser(name); cmd.add_argument("project"); cmd.add_argument("layout", help="Project-relative JSON path")
        cmd.add_argument("--font")
    cmd = commands.add_parser("check-layout"); cmd.add_argument("layout")
    cmd = commands.add_parser("review-layout"); cmd.add_argument("project"); cmd.add_argument("id")
    cmd.add_argument("--note", required=True); cmd.add_argument("--blockout", action="store_true")
    cmd = commands.add_parser("register"); cmd.add_argument("project"); cmd.add_argument("id")
    cmd.add_argument("--image", required=True); cmd.add_argument("--tool", required=True)
    for name in ("review", "approve"):
        cmd = commands.add_parser(name); cmd.add_argument("project"); cmd.add_argument("id")
        cmd.add_argument("--note", required=True)
        if name == "review":
            cmd.add_argument("--reject", action="store_true")
    cmd = commands.add_parser("approve-gate"); cmd.add_argument("project"); cmd.add_argument("id"); cmd.add_argument("--evidence", required=True)
    cmd = commands.add_parser("revise"); cmd.add_argument("project"); cmd.add_argument("id"); cmd.add_argument("--reason", required=True)
    cmd = commands.add_parser("package"); cmd.add_argument("project"); cmd.add_argument("output"); cmd.add_argument("--draft", action="store_true")
    cmd = commands.add_parser("review-init", help="Import Chinese shots without overwriting existing review")
    cmd.add_argument("project"); cmd.add_argument("--system-file"); cmd.add_argument("--durations"); cmd.add_argument("--analysis-files"); cmd.add_argument("--storyboard-file"); cmd.add_argument("--workflow", choices=("layout-first-v1","storyboard-first-v1"), default="layout-first-v1")
    cmd = commands.add_parser("review-check", help="Check director completeness and export editorial review context")
    cmd.add_argument("project"); cmd.add_argument("--output")
    cmd = commands.add_parser("review-director", help="Record actual Assistant editorial review; not user approval")
    cmd.add_argument("project"); cmd.add_argument("packet")
    cmd = commands.add_parser("review-edit", help="Save structured Chinese shot changes with revision checking")
    cmd.add_argument("project"); cmd.add_argument("packet")
    cmd = commands.add_parser("review-serve", help="Open a local browser editor; no model calls")
    cmd.add_argument("project"); cmd.add_argument("--port", type=int, default=0)
    cmd = commands.add_parser("review-export", help="Export unsynced shots for Assistant")
    cmd.add_argument("project"); cmd.add_argument("output")
    cmd = commands.add_parser("review-sync", help="Apply a Assistant-reviewed sync packet")
    cmd.add_argument("project"); cmd.add_argument("packet")
    cmd = commands.add_parser("review-config")
    cmd.add_argument("project"); cmd.add_argument("config")
    cmd = commands.add_parser("review-confirm")
    cmd.add_argument("project")
    group = cmd.add_mutually_exclusive_group(required=True)
    group.add_argument("--shot"); group.add_argument("--stage", choices=("analysis", "layout", "blocking", "previs"))
    cmd.add_argument("--evidence", required=True)
    cmd = commands.add_parser('review-storyboard'); cmd.add_argument('project'); cmd.add_argument('packet')
    for name in ('library-list','library-fetch','library-pin','library-restore'):
        cmd=commands.add_parser(name);cmd.add_argument('--cache')
        if name=='library-fetch':cmd.add_argument('asset');cmd.add_argument('--descriptor')
        if name=='library-pin':cmd.add_argument('project');cmd.add_argument('asset');cmd.add_argument('version')
        if name=='library-restore':cmd.add_argument('project')
    cmd=commands.add_parser('library-inspect');cmd.add_argument('project');cmd.add_argument('key');cmd.add_argument('model');cmd.add_argument('output');cmd.add_argument('--collection');cmd.add_argument('--blender');cmd.add_argument('--pose')
    cmd=commands.add_parser('library-bundle');cmd.add_argument('project');cmd.add_argument('output')
    cmd=commands.add_parser('library-check');cmd.add_argument('project')
    cmd=commands.add_parser('scene-bind');cmd.add_argument('project');cmd.add_argument('plan');cmd.add_argument('--layout',required=True)
    cmd=commands.add_parser('scene-compile');cmd.add_argument('plan');cmd.add_argument('output')
    cmd=commands.add_parser('scene-diff');cmd.add_argument('before');cmd.add_argument('after')
    cmd=commands.add_parser('scene-build');cmd.add_argument('plan');cmd.add_argument('output');cmd.add_argument('--blender');cmd.add_argument('--render',action='store_true')
    cmd = commands.add_parser('model-validate'); cmd.add_argument('spec')
    cmd = commands.add_parser('model-build'); cmd.add_argument('spec'); cmd.add_argument('output'); cmd.add_argument('--blender')
    cmd = commands.add_parser('model-bind'); cmd.add_argument('project'); cmd.add_argument('spec'); cmd.add_argument('--layout',required=True)
    cmd = commands.add_parser('blocking-choice'); cmd.add_argument('project'); cmd.add_argument('choice', choices=('generate','skip')); cmd.add_argument('--evidence',required=True)
    cmd = commands.add_parser('blocking-bind'); cmd.add_argument('project'); cmd.add_argument('script'); cmd.add_argument('--coverage',required=True)
    cmd = commands.add_parser('blocking-run'); cmd.add_argument('project'); cmd.add_argument('--mode',choices=('build','smoke','render'),default='smoke'); cmd.add_argument('--blender')
    cmd = commands.add_parser('blocking-check'); cmd.add_argument('project'); cmd.add_argument('run'); cmd.add_argument('--note',required=True); cmd.add_argument('--reject',action='store_true'); cmd.add_argument('--blender')
    cmd = commands.add_parser('previs-doctor'); cmd.add_argument('--blender')
    cmd = commands.add_parser('previs-choice'); cmd.add_argument('project'); cmd.add_argument('choice', choices=('generate','skip')); cmd.add_argument('--evidence', required=True)
    cmd = commands.add_parser('previs-bind'); cmd.add_argument('project'); cmd.add_argument('script'); cmd.add_argument('--coverage', required=True)
    cmd = commands.add_parser('previs-run'); cmd.add_argument('project'); cmd.add_argument('--mode', choices=('build','smoke','render'), default='smoke'); cmd.add_argument('--blender')
    cmd = commands.add_parser('previs-check'); cmd.add_argument('project'); cmd.add_argument('run'); cmd.add_argument('--note', required=True); cmd.add_argument('--reject', action='store_true'); cmd.add_argument('--blender')
    cmd = commands.add_parser('previs-export-shots'); cmd.add_argument('project'); cmd.add_argument('run'); cmd.add_argument('--blender')
    for name in ('groups-apply','groups-sync'):
        cmd=commands.add_parser(name); cmd.add_argument('project'); cmd.add_argument('packet')
    cmd=commands.add_parser('groups-request'); cmd.add_argument('project'); cmd.add_argument('output')
    cmd=commands.add_parser('groups-check'); cmd.add_argument('project')
    cmd=commands.add_parser('groups-confirm'); cmd.add_argument('project'); cmd.add_argument('--evidence',required=True)
    cmd=commands.add_parser('groups-package'); cmd.add_argument('project'); cmd.add_argument('output'); cmd.add_argument('--draft',action='store_true'); cmd.add_argument('--director-group')
    cmd=commands.add_parser('groups-bundle'); cmd.add_argument('project'); cmd.add_argument('output'); cmd.add_argument('--draft',action='store_true')
    cmd=commands.add_parser('groups-previs'); cmd.add_argument('project'); cmd.add_argument('index'); cmd.add_argument('--blender')
    cmd=commands.add_parser('series-init');cmd.add_argument('library');cmd.add_argument('--name',required=True)
    cmd=commands.add_parser('series-list');cmd.add_argument('library')
    cmd=commands.add_parser('series-publish');cmd.add_argument('project');cmd.add_argument('library');cmd.add_argument('--episode',required=True);cmd.add_argument('--assets',required=True)
    cmd=commands.add_parser('series-inherit');cmd.add_argument('project');cmd.add_argument('library');cmd.add_argument('plan')
    cmd=commands.add_parser('series-check');cmd.add_argument('project')
    args = parser.parse_args(argv)
    try:
        if args.command.startswith('series-'):
            import series
            if args.command=='series-init': result=series.initialize(args.library,args.name)
            elif args.command=='series-list': result=series.catalog(args.library)
            elif args.command=='series-publish': result=series.publish(args.project,args.library,args.episode,[x.strip() for x in args.assets.split(',') if x.strip()])
            elif args.command=='series-inherit': result=series.inherit(args.project,args.library,read_json(args.plan))
            else: result=series.verify(args.project)
        elif args.command.startswith('groups-'):
            import groups
            if args.command == 'groups-apply': result=groups.apply(args.project,read_json(args.packet))
            elif args.command == 'groups-sync': result=groups.sync(args.project,read_json(args.packet))
            elif args.command == 'groups-request':
                write_json(args.output,groups.request(args.project)); result={'path':args.output}
            elif args.command == 'groups-check': result=groups.readiness(args.project)
            elif args.command == 'groups-confirm':
                import review
                result=groups.confirm(args.project,groups.load(args.project)['revision'],review.load_state(args.project)['revision'],args.evidence)
            elif args.command == 'groups-previs':
                import group_previs
                result=group_previs.build(args.project,args.index,args.blender)
            else:
                import group_package
                result=(group_package.bundle(args.project,args.output,args.draft) if args.command=='groups-bundle' else group_package.package(args.project,args.output,args.draft,args.director_group))
                output_path=Path(args.output).resolve()
                try: output_path.relative_to(Path(args.project).resolve())
                except ValueError: pass
                else:
                    import previs
                    previs.documents(args.project,[output_path])
        elif args.command.startswith('library-'):
            import model_library
            if args.command=='library-list':result=model_library.inventory(args.cache)
            elif args.command=='library-fetch':result=model_library.fetch(args.asset,args.cache,args.descriptor)
            elif args.command=='library-pin':result=model_library.pin(args.project,args.asset,args.version,args.cache)
            elif args.command=='library-restore':result=model_library.restore(args.project,args.cache)
            elif args.command=='library-bundle':result=model_library.bundle(args.project,args.output)
            elif args.command=='library-inspect':result=model_library.inspect_model(args.project,args.key,args.model,args.output,args.collection,args.blender,args.pose)
            else:result=model_library.check_project(args.project)
        elif args.command.startswith('scene-'):
            import scene_plan
            if args.command=='scene-bind':result=scene_plan.bind(args.project,args.plan,args.layout)
            elif args.command=='scene-compile':result=scene_plan.compile_file(args.plan,args.output)
            elif args.command=='scene-diff':result=scene_plan.changes(scene_plan.compile_plan(read_json(args.before)),scene_plan.compile_plan(read_json(args.after)))
            else:result=scene_plan.build(args.plan,args.output,args.blender,args.render)
        elif args.command.startswith('model-'):
            import modeling
            if args.command == 'model-validate':
                modeling.validate(read_json(args.spec)); result={'valid':True}
            elif args.command == 'model-build': result=modeling.build_scene(args.spec,args.output,args.blender)
            else: result=modeling.bind_blocking(args.project,args.spec,args.layout)
        elif args.command.startswith('blocking-'):
            import previs, review
            if args.command == 'blocking-choice': result=previs.choose(args.project,args.choice,review.load_state(args.project)['revision'],args.evidence,phase='blocking')
            elif args.command == 'blocking-bind': result=previs.bind(args.project,args.script,read_json(args.coverage),phase='blocking')
            elif args.command == 'blocking-run': result=previs.run(args.project,args.mode,args.blender,phase='blocking')
            else: result=previs.check_run(args.project,args.run,args.note,args.reject,args.blender,phase='blocking')
        elif args.command.startswith('previs-'):
            import previs
            if args.command == 'previs-doctor': result = previs.doctor(args.blender)
            elif args.command == 'previs-choice':
                import review
                state = previs.choose(args.project,args.choice,review.load_state(args.project)['revision'],args.evidence)
                result = {'revision':state['revision'],'choice':args.choice}
            elif args.command == 'previs-bind': result = previs.bind(args.project,args.script,read_json(args.coverage))
            elif args.command == 'previs-export-shots':
                import previs_export
                result = previs_export.export_shots(args.project,args.run,args.blender)
            elif args.command == 'previs-run': result = previs.run(args.project,args.mode,args.blender)
            else: result = previs.check_run(args.project,args.run,args.note,args.reject,args.blender)
        elif args.command.startswith("review-") and args.command != "review-layout":
            import review
            if args.command == "review-storyboard":
                state=review.add_storyboard(args.project,read_json(args.packet)); result={"revision":state["revision"]}
            elif args.command == "review-init":
                state = review.initialize(args.project, read_json(args.system_file) if args.system_file else None,
                                          read_json(args.durations) if args.durations else None, read_json(args.analysis_files) if args.analysis_files else None,
                                          read_json(args.storyboard_file) if args.storyboard_file else None, workflow=args.workflow)
                result = {"shots": len(state["shots"]), "revision": state["revision"]}
            elif args.command == "review-check":
                import director
                result = director.report(args.project)
                if args.output:
                    write_json(args.output, result)
                    result = {"output": args.output, "ready": result['ready'], "shots": len(result['shots']),
                              "incomplete_shots": sum(bool(s['errors']) for s in result['shots'])}
            elif args.command == "review-director":
                import director
                state = director.apply(args.project, read_json(args.packet))
                result = {"revision": state['revision'], "pending": review.blockers(args.project)}
            elif args.command == "review-edit":
                p = read_json(args.packet)
                if set(p) != {'id', 'zh', 'revision'}:
                    raise ValueError('修改需要 id、完整 zh 与 revision')
                state = review.edit_shot(args.project, p['id'], p['zh'], p['revision'])
                result = {"revision": state['revision']}
            elif args.command == "review-serve":
                from review_server import serve
                serve(args.project, args.port)
                return 0
            elif args.command == "review-export":
                packet = review.sync_request(args.project)
                write_json(args.output, packet)
                result = {"output": args.output, "pending_shots": len(packet["shots"])}
            elif args.command == "review-sync":
                state = review.apply_sync(args.project, read_json(args.packet))
                result = {"revision": state["revision"], "pending": review.blockers(args.project)}
            elif args.command == "review-config":
                config = read_json(args.config)
                if not config or set(config) - {"system", "previs"}:
                    raise ValueError("Config accepts system and/or previs only")
                state = review.configure(args.project, **config)
                result = {"revision": state["revision"]}
            else:
                state = review.load_state(args.project)
                if args.shot:
                    state = review.confirm_shot(args.project, args.shot, state["revision"], args.evidence)
                else:
                    state = review.confirm_stage(args.project, args.stage, state["revision"], args.evidence)
                result = {"revision": state["revision"]}
        elif args.command == "init":
            result = init_project(args.project, args.script, args.name)
        elif args.command == "validate":
            result = validate_project(args.project, args.strict)
        elif args.command == "queue":
            result = queue(args.project)
        elif args.command in ("render-layout", "blockout"):
            result = spatial_command(args.project, args.layout, args.command, args.font)
        elif args.command == "check-layout":
            result = spatial_checks(load_layout(args.layout))
        elif args.command == "review-layout":
            result = review_layout(args.project, args.id, args.note, args.blockout)
        elif args.command == "register":
            result = register(args.project, args.id, args.image, args.tool)
        elif args.command == "review":
            result = mark(args.project, args.id, "needs_revision" if args.reject else "passed", args.note)
        elif args.command == "approve":
            result = mark(args.project, args.id, "approved", args.note, approval=True)
        elif args.command == "approve-gate":
            result = approve_gate(args.project, args.id, args.evidence)
        elif args.command == "revise":
            result = revise(args.project, args.id, args.reason)
        else:
            result = package(args.project, args.output, args.draft)
        print(json.dumps(result if result is not None else {"ok": True}, ensure_ascii=False, indent=2))
        return 1 if (args.command in ('scene-build','scene-compile') and result['status'] in ('blocked','failed')) or (args.command == 'model-build' and result['status'] != 'passed') or (args.command == 'series-check' and not result['ok']) or (args.command == 'groups-check' and not result['ready']) or (args.command == "validate" and not result["ok"]) or (args.command == "review-check" and not result['ready']) else 0
    except (ValueError, OSError, KeyError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
