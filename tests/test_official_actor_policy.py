"""Spatial proxies are allowed; imported models retain provenance checks."""
import sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import modeling

class ActorPolicyTests(unittest.TestCase):
    def test_proxy_motion_materializes_without_download(self):
        spec = {'schema_version': 1, 'frames': 24, 'components': [{
            'type': 'actor', 'id': 'lead', 'position': [0, 0, 0],
            'keys': [{'frame': 1, 'position': [0, 0, 0]},
                     {'frame': 24, 'position': [0, 2, 0]}],
        }]}
        with tempfile.TemporaryDirectory() as d:
            with patch('model_library.check_project') as check:
                result = modeling.materialize(modeling.validate(spec), d, Path(d) / 'out')
            check.assert_not_called()
            self.assertEqual(result, spec)
            self.assertIsNot(result, spec)

    def test_imported_actor_still_requires_lock(self):
        spec = {'components': [{'type': 'asset', 'category': 'actor'}]}
        with tempfile.TemporaryDirectory() as d:
            with patch('model_library.check_project', side_effect=ValueError('missing asset lock')) as check:
                with self.assertRaisesRegex(ValueError, 'asset lock'):
                    modeling.materialize(spec, d, Path(d) / 'out')
            check.assert_called_once()
