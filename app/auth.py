"""Verify Supabase access tokens with cached public keys, or the Auth server.

Only public signing keys are cached. Every JWT is verified on every request;
tokens, users and authentication decisions are never cached.
"""
from threading import Lock
from time import monotonic
from uuid import UUID

import jwt
from fastapi import HTTPException

from .timing import measure, note_auth

ASYMMETRIC_ALGORITHMS = ('ES256', 'RS256', 'EdDSA')


class SigningKeysUnavailable(Exception):
    """Use the existing authenticated Auth endpoint when discovery is unavailable."""


class PublicSigningKeys:
    def __init__(self, fetch, clock=monotonic):
        self.fetch, self.clock = fetch, clock
        self.keys = {}
        self.expires_at = 0.0
        self.next_fetch_at = 0.0
        self.lock = Lock()

    @staticmethod
    def parse(document):
        if not isinstance(document, dict) or not isinstance(document.get('keys'), list) or len(document['keys']) > 128:
            raise SigningKeysUnavailable()
        keys = {}
        for raw in document['keys']:
            if not isinstance(raw, dict):
                raise SigningKeysUnavailable()
            kid, algorithm = raw.get('kid'), raw.get('alg')
            if not isinstance(kid, str) or not kid or len(kid) > 256:
                continue
            if algorithm not in ASYMMETRIC_ALGORITHMS or raw.get('use', 'sig') != 'sig':
                continue
            if 'key_ops' in raw and (not isinstance(raw['key_ops'], list) or 'verify' not in raw['key_ops']):
                continue
            if kid in keys:
                raise SigningKeysUnavailable()
            if raw.get('kty') != {'ES256': 'EC', 'RS256': 'RSA', 'EdDSA': 'OKP'}[algorithm]:
                raise SigningKeysUnavailable()
            if any(field in raw for field in ('d', 'p', 'q', 'dp', 'dq', 'qi', 'oth')):
                raise SigningKeysUnavailable()
            try:
                key = jwt.PyJWK.from_dict(raw)
            except (jwt.PyJWTError, ValueError, TypeError, KeyError):
                raise SigningKeysUnavailable() from None
            if key.algorithm_name != algorithm or key.key_type not in ('EC', 'RSA', 'OKP'):
                raise SigningKeysUnavailable()
            keys[kid] = key
        return keys

    def get(self, kid):
        # One discovery request at a time. Unknown kids cannot force a fetch for
        # each request. A new key inside the cooldown is checked by Auth instead.
        with measure('auth_lock'):
            self.lock.acquire()
        try:
            now = self.clock()
            if now < self.expires_at and kid in self.keys:
                return self.keys[kid]
            if now < self.next_fetch_at:
                return None
            self.next_fetch_at = now + 30
            try:
                keys = self.parse(self.fetch())
            except SigningKeysUnavailable:
                if now >= self.expires_at:
                    self.keys = {}
                return None
            self.keys = keys
            self.expires_at = self.clock() + 300
            return self.keys.get(kid)
        finally:
            self.lock.release()


class SupabaseIdentity:
    def __init__(self, url, fetch_keys, remote_user, strategy='auto'):
        if strategy not in ('auto', 'remote'):
            raise RuntimeError('AUTH_VERIFICATION must be auto or remote')
        self.issuer = url.rstrip('/') + '/auth/v1'
        self.remote_user, self.strategy = remote_user, strategy
        self.signing_keys = PublicSigningKeys(fetch_keys)

    @staticmethod
    def reject():
        note_auth('jwt-rejected')
        raise HTTPException(401, '로그인이 필요하거나 접근 권한이 없습니다.')

    def user(self, token):
        # Nested transport events count requests separately, without counting
        # their elapsed time twice in auth_ms.
        with measure('auth'):
            if self.strategy == 'remote':
                note_auth('remote-forced')
                return self.remote_user(token)
            try:
                if len(token) > 32768:
                    self.reject()
                header = jwt.get_unverified_header(token)
            except (jwt.PyJWTError, ValueError, TypeError):
                self.reject()
            algorithm = header.get('alg')
            if algorithm == 'HS256':
                note_auth('remote-legacy')
                return self.remote_user(token)
            if algorithm not in ASYMMETRIC_ALGORITHMS:
                self.reject()
            kid = header.get('kid')
            if kid is not None and (not isinstance(kid, str) or len(kid) > 256):
                self.reject()
            key = self.signing_keys.get(kid) if kid else None
            if key is None:
                note_auth('remote-fallback')
                return self.remote_user(token)
            try:
                # The allowed algorithm comes from the trusted configured JWKS,
                # never an algorithm list supplied by an unverified JWT header.
                claims = jwt.decode(
                    token, key.key, algorithms=[key.algorithm_name],
                    issuer=self.issuer, audience='authenticated', leeway=0,
                    options={'require': ['exp', 'iat', 'iss', 'aud', 'sub', 'role']},
                )
                if claims['role'] != 'authenticated':
                    self.reject()
                owner = str(UUID(claims['sub']))
            except (jwt.PyJWTError, ValueError, TypeError, KeyError):
                self.reject()
            note_auth('jwks')
            return owner
