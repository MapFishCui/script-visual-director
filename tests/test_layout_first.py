import copy
import unittest
from unittest.mock import patch
from PIL import Image
import test_review, test_workflow
import review, previs
from core import load_project, write_json, read_json
from layout import layout_fingerprint, load_layout


class LayoutFirstCase(unittest.TestCase):
    setUp = test_workflow.ProjectCase.setUp
    packet = test_review.ReviewCase.packet
    audit = test_review.ReviewCase.audit
    audit_packet = test_review.ReviewCase.audit_packet

    def prepare(self):
        m=load_project(self.root); self.rows=copy.deepcopy(m['shots'])
        m['shots']=[];m['assets']=[];m['gates']=[]
        lay=test_workflow.example_layout()
        for item in lay['cameras']+lay['paths']: item['shot']=None
        write_json(self.root/'layout.json',lay)
        m['layouts']=[dict(id=lay['id'],version=1,path='layout.json',outputs=[],review={'status':'passed','note':'Synthetic'},blockout_required=False,blockout_review={'status':'pending','note':''})]
        write_json(self.root/'manifest.json',m)
        (self.root/'creative-treatment.md').write_text('Synthetic continuous action and dialogue, not a shot list')
        m['documents'].append({'role':'analysis','path':'creative-treatment.md'});write_json(self.root/'manifest.json',m)
        s=review.initialize(self.root,workflow='layout-first-v1')
        self.assertEqual(s['shots'],[])
        self.assertEqual(review.view(self.root)['shots'],[])
        with self.assertRaises(ValueError): review.confirm_stage(self.root,'layout',s['revision'],'Too early')
        s=review.add_storyboard(self.root,self.storyboard())
        s=review.confirm_stage(self.root,'analysis',s['revision'],'Synthetic user approves Chinese director draft')
        review.require_phase(self.root,'render-layout')
        load_layout(self.root/'layout.json')
        return review.confirm_stage(self.root,'layout',s['revision'],'Synthetic user approves layout')

    def storyboard(self):
        rows=copy.deepcopy(self.rows)
        for row in rows: row['assets']=[]
        zh={k:'Synthetic fixture' for k in review.FIELDS}
        zh.update(duration=5,camera='固定中景',description='室内',action='人物走过房间')
        return {'revision':review.load_state(self.root)['revision'],'shots':rows,'storyboard':{q['id']:copy.deepcopy(zh) for q in rows}}

    def test_director_draft_before_layout_and_final_text_after_blocking(self):
        s=self.prepare()
        self.assertEqual(len(s['shots']),1)
        self.assertFalse(s['shots'][0]['target']['text'])
        with self.assertRaisesRegex(ValueError,'整场'):review.sync_request(self.root)
        s=previs.choose(self.root,'skip',s['revision'],'Synthetic user skips blocking',phase='blocking')
        before=review.proof(self.root,s,'layout')
        s=review.apply_sync(self.root,self.packet())
        self.assertEqual(review.proof(self.root,s,'layout'),before)
        self.assertTrue(review.stage_ready(self.root,s,'blocking'))
        self.assertFalse(review.is_approved(s,s['shots'][0]))
        with self.assertRaises(ValueError):review.add_storyboard(self.root,self.storyboard())
        with self.assertRaisesRegex(ValueError,'正式分镜'):previs.choose(self.root,'generate',s['revision'],'too early')
        zh=copy.deepcopy(s['shots'][0]['zh']);zh['camera']='缓慢横移'
        s=review.edit_shot(self.root,'S1',zh,s['revision'])
        for stage in ('analysis','layout','blocking'):
            self.assertFalse(review.stage_ready(self.root,s,stage))
        with self.assertRaises(ValueError):review.confirm_shot(self.root,'S1',s['revision'],'stale')

    def bind(self):
        s=self.prepare();previs.choose(self.root,'generate',s['revision'],'Synthetic generate',phase='blocking')
        base=self.root/'blocking/adapter';base.mkdir(parents=True)
        (base/'build.py').write_text('# Synthetic test adapter, no real render')
        (base/'layout.json').write_bytes((self.root/'layout.json').read_bytes())
        job={'fps':2,'beats':[{'id':'B1','duration':1,'action':'move','start_state':'left','end_state':'right'}],
             'clips':[{'beat':'B1','duration':1,'original_start':0}], 'source_layout':'layout.json',
             'layout_fingerprint':layout_fingerprint(read_json(self.root/'layout.json')),
             'input_sha256':{p.name:previs.sha(p) for p in base.iterdir()}}
        write_json(base/'job.json',job)
        coverage={'required_beats':['B1'],'reason':'Synthetic entire scene'}
        previs.bind(self.root,'blocking/adapter/build.py',coverage,phase='blocking')
        return base,coverage

    def render_fixture(self):
        self.bind();folder=self.root/'blocking/runs/test';out=folder/'output';(out/'comparison').mkdir(parents=True)
        job=previs.fresh_job(self.root,phase='blocking')
        write_json(folder/'run.json',{'mode':'render','job':job})
        write_json(out/'frame-map.json',[{'frame':i+1,'beat':'B1','original_time':i/2} for i in range(2)])
        for i in (1,2):Image.new('RGB',(32,32),'white').save(out/'comparison'/f'{i:06d}.png')
        (out/'test.mp4').write_bytes(b'Synthetic video; decoder is mocked in this test.'*2)
        (out/'critical-previs.blend').write_bytes(b'Synthetic scene')
        write_json(out/'render-report.json',{'status':'rendered','video':'test.mp4','rendered_frames':[1,2]})
        def decode(binary,script,args,log):
            req=read_json(args[0]);write_json(req['report'],{'frames':2,'size':[32,32],'fps':2})
        with patch('previs.blender_path',return_value='/synthetic/blender'),patch('previs.invoke',side_effect=decode):
            return folder,previs.check_run(self.root,'blocking/runs/test','Synthetic inspected',phase='blocking')

    def test_full_blocking_check_confirm_and_scene_tamper(self):
        folder,rec=self.render_fixture();self.assertEqual(rec['status'],'passed')
        s=review.load_state(self.root);self.assertIsNone(s['stages']['blocking'])
        s=review.confirm_stage(self.root,'blocking',s['revision'],'Synthetic user confirms video')
        self.assertTrue(review.stage_ready(self.root,s,'blocking'))
        s=review.apply_sync(self.root,self.packet())
        self.assertTrue(review.stage_ready(self.root,s,'blocking'))
        (folder/'output/critical-previs.blend').write_bytes(b'changed')
        self.assertFalse(review.stage_ready(self.root,s,'blocking'))
        self.assertFalse(review.view(self.root)['storyboard_prerequisites'])

    def test_coverage_smoke_and_stale_inputs_cannot_pass(self):
        base,coverage=self.bind()
        with self.assertRaisesRegex(ValueError,'尚未经过'):previs.confirmation_check(self.root,phase='blocking')
        job=read_json(base/'job.json');job['beats'].append({'id':'B2','duration':1,'action':'stop','start_state':'right','end_state':'right'})
        write_json(base/'job.json',job)
        with self.assertRaisesRegex(ValueError,'全部动作'):previs.bind(self.root,'blocking/adapter/build.py',coverage,phase='blocking')
        with self.assertRaisesRegex(ValueError,'输入已改变'):previs.fresh_job(self.root,phase='blocking')

    def test_shot_sync_keeps_upstream_but_explicit_layout_impact_invalidates(self):
        s=self.prepare();s=previs.choose(self.root,'skip',s['revision'],'Synthetic skip',phase='blocking')
        s=review.apply_sync(self.root,self.packet())
        self.assertTrue(review.stage_ready(self.root,s,'layout'))
        self.assertTrue(review.stage_ready(self.root,s,'blocking'))
        packet=self.packet();packet['shots'][0]['invalidate_layouts']=[load_project(self.root)['layouts'][0]['id']]
        s=review.apply_sync(self.root,packet)
        self.assertFalse(review.stage_ready(self.root,s,'layout'))
        self.assertFalse(review.stage_ready(self.root,s,'blocking'))

    def test_analysis_summary_without_chinese_shots_cannot_be_confirmed(self):
        m=load_project(self.root);m['shots']=[];m['assets']=[];m['gates']=[];write_json(self.root/'manifest.json',m)
        s=review.initialize(self.root,workflow='layout-first-v1')
        with self.assertRaisesRegex(ValueError,'中文导演稿'):
            review.confirm_stage(self.root,'analysis',s['revision'],'Synthetic premature approval')

    def test_blocking_reconfirmation_invalidates_old_director_audit(self):
        import director
        s=self.prepare();s=previs.choose(self.root,'skip',s['revision'],'Synthetic skip',phase='blocking')
        s=review.apply_sync(self.root,self.packet());s=self.audit()
        s=review.confirm_shot(self.root,'S1',s['revision'],'Synthetic user approves shot')
        self.assertTrue(review.is_approved(s,s['shots'][0]))
        s=previs.choose(self.root,'skip',s['revision'],'Synthetic new blocking decision',phase='blocking')
        self.assertFalse(director.ready(s,s['shots'][0]))
        with self.assertRaisesRegex(ValueError,'导演检查'):review.confirm_shot(self.root,'S1',s['revision'],'Cannot reuse old audit')
