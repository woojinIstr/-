"""NextMeal inventory API. Local demo and authenticated Supabase modes."""
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from .catalog import EXTRA_INGREDIENTS, RECIPES, RECIPE_INGREDIENTS
from .meals import register_meal_routes

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, model_validator

DEMO_USER = '00000000-0000-4000-8000-000000000001'
SEEDS = [
    {'ingredient_id': '10000000-0000-4000-8000-000000000001', 'ingredient_name': '닭가슴살', 'unit': 'g'},
    {'ingredient_id': '10000000-0000-4000-8000-000000000002', 'ingredient_name': '시금치', 'unit': 'g'},
    {'ingredient_id': '10000000-0000-4000-8000-000000000003', 'ingredient_name': '달걀', 'unit': 'count'},
]
Unit = Literal['g', 'ml', 'count']
SEEDS = SEEDS + EXTRA_INGREDIENTS
Location = Literal['fridge', 'freezer', 'pantry']

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

class InventoryCreate(StrictModel):
    ingredient_id: UUID
    quantity: float = Field(ge=0, le=1000000000, strict=True)
    unit: Unit
    storage_location: Location

class InventoryPatch(StrictModel):
    quantity: float | None = Field(default=None, ge=0, le=1000000000, strict=True)
    storage_location: Location | None = None

    @model_validator(mode='after')
    def check_patch(self):
        if not self.model_fields_set or any(getattr(self, k) is None for k in self.model_fields_set):
            raise ValueError('최소 한 개의 필드를 지정해야 하며 null은 허용하지 않습니다.')
        return self

class IngredientOut(BaseModel):
    ingredient_id: UUID
    ingredient_name: str
    unit: Unit

class InventoryOut(BaseModel):
    inventory_id: UUID
    user_id: UUID
    ingredient_id: UUID
    quantity: float
    unit: Unit
    storage_location: Location
    created_at: datetime
    updated_at: datetime

class LocalStore:
    def __init__(self, path):
        self.path = path
        with closing(sqlite3.connect(path)) as c:
            c.executescript('''
            CREATE TABLE IF NOT EXISTS ingredients(ingredient_id TEXT PRIMARY KEY, ingredient_name TEXT NOT NULL, unit TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS inventory(inventory_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, ingredient_id TEXT NOT NULL REFERENCES ingredients(ingredient_id), quantity REAL NOT NULL CHECK(quantity>=0), unit TEXT NOT NULL CHECK(unit IN ('g','ml','count')), storage_location TEXT NOT NULL CHECK(storage_location IN ('fridge','freezer','pantry')), created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS inventory_owner ON inventory(user_id);
            ''')
            c.executemany('INSERT OR IGNORE INTO ingredients VALUES (:ingredient_id,:ingredient_name,:unit)', SEEDS)
            c.executescript('''
            CREATE TABLE IF NOT EXISTS recipes(recipe_id TEXT PRIMARY KEY, recipe_name TEXT NOT NULL, base_servings REAL NOT NULL CHECK(base_servings>0), cooking_time_minutes INTEGER NOT NULL CHECK(cooking_time_minutes>0), description TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS recipe_ingredients(recipe_id TEXT NOT NULL REFERENCES recipes(recipe_id), ingredient_id TEXT NOT NULL REFERENCES ingredients(ingredient_id), required_quantity REAL NOT NULL CHECK(required_quantity>0), unit TEXT NOT NULL CHECK(unit IN ('g','ml','count')), PRIMARY KEY(recipe_id,ingredient_id));
            CREATE TABLE IF NOT EXISTS meals(meal_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, meal_date TEXT NOT NULL, meal_slot TEXT NOT NULL CHECK(meal_slot IN ('breakfast','lunch','dinner')), recipe_id TEXT NOT NULL REFERENCES recipes(recipe_id), servings REAL NOT NULL CHECK(servings>0 AND servings<=12), meal_status TEXT NOT NULL CHECK(meal_status IN ('planned','eating_out','cancelled')), version INTEGER NOT NULL CHECK(version>=0), created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS meals_owner_date ON meals(user_id,meal_date);
            ''')
            c.executemany('INSERT OR IGNORE INTO recipes VALUES (:recipe_id,:recipe_name,:base_servings,:cooking_time_minutes,:description)', RECIPES)
            c.executemany('INSERT OR IGNORE INTO recipe_ingredients VALUES (:recipe_id,:ingredient_id,:required_quantity,:unit)', RECIPE_INGREDIENTS)
            c.commit()

    def request(self, method, table, token, params=None, data=None):
        # Only server-defined table/field names reach this method.
        params = params or {}
        conditions, values = [], []
        for key, value in params.items():
            if key in ('limit', 'offset', 'order'): continue
            conditions.append(f'{key} = ?')
            values.append(value.removeprefix('eq.'))
        where = ' WHERE ' + ' AND '.join(conditions) if conditions else ''
        with closing(sqlite3.connect(self.path)) as c:
            c.execute('PRAGMA foreign_keys=ON')
            c.row_factory = sqlite3.Row
            if method == 'GET':
                sql = f'SELECT * FROM {table}{where} ORDER BY ' + {'ingredients':'ingredient_id','inventory':'inventory_id','recipes':'recipe_id','recipe_ingredients':'ingredient_id','meals':'meal_id'}[table]
                sql += ' LIMIT ? OFFSET ?'
                return [dict(r) for r in c.execute(sql, values + [int(params.get('limit',100)), int(params.get('offset',0))])]
            if method == 'POST':
                keys = list(data)
                c.execute(f"INSERT INTO {table} ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})", list(data.values()))
                c.commit()
                return [data]
            if method == 'PATCH':
                rows = c.execute(f"UPDATE {table} SET {','.join(k+'=?' for k in data)}{where} RETURNING *", list(data.values()) + values).fetchall()
            else:
                rows = c.execute(f'DELETE FROM {table}{where} RETURNING *', values).fetchall()
            c.commit()
            return [dict(r) for r in rows]

class SupabaseStore:
    def __init__(self, url, key):
        self.url, self.key = url.rstrip('/'), key

    def call(self, method, path, token, **kwargs):
        try:
            r = httpx.request(method, self.url + path, headers={'apikey': self.key, 'Authorization': 'Bearer '+token, 'Prefer': 'return=representation'}, timeout=15, **kwargs)
        except httpx.RequestError:
            raise HTTPException(503, '데이터 서비스에 연결할 수 없습니다.')
        if r.status_code in (401,403): raise HTTPException(401, '로그인이 필요하거나 접근 권한이 없습니다.')
        if r.status_code == 409: raise HTTPException(409, '데이터가 충돌했습니다.')
        if r.is_error: raise HTTPException(503, '데이터 서비스 요청에 실패했습니다.')
        return r.json()

    def request(self, method, table, token, params=None, data=None):
        return self.call(method, '/rest/v1/'+table, token, params=params, json=data)

    def user(self, token):
        return str(UUID(self.call('GET', '/auth/v1/user', token)['id']))


def create_app(mode=None, db_path=None):
    mode = mode or os.getenv('APP_MODE', 'supabase')
    if mode not in ('local', 'supabase'): raise RuntimeError('APP_MODE must be local or supabase')
    if mode == 'local':
        if os.getenv('APP_ENV', 'development') != 'development': raise RuntimeError('Local demo is development-only')
        store = LocalStore(db_path or os.getenv('SQLITE_PATH', 'nextmeal.local.db'))
    else:
        url, key = os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_PUBLISHABLE_KEY')
        if not url or not key or not url.startswith('https://'): raise RuntimeError('Set SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY, or explicitly use APP_MODE=local')
        store = SupabaseStore(url, key)
    app = FastAPI(title='다음한끼 Backend', version='0.2.0')
    app.add_middleware(CORSMiddleware, allow_origins=os.getenv('CORS_ORIGINS','http://localhost:5173').split(','), allow_methods=['GET','POST','PATCH','DELETE'], allow_headers=['Authorization','Content-Type'])
    bearer = HTTPBearer(auto_error=False)

    def identity(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if mode == 'local': return DEMO_USER, ''
        if credentials is None: raise HTTPException(401, '로그인이 필요합니다.')
        return store.user(credentials.credentials), credentials.credentials

    @app.get('/health')
    def health():
        return {'status': 'ok', 'mode': mode, 'database_checked': False}

    @app.get('/ingredients', response_model=list[IngredientOut])
    def ingredients(limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0), auth=Depends(identity)):
        return store.request('GET','ingredients',auth[1], {'limit':str(limit),'offset':str(offset),'order':'ingredient_id'})

    @app.get('/inventory', response_model=list[InventoryOut])
    def inventory(limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0), auth=Depends(identity)):
        return store.request('GET','inventory',auth[1], {'user_id':'eq.'+auth[0],'limit':str(limit),'offset':str(offset),'order':'inventory_id'})

    @app.post('/inventory', response_model=InventoryOut, status_code=201)
    def add(body: InventoryCreate, auth=Depends(identity)):
        found = store.request('GET','ingredients',auth[1],{'ingredient_id':'eq.'+str(body.ingredient_id)})
        if not found: raise HTTPException(404, '등록된 재료 종류가 없습니다.')
        if found[0]['unit'] != body.unit: raise HTTPException(422, '재료 기준 단위와 일치하지 않습니다.')
        now = datetime.now(timezone.utc).isoformat()
        data = body.model_dump(mode='json') | {'inventory_id':str(uuid4()),'user_id':auth[0],'created_at':now,'updated_at':now}
        return store.request('POST','inventory',auth[1],data=data)[0]

    @app.patch('/inventory/{inventory_id}', response_model=InventoryOut)
    def patch(inventory_id: UUID, body: InventoryPatch, auth=Depends(identity)):
        data = body.model_dump(exclude_unset=True) | {'updated_at':datetime.now(timezone.utc).isoformat()}
        rows = store.request('PATCH','inventory',auth[1],{'inventory_id':'eq.'+str(inventory_id),'user_id':'eq.'+auth[0]},data)
        if not rows: raise HTTPException(404, '재고를 찾을 수 없습니다.')
        return rows[0]

    @app.delete('/inventory/{inventory_id}', status_code=204)
    def delete(inventory_id: UUID, auth=Depends(identity)):
        rows = store.request('DELETE','inventory',auth[1],{'inventory_id':'eq.'+str(inventory_id),'user_id':'eq.'+auth[0]})
        if not rows: raise HTTPException(404, '재고를 찾을 수 없습니다.')
        return Response(status_code=204)
    register_meal_routes(app, store, identity)
    return app
