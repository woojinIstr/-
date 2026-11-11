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
