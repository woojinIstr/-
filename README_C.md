# 다음한끼 C파트 — GPT 추천 연동 수정본 (2026-11-18)

**상태:** 코드·모의 SDK 테스트 검증 완료(14개 통과). **실제 OpenAI API 실호출 및 Render 통합 호출은 아직 수행하지 않았음.** API 키가 이 실행 환경에 없어 실호출 성공을 주장할 수 없습니다.

## 변경 및 보안
- `recommendation/conditions.py`: 한국어 요청의 제외 재료, 최대 조리시간, 인분(0.1~12), 날짜(Asia/Seoul)를 제한된 표현으로 파싱. 이해 못 한 조건은 `source=needs_input`과 빈 추천으로 반환하므로 **조건을 무시한 추천은 하지 않음**. 예: `달걀 제외 10분 이내 2인분 내일 저녁 추천해줘`.
- `engine.py`: KST 오늘 날짜 기본값, 숨김/만료/미구매 재고 제외, 후보별 재료 required/available/missing 첨부, 인분 스케일링.
- `gpt.py`: 사전 필터 후보에 `recipe_id`와 재료 목록 포함 → GPT는 JSON `recipe_ids`와 `message`만 반환 → 서버에서 ID 소속, 중복, 개수, 빈 문자열 및 JSON 구조 검증 → `recommendations`를 모델 순위 그대로 반환. 잘못된 응답·호출 오류는 **같은 필터 조건의** 기본 추천으로 복귀.
- `api.py`: 이전 `/v3/recommendations` 유지, `/v3/gpt-recommendations` 유지. 조회만 하며 DB 변경 안 함.
- `.env.example`: `OPENAI_API_KEY`와 `OPENAI_MODEL` 키 이름 안내. **실제 키 값을 GitHub에 저장하지 말 것.**

## 서버 통합 (B가 진행)
B FastAPI 코드 최상위(기존 `app/` 폴더와 같은 레벨)에 `recommendation/` 추가. B의 `app/main.py`에서 `register_workspace_routes(app, store, identity, mode)` 호출 직후 아래 두 줄 추가:

```python
from recommendation.api import register_recommendation_routes
register_recommendation_routes(app, identity)
```

B 백엔드의 `requirements.txt`에 `openai>=1.68,<3` 추가 (`requirements-C.txt` 참고) 후 재설치·재배포. B Render의 **비공개** 환경변수에 `OPENAI_API_KEY`를 설정하고 `OPENAI_MODEL=gpt-4.1-mini` 등 실제 계정에서 사용 가능한 모델을 설정. 프론트 `VITE_*` 변수에 키를 넣지 말 것. B API는 인증이 필요함.

**API 예시** (로그인 토큰 인증 필요):
- `GET /v3/recommendations?servings=2&max_minutes=10` — 규칙 기반
- `GET /v3/gpt-recommendations?user_request=달걀%20제외%2010분%20이내%202인분` — GPT 정렬

결과 `source`는 `gpt`, `rules`, `needs_input` 중 하나. `needs_input`이면 `message`를 안내하고 사용자가 제외 재료·시간·인분·날짜를 화면에서 직접 입력할 수 있도록 A와 UX 협의 필요. **현재 GET 쿼리에는 민감한 텍스트를 입력하지 말 것**(URL 로그에 남을 수 있음). GPT의 선택은 재고를 변경하거나 식사를 예약하지 않음. B의 기존 API를 통한 사용자 승인만 상태 변경 가능.

## 검증
```powershell
py -m unittest discover -s tests -v
```

2026-11-18 로컬(네트워크/비밀키 없이) 결과: **14 tests, OK**.
검사: 달걀 제외, 10분 이하, 2·3인분 재고, KST 내일/모레, 제외 재료 미등록 시 입력 요청, 0·13인분 거부, GPT 순위 및 배열 일치, API 성공 모의 응답, 네트워크 실패, 빈 응답, JSON 오류, 미등록/중복 ID, 필터 유지 및 원본 workspace 미변경.

## 실호출 확인(미실행)
- B가 `OPENAI_API_KEY`와 `OPENAI_MODEL`을 Render에 설정, 라우트 등록 후 `/docs`에서 인증 토큰으로 호출하고 `source=gpt` 응답 및 `recommendations`의 `recipe_id`, rank를 검증해야 함.
- 호출이 `source=rules`로 돌아오면 키/모델 권한/요청 오류 등을 서버의 민감정보 없는 로그로 점검. 실패 시 비밀키를 출력하지 않음.
- 외부 API 비용 발생 가능. 테스트용 샘플 계정 및 낮은 한도 사용 권장.

## 한계
- 자연어 해석은 의도적으로 제한적이며, 미지원 표현은 조건을 짐작하지 않고 직접 입력을 요구합니다. 특히 복잡한 여러 조건, 모호한 날짜·시간·제외 표현은 추가 UI 또는 파서 확장이 필요합니다.
- B의 다른 예정 식사에 이미 배정된 재고를 차감한 가용량은 별도 계산하지 않습니다. 추천의 `ready`는 단일 레시피 기준일 뿐 확정 가능한 재고 보장은 아닙니다.
- 식품 안전성, 알레르기, 영양, 실제 조리법은 검증하지 않습니다.
