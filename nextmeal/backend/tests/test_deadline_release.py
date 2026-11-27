from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.main import create_app
from app.starter_recipes import expand_for_recommendation
from app.workspace import apply, bootstrap, shopping, today
from recommendation.engine import recommend


def empty():
    return bootstrap([], [], [], [], [])


def pantry(items, state=None):
    return apply(state or empty(), 'lot.quick_add', {
        'items': [dict(name=name, quantity=quantity, unit=unit) for name, quantity, unit in items]
    })[0]


# Synthetic fixtures with a concrete expected dish, and cases with no eligible dish.
COOKABLE = (
    ([('달걀', 2, 'count'), ('밥', 200, 'g')], '달걀밥'),
    ([('계란', 2, 'count')], '삶은 달걀'),
    ([('햇반', 210, 'g'), ('삼겹살', 200, 'g')], '삼겹살구이'),
    ([('흰밥', 210, 'g'), ('삼겹살', 200, 'g'), ('양파', 100, 'g')], '삼겹살 덮밥'),
    ([('두부', 300, 'g'), ('양파', 100, 'g')], '따뜻한 두부'),
    ([('두부', 150, 'g'), ('양배추', 150, 'g')], '두부 양배추찜'),
    ([('감자', 200, 'g')], '찐 감자'),
    ([('고구마', 200, 'g')], '찐 고구마'),
    ([('감자', 180, 'g'), ('당근', 100, 'g')], '감자 당근찜'),
    ([('닭가슴살', 180, 'g'), ('양파', 100, 'g')], '닭가슴살 양파찜'),
    ([('즉석밥', 210, 'g'), ('우유', 250, 'ml')], '우유죽'),
    ([('토마토', 200, 'g'), ('달걀', 2, 'count')], '토마토 달걀국'),
    ([('김치', 150, 'g'), ('참치캔', 150, 'g'), ('햇반', 210, 'g'), ('대파', 50, 'g')], '김치참치덮밥'),
    ([('배추김치', 150, 'g'), ('계란', 1, 'count'), ('밥', 200, 'g')], '김치달걀덮밥'),
    ([('김치', 100, 'g'), ('두부', 150, 'g')], '두부김치'),
    ([('대파', 30, 'g'), ('달걀', 1, 'count')], '대파달걀국'),
    ([('스팸햄', 100, 'g'), ('밥', 200, 'g')], '스팸덮밥'),
    ([('식빵', 2, 'count'), ('슬라이스 치즈', 1, 'count')], '치즈 토스트'),
    ([('식빵', 2, 'count'), ('계란', 1, 'count')], '달걀 토스트'),
    ([('두부', 200, 'g'), ('달걀', 1, 'count')], '두부 달걀 스크램블'),
)
NO_MATCH = (
    (),
    [('양파', 100, 'g')],
    [('두부', 1, 'count'), ('양파', 100, 'g')],
    [('달걀', 1, 'count')],
    [('김치', 150, 'g'), ('참치', 150, 'g'), ('햇반', 210, 'g'), ('대파', 50, 'g')],
    [('식빵', 1, 'count'), ('치즈', 1, 'count')],
    [('김치', 150, 'g'), ('참치캔', 150, 'g'), ('생쌀', 210, 'g')],
)


class EvidenceTests(TestCase):
    def test_twenty_cookable_and_seven_ineligible_pantry_fixtures(self):
        for items, expected in COOKABLE:
            with self.subTest(items=items):
                result = recommend(expand_for_recommendation(pantry(items)), max_minutes=20, ready_only=True)
                self.assertIn(expected, {item['name'] for item in result})
                self.assertTrue(all(item['ready'] and item['minutes'] <= 20 for item in result))
        for items in NO_MATCH:
            with self.subTest(items=items):
                state = pantry(items) if items else empty()
                self.assertEqual(recommend(expand_for_recommendation(state), max_minutes=20, ready_only=True), [])

    def test_legacy_separate_alias_lots_debit_and_restore_exactly(self):
        state = empty()
        for alias in ('계란', '달걀'):
            state, _ = apply(state, 'lot.create', dict(new_ingredient=dict(name=alias, unit='count'),
                             input_quantity=1, input_unit='count', purchased_on=today()))
        snapshot = deepcopy(state['inventory'])
        candidates = recommend(expand_for_recommendation(state), max_minutes=20, ready_only=True)
        recipe = next(r for r in candidates if r['name'] == '삶은 달걀')
        state, _ = apply(state, 'meal.save', dict(date=today(), slot='lunch', recipe_id=recipe['recipe_id'], servings=1))
        self.assertEqual(shopping(state), [])
        self.assertEqual(recommend(expand_for_recommendation(state), target_slot='dinner', ready_only=True), [])
        meal = state['meals'][0]
        state, _ = apply(state, 'meal.cook', dict(id=meal['id'], usage=meal['recipe']['ingredients']))
        self.assertEqual([lot['quantity'] for lot in state['inventory']], [0, 0])
        self.assertEqual({lot['ingredient_id'] for lot in state['meals'][0]['used']},
                         {lot['ingredient_id'] for lot in snapshot})
        state, _ = apply(state, 'history.undo', dict(id=state['history'][0]['id']))
        self.assertEqual(state['inventory'], snapshot)

    def test_known_pack_size_reuses_product_without_including_old_unknown_weight(self):
        state = pantry([('두부', 1, 'count')])
        items = [dict(name='두부', quantity=1, unit='pack', pack_size=300, pack_label='모')]
        state, _ = apply(state, 'lot.quick_add', dict(items=items))
        items[0].update(pack_size=150)
        state, _ = apply(state, 'lot.quick_add', dict(items=items))
        product = next(p for p in state['products'] if p['pack_size'] == 300)
        items = [dict(name='두부', quantity=2, unit='pack', product_id=product['id'])]
        state, _ = apply(state, 'lot.quick_add', dict(items=items))
        recipe = next(r for r in recommend(expand_for_recommendation(state), ready_only=True) if r['name'] == '따뜻한 두부')
        self.assertEqual(recipe['ingredients'][0]['available'], 1050)
        self.assertEqual([lot['quantity'] for lot in state['inventory']], [1, 300, 150, 600])
        self.assertEqual(len(state['products']), 2)

    def test_429_coalesces_same_revision_and_keeps_all_constraints(self):
        import httpx
        from openai import RateLimitError
        import openai
        with TemporaryDirectory() as temp, patch.dict(os.environ, {
            'APP_MODE':'local', 'APP_ENV':'development', 'SQLITE_PATH':str(Path(temp)/'test.db'),
            'OPENROUTER_API_KEY':'test-key'
        }):
            app = create_app()
            repo = app.state.workspace_repository
            repo.put('00000000-0000-4000-8000-000000000001','',-1,
                     pantry([('달걀', 2,'count'),('햇반',210,'g'),('토마토',150,'g')]))
            body = dict(user_request='냉장고에서 만들 수 있는 요리 추천해줘 20분 이내 토마토 제외')
            entered, release = Event(), Event()
            class Model:
                def __enter__(self):
                    return self
                def __exit__(self, *_):
                    pass
                @property
                def chat(self):
                    return self
                @property
                def completions(self):
                    return self
                def create(self, **_):
                    entered.set()
                    release.wait(3)
                    raise RateLimitError('limited', response=httpx.Response(
                        429, request=httpx.Request('POST','https://example.test')), body={})
            with patch.object(openai, 'OpenAI', return_value=Model()) as model, TestClient(app) as client:
                def get():
                    response = client.post('/v3/gpt-recommendations', json=body)
                    self.assertEqual(response.status_code, 200)
                    return response.json()
                with ThreadPoolExecutor(2) as pool:
                    first = pool.submit(get)
                    self.assertTrue(entered.wait(3))
                    second = pool.submit(get)
                    release.set()
                    result = first.result(5)
                    self.assertEqual(second.result(5), result)
                self.assertEqual(get(), result)
                self.assertEqual(model.call_count, 1)
                self.assertEqual(result['reason_code'], 'rate_limited')
                self.assertTrue(result['conditions']['ready_only'])
                self.assertEqual(result['conditions']['max_minutes'], 20)
                self.assertTrue(result['recommendations'])
                self.assertTrue(all(r['ready'] and r['minutes'] <= 20 and '토마토' not in r['name']
                                    for r in result['recommendations']))
