import copy,unittest
import scene_plan as sp

def fixture():
 return {'schema_version':1,'fps':12,'duration':2,'scene':{'schema_version':1,'components':[{'id':'box','type':'box','position':[0,0,.5],'size':[.5,.5,1]}]},'actors':[],'actions':[{'id':'move','object':'box','kind':'object_motion','intent':'道具移动以测试目标跟随','origin':'explicit','start':{'at':0},'duration':1,'end_position':[1,0,.5]},{'id':'stop','object':'box','kind':'hold','intent':'停住','origin':'explicit','start':{'after':'move'},'duration':1}],'cameras':[{'id':'camera','target':'box','offset':[3,-5,2],'target_offset':[0,0,0],'lens':42,'follow':True,'start':{'at':0},'duration':2}]}

class ScenePlanTest(unittest.TestCase):
 def test_event_resolution(self):
  c=sp.compile_plan(fixture());self.assertEqual(c['status'],'compiled');self.assertEqual(c['plan']['actions'][1]['start_frame'],13)
 def test_cycle_and_missing_dependency(self):
  p=fixture();p['actions'][0]['start']={'after':'stop'}
  with self.assertRaisesRegex(ValueError,'成环'):sp.compile_plan(p)
  p['actions'][0]['start']={'after':'missing'}
  with self.assertRaisesRegex(ValueError,'不存在'):sp.compile_plan(p)
 def test_unsupported_action_does_not_fallback(self):
  p=fixture();p['actions'][0]['kind']='run';c=sp.compile_plan(p);self.assertEqual(c['status'],'blocked');self.assertEqual(c['findings'][0]['kind'],'unsupported_action')
 def test_no_actor_translation(self):
  p=fixture();p['scene']['components'][0]={'id':'box','type':'actor','position':[0,0,0]}
  with self.assertRaisesRegex(ValueError,'官网'):sp.compile_plan(p)
  p['scene']['components'][0]={'id':'box','type':'asset','category':'actor','position':[0,0,0],'asset_key':'blender-snow@3','model':'snow_v03.blend','collection':'CH-snow'}
  p['actors']=[{'id':'box','adapter':'snow-v3'}]
  with self.assertRaisesRegex(ValueError,'平移'):sp.compile_plan(p)
 def test_overlap_and_camera_gap(self):
  p=fixture();p['actions'][1]['start']={'at':.5}
  with self.assertRaisesRegex(ValueError,'重叠'):sp.compile_plan(p)
  p=fixture();p['cameras'][0]['duration']=1
  with self.assertRaisesRegex(ValueError,'覆盖'):sp.compile_plan(p)
 def test_schema_and_finite(self):
  p=fixture();p['scene']['components'][0]['position'][0]=float('nan')
  with self.assertRaises(ValueError):sp.compile_plan(p)
  p=fixture();p['cameras'][0]['typo']=3
  with self.assertRaises(ValueError):sp.compile_plan(p)
 def test_dependency_invalidation(self):
  p=fixture();a=sp.compile_plan(p);p['cameras'][0]['lens']=50;b=sp.compile_plan(p)
  self.assertEqual(sp.changes(a,b)['changed'],['camera']);self.assertNotIn('animation',sp.changes(a,b)['invalidate'])
  p['actions'][0]['end_position']=[2,0,.5];c=sp.compile_plan(p);self.assertIn('camera',sp.changes(b,c)['invalidate'])
 def test_time_alignment(self):
  p=fixture();p['actions'][0]['duration']=.333
  with self.assertRaisesRegex(ValueError,'对齐'):sp.compile_plan(p)
 def test_state_mismatch(self):
  p=fixture();p['actions'][0]['to_state']='standing';p['actions'][1]['from_state']='prone'
  with self.assertRaisesRegex(ValueError,'不匹配'):sp.compile_plan(p)

if __name__=='__main__':unittest.main()

class SceneBindingTest(unittest.TestCase):
 def test_existing_review_gate_and_dependency_hashes(self):
  from test_layout_first import LayoutFirstCase
  import previs,review
  from core import write_json
  case=LayoutFirstCase('test_director_draft_before_layout_and_final_text_after_blocking');case.setUp()
  try:
   s=case.prepare();write_json(case.root/'scene-plan.json',fixture())
   with self.assertRaises(ValueError):sp.bind(case.root,'scene-plan.json','layout.json')
   previs.choose(case.root,'generate',s['revision'],'Synthetic test authorization',phase='blocking')
   sp.bind(case.root,'scene-plan.json','layout.json')
   job=previs.fresh_job(case.root,phase='blocking');self.assertTrue(job)
   scripts=list((case.root/'blocking/adapters').glob('scene-*/scene_executor.py'));self.assertEqual(len(scripts),1)
   scripts[0].write_text(scripts[0].read_text()+'\n# changed\n')
   with self.assertRaises(ValueError):previs.fresh_job(case.root,phase='blocking')
  finally:case.doCleanups()
