from contextlib import closing
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from threading import Thread
from tempfile import TemporaryDirectory
import json,os,unittest
from unittest.mock import patch
from uuid import uuid4
import httpx
import jwt
from fastapi.testclient import TestClient
from app.main import create_app,SupabaseStore,DEMO_USER

class PerformanceTests(unittest.TestCase):
 def test_transport_reuses_connection_without_reusing_user_header(self):
  accepted=[];headers=[]
  class Server(ThreadingHTTPServer):
   daemon_threads=True
   def get_request(self):
    result=super().get_request();accepted.append(1);return result
  class Handler(BaseHTTPRequestHandler):
   protocol_version='HTTP/1.1'
   def do_GET(self):
    headers.append(self.headers.get('Authorization'))
    body=b'[]';self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
   def log_message(self,*args):pass
  with Server(('127.0.0.1',0),Handler) as server,patch.dict(os.environ,{'NO_PROXY':'127.0.0.1'}):
   thread=Thread(target=server.serve_forever,daemon=True);thread.start()
   store=SupabaseStore('http://127.0.0.1:'+str(server.server_port),'test-publishable')
   try:
    for token in ['user-A','user-B','user-A']:store.call('GET','/rest/v1/example',token)
    self.assertEqual(len(accepted),1);self.assertEqual(headers,['Bearer user-A','Bearer user-B','Bearer user-A'])
    self.assertNotIn('Authorization',store.client.headers)
   finally:store.close();server.shutdown();thread.join(timeout=2)

 def test_timing_headers_and_logs_exclude_credentials_and_payload(self):
  with TemporaryDirectory() as tmp,TestClient(create_app('local',tmp+'/local.db')) as local:
   document=local.get('/v3/workspace').json()['workspace']|{'requests':[]}
  def handler(request):
   if request.url.path=='/auth/v1/user':return httpx.Response(200,json={'id':DEMO_USER})
   if request.url.path=='/rest/v1/nextmeal_workspaces':return httpx.Response(200,json=[{'revision':0,'document':document}])
   if request.url.path=='/rest/v1/rpc/nextmeal_workspace_put':return httpx.Response(200,json={'saved':True})
   raise AssertionError(str(request.url))
  client=httpx.Client(transport=httpx.MockTransport(handler))
  token=jwt.encode({'private-marker':'private-user-token-marker'},'a-long-test-only-shared-secret-1234567890',algorithm='HS256')
  body={'request_id':str(uuid4()),'expected_revision':0,'action':'ingredient.create','payload':{'name':'PRIVATE-INGREDIENT-NAME','unit':'g'}}
  with patch.dict(os.environ,{'SUPABASE_URL':'https://test.supabase.co','SUPABASE_PUBLISHABLE_KEY':'private-key-marker'}),patch('app.main.httpx.Client',return_value=client),patch('app.timing.logger.info') as log:
   with TestClient(create_app('supabase')) as app:
    preview=app.post('/v3/preview?compact=true',json=body,headers={'Authorization':'Bearer '+token})
    saved=app.post('/v3/commands',json=body,headers={'Authorization':'Bearer '+token})
    self.assertEqual(preview.status_code,200,preview.text);self.assertEqual(saved.status_code,200,saved.text)
    self.assertEqual(preview.headers['X-Upstream-Requests'],'2');self.assertEqual(saved.headers['X-Upstream-Requests'],'3')
    self.assertEqual(saved.headers['X-Auth-Verification'],'remote-legacy')
    for stage in ['auth','db_read','db_write','compute','total']:self.assertIn(stage+';dur=',saved.headers['Server-Timing'])
    for response in [preview,saved]:self.assertNotIn('private-user-token-marker',str(response.headers))
   self.assertTrue(client.is_closed)
   records=str(log.call_args_list)
   for secret in ['private-key-marker','private-user-token-marker','PRIVATE-INGREDIENT-NAME',token]:self.assertNotIn(secret,records)
   self.assertIn('total_ms',records)

 def test_compact_preview_size_and_no_mutation(self):
  with TemporaryDirectory() as tmp,TestClient(create_app('local',tmp+'/local.db')) as app:
   state=app.get('/v3/workspace').json();body={'request_id':str(uuid4()),'expected_revision':state['revision'],'action':'ingredient.create','payload':{'name':'당근','unit':'g'}}
   response=app.post('/v3/preview?compact=true',json=body);self.assertEqual(response.status_code,200)
   self.assertNotIn('workspace',response.text)
   old_size=len(json.dumps({'summary':'추가','before':state,'after':state},ensure_ascii=False,separators=(',',':')).encode())
   self.assertLess(len(response.content),old_size/5)
   self.assertEqual(app.get('/v3/workspace').json(),state)
