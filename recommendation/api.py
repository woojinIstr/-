
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from .engine import recommend
from .gpt import recommend_with_gpt


def register_recommendation_routes(app, identity):
    router = APIRouter(tags=["C - 메뉴 추천"])

    # 기존 규칙 기반 메뉴 추천
    @router.get("/v3/recommendations")
    def suggestions(
        target_date: date | None = None,
        servings: float = Query(1, gt=0, le=12),
        max_minutes: int | None = Query(None, ge=1, le=1440),
        excluded_ids: list[UUID] = Query(default=[]),
        preferred_ids: list[UUID] = Query(default=[]),
        limit: int = Query(10, ge=1, le=30),
        auth=Depends(identity)
    ):
        repository = app.state.workspace_repository
        revision, state = repository.load(*auth)

        results = recommend(
            state,
            target_date=str(target_date) if target_date else None,
            servings=servings,
            max_minutes=max_minutes,
            excluded_ids=[str(i) for i in excluded_ids],
            preferred_ids=[str(i) for i in preferred_ids],
            limit=limit
        )

        return {
            "revision": revision,
            "recommendations": results,
            "notice": "규칙 기반 추천입니다."
        }

    # GPT를 활용한 메뉴 추천
    @router.get("/v3/gpt-recommendations")
    def gpt_suggestions(
        user_request: str = Query(
            "오늘 저녁 추천해 줘",
            min_length=1,
            max_length=500
        ),
        auth=Depends(identity)
    ):
        repository = app.state.workspace_repository
        revision, state = repository.load(*auth)

        result = recommend_with_gpt(
            state,
            user_request=user_request
        )

        return {
            "revision": revision,
            **result
        }

    app.include_router(router)
