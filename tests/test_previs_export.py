"""Synthetic contract tests; these fixtures are not production videos."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from PIL import Image
import test_previs
import previs
import previs_export
import review
from core import write_json


class ShotExportCase(unittest.TestCase):
    setUp = test_previs.PrevisCase.setUp
    init = test_previs.PrevisCase.init
    packet = test_previs.PrevisCase.packet
    audit_packet = test_previs.PrevisCase.audit_packet
    audit = test_previs.PrevisCase.audit
    ready_after_init = test_previs.PrevisCase.ready_after_init
    prepare = test_previs.PrevisCase.prepare
    adapter = test_previs.PrevisCase.adapter

    def fixture(self):
        s = self.prepare(two=True)
        previs.choose(self.root, 'generate', s['revision'], 'Synthetic generate')
        script = self.adapter()
        path = self.root / script
        spec = json.loads((path.parent / 'job.json').read_text())
        spec['clips'].append({'shot': 'S2', 'duration': 5, 'original_start': 5})
        spec['delivery'] = 'per_shot_v1'
        write_json(path.parent / 'job.json', spec)
        previs.bind(self.root, script, {'required_shots': ['S1', 'S2'], 'reason': 'Synthetic full coverage'})
        folder = self.root / 'previs/runs/synthetic'
        for kind, size in [('comparison', (64, 24)), ('camera', (32, 18))]:
            base = folder / 'output' / kind
            base.mkdir(parents=True)
            for i in range(1, 121):
                Image.new('RGB', size, (i, 0, 0)).save(base / f'{i:06d}.png')
        write_json(folder / 'run.json', {'mode': 'render', 'status': 'video_rendered_awaiting_review', 'job': previs.fresh_job(self.root)})
        write_json(folder / 'output/render-report.json', {'rendered_frames': list(range(1, 121)), 'video': 'synthetic.mp4'})
        write_json(folder / 'output/frame-map.json', [{'frame': i, 'shot': 'S1' if i <= 60 else 'S2', 'original_time': (i - 1) / 12} for i in range(1, 121)])
        return folder

    def encoder(self, binary, script, args, log):
        request = json.loads(Path(args[0]).read_text())
        self.requests = request['items']
        for item in request['items']:
            Path(item['output']).write_bytes(b'Synthetic video fixture, not real MP4.' * 2)
            with Image.open(Path(item['directory']) / f"{item.get('frame_start',1):06d}.png") as image:
                size = list(image.size)
            write_json(item['report'], {'frames': item['frames'], 'fps': item['fps'], 'size': size, 'decoded': True})

    def test_per_shot_ranges_and_no_forged_approval(self):
        folder = self.fixture()
        with patch('previs.blender_path', return_value='synthetic'), patch('previs.invoke', side_effect=self.encoder):
            result = previs_export.export_shots(self.root, 'previs/runs/synthetic')
        self.assertEqual(result['shots'], 2)
        self.assertEqual(result['missing_shots'], [])
        self.assertEqual([(r.get('frame_start',1), r['frames']) for r in self.requests], [(1,60),(1,60),(61,60),(61,60),(1,120),(1,120)])
        data = json.loads((self.root / result['index']).read_text())
        self.assertEqual(data['boundaries'][0]['type'], 'adjacent')
        self.assertFalse(data['target_validated'])
        self.assertIsNone(review.load_state(self.root)['stages']['previs'])
        self.assertEqual(review.load_state(self.root)['previs']['files'], [])
        previs_export.checked_bundle(self.root, folder)
        (folder / 'output/camera/000061.png').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, '源帧已改变'):
            previs_export.checked_bundle(self.root, folder)

    def test_missing_camera_and_wrong_timing_refused_before_encoding(self):
        folder = self.fixture()
        path = folder / 'output/camera/000060.png'
        saved = path.read_bytes(); path.unlink()
        with self.assertRaises(OSError):
            previs_export.plan(self.root, 'previs/runs/synthetic')
        path.write_bytes(saved)
        path = folder / 'output/frame-map.json'
        data = json.loads(path.read_text()); data[60]['shot'] = 'S1'; write_json(path, data)
        with self.assertRaisesRegex(ValueError, '镜号／时间'):
            previs_export.plan(self.root, 'previs/runs/synthetic')

    def test_bad_movie_metadata_cannot_register(self):
        self.fixture()
        def bad_encoder(*args):
            self.encoder(*args)
            item = self.requests[2]
            meta = json.loads(Path(item['report']).read_text()); meta['frames'] -= 1
            write_json(item['report'], meta)
        with patch('previs.blender_path', return_value='synthetic'), patch('previs.invoke', side_effect=bad_encoder):
            with self.assertRaisesRegex(ValueError, '解码校验失败'):
                previs_export.export_shots(self.root, 'previs/runs/synthetic')
        self.assertFalse((self.root / 'previs/runs/synthetic/shot-export.json').exists())


if __name__ == '__main__':
    unittest.main()
