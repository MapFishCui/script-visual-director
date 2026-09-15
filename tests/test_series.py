"""Cross-episode synthetic image fixtures; no production approvals or images."""
import copy
import json
from pathlib import Path
import shutil
import unittest
import zipfile
from PIL import Image
import test_workflow
import test_review
import series
import review
from core import current, load_project, write_json, revise, validate_project, package


class SeriesCase(unittest.TestCase):
    def setUp(self):
        self.first=test_workflow.ProjectCase();self.first.setUp();self.addCleanup(self.first.doCleanups)
        self.second=test_workflow.ProjectCase();self.second.setUp();self.addCleanup(self.second.doCleanups)
        self.library=self.first.base/'library';series.initialize(self.library,'Synthetic series')

    def plan(self,aid='DAD',version=1,mode='reuse'):
        return {'episode':'EP02','items':[{'source_id':aid,'version':version,'target_id':aid,'shots':['S1'],
            'mode':mode,'continuity_note':'Synthetic same approved appearance and costume in a new episode'}]}

    def publish(self,ids=None):
        self.first.all_done()
        return series.publish(self.first.root,self.library,'EP01',ids or ['DAD'])

    def test_unfinished_source_and_invalid_version_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'不能入库'):series.publish(self.first.root,self.library,'EP01',['DAD'])
        self.publish();plan=self.plan();plan['items'][0]['version']='latest'
        with self.assertRaisesRegex(ValueError,'确切共享版本'):series.inherit(self.second.root,self.library,plan)

    def test_pin_survives_library_upgrade_and_project_move(self):
        self.publish();entry=series.load(self.library)['assets'][0]['versions'][0]
        result=series.inherit(self.second.root,self.library,self.plan())
        self.assertEqual(result['needs_review'],[])
        v=current(load_project(self.second.root)['assets'][0]);original=(self.second.root/v['file']).read_bytes()
        self.assertEqual(v['approval']['status'],'approved')
        self.assertEqual(v['approval']['evidence'],current(load_project(self.first.root)['assets'][0])['approval']['evidence'])
        revise(self.first.root,'DAD','Synthetic new hairstyle')
        Image.new('RGB',(32,32),'blue').save(self.first.picture);self.first.finish('DAD')
        series.publish(self.first.root,self.library,'EP01',['DAD'])
        self.assertEqual([x['version'] for x in series.load(self.library)['assets'][0]['versions']],[1,2])
        self.assertEqual(series.load(self.library)['assets'][0]['versions'][0],entry)
        self.assertEqual((self.second.root/v['file']).read_bytes(),original)
        moved=self.second.base/'moved';shutil.move(str(self.second.root),moved)
        shutil.move(str(self.library),self.first.base/'offline-library')
        self.assertTrue(series.verify(moved)['ok'])
        self.assertEqual(validate_project(moved)['errors'],[])
        self.assertEqual(series.view(moved)['items'][0]['library_version'],1)
        delivery=self.second.base/'episode2.zip';package(moved,delivery,draft=True)
        with zipfile.ZipFile(delivery) as archive:
            self.assertEqual(archive.read('project-assets/'+v['file']),original)
            self.assertTrue(any(name.startswith('project-assets/series/inheritance/') for name in archive.namelist()))

    def test_republish_idempotent_and_import_batch_is_atomic(self):
        self.publish(['DAD','MOM'])
        repeat=series.publish(self.first.root,self.library,'EP01',['DAD'])
        self.assertTrue(repeat['published'][0]['reused_snapshot'])
        before=(self.second.root/'manifest.json').read_bytes()
        bad=self.plan();bad['items']+=self.plan('MOM',999)['items']
        with self.assertRaisesRegex(ValueError,'不存在'):series.inherit(self.second.root,self.library,bad)
        self.assertEqual((self.second.root/'manifest.json').read_bytes(),before)
        self.assertFalse((self.second.root/'series').exists())
        series.inherit(self.second.root,self.library,self.plan())
        with self.assertRaisesRegex(ValueError,'不能覆盖'):series.inherit(self.second.root,self.library,self.plan())

    def test_tampering_detected_and_local_revision_preserves_source(self):
        self.publish();series.inherit(self.second.root,self.library,self.plan())
        asset=load_project(self.second.root)['assets'][0];file=self.second.root/current(asset)['file']
        original=file.read_bytes();revise(self.second.root,'DAD','Synthetic local change')
        self.assertTrue(series.verify(self.second.root)['ok'])
        file.write_bytes(b'changed')
        self.assertFalse(series.verify(self.second.root)['ok'])
        self.assertTrue(any('继承图片内容已改变' in x for x in validate_project(self.second.root)['errors']))
        file.write_bytes(original)
        entry=series.load(self.library)['assets'][0]['versions'][0]
        self.assertEqual((self.library/entry['file']).read_bytes(),original)

    def test_reference_requires_episode_review_and_existing_review_is_not_rewritten(self):
        self.publish();test_review.ReviewCase.init(self.second)
        before=(self.second.root/review.STATE).read_bytes()
        result=series.inherit(self.second.root,self.library,self.plan(mode='reference'))
        self.assertEqual(result['needs_review'],['DAD'])
        self.assertEqual((self.second.root/review.STATE).read_bytes(),before)
        view=review.view(self.second.root)
        asset=next(x for x in view['production']['assets'] if x['id']=='DAD')
        self.assertEqual(asset['inheritance']['source_episode'],'EP01')
        self.assertEqual(asset['approval']['status'],'pending')
        self.assertFalse(asset['complete'])
        bad=self.plan();bad['items'][0]['target_id']='NEW_ID'
        with self.assertRaisesRegex(ValueError,'先在本集声明'):series.inherit(self.second.root,self.library,bad)

    def test_scene_needs_local_layout_and_never_copies_spatial_approval(self):
        for case in (self.first,self.second):
            m=load_project(case.root);m['assets'][0]['type']='scene';write_json(case.root/'manifest.json',m)
        self.publish()
        with self.assertRaisesRegex(ValueError,'本集确切布局'):series.inherit(self.second.root,self.library,self.plan())
        m=load_project(self.second.root)
        m['layouts']=[{'id':'STORE','version':1,'path':'layout.json','outputs':[],
            'review':{'status':'pending','note':''},'blockout_required':False,
            'blockout_review':{'status':'pending','note':''}}]
        m['shots'][0]['layout']={'id':'STORE','version':1};write_json(self.second.root/'manifest.json',m)
        geometry=test_workflow.example_layout();geometry.update(id='STORE',version=1)
        write_json(self.second.root/'layout.json',geometry)
        plan=self.plan();plan['items'][0]['layout']={'id':'STORE','version':1}
        result=series.inherit(self.second.root,self.library,plan)
        v=current(load_project(self.second.root)['assets'][0])
        self.assertEqual(result['needs_review'],['DAD']);self.assertEqual(v['review']['status'],'pending')
        self.assertEqual(v['approval']['status'],'pending')
        self.assertIn({'kind':'layout','id':'STORE','version':1},v['dependencies'])

if __name__=='__main__':unittest.main()
