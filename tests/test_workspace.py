from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date, timedelta
import tempfile
import unittest
from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import create_app, SEEDS
from app.workspace import today

class WorkspaceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=self.tmp.name+'/test.db';self.app=create_app('local',self.path);self.client=TestClient(self.app)
  self.chicken=SEEDS[0]['ingredient_id'];self.milk=SEEDS[4]['ingredient_id'];self.egg=SEEDS[2]['ingredient_id'];self.rice=SEEDS[3]['ingredient_id']
 def tearDown(self):self.client.close();self.tmp.cleanup()
 def state(self):
  r=self.client.get('/v3/workspace');self.assertEqual(r.status_code,200,r.text);return r.json()
 def command(self,action,payload,code=200,**opts):
  body={'request_id':str(uuid4()),'expected_revision':self.state()['revision'],'action':action,'payload':payload}|opts
  r=self.client.post('/v3/commands',json=body);self.assertEqual(r.status_code,code,r.text);return r.json()
 def lot(self,ingredient=None,q=100,**opts):
  p={'ingredient_id':ingredient or self.chicken,'input_quantity':q,'input_unit':'g','purchased_on':today()}|opts
  return self.command('lot.create',p)['workspace']['inventory'][-1]
 def recipe(self,parts=None,**opts):
  p={'name':'내 요리','base_servings':1,'minutes':10,'ingredients':parts or [{'ingredient_id':self.chicken,'quantity':100,'unit':'g'}]}|opts
  return self.command('recipe.save',p)['workspace']['recipes'][-1]
 def meal(self,r=None,**opts):
  r=r or self.recipe();p={'date':today(),'slot':'dinner','recipe_id':r['id'],'servings':1}|opts
  return self.command('meal.save',p)['workspace']['meals'][-1]
 def test_all_units_and_package_reuse(self):
  examples=[(self.chicken,10,100,'g',1000),(self.milk,2,900,'ml',1800),(self.egg,2,30,'count',60),(self.rice,2,10,'kg',20000)]
  for ing,q,size,unit,expected in examples:
   lot=self.lot(ing,q,input_unit='pack',pack_size=size,content_unit=unit,pack_label='포장',save_product=True,name='내 제품')
   self.assertEqual(lot['quantity'],expected)
   product=self.state()['workspace']['products'][-1]
   repeat=self.lot(ing,1,input_unit='pack',product_id=product['id']);self.assertEqual(repeat['quantity'],expected/q)
 def test_decimal_packages(self):
  l=self.lot(q=3,input_unit='pack',pack_size=0.1,content_unit='kg');self.assertEqual(l['quantity'],300)
  self.command('lot.use',{'id':l['id'],'quantity':0.1,'reason':'use'})
  self.assertEqual(self.state()['workspace']['inventory'][0]['quantity'],299.9)
 def test_cross_dimension_and_invalid_quantity(self):
  for changes in [{'input_unit':'ml'},{'input_unit':'pack'},{'input_quantity':True},{'input_quantity':'10'},{'input_quantity':-1},{'input_quantity':1e9,'input_unit':'kg'}]:
   self.command('lot.create',{'ingredient_id':self.chicken,'input_quantity':1,'input_unit':'g','purchased_on':today()}|changes,422)
 def test_ingredient_create_and_duplicate(self):
  self.command('ingredient.create',{'name':'양파(개수)','unit':'count'})
  self.command('ingredient.create',{'name':'양파 (개수)','unit':'count'},409)
 def test_dates(self):
  self.command('lot.create',{'ingredient_id':self.chicken,'input_quantity':1,'input_unit':'g','purchased_on':(date.fromisoformat(today())+timedelta(days=1)).isoformat()},422)
  self.command('lot.create',{'ingredient_id':self.chicken,'input_quantity':1,'input_unit':'g','purchased_on':today(),'expires_on':'2000-01-01'},422)
 def test_preview_no_write(self):
  before=self.state();body={'request_id':str(uuid4()),'expected_revision':before['revision'],'action':'ingredient.create','payload':{'name':'당근','unit':'g'}}
  r=self.client.post('/v3/preview',json=body);self.assertEqual(r.status_code,200,r.text);self.assertEqual(len(r.json()['after']['workspace']['ingredients']),9);self.assertEqual(self.state(),before)
 def test_idempotent_and_key_mismatch(self):
  body={'request_id':str(uuid4()),'expected_revision':0,'action':'ingredient.create','payload':{'name':'당근','unit':'g'}}
  a=self.client.post('/v3/commands',json=body);b=self.client.post('/v3/commands',json=body)
  self.assertEqual(a.status_code,200,a.text);self.assertEqual(b.status_code,200,b.text);self.assertTrue(b.json()['replayed']);self.assertEqual(b.json()['revision'],1)
  self.assertEqual(self.client.post('/v3/commands',json=body|{'payload':{'name':'감자','unit':'g'}}).status_code,409)
 def test_concurrent_changes_and_same_request(self):
  self.state()
  def submit(body):return self.client.post('/v3/commands',json=body).status_code
  base={'expected_revision':0,'action':'ingredient.create'}
  bodies=[base|{'request_id':str(uuid4()),'payload':{'name':name,'unit':'g'}} for name in ['당근','감자']]
  with ThreadPoolExecutor(2) as p:self.assertEqual(sorted(p.map(submit,bodies)),[200,409])
  rev=self.state()['revision'];same={'request_id':str(uuid4()),'expected_revision':rev,'action':'ingredient.create','payload':{'name':'대파','unit':'g'}}
  with ThreadPoolExecutor(2) as p:self.assertEqual(list(p.map(submit,[same,same])),[200,200])
  self.assertEqual(self.state()['revision'],rev+1)
 def test_recipe_snapshot_and_archival(self):
  r=self.recipe();m=self.meal(r)
  self.command('recipe.save',{k:v for k,v in r.items() if k!='archived'}|{'name':'변경된 요리','ingredients':[{'ingredient_id':self.chicken,'quantity':500,'unit':'g'}]})
  self.assertEqual(self.state()['workspace']['meals'][0]['recipe']['ingredients'][0]['quantity'],100)
  self.command('recipe.archive',{'id':r['id']})
  self.command('meal.save',{'id':m['id'],'date':m['date'],'slot':m['slot'],'recipe_id':r['id'],'servings':2})
  self.command('recipe.restore',{'id':r['id']})
 def test_recipe_invalid_duplicate_parts(self):
  p={'name':'요리','base_servings':1,'minutes':10,'ingredients':[{'ingredient_id':self.chicken,'quantity':1,'unit':'g'}]*2}
  self.command('recipe.save',p,422)
 def test_cook_deducts_fefo_and_no_double_deduction(self):
  day=date.fromisoformat(today());early=(day+timedelta(days=1)).isoformat();late=(day+timedelta(days=3)).isoformat()
  a=self.lot(q=80,expires_on=late);b=self.lot(q=80,expires_on=early);m=self.meal()
  result=self.command('meal.cook',{'id':m['id'],'usage':[{'ingredient_id':self.chicken,'quantity':100,'unit':'g'}]})
  lots={l['id']:l['quantity'] for l in result['workspace']['inventory']};self.assertEqual(lots[b['id']],0);self.assertEqual(lots[a['id']],60)
  before=self.state();self.command('meal.cook',{'id':m['id'],'usage':[{'ingredient_id':self.chicken,'quantity':100,'unit':'g'}]},409);self.assertEqual(self.state(),before)
 def test_partial_failure_rolls_back(self):
  self.lot(q=500);m=self.meal(self.recipe([{'ingredient_id':self.chicken,'quantity':100,'unit':'g'},{'ingredient_id':self.milk,'quantity':100,'unit':'ml'}]))
  before=self.state();self.command('meal.cook',{'id':m['id'],'usage':[{'ingredient_id':self.chicken,'quantity':100,'unit':'g'},{'ingredient_id':self.milk,'quantity':100,'unit':'ml'}]},409);self.assertEqual(self.state(),before)
 def test_usage_waste_and_archive_restore(self):
  l=self.lot(q=100);self.command('lot.use',{'id':l['id'],'quantity':20,'reason':'waste'});self.assertEqual(self.state()['workspace']['inventory'][0]['quantity'],80)
  self.command('lot.use',{'id':l['id'],'quantity':81,'reason':'use'},409)
  self.command('lot.archive',{'id':l['id']});self.assertTrue(self.state()['workspace']['inventory'][0]['archived'])
  self.command('lot.restore',{'id':l['id']});self.assertFalse(self.state()['workspace']['inventory'][0]['archived'])
 def test_out_cancel_restore_preserves_inventory(self):
  self.lot(q=100);m=self.meal();before=deepcopy(self.state()['workspace']['inventory'])
  for status in ['eating_out','planned','cancelled','planned']:
   result=self.command('meal.state',{'id':m['id'],'status':status});self.assertEqual(result['workspace']['inventory'],before)
 def test_shopping_does_not_reuse_stock(self):
  self.lot(q=150);r=self.recipe();self.meal(r,slot='breakfast');self.meal(r,slot='dinner')
  self.assertEqual(self.state()['shopping'][0]['shortage'],50)
 def test_stock_expiring_before_meal_not_available(self):
  day=date.fromisoformat(today());self.lot(q=100,expires_on=today());self.meal(date=(day+timedelta(days=1)).isoformat())
  self.assertEqual(self.state()['shopping'][0]['shortage'],100)
 def test_meal_repeat_copy_no_duplicates(self):
  m=self.meal(repeat_days=2);self.assertEqual(len(self.state()['workspace']['meals']),2)
  self.command('meal.copy',{'source_date':today(),'days':2});self.assertEqual(len(self.state()['workspace']['meals']),3)
  self.command('meal.copy',{'source_date':today(),'days':2});self.assertEqual(len(self.state()['workspace']['meals']),3)
 def test_manual_purchase_is_atomic(self):
  r=self.command('shopping.add',{'name':'닭가슴살','quantity':2,'unit':'팩'});manual=r['workspace']['manual'][0]
  self.lot(q=2,input_unit='pack',pack_size=100,content_unit='g',manual_id=manual['id'])
  self.assertTrue(self.state()['workspace']['manual'][0]['checked']);self.assertEqual(self.state()['workspace']['inventory'][0]['quantity'],200)
 def test_completed_shopping_cannot_be_received_twice(self):
  item=self.command('shopping.add',{'name':'달걀','quantity':2,'unit':'판'})['workspace']['manual'][0]
  lot=self.lot(self.egg,2,input_unit='pack',pack_size=30,content_unit='count',manual_id=item['id'])
  before=self.state()
  self.assertEqual(before['workspace']['manual'][0]['received_lot_id'],lot['id'])
  self.command('lot.create',{'ingredient_id':self.egg,'input_quantity':2,'input_unit':'pack',
               'pack_size':30,'content_unit':'count','manual_id':item['id'],'purchased_on':today()},409)
  self.assertEqual(self.state(),before)
 def test_purchase_new_ingredient_preview_replay_and_reuse(self):
  item=self.command('shopping.add',{'name':'두부','quantity':2,'unit':'모'})['workspace']['manual'][0]
  before=self.state()
  payload={'new_ingredient':{'name':'두부','unit':'count'},'manual_id':item['id'],'input_quantity':2,
           'input_unit':'pack','pack_label':'모','pack_size':1,'content_unit':'count','purchased_on':today()}
  command={'request_id':str(uuid4()),'expected_revision':before['revision'],'action':'lot.create','payload':payload}
  preview=self.client.post('/v3/preview?compact=true',json=command).json()
  change=preview['inventory_changes'][0]
  self.assertEqual((change['name'],change['before'],change['after'],change['unit']),('두부',0,2,'count'))
  self.assertEqual(self.state(),before)
  saved=self.client.post('/v3/commands',json=command).json()
  self.assertTrue(saved['workspace']['manual'][0]['checked'])
  self.assertTrue(self.client.post('/v3/commands',json=command).json()['replayed'])
  self.assertEqual(len(self.state()['workspace']['inventory']),1)
  payload=dict(payload,new_ingredient={'name':'두 부','unit':'count'},manual_id=None)
  stock=self.command('lot.create',payload)['workspace']
  self.assertEqual(len(stock['ingredients']),len(before['workspace']['ingredients'])+1)
  self.assertEqual(stock['inventory'][0]['ingredient_id'],stock['inventory'][1]['ingredient_id'])
 def test_purchase_errors_leave_no_new_ingredient_or_stock(self):
  before=self.state()
  p={'new_ingredient':{'name':'두부','unit':'count'},'input_quantity':2,'input_unit':'count','purchased_on':today()}
  for fields,code in [
   ({'manual_id':str(uuid4())},404),({'ingredient_id':self.chicken},422),
   ({'new_ingredient':None},422),({'input_unit':'g'},422),({'product_id':str(uuid4())},422),
   ({'new_ingredient':{'name':'닭가슴살','unit':'count'}},409)]:
   self.command('lot.create',p|fields,code)
  self.assertEqual(self.state(),before)
 def test_conflict_header_only_for_outdated_revision(self):
  self.command('ingredient.create',{'name':'당근','unit':'g'})
  command={'request_id':str(uuid4()),'expected_revision':0,'action':'ingredient.create','payload':{'name':'당근','unit':'g'}}
  for endpoint in ['/v3/preview?compact=true','/v3/commands']:
   stale=self.client.post(endpoint,json=command)
   self.assertEqual(stale.status_code,409)
   self.assertEqual(stale.headers.get('X-Conflict-Reason'),'revision')
   duplicate=self.client.post(endpoint,json=command|{'expected_revision':self.state()['revision']})
   self.assertEqual(duplicate.status_code,409)
   self.assertNotIn('X-Conflict-Reason',duplicate.headers)
 def test_legacy_import_once_and_persistence(self):
  self.client.post('/inventory',json={'ingredient_id':self.chicken,'quantity':123,'unit':'g','storage_location':'fridge'})
  self.assertEqual(self.state()['workspace']['inventory'][0]['quantity'],123)
  self.command('ingredient.create',{'name':'당근','unit':'g'})
  with TestClient(create_app('local',self.path)) as c:self.assertEqual(c.get('/v3/workspace').json(),self.state())
 def test_owners_separated(self):
  repo=self.app.state.workspace_repository;a=repo.load('user-a','');b=repo.load('user-b','')
  doc=deepcopy(a[1]);doc['ingredients'].append({'id':str(uuid4()),'name':'A의 재료','unit':'g'});self.assertTrue(repo.put('user-a','',a[0],doc))
  self.assertEqual(len(repo.load('user-b','')[1]['ingredients']),8)
 def test_auth_and_unknown_fields(self):
  self.command('ingredient.create',{'name':'당근','unit':'g','user_id':'other'},422)
  self.assertEqual(self.client.post('/v3/commands',json={'request_id':str(uuid4()),'expected_revision':True,'action':'ingredient.create','payload':{'name':'당근','unit':'g'}}).status_code,422)
 def test_derived_quantity_overflow_rejects_before_commit(self):
  r=self.recipe([{'ingredient_id':self.chicken,'quantity':1e9,'unit':'g'}],base_servings=0.1)
  before=self.state();self.command('meal.save',{'recipe_id':r['id'],'date':today(),'slot':'dinner','servings':1},422)
  self.assertEqual(self.state(),before)

if __name__=='__main__':unittest.main()
