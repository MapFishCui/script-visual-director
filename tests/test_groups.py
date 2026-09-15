import copy
import json
from pathlib import Path
import unittest
import zipfile

import test_review
import test_workflow
import groups
import group_package
import review
from core import load_project, write_json


class GroupsCase(unittest.TestCase):
    setUp = test_workflow.ProjectCase.setUp
    finish = test_workflow.ProjectCase.finish
    all_done = test_workflow.ProjectCase.all_done
    init = test_review.ReviewCase.init
    packet = test_review.ReviewCase.packet
    audit_packet = test_review.ReviewCase.audit_packet
    audit = test_review.ReviewCase.audit
    ready = test_review.ReviewCase.ready

    def plan(self, adapter='aimixer-h3'):
        return {'revision': 0, 'project_revision': review.load_state(self.root)['revision'], 'adapter': adapter,
                'director_groups':[{'id':'D01','title':'Synthetic director group','tasks':['G01'],'intent_zh':'测试段落','continuity_in':'start','continuity_out':'end'}],
                'shared_references': [{'key':'dad','kind':'image','asset':'DAD','version':1}],
                'groups': [{'id':'G01','title':'Synthetic group','shots':['S1'],'intent_zh':'测试意图',
                            'continuity_in':'静止起始','continuity_out':'放下碗',
                            'references':[{'key':'mom','kind':'image','asset':'MOM','version':1}]}]}

    def compile_packet(self):
        request=groups.request(self.root)
        text=('subject_definitions:\n<Subject 1> is the father in <Picture 1>; <Picture 2> provides the mother.\n'
              'summary:\nSynthetic test.\nretention_analysis:\nTest-only refs.\ndetailed_description:\n'
              '[Shot 1] A static test shot.\noverall_soundscape:\nSilence.\nnon_diegetic_music:\nNone.')
        return {k:request[k] for k in ('revision','project_revision','storyboard_fingerprint')} | {
            'groups':[{'id':g['id'],'text':text,'translation_zh':'仅供测试：父亲与母亲同处固定画面，无声无配乐。',
                       'check_note':'Synthetic contract fixture; not real director review.'} for g in request['groups']]}

    def synced(self, assets=False):
        if assets:self.all_done()
        self.ready(); groups.apply(self.root,self.plan()); groups.sync(self.root,self.compile_packet())
        state=groups.load(self.root)
        groups.confirm(self.root,state['revision'],review.load_state(self.root)['revision'],'Synthetic user group confirmation')

    def test_complete_native_pack_and_shared_slot_numbering(self):
        self.synced(assets=True)
        path=self.base/'complete.mmxpack.zip'
        result=group_package.package(self.root,path)
        self.assertEqual(result['status'],'ready_for_import_test')
        with zipfile.ZipFile(path) as z:
            self.assertEqual(json.loads(z.read('pack.json'))['format'],'minimax-h3-director-pack')
            self.assertIn('shared_params/Picture1.png',z.namelist())
            self.assertIn('asset_groups/0001/Picture2.png',z.namelist())
            group=json.loads(z.read('asset_groups/0001/group.json'))
            self.assertEqual(group['refs'][0]['index'],1)
            self.assertEqual(group['frameCount'],124)
            self.assertFalse(group['continuityFromPrev'])
            self.assertIn('仅供测试',z.read('extra/shot_map.json').decode())
            self.assertFalse(json.loads(z.read('extra/delivery.json'))['target_h3_validated'])
        with self.assertRaisesRegex(ValueError,'已存在'):group_package.package(self.root,path)

    def test_missing_media_only_allows_explicit_draft(self):
        self.synced()
        path=self.base/'missing.draft.mmxpack.zip'
        with self.assertRaisesRegex(ValueError,'正式导出'):group_package.package(self.root,path)
        result=group_package.package(self.root,path,True)
        self.assertEqual(result['status'],'draft');self.assertTrue(result['pending'])
        with zipfile.ZipFile(path) as z:
            self.assertFalse(any(n.endswith('.png') for n in z.namelist()))
            self.assertEqual(json.loads(z.read('asset_groups/0001/group.json'))['refs'],[])

    def test_group_and_source_changes_invalidate_confirmation_and_old_packets(self):
        self.synced(assets=True)
        old=groups.request(self.root)
        s=review.load_state(self.root);zh=copy.deepcopy(s['shots'][0]['zh']);zh['duration']=6
        review.edit_shot(self.root,'S1',zh,s['revision'])
        self.assertFalse(groups.approved(self.root,groups.load(self.root)))
        with self.assertRaises(ValueError):group_package.package(self.root,self.base/'stale.mmxpack.zip')
        data=self.compile_packet();data['revision']=old['revision'];data['project_revision']=old['project_revision']
        with self.assertRaises(ValueError):groups.sync(self.root,data)

    def test_invalid_group_coverage_and_undefined_slots_are_atomic(self):
        self.ready();packet=self.plan();packet['groups'][0]['shots']=['S1','S1']
        with self.assertRaises(ValueError):groups.apply(self.root,packet)
        self.assertFalse((self.root/groups.STATE).exists())
        groups.apply(self.root,self.plan());data=self.compile_packet();data['groups'][0]['text']+='<Picture 8>'
        before=(self.root/groups.STATE).read_bytes()
        with self.assertRaisesRegex(ValueError,'未绑定槽位'):groups.sync(self.root,data)
        self.assertEqual(before,(self.root/groups.STATE).read_bytes())

    def test_adapter_change_keeps_shots_and_invalidates_compiled_text(self):
        self.synced(assets=True);old=groups.load(self.root);packet=self.plan('generic')
        packet['revision']=old['revision'];groups.apply(self.root,packet)
        new=groups.load(self.root)
        self.assertEqual(new['groups'],old['groups']);self.assertEqual(new['compiled'],{})
        self.assertIsNone(new['approval'])

    def test_group_local_cut_times_restart_at_zero(self):
        m=load_project(self.root);second=copy.deepcopy(m['shots'][0]);second['id']='S2';m['shots'].append(second)
        for a in m['assets']:a['shots'].append('S2')
        write_json(self.root/'manifest.json',m);self.init()
        packet=self.plan();packet['groups'][0]['shots']=['S1','S2'];groups.apply(self.root,packet)
        request=groups.request(self.root)
        self.assertEqual([c['local_start'] for c in request['groups'][0]['cuts']],[0,5])
        packet=self.compile_packet();packet['groups'][0]['text']=packet['groups'][0]['text'].replace('overall_soundscape:', '[Shot 2] At 00:06.000, Incorrect time.\noverall_soundscape:')
        with self.assertRaisesRegex(ValueError,'切镜时刻'):groups.sync(self.root,packet)
        packet['groups'][0]['text']=packet['groups'][0]['text'].replace('00:06.000','00:05.000')
        groups.sync(self.root,packet)

    def test_browser_group_confirmation_and_stale_edit(self):
        import threading
        from urllib.request import Request,urlopen
        from urllib.error import HTTPError
        from review_server import make_server
        self.ready();groups.apply(self.root,self.plan());groups.sync(self.root,self.compile_packet())
        server=make_server(self.root,0,'synthetic-group-token')
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            data={'revision':groups.load(self.root)['revision'],'project_revision':review.load_state(self.root)['revision']}
            req=Request(f'http://127.0.0.1:{server.server_port}/api/groups-confirm',data=json.dumps(data).encode(),headers={'Content-Type':'application/json','X-Review-Token':'synthetic-group-token'})
            with urlopen(req) as response:state=json.load(response)
            self.assertTrue(state['generation_groups']['approved'])
            with self.assertRaises(HTTPError) as error:urlopen(req)
            self.assertEqual(error.exception.code,409)
        finally:
            server.shutdown();server.server_close();thread.join()




class PlanningLimitCase(unittest.TestCase):
    setUp = GroupsCase.setUp
    init = GroupsCase.init
    packet = GroupsCase.packet
    audit_packet = GroupsCase.audit_packet
    audit = GroupsCase.audit
    ready = GroupsCase.ready
    plan = GroupsCase.plan
    compile_packet = GroupsCase.compile_packet
    synced = GroupsCase.synced
    def test_twenty_second_h3_plan_rejected_before_persisting(self):
        self.ready()
        s=review.load_state(self.root);zh=copy.deepcopy(s['shots'][0]['zh']);zh['duration']=20
        review.edit_shot(self.root, 'S1', zh, s['revision'])
        with self.assertRaisesRegex(ValueError, '15 秒'):
            groups.apply(self.root, self.plan())
        self.assertFalse((self.root/groups.STATE).exists())
        generic=groups.apply(self.root, self.plan('generic'))
        self.assertEqual(generic['schedule'][0]['duration'],20)

    def test_legacy_overlong_group_cannot_remain_approved(self):
        self.synced()
        s=review.load_state(self.root);zh=copy.deepcopy(s['shots'][0]['zh']);zh['duration']=20
        review.edit_shot(self.root,'S1',zh,s['revision'])
        data=groups.load(self.root)
        self.assertTrue(any('15 秒' in msg for msg in groups.planning_pending(self.root,data)))
        self.assertFalse(groups.approved(self.root,data))
        with self.assertRaisesRegex(ValueError, '15 秒'):
            review.require_phase(self.root,'blockout')

    def test_fifteen_second_budget_is_allowed(self):
        self.ready()
        state=review.load_state(self.root);zh=copy.deepcopy(state['shots'][0]['zh']);zh['duration']=15
        review.edit_shot(self.root,'S1',zh,state['revision'])
        result=groups.apply(self.root,self.plan())
        self.assertEqual(result['schedule'][0]['duration'],15)
        self.assertEqual(groups.plan_limits(self.root,groups.load(self.root)),[])

if __name__=='__main__':unittest.main()
