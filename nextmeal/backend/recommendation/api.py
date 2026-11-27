"""Read-only recommendation endpoints."""
from concurrent.futures import Future
from datetime import date
from threading import Lock
from time import monotonic
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import Field

from app.starter_recipes import expand_for_recommendation
from app.ingredient_names import canonical_name, name_key
from app.workspace import MealSlot, Model, today
from .diagnostics import configuration_status
from .engine import recommend
from .gpt import recommend_with_gpt

RecipeSource = Literal['all', 'personal', 'starter']


class RecommendationRequest(Model):
    user_request: str = Field(min_length=1, max_length=500, pattern=r'\S')
    target_date: date | None = None
    target_slot: MealSlot = 'dinner'
    target_meal_id: UUID | None = None
    servings: float = Field(default=1, ge=0.1, le=12, strict=True)
    max_minutes: int | None = Field(default=None, ge=1, le=1440)
    exclude: str = Field(default='', max_length=300)
    prefer: str = Field(default='', max_length=300)
    ready_only: bool = False
    recipe_source: RecipeSource = 'all'


def selected_meal(state, meal_id):
    if meal_id is None:
        return None
    meal = next((meal for meal in state['meals'] if meal['id'] == str(meal_id)), None)
    if meal is None or meal['status'] != 'planned':
        raise HTTPException(404, '변경할 예정 식사를 찾을 수 없어요. 식사 계획을 새로고침해 주세요.')
    return meal


def ids_matching(ingredients, text):
    fragments = [canonical_name(word) for word in text.split(',') if word.strip()]
    return [
        item['id'] for item in ingredients
        if any(fragment in name_key(item['name'])
               or fragment == canonical_name(item.get('canonical_name',item['name'])) for fragment in fragments)
    ]


def register_recommendation_routes(app, identity):
    router = APIRouter(tags=['C - 메뉴 추천'])
    cache_lock = Lock()
    in_flight = {}
    recent = {}

    @router.get('/v3/recommendation-status')
    def status(response: Response, auth=Depends(identity)):
        response.headers['Cache-Control'] = 'private, no-store'
        return {**configuration_status(), 'version': app.version}

    @router.get('/v3/recommendations')
    def suggestions(response: Response, target_date: date | None = None, target_slot: MealSlot = 'dinner',
                    target_meal_id: UUID | None = None, servings: float = Query(1, ge=0.1, le=12),
                    max_minutes: int | None = Query(None, ge=1, le=1440),
                    excluded_ids: list[UUID] = Query(default=[]), preferred_ids: list[UUID] = Query(default=[]),
                    exclude: str = Query('', max_length=300), prefer: str = Query('', max_length=300),
                    ready_only: bool = False, recipe_source: RecipeSource = 'all',
                    limit: int = Query(10, ge=1, le=30), auth=Depends(identity)):
        response.headers['Cache-Control'] = 'private, no-store'
        revision, document = app.state.workspace_repository.load(*auth)
        state = expand_for_recommendation(document)
        meal = selected_meal(state, target_meal_id)
        excluded = [str(item) for item in excluded_ids]
        preferred = [str(item) for item in preferred_ids]
        registered = {item['id'] for item in state['ingredients']}
        if set(excluded + preferred) - registered:
            raise HTTPException(422, '제외하거나 우선 사용할 재료를 목록에서 선택해 주세요.')
        criteria = dict(
            target_date=meal['date'] if meal else (target_date.isoformat() if target_date else None),
            target_slot=meal['slot'] if meal else target_slot, target_meal_id=meal['id'] if meal else None,
            servings=meal['servings'] if meal else servings, max_minutes=max_minutes,
            excluded_ids=excluded + ids_matching(state['ingredients'], exclude),
            preferred_ids=preferred + ids_matching(state['ingredients'], prefer),
            recipe_source=recipe_source,
        )
        results = recommend(state, **criteria, ready_only=ready_only, limit=limit)
        near = recommend(state, **criteria, limit=3) if ready_only and not results else []
        unit_checks = list(dict.fromkeys(part['name'] for item in near for part in item['missing']
                                        if part.get('needs_unit')))
        return {'revision': revision, 'recommendations': results, 'unit_checks': unit_checks,
                'notice': '규칙 기반 추천입니다.'}

    @router.post('/v3/gpt-recommendations')
    def gpt_suggestions(body: RecommendationRequest, response: Response, auth=Depends(identity)):
        response.headers['Cache-Control'] = 'private, no-store'
        revision, document = app.state.workspace_repository.load(*auth)
        key = (auth[0], revision, today(), body.model_dump_json())
        with cache_lock:
            now = monotonic()
            for expired in [item for item, (until, _) in recent.items() if until <= now]:
                del recent[expired]
            if key in recent:
                return recent[key][1]
            existing = in_flight.get(key)
            if existing is None:
                in_flight[key] = future = Future()
        if existing is not None:
            return existing.result()

        try:
            result = rank(document, revision, body)
            seconds = 20 if result.get('reason_code') == 'rate_limited' else 45 if result['source'] == 'gpt' else 0
            if seconds:
                with cache_lock:
                    if len(recent) >= 128:
                        recent.pop(next(iter(recent)))
                    recent[key] = (monotonic() + seconds, result)
            future.set_result(result)
            return result
        except Exception as error:
            future.set_exception(error)
            raise
        finally:
            with cache_lock:
                in_flight.pop(key, None)

    def rank(document, revision, body):
        state = expand_for_recommendation(document)
        meal = selected_meal(state, body.target_meal_id)
        result = recommend_with_gpt(
            state, body.user_request.strip(),
            default_date=date.fromisoformat(meal['date']) if meal else body.target_date,
            default_servings=meal['servings'] if meal else body.servings,
            target_slot=meal['slot'] if meal else body.target_slot, target_meal_id=meal['id'] if meal else None,
            ready_only=body.ready_only, recipe_source=body.recipe_source,
            default_max_minutes=body.max_minutes, excluded_ids=ids_matching(state['ingredients'], body.exclude),
            preferred_ids=ids_matching(state['ingredients'], body.prefer),
        )
        conditions = result['conditions'] or {}
        label_ids = set(conditions.get('excluded_ids', []) + conditions.get('required_ids', []))
        return {'revision': revision, **result, 'condition_labels': {
            item['id']: item['name'] for item in state['ingredients'] if item['id'] in label_ids
        }}

    app.include_router(router)
