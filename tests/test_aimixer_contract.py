"""Opt-in test against a real checkout; no ComfyUI sampling or HTTP service.

SVD_AIMIXER_SOURCE=/path/to/ComfyUI_MiniMaxH3_Director enables this test.
Only host path lookup and aiohttp transport imports are stubbed. ZIP extraction,
timeline assembly, media copy and path rewriting run the upstream source unchanged.
"""
import importlib.util
import json
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

import test_groups
import group_package


class AIMixerContract(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('SVD_AIMIXER_SOURCE'), 'Set SVD_AIMIXER_SOURCE for actual upstream importer test')
    def test_real_importer_preserves_slots_prompts_and_media(self):
        case = test_groups.GroupsCase();case.setUp()
        self.addCleanup(case.doCleanups)
        case.synced(assets=True)
        target=case.base/'fixture.mmxpack.zip'
        group_package.package(case.root,target)
        source=Path(os.environ['SVD_AIMIXER_SOURCE']).resolve()
        name='_svd_aimixer_fixture'
        modules={}
        for suffix, directory in [('',source),('.director',source/'director'),('.lib',source/'lib')]:
            m=types.ModuleType(name+suffix);m.__path__=[str(directory)];modules[name+suffix]=m
        input_dir=case.base/'input';input_dir.mkdir()
        temp_dir=case.base/'temp';temp_dir.mkdir()
        paths=types.ModuleType('folder_paths')
        paths.get_input_directory=lambda:str(input_dir)
        paths.get_temp_directory=lambda:str(temp_dir)
        paths.get_output_directory=lambda:str(case.base/'output')
        transport=types.ModuleType('aiohttp');transport.web=types.SimpleNamespace()
        modules.update(folder_paths=paths,aiohttp=transport)
        with patch.dict(sys.modules,modules):
            spec=importlib.util.spec_from_file_location(name+'.director.pack',source/'director/pack.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            extracted=case.base/'extracted'
            module.extract_pack_zip(target,extracted)
            result=module.import_extracted_pack(extracted)
            self.assertEqual(result['missing'],[])
            timeline=result['timeline']
            self.assertEqual(timeline['timelineMode'],'prompt_batch')
            self.assertEqual(timeline['global']['refs'][0]['index'],0)
            segment=timeline['segments'][0]
            self.assertEqual(segment['refs'][0]['index'],1)
            self.assertEqual(segment['frameCount'],124)
            self.assertIn('<Picture 2>',segment['prompt'])
            for ref in timeline['global']['refs']+segment['refs']:
                self.assertTrue((input_dir/ref['imageFile']).is_file())
            self.assertEqual(json.loads((extracted/'extra/shot_map.json').read_text())[0]['shots'][0]['shot'],'S1')


if __name__=='__main__':unittest.main()
