import json
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch
from recommendation.conditions import parse_conditions, ConditionError
from recommendation.engine import recommend
from recommendation.gpt import recommend_with_gpt

TODAY=date(2026,11,18)

def workspace():
    return {
        'ingredients':[{'id':'egg','name':'계란','unit':'count'}, {'id':'rice','name':'밥','unit':'g'}, {'id':'onion','name':'양파','unit':'g'}],
        'inventory':[{'ingredient_id':'egg','quantity':1,'unit':'count'}, {'ingredient_id':'rice','quantity':300,'unit':'g'}, {'ingredient_id':'onion','quantity':100,'unit':'g'}],
        'recipes':[
            {'id':'egg_rice','name':'계란볶음밥','minutes':30,'base_servings':1,'ingredients':[{'ingredient_id':'egg','quantity':1,'unit':'count'},{'ingredient_id':'rice','quantity':100,'unit':'g'}]},
            {'id':'onion_rice','name':'양파밥','minutes':8,'base_servings':1,'ingredients':[{'ingredient_id':'onion','quantity':50,'unit':'g'},{'ingredient_id':'rice','quantity':100,'unit':'g'}]},
            {'id':'rice','name':'밥만 먹기','minutes':5,'base_servings':1,'ingredients':[{'ingredient_id':'rice','quantity':100,'unit':'g'}]},
        ]}

class MockClient:
    def __init__(self, reply=None, exception=None): self.reply=reply; self.exception=exception; self.kwargs=None; self.responses=self
    def create(self, **kwargs):
        self.kwargs=kwargs
        if self.exception: raise self.exception
        return SimpleNamespace(output_text=self.reply)

class TestRecommendation(unittest.TestCase):
    def test_basic_engine(self): self.assertEqual(len(recommend(workspace())),3)
    def test_korean_exclusion_time_servings(self):
        w=workspace(); c=MockClient(json.dumps({'recipe_ids':['rice','onion_rice'],'message':'추천합니다'}))
        result=recommend_with_gpt(w,'달걀 제외 10분 이내 2인분 내일 저녁 추천해줘',client=c,today=TODAY)
        self.assertEqual(result['source'],'gpt')
        self.assertEqual([x['recipe_id'] for x in result['recommendations']],['rice','onion_rice'])
        self.assertEqual([x['rank'] for x in result['recommendations']],[1,2])
        self.assertEqual(result['conditions']['target_date'],'2026-11-19')
        self.assertEqual(result['conditions']['servings'],2)
        self.assertEqual(result['conditions']['max_minutes'],10)
        self.assertEqual(result['conditions']['excluded_ids'],['egg'])
        self.assertNotIn('egg_rice',[x['recipe_id'] for x in result['recommendations']])
        self.assertEqual(result['recommendations'][1]['missing'],[])
        sent=json.loads(c.kwargs['input'])
        self.assertTrue(all('recipe_id' in x and 'ingredients' in x for x in sent['candidates']))
        self.assertEqual(len(sent['candidates']),2)
        self.assertEqual(sent['candidates'][0]['ingredients'][0]['required'],100)
        self.assertEqual(w,workspace())
    def test_two_servings_shortage(self):
        r=recommend_with_gpt(workspace(),'달걀 제외 10분 이내 3인분',client=MockClient('{"recipe_ids":["onion_rice"],"message":"추천"}'),today=TODAY)
        self.assertEqual(r['recommendations'][0]['missing'][0]['name'],'양파')
        self.assertEqual(r['recommendations'][0]['missing'][0]['shortage'],50)
    def test_gpt_service_failure_keeps_conditions(self):
        r=recommend_with_gpt(workspace(),'달걀 제외 10분 이내 2인분',client=MockClient(exception=RuntimeError('network')),today=TODAY)
        self.assertEqual(r['source'],'rules')
        self.assertTrue(all(x['minutes']<=10 and x['recipe_id']!='egg_rice' for x in r['recommendations']))
    def test_empty_response(self):
        r=recommend_with_gpt(workspace(),'계란 제외',client=MockClient(''),today=TODAY)
        self.assertEqual(r['source'],'rules')
    def test_invalid_json(self):
        r=recommend_with_gpt(workspace(),'계란 제외',client=MockClient('not json'),today=TODAY)
        self.assertEqual(r['source'],'rules')
    def test_unknown_id(self):
        r=recommend_with_gpt(workspace(),'계란 제외',client=MockClient('{"recipe_ids":["unregistered"],"message":"추천"}'),today=TODAY)
        self.assertEqual(r['source'],'rules')
        self.assertTrue(all(x['recipe_id']!='egg_rice' for x in r['recommendations']))
    def test_duplicate_ids_rejected(self):
        r=recommend_with_gpt(workspace(),'계란 제외',client=MockClient('{"recipe_ids":["rice","rice"],"message":"추천"}'),today=TODAY)
        self.assertEqual(r['source'],'gpt')
        self.assertEqual(len(r['recommendations']), 1)
        self.assertEqual(r['recommendations'][0]['rank'], 1)
    def test_unrecognized_exclusion_is_not_ignored(self):
        r=recommend_with_gpt(workspace(),'버섯 제외 10분 이내',client=MockClient('{}'),today=TODAY)
        self.assertEqual(r['source'],'needs_input');self.assertEqual(r['recommendations'],[])
    def test_ambiguous_time_requires_input(self):
        r=recommend_with_gpt(workspace(),'10분 이상 메뉴',client=MockClient('{}'),today=TODAY)
        self.assertEqual(r['source'],'needs_input')
    def test_kst_relative_date(self):
        c=parse_conditions('모레 저녁',workspace()['ingredients'],today=TODAY)
        self.assertEqual(c['target_date'],'2026-11-20')
    def test_servings_bounds(self):
        for x in ['0인분','13인분']:
            with self.subTest(x=x),self.assertRaises(ConditionError):parse_conditions(x,workspace()['ingredients'],today=TODAY)
    def test_no_model_call_when_no_candidates(self):
        r=recommend_with_gpt(workspace(),'계란 제외 1분 이내',client=MockClient('{}'),today=TODAY)
        self.assertEqual(r['recommendations'],[])
    def test_kst_default_engine(self):
        with patch('recommendation.engine.workspace_today', return_value='2026-11-18'):
            self.assertEqual(len(recommend(workspace())),3)

if __name__=='__main__':unittest.main()
