# 다음한끼 추천 API

C의 `d71892f`를 B v0.3.5의 작업 공간에 연결했습니다. B는 한국 날짜, 재고, 메뉴, 인증을 제공합니다. 추천은 사용자 계정의 자료를 읽고, 최초 접속 시 기존 작업 공간 초기화 절차를 따릅니다. 사용자가 식사를 등록할 때는 기존 `POST /v3/commands`의 `meal.save`를 호출하세요.

| 요청 | 입력 | 응답 |
|---|---|---|
| `GET /v3/recommendations` | 선택 쿼리 `target_date`, `servings`(0.1~12), `max_minutes`(1~1440), `excluded_ids`, `preferred_ids`, `limit`(1~30) | `revision`, `recommendations`, `notice` |
| `POST /v3/gpt-recommendations` | JSON 본문의 `user_request`(공백을 제외해 글자가 있는 문자열, 최대 500자), 선택 기본값 `target_date`와 `servings`(0.1~12) | `revision`, `source`, `message`, `conditions`, `recommendations` |

Supabase 모드는 두 API 모두 `Authorization: Bearer <사용자 액세스 토큰>`을 받습니다. 로컬 시연 모드는 테스트 계정으로 읽습니다. 두 API의 응답은 `private, no-store`입니다. 규칙 API에서 재료 ID 여러 개를 선택할 때는 같은 쿼리 이름을 반복하세요. 현재 계정에 없는 ID를 보내면 422가 반환됩니다.

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

`backend/.env`에 `OPENAI_API_KEY`를 입력하고 서버를 재시작하면, 조건을 통과한 메뉴가 있을 때 OpenAI를 호출합니다. `OPENAI_MODEL`은 선택이며 기본값은 `gpt-4.1-mini`입니다. 운영에서는 서버 환경변수에 값을 설정하세요. API 키는 프론트 설정이나 GitHub에 올리지 마세요.

OpenAI에는 사용자 입력 문장과 추천 후보를 전송합니다. 직접 입력 화면에는 추천에 필요한 조건만 적도록 안내하세요. 키가 비어 있으면 외부 호출 없이 규칙 추천을 반환합니다. OpenAI에서 실패할 경우 서버 로그에 오류 종류가 기록됩니다.

통합 화면은 이 API 응답의 `revision`이 화면의 작업 공간과 일치할 때 추천을 추가할 수 있습니다. 식사 저장에는 서버가 적용한 날짜와 인분, 화면에서 선택한 끼니를 사용합니다. 시작 파일로 실행하면 필요한 SDK가 설치됩니다. Supabase SQL 변경은 필요 없습니다.
