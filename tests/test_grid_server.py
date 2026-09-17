import json,tempfile,threading,unittest,urllib.request,urllib.error
from pathlib import Path
import grid_workflow as grid
import grid_server

class GridServerTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'p';grid.run(self.root,'init')
  (self.root/'director.md').write_text('原导演稿',encoding='utf-8');grid.run(self.root,'register','director',['director.md'])
  self.server=grid_server.make_server(self.root);self.url='http://127.0.0.1:'+str(self.server.server_port)
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
 def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
 def request(self,path,data=None,authorized=True):
  headers={'X-Review-Token':self.server.review_token} if authorized else {}
  if data is not None:headers['Content-Type']='application/json'
  req=urllib.request.Request(self.url+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
  try:
   with urllib.request.urlopen(req) as r:return r.status,r.read()
  except urllib.error.HTTPError as e:return e.code,e.read()
 def state(self):return json.loads(self.request('/api/state')[1])
 def test_auth_confirmation_feedback_edit_and_stale_revision(self):
  self.assertEqual(self.request('/api/state',authorized=False)[0],403)
  s=self.state();rev=s['revision']
  code,_=self.request('/api/confirm',{'stage':'director','revision':rev});self.assertEqual(code,200)
  self.assertEqual(self.state()['status']['director'],'confirmed')
  self.assertEqual(self.request('/api/edit',{'stage':'director','revision':rev,'file':'director.md','text':'stale overwrite'})[0],409)
  s=self.state();self.assertEqual(self.request('/api/feedback',{'stage':'director','revision':s['revision'],'text':'调整节奏'})[0],200)
  s=self.state();self.assertEqual(s['status']['director'],'needs_revision')
  self.assertEqual(self.request('/api/confirm',{'stage':'director','revision':s['revision']})[0],409)
  self.assertEqual(self.request('/api/edit',{'stage':'director','revision':s['revision'],'file':'director.md','text':'修改后导演稿'})[0],200)
  self.assertEqual((self.root/'director.md').read_text(encoding='utf-8'),'修改后导演稿')
  self.assertEqual(self.state()['status']['director'],'awaiting_confirmation')
  self.assertIn('previous_text',json.dumps(json.loads((self.root/'grid-workflow.json').read_text())['history']))
 def test_external_change_prevents_confirmation_and_files_are_allowlisted(self):
  s=self.state();(self.root/'director.md').write_text('external',encoding='utf-8')
  self.assertNotEqual(s['revision'],self.state()['revision'])
  self.assertEqual(self.request('/api/confirm',{'stage':'director','revision':s['revision']})[0],409)
  self.assertEqual(self.request('/api/file?path=grid-workflow.json')[0],409)
  self.assertEqual(self.request('/api/file?path=director.md')[0],200)
  self.assertEqual(self.request('/api/file?path=../outside')[0],409)
