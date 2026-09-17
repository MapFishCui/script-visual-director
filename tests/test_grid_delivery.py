"""Synthetic fixtures only: no production images or real user approvals."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from PIL import Image
from core import write_json, read_json
import grid_workflow as grid
import grid_items
import grid_delivery as delivery
import grid_series
import h3
import series


def fixture(root, confirmed=True):
    grid.run(root, 'init')
    (root / 'director.md').write_text('合成测试导演稿', encoding='utf-8')
    plan = {'schema_version': 1, 'director': 'director.md', 'characters': [], 'tasks': []}
    for i in (1, 2):
        cid, tid = f'C{i}', f'T{i}'
        views = {v: f'{cid}/{v}.png' for v in delivery.VIEWS}
        source = f'{cid}/source.json'
        for path in views.values():
            p = root / path; p.parent.mkdir(parents=True, exist_ok=True)
            Image.new('RGB', (12, 12), (i * 40, 50, 100)).save(p)
        write_json(root / source, {'synthetic': True, 'note': 'isolated test fixture'})
        plan['characters'].append({'id': cid, 'version': 1, 'views': views, 'source': source})
        task = {'id': tid, 'duration': 5, 'characters': {cid: 1}, 'grid': f'{tid}/grid.png',
                'panel_map': f'{tid}/panel-map.json', 'prompt_spec': f'{tid}/spec.json', 'prompt': f'{tid}/prompt.json',
                'references': [{'label': '<Picture 1>', 'path': views['sheet'], 'roles': ['appearance']},
                               {'label': '<Picture 2>', 'path': f'{tid}/grid.png', 'roles': ['composition']}]}
        (root / tid).mkdir()
        Image.new('RGB', (30, 30), 'white').save(root / task['grid'])
        write_json(root / task['panel_map'], {'task_id': tid, 'duration': 5, 'characters': {cid: 1},
            'panels': [{'panel': n + 1, 'time_seconds': n * 5 / 8, 'shot_id': 'S1', 'description': '完整测试画面', 'transition': 'continuous' if n < 8 else 'hold'} for n in range(9)]})
        spec = {'mode': 'Ref2VA', 'labels': ['<Picture 1>', '<Picture 2>'],
            'media': [{'label': r['label'], 'type': 'image', 'roles': r['roles']} for r in task['references']],
            'sections': {k: {'en': v, 'zh': '合成测试中文对照'} for k, v in {
                'subject_definitions': '<Subject 1> is the person in <Picture 1>.\n<Picture 2> shows complete keyframes.',
                'summary': '[reference generation] A quiet scene.',
                'retention_analysis': '<Subject 1>: fully_preserved - identity.\n<Picture 2>: partially_preserved - composition.',
                'overall_soundscape': 'Room tone.', 'non_diegetic_music': 'No music.'}.items()},
            'shots': [{'id': 'S1', 'duration': 5, 'camera': {'en': 'a static medium shot.', 'zh': '固定中景'}, 'scene': {'en': 'A room.', 'zh': '房间'}, 'action': [{'en': 'The person sits.', 'zh': '人物坐着'}]}]}
        write_json(root / task['prompt_spec'], spec)
        write_json(root / task['prompt'], h3.compile_task(spec))
        plan['tasks'].append(task)
    write_json(root / delivery.PLAN, plan)
    grid.run(root, 'register', 'director', ['director.md', delivery.PLAN])
    grid.run(root, 'confirm', 'director', evidence='synthetic test only')
    for c in plan['characters']:
        grid_items.change(root, 'register-item', 'characters', c['id'], list(c['views'].values()) + [c['source']])
        grid_items.change(root, 'confirm-item', 'characters', c['id'], evidence='synthetic test only')
    for t in plan['tasks']:
        grid_items.change(root, 'register-item', 'grids', t['id'], [t['grid'], t['panel_map']], list(t['characters']))
        grid_items.change(root, 'confirm-item', 'grids', t['id'], evidence='synthetic test only')
        grid_items.change(root, 'register-item', 'prompts', t['id'], [t['prompt_spec'], t['prompt']])
        if confirmed:
            grid_items.change(root, 'confirm-item', 'prompts', t['id'], evidence='synthetic test only')
    return plan


class GridDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name); self.root = self.base / 'project'
        self.plan = fixture(self.root)

    def test_portable_and_native_export(self):
        self.assertTrue(delivery.validate(self.root)['ok'])
        for adapter, name in [('generic', 'delivery.zip'), ('aimixer-h3', 'delivery.mmxpack.zip')]:
            dest = self.base / name
            delivery.package(self.root, dest, adapter)
            with zipfile.ZipFile(dest) as z:
                self.assertIsNone(z.testzip())
                self.assertIn('project/grid-workflow.json', z.namelist())
                bindings = json.loads(z.read('extra/bindings.json'))
                self.assertEqual(len(bindings), 4)
                self.assertTrue(all(b['pack_path'] in z.namelist() for b in bindings))
                if adapter == 'aimixer-h3':
                    group = json.loads(z.read('asset_groups/0001/group.json'))
                    self.assertEqual([r['index'] for r in group['refs']], [0, 1])
                    self.assertEqual(group['frameCount'] % 17, 5)
            with self.assertRaises(ValueError): delivery.package(self.root, dest, adapter)
        restored = self.base / 'restored'
        with zipfile.ZipFile(self.base / 'delivery.zip') as z: z.extractall(restored)
        self.assertTrue(delivery.validate(restored / 'project')['ok'])

    def test_text_only_approval_is_not_delivery(self):
        root = self.base / 'text-only'; grid.run(root, 'init')
        (root / 'note.txt').write_text('synthetic', encoding='utf-8')
        for stage in grid.STAGES:
            grid.run(root, 'register', stage, ['note.txt'])
            grid.run(root, 'confirm', stage, evidence='synthetic')
        self.assertFalse(delivery.validate(root)['ok'])
        with self.assertRaises(ValueError): delivery.package(root, self.base / 'bad.zip')

    def test_panel_slots_translation_and_corrupt_image_rejected(self):
        task = self.plan['tasks'][0]
        cases = [(task['panel_map'], lambda d: d['panels'].pop()),
                 (task['prompt_spec'], lambda d: d['labels'].reverse()),
                 (task['prompt'], lambda d: d.update(translation_zh='stale'))]
        for path, mutate in cases:
            original = (self.root / path).read_bytes()
            data = read_json(self.root / path); mutate(data); write_json(self.root / path, data)
            self.assertTrue(delivery.validate(self.root)['errors'], path)
            (self.root / path).write_bytes(original)
        (self.root / task['grid']).write_bytes(b'not an image')
        self.assertTrue(delivery.validate(self.root)['errors'])

    def test_task_revision_preserves_unrelated_approvals(self):
        t = self.plan['tasks'][0]
        grid_items.change(self.root, 'feedback-item', 'grids', 'T1', evidence='synthetic feedback')
        state = read_json(self.root / 'grid-workflow.json')
        self.assertEqual(grid_items.condition(self.root, state, 'grids/T1'), 'needs_revision')
        self.assertEqual(grid_items.condition(self.root, state, 'prompts/T1'), 'waiting_upstream')
        self.assertEqual(grid_items.condition(self.root, state, 'prompts/T2'), 'confirmed')
        grid_items.change(self.root, 'register-item', 'grids', 'T1', [t['grid'], t['panel_map']], ['C1'])
        grid_items.change(self.root, 'confirm-item', 'grids', 'T1', evidence='synthetic revised confirmation')
        state = read_json(self.root / 'grid-workflow.json')
        self.assertEqual(grid_items.condition(self.root, state, 'prompts/T1'), 'stale')
        self.assertEqual(grid_items.condition(self.root, state, 'prompts/T2'), 'confirmed')
        with self.assertRaises(ValueError): grid_items.change(self.root, 'confirm-item', 'prompts', 'T1', evidence='synthetic')
        with self.assertRaises(ValueError): delivery.package(self.root, self.base / 'unconfirmed.zip')
        self.assertEqual(delivery.package(self.root, self.base / 'draft.zip', draft=True)['status'], 'draft')

    def test_character_revision_is_scoped_to_its_consumers(self):
        c = self.plan['characters'][0]
        grid_items.change(self.root, 'register-item', 'characters', 'C1', list(c['views'].values()) + [c['source']])
        state = read_json(self.root / 'grid-workflow.json')
        self.assertEqual(grid_items.condition(self.root, state, 'grids/T1'), 'stale')
        self.assertEqual(grid_items.condition(self.root, state, 'prompts/T2'), 'confirmed')

    def test_grid_series_roundtrip_and_tampering(self):
        library = self.base / 'library'; series.initialize(library, 'synthetic series')
        first = series.publish(self.root, library, 'EP01', ['C1'])
        self.assertEqual(first['published'][0]['version'], 1)
        self.assertTrue(series.publish(self.root, library, 'EP01', ['C1'])['published'][0]['reused_snapshot'])
        dest = self.base / 'episode2'; grid.run(dest, 'init')
        (dest / 'director.md').write_text('test episode2', encoding='utf-8')
        write_json(dest / delivery.PLAN, self.plan)
        grid.run(dest, 'register', 'director', ['director.md', delivery.PLAN])
        grid.run(dest, 'confirm', 'director', evidence='synthetic')
        plan = {'episode': 'EP02', 'items': [{'source_id': 'C1', 'version': 1, 'target_id': 'C1', 'continuity_note': 'synthetic same appearance'}]}
        self.assertEqual(series.inherit(dest, library, plan)['inherited'], ['C1'])
        self.assertTrue(series.verify(dest)['ok'])
        with self.assertRaises(ValueError): series.inherit(dest, library, plan)
        (dest / self.plan['characters'][0]['views']['head']).write_bytes(b'changed')
        self.assertFalse(series.verify(dest)['ok'])

    def test_empty_translation_and_invalid_panel_time_rejected(self):
        task = self.plan['tasks'][0]
        spec = read_json(self.root / task['prompt_spec'])
        spec['shots'][0]['camera']['zh'] = ''
        write_json(self.root / task['prompt_spec'], spec)
        write_json(self.root / task['prompt'], h3.compile_task(spec))
        self.assertIn('中文对照', ' '.join(delivery.validate(self.root)['errors']))
        spec['shots'][0]['camera']['zh'] = '固定镜头'
        write_json(self.root / task['prompt_spec'], spec)
        write_json(self.root / task['prompt'], h3.compile_task(spec))
        panels = read_json(self.root / task['panel_map'])
        panels['panels'][-1]['time_seconds'] = 16
        write_json(self.root / task['panel_map'], panels)
        self.assertIn('时间', ' '.join(delivery.validate(self.root)['errors']))

    def test_wrong_item_dependency_and_external_paths_rejected(self):
        task = self.plan['tasks'][0]
        grid_items.change(self.root, 'register-item', 'grids', 'T1', [task['grid'], task['panel_map']], ['C2'])
        self.assertIn('依赖', ' '.join(delivery.validate(self.root)['errors']))
        with self.assertRaises(ValueError):
            grid_items.change(self.root, 'register-item', 'characters', 'escape', ['../outside'])
        self.plan['tasks'][0]['grid'] = '../outside.png'
        write_json(self.root / delivery.PLAN, self.plan)
        self.assertTrue(delivery.validate(self.root)['errors'])

    def test_no_character_task_without_fabricated_images(self):
        root = self.base / 'empty-scene'; grid.run(root, 'init')
        (root / 'director.md').write_text('无人物空景测试', encoding='utf-8')
        (root / 'none.md').write_text('本段无人物', encoding='utf-8')
        task = copy.deepcopy(self.plan['tasks'][0]); task['characters'] = {}
        task['references'] = [{'label': '<Picture 1>', 'path': task['grid'], 'roles': ['composition']}]
        (root / 'T1').mkdir()
        Image.new('RGB', (30, 30), 'white').save(root / task['grid'])
        panel_map = read_json(self.root / task['panel_map']); panel_map['characters'] = {}
        write_json(root / task['panel_map'], panel_map)
        spec = read_json(self.root / task['prompt_spec']); spec['labels'] = ['<Picture 1>']
        spec['media'] = [{'label': '<Picture 1>', 'type': 'image', 'roles': ['composition']}]
        spec['sections']['subject_definitions']['en'] = '<Picture 1> shows empty room keyframes.'
        spec['sections']['retention_analysis']['en'] = '<Picture 1>: partially_preserved - composition.'
        write_json(root / task['prompt_spec'], spec); write_json(root / task['prompt'], h3.compile_task(spec))
        write_json(root / delivery.PLAN, {'schema_version': 1, 'director': 'director.md', 'characters': [], 'no_characters': 'none.md', 'tasks': [task]})
        grid.run(root, 'register', 'director', ['director.md', delivery.PLAN]); grid.run(root, 'confirm', 'director', evidence='synthetic')
        for stage, item, files, deps in [('characters', 'NONE', ['none.md'], None), ('grids', 'T1', [task['grid'], task['panel_map']], ['NONE']), ('prompts', 'T1', [task['prompt_spec'], task['prompt']], None)]:
            grid_items.change(root, 'register-item', stage, item, files, deps)
            grid_items.change(root, 'confirm-item', stage, item, evidence='synthetic')
        self.assertTrue(delivery.validate(root)['ok'])

    def test_failed_batch_inheritance_leaves_no_partial_character(self):
        library = self.base / 'library'; series.initialize(library, 'test')
        series.publish(self.root, library, 'EP01', ['C1', 'C2'])
        dest = self.base / 'episode'; grid.run(dest, 'init')
        (dest / 'director.md').write_text('test', encoding='utf-8'); write_json(dest / delivery.PLAN, self.plan)
        grid.run(dest, 'register', 'director', ['director.md', delivery.PLAN]); grid.run(dest, 'confirm', 'director', evidence='synthetic')
        items = [{'source_id': cid, 'target_id': cid, 'version': 1 if cid == 'C1' else 99, 'continuity_note': 'test'} for cid in ('C1', 'C2')]
        with self.assertRaises(ValueError): series.inherit(dest, library, {'episode': 'EP02', 'items': items})
        self.assertFalse((dest / 'C1').exists())
        self.assertNotIn('characters', read_json(dest / 'grid-workflow.json')['stages'])

if __name__ == '__main__': unittest.main()
