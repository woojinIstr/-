# v0.2 적용 안내

## 이번에 완성한 범위

- 공통 재료 8종, A의 예시 레시피 4종을 UUID·기준 단위로 제공.
- 식사 등록·날짜별 조회·단건 조회·메뉴/날짜/시간대/인분 수정.
- 외식·취소 처리. 계획 및 상태 변경만으로 재고는 줄지 않음.
- 사용자별 접근 제한. 이전 버전 번호로 수정하면 409로 거절.

조리 차감·장보기 서버 계산·AI·변경안 미리보기·로그인 UI 연결은 다음 단계다.
현재 A의 배포 사이트는 수정하거나 재배포하지 않았다. integration/frontend-api.js는 A의 필드로 변환하는 연결용 모듈이며 App.jsx에 아직 연결되지 않았다.

## 적용 순서 Windows

1. 실행 중인 서버 터미널에서 Ctrl+C.
2. ZIP을 **새 폴더**에 압축 해제. 기존 실행 폴더의 `.env`는 지우거나 공유하지 말고 새 backend 폴더에 복사.
3. 기존 Supabase 프로젝트의 SQL Editor에서 `migrations/002_recipes_meals.sql` 전체를 한 번 실행. 001은 이미 적용했으므로 재실행하지 않음. 기존 재고는 유지됨.
4. VS Code로 새 backend 폴더를 열고 새 터미널에서:

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --reload --env-file .env --host 127.0.0.1
```

5. http://127.0.0.1:8000/docs 에서 기존처럼 테스트 계정 토큰으로 Authorize.

## 직접 검증

- `GET /recipes` → 200, 메뉴 4개.
- `GET /inventory` → 기존 재고 확인. 결과를 보관.
- `POST /meals`에 다음 입력. 날짜는 시험할 날짜로 변경 가능.

```json
{
  "meal_date": "2026-11-13",
  "meal_slot": "dinner",
  "recipe_id": "20000000-0000-4000-8000-000000000003",
  "servings": 1
}
```

- 201 응답에서 meal_id와 version(처음 0) 확인.
- `GET /meals?meal_date=2026-11-13` → 방금 등록한 식사 조회.
- `POST /meals/{meal_id}/eat-out`에 `{"expected_version":0}` → 200, eating_out, version 1.
- `GET /inventory` → 이전과 완전히 동일.
- 같은 외식 요청을 version 0으로 다시 전송 → 409. 두 번 변경하지 않음.
- 다른 새 식사를 등록하고 `/cancel`에 version 0 전송 → cancelled.
- 두 번째 계정으로 첫 계정 식사 조회·수정·외식·취소 시도 → 404, 목록에는 표시되지 않아야 함.

PATCH 예: `{"expected_version":0,"servings":2}`. 최신 조회 결과의 version을 사용. 이미 외식·취소한 식사는 이번 버전에서 다시 수정·복귀시키지 않음.
등록 POST 자체는 자동 중복 제거하지 않음. 성공 여부가 불명확하면 먼저 목록을 조회하며 무조건 재전송하지 않음.

## 검증 수준

Python 로컬 API·영속성·경합 테스트와 Supabase 요청 모의 테스트, JS 변환·요청 테스트를 수행했다.
002 SQL은 실제 프로젝트에서 실행하지 않았고 실환경 RLS도 아직 검증 전이다. 배포된 통합 서비스가 완성된 것은 아니다.
레시피 분량·조리 시간은 A의 개발용 데이터이며 실제 조리·영양 검수 결과가 아니다.
