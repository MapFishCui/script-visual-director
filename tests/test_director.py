import copy
import json
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from core import load_project, write_json
import review
import director
import test_review


class DirectorCase(unittest.TestCase):
    setUp = test_review.ReviewCase.setUp
    init = test_review.ReviewCase.init
    packet = test_review.ReviewCase.packet
    audit_packet = test_review.ReviewCase.audit_packet
    audit = test_review.ReviewCase.audit
    ready = test_review.ReviewCase.ready

    def test_legacy_draft_read_is_non_destructive_and_not_confirmable(self):
        review.initialize(self.root)
        path=self.root/review.STATE
        legacy=json.loads(path.read_text())
        for k in review.ADDED_FIELDS: legacy['shots'][0]['zh'].pop(k)
        write_json(path,legacy)
        saved=path.read_bytes()
        state=review.load_state(self.root)
        self.assertEqual(path.read_bytes(),saved)
        self.assertEqual(state['shots'][0]['zh']['delivery'],'')
        state=review.apply_sync(self.root,self.packet())
        state=review.confirm_stage(self.root,'analysis',state['revision'],'Test')
        self.assertEqual(review.view(self.root)['shots'][0]['status'],'needs_direction')
        with self.assertRaisesRegex(ValueError,'导演检查'):
            review.confirm_shot(self.root,'S1',state['revision'],'Test')
        before=path.read_bytes()
        with self.assertRaisesRegex(ValueError,'字段未完整'): self.audit()
        self.assertEqual(path.read_bytes(),before)

    def test_full_import_retains_per_line_delivery_and_structure(self):
        state=self.init()
        zh=copy.deepcopy(state['shots'][0]['zh'])
        zh['dialogue']='L1｜妈妈｜你怎么才来。\nL2｜爸爸｜路上堵车。'
        zh['delivery']='L1｜压抑的愤怒，低声，重读“才”。\nL2｜试探，语速稍慢，句尾收轻。'
        state=review.edit_shot(self.root,'S1',zh,state['revision'])
        self.assertEqual(review.sync_request(self.root)['shots'][0]['zh']['delivery'],zh['delivery'])
        self.assertEqual(review.view(self.root)['shots'][0]['zh']['delivery'],zh['delivery'])

    def test_complete_and_synced_is_not_editorially_approved(self):
        self.init();state=review.apply_sync(self.root,self.packet())
        state=review.confirm_stage(self.root,'analysis',state['revision'],'Test')
        self.assertTrue(review.is_synced(state,state['shots'][0]))
        self.assertFalse(director.report(self.root)['ready'])
        with self.assertRaises(ValueError): review.confirm_shot(self.root,'S1',state['revision'],'Test')
        state=self.audit()
        state=review.confirm_shot(self.root,'S1',state['revision'],'Test')
        self.assertTrue(review.is_approved(state,state['shots'][0]))

    def test_delivery_edit_invalidates_translation_and_director_review(self):
        state=self.ready()
        zh=copy.deepcopy(state['shots'][0]['zh'])
        zh['delivery']='L1｜害羞，轻声，回答前短暂停顿。'
        state=review.edit_shot(self.root,'S1',zh,state['revision'])
        self.assertFalse(review.is_synced(state,state['shots'][0]))
        self.assertFalse(director.report(self.root)['ready'])
        state=review.apply_sync(self.root,self.packet())
        with self.assertRaisesRegex(ValueError,'导演检查'):
            review.confirm_shot(self.root,'S1',state['revision'],'Test')

    def test_neighbor_change_invalidates_whole_sequence_review(self):
        m=load_project(self.root);s=copy.deepcopy(m['shots'][0]);s['id']='S2';m['shots'].append(s)
        for a in m['assets']:a['shots'].append('S2')
        write_json(self.root/'manifest.json',m)
        self.init();state=review.apply_sync(self.root,self.packet());state=self.audit()
        self.assertTrue(director.report(self.root)['ready'])
        packet=self.audit_packet()
        zh=copy.deepcopy(state['shots'][1]['zh']);zh['psychology']='得知对方已离开，停止等待。'
        state=review.edit_shot(self.root,'S2',zh,state['revision'])
        self.assertEqual(director.report(self.root)['shots'][0]['review_status'],'stale')
        packet['project_revision']=state['revision']
        with self.assertRaisesRegex(ValueError,'过期'): director.apply(self.root,packet)

    def test_analysis_edit_rejects_old_editorial_proof(self):
        self.init();review.apply_sync(self.root,self.packet());self.audit()
        packet=self.audit_packet()
        (self.root/'analysis.md').write_text('父亲的目的改变，不能再沿用原判断。')
        self.assertFalse(director.report(self.root)['ready'])
        with self.assertRaisesRegex(ValueError,'过期'):director.apply(self.root,packet)

    def test_revise_blocks_but_retains_specific_findings(self):
        self.init();state=review.apply_sync(self.root,self.packet())
        p=self.audit_packet();p['shots'][0]['checks']['pacing']={'status':'revise','note':'信息尚未出现，反应提前。'}
        director.apply(self.root,p)
        result=director.report(self.root)['shots'][0]
        self.assertFalse(result['ready'])
        self.assertEqual(result['review']['checks']['pacing']['note'],'信息尚未出现，反应提前。')

    def test_invalid_editorial_packet_cannot_partially_write(self):
        self.init();review.apply_sync(self.root,self.packet())
        path=self.root/review.STATE;before=path.read_bytes()
        p=self.audit_packet();p['shots'][0]['checks']['performance']['note']=''
        with self.assertRaises(ValueError):director.apply(self.root,p)
        self.assertEqual(path.read_bytes(),before)

    def test_old_browser_edit_preserves_new_fields(self):
        state=self.init();delivery=state['shots'][0]['zh']['delivery']
        zh={k:state['shots'][0]['zh'][k] for k in review.LEGACY_FIELDS+('duration',)}
        zh['description']='老页面的新画面修改'
        state=review.edit_shot(self.root,'S1',zh,state['revision'])
        self.assertEqual(state['shots'][0]['zh']['delivery'],delivery)

    def test_draft_save_allows_incomplete_new_fields(self):
        state=self.init();zh=copy.deepcopy(state['shots'][0]['zh']);zh['delivery']=''
        state=review.edit_shot(self.root,'S1',zh,state['revision'])
        self.assertEqual(review.load_state(self.root)['shots'][0]['zh']['delivery'],'')
        self.assertIn('缺少逐句台词语气',director.report(self.root)['shots'][0]['errors'])


if __name__=='__main__':unittest.main()


class WritingStandardsCase(unittest.TestCase):
    setUp = DirectorCase.setUp
    init = DirectorCase.init
    packet = DirectorCase.packet
    audit_packet = DirectorCase.audit_packet
    audit = DirectorCase.audit
    ready = DirectorCase.ready
    def test_vague_camera_reports_original_and_blocks_approval(self):
        self.init()
        state=review.load_state(self.root)
        zh=copy.deepcopy(state['shots'][0]['zh'])
        zh['camera']='固定中景，留足后退空间，切点落在视线将回手机时。'
        review.edit_shot(self.root,'S1',zh,state['revision'])
        review.apply_sync(self.root,self.packet())
        report=director.report(self.root)
        row=report['shots'][0]
        self.assertFalse(row['ready'])
        self.assertEqual(len(row['findings']),2)
        self.assertEqual(row['findings'][0]['excerpt'],zh['camera'])
        with self.assertRaisesRegex(ValueError,'规范未通过'): self.audit()

    def test_translation_order_is_checked(self):
        self.init()
        packet=self.packet()
        packet['shots'][0]['translation_zh']='场景：店内。人物运动：后退。镜头运动：固定中景。'
        review.apply_sync(self.root,packet)
        self.assertIn('camera-before-action', [f['rule'] for f in director.report(self.root)['shots'][0]['findings']])

    def test_old_audit_and_missing_standards_cannot_pass(self):
        self.ready()
        state=review.load_state(self.root)
        state['shots'][0]['director_review']['version']=1
        self.assertFalse(director.ready(state,state['shots'][0]))
        packet=self.audit_packet()
        del packet['shots'][0]['checks']['standards']
        with self.assertRaisesRegex(ValueError,'七项'): director.apply(self.root,packet)

    def test_standards_cannot_be_skipped(self):
        self.ready()
        packet=self.audit_packet()
        packet['shots'][0]['checks']['standards']={'status':'not_applicable','note':'skip'}
        with self.assertRaisesRegex(ValueError,'不能标记不适用'): director.apply(self.root,packet)
