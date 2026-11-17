# 다음한끼 — C 역할: 규칙 기반 메뉴 추천 (초안)

이 코드는 A README의 'C: 추천 API가 준비되면 recommend()의 규칙 기반 데모 로직을 교체'라는 역할에 맞춰 작성한 **초기 추천 엔진 + B v0.3 API 확장안**입니다. 외부 AI 서비스 호출은 구현하지 않았고, 실제 AI 학습 결과라고 소개하지 않습니다.

## 구성
- `recommendation/engine.py`: 재고·기존 레시피·인분·시간·제외/우선 재료를 사용해 메뉴 추천
- `recommendation/api.py`: B 백엔드에 `/v3/recommendations` 조회 API 추가
- `tests/test_recommendation.py`: 추천 엔진 기본 테스트 5개

## 쉽게 확인하기
Python 3.11+에서 이 폴더를 열고 `py -m unittest discover -s tests -v` 실행. FastAPI 설치 없이 추천 엔진의 단위 테스트만 실행됩니다.

## B 서버와 통합하기 (팀원 B/D 담당과 함께)
1. 이 폴더의 `recommendation`을 **B 브랜치 서버 최상위**(기존 `app` 폴더와 같은 높이)에 복사합니다.
2. B의 `app/main.py`에서 기존 `register_workspace_routes(app, store, identity, mode)` 호출 바로 다음에 아래 두 줄을 추가합니다.

```python
from recommendation.api import register_recommendation_routes
register_recommendation_routes(app, identity)
```

3. B 서버 실행 후 `GET /v3/recommendations`를 `/docs`에서 호출합니다. 로컬 모드 또는 Supabase 인증이 필요합니다.
4. A 프론트엔드는 해당 API를 호출하여 결과를 화면에 출력합니다. `recipe_id`로 기존 레시피를 찾고, 사용자가 승인하기 전에는 식사/재고 변경을 저장하지 않습니다.

## 제한사항
- 1인분 기준 레시피 재료를 인분에 따라 비례 계산하며, B의 g/ml/count 기준 단위만 비교합니다.
- 지정일 기준 구매일 이전·소비기한 경과·숨김 재고는 사용 가능량에서 제외합니다. 단, 소비기한 날짜만으로 식품의 안전성을 판단할 수 없습니다.
- 이미 예정된 다른 식사에 예약된 재고량은 차감하지 않습니다. 따라서 추천 화면의 '조리 가능'은 해당 메뉴 단독 기준입니다. 확정 장보기와 식사 계획 계산은 반드시 B API를 사용합니다.
- 알레르기, 영양, 위생, 예산, 실제 레시피의 조리법 적합성은 판정하지 않습니다.
- 이 코드는 C 브랜치에 독립적으로 제출할 수 있는 초안이며 A/B 통합 실행 검증은 아직 필요합니다.
