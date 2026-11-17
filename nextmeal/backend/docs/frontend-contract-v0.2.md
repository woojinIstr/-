# A 프론트와 B 백엔드 연결 규칙

확인한 A 소스: https://github.com/hong46/daeum-hankki-react
기준 커밋: 6b53f027f49f0049a3c9007f8c4a182b5559d8ae
B 기준: https://github.com/woojinIstr/- 의 woojinIstr-patch-1, 992f3aa76ce09900a3725a97811bdb2414baa6d0.
A 저장소는 수정하지 않음. B 기준에 식사 API를 추가함.

| A 필드/값 | B 필드/값 |
|---|---|
| inventory.id | inventory_id |
| inventory.name | ingredient_id로 /ingredients의 ingredient_name 조회 |
| inventory.storage 냉장/냉동/실온 | storage_location fridge/freezer/pantry |
| mL, 개 | ml, count |
| kg, L | g, ml로 정확한 수량 변환 후 전송 |
| 팩 | 지원 안 함. 내용량을 확인하여 g/ml/count로 등록 |
| recipe.id / name / minutes | recipe_id / recipe_name / cooking_time_minutes |
| recipe.ingredients[].quantity | required_quantity (base_servings 기준) |
| meal.id / date / slot / recipeId / status | meal_id / meal_date / meal_slot / recipe_id / meal_status |
| 아침/점심/저녁 | breakfast/lunch/dinner |
| eaten_out / skipped | eating_out / cancelled |
| 없음 | version (조회 후 다음 수정에 expected_version으로 전송) |

r1~r4는 B에서 20000000-0000-4000-8000-000000000001~4에 각각 대응.
initialMeals의 계란밥은 recipeId=null이어서 자동 식사 API로 이전하지 않음. 검수 레시피를 등록한 뒤 추가해야 함.
기존 로컬 i1/m1/r1을 UUID처럼 서버에 전송하지 말 것. 새 서버 목록을 조회하여 반환된 ID를 사용.
localStorage 데모 기록과 서버 기록은 자동 병합하지 않음. 데모/서버 모드를 명시적으로 구분.

## 제공한 연결 모듈

integration/frontend-api.js를 A의 src/로 복사할 수 있다. createMealApi(baseUrl,getAccessToken)으로 인증 토큰을 요청 시 전달.
메뉴·재료 목록을 조회한 다음 inventoryToView / recipeToView / mealToView로 기존 UI 형식으로 변환.
API URL은 설정으로 관리하고 토큰·키를 소스에 넣지 않는다. Supabase publishable key는 사용자 access_token이 아니다.

예정 식사 수정은 PATCH /meals/{id}, 외식은 POST /meals/{id}/eat-out, 취소는 POST /meals/{id}/cancel.
미리보기 진입 시 호출하지 않고 사용자 최종 승인 시 호출해야 한다. API 성공 후 목록을 다시 조회한다.
현재 서버는 미리보기/장보기 계산을 제공하지 않으므로 클라이언트 계산 결과를 서버 확정값으로 표시하지 않는다.
이전 상태 전체를 setMeals로 덮어쓰는 A의 되돌리기 동작은 서버 모드에서 사용하지 않는다.
서버 모드에서 아직 제공하지 않는 조리 완료·장보기·추천 변경안은 연결 완료 전 활성화하지 않는다.

## 담당 경계

B: 이번 API·SQL·검증. A: 로그인 UI·상태 관리·버튼 API 호출. C: 같은 JSON과 UUID로 추천. D: 위 연결 및 실환경 통합 테스트.
A의 자유 입력/임의 단위 선택은 서버 공통 재료 선택 방식과 맞춰야 한다.

공식 참고: https://fastapi.tiangolo.com/tutorial/body-updates/
https://supabase.com/docs/guides/database/postgres/row-level-security
