"""Configuration checks and safe error codes for the recommendation adapter."""
import importlib.util
import os

OPENROUTER_URL = 'https://openrouter.ai/api/v1'
FREE_MODEL = 'google/gemma-4-26b-a4b-it:free'


def openrouter_model():
    return os.getenv('OPENROUTER_MODEL', '').strip() or FREE_MODEL


def openrouter_key():
    key = os.getenv('OPENROUTER_API_KEY', '').strip()
    if key:
        return key
    legacy = os.getenv('OPENAI_API_KEY', '').strip()
    return legacy if legacy.startswith('sk-or-') else ''


FALLBACK_MESSAGES = {
    'not_configured': 'AI 연결 설정이 준비되지 않아 현재 재료와 조건으로 기본 추천을 표시합니다.',
    'sdk_missing': 'AI 연결 준비가 완료되지 않아 현재 재료와 조건으로 기본 추천을 표시합니다.',
    'authentication_error': 'AI 연결 설정을 확인해야 해 현재 재료와 조건으로 기본 추천을 표시합니다.',
    'permission_denied': 'AI 사용 권한을 확인해야 해 현재 재료와 조건으로 기본 추천을 표시합니다.',
    'model_unavailable': 'AI 모델 연결 설정을 확인해야 해 현재 재료와 조건으로 기본 추천을 표시합니다.',
    'invalid_request': 'AI 요청을 처리하지 못해 현재 재료와 조건으로 기본 추천을 표시합니다.',
    'quota_exceeded': 'AI 이용 한도에 도달해 현재 재료와 조건으로 기본 추천을 표시합니다.',
    'rate_limited': 'AI 서비스의 요청 한도에 걸려 기본 추천을 표시합니다. 잠시 후 다시 시도해 주세요.',
    'credit_unavailable': 'AI 서비스의 결제 한도를 확인해야 해 현재 재료와 조건으로 기본 추천을 표시합니다.',
    'timeout': 'AI 응답이 늦어 현재 재료와 조건으로 기본 추천을 표시합니다. 다시 추천받을 수 있어요.',
    'connection_error': 'AI에 연결하지 못해 현재 재료와 조건으로 기본 추천을 표시합니다. 잠시 후 다시 추천받을 수 있어요.',
    'invalid_response': 'AI 응답을 확인하지 못해 현재 재료와 조건으로 기본 추천을 표시합니다. 다시 추천받을 수 있어요.',
    'service_error': 'AI 서비스에 오류가 있어 현재 재료와 조건으로 기본 추천을 표시합니다. 잠시 후 다시 추천받을 수 있어요.',
}


def configuration_status():
    """Inspect configuration without making an external request or exposing a key."""
    return {
        'check': 'configuration_only',
        'key_configured': bool(openrouter_key()),
        'sdk_available': importlib.util.find_spec('openai') is not None,
        'provider': 'openrouter',
        'model': openrouter_model(),
    }


def failure_code(error):
    """Classify SDK failures without returning provider messages or credentials."""
    if isinstance(error, ImportError):
        return 'sdk_missing'
    try:
        import openai
    except ImportError:
        return 'sdk_missing'
    if isinstance(error, openai.APITimeoutError):
        return 'timeout'
    if isinstance(error, openai.APIConnectionError):
        return 'connection_error'
    status = getattr(error, 'status_code', None)
    if status == 429:
        return 'quota_exceeded' if getattr(error, 'code', None) == 'insufficient_quota' else 'rate_limited'
    if getattr(error, 'code', None) == 'model_not_found' or status == 404:
        return 'model_unavailable'
    return {
        400: 'invalid_request',
        401: 'authentication_error',
        402: 'credit_unavailable',
        403: 'permission_denied',
    }.get(status, 'service_error')
