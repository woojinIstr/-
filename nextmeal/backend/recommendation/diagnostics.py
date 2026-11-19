"""Configuration checks and safe error codes for the recommendation adapter."""
import importlib.util
import os


FALLBACK_MESSAGES = {
    'not_configured': 'AI 연결 설정이 준비되지 않아 현재 재료와 조건으로 기본 추천을 표시합니다.',
    'sdk_missing': 'AI 연결 준비가 완료되지 않아 현재 재료와 조건으로 기본 추천을 표시합니다.',
    'authentication_error': 'AI 연결 설정을 확인해야 해 현재 재료와 조건으로 기본 추천을 표시합니다.',
    'permission_denied': 'AI 사용 권한을 확인해야 해 현재 재료와 조건으로 기본 추천을 표시합니다.',
    'model_unavailable': 'AI 모델 연결 설정을 확인해야 해 현재 재료와 조건으로 기본 추천을 표시합니다.',
    'invalid_request': 'AI 요청을 처리하지 못해 현재 재료와 조건으로 기본 추천을 표시합니다.',
    'quota_exceeded': 'AI 이용 한도에 도달해 현재 재료와 조건으로 기본 추천을 표시합니다.',
    'rate_limited': 'AI 요청이 몰려 현재 재료와 조건으로 기본 추천을 표시합니다. 잠시 후 다시 추천받을 수 있어요.',
    'timeout': 'AI 응답이 늦어 현재 재료와 조건으로 기본 추천을 표시합니다. 다시 추천받을 수 있어요.',
    'connection_error': 'AI에 연결하지 못해 현재 재료와 조건으로 기본 추천을 표시합니다. 잠시 후 다시 추천받을 수 있어요.',
    'invalid_response': 'AI 응답을 확인하지 못해 현재 재료와 조건으로 기본 추천을 표시합니다. 다시 추천받을 수 있어요.',
    'service_error': 'AI 서비스에 오류가 있어 현재 재료와 조건으로 기본 추천을 표시합니다. 잠시 후 다시 추천받을 수 있어요.',
}


def configuration_status():
    """Inspect configuration without making an external request or exposing a key."""
    return {
        'check': 'configuration_only',
        'key_configured': bool(os.getenv('OPENAI_API_KEY', '').strip()),
        'sdk_available': importlib.util.find_spec('openai') is not None,
        'model': os.getenv('OPENAI_MODEL', '').strip() or 'gpt-4.1-mini',
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
        403: 'permission_denied',
    }.get(status, 'service_error')
