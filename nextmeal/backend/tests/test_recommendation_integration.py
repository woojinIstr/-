"""Regression tests through the B server entry point with isolated data."""
import json
import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from openai import OpenAI

from app.serve import create_app


class RecommendationIntegrationTests(unittest.TestCase):
    def setUp(self):
        temp = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, {
            'APP_MODE': 'local',
            'APP_ENV': 'development',
            'SQLITE_PATH': str(Path(temp) / 'test.db'),
            'OPENAI_API_KEY': '',
        }))
        self.client = self.enterContext(TestClient(create_app()))
        self.initial = self.workspace()
        self.egg = self.ingredient_id('달걀')
        self.rice = self.ingredient_id('밥')

    def workspace(self):
        response = self.client.get('/v3/workspace')
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def ingredient_id(self, name):
        return next(item['id'] for item in self.initial['workspace']['ingredients'] if item['name'] == name)

    def command(self, action, payload):
        response = self.client.post('/v3/commands', json={
            'request_id': str(uuid4()),
            'expected_revision': self.workspace()['revision'],
            'action': action,
            'payload': payload,
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['workspace']

    def add_recipe(self, name, minutes, ingredient_id, quantity, unit):
        result = self.command('recipe.save', {
            'name': name, 'minutes': minutes, 'base_servings': 1,
            'ingredients': [{'ingredient_id': ingredient_id, 'quantity': quantity, 'unit': unit}],
        })
        return result['recipes'][-1]['id']

    def ask(self, user_request, **defaults):
        response = self.client.post('/v3/gpt-recommendations', json={'user_request': user_request, **defaults})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['Cache-Control'], 'private, no-store')
        return response.json()

    def test_exclusion_uses_b_catalog_before_and_after_alias_added(self):
        egg_recipe = self.add_recipe('달걀 시험 요리', 5, self.egg, 1, 'count')
        rice_recipe = self.add_recipe('간단 쌀 요리', 6, self.rice, 100, 'g')
        aliases = [self.egg]
        for both_names in (False, True):
            if both_names:
                workspace = self.command('ingredient.create', {'name': '계란', 'unit': 'count'})
                other_egg = workspace['ingredients'][-1]['id']
                aliases.append(other_egg)
                other_recipe = self.add_recipe('계란 시험 요리', 5, other_egg, 1, 'count')
            before = self.workspace()
            result = self.ask('10분 이내 달걀 제외 2인분')
            self.assertEqual(result['source'], 'rules')
            self.assertEqual(set(result['conditions']['excluded_ids']), set(aliases))
            ids = [item['recipe_id'] for item in result['recommendations']]
            self.assertNotIn(egg_recipe, ids)
            self.assertIn(rice_recipe, ids)
            if both_names:
                self.assertNotIn(other_recipe, ids)
            self.assertEqual(self.workspace(), before)

    def test_decimal_time_and_servings_reach_the_rule_fallback(self):
        self.command('lot.create', {
            'ingredient_id': self.rice, 'input_quantity': 150, 'input_unit': 'g',
            'purchased_on': self.initial['today'],
        })
        quick = self.add_recipe('89분 시험 요리', 89, self.rice, 100, 'g')
        slow = self.add_recipe('120분 시험 요리', 120, self.rice, 100, 'g')
        before = self.workspace()
        result = self.ask('달걀 제외 1.5시간 이내 2인분')
        self.assertEqual(result['conditions']['target_date'], before['today'])
        self.assertEqual(result['conditions']['max_minutes'], 90)
        self.assertEqual(result['conditions']['servings'], 2)
        rows = {item['recipe_id']: item for item in result['recommendations']}
        self.assertNotIn(slow, rows)
        self.assertEqual(rows[quick]['missing'][0]['shortage'], 50)
        for prompt in ('1시간 30분 이내', '10분 이내 5분 이상', '-2인분', '1~2시간 이내'):
            with self.subTest(prompt=prompt):
                rejected = self.ask(prompt)
                self.assertEqual(rejected['source'], 'needs_input')
                self.assertEqual(rejected['recommendations'], [])
        self.assertEqual(self.workspace(), before)

    def test_picker_defaults_and_explicit_text_overrides(self):
        base = date.fromisoformat(self.initial['today'])
        selected_date = (base + timedelta(days=3)).isoformat()
        result = self.ask('20분 이내', target_date=selected_date, servings=2)
        self.assertEqual(result['conditions']['target_date'], selected_date)
        self.assertEqual(result['conditions']['servings'], 2)
        result = self.ask('내일 3인분 20분 이내', target_date=selected_date, servings=2)
        self.assertEqual(result['conditions']['target_date'], (base + timedelta(days=1)).isoformat())
        self.assertEqual(result['conditions']['servings'], 3)


    def test_openrouter_sdk_roundtrip_and_failure_use_only_filtered_candidates(self):
        fast_id = self.add_recipe('쌀 시험 요리', 9, self.rice, 100, 'g')
        filtered_id = self.add_recipe('달걀 시험 요리', 5, self.egg, 1, 'count')
        before = self.workspace()
        calls = []

        def mock_responses(request):
            self.assertEqual(request.method, 'POST')
            self.assertEqual(
                request.url.path, '/api/v1/chat/completions'
            )
            self.assertEqual(request.url.host, 'openrouter.ai')

            body = json.loads(request.content)
            calls.append(body)

            # Only free routing is allowed.
            self.assertEqual(body['model'], 'openrouter/free')

            messages = body['messages']
            self.assertEqual(messages[0]['role'], 'system')
            self.assertEqual(messages[1]['role'], 'user')

            data = json.loads(messages[1]['content'])
            candidate_ids = {
                item['recipe_id']
                for item in data['candidates']
            }

            self.assertIn(fast_id, candidate_ids)
            self.assertNotIn(filtered_id, candidate_ids)

            if len(calls) == 2:
                return httpx.Response(
                    503,
                    json={'error': {'message': 'simulated failure'}}
                )

            return httpx.Response(
                200,
                json={
                    'id': 'chatcmpl_test',
                    'object': 'chat.completion',
                    'created': 1,
                    'model': 'openrouter/free',
                    'choices': [{
                        'index': 0,
                        'finish_reason': 'stop',
                        'message': {
                            'role': 'assistant',
                            'content': json.dumps({
                                'recipe_ids': [fast_id],
                                'message': '쌀 요리를 추천해요.'
                            })
                        }
                    }]
                }
            )

        def make_client(**kwargs):
            return OpenAI(
                http_client=httpx.Client(
                    transport=httpx.MockTransport(mock_responses)
                ),
                **kwargs
            )

        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}), \
             patch('openai.OpenAI', side_effect=make_client):
            ai = self.ask('달걀 제외 10분 이내 2인분')
            fallback = self.ask('달걀 제외 10분 이내 2인분')
            self.assertNotIn(
                'test-key', self.client.get('/app-config').text
            )

        self.assertEqual(len(calls), 2)
        self.assertEqual(ai['source'], 'gpt')
        self.assertEqual(
            [(row['recipe_id'], row['rank'])
             for row in ai['recommendations']],
            [(fast_id, 1)]
        )
        self.assertEqual(fallback['source'], 'rules')
        self.assertEqual(fallback['conditions'], ai['conditions'])
        self.assertTrue(
            all(
                row['recipe_id'] != filtered_id
                and row['minutes'] <= 10
                for row in fallback['recommendations']
            )
        )
        self.assertEqual(self.workspace(), before)


    def test_registered_endpoints_validate_inputs_and_require_login_in_supabase_mode(self):
        schema = self.client.get('/openapi.json').json()
        self.assertIn('get', schema['paths']['/v3/recommendations'])
        self.assertIn('post', schema['paths']['/v3/gpt-recommendations'])
        self.assertEqual(self.client.get('/v3/recommendations', params={'servings': 0.05}).status_code, 422)
        self.assertEqual(self.client.get('/v3/recommendations', params={'excluded_ids': str(uuid4())}).status_code, 422)
        self.assertEqual(self.client.post('/v3/gpt-recommendations', json={'user_request': ' '}).status_code, 422)

        with patch.dict(os.environ, {
            'APP_MODE': 'supabase',
            'SUPABASE_URL': 'https://example.supabase.co',
            'SUPABASE_PUBLISHABLE_KEY': 'sb_publishable_test',
        }), TestClient(create_app()) as secure:
            self.assertEqual(secure.get('/v3/recommendations').status_code, 401)
            self.assertEqual(secure.post('/v3/gpt-recommendations', json={'user_request': '달걀 제외'}).status_code, 401)
