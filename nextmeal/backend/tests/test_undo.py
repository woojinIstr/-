from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import tempfile
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
from app.main import create_app, SEEDS
from app.workspace import today


class UndoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = self.tmp.name + '/undo.db'
        self.app = create_app('local', self.path)
        self.client = TestClient(self.app)
        self.ing = SEEDS[0]['ingredient_id']
        self.milk = SEEDS[4]['ingredient_id']

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

    def view(self):
        response = self.client.get('/v3/workspace')
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def body(self, action, payload):
        return dict(request_id=str(uuid4()), expected_revision=self.view()['revision'], action=action, payload=payload)

    def send(self, action, payload, status=200):
        result = self.client.post('/v3/commands', json=self.body(action, payload))
        self.assertEqual(result.status_code, status, result.text)
        return result.json()

    def lot(self, amount=100, **fields):
        return self.send('lot.create', dict(ingredient_id=self.ing, input_quantity=amount,
                         input_unit='g', purchased_on=today()) | fields)['workspace']['inventory'][-1]

    def use(self, lot, amount=20, reason='use'):
        result = self.send('lot.use', dict(id=lot['id'], quantity=amount, reason=reason))
        return result['workspace']['history'][0]

    def cook(self, usage=None):
        recipe = self.send('recipe.save', dict(name='되돌리기 시험 요리', base_servings=1,
            minutes=10, ingredients=[dict(ingredient_id=self.ing, quantity=100, unit='g')]))['workspace']['recipes'][-1]
        meal = self.send('meal.save', dict(date=today(), slot='dinner', recipe_id=recipe['id'], servings=1))['workspace']['meals'][-1]
        result = self.send('meal.cook', dict(id=meal['id'], usage=usage or [dict(ingredient_id=self.ing, quantity=100, unit='g')]))
        return meal, result['workspace']['history'][0]

    def patch(self, lot, **changes):
        payload = {k: lot.get(k) for k in ('id','quantity','storage','name','purchased_on','expires_on','opened_on')}
        return self.send('lot.patch', payload | changes)

    def test_actual_lots_restored_meal_reopened_and_can_recook(self):
        later = self.lot(80, expires_on=(date.fromisoformat(today())+timedelta(days=5)).isoformat())
        sooner = self.lot(70, expires_on=today())
        before = self.view()
        meal, event = self.cook()
        self.assertEqual([l['quantity'] for l in self.view()['workspace']['inventory']], [50, 0])
        restored = self.send('history.undo', dict(id=event['id']))
        self.assertEqual(restored['workspace']['inventory'], before['workspace']['inventory'])
        self.assertEqual(restored['workspace']['meals'][0], meal)
        self.assertEqual(restored['shopping'], [])
        original = next(h for h in restored['workspace']['history'] if h['id']==event['id'])
        self.assertTrue(original['undone_at'])
        self.assertFalse(original['can_undo'])
        recooked = self.send('meal.cook', dict(id=meal['id'],usage=[dict(ingredient_id=self.ing,quantity=60,unit='g')]))
        self.assertEqual([l['quantity'] for l in recooked['workspace']['inventory']], [80, 10])

    def test_usage_and_waste_decimals(self):
        lot = self.lot(0.3)
        for reason in ('use', 'waste'):
            with self.subTest(reason=reason):
                event = self.use(lot, 0.1, reason)
                result = self.send('history.undo', dict(id=event['id']))
                self.assertEqual(result['workspace']['inventory'][0]['quantity'], 0.3)

    def test_preview_changes_no_write_and_repeated_preview_no_duplicate(self):
        self.lot()
        meal, event = self.cook()
        before = self.view()
        command = self.body('history.undo', dict(id=event['id']))
        for compact in (False, True):
            endpoint = '/v3/preview?compact=true' if compact else '/v3/preview'
            for _ in range(2):
                response = self.client.post(endpoint, json=command)
                self.assertEqual(response.status_code, 200, response.text)
                data = response.json()
                if compact:
                    self.assertEqual(data['inventory_changes'][0]['after'], 100)
                    self.assertEqual(data['meal_changes'][0]['after'], 'planned')
                else:
                    self.assertEqual(data['after']['workspace']['meals'][0]['status'], 'planned')
        self.assertEqual(self.view(), before)

    def test_same_id_replay_new_id_duplicate_and_evicted_request_rejected(self):
        event = self.use(self.lot())
        command = self.body('history.undo', dict(id=event['id']))
        first = self.client.post('/v3/commands', json=command).json()
        replay = self.client.post('/v3/commands', json=command)
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.json()['replayed'])
        self.assertEqual(replay.json()['revision'], first['revision'])
        self.send('history.undo', dict(id=event['id']), 409)
        repo = self.app.state.workspace_repository
        # Remove the replay ledger to simulate an old request falling outside its window.
        route = next(r for r in self.app.routes if getattr(r,'path',None)=='/v3/workspace')
        owner, token = route.dependant.dependencies[0].call(None)
        revision, doc = repo.load(owner, token)
        doc['requests'] = []
        self.assertTrue(repo.put(owner, token, revision, doc))
        before = self.view()
        self.send('history.undo', dict(id=event['id']), 409)
        self.assertEqual(self.view(), before)

    def test_latest_first_and_unrelated_changes_preserved(self):
        lot = self.lot()
        first = self.use(lot)
        second = self.use(lot, 30, 'waste')
        self.send('shopping.add', dict(name='다른 변경', quantity=2, unit='개'))
        other = self.lot(200, ingredient_id=self.milk, input_unit='ml')
        self.send('history.undo', dict(id=first['id']), 409)
        self.send('history.undo', dict(id=second['id']))
        restored = self.send('history.undo', dict(id=first['id']))
        self.assertEqual([i['quantity'] for i in restored['workspace']['inventory']], [100, 200])
        self.assertEqual(restored['workspace']['manual'][0]['name'], '다른 변경')

    def test_metadata_quantity_and_hide_restore_aba_block_undo(self):
        for change in ('quantity','metadata','archive'):
            with self.subTest(change=change):
                lot = self.lot()
                event = self.use(lot)
                current = next(i for i in self.view()['workspace']['inventory'] if i['id']==lot['id'])
                if change=='quantity':
                    self.patch(current, quantity=50)
                    self.patch(current, quantity=80)
                elif change=='metadata':
                    self.patch(current, storage='freezer')
                    self.patch(current, storage='fridge')
                else:
                    self.send('lot.archive', dict(id=lot['id']))
                    self.send('lot.restore', dict(id=lot['id']))
                before = self.view()
                self.send('history.undo', dict(id=event['id']), 409)
                self.assertEqual(self.view(), before)

    def test_multi_lot_conflict_rolls_back_every_lot_and_meal(self):
        a = self.lot(60)
        b = self.lot(60)
        meal, event = self.cook()
        self.patch(next(i for i in self.view()['workspace']['inventory'] if i['id']==b['id']), quantity=5)
        before = self.view()
        self.send('history.undo', dict(id=event['id']), 409)
        self.assertEqual(self.view(), before)
        self.assertEqual(before['workspace']['meals'][0]['status'], 'cooked')

    def test_concurrent_different_and_same_request_restore_once(self):
        for same in (False, True):
            with self.subTest(same=same):
                event = self.use(self.lot())
                a = self.body('history.undo', dict(id=event['id']))
                b = a if same else a | dict(request_id=str(uuid4()))
                def send(body):
                    with TestClient(self.app) as client:
                        return client.post('/v3/commands', json=body).status_code
                with ThreadPoolExecutor(2) as pool:
                    codes = sorted(pool.map(send,[a,b]))
                self.assertEqual(codes, [200,200] if same else [200,409])
                self.assertEqual(self.view()['workspace']['inventory'][-1]['quantity'], 100)

    def test_stale_after_preview_cannot_overwrite_new_stock(self):
        lot = self.lot()
        event = self.use(lot)
        command = self.body('history.undo',dict(id=event['id']))
        self.assertEqual(self.client.post('/v3/preview?compact=true', json=command).status_code,200)
        self.use(lot,10)
        before = self.view()
        response = self.client.post('/v3/commands',json=command)
        self.assertEqual(response.status_code,409)
        self.assertEqual(response.headers['X-Conflict-Reason'],'revision')
        self.assertEqual(self.view(),before)

    def test_legacy_history_not_guessed_but_new_actions_on_legacy_stock_work(self):
        from app.workspace import apply, bootstrap, history_status
        state = bootstrap([],[],[],[],[])
        state['ingredients']=[dict(id=self.ing,name='시험',unit='g')]
        state['inventory']=[dict(id=str(uuid4()),ingredient_id=self.ing,quantity=100,unit='g',archived=False)]
        old = dict(id=str(uuid4()),action='lot.use',summary='이전 기록',at='2026-01-01T00:00:00Z')
        state['history']=[old]
        with self.assertRaises(Exception) as caught:
            apply(state,'history.undo',dict(id=old['id']))
        self.assertEqual(caught.exception.status_code,409)
        self.assertFalse(history_status(state)[0]['can_undo'])
        new,_ = apply(state,'lot.use',dict(id=state['inventory'][0]['id'],quantity=10,reason='use'))
        result,_ = apply(new,'history.undo',dict(id=new['history'][0]['id']))
        self.assertEqual(result['inventory'],state['inventory'])

    def test_retained_after_restart_and_other_user_cannot_undo(self):
        event = self.use(self.lot())
        command = self.body('history.undo',dict(id=event['id']))
        other_app = create_app('local',self.path)
        identity = next(r for r in other_app.routes if getattr(r,'path',None)=='/v3/workspace').dependant.dependencies[0].call
        other_owner = str(uuid4())
        other_app.dependency_overrides[identity] = lambda: (other_owner,'')
        with TestClient(other_app) as other:
            response = other.post('/v3/commands',json=command|dict(expected_revision=0))
            self.assertEqual(response.status_code,404)
        before = self.view()
        with TestClient(create_app('local',self.path)) as restarted:
            self.assertEqual(restarted.post('/v3/commands',json=command).status_code,200)
        self.assertEqual(self.view()['workspace']['inventory'][0]['quantity'],100)

    def test_missing_event_unsupported_action_and_too_small_quantity(self):
        lot = self.lot()
        event = self.view()['workspace']['history'][0]
        self.send('history.undo',dict(id=str(uuid4())),404)
        self.send('history.undo',dict(id=event['id']),409)
        before = self.view()
        self.send('lot.use',dict(id=lot['id'],quantity=0.00000001,reason='use'),422)
        self.assertEqual(self.view(),before)
