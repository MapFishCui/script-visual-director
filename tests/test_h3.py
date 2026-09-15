import copy
import unittest
import test_groups
import h3
import groups
import review

class CompilerCase(unittest.TestCase):
    def spec(self):
        return {'mode':'Ref2VA','labels':['<Picture 1>'],
          'sections':{k:{'en':v,'zh':'审核内容'} for k,v in {
          'subject_definitions':'<Subject 1> is the woman in <Picture 1>.',
          'summary':'[reference generation] A woman speaks.',
          'retention_analysis':'<Subject 1>: fully_preserved - appearance retained.',
          'overall_soundscape':'Quiet room tone.', 'non_diegetic_music':'No music.'}.items()},
          'shots':[{'duration':5,'camera':{'en':'a static medium shot.','zh':'固定中景。'},
          'scene':{'en':'A woman sits in a room.','zh':'女人坐在房间里。'},
          'action':[{'speaker':'S1','language':'Chinese','text':'你回来啦？','voiceover':True,
          'delivery':{'en':'The woman softly','zh':'女人轻声'}}]}]}
    def test_compiler_preserves_dialogue_and_resets_task_clock(self):
        s=self.spec();s['shots'].append(copy.deepcopy(s['shots'][0]))
        r=h3.compile_task(s)
        self.assertIn('[Shot 2] At 00:05.000, the camera cuts to a static medium shot.',r['text'])
        self.assertNotIn('[Shot 1] At',r['text'])
        self.assertIn('<d>[Chinese] 你回来啦？</d>',r['text'])
        self.assertIn('says in an off-screen voiceover',r['text'])
        self.assertFalse(r['target_h3_validated'])
    def test_duration_and_injected_dialogue_rejected(self):
        s=self.spec();s['shots'][0]['duration']=20
        with self.assertRaisesRegex(ValueError,'4–15'):h3.compile_task(s)
        s=self.spec();s['shots'][0]['action'][0]['text']='<d>wrong</d>'
        with self.assertRaisesRegex(ValueError,'控制标签'):h3.compile_task(s)
    def test_reference_in_prose_and_shot_references_in_analysis(self):
        s=self.spec();s['sections']['retention_analysis']['en']+=' Appears in [Shot 1].'
        self.assertTrue(h3.compile_task(s)['syntax_validated'])
        s['labels']=[]
        with self.assertRaisesRegex(ValueError,'未绑定'):h3.compile_task(s)
    def test_malformed_sections_unknown_tags_and_first_timestamp(self):
        t=h3.compile_task(self.spec())['text'];cuts=[{'local_start':0}]
        self.assertTrue(h3.validate(t.replace('[Shot 1]','[Shot 1] At 00:00.000,'),cuts,['<Picture 1>']))
        self.assertTrue(h3.validate(t+'<invented>',cuts,['<Picture 1>']))
        self.assertTrue(h3.validate(t+'\nsummary: duplicate',cuts,['<Picture 1>']))
        self.assertTrue(h3.validate(t.replace('</d>',''),cuts,['<Picture 1>']))

class H3GateCase(unittest.TestCase):
    setUp = test_groups.GroupsCase.setUp
    finish = test_groups.GroupsCase.finish
    all_done = test_groups.GroupsCase.all_done
    init = test_groups.GroupsCase.init
    packet = test_groups.GroupsCase.packet
    audit_packet = test_groups.GroupsCase.audit_packet
    audit = test_groups.GroupsCase.audit
    ready = test_groups.GroupsCase.ready
    plan = test_groups.GroupsCase.plan
    compile_packet = test_groups.GroupsCase.compile_packet
    synced = test_groups.GroupsCase.synced
    def test_h3_generic_cannot_bypass_format_gate(self):
        self.init()
        review.configure(self.root,system={'name':'MiniMax-H3','mode':'Ref2VA','format':'official_guidance','sources':['https://huggingface.co/MiniMaxAI/MiniMax-H3']})
        groups.apply(self.root,self.plan(adapter='generic'))
        p=self.compile_packet();p['groups'][0]['text']='unstructured prompt'
        with self.assertRaisesRegex(ValueError,'六部分'):groups.sync(self.root,p)
    def test_legacy_invalid_text_blocks_readiness(self):
        self.synced()
        d=groups.load(self.root);d['compiled']['G01']['text']+=' <madeup>'
        groups.persist(self.root,d,'test')
        self.assertTrue(any('未知控制' in p for p in groups.planning_pending(self.root,d)))
