"""B v0.3 FastAPI route add-on. Registers routes, never writes state."""
from datetime import date
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import Field

from app.workspace import Model
from .engine import recommend
from .gpt import recommend_with_gpt


class RecommendationRequest(Model):
    user_request: str = Field(min_length=1, max_length=500, pattern=r'\S')
    target_date: date | None = None
    servings: float = Field(default=1, ge=0.1, le=12, strict=True)


def register_recommendation_routes(app, identity):
    router=APIRouter(tags=['C - 메뉴 추천'])

    @router.get('/v3/recommendations')
    def suggestions(response:Response,target_date:date|None=None,
                    servings:float=Query(1,ge=0.1,le=12),
                    max_minutes:int|None=Query(None,ge=1,le=1440),
                    excluded_ids:list[UUID]=Query(default=[]),
                    preferred_ids:list[UUID]=Query(default=[]),
                    limit:int=Query(10,ge=1,le=30),auth=Depends(identity)):
        response.headers['Cache-Control'] = 'private, no-store'
        revision,state=app.state.workspace_repository.load(*auth)
        excluded = [str(i) for i in excluded_ids]
        preferred = [str(i) for i in preferred_ids]
        registered = {item['id'] for item in state['ingredients']}
        if set(excluded + preferred) - registered:
            raise HTTPException(422, '현재 계정의 재료 목록에서 제외·우선 재료를 선택해 주세요.')
        results=recommend(state,target_date=str(target_date) if target_date else None,
                          servings=servings,max_minutes=max_minutes,
                          excluded_ids=excluded,preferred_ids=preferred,limit=limit)
        return {'revision':revision,'recommendations':results,'notice':'규칙 기반 추천입니다.'}

    @router.post('/v3/gpt-recommendations')
    def gpt_suggestions(body:RecommendationRequest,response:Response,auth=Depends(identity)):
        response.headers['Cache-Control'] = 'private, no-store'
        revision,state=app.state.workspace_repository.load(*auth)
        result = recommend_with_gpt(
            state, body.user_request.strip(),
            default_date=body.target_date, default_servings=body.servings,
        )
        return {'revision': revision, **result}
    app.include_router(router)
