# v0.3.5 추가 전달

- B: `/v3/commands`의 `history.undo`와 충돌·중복 방지를 구현했습니다. 동일 요청 재시도는 기존 UUID를 유지합니다. action payload는 `{id: 대상 이력 UUID}`입니다. API·스키마는 이 폴더의 최신 문서를 기준으로 사용하세요.
- A·D: 통합 화면의 `HistoryList.jsx`, `IntegratedApp.jsx`, `integrated-ui.jsx`에 복원 버튼·이유 안내·확인창을 연결했습니다. 응답의 `can_undo/undo_reason`을 표시하되 최종 가능 여부는 저장 시 서버가 다시 확인합니다. 기존 데이터를 삭제하거나 신규 SQL을 실행할 필요는 없습니다.
- A: 회원가입·비밀번호 복구 UI와 인증 콜백은 아직 구현 대상입니다. 실제 프로젝트에서 이메일 인증은 ON입니다. 가입 응답이 세션 없는 상태일 때 메일 확인을 안내하세요.
- B·D: Site URL은 localhost:3000, Redirect URLs는 비어 있으며 custom SMTP는 OFF입니다. A의 실제 콜백과 최종 서비스 주소, 메일 제공자를 확정한 뒤 반영하고 실제 메일 수신을 시험하세요. `signup-readiness.md`에 현재 값과 절차를 정리했습니다.
- D: Windows/Supabase에서 새 사용·폐기·조리 → 변경 이력 → 되돌리기 → 잔량/식사/장보기 → 두 번째 계정 격리를 확인하세요. 백엔드 소스는 B, 통합 변경은 D 브랜치에 공유하고 팀 검증 후 main에 반영합니다.

---

아래는 v0.1 초기 개발 당시의 참고 기록입니다. 현재 통합본은 README와 api-v0.3.md를 기준으로 작업하세요.

# 팀 공유 계약 v0.1

실행 중 /docs와 /openapi.json이 실제 API 계약입니다. openapi.json은 현재 코드에서 추출한 공유용 사본입니다.

| API | 성공 | 내용 |
|---|---|---|
| GET /health | 200 | 프로세스/모드 확인 (DB 검증 아님) |
| GET /ingredients | 200 | 재료 종류 배열 |
| GET /inventory | 200 | 로그인 사용자 재고 배열 |
| POST /inventory | 201 | 신규 구매 묶음 생성 |
| PATCH /inventory/{inventory_id} | 200 | 최종 잔량 또는 보관 장소 수정 |
| DELETE /inventory/{inventory_id} | 204 | 재고 삭제, 응답 본문 없음 |

목록은 limit(기본 100, 최대 100), offset(기본 0) 사용. ID 순으로 정렬.
오류는 HTTP 상태와 detail 필드로 전달. 401 인증 실패, 404 대상 없음, 409 DB 충돌, 422 입력 오류, 503 외부 서비스 실패.
422의 detail은 FastAPI 검증 오류 배열이거나 설명 문자열일 수 있음.
등록 입력: ingredient_id, quantity, unit, storage_location. user_id/생성 시각/재고 ID는 서버가 결정.
수정 입력: quantity와 storage_location 중 하나 이상. null 금지. 수량 0 허용, 음수/문자열/불리언 거부.

A: localhost:8000 API 사용. React 기본 origin localhost:5173. 필요하면 CORS_ORIGINS에 쉼표로 추가.
B: 테이블·검증·서버 유지. C가 필요한 재료는 검토 후 마이그레이션으로 공통 카탈로그에 추가.
C: ingredients의 ingredient_id를 사용. 미등록 ID 추천을 바로 재고에 넣을 수 없음.
D: 서버 실행·인증 토큰 전달·실제 Supabase 검증·통합 테스트. 레포 폴더 위치 및 CI 합의.

첫 PR 검토 기준: 300g 등록 → 180g 수정 → 재시작 후 180g 조회 → 삭제.
식사/추천 관련 공통 변수는 이전 합의 초안으로 유지하되 이번 DB에는 아직 생성하지 않았음.
