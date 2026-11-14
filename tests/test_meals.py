import os, sqlite3, tempfile, unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import create_app, DEMO_USER, SupabaseStore
from app.catalog import recipe_id

class MealTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=self.tmp.name+'/test.db'
  self.client=TestClient(create_app('local',self.db))
  self.body={'meal_date':'2026-11-13','meal_slot':'dinner','recipe_id':recipe_id(3),'servings':1}
 def tearDown(self):self.client.close();self.tmp.cleanup()
 def add(self,**changes):
  r=self.client.post('/meals',json=self.body|changes);self.assertEqual(r.status_code,201,r.text);return r.json()
 def test_recipe_catalog(self):
  self.assertEqual(len(self.client.get('/recipes').json()),4)
  r=self.client.get('/recipes/'+recipe_id(1)).json()
  self.assertEqual(r['base_servings'],1);self.assertEqual(r['ingredients'][-1]['unit'],'ml')
  self.assertEqual(len(self.client.get('/ingredients').json()),8)
 def test_persistence_and_date_filter(self):
  m=self.add();self.add(meal_date='2026-11-14')
  self.assertEqual(len(self.client.get('/meals?meal_date=2026-11-13').json()),1)
  with TestClient(create_app('local',self.db)) as c:self.assertEqual(c.get('/meals/'+m['meal_id']).json()['recipe_id'],recipe_id(3))
 def test_patch_supplied_fields(self):
  m=self.add();r=self.client.patch('/meals/'+m['meal_id'],json={'expected_version':0,'servings':2})
  self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['meal_date'],m['meal_date'])
  self.assertEqual(r.json()['servings'],2);self.assertEqual(r.json()['version'],1)
 def test_invalid_payloads(self):
  for x in [{'servings':0},{'servings':True},{'servings':'1'},{'servings':13},{'meal_slot':'저녁'},{'meal_date':'2026-02-30'},{'user_id':DEMO_USER},{'meal_status':'cooked'}]:
   self.assertEqual(self.client.post('/meals',json=self.body|x).status_code,422)
  self.assertEqual(self.client.post('/meals',json=self.body|{'recipe_id':'90000000-0000-4000-8000-000000000001'}).status_code,404)
 def test_invalid_patch(self):
  m=self.add()
  for b in [{'expected_version':0},{'expected_version':0,'recipe_id':None},{'servings':2},{'expected_version':True,'servings':2},{'expected_version':0,'meal_status':'cooked'}]:
   self.assertEqual(self.client.patch('/meals/'+m['meal_id'],json=b).status_code,422)
 def test_out_cancel_preserve_inventory(self):
  self.client.post('/inventory',json={'ingredient_id':'10000000-0000-4000-8000-000000000001','quantity':300,'unit':'g','storage_location':'fridge'})
  before=self.client.get('/inventory').json()
  for action,status in [('eat-out','eating_out'),('cancel','cancelled')]:
   m=self.add();r=self.client.post('/meals/'+m['meal_id']+'/'+action,json={'expected_version':0})
   self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['meal_status'],status)
   self.assertEqual(self.client.get('/inventory').json(),before)
 def test_owner_isolation(self):
  m=self.add()
  with sqlite3.connect(self.db) as c:c.execute('UPDATE meals SET user_id=?',('other',))
  self.assertEqual(self.client.get('/meals').json(),[])
  self.assertEqual(self.client.get('/meals/'+m['meal_id']).status_code,404)
  for a in ['eat-out','cancel']:self.assertEqual(self.client.post('/meals/'+m['meal_id']+'/'+a,json={'expected_version':0}).status_code,404)
  self.assertEqual(self.client.patch('/meals/'+m['meal_id'],json={'expected_version':0,'servings':2}).status_code,404)
 def test_stale_update_terminal_state(self):
  m=self.add();url='/meals/'+m['meal_id']
  self.assertEqual(self.client.post(url+'/eat-out',json={'expected_version':0}).status_code,200)
  self.assertEqual(self.client.post(url+'/eat-out',json={'expected_version':0}).status_code,409)
  self.assertEqual(self.client.post(url+'/cancel',json={'expected_version':1}).status_code,409)
  self.assertEqual(self.client.patch(url,json={'expected_version':1,'servings':2}).status_code,409)
 def test_concurrent_actions(self):
  m=self.add();url='/meals/'+m['meal_id']
  with ThreadPoolExecutor(2) as pool:codes=list(pool.map(lambda a:self.client.post(url+'/'+a,json={'expected_version':0}).status_code,['eat-out','cancel']))
  self.assertEqual(sorted(codes),[200,409]);self.assertEqual(self.client.get(url).json()['version'],1)
 def test_supabase_owner_version_filter(self):
  m=self.add();updated=m|{'meal_status':'eating_out','version':1}
  with patch.dict(os.environ,{'SUPABASE_URL':'https://example.supabase.co','SUPABASE_PUBLISHABLE_KEY':'test'}):
   with patch.object(SupabaseStore,'user',return_value=DEMO_USER),patch.object(SupabaseStore,'request',side_effect=[[m],[updated]]) as req:
    with TestClient(create_app('supabase')) as c:r=c.post('/meals/'+m['meal_id']+'/eat-out',json={'expected_version':0},headers={'Authorization':'Bearer test-token'})
    self.assertEqual(r.status_code,200);args=req.call_args.args
    self.assertEqual(args[0],'PATCH');self.assertEqual(args[2],'test-token');self.assertEqual(args[3]['version'],'eq.0');self.assertEqual(args[3]['user_id'],'eq.'+DEMO_USER)
 def test_unknown_id(self):
  self.assertEqual(self.client.get('/meals/bad-id').status_code,422)
  self.assertEqual(self.client.get('/meals/90000000-0000-4000-8000-000000000001').status_code,404)
if __name__=='__main__':unittest.main()
