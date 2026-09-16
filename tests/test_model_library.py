import io,json,tempfile,unittest,zipfile,shutil
from pathlib import Path
from unittest.mock import patch
import model_library as lib

class Response(io.BytesIO):
    url='https://example.org/model.zip'
class LibraryCase(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.cache=self.root/'cache'
        self.d={'id':'test','version':'1','title':'Test','author':'Author','source_url':'https://example.org','download_url':'https://example.org/model.zip','license':'CC0-1.0','license_url':'https://creativecommons.org/publicdomain/zero/1.0/','attribution':'Test Author'}
        self.descriptor=self.root/'d.json';lib.write(self.descriptor,self.d)
    def archive(self,name='model.blend'):
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w') as z:z.writestr(name,b'BLENDER-v-test');z.writestr('maps/image.png',b'image')
        return data.getvalue()
    def fetch(self):
        with patch('urllib.request.urlopen',return_value=Response(self.archive())):return lib.fetch('test',self.cache,self.descriptor)
    def test_cache_reuse_pin_and_tamper(self):
        self.assertFalse(self.fetch()['reused'])
        with patch('urllib.request.urlopen',side_effect=AssertionError('must not redownload')):self.assertTrue(lib.fetch('test',self.cache,self.descriptor)['reused'])
        project=self.root/'project';entry=lib.pin(project,'test','1',self.cache);self.assertEqual(entry['status'],'downloaded_unverified');self.assertTrue(lib.check_project(project)['valid'])
        (project/entry['directory']/'files/model.blend').write_bytes(b'tampered')
        with self.assertRaises(ValueError):lib.check_project(project)
    def test_archive_escape_and_missing_model(self):
        with patch('urllib.request.urlopen',return_value=Response(self.archive('../escape.blend'))):
            with self.assertRaises(ValueError):lib.fetch('test',self.cache,self.descriptor)
        self.assertFalse((self.cache/'test/1').exists())
        with patch('urllib.request.urlopen',return_value=Response(b'<html>login</html>')):
            with self.assertRaises(ValueError):lib.fetch('test',self.cache,self.descriptor)
    def test_failed_checksum_and_unknown_license(self):
        self.d['sha256']='0'*64;lib.write(self.descriptor,self.d)
        with patch('urllib.request.urlopen',return_value=Response(self.archive())):
            with self.assertRaises(ValueError):lib.fetch('test',self.cache,self.descriptor)
        self.d['license']='unknown';lib.write(self.descriptor,self.d)
        with self.assertRaises(ValueError):lib.fetch('test',self.cache,self.descriptor)
    def test_offline_restore_uses_pinned_version(self):
        self.fetch();project=self.root/'project';e=lib.pin(project,'test','1',self.cache);shutil.rmtree(project/e['directory'])
        with patch('urllib.request.urlopen',side_effect=AssertionError('offline')):self.assertTrue(lib.restore(project,self.cache)['valid'])

    def test_bundle_and_component_copy_preserve_lock_and_dependencies(self):
        import modeling
        self.fetch();project=self.root/'project';lib.pin(project,'test','1',self.cache)
        archive=self.root/'transfer.zip';lib.bundle(project,archive)
        other=self.root/'other';other.mkdir();lib.unpack(archive,other);self.assertTrue(lib.check_project(other)['valid'])
        spec={'schema_version':1,'components':[{'id':'actor','type':'asset','asset_key':'test@1','model':'model.blend','collection':'Actor','category':'actor','position':[0,0,0]}]}
        modeling.validate(spec);out=self.root/'render';out.mkdir();copied=modeling.materialize(spec,other,out)
        self.assertTrue((out/copied['components'][0]['file']).is_file())
        self.assertTrue((out/'MODEL-ASSET-CREDITS.txt').is_file())
        self.assertTrue((out/'model-assets/test/1/files/maps/image.png').is_file())
        self.assertNotIn('file',spec['components'][0])
        (other/'model-assets/test/1/files/maps/image.png').write_bytes(b'changed')
        with self.assertRaises(ValueError):modeling.materialize(spec,other,out)
