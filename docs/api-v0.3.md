# 통합본 API v0.3

v0.3.4는 수동 장보기 입고 시 `manual.received_lot_id`를 함께 저장합니다. 이 값이 있는 수동 항목에 새 `lot.create`를 요청하면 409로 거절합니다. 같은 request_id 재시도는 이전과 같이 중복 저장 없이 결과를 확인합니다. 예전 checked 값만으로 입고 여부를 추정하지 않습니다. 기존 `shopping.check` API는 호환 목적으로 유지합니다. SQL 변경은 없습니다.

v0.3.3부터 `lot.create`는 기존 `ingredient_id` 또는 `new_ingredient: {name,unit}` 중 정확히 하나를 받습니다. 새 재료, 재고, 선택한 수동 장보기 항목의 체크를 같은 트랜잭션에 저장합니다. 이름·기준 단위가 일치하면 기존 재료를 재사용합니다. 미리보기는 기록을 남기지 않습니다.

간소화된 미리보기 응답에는 `inventory_changes` 배열이 추가됐습니다. 항목은 `{ingredient_id,name,unit,before,after}`이며, 숨긴 구매분을 제외한 재료별 보유 총량이 바뀐 항목만 담습니다. 새 재료의 미리보기 ID는 임시 값입니다. 저장 응답의 ID를 사용하세요. 장보기의 전후 배열은 기존 형식입니다. 오래된 revision으로 거절한 요청에는 HTTP 409와 `X-Conflict-Reason: revision`을 반환합니다. 재고 부족 등 업무 규칙의 409와 구분할 수 있습니다.

v0.3.2: 공개키 기반 JWT 검증(auto) 및 X-Auth-Verification 시간 측정 헤더를 추가했다. HS256/공개키 확인 실패 시 기존 Auth 서버 확인을 유지한다. 모든 DB 요청에는 사용자 토큰을 그대로 전달한다. API의 요청·응답 본문과 SQL은 바뀌지 않았다.

v0.3.1: `POST /v3/preview?compact=true`는 `{summary,revision,before_shopping,after_shopping}`만 반환한다. 기존 쿼리 없는 `/v3/preview`의 before/after 응답은 그대로 유지한다. HTTP 연결 재사용과 시간 측정은 PERFORMANCE_UPDATE.md 참고.

기존 `/ingredients`, `/inventory`, `/recipes`, `/meals`는 v0.2 호환·참고용이다. v0.3 화면은 이 API로 작업하지 않는다. 첫 접속 때 이전 데이터를 가져온 이후에는 양방향 동기화하지 않는다.

## 조회

GET /v3/workspace, Authorization: Bearer USER_ACCESS_TOKEN

응답: `{revision, workspace, shopping, today}`.
workspace 목록: ingredients, recipes, products, inventory, meals, manual, history.
각 항목의 id는 UUID이고 사용자 범위에서 참조한다. 수량은 g/ml/count 기준으로 정규화된다.
shopping은 오늘 이후 예정 식사만 날짜순으로 계산하며, 식사일까지 소비기한이 유효한 재고를 한 번씩 배분한다.

## 미리보기 및 저장

POST /v3/preview 또는 POST /v3/commands

```json
{
  "request_id": "새 UUID",
  "expected_revision": 0,
  "action": "lot.create",
  "payload": {
    "ingredient_id": "10000000-0000-4000-8000-000000000001",
    "input_quantity": 10,
    "input_unit": "pack",
    "pack_size": 100,
    "content_unit": "g",
    "pack_label": "팩",
    "save_product": true,
    "purchased_on": "2026-11-13"
  }
}
```

미리보기는 저장하지 않고 `{summary,before,after}`를 반환한다. 저장 성공은 최신 조회 응답과 summary,replayed를 반환한다.
수량은 JSON 숫자로 전달하고 bool·문자열 숫자·NaN·무한대는 허용하지 않는다. g↔kg, ml↔L만 환산한다.

| action | payload 주요 필드 |
|---|---|
| ingredient.create | name, unit(g/ml/count) |
| recipe.save | id(수정 시), name, base_servings, minutes, description, instructions, ingredients[{ingredient_id,quantity,unit}] |
| recipe.archive / recipe.restore | id |
| lot.create | ingredient_id 또는 new_ingredient, input_quantity, input_unit, 선택 product_id/pack_size/content_unit/pack_label/save_product/estimated/name/storage, purchased_on, 선택 expires_on/opened_on/manual_id |
| lot.patch | id, quantity(기준 단위 잔량), storage, name, purchased_on, expires_on, opened_on |
| lot.use | id, quantity(기준 단위), reason(use/waste) |
| lot.archive / lot.restore | id |
| meal.save | id(수정 시), date, slot(breakfast/lunch/dinner), recipe_id, servings, repeat_days(1~31) |
| meal.state | id, status(planned/eating_out/cancelled) |
| meal.copy | source_date, days(다음 날부터 1~31일) |
| meal.cook | id, usage[{ingredient_id,quantity,unit}] — 사용하지 않은 재료는 생략 |
| shopping.add | name, quantity, unit(표시용 문자열) |
| shopping.check | id, checked |
| shopping.archive / shopping.restore | id |

동일 request_id·내용 재전송은 재저장하지 않는다. 같은 ID의 다른 내용은 409다. 최신 revision과 다르면 409이며 자동 재적용하지 않는다.
중복 요청 ID는 최근 256개 보관한다. 오래된 요청을 재시도해도 이전 expected_revision은 409다. 새 revision으로 새 의도를 전송할 때는 새 request_id를 만든다.
조리 완료 상태는 새 요청 ID로 다시 요청해도 409다. 부족한 재료가 있으면 어떤 재료도 차감하지 않는다.
상태 변경·재고 변경·구매 등록은 인증 사용자 한 명의 문서 안에서 원자적으로 저장한다. 다른 계정 ID를 요청에 지정하는 인터페이스는 없다.
