import copy
import json
from pathlib import Path
import sys
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_workflow
from core import current, load_project, package, queue, read_json, write_json
import review
import director
from review_server import make_server


class ReviewCase(unittest.TestCase):
    setUp = test_workflow.ProjectCase.setUp

    def init(self):
        m=load_project(self.root)
        storyboard={s['id']: {**{k:s.get(k,'') for k in review.FIELDS},
            'framing':'固定双人中景，正对餐桌', 'action':'父亲将碗放下，手离开碗',
            'camera':'固定机位', 'dialogue':'无台词', 'psychology':'测试场景：用餐动作，不作额外心理推断',
            'performance':'平静放碗，没有额外情绪动作', 'delivery':'无发声',
            'rhythm':'暂定 5 秒，放碗后停留，再切镜；仅测试用估算', 'duration':5} for s in m['shots']}
        return review.initialize(self.root,storyboard=storyboard)

    def packet(self, state=None):
        state = state or review.load_state(self.root)
        return {'project_revision': state['revision'], 'system': state['system'], 'shots': [
            {'id': s['id'], 'source_revision': s['revision'], 'text': '[Shot 1] Test-only camera instruction.', 'translation_zh': '仅供测试的镜头指令。',
             'check_note': 'Test fixture, not official syntax validation', 'impact_note': 'No downstream changes in this fixture',
             'invalidate_assets': [], 'invalidate_layouts': []} for s in state['shots']]}

    def audit_packet(self, state=None):
        report=director.report(self.root,state)
        return {k:report[k] for k in ('project_revision','context_hash','analysis_hash')} | {
            'sequence_note':'Synthetic test fixture; not a real editorial approval.',
            'shots':[{'id':s['id'],'checks':{k:{'status':'pass','note':'Synthetic fixture evidence for '+k} for k in director.CHECKS}} for s in report['shots']]}

    def audit(self, state=None):
        return director.apply(self.root,self.audit_packet(state))

    def ready(self):
        self.init()
        s=review.apply_sync(self.root, self.packet())
        s=self.audit(s)
        s=review.confirm_stage(self.root,'analysis',s['revision'],'Synthetic user confirmation')
        s=review.confirm_shot(self.root,'S1',s['revision'],'Synthetic user confirmation')
        s=review.confirm_stage(self.root,'layout',s['revision'],'No spatial scene in fixture')
        s=review.configure(self.root,previs={'required':False,'reason':'Static test fixture','files':[]})
        return review.confirm_stage(self.root,'previs',s['revision'],'Synthetic confirmation of exemption')

    def test_stage_gate_and_reedit_invalidates_confirmation(self):
        s=self.ready()
        self.assertEqual(review.blockers(self.root),[])
        self.assertTrue(next(r for r in queue(self.root) if r['id']=='DAD')['ready'])
        zh=copy.deepcopy(s['shots'][0]['zh']);zh['description']='新动作：左手抓紧柜台'
        changed=review.edit_shot(self.root,'S1',zh,s['revision'])
        self.assertFalse(review.is_approved(changed,changed['shots'][0]))
        self.assertFalse(next(r for r in queue(self.root) if r['id']=='DAD')['ready'])
        self.assertEqual(changed['shots'][0]['history'][-1]['snapshot']['zh']['description'],'family')
        self.assertTrue(changed['shots'][0]['target']['text'])
        with self.assertRaises(ValueError): review.confirm_shot(self.root,'S1',changed['revision'],'test')

    def test_stale_browser_write_preserves_first_editor(self):
        s=self.init(); a=copy.deepcopy(s['shots'][0]['zh']);b=copy.deepcopy(a)
        a['description']='Editor A';b['description']='Editor B'
        review.edit_shot(self.root,'S1',a,s['revision'])
        with self.assertRaisesRegex(ValueError,'版本冲突'): review.edit_shot(self.root,'S1',b,s['revision'])
        self.assertEqual(review.load_state(self.root)['shots'][0]['zh']['description'],'Editor A')

    def test_concurrent_writers_only_one_commits(self):
        s=self.init();out=[]
        def change(text):
            zh=copy.deepcopy(s['shots'][0]['zh']);zh['description']=text
            try:review.edit_shot(self.root,'S1',zh,s['revision']);out.append('ok')
            except ValueError:out.append('conflict')
        threads=[threading.Thread(target=change,args=(t,)) for t in ['A','B']]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertCountEqual(out,['ok','conflict'])

    def test_sync_packet_cannot_overwrite_new_chinese(self):
        s=self.init();packet=self.packet(s);zh=copy.deepcopy(s['shots'][0]['zh']);zh['camera']='缓慢推近'
        review.edit_shot(self.root,'S1',zh,s['revision'])
        before=(self.root/review.STATE).read_bytes()
        with self.assertRaises(ValueError):review.apply_sync(self.root,packet)
        self.assertEqual(before,(self.root/review.STATE).read_bytes())

    def test_invalid_sync_has_no_partial_commit(self):
        self.init();packet=self.packet();packet['shots'][0]['invalidate_assets']=['UNKNOWN']
        before=(self.root/'manifest.json').read_bytes()
        with self.assertRaises(ValueError):review.apply_sync(self.root,packet)
        self.assertEqual(before,(self.root/'manifest.json').read_bytes())
        self.assertEqual(review.load_state(self.root)['revision'],1)

    def test_confirmed_system_change_requires_resync(self):
        self.ready();system={'name':'Another system','mode':'reference','format':'generic','sources':[]}
        s=review.configure(self.root,system=system)
        self.assertFalse(review.is_synced(s,s['shots'][0]))
        self.assertTrue(review.blockers(self.root))

    def test_analysis_change_requires_new_shot_approval(self):
        self.ready();(self.root/'analysis.md').write_text('Updated narrative')
        s=review.load_state(self.root)
        self.assertFalse(review.stage_ready(self.root,s,'analysis'))
        s=review.confirm_stage(self.root,'analysis',s['revision'],'User approves changed narrative')
        self.assertFalse(review.is_approved(s,s['shots'][0]))
        self.assertFalse(review.stage_ready(self.root,s,'layout'))

    def test_impact_invalidates_indirect_assets(self):
        self.init();p=self.packet();p['shots'][0]['invalidate_assets']=['DAD'];review.apply_sync(self.root,p)
        assets=load_project(self.root)['assets']
        self.assertEqual(current(assets[0])['validity'],'stale')
        self.assertEqual(current(assets[2])['validity'],'stale')

    def test_external_manifest_change_is_detected(self):
        self.init();m=load_project(self.root);m['shots'][0]['description']='External change';write_json(self.root/'manifest.json',m)
        with self.assertRaisesRegex(ValueError,'页面外'):review.load_state(self.root)
        with self.assertRaises(ValueError):queue(self.root)

    def test_invalid_duration_unknown_fields_and_reimport(self):
        s=self.init()
        for value in (0,-1,float('nan'),True,999999):
            zh=copy.deepcopy(s['shots'][0]['zh']);zh['duration']=value
            with self.assertRaises(ValueError):review.edit_shot(self.root,'S1',zh,s['revision'])
        zh=copy.deepcopy(s['shots'][0]['zh']);zh['approved']=True
        with self.assertRaises(ValueError):review.edit_shot(self.root,'S1',zh,s['revision'])
        with self.assertRaises(ValueError):self.init()

    def test_draft_package_includes_edit_history(self):
        s=self.init();zh=copy.deepcopy(s['shots'][0]['zh']);zh['description']='Saved Chinese';review.edit_shot(self.root,'S1',zh,s['revision'])
        dest=self.base/'review.zip';package(self.root,dest,draft=True)
        with zipfile.ZipFile(dest) as z:
            state=json.loads(z.read('project-assets/review/state.json'))
            self.assertEqual(state['shots'][0]['zh']['description'],'Saved Chinese')
            self.assertTrue(state['shots'][0]['history'])
            self.assertNotIn('project-assets/review/write.lock',z.namelist())

    def test_duration_change_invalidates_later_cut_times(self):
        m=load_project(self.root); second=copy.deepcopy(m['shots'][0]);second['id']='S2';m['shots'].append(second)
        for a in m['assets']:a['shots'].append('S2')
        write_json(self.root/'manifest.json',m)
        self.init();s=review.apply_sync(self.root,self.packet())
        zh=copy.deepcopy(s['shots'][0]['zh']);zh['duration']=7
        s=review.edit_shot(self.root,'S1',zh,s['revision'])
        self.assertFalse(review.is_synced(s,s['shots'][1]))
        self.assertEqual([s['id'] for s in review.sync_request(self.root)['shots']],['S1','S2'])

    def test_spatial_generation_waits_for_storyboard_confirmation(self):
        self.init()
        with self.assertRaises(ValueError):review.require_phase(self.root,'render-layout')
        self.ready_after_init()
        review.require_phase(self.root,'render-layout')
        with self.assertRaises(ValueError):review.require_phase(self.root,'blockout')

    def ready_after_init(self):
        s=review.apply_sync(self.root,self.packet())
        s=self.audit(s)
        s=review.confirm_stage(self.root,'analysis',s['revision'],'Test')
        return review.confirm_shot(self.root,'S1',s['revision'],'Test')

    def test_translation_required_and_bound_to_confirmation(self):
        self.init();packet=self.packet();packet['shots'][0]['translation_zh']=''
        with self.assertRaises(ValueError):review.apply_sync(self.root,packet)
        s=review.apply_sync(self.root,self.packet())
        self.assertEqual(s['shots'][0]['target']['translation_zh'],'仅供测试的镜头指令。')
        del s['shots'][0]['target']['translation_zh']
        self.assertFalse(review.is_synced(s,s['shots'][0]))

    def test_http_roundtrip_auth_origin_and_file_scope(self):
        s=self.init();server=make_server(self.root,0,'test-token');thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        base=f'http://127.0.0.1:{server.server_port}'
        def request(path,data=None,token='test-token',origin=None):
            headers={'X-Review-Token':token}
            if origin:headers['Origin']=origin
            if data is not None:headers['Content-Type']='application/json'
            return urlopen(Request(base+path,headers=headers,data=json.dumps(data).encode() if data is not None else None),timeout=5)
        with request('/api/state') as r:self.assertEqual(json.load(r)['revision'],1)
        with self.assertRaises(HTTPError) as error:request('/api/state',token='bad')
        self.assertEqual(error.exception.code,403)
        zh=copy.deepcopy(s['shots'][0]['zh']);zh['description']='中文浏览器编辑'
        body={'id':'S1','zh':zh,'revision':1}
        with self.assertRaises(HTTPError):request('/api/edit',body,origin='https://other.example')
        with request('/api/edit',body) as r:self.assertEqual(json.load(r)['shots'][0]['zh']['description'],'中文浏览器编辑')
        with self.assertRaises(HTTPError):request('/api/file?path=../script.md')
        with self.assertRaises(HTTPError):request('/api/file?path=review/write.lock')
        with request('/api/file?path=source.md') as r:self.assertIn('父母',r.read().decode())
        with request('/') as r:self.assertIn('script-src',r.headers['Content-Security-Policy'])




class ProductionOverviewCase(unittest.TestCase):
    setUp = ReviewCase.setUp
    init = ReviewCase.init
    packet = ReviewCase.packet
    audit_packet = ReviewCase.audit_packet
    audit = ReviewCase.audit
    ready = ReviewCase.ready
    def test_asset_progress_changes_without_storyboard_revision(self):
        self.ready()
        before = review.view(self.root)
        test_workflow.ProjectCase.finish(self, 'DAD')
        after = review.view(self.root)
        self.assertEqual(before['revision'], after['revision'])
        self.assertNotEqual(before['display_fingerprint'], after['display_fingerprint'])
        self.assertEqual(after['production']['completed'], 1)
        self.assertFalse(after['production']['complete'])
        self.assertTrue(after['production']['assets'][0]['file'])

    def test_empty_asset_list_does_not_claim_completed(self):
        m = load_project(self.root)
        m['assets'] = []; m['gates'] = []; m['shots'][0]['assets'] = []
        write_json(self.root/'manifest.json', m)
        self.ready()
        result = review.view(self.root)
        self.assertEqual(result['production']['total'], 0)
        self.assertFalse(result['production']['complete'])

    def test_zip_is_downloaded_with_correct_mime(self):
        self.init()
        m = load_project(self.root)
        m['documents'].append({'path':'delivery.zip', 'role':'handoff'})
        write_json(self.root/'manifest.json', m)
        with zipfile.ZipFile(self.root/'delivery.zip', 'w') as out: out.writestr('test.txt', 'fixture')
        server=make_server(self.root,0,'test-token')
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        req=Request(f'http://127.0.0.1:{server.server_port}/api/file?path=delivery.zip',headers={'X-Review-Token':'test-token'})
        with urlopen(req) as response:
            self.assertEqual(response.headers['Content-Type'], 'application/zip')
            self.assertEqual(response.headers['Content-Disposition'], 'attachment')
            self.assertEqual(response.read(), (self.root/'delivery.zip').read_bytes())

    def test_progress_page_available_before_storyboard_without_initializing(self):
        m=load_project(self.root);m['shots']=[];m['assets']=[];m['gates']=[]
        write_json(self.root/'manifest.json',m)
        result=review.view(self.root)
        self.assertFalse(result['initialized'])
        self.assertEqual(result['shots'],[])
        self.assertFalse(result['production']['complete'])
        self.assertFalse((self.root/review.STATE).exists())
        server=make_server(self.root,0,'early-token')
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        req=Request(f'http://127.0.0.1:{server.server_port}/api/state',headers={'X-Review-Token':'early-token'})
        with urlopen(req) as response:self.assertFalse(json.load(response)['initialized'])

if __name__=='__main__':unittest.main()
