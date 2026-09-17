"""Run DOM event regression tests when Node.js is available."""
from pathlib import Path
import shutil
import subprocess
import unittest

class GridFrontendTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node.js is required for frontend event tests')
    def test_frontend_events(self):
        result = subprocess.run([shutil.which('node'), '--test', str(Path(__file__).with_name('grid_frontend.test.js'))], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
