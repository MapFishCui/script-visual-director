"""Synthetic timing fixtures: no production script or media is approved here."""
import copy
import io
import json
import unittest
import zipfile
import test_groups
import test_review
import test_workflow
import groups
import group_package
import review
from core import load_project, write_json


class DirectorGroupCase(unittest.TestCase):
    setUp=test_workflow.ProjectCase.setUp
    finish=test_workflow.ProjectCase.finish
    all_done=test_workflow.ProjectCase.all_done
    init=test_review.ReviewCase.init
    packet=test_review.ReviewCase.packet
    audit_packet=test_review.ReviewCase.audit_packet
    audit=test_review.ReviewCase.audit
    compile_packet=test_groups.GroupsCase.compile_packet

    def prepare(self):
        m=load_project(self.root)
        m['shots']=[dict(copy.deepcopy(m['shots'][0]),id=f'S{i+1}') for i in range(8)]
        for a in m['assets']: a['shots']=[s['id'] for s in m['shots']]
        write_json(self.root/'manifest.json',m)
        self.all_done();s=self.init()
        for q,seconds in zip(list(s['shots']),[13,14,14,12,12,12,12,12]):
            zh=copy.deepcopy(q['zh']);zh['duration']=seconds
            s=review.edit_shot(self.root,q['id'],zh,s['revision'])
        s=review.apply_sync(self.root,self.packet());s=self.audit(s)
        s=review.confirm_stage(self.root,'analysis',s['revision'],'Synthetic fixture user approval')
        for q in s['shots']: s=review.confirm_shot(self.root,q['id'],s['revision'],'Synthetic fixture user approval')
        s=review.confirm_stage(self.root,'layout',s['revision'],'Synthetic fixture no spatial layout')
        s=review.configure(self.root,previs={'required':False,'reason':'Synthetic timing fixture','files':[]})
        s=review.confirm_stage(self.root,'previs',s['revision'],'Synthetic fixture skip')
        tasks=[{'id':f'T{i+1:02d}','title':f'Fixture task {i+1}','shots':[f'S{i+1}'],
            'intent_zh':'Synthetic task intent','continuity_in':'start','continuity_out':'end',
            'references':[{'key':'mom','kind':'image','asset':'MOM','version':1}]} for i in range(8)]
        directors=[{'id':f'D{i+1:02d}','title':f'Fixture director {i+1}','tasks':[g['id'] for g in tasks[i*4:(i+1)*4]],
            'intent_zh':'Synthetic complete dramatic passage','continuity_in':'start','continuity_out':'end'} for i in range(2)]
        plan={'revision':0,'project_revision':s['revision'],'adapter':'aimixer-h3','groups':tasks,'director_groups':directors,
            'shared_references':[{'key':'dad','kind':'image','asset':'DAD','version':1}]}
        groups.apply(self.root,plan);groups.sync(self.root,self.compile_packet())
        data=groups.load(self.root);groups.confirm(self.root,data['revision'],review.load_state(self.root)['revision'],'Synthetic fixture two director approvals')
        return plan

    def test_53_48_outputs_have_independent_native_timelines(self):
        self.prepare();result=groups.readiness(self.root)
        self.assertTrue(result['ready'],result['pending'])
        self.assertEqual([g['duration'] for g in result['director_groups']],[53,48])
        self.assertEqual(groups.request(self.root)['planning_limits']['max_task_seconds'],15)
        self.assertIsNone(groups.request(self.root)['planning_limits']['max_director_group_seconds'])
        out=self.base/'directors.zip';group_package.bundle(self.root,out)
        with zipfile.ZipFile(out) as outer:
            self.assertEqual([g['planned_seconds'] for g in json.loads(outer.read('director-groups.json'))],[53,48])
            for did,seconds,first in [('D01',53,'T01'),('D02',48,'T05')]:
                with zipfile.ZipFile(io.BytesIO(outer.read(did+'.mmxpack.zip'))) as native:
                    tasks=[json.loads(native.read(f'asset_groups/{i:04d}/group.json')) for i in range(1,5)]
                    self.assertEqual(tasks[0]['start'],0);self.assertEqual(tasks[0]['id'],first)
                    self.assertEqual(sum(t['durationSec'] for t in tasks),seconds)
                    for a,b in zip(tasks,tasks[1:]): self.assertEqual(b['start'],a['start']+a['length'])
                    self.assertEqual(json.loads(native.read('extra/director_group.json'))['output_file'],did+'.mp4')
        with self.assertRaisesRegex(ValueError,'多个导演组'):
            group_package.package(self.root,self.base/'ambiguous.mmxpack.zip')

    def test_invalid_parent_coverage_is_atomic_and_change_revokes_approval(self):
        plan=self.prepare();old=(self.root/groups.STATE).read_bytes()
        plan.update(revision=groups.load(self.root)['revision'],project_revision=review.load_state(self.root)['revision'])
        plan['director_groups'][1]['tasks'][0]='T01'
        with self.assertRaisesRegex(ValueError,'完整覆盖'):groups.apply(self.root,plan)
        self.assertEqual((self.root/groups.STATE).read_bytes(),old)
        plan['director_groups'][1]['tasks'][0]='T05';plan['director_groups'][0]['intent_zh']='Changed synthetic intent'
        groups.apply(self.root,plan)
        self.assertFalse(groups.view(self.root)['approved']);self.assertFalse(groups.load(self.root)['compiled'])
        q=review.load_state(self.root);zh=copy.deepcopy(q['shots'][0]['zh']);zh['duration']=20
        review.edit_shot(self.root,'S1',zh,q['revision'])
        with self.assertRaisesRegex(ValueError,'15 秒'):
            group_package.package(self.root,self.base/'overlong.draft.mmxpack.zip',True,'D01')

    def test_generic_long_output_and_legacy_read_only_migration(self):
        plan=self.prepare();plan.update(revision=groups.load(self.root)['revision'],project_revision=review.load_state(self.root)['revision'],adapter='generic')
        groups.apply(self.root,plan);out=self.base/'generic.zip';group_package.bundle(self.root,out,True)
        with zipfile.ZipFile(out) as z:self.assertIn('D01.zip',z.namelist())
        legacy=groups.load(self.root);legacy.pop('director_groups');legacy['schema_version']=1
        write_json(self.root/groups.STATE,legacy);before=(self.root/groups.STATE).read_bytes()
        self.assertTrue(any('导演组尚未规划' in p for p in groups.view(self.root)['pending']))
        self.assertFalse(groups.view(self.root)['approved'])
        self.assertEqual((self.root/groups.STATE).read_bytes(),before)

    def test_changed_treatment_revokes_prior_approvals(self):
        self.prepare();m=load_project(self.root);m['documents'].append({'path':'creative-treatment.md','role':'analysis'})
        (self.root/'creative-treatment.md').write_text('Synthetic director adaptation')
        write_json(self.root/'manifest.json',m)
        old=review.load_state(self.root)
        review.configure(self.root,analysis_files=old['analysis_files']+['creative-treatment.md'])
        new=review.load_state(self.root)
        self.assertFalse(review.stage_ready(self.root,new,'analysis'))
        self.assertFalse(groups.view(self.root)['approved'])
        self.assertTrue(all(s['approval'] is None for s in new['shots']))

if __name__=='__main__':unittest.main()
