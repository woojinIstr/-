"""Check configuration or make one real recommendation request with sample data."""
import argparse
import json
from pathlib import Path
import sys

from dotenv import load_dotenv

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from recommendation.diagnostics import FALLBACK_MESSAGES, configuration_status
from recommendation.gpt import recommend_with_gpt


def sample_workspace():
    return {
        'ingredients': [
            {'id': 'sample-egg', 'name': '달걀', 'unit': 'count'},
            {'id': 'sample-rice', 'name': '밥', 'unit': 'g'},
            {'id': 'sample-onion', 'name': '양파', 'unit': 'g'},
        ],
        'inventory': [
            {'ingredient_id': 'sample-egg', 'quantity': 2, 'unit': 'count'},
            {'ingredient_id': 'sample-rice', 'quantity': 400, 'unit': 'g'},
            {'ingredient_id': 'sample-onion', 'quantity': 100, 'unit': 'g'},
        ],
        'recipes': [
            {'id': 'sample-onion-rice', 'name': '양파밥', 'minutes': 8, 'base_servings': 1,
             'ingredients': [
                 {'ingredient_id': 'sample-rice', 'quantity': 100, 'unit': 'g'},
                 {'ingredient_id': 'sample-onion', 'quantity': 50, 'unit': 'g'},
             ]},
            {'id': 'sample-egg-rice', 'name': '달걀볶음밥', 'minutes': 30, 'base_servings': 1,
             'ingredients': [
                 {'ingredient_id': 'sample-rice', 'quantity': 100, 'unit': 'g'},
                 {'ingredient_id': 'sample-egg', 'quantity': 1, 'unit': 'count'},
             ]},
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description='샘플 데이터로 AI 연결을 확인합니다.')
    parser.add_argument('--env-file', type=Path, default=BACKEND / '.env')
    parser.add_argument('--live', action='store_true', help='설정한 OpenRouter 모델을 한 번 실제 호출합니다.')
    args = parser.parse_args(argv)
    # Match the running server: existing process variables take precedence.
    load_dotenv(args.env_file, override=False, encoding='utf-8-sig')
    status = configuration_status()
    print(json.dumps(status, ensure_ascii=False, indent=2))
    if not status['key_configured']:
        print('확인 실패 · backend/.env에 OPENROUTER_API_KEY를 설정하고 서버를 재시작하세요.')
        return 1
    if not status['sdk_available']:
        print('확인 실패 · START_WINDOWS.cmd를 실행해 서버 라이브러리를 설치하세요.')
        return 1
    if not args.live:
        print('설정만 확인했습니다. 실제 호출 확인은 CHECK_AI_WINDOWS.cmd를 실행하세요.')
        return 0
    print('샘플 데이터로 설정한 OpenRouter 모델을 한 번 호출합니다.')
    request = '달걀 제외 10분 이내 2인분 내일 저녁 추천해줘'
    result = recommend_with_gpt(sample_workspace(), request)
    success = result['source'] == 'gpt'
    print(json.dumps({
        'check': 'live_openrouter', 'success': success, 'provider': status['provider'], 'model': status['model'],
        'user_request': request, **result,
    }, ensure_ascii=False, indent=2))
    if success:
        print('실제 호출 성공 · AI가 고른 샘플 메뉴와 추천 이유를 받았습니다.')
        return 0
    print('실제 호출 확인 실패 · ' + FALLBACK_MESSAGES.get(result.get('reason_code'), result['message']))
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
