import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import previs,review
from core import load_project,write_json,queue
from layout import layout_fingerprint
import test_review
import test_workflow


class PrevisCase(unittest.TestCase):
    setUp=test_workflow.ProjectCase.setUp
    init=test_review.ReviewCase.init
    packet=test_review.ReviewCase.packet
    audit_packet=test_review.ReviewCase.audit_packet
    audit=test_review.ReviewCase.audit
    ready_after_init=test_review.ReviewCase.ready_after_init

    def prepare(self, two=False):
        m=load_project(self.root);lay=test_workflow.example_layout();lay['cameras']=lay['cameras'][:1]
        lay['cameras'][0]['shot']='S1';lay['paths'][0]['shot']='S1'
        write_json(self.root/'layout.json',lay)
        m['layouts']=[dict(id=lay['id'],version=1,path='layout.json',outputs=[],review={'status':'passed','note':'Synthetic fixture'},blockout_required=True,blockout_review={'status':'pending','note':''})]
        m['shots'][0].update(layout={'id':lay['id'],'version':1},camera=lay['cameras'][0]['id'])
        m['assets'][0]['versions'][0]['dependencies']=[{'kind':'layout','id':lay['id'],'version':1}]
        if two:
            second=copy.deepcopy(m['shots'][0]);second.update(id='S2',layout=None,camera=None);m['shots'].append(second)
            for a in m['assets']:a['shots'].append('S2')
        write_json(self.root/'manifest.json',m)
        self.init();s=self.ready_after_init()
        if two:s=review.confirm_shot(self.root,'S2',s['revision'],'Synthetic second shot confirmation')
        return review.confirm_stage(self.root,'layout',s['revision'],'Synthetic layout confirmation')

    def adapter(self):
        base=self.root/'previs/adapter';base.mkdir(parents=True)
        (base/'build.py').write_text('# Synthetic adapter only; never claims Blender render\n')
        (base/'layout.json').write_bytes((self.root/'layout.json').read_bytes())
        job=dict(fps=12,clips=[dict(shot='S1',duration=5,original_start=0)],source_layout='layout.json',layout_fingerprint=layout_fingerprint(json.loads((self.root/'layout.json').read_text())),input_sha256={p.name:previs.sha(p) for p in base.iterdir()})
        write_json(base/'job.json',job)
        return 'previs/adapter/build.py'

    def test_skip_releases_complex_layout_without_forged_pass(self):
        s=self.prepare();self.assertFalse(queue(self.root)[0]['ready'])
        s=previs.choose(self.root,'skip',s['revision'],'Synthetic user explicitly skips')
        self.assertTrue(queue(self.root)[0]['ready'])
        self.assertTrue(review.stage_ready(self.root,s,'previs'))
        self.assertFalse(load_project(self.root)['layouts'][0]['blockout_required'])
        self.assertEqual(load_project(self.root)['layouts'][0]['blockout_review']['status'],'pending')
        s=previs.choose(self.root,'generate',s['revision'],'Synthetic user wants previs now')
        self.assertTrue(load_project(self.root)['layouts'][0]['blockout_required'])
        self.assertFalse(queue(self.root)[0]['ready'])
        self.assertIsNone(s['stages']['previs'])

    def test_choice_revision_and_context_invalidation(self):
        s=self.prepare();old=s['revision']
        s=previs.choose(self.root,'skip',old,'Synthetic skip')
        with self.assertRaisesRegex(ValueError,'版本冲突'):previs.choose(self.root,'generate',old,'Stale click')
        zh=copy.deepcopy(s['shots'][0]['zh']);zh['camera']='改成缓慢推镜'
        s=review.edit_shot(self.root,'S1',zh,s['revision'])
        self.assertFalse(review.stage_ready(self.root,s,'previs'))
        self.assertFalse(queue(self.root)[0]['ready'])

    def test_binding_rejects_wrong_timing_and_stale_inputs(self):
        s=self.prepare();previs.choose(self.root,'generate',s['revision'],'Synthetic generate')
        script=self.adapter();coverage={'required_shots':['S1'],'reason':'Synthetic full coverage'}
        previs.bind(self.root,script,coverage)
        self.assertEqual(previs.fresh_job(self.root)['fps'],12)
        path=self.root/script;path.write_text('# changed adapter')
        with self.assertRaisesRegex(ValueError,'输入已改变'):previs.fresh_job(self.root)
        with self.assertRaisesRegex(ValueError,'输入已变更'):previs.bind(self.root,script,coverage)
        job_path=path.parent/'job.json';job=json.loads(job_path.read_text());job['input_sha256']['build.py']=previs.sha(path);job['clips'][0]['original_start']=3;write_json(job_path,job)
        with self.assertRaisesRegex(ValueError,'时间必须'):previs.bind(self.root,script,coverage)

    def test_missing_blender_and_failure_do_not_complete_or_approve(self):
        self.assertFalse(previs.doctor(str(self.base/'missing-blender'))['available'])
        s=self.prepare();previs.choose(self.root,'generate',s['revision'],'Synthetic generate')
        previs.bind(self.root,self.adapter(),{'required_shots':['S1'],'reason':'Synthetic full coverage'})
        with patch('previs.blender_path',return_value='/synthetic/blender'),patch('previs.invoke',side_effect=ValueError('synthetic failure')):
            with self.assertRaisesRegex(ValueError,'synthetic failure'):previs.run(self.root,'render')
        last=json.loads((self.root/'previs/local-run.json').read_text());self.assertEqual(last['status'],'failed')
        self.assertIsNone(review.load_state(self.root)['stages']['previs'])
        with self.assertRaisesRegex(ValueError,'尚未经过'):previs.confirmation_check(self.root)

    def test_smoke_cannot_be_registered_as_video(self):
        s=self.prepare();previs.choose(self.root,'generate',s['revision'],'Synthetic generate')
        previs.bind(self.root,self.adapter(),{'required_shots':['S1'],'reason':'Synthetic full coverage'})
        folder=self.root/'previs/runs/smoke';folder.mkdir(parents=True)
        write_json(folder/'run.json',{'job':previs.fresh_job(self.root),'mode':'smoke'})
        with self.assertRaisesRegex(ValueError,'完整渲染'):previs.check_run(self.root,'previs/runs/smoke','Synthetic note')

    def rendered_fixture(self):
        from PIL import Image
        folder=self.root/'previs/runs/test-render';out=folder/'output';(out/'comparison').mkdir(parents=True)
        job=previs.fresh_job(self.root);count=job['fps']*5
        write_json(folder/'run.json',{'job':job,'mode':'render'})
        for i in range(1,count+1):Image.new('RGB',(32,16),'white').save(out/'comparison'/f'{i:06d}.png')
        (out/'critical-previs.blend').write_text('synthetic fixture')
        (out/'test.mp4').write_bytes(b'Synthetic metadata-test fixture; not a real movie.'*2)
        write_json(out/'render-report.json',{'rendered_frames':list(range(1,count+1)),'video':'test.mp4'})
        write_json(out/'frame-map.json',[{'frame':i,'shot':'S1','original_time':(i-1)/job['fps']} for i in range(1,count+1)])
        def fake_inspect(binary,script,args,log):
            req=json.loads(Path(args[0]).read_text());write_json(req['report'],{'frames':count,'size':[32,16],'fps':job['fps']})
        return fake_inspect

    def test_partial_scope_cannot_approve_and_missing_frames_rejected(self):
        s=self.prepare(two=True);previs.choose(self.root,'generate',s['revision'],'Synthetic generate')
        previs.bind(self.root,self.adapter(),{'required_shots':['S1','S2'],'reason':'Synthetic two-shot coverage'})
        inspect=self.rendered_fixture()
        with patch('previs.blender_path',return_value='synthetic'),patch('previs.invoke',side_effect=inspect):
            result=previs.check_run(self.root,'previs/runs/test-render','Synthetic partial review')
        self.assertEqual(result['status'],'partial');self.assertEqual(result['missing_shots'],['S2'])
        self.assertEqual(review.load_state(self.root)['previs']['files'],[])
        with self.assertRaises(ValueError):previs.confirmation_check(self.root)
        (self.root/'previs/runs/test-render/output/comparison/000003.png').unlink()
        with self.assertRaises(OSError):previs.check_run(self.root,'previs/runs/test-render','Synthetic note')

    def test_completed_check_needs_separate_user_confirmation_and_becomes_stale(self):
        s=self.prepare();previs.choose(self.root,'generate',s['revision'],'Synthetic generate')
        previs.bind(self.root,self.adapter(),{'required_shots':['S1'],'reason':'Synthetic coverage'})
        inspect=self.rendered_fixture()
        with patch('previs.blender_path',return_value='synthetic'),patch('previs.invoke',side_effect=inspect):
            result=previs.check_run(self.root,'previs/runs/test-render','Synthetic video review')
        s=review.load_state(self.root);self.assertEqual(result['status'],'passed');self.assertIsNone(s['stages']['previs'])
        s=review.confirm_stage(self.root,'previs',s['revision'],'Synthetic user confirmation')
        self.assertTrue(review.stage_ready(self.root,s,'previs'))
        (self.root/'previs/adapter/build.py').write_text('# new movement')
        self.assertFalse(review.stage_ready(self.root,s,'previs'))

    def test_browser_choice_endpoint_records_actual_selection(self):
        import threading
        from urllib.request import Request,urlopen
        from review_server import make_server
        s=self.prepare();server=make_server(self.root,0,'test-previs-token')
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            req=Request(f'http://127.0.0.1:{server.server_port}/api/previs-choice',data=json.dumps({'choice':'skip','revision':s['revision']}).encode(),headers={'Content-Type':'application/json','X-Review-Token':'test-previs-token'})
            with urlopen(req) as response:result=json.load(response)
            self.assertTrue(result['stage_status']['previs'])
            self.assertFalse(result['previs']['required'])
            self.assertEqual(result['pending'],[])
        finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
