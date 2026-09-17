import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from grid_workflow import run,STAGES
class GridWorkflowTests(unittest.TestCase):
 def test_order_and_content_invalidation(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'project';run(p,'init')
   (p/'draft.md').write_text('draft')
   with self.assertRaises(ValueError):run(p,'register','grids',['draft.md'])
   for stage in STAGES:
    (p/(stage+'.txt')).write_text(stage)
    run(p,'register',stage,[stage+'.txt'])
    run(p,'confirm',stage,evidence='test-only confirmation')
   self.assertEqual(run(p,'status')['stages']['prompts'],'confirmed')
   (p/'characters.txt').write_text('changed identity')
   s=run(p,'status')['stages']
   self.assertEqual(s['characters'],'stale');self.assertEqual(s['prompts'],'waiting_upstream')
   run(p,'register','characters',['characters.txt']);run(p,'confirm','characters',evidence='new test version')
   self.assertEqual(run(p,'status')['stages']['grids'],'awaiting_confirmation')
   with self.assertRaises(ValueError):run(p,'init')
 def test_no_path_escape(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'p';run(p,'init')
   with self.assertRaises(ValueError):run(p,'register','director',['../outside'])
