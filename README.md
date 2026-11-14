# v0.3 통합본 안내

현재 실행 방법은 프로젝트 최상위 README.md를 따르세요. 새 화면은 /v3 API를 사용하며 세부 형식은 docs/api-v0.3.md에 있습니다. 아래는 이전 v0.1~v0.2 기록입니다.

---

# 다음한끼 백엔드 — 0.2.0

재고 CRUD에 메뉴 조회·식사 계획·외식·취소 API를 추가했습니다.

**기존 v0.1 사용자: docs/upgrade-v0.2.md부터 확인하세요. 이미 적용한 001 SQL은 다시 실행하지 않습니다.**
Python 3.11 이상 사용. 테스트 환경: Python 3.11+, requirements.txt에 기록된 패키지.

## Windows에서 실행
프로젝트 폴더를 VS Code로 열고 PowerShell 터미널에서:

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --reload --env-file .env --host 127.0.0.1
```

브라우저에서 http://127.0.0.1:8000/docs 를 열면 화면 없이 API를 실행할 수 있습니다.
GET /ingredients에서 재료 ID를 확인한 뒤 POST /inventory의 Try it out에 입력:

```json
{
  "ingredient_id": "10000000-0000-4000-8000-000000000001",
  "quantity": 300,
  "unit": "g",
  "storage_location": "fridge"
}
```

GET /inventory로 조회하고 반환된 inventory_id를 PATCH 경로에 넣어 `{"quantity":180}`으로 수정합니다.
DELETE는 잘못 등록한 재고를 삭제합니다. 식사 연결 기능을 추가할 때 삭제 규칙을 재검토해야 합니다.
로컬 데이터는 nextmeal.local.db에 저장됩니다. 새 프로세스로 실행해도 유지됩니다.
로컬 모드는 고정 데모 사용자 한 명을 사용하며 로그인·다중 사용자 서비스를 제공하지 않습니다.
로컬 모드는 localhost에서만 실행하세요. 실제 서비스에는 Supabase 모드를 사용합니다.

## Supabase 연결
1. 전용 Supabase 프로젝트를 만들고 SQL Editor에서 migrations/001_inventory.sql과 002_recipes_meals.sql을 순서대로 한 번씩 실행합니다.
2. `.env`의 APP_MODE를 supabase로 바꿉니다.
3. SUPABASE_URL과 SUPABASE_PUBLISHABLE_KEY를 본인 컴퓨터의 `.env`에 설정합니다. 관리자 키는 필요하지 않습니다.
4. A/D 담당 로그인에서 받은 access_token을 API의 Authorization: Bearer 헤더로 전달합니다. /docs의 Authorize에도 토큰만 넣을 수 있습니다.
5. 서버는 Supabase Auth로 사용자를 확인하고 동일 토큰으로 DB에 접근합니다. DB의 RLS도 사용자별 접근을 제한합니다.
6. 두 개의 테스트 계정으로 조회·수정·삭제 격리를 실제 환경에서 점검합니다.

실제 Supabase 프로젝트 연결, SQL 실행, 실환경 RLS 테스트는 아직 진행하지 않았습니다.
APP_MODE 미설정 시 Supabase 설정을 요구합니다. 잘못된 설정에서 로컬 모드로 자동 전환하지 않습니다.
GET /health는 프로세스 확인용이며 DB 연결 성공을 의미하지 않습니다.

## 테스트
```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## GitHub 공유
공유 저장소 주소가 정해지면 저장소를 clone하고 이 폴더의 내용을 팀이 합의한 backend/ 아래 복사합니다.
루트 .gitignore에서도 .env, .venv, *.db가 제외되는지 확인합니다.
별도 작업 브랜치 예: feat/backend-inventory. main에 직접 올리지 말고 PR로 검토합니다.
현재 원격 저장소 연결·push는 수행하지 않았습니다.

## 범위와 다음 단계
- 구현: 서버, CORS, 입력 검증, 공통 재료 3개, 재고 CRUD, 로컬 영속 저장, Supabase REST/Auth 어댑터, SQL 및 RLS, 테스트, OpenAPI 명세.
- 추가 구현: 레시피 4개·식사 등록/조회/수정·외식/취소·버전 충돌 방지.
- 미구현: 실제 조리 차감·장보기 서버 계산·변경안·이력·AI·로그인 UI 연결.
- PATCH 수량은 증감량이 아닌 최종 잔량입니다. 동시 수정은 마지막 쓰기가 반영됩니다. 조리 차감 단계에서 트랜잭션·중복 처리 방지를 추가해야 합니다.
- API 단위: g / ml / count. 구매 묶음은 서로 다른 inventory_id입니다. 재료 종류 ID는 C와 공유합니다.
- 숫자는 JSON number, DB는 Supabase numeric. 향후 원가·정밀 계산은 Decimal 정책을 별도 확정합니다.

공식 참고: https://fastapi.tiangolo.com/tutorial/testing/ , https://supabase.com/docs/reference/python/auth-getuser
