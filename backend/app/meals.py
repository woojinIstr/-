"""Meal planning only: no inventory mutation or shopping preview in this milestone."""
from datetime import date, datetime, timezone
from typing import Literal
from uuid import UUID, uuid4
from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator

Slot = Literal['breakfast','lunch','dinner']
Status = Literal['planned','eating_out','cancelled']

class Input(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)

class MealCreate(Input):
    meal_date: date
    meal_slot: Slot
    recipe_id: UUID
    servings: float = Field(default=1,gt=0,le=12,strict=True)

class ExpectedVersion(Input):
    expected_version: int = Field(ge=0,strict=True)

class MealPatch(ExpectedVersion):
    meal_date: date | None = None
    meal_slot: Slot | None = None
    recipe_id: UUID | None = None
    servings: float | None = Field(default=None,gt=0,le=12,strict=True)

    @model_validator(mode='after')
    def changes_present(self):
        changes=self.model_fields_set-{'expected_version'}
        if not changes or any(getattr(self,k) is None for k in changes):
            raise ValueError('변경 필드를 한 개 이상 지정하고 null은 사용하지 마세요.')
        return self

class RecipeIngredient(BaseModel):
    ingredient_id: UUID
    required_quantity: float
    unit: Literal['g','ml','count']

class RecipeOut(BaseModel):
    recipe_id: UUID
    recipe_name: str
    base_servings: float
    cooking_time_minutes: int
    description: str
    ingredients: list[RecipeIngredient]

class MealOut(BaseModel):
    meal_id: UUID
    user_id: UUID
    meal_date: date
    meal_slot: Slot
    recipe_id: UUID
    servings: float
    meal_status: Status
    version: int
    created_at: datetime
    updated_at: datetime


def register_meal_routes(app, store, identity):
    def fetch_recipe(recipe_id,token):
        rows=store.request('GET','recipes',token,{'recipe_id':'eq.'+str(recipe_id)})
        if not rows: raise HTTPException(404,'메뉴를 찾을 수 없습니다.')
        return rows[0]

    def fetch_meal(meal_id,auth):
        rows=store.request('GET','meals',auth[1],{'meal_id':'eq.'+str(meal_id),'user_id':'eq.'+auth[0]})
        if not rows: raise HTTPException(404,'식사를 찾을 수 없습니다.')
        return rows[0]

    def update(meal_id,body,auth,target_status=None):
        current=fetch_meal(meal_id,auth)
        if current['version'] != body.expected_version:
            raise HTTPException(409,'식사가 변경되었습니다. 새로 조회한 뒤 다시 확인하세요.')
        if current['meal_status'] != 'planned':
            raise HTTPException(409,'예정 상태의 식사만 변경할 수 있습니다.')
        changes=body.model_dump(mode='json',exclude_unset=True,exclude={'expected_version'})
        if 'recipe_id' in changes: fetch_recipe(changes['recipe_id'],auth[1])
        changes.update(version=body.expected_version+1,updated_at=datetime.now(timezone.utc).isoformat())
        if target_status: changes['meal_status']=target_status
        # Atomic compare-and-set. A competing update makes the result empty.
        rows=store.request('PATCH','meals',auth[1],{
            'meal_id':'eq.'+str(meal_id),'user_id':'eq.'+auth[0],
            'version':'eq.'+str(body.expected_version),'meal_status':'eq.planned'},changes)
        if not rows: raise HTTPException(409,'동시에 식사가 변경되었습니다. 다시 조회하세요.')
        return rows[0]

    @app.get('/recipes',response_model=list[RecipeOut],tags=['recipes'])
    def recipes(limit:int=Query(100,ge=1,le=100),offset:int=Query(0,ge=0),auth=Depends(identity)):
        rows=store.request('GET','recipes',auth[1],{'limit':str(limit),'offset':str(offset),'order':'recipe_id'})
        return [row|{'ingredients':store.request('GET','recipe_ingredients',auth[1],{'recipe_id':'eq.'+row['recipe_id']})} for row in rows]

    @app.get('/recipes/{recipe_id}',response_model=RecipeOut,tags=['recipes'])
    def recipe(recipe_id:UUID,auth=Depends(identity)):
        row=fetch_recipe(recipe_id,auth[1])
        return row|{'ingredients':store.request('GET','recipe_ingredients',auth[1],{'recipe_id':'eq.'+str(recipe_id)})}

    @app.post('/meals',response_model=MealOut,status_code=201,tags=['meals'])
    def create(body:MealCreate,auth=Depends(identity)):
        fetch_recipe(body.recipe_id,auth[1])
        now=datetime.now(timezone.utc).isoformat()
        data=body.model_dump(mode='json')|dict(meal_id=str(uuid4()),user_id=auth[0],meal_status='planned',version=0,created_at=now,updated_at=now)
        return store.request('POST','meals',auth[1],data=data)[0]

    @app.get('/meals',response_model=list[MealOut],tags=['meals'])
    def meals(meal_date:date|None=None,limit:int=Query(100,ge=1,le=100),offset:int=Query(0,ge=0),auth=Depends(identity)):
        params={'user_id':'eq.'+auth[0],'limit':str(limit),'offset':str(offset),'order':'meal_id'}
        if meal_date: params['meal_date']='eq.'+meal_date.isoformat()
        return store.request('GET','meals',auth[1],params)

    @app.get('/meals/{meal_id}',response_model=MealOut,tags=['meals'])
    def meal(meal_id:UUID,auth=Depends(identity)):return fetch_meal(meal_id,auth)

    @app.patch('/meals/{meal_id}',response_model=MealOut,tags=['meals'])
    def patch(meal_id:UUID,body:MealPatch,auth=Depends(identity)):return update(meal_id,body,auth)

    @app.post('/meals/{meal_id}/eat-out',response_model=MealOut,tags=['meals'])
    def eat_out(meal_id:UUID,body:ExpectedVersion,auth=Depends(identity)):return update(meal_id,body,auth,'eating_out')

    @app.post('/meals/{meal_id}/cancel',response_model=MealOut,tags=['meals'])
    def cancel(meal_id:UUID,body:ExpectedVersion,auth=Depends(identity)):return update(meal_id,body,auth,'cancelled')
