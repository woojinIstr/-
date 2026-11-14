"""Real signature verification and HTTP-boundary regression tests."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from tempfile import TemporaryDirectory
import json
import os
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric import ec, rsa, ed25519
from fastapi import HTTPException
from fastapi.testclient import TestClient
import httpx
import jwt

from app.auth import PublicSigningKeys
from app.main import SupabaseStore, create_app, DEMO_USER

PROJECT = 'https://test.supabase.co'


def public_key(private, kid='key-A', algorithm='ES256'):
    factory = {'ES256': jwt.algorithms.ECAlgorithm, 'RS256': jwt.algorithms.RSAAlgorithm,
               'EdDSA': jwt.algorithms.OKPAlgorithm}[algorithm]
    return json.loads(factory.to_jwk(private.public_key())) | {'kid': kid, 'alg': algorithm, 'use': 'sig'}


def access_token(private, owner=DEMO_USER, kid='key-A', algorithm='ES256', changes=None, omit=(), headers=None):
    now = int(time.time())
    claims = {'iss': PROJECT + '/auth/v1', 'aud': 'authenticated', 'role': 'authenticated',
              'sub': owner, 'iat': now - 10, 'exp': now + 3600}
    claims.update(changes or {})
    for field in omit:
        claims.pop(field, None)
    return jwt.encode(claims, private, algorithm=algorithm, headers={'kid': kid} | (headers or {}))


class AuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private = ec.generate_private_key(ec.SECP256R1())
        cls.public = public_key(cls.private)

    @contextmanager
    def store(self, keys=None, remote_status=200):
        seen = []
        def handler(request):
            seen.append(request)
            if request.url.path.endswith('/jwks.json'):
                return httpx.Response(200, json={'keys': keys if keys is not None else [self.public]})
            if request.url.path == '/auth/v1/user':
                return httpx.Response(remote_status, json={'id': DEMO_USER})
            raise AssertionError(request.url)
        client = httpx.Client(transport=httpx.MockTransport(handler))
        with patch.dict(os.environ, {'AUTH_VERIFICATION': 'auto'}), patch('app.main.httpx.Client', return_value=client):
            store = SupabaseStore(PROJECT, 'test-key')
        try:
            yield store, seen
        finally:
            store.close()

    def test_cached_keys_verify_each_request_and_separate_users(self):
        owner_b = str(uuid4())
        with self.store() as (store, seen):
            token_a = access_token(self.private)
            token_b = access_token(self.private, owner_b)
            self.assertEqual(store.user(token_a), DEMO_USER)
            self.assertEqual(store.user(token_b), owner_b)
            self.assertEqual(store.user(token_a), DEMO_USER)
            self.assertEqual(len(seen), 1)
            self.assertTrue(seen[0].url.path.endswith('/jwks.json'))
            self.assertNotIn('Authorization', seen[0].headers)

    def test_rsa_and_eddsa_verification(self):
        for private, algorithm in [(rsa.generate_private_key(public_exponent=65537, key_size=2048), 'RS256'),
                                   (ed25519.Ed25519PrivateKey.generate(), 'EdDSA')]:
            with self.subTest(algorithm=algorithm), self.store([public_key(private, algorithm=algorithm)]) as (store, seen):
                self.assertEqual(store.user(access_token(private, algorithm=algorithm)), DEMO_USER)
                self.assertEqual(len(seen), 1)

    def test_forged_signature_is_rejected_even_after_valid_token(self):
        other = ec.generate_private_key(ec.SECP256R1())
        with self.store() as (store, seen):
            store.user(access_token(self.private))
            with self.assertRaises(HTTPException) as rejected:
                store.user(access_token(other))
            self.assertEqual(rejected.exception.status_code, 401)
            self.assertEqual(len(seen), 1)

    def test_wrong_claims_and_missing_required_claims_are_rejected(self):
        variants = [({'exp': int(time.time()) - 1}, ()),
                    ({'iat': int(time.time()) + 300}, ()),
                    ({'nbf': int(time.time()) + 300}, ()),
                    ({'iss': 'https://other.supabase.co/auth/v1'}, ()),
                    ({'aud': 'another-audience'}, ()),
                    ({'sub': 'not-a-uuid'}, ()),
                    ({'role': 'service_role'}, ())]
        variants += [({}, (field,)) for field in ['exp', 'iat', 'iss', 'aud', 'sub', 'role']]
        with self.store() as (store, seen):
            for changes, omit in variants:
                with self.subTest(changes=changes, omit=omit), self.assertRaises(HTTPException) as rejected:
                    store.user(access_token(self.private, changes=changes, omit=omit))
                self.assertEqual(rejected.exception.status_code, 401)
            self.assertEqual(len(seen), 1)

    def test_untrusted_key_urls_are_ignored(self):
        token = access_token(self.private, headers={'jku': 'https://attacker.invalid/keys', 'x5u': 'https://attacker.invalid/cert'})
        with self.store() as (store, seen):
            self.assertEqual(store.user(token), DEMO_USER)
            self.assertTrue(all(str(r.url).startswith(PROJECT + '/') for r in seen))

    def test_malformed_and_unsigned_tokens_are_rejected_without_network(self):
        unsigned = jwt.encode({'sub': DEMO_USER}, '', algorithm='none')
        with self.store() as (store, seen):
            for token in ['not-a-jwt', unsigned, 'x' * 32769]:
                with self.subTest(token=token[:10]), self.assertRaises(HTTPException) as rejected:
                    store.user(token)
                self.assertEqual(rejected.exception.status_code, 401)
            self.assertEqual(seen, [])

    def test_legacy_and_forced_remote_keep_authenticated_server_check(self):
        legacy = access_token('a-long-test-only-shared-secret-1234567890', algorithm='HS256')
        with self.store() as (store, seen):
            self.assertEqual(store.user(legacy), DEMO_USER)
            store.identity.strategy = 'remote'
            self.assertEqual(store.user(access_token(self.private)), DEMO_USER)
            self.assertEqual([r.url.path for r in seen], ['/auth/v1/user', '/auth/v1/user'])
            self.assertEqual(seen[0].headers['Authorization'], 'Bearer ' + legacy)

    def test_unknown_kid_uses_auth_and_discovery_is_rate_limited(self):
        with self.store() as (store, seen):
            for i in range(3):
                self.assertEqual(store.user(access_token(self.private, kid='new-' + str(i))), DEMO_USER)
            self.assertEqual(sum(r.url.path.endswith('/jwks.json') for r in seen), 1)
            self.assertEqual(sum(r.url.path == '/auth/v1/user' for r in seen), 3)

    def test_empty_keys_still_require_remote_authorization(self):
        with self.store([], remote_status=401) as (store, seen):
            with self.assertRaises(HTTPException) as rejected:
                store.user(access_token(self.private))
            self.assertEqual(rejected.exception.status_code, 401)
            self.assertEqual(len(seen), 2)

    def test_discovery_failure_falls_back_and_never_trusts_unverified_subject(self):
        with self.store(remote_status=401) as (store, seen):
            def failing_fetch():
                from app.auth import SigningKeysUnavailable
                raise SigningKeysUnavailable()
            store.identity.signing_keys.fetch = failing_fetch
            with self.assertRaises(HTTPException) as rejected:
                store.user(access_token(self.private))
            self.assertEqual(rejected.exception.status_code, 401)
            self.assertEqual([r.url.path for r in seen], ['/auth/v1/user'])

    def test_key_expiry_rotation_and_concurrent_first_use(self):
        now = [0.0]
        next_private = ec.generate_private_key(ec.SECP256R1())
        keys = [self.public]
        calls = []
        def fetch():
            calls.append(1)
            return {'keys': keys.copy()}
        cache = PublicSigningKeys(fetch, clock=lambda: now[0])
        with ThreadPoolExecutor(8) as pool:
            results = list(pool.map(cache.get, ['key-A'] * 16))
        self.assertTrue(all(r is not None for r in results))
        self.assertEqual(len(calls), 1)
        keys[:] = [public_key(next_private, 'key-B')]
        now[0] = 301
        self.assertIsNone(cache.get('key-A'))
        self.assertIsNotNone(cache.get('key-B'))
        self.assertEqual(len(calls), 2)

    def test_expired_key_is_not_used_during_discovery_outage(self):
        from app.auth import SigningKeysUnavailable
        now = [0.0]
        def fetch():
            if now[0] > 0:
                raise SigningKeysUnavailable()
            return {'keys': [self.public]}
        cache = PublicSigningKeys(fetch, clock=lambda: now[0])
        self.assertIsNotNone(cache.get('key-A'))
        now[0] = 301
        self.assertIsNone(cache.get('key-A'))
        self.assertIsNone(cache.get('key-A'))

    def test_bad_key_documents_fall_back_and_transport_errors_are_sanitized(self):
        documents = [[], {'keys': 'invalid'}, {'keys': [self.public, self.public]},
                     {'keys': [self.public | {'x': 'invalid'}]},
                     {'keys': [self.public | {'kty': 'RSA'}]},
                     {'keys': [self.public | {'d': 'PRIVATE-MARKER'}]}]
        with self.store(remote_status=401) as (store, seen):
            for document in documents:
                with self.subTest(document=str(document)[:25]):
                    store.identity.signing_keys = PublicSigningKeys(lambda: document)
                    with self.assertRaises(HTTPException) as rejected:
                        store.user(access_token(self.private))
                    self.assertEqual(rejected.exception.status_code, 401)
                    self.assertNotIn('PRIVATE-MARKER', rejected.exception.detail)
        def handler(request):
            if request.url.path.endswith('/jwks.json'):
                raise httpx.ReadTimeout('PRIVATE-INTERNAL-ERROR')
            return httpx.Response(401, json={'message': 'PRIVATE-INTERNAL-ERROR'})
        client = httpx.Client(transport=httpx.MockTransport(handler))
        with patch.dict(os.environ, {'AUTH_VERIFICATION': 'auto'}), patch('app.main.httpx.Client', return_value=client):
            store = SupabaseStore(PROJECT, 'test-key')
        try:
            with self.assertRaises(HTTPException) as rejected:
                store.user(access_token(self.private))
            self.assertEqual(rejected.exception.status_code, 401)
            self.assertNotIn('PRIVATE', rejected.exception.detail)
        finally:
            store.close()

    def test_api_warm_auth_reduces_upstream_calls_and_keeps_rls_token(self):
        with TemporaryDirectory() as tmp, TestClient(create_app('local', tmp + '/test.db')) as local:
            document = local.get('/v3/workspace').json()['workspace'] | {'requests': []}
        token = access_token(self.private)
        seen = []
        def handler(request):
            seen.append(request)
            if request.url.path.endswith('/jwks.json'):
                return httpx.Response(200, json={'keys': [self.public]})
            self.assertEqual(request.headers['Authorization'], 'Bearer ' + token)
            if request.url.path == '/rest/v1/nextmeal_workspaces':
                self.assertEqual(request.url.params['user_id'], 'eq.' + DEMO_USER)
                return httpx.Response(200, json=[{'revision': 0, 'document': document}])
            if request.url.path == '/rest/v1/rpc/nextmeal_workspace_put':
                return httpx.Response(200, json={'saved': True})
            raise AssertionError(request.url)
        client = httpx.Client(transport=httpx.MockTransport(handler))
        settings = {'SUPABASE_URL': PROJECT, 'SUPABASE_PUBLISHABLE_KEY': 'test-key', 'AUTH_VERIFICATION': 'auto'}
        with patch.dict(os.environ, settings), patch('app.main.httpx.Client', return_value=client), TestClient(create_app('supabase')) as app:
            headers = {'Authorization': 'Bearer ' + token}
            cold = app.get('/v3/workspace', headers=headers)
            warm = app.get('/v3/workspace', headers=headers)
            command = {'request_id': str(uuid4()), 'expected_revision': 0, 'action': 'ingredient.create', 'payload': {'name': 'PRIVATE-FOOD', 'unit': 'g'}}
            preview = app.post('/v3/preview?compact=true', json=command, headers=headers)
            saved = app.post('/v3/commands', json=command, headers=headers)
            self.assertEqual([r.status_code for r in [cold, warm, preview, saved]], [200] * 4)
            self.assertEqual([r.headers['X-Upstream-Requests'] for r in [cold, warm, preview, saved]], ['2', '1', '1', '2'])
            self.assertEqual(saved.headers['X-Auth-Verification'], 'jwks')
            self.assertFalse(any(r.url.path == '/auth/v1/user' for r in seen))
            # A revoked/rejected token is still rejected by the actual Data API.
            client._transport = httpx.MockTransport(lambda request: httpx.Response(401, json={'message': 'JWT rejected'}))
            self.assertEqual(app.get('/v3/workspace', headers=headers).status_code, 401)


if __name__ == '__main__':
    unittest.main()
