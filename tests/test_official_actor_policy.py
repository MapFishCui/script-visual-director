import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import modeling

class OfficialActorPolicyTests(unittest.TestCase):
    def test_proxy_rejected_before_materialization(self):
        spec={'components':[{'type':'actor','id':'lead'}]}
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'官网'):
                modeling.materialize(spec,d,Path(d)/'out')
            self.assertFalse((Path(d)/'out').exists())

    def test_imported_actor_and_structure_allowed(self):
        for c in [{'type':'asset','category':'actor'},{'type':'box','category':'structure'}]:
            s={'components':[c]}
            self.assertIs(modeling.require_imported_characters(s),s)
