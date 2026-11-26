# 다음한끼 프론트·백엔드 연결판 실행

A 원본 기준: hong46/daeum-hankki-react 커밋 6b53f027f49f0049a3c9007f8c4a182b5559d8ae.
B의 테스트 완료된 백엔드 v0.2와 연결하는 별도 작업본이다. A 저장소 및 Vercel 배포에는 아직 반영하지 않았다.

## 1. 백엔드 실행

기존 테스트를 통과한 backend 폴더를 사용한다. 백엔드 ZIP을 다시 교체하거나 SQL을 다시 실행하지 않는다.
backend/.env의 기존 Supabase 설정을 유지하고 아래 항목을 확인한다.

```dotenv
APP_MODE=supabase
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

쉼표 뒤에 공백을 넣지 않는다. 기존 서버를 Ctrl+C로 종료한 뒤 backend 폴더의 PowerShell에서 실행한다.

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --reload --env-file .env --host 127.0.0.1
```

이 창은 켜 둔다. http://127.0.0.1:8000/docs 에 기존 API가 보이는지 확인한다.

## 2. 프론트 설정

새 ZIP의 frontend 폴더를 연다. backend 폴더와 구분한다.
Windows 파일 탐색기에서 파일 이름 확장명을 표시하면 .env.txt로 잘못 저장하는 것을 피할 수 있다.
.env.example 파일을 복사해 같은 폴더에 .env로 저장한다.

```dotenv
VITE_APP_MODE=server
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_SUPABASE_URL=https://실제프로젝트주소.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=sb_publishable_실제키
```

URL과 Publishable key는 기존 backend/.env의 SUPABASE_URL 및 SUPABASE_PUBLISHABLE_KEY와 동일한 값으로 입력한다.
여기에 access_token, 비밀번호, service_role 또는 secret key를 넣지 않는다.
VITE_ 설정은 브라우저에 포함되므로 Publishable key만 사용한다.

## 3. 프론트 실행

Node.js 22 이상과 npm을 사용한다. frontend 폴더에서 별도의 PowerShell 창을 연다.

```powershell
npm.cmd ci
npm.cmd run dev
```

http://localhost:5173 으로 접속한다. 다른 개발 서버가 5173 포트를 사용 중이면 먼저 해당 창에서 Ctrl+C로 종료한다.
이 작업본은 CORS 주소가 바뀌지 않도록 5173 포트가 사용 중일 때 종료한다.
.env를 수정했다면 프론트도 Ctrl+C 후 npm.cmd run dev로 다시 실행한다.

## 4. 확인 순서

1. 기존 Supabase 테스트 계정의 이메일·비밀번호로 화면에서 로그인한다. Swagger에 토큰을 붙여 넣을 필요가 없다.
2. 식재료 메뉴에서 기존 계정의 재고가 보이는지 확인한다.
3. 테스트 재료를 추가하고 수정한다. Swagger GET /inventory에서도 같은 결과인지 확인한다.
4. 메뉴 화면에서 서버의 메뉴와 재료를 확인한다.
5. 식사 계획에서 날짜를 선택하고 식사를 추가한다. 변경 확인 화면의 ‘돌아가기’는 저장하지 않는다. ‘확인 및 저장’은 저장한다.
6. 계획 수정에서 메뉴·인분을 변경한다.
7. 한 식사는 외식으로 처리하고, 다른 새 식사는 취소한다. 재고 수량이 그대로인지 확인한다.
8. 로그아웃 후 두 번째 계정으로 로그인하여 첫 번째 계정 재고·식사가 나타나지 않는지 확인한다.
9. 브라우저 새로고침 후 첫 번째 계정으로 다시 로그인하여 저장된 내용이 유지되는지 확인한다.

## 현재 연결 범위

- 로그인: Supabase 이메일·비밀번호 인증. 회원가입·비밀번호 재설정 화면은 미포함.
- 재고: 공통 재료 선택, 조회·등록·수정·삭제. 단위는 공통 목록의 g/ml/count 기준이다. 임의 재료 생성은 미포함.
- 메뉴: 서버 데이터 조회. 개인 메뉴 생성은 미포함.
- 식사: 조회·등록·날짜/시간/메뉴/인분 수정·외식·취소. version으로 이전 상태의 수정을 거절한다.
- 확인 전에는 서버를 변경하지 않는다. 응답 성공 후 다시 조회한다. 중복 클릭을 차단한다.
- 조리 완료, AI 추천, 장보기는 서버 기능 준비 중으로 표시한다. 이 화면에서는 로컬 데모의 재고 차감·되돌리기를 실행하지 않는다.
- 원본 App.jsx는 유지했다. VITE_APP_MODE=demo로 변경 후 프론트를 재시작하면 기존 데모를 볼 수 있다. 데모 데이터와 계정의 서버 데이터를 합치지 않는다.
- 토큰은 메모리에서만 보관하고 만료 전에 갱신한다. 새로고침 후 다시 로그인한다. 로그아웃은 이 화면의 세션을 지우며 다른 기기의 세션을 종료하지 않는다.

## 오류 대응

- ‘설정이 필요합니다’: frontend/.env의 네 값을 확인하고 프론트를 재시작한다.
- Failed to fetch: 백엔드 실행 여부, API URL, CORS_ORIGINS 및 실제 접속 주소가 일치하는지 확인한다.
- 401: 같은 Supabase 프로젝트 계정인지 확인한 뒤 로그아웃하고 다시 로그인한다.
- 409: 다른 탭에서 수정되었거나 종료된 식사다. 확인창에서 돌아간 뒤 서버 새로고침을 누른다.
- 등록 결과를 확인할 수 없음: 네트워크가 끊겨도 서버 저장이 끝났을 수 있다. 새로고침으로 목록을 확인한 뒤 재등록 여부를 결정한다.
- 저장 후 조회 실패: 편집을 잠그고 새로고침을 요구한다. 저장 버튼을 다시 눌러 중복 등록하지 않는다.

## 팀 공유

이 ZIP의 frontend/는 A 담당 프론트 변경본이다. B 브랜치의 backend/를 덮어쓰지 않는다.
A 또는 D에게 전달하여 원본과 비교 후 A 브랜치 또는 integration 브랜치에 반영한다.
.env와 node_modules/, dist/는 업로드하지 않는다. .env.example, package-lock.json은 포함한다.
공용 서버 배포 시 VITE_API_BASE_URL을 HTTPS 백엔드 URL로 바꾸고, 백엔드 CORS_ORIGINS에 실제 프론트 도메인을 추가해야 한다.
현재 127.0.0.1 주소로는 다른 팀원이 자신의 컴퓨터에서 내 백엔드를 사용할 수 없다.

## 개발 검증

```powershell
npm.cmd test
npm.cmd run build
```

화면 테스트는 가상 DOM과 모의 API로 로그인·재고 CRUD·식사 승인·수정·외식·취소·401·409·로그아웃을 검사한다.
세션 테스트는 토큰 갱신과 메모리 삭제를 검사한다.
실제 Supabase·브라우저 CORS·배포 환경은 위 수동 확인 순서로 추가 검증한다.
