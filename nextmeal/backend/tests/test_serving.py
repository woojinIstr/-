import os,tempfile,unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.serve import create_app

class ServingTests(unittest.TestCase):
 def test_single_origin_config_and_api(self):
  with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'APP_MODE':'local','APP_ENV':'development','SQLITE_PATH':tmp+'/test.db','SUPABASE_PUBLISHABLE_KEY':'must-not-be-exposed'}):
   with TestClient(create_app()) as c:
    self.assertEqual(c.get('/app-config').json(),{'mode':'local','url':'','key':'','api':''})
    self.assertEqual(c.get('/v3/workspace').status_code,200)
    # Build artifacts are optional in a source checkout; API is always available.
    r=c.get('/')
    if r.status_code==200:self.assertIn('<div id="root">',r.text)
 def test_secret_key_not_exposed(self):
  with patch.dict(os.environ,{'APP_MODE':'supabase','SUPABASE_URL':'https://example.supabase.co','SUPABASE_PUBLISHABLE_KEY':'sb_secret_invalid'}):
   with self.assertRaises(RuntimeError):create_app()
 def test_v3_requires_supabase_login(self):
  with patch.dict(os.environ,{'APP_MODE':'supabase','SUPABASE_URL':'https://example.supabase.co','SUPABASE_PUBLISHABLE_KEY':'sb_publishable_test'}):
   with TestClient(create_app()) as c:self.assertEqual(c.get('/v3/workspace').status_code,401)
