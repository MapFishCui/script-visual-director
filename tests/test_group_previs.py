import json
import unittest
from unittest.mock import patch
import test_previs_export
import previs_export
import groups
import group_previs
import group_package
import review


class GroupPrevisCase(unittest.TestCase):
    def test_group_video_uses_all_member_shots_and_invalidates_on_change(self):
        case=test_previs_export.ShotExportCase();case.setUp();self.addCleanup(case.doCleanups)
        case.fixture()
        with patch('previs.blender_path',return_value='synthetic'),patch('previs.invoke',side_effect=case.encoder):
            source=previs_export.export_shots(case.root,'previs/runs/synthetic')['index']
            packet={'revision':0,'project_revision':review.load_state(case.root)['revision'],'adapter':'aimixer-h3',
                    'shared_references':[],'groups':[{'id':'G01','title':'Test','shots':['S1','S2'],
                        'intent_zh':'Test only','continuity_in':'start','continuity_out':'end','references':[]}]}
            groups.apply(case.root,packet)
            result=group_previs.build(case.root,source)
        self.assertEqual(result['generated_groups'],1);self.assertEqual(result['missing_groups'],[])
        self.assertEqual([r['frames'] for r in case.requests],[120,120])
        ref={'key':'movement','kind':'video','index':result['index'],'item':'G01'}
        self.assertEqual(groups.resolve(case.root,ref)['seconds'],10)
        packet['revision']=groups.load(case.root)['revision'];packet['project_revision']=review.load_state(case.root)['revision']
        packet['groups'][0]['references']=[ref,dict(ref,key='duplicate_motion')]
        groups.apply(case.root,packet)
        self.assertTrue(any('合计不超过15秒' in p for p in groups.readiness(case.root)['pending']))
        with self.assertRaisesRegex(ValueError,'参考视频时长超限'):
            group_package.package(case.root,case.base/'bad.draft.mmxpack.zip',True)
        data=json.loads((case.root/result['index']).read_text())
        video=case.root/next(p for p in data['sha256'] if p.endswith('reference.mp4'))
        video.write_bytes(b'changed output')
        with self.assertRaisesRegex(ValueError,'文件已改变'):groups.resolve(case.root,ref)


if __name__=='__main__':unittest.main()
