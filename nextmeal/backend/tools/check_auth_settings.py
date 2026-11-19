"""Read Supabase's public auth settings. Never creates users or changes settings."""
import argparse
import base64
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values
import httpx


def configuration(values):
    if values.get('APP_MODE', 'supabase') != 'supabase':
        raise ValueError('APP_MODE가 local입니다. Supabase를 사용하는 .env에서 확인하세요.')
    url = str(values.get('SUPABASE_URL') or '').strip().rstrip('/')
    key = str(values.get('SUPABASE_PUBLISHABLE_KEY') or '').strip()
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment or any(c.isspace() for c in url+key)):
        raise ValueError('SUPABASE_URL에 실제 HTTPS 프로젝트 주소를 입력하세요.')
    if not key.startswith('sb_publishable_'):
        try:
            role = json.loads(base64.urlsafe_b64decode(key.split('.')[1]+'==='))['role']
            if role != 'anon':
                raise ValueError()
        except Exception:
            raise ValueError('SUPABASE_PUBLISHABLE_KEY에는 Publishable 또는 anon key를 입력하세요.') from None
    return url, key


def inspect_settings(values, client):
    url, key = configuration(values)
    try:
        response = client.get(url+'/auth/v1/settings', headers={'apikey':key})
        response.raise_for_status()
        data = response.json()
        if not isinstance(data,dict):
            raise ValueError()
    except httpx.HTTPStatusError as error:
        raise ValueError(f'인증 설정 조회에 실패했습니다(HTTP {error.response.status_code}). 프로젝트 주소·공개 키를 확인하세요.') from None
    except (httpx.RequestError,ValueError):
        raise ValueError('인증 설정을 읽지 못했습니다. 네트워크와 프로젝트 상태를 확인하세요.') from None
    external = data.get('external') if isinstance(data.get('external'),dict) else {}
    # Missing fields mean unknown, never "ready".
    signup = data.get('disable_signup')
    email = external.get('email')
    auto = data.get('mailer_autoconfirm')
    return dict(signup_allowed=not signup if type(signup) is bool else None,
                email_login_enabled=email if type(email) is bool else None,
                email_confirmation_required=not auto if type(auto) is bool else None)


def main(argv=None):
    parser=argparse.ArgumentParser(description='Supabase 회원가입 공개 설정 점검(읽기 전용)')
    parser.add_argument('--env-file',type=Path,default=Path(__file__).resolve().parents[1]/'.env')
    args=parser.parse_args(argv)
    try:
        if not args.env_file.is_file():
            raise ValueError('backend/.env를 찾지 못했습니다. 먼저 통합본을 실행해 기존 설정을 복사하세요.')
        values=dict(dotenv_values(args.env_file,encoding='utf-8-sig'))
        # Match uvicorn/python-dotenv: pre-existing environment takes precedence.
        for key in ('APP_MODE','SUPABASE_URL','SUPABASE_PUBLISHABLE_KEY'):
            if key in os.environ:values[key]=os.environ[key]
        with httpx.Client(timeout=httpx.Timeout(10,connect=5),follow_redirects=False) as client:
            result=inspect_settings(values,client)
        print('Supabase 회원가입 설정 점검 (계정 생성·설정 변경 없음)')
        labels={'signup_allowed':'신규 회원가입 허용','email_login_enabled':'이메일 로그인 사용','email_confirmation_required':'가입 후 이메일 인증 필요'}
        for key,label in labels.items():
            print(label+': '+{True:'예',False:'아니요',None:'확인 필요'}[result[key]])
        print('\n별도 확인: Site URL, Redirect URLs, SMTP와 실제 인증 메일 수신.')
        print('이 결과만으로 회원가입 화면·메일 전달·콜백 연결 완료를 뜻하지 않습니다.')
        return 0 if result['signup_allowed'] is True and result['email_login_enabled'] is True else 1
    except ValueError as error:
        print('점검 실패: '+str(error))
        return 1


if __name__=='__main__':
    raise SystemExit(main())
