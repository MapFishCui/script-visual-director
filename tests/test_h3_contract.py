import copy,unittest
import h3,h3_contract
import test_h3

class ContractTest(unittest.TestCase):
 def image(self,role='appearance'):
  return {'label':'<Picture 1>','type':'image','roles':[role]}
 def test_five_modes(self):
  self.assertEqual(h3_contract.route([])['mode'],'T2VA')
  self.assertEqual(h3_contract.route([self.image('first_frame')])['mode'],'I2VA')
  self.assertEqual(h3_contract.route([self.image('last_frame')])['mode'],'L2VA')
  self.assertEqual(h3_contract.route([self.image('first_frame'),{'label':'<Picture 2>','type':'image','roles':['last_frame']}])['mode'],'FL2VA')
  self.assertEqual(h3_contract.route([self.image()])['mode'],'Ref2VA')
 def test_camera_reference_is_not_video_edit(self):
  r=h3_contract.route([{'label':'<Video 1>','type':'video','roles':['camera'],'duration':4}]);self.assertEqual(r['task_types'],['reference generation'])
  r=h3_contract.route([{'label':'<Video 1>','type':'video','roles':['source_edit'],'duration':4}]);self.assertEqual(r['task_types'],['video editing'])
 def test_voice_reference_does_not_copy_audio(self):
  r=h3_contract.route([{'label':'<Audio 1>','type':'audio','roles':['voice'],'duration':3}]);self.assertEqual(r['task_types'],['audio reference'])
 def test_previs_requires_approved_purpose(self):
  m={'label':'<Video 1>','type':'video','roles':['motion'],'duration':4,'previs':True,'approved_roles':['camera']}
  with self.assertRaisesRegex(ValueError,'用途审阅'):h3_contract.route([m])
  m['roles']=['camera'];self.assertTrue(h3_contract.route([m])['warnings'])
 def test_limits_and_ambiguous_inputs(self):
  media=[{'label':'<Video '+str(i)+'>','type':'video','roles':['camera'],'duration':8} for i in (1,2)]
  with self.assertRaises(ValueError):h3_contract.route(media)
  with self.assertRaises(ValueError):h3_contract.route([self.image(),self.image()])
  with self.assertRaises(ValueError):h3_contract.route([{'label':'<Video 1>','type':'video','roles':['camera'],'duration':float('nan')}])
 def test_indirect_mention_is_not_a_definition(self):
  s=test_h3.CompilerCase().spec();s['sections']['subject_definitions']['en']+=' standing beside <Subject 2>.'
  with self.assertRaisesRegex(ValueError,'未独立定义'):h3.compile_task(s)
 def test_duplicate_and_missing_retention(self):
  s=test_h3.CompilerCase().spec();s['sections']['subject_definitions']['en']+='\n'+s['sections']['subject_definitions']['en']
  with self.assertRaisesRegex(ValueError,'重复定义'):h3.compile_task(s)
  s=test_h3.CompilerCase().spec();s['sections']['retention_analysis']['en']='N/A'
  with self.assertRaisesRegex(ValueError,'缺少保留'):h3.compile_task(s)
 def test_audio_relationship_and_dialogue_scope(self):
  s=test_h3.CompilerCase().spec();s['labels'].append('<Audio 1>');s['sections']['subject_definitions']['en']+='\n<Audio 1> is the voice reference.';s['sections']['retention_analysis']['en']+='\n<Audio 1>: fully_preserved - voice.'
  with self.assertRaisesRegex(ValueError,'类型不符'):h3.compile_task(s)
  s=test_h3.CompilerCase().spec();s['sections']['overall_soundscape']['en']='<d>[English] Hello.</d>'
  with self.assertRaisesRegex(ValueError,'完整台词'):h3.compile_task(s)
 def test_optional_media_contract_checks_summary(self):
  s=test_h3.CompilerCase().spec();s['media']=[self.image()];self.assertEqual(h3.compile_task(s)['reference_routing']['mode'],'Ref2VA')
  s['sections']['summary']['en']='[video editing] A woman speaks.'
  with self.assertRaisesRegex(ValueError,'实际用途'):h3.compile_task(s)
 def test_label_type_is_not_inferred_from_slot_number(self):
  with self.assertRaises(ValueError):h3_contract.route([{'label':'<Picture 1>','type':'video','roles':['motion'],'duration':4}])

if __name__=='__main__':unittest.main()
