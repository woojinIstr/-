# 다음한끼 추천 API

C의 `d71892f`를 B v0.3.5의 작업 공간에 연결했습니다. B는 한국 날짜, 재고, 메뉴, 인증을 제공합니다. 추천은 사용자 계정의 자료를 읽고, 최초 접속 시 기존 작업 공간 초기화 절차를 따릅니다. 사용자가 식사를 등록할 때는 기존 `POST /v3/commands`의 `meal.save`를 호출하세요.

| 요청 | 입력 | 응답 |
|---|---|---|
| `GET /v3/recommendations` | 선택 쿼리 `target_date`, `servings`(0.1~12), `max_minutes`(1~1440), `excluded_ids`, `preferred_ids`, `limit`(1~30) | `revision`, `recommendations`, `notice` |
| `POST /v3/gpt-recommendations` | JSON 본문의 `user_request`(공백을 제외해 글자가 있는 문자열, 최대 500자), 선택 기본값 `target_date`와 `servings`(0.1~12) | `revision`, `source`, `message`, `conditions`, `recommendations` |
| `GET /v3/recommendation-status` | 로그인 인증 | `check=configuration_only`, `key_configured`, `sdk_available`, `model`, `version` |

Supabase 모드에서 추천·상태 API는 `Authorization: Bearer <사용자 액세스 토큰>`을 받습니다. 로컬 시연 모드는 테스트 계정으로 읽습니다. 응답은 `private, no-store`입니다. 규칙 API에서 재료 ID 여러 개를 선택할 때는 같은 쿼리 이름을 반복하세요. 현재 계정에 없는 ID를 보내면 422가 반환됩니다.

v0.3.8의 상태 확인 API에도 같은 인증과 캐시 정책이 적용됩니다. `key_configured=true`는 서버에 값이 있다는 의미이며, 실제 OpenAI 연결 성공은 추천 응답의 `source=gpt`로 확인합니다.

## v0.3.8 호출 결과 구분

기존 응답에 `reason_code`를 추가했습니다. 성공한 AI 추천은 `source=gpt`, `reason_code=null`입니다. `source`와 기존 추천 배열 형식은 그대로 사용할 수 있습니다.

| reason_code | 확인할 내용 |
|---|---|
| `not_configured` | 서버 환경변수의 `OPENROUTER_API_KEY` 설정 |
| `sdk_missing` | 서버의 requirements.txt 설치 |
| `authentication_error` | API 키의 유효성 |
| `permission_denied` | 프로젝트와 모델 사용 권한 |
| `model_unavailable` | `OPENROUTER_MODEL` 이름과 모델 접근 권한 |
| `quota_exceeded` | API 계정의 이용 한도 |
| `rate_limited` | 요청 빈도, 잠시 후 재시도 |
| `timeout` | 응답 지연, 네트워크 상태와 재시도 |
| `connection_error` | 서버의 외부 네트워크 연결 |
| `invalid_request` | 요청 형식과 선택한 모델의 지원 여부 |
| `invalid_response` | AI 응답의 JSON, 메뉴 ID와 순위 검증 실패 |
| `service_error` | 외부 서비스 또는 예기치 않은 처리 오류 |
| `no_candidates` | 조건에 맞는 등록 메뉴 없음 |
| `conditions_unclear` | 조건을 명확히 다시 입력 |

오류 응답과 로그에는 고정된 원인 코드와 오류 종류만 사용합니다. 공급자가 반환한 원문 오류는 전송하지 않습니다. 오류 때도 서버가 검증한 제외·시간·인분·날짜 조건을 유지합니다.

## 실제 호출 확인 프로그램

Windows에서 최상위 `CHECK_AI_WINDOWS.cmd`를 실행하면 설치된 서버 환경으로 샘플 재료와 메뉴를 사용해 실제 호출을 한 번 수행합니다. API 사용료가 발생할 수 있습니다. `source=gpt`만 성공으로 처리하며 응답에 적용된 조건, 메뉴 ID, 순위와 추천 이유를 출력합니다. 이 프로그램은 DB에 연결하지 않습니다.

설정만 확인하려면 프로젝트 최상위에서 다음 명령을 실행하세요.

```powershell
backend\.venv\Scripts\python.exe backend\tools\check_ai.py
```

실제 호출은 다음 명령으로도 실행할 수 있습니다.

```powershell
backend\.venv\Scripts\python.exe backend\tools\check_ai.py --live
```

`.env`를 수정한 뒤에는 실행 중인 서버도 재시작하세요. 프로그램과 서버 모두 기존 프로세스의 환경변수가 `.env`보다 우선합니다. 종료 코드 0은 설정 확인 모드에서는 설정이 준비됐다는 뜻이며, `--live` 모드에서는 실제 추천 응답을 받았다는 뜻입니다. 샘플 실호출 성공 후에는 로그인한 웹 화면에서 보유 재료를 이용한 추천과 식사 저장 흐름을 확인하세요.

## 자연어 요청 확인

서버를 실행하고 `http://127.0.0.1:8000/docs`의 `POST /v3/gpt-recommendations`에서 아래 본문을 실행하세요. 자연어 문장이 URL에 남지 않도록 C 초안의 GET을 POST 본문으로 옮겼습니다.

```json
{
  "user_request": "달걀 제외 1.5시간 이내 2인분"
}
```

- `conditions.max_minutes=90`, `servings=2`이며 기본 날짜는 한국 기준 오늘입니다. v0.3.7부터 본문의 `target_date`와 `servings`를 기본값으로 지정할 수 있습니다. 문장에 명시한 날짜와 인분을 먼저 적용합니다. `excluded_ids`에는 계정에 등록된 달걀, 계란, 에그의 해당 ID가 들어갑니다.
- `source=gpt`는 OpenAI의 응답에 포함된 유효한 메뉴 ID를 순서대로 적용한 결과입니다. `source=rules`는 같은 조건으로 계산한 기본 결과이거나 조건에 해당하는 메뉴가 없다는 뜻입니다. `source=needs_input`은 지원하지 않는 조건을 다시 입력해야 한다는 뜻으로 빈 추천과 안내를 반환합니다.
- 추천 항목에는 `recipe_id`, `name`, `minutes`, `score`, `ingredients`, `missing`, `ready`, `reason`이 있습니다. GPT가 선택한 항목은 선택 순서대로 `rank`를 포함합니다. 클라이언트는 `recipe_id`로 등록된 메뉴를 찾고, 수량은 서버 계산값을 사용하세요.
- 한국어 조건 해석은 제외 재료, 날짜, 최대 조리시간, 인분 등 제한된 표현을 지원합니다. 예를 들어 `1시간 30분 이내`는 `90분 이내`로 입력하세요. 화면에서 시간이나 재료를 직접 고르면 규칙 API에 해당 값을 전달할 수 있습니다.
- `ready`는 해당 날짜에 사용 가능한 재고로 **이 메뉴 한 건**을 조리할 수 있는지를 나타냅니다. 다른 예정 식사에는 기존 B 장보기 계산을 사용하세요. 등록 이름 기준 재료 제외로 식품 안전이나 알레르기를 판정할 수는 없습니다.

## 서버 설정

`backend/.env`에 `OPENROUTER_API_KEY`를 입력하고 서버를 재시작하면, 조건을 통과한 메뉴가 있을 때 OpenRouter를 호출합니다. `OPENROUTER_MODEL`은 선택이며 기본값은 `google/gemma-4-26b-a4b-it:free`입니다. 운영에서는 서버 환경변수에 값을 설정하세요. API 키는 프론트 설정이나 GitHub에 올리지 마세요.

OpenAI에는 사용자 입력 문장과 추천 후보를 전송합니다. 직접 입력 화면에는 추천에 필요한 조건만 적도록 안내하세요. 키가 비어 있으면 외부 호출 없이 규칙 추천을 반환합니다. OpenAI에서 실패할 경우 서버 로그에 오류 종류가 기록됩니다.

통합 화면은 이 API 응답의 `revision`이 화면의 작업 공간과 일치할 때 추천을 추가할 수 있습니다. 식사 저장에는 서버가 적용한 날짜와 인분, 화면에서 선택한 끼니를 사용합니다. 시작 파일로 실행하면 필요한 SDK가 설치됩니다. Supabase SQL 변경은 필요 없습니다.
