"""Exercise error reporting through the installed SDK and the B server routes."""
from contextlib import redirect_stdout
from io import StringIO
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import httpx
from openai import OpenAI

from app.serve import create_app
from tools.check_ai import main as check_ai


class AIDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.dict(os.environ, {
            'APP_MODE': 'local', 'APP_ENV': 'development',
            'SQLITE_PATH': str(self.temp / 'test.db'),
            'OPENAI_API_KEY': '', 'OPENAI_MODEL': '',
        }))
        self.client = self.enterContext(TestClient(create_app()))

    def test_status_checks_configuration_without_network_or_workspace_changes(self):
        before = self.client.get('/v3/workspace').json()
        with patch('openai.OpenAI') as sdk:
            response = self.client.get('/v3/recommendation-status')
            sdk.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Cache-Control'], 'private, no-store')
        self.assertEqual(response.json(), {
            'check': 'configuration_only', 'key_configured': False,
            'sdk_available': True, 'model': 'gpt-4.1-mini', 'version': '0.3.8',
        })
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'private-key-sentinel', 'OPENAI_MODEL': 'custom-model'}):
            configured = self.client.get('/v3/recommendation-status')
            self.assertTrue(configured.json()['key_configured'])
            self.assertEqual(configured.json()['model'], 'custom-model')
            self.assertNotIn('private-key-sentinel', configured.text)
        self.assertEqual(self.client.get('/v3/workspace').json(), before)
        with patch.dict(os.environ, {
            'APP_MODE': 'supabase', 'SUPABASE_URL': 'https://example.supabase.co',
            'SUPABASE_PUBLISHABLE_KEY': 'sb_publishable_test',
        }), TestClient(create_app()) as secure:
            self.assertEqual(secure.get('/v3/recommendation-status').status_code, 401)

    def test_error_codes_use_real_sdk_exceptions_and_keep_conditions(self):
        before = self.client.get('/v3/workspace').json()
        cases = [
            (401, 'invalid_api_key', 'authentication_error'),
            (403, 'permission_denied', 'permission_denied'),
            (404, 'model_not_found', 'model_unavailable'),
            (429, 'insufficient_quota', 'quota_exceeded'),
            (429, 'rate_limit_exceeded', 'rate_limited'),
            (400, 'invalid_request_error', 'invalid_request'),
            (503, 'server_error', 'service_error'),
            (None, 'timeout', 'timeout'),
            (None, 'connection_error', 'connection_error'),
            (200, 'invalid_json', 'invalid_response'),
        ]
        for status, code, expected in cases:
            with self.subTest(code=code):
                def response(request):
                    if code == 'timeout':
                        raise httpx.ReadTimeout('private-key-sentinel', request=request)
                    if code == 'connection_error':
                        raise httpx.ConnectError('private-key-sentinel', request=request)
                    if status == 200:
                        return httpx.Response(200, json={
                            'id': 'resp_test', 'object': 'response', 'status': 'completed',
                            'created_at': 1, 'model': 'gpt-4.1-mini',
                            'output': [{'type': 'message', 'id': 'msg_test', 'role': 'assistant',
                                        'status': 'completed', 'content': [
                                            {'type': 'output_text', 'annotations': [], 'text': '{broken'},
                                        ]}],
                        })
                    return httpx.Response(status, json={'error': {
                        'message': 'private-key-sentinel', 'code': code,
                    }})

                def make_client(**kwargs):
                    return OpenAI(http_client=httpx.Client(transport=httpx.MockTransport(response)), **kwargs)

                with patch.dict(os.environ, {'OPENAI_API_KEY': 'private-key-sentinel'}), \
                        patch('openai.OpenAI', side_effect=make_client), \
                        self.assertLogs('recommendation.gpt', level='WARNING') as logs:
                    result = self.client.post('/v3/gpt-recommendations', json={
                        'user_request': '달걀 제외 20분 이내 2인분',
                    })
                self.assertEqual(result.status_code, 200)
                body = result.json()
                self.assertEqual((body['source'], body['reason_code']), ('rules', expected))
                self.assertEqual(body['conditions']['servings'], 2)
                self.assertEqual(body['conditions']['max_minutes'], 20)
                excluded = set(body['conditions']['excluded_ids'])
                for row in body['recommendations']:
                    self.assertLessEqual(row['minutes'], 20)
                    self.assertFalse(excluded.intersection(p['ingredient_id'] for p in row['ingredients']))
                self.assertNotIn('private-key-sentinel', result.text + '\n'.join(logs.output))
        self.assertEqual(self.client.get('/v3/workspace').json(), before)

    def test_missing_key_empty_candidates_and_unclear_conditions_are_distinct(self):
        for prompt, source, reason in [
            ('20분 이내', 'rules', 'not_configured'),
            ('1분 이내', 'rules', 'no_candidates'),
            ('-2인분', 'needs_input', 'conditions_unclear'),
        ]:
            with self.subTest(prompt=prompt), patch('openai.OpenAI') as sdk:
                result = self.client.post('/v3/gpt-recommendations', json={'user_request': prompt}).json()
                self.assertEqual((result['source'], result['reason_code']), (source, reason))
                sdk.assert_not_called()

    def test_live_checker_fails_for_fallback_and_only_calls_on_explicit_live(self):
        env = self.temp / 'test.env'
        env.write_text('OPENAI_API_KEY=file-secret-sentinel\n', encoding='utf-8-sig')
        output = StringIO()
        with patch('tools.check_ai.recommend_with_gpt') as recommend, redirect_stdout(output):
            # Existing environment overrides the file, matching the running server.
            self.assertEqual(check_ai(['--env-file', str(env), '--live']), 1)
            recommend.assert_not_called()
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'process-secret-sentinel'}), \
                patch('tools.check_ai.recommend_with_gpt') as recommend, redirect_stdout(output):
            self.assertEqual(check_ai(['--env-file', str(env)]), 0)
            recommend.assert_not_called()
            recommend.return_value = {
                'source': 'rules', 'reason_code': 'quota_exceeded', 'message': '기본 추천',
                'recommendations': [], 'conditions': {},
            }
            self.assertEqual(check_ai(['--env-file', str(env), '--live']), 1)
            recommend.return_value = {
                'source': 'gpt', 'reason_code': None, 'message': '양파밥 추천',
                'recommendations': [{'recipe_id': 'sample-onion-rice', 'rank': 1}], 'conditions': {},
            }
            self.assertEqual(check_ai(['--env-file', str(env), '--live']), 0)
            self.assertEqual(recommend.call_count, 2)
            workspace, prompt = recommend.call_args.args
            self.assertEqual(len(workspace['inventory']), 3)
            self.assertIn('달걀 제외 10분 이내 2인분', prompt)
        self.assertNotIn('file-secret-sentinel', output.getvalue())
        self.assertNotIn('process-secret-sentinel', output.getvalue())


if __name__ == '__main__':
    unittest.main()
