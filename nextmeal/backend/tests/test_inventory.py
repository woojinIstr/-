import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from app.main import create_app, SEEDS, SupabaseStore

class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = self.temp.name+'/test.db'
        self.client = TestClient(create_app('local',self.path))
        self.body = {'ingredient_id':SEEDS[0]['ingredient_id'],'quantity':300,'unit':'g','storage_location':'fridge'}
    def tearDown(self):
        self.client.close()
        self.temp.cleanup()
    def add(self):
        r = self.client.post('/inventory',json=self.body)
        self.assertEqual(r.status_code,201)
        return r.json()['inventory_id']
    def test_roundtrip_persistence(self):
        key = self.add()
        self.assertEqual(self.client.patch('/inventory/'+key,json={'quantity':180}).json()['quantity'],180)
        with TestClient(create_app('local',self.path)) as second:
            self.assertEqual(second.get('/inventory').json()[0]['quantity'],180)
        self.assertEqual(self.client.delete('/inventory/'+key).status_code,204)
        self.assertEqual(self.client.get('/inventory').json(),[])
    def test_invalid_quantity(self):
        for q in [-1,True,'100',1000000001]:
            self.assertEqual(self.client.post('/inventory',json=self.body|{'quantity':q}).status_code,422)
    def test_unit_mismatch(self):
        self.assertEqual(self.client.post('/inventory',json=self.body|{'unit':'count'}).status_code,422)
    def test_unknown_ingredient(self):
        self.assertEqual(self.client.post('/inventory',json=self.body|{'ingredient_id':'90000000-0000-4000-8000-000000000001'}).status_code,404)
    def test_patch_validation(self):
        key = self.add()
        for data in [{},{'quantity':None},{'unit':'ml'},{'quantity':-1}]:
            self.assertEqual(self.client.patch('/inventory/'+key,json=data).status_code,422)
        self.assertEqual(self.client.get('/inventory').json()[0]['quantity'],300)
    def test_distinct_lots(self):
        self.add()
        self.body['storage_location']='freezer'
        self.add()
        self.assertEqual(len(self.client.get('/inventory').json()),2)
    def test_owner_filter(self):
        key=self.add()
        with sqlite3.connect(self.path) as c:
            c.execute('UPDATE inventory SET user_id=?',('other-user',))
        self.assertEqual(self.client.get('/inventory').json(),[])
        self.assertEqual(self.client.patch('/inventory/'+key,json={'quantity':0}).status_code,404)
        self.assertEqual(self.client.delete('/inventory/'+key).status_code,404)
    def test_cannot_supply_owner(self):
        self.assertEqual(self.client.post('/inventory',json=self.body|{'user_id':'fake'}).status_code,422)
    def test_uuid_and_pagination(self):
        self.assertEqual(self.client.delete('/inventory/not-a-uuid').status_code,422)
        self.assertEqual(self.client.get('/inventory?limit=101').status_code,422)
    def test_supabase_requires_auth(self):
        with patch.dict(os.environ,{'SUPABASE_URL':'https://example.supabase.co','SUPABASE_PUBLISHABLE_KEY':'test'}):
            with TestClient(create_app('supabase')) as c:
                self.assertEqual(c.get('/inventory').status_code,401)
    def test_supabase_forwards_user_token(self):
        store=SupabaseStore('https://example.supabase.co','publishable')
        with patch.object(store.client,'request',return_value=httpx.Response(200,json=[])) as req:
            store.request('GET','inventory','user-jwt',{'user_id':'eq.user'})
            self.assertEqual(req.call_args.kwargs['headers']['Authorization'],'Bearer user-jwt')
        store.close()
    def test_supabase_failure_is_sanitized(self):
        store=SupabaseStore('https://example.supabase.co','publishable')
        with patch.object(store.client,'request',return_value=httpx.Response(500,text='secret internal error')):
            from fastapi import HTTPException
            with self.assertRaises(HTTPException) as err: store.request('GET','inventory','jwt')
            self.assertEqual(err.exception.status_code,503)
            self.assertNotIn('secret',err.exception.detail)
        store.close()

if __name__ == '__main__': unittest.main()
