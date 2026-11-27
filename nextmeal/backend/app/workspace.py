"""User workspace domain: all changes operate on a copy and commit atomically.

v0.2 data is imported once. Recipe snapshots keep past plans stable after edits.
Quantities use Decimal arithmetic before storage as finite JSON numbers.
"""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import json
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .starter_recipes import starter_recipe_for_plan
from .ingredient_names import canonical_name, name_key, stock_keys

def uid(): return str(uuid4())
def now(): return datetime.now(timezone.utc).isoformat()
def today(): return (datetime.now(timezone(timedelta(hours=9)))).date().isoformat()
def fail(message, code=422): raise HTTPException(code, message)
def day_after(day, offset):
    try:return (date.fromisoformat(day)+timedelta(days=offset)).isoformat()
    except (OverflowError,ValueError):fail('등록 가능한 날짜 범위를 벗어났습니다.')
def dec(n): return Decimal(str(n))
def number(n):
    n = dec(n).quantize(Decimal('0.000001'))
    if not n.is_finite() or abs(n) > 1000000000: fail('환산한 수량은 10억 이하여야 합니다.')
    return float(n)
def find(state, collection, key):
    item = next((x for x in state[collection] if x['id'] == str(key)), None)
    if not item: fail('항목을 찾을 수 없습니다.', 404)
    return item
def active(item):
    if item.get('archived'): fail('보관 처리된 항목입니다. 먼저 복원하세요.', 409)
    return item
def unit_label(unit): return {'g':'g','ml':'mL','count':'개'}[unit]
def converted(quantity, unit, target):
    base, scale = {'g':('g',1),'kg':('g',1000),'ml':('ml',1),'L':('ml',1000),'count':('count',1)}[unit]
    if base != target: fail('무게·부피·개수를 서로 환산할 수 없습니다. 재료 기준 단위를 확인하세요.')
    result=number(dec(quantity)*scale)
    if dec(quantity)>0 and result<=0: fail('환산한 수량이 너무 작습니다. 소수점 여섯 자리 이상은 사용할 수 없습니다.')
    return result

class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
Quantity = Annotated[float, Field(strict=True, ge=0, le=1000000000)]
Positive = Annotated[float, Field(strict=True, gt=0, le=1000000000)]
Name = Annotated[str, Field(min_length=1,max_length=100)]
Unit = Literal['g','ml','count']
InputUnit = Literal['g','kg','ml','L','count']
MealSlot = Literal['breakfast','lunch','dinner']
MEAL_SLOTS = {'breakfast': 0, 'lunch': 1, 'dinner': 2}

class Ingredient(Model):
    name: Name
    unit: Unit
class Key(Model): id: UUID
class Part(Model):
    ingredient_id: UUID
    quantity: Positive
    unit: InputUnit
class Recipe(Model):
    id: UUID | None = None
    name: Name
    base_servings: float = Field(strict=True, ge=0.1, le=100)
    minutes: int = Field(strict=True,ge=1,le=1440)
    description: str = Field(default='',max_length=1000)
    instructions: str = Field(default='',max_length=10000)
    ingredients: list[Part] = Field(min_length=1,max_length=100)
class Lot(Model):
    ingredient_id: UUID | None = None
    new_ingredient: Ingredient | None = None
    product_id: UUID | None = None
    name: str = Field(default='',max_length=100)
    input_quantity: Positive
    input_unit: Literal['g','kg','ml','L','count','pack']
    pack_size: Positive | None = None
    content_unit: InputUnit = 'g'
    pack_label: str = Field(default='팩',min_length=1,max_length=20)
    save_product: bool = False
    estimated: bool = False
    storage: Literal['fridge','freezer','pantry'] = 'fridge'
    purchased_on: date
    expires_on: date | None = None
    opened_on: date | None = None
    manual_id: UUID | None = None
    @model_validator(mode='after')
    def validate_purchase(self):
        if (self.ingredient_id is None) == (self.new_ingredient is None):
            fail('기존 재료를 선택하거나 새 재료의 이름과 기준 단위를 입력하세요.')
        if self.new_ingredient and self.product_id:
            fail('저장한 제품은 해당 재료를 선택한 뒤 사용할 수 있습니다.')
        if self.purchased_on.isoformat()>today(): fail('미래의 구매는 재고로 등록하지 말고 장보기 목록에 추가하세요.')
        if self.expires_on and self.expires_on<self.purchased_on: fail('소비기한은 구매일보다 빠를 수 없습니다.')
        if self.opened_on and (self.opened_on<self.purchased_on or self.opened_on.isoformat()>today()): fail('개봉일은 구매일 이후, 오늘 이하여야 합니다.')
        return self
class QuickStockRow(Model):
    name: Name
    quantity: Positive
    unit: Literal['g','kg','ml','L','count','pack']
    pack_size: Positive | None = None
    pack_label: str = Field(default='팩', min_length=1, max_length=20)
    product_id: UUID | None = None


class QuickStock(Model):
    items: list[QuickStockRow] = Field(min_length=1,max_length=12)

class LotPatch(Model):
    id: UUID
    quantity: Quantity
    storage: Literal['fridge','freezer','pantry']
    name: str = Field(default='',max_length=100)
    purchased_on: date
    expires_on: date | None = None
    opened_on: date | None = None
class Use(Model):
    id: UUID
    quantity: Positive
    reason: Literal['use','waste']
class Meal(Model):
    id: UUID | None = None
    after_eating_out: UUID | None = None
    date: date
    slot: MealSlot
    recipe_id: UUID
    servings: float = Field(strict=True,ge=0.1,le=12)
    repeat_days: int = Field(default=1,strict=True,ge=1,le=31)
class MealState(Key): status: Literal['eating_out','cancelled','planned']
class CopyDay(Model):
    source_date: date
    days: int = Field(strict=True,ge=1,le=31)
class Cook(Key):
    usage: list[Part] = Field(min_length=1,max_length=100)
class Manual(Model):
    name: Name
    quantity: Positive
    unit: str = Field(min_length=1,max_length=20)
class CheckManual(Key): checked: bool

MODELS = {'ingredient.create':Ingredient,'recipe.save':Recipe,'recipe.archive':Key,'recipe.restore':Key,'recipe.delete':Key,
          'lot.create':Lot,'lot.quick_add':QuickStock,'lot.patch':LotPatch,'lot.archive':Key,'lot.restore':Key,'lot.use':Use,
          'meal.save':Meal,'meal.state':MealState,'meal.skip_followup':Key,'meal.copy':CopyDay,'meal.cook':Cook,
          'shopping.add':Manual,'shopping.check':CheckManual,'shopping.archive':Key,'shopping.restore':Key,
          'history.undo':Key}

def bootstrap(ingredients, recipes, parts, inventory, meals):
    state = {'schema':3,'ingredients':[],'recipes':[],'products':[],'inventory':[], 'meals':[], 'manual':[], 'history':[], 'requests':[], 'meal_followups':{}}
    state['ingredients'] = [dict(id=i['ingredient_id'],name=i['ingredient_name'],unit=i['unit']) for i in ingredients]
    for r in recipes:
        state['recipes'].append(dict(id=r['recipe_id'],name=r['recipe_name'],base_servings=r['base_servings'],minutes=r['cooking_time_minutes'],description=r['description'],instructions='',archived=False,
            ingredients=[dict(ingredient_id=p['ingredient_id'],quantity=p['required_quantity'],unit=p['unit']) for p in parts if p['recipe_id']==r['recipe_id']]))
    for i in inventory:
        state['inventory'].append(dict(id=i['inventory_id'],ingredient_id=i['ingredient_id'],quantity=i['quantity'],unit=i['unit'],name='기존 재고',storage=i['storage_location'],purchased_on=None,expires_on=None,opened_on=None,pack_size=None,pack_label='',estimated=False,archived=False,created_at=i['created_at']))
    for m in meals:
        recipe = deepcopy(find(state,'recipes',m['recipe_id']))
        state['meals'].append(dict(id=m['meal_id'],date=m['meal_date'],slot=m['meal_slot'],recipe_id=m['recipe_id'],recipe=recipe,servings=m['servings'],status=m['meal_status'],created_at=m['created_at']))
    return state

def requirements(meal):
    r=meal['recipe']
    return [dict(ingredient_id=i['ingredient_id'],quantity=number(dec(i['quantity'])*dec(meal['servings'])/dec(r['base_servings'])),unit=i['unit']) for i in r['ingredients']]

def usable(lot, on):
    return not lot.get('archived') and lot['quantity']>0 and (not lot.get('expires_on') or lot['expires_on']>=on) and (not lot.get('purchased_on') or lot['purchased_on']<=on)
def ordered_lots(state, ingredient_id, on):
    selected = state['stock_keys'][ingredient_id]
    return sorted((lot for lot in state['inventory']
                   if state['stock_keys'].get(lot['ingredient_id']) == selected and lot['unit'] == selected[1] and usable(lot, on)),
                  key=lambda lot: (lot.get('expires_on') or '9999-12-31', lot.get('purchased_on') or '0000-00-01',
                                   {'fridge':0,'pantry':1,'freezer':2}[lot['storage']], lot['id']))


def meal_order(meal):
    return meal['date'], MEAL_SLOTS[meal['slot']]


def planned_meals(state):
    current_day = today()
    # Stable sorting gives earlier entries within the same slot first use.
    return sorted((meal for meal in state.get('meals', [])
                   if meal['status'] == 'planned' and meal['date'] >= current_day), key=meal_order)

def next_home_slot(state, source):
    target = next((meal for meal in planned_meals(state) if meal_order(meal) > meal_order(source)), None)
    if target:
        return dict(target_id=target['id'], date=target['date'], slot=target['slot'])
    slot_index = MEAL_SLOTS[source['slot']] + 1
    if slot_index == len(MEAL_SLOTS):
        if source['date'] == date.max.isoformat():
            return None
        return dict(target_id=None, date=day_after(source['date'], 1), slot='breakfast')
    return dict(target_id=None, date=source['date'], slot=tuple(MEAL_SLOTS)[slot_index])


def active_followups(state):
    current_day = today()
    meals = {meal['id']: meal for meal in state['meals']}
    pending = state.get('meal_followups')
    if pending is None:
        # Older releases did not link a subsequent save back to the external meal.
        # Recover recent, identifiable transitions only until a later plan edit makes intent ambiguous.
        yesterday = day_after(current_day, -1)
        recent = {meal.get('change_id'): meal for meal in meals.values()
                  if meal['status'] == 'eating_out' and meal['date'] >= yesterday}
        pending = {}
        for event in state.get('history', []):
            if event['action'] in ('meal.save', 'meal.copy', 'meal.cook'):
                break
            source = recent.get(event['id'])
            if source and event['action'] == 'meal.state':
                pending[source['id']] = next_home_slot(state, source)
    result = {}
    for source_id, slot in pending.items():
        source = meals.get(source_id)
        if not source or source['status'] != 'eating_out' or not slot:
            continue
        if not slot['target_id']:
            # Keep an unplanned next meal available through the following calendar day.
            if source['date'] < day_after(current_day, -1):
                continue
            slot = next_home_slot(state, source)
            if slot and slot['date'] < current_day:
                slot = dict(target_id=None, date=current_day, slot='breakfast')
        if not slot or slot['date'] < current_day:
            continue
        if slot['target_id']:
            target = meals.get(slot['target_id'])
            if not target or target['status'] != 'planned' or meal_order(target) != meal_order(slot):
                continue
        result[source_id] = slot
    return result


def reserve_part(working, part, day):
    remaining = dec(part['quantity'])
    for lot in ordered_lots(working, part['ingredient_id'], day):
        amount = min(dec(lot['quantity']), remaining)
        lot['quantity'] = number(dec(lot['quantity']) - amount)
        remaining -= amount
        if remaining == 0:
            break
    return remaining


def stock_for_meal(state, day, slot, meal_id=None):
    working = {'inventory': deepcopy(state.get('inventory', [])), 'stock_keys': stock_keys(state['ingredients'])}
    target = (day, MEAL_SLOTS[slot])
    for meal in planned_meals(state):
        order = meal_order(meal)
        if order > target or (order == target and meal['id'] == meal_id):
            break
        if meal['id'] == meal_id:
            continue
        for part in requirements(meal):
            reserve_part(working, part, meal['date'])
    return working['inventory']


def shopping(state):
    keys = stock_keys(state['ingredients'])
    working = {'inventory': deepcopy(state['inventory']), 'stock_keys': keys}
    totals = {}
    ingredients = {}
    for item in state['ingredients']:
        ingredients.setdefault(keys[item['id']], item)
    for meal in planned_meals(state):
        for part in requirements(meal):
            ingredient = ingredients[keys[part['ingredient_id']]]
            row = totals.setdefault(ingredient['id'], dict(ingredient_id=ingredient['id'], name=ingredient['name'],
                                                           unit=ingredient['unit'], required=0, shortage=0))
            row['required'] = number(dec(row['required']) + dec(part['quantity']))
            row['shortage'] = number(dec(row['shortage']) + reserve_part(working, part, meal['date']))
    return [row for row in totals.values() if row['shortage'] > 0]

def present(state, revision):
    return {'revision':revision,'workspace':state,'shopping':shopping(state),'today':today()}

def meal_summary(state, meal): return f"{meal['date']} {meal['recipe']['name']} {meal['servings']:g}인분"

def register_ingredient(state, fields, *, reuse=False):
    name = fields['name'].strip()
    if not name:
        fail('재료 이름을 입력하세요.')
    key = name.replace(' ', '').casefold()
    for item in state['ingredients']:
        if item['name'].replace(' ', '').casefold() == key:
            if reuse and item['unit'] == fields['unit']:
                return item
            fail('같은 이름의 재료가 있습니다. 기존 재료를 사용하거나 다른 이름을 입력하세요.', 409)
    item = dict(id=uid(), name=name, unit=fields['unit'])
    state['ingredients'].append(item)
    return item

def inventory_changes(before, after):
    def totals(state):
        result = {}
        for lot in state['inventory']:
            if not lot['archived']:
                key = lot['ingredient_id']
                result[key] = result.get(key, Decimal(0)) + dec(lot['quantity'])
        return result
    old, new = totals(before), totals(after)
    changes = []
    for ingredient in after['ingredients']:
        key = ingredient['id']
        previous, current = old.get(key, 0), new.get(key, 0)
        if previous != current:
            changes.append(dict(ingredient_id=key, name=ingredient['name'], unit=ingredient['unit'],
                                before=float(previous), after=float(current)))
    return changes

# Causal markers catch quantity changes, metadata edits, hide/restore and ABA edits.
# Undo restores the preceding marker so a sequence can be undone newest first.
def mark_changes(before, after, event_id):
    for collection in ('inventory', 'meals'):
        old = {item['id']: item for item in before[collection]}
        for item in after[collection]:
            if old.get(item['id']) != item:
                item['change_id'] = event_id

def reversal_data(before, after, action, body):
    if action not in ('lot.use', 'meal.cook'):
        return None
    old = {item['id']: item for item in before['inventory']}
    lots = []
    for item in after['inventory']:
        previous = old.get(item['id'])
        if previous and dec(previous['quantity']) > dec(item['quantity']):
            lots.append(dict(id=item['id'], ingredient_id=item['ingredient_id'], unit=item['unit'],
                             before_quantity=previous['quantity'], after_quantity=item['quantity'],
                             previous_change_id=previous.get('change_id')))
    if not lots:
        return None
    undo = dict(version=1, lots=lots)
    if action == 'meal.cook':
        meal = find(before, 'meals', body['id'])
        undo['meal'] = dict(id=meal['id'], previous_change_id=meal.get('change_id'),
                            before={k: deepcopy(meal[k]) for k in ('status', 'used', 'cooked_at') if k in meal})
    return undo

def undo_problem(state, event, indexes=None):
    if event.get('undone_at'):
        return '이미 되돌린 기록입니다.'
    undo = event.get('undo')
    if event['action'] not in ('lot.use','meal.cook') or not undo or undo.get('version') != 1 or not undo.get('lots'):
        return '이전 버전의 기록이거나 되돌리기를 지원하지 않는 작업입니다.'
    for row in undo['lots']:
        lot = (indexes['inventory'].get(row['id']) if indexes else
               next((i for i in state['inventory'] if i['id'] == row['id']), None))
        if not lot or lot.get('change_id') != event['id'] or any(
            lot.get(key) != row[key] for key in ('ingredient_id', 'unit')
        ) or dec(lot['quantity']) != dec(row['after_quantity']):
            return '이후 같은 재고가 변경되었습니다. 더 최근 기록을 먼저 되돌리거나 재고를 확인해 정정하세요.'
    if undo.get('meal'):
        meal = (indexes['meals'].get(undo['meal']['id']) if indexes else
                next((m for m in state['meals'] if m['id'] == undo['meal']['id']), None))
        if not meal or meal.get('change_id') != event['id'] or meal['status'] != 'cooked':
            return '이후 해당 식사가 변경되어 이 기록을 되돌릴 수 없습니다.'
    return None

def history_status(state):
    """Derived presentation only; eligibility is always rechecked on commit."""
    result = []
    indexes={key:{item['id']:item for item in state[key]} for key in ('inventory','meals')}
    for event in state['history']:
        row = deepcopy(event)
        if event['action'] in ('lot.use', 'meal.cook'):
            problem = undo_problem(state, event, indexes)
            row['can_undo'] = problem is None
            row['undo_reason'] = problem or ''
        result.append(row)
    return result

def meal_changes(before, after):
    old={m['id']:m for m in before['meals']}
    return [dict(id=m['id'], date=m['date'], name=m['recipe']['name'],
                 before=old[m['id']]['status'], after=m['status'])
            for m in after['meals'] if m['id'] in old and old[m['id']]['status']!=m['status']]

def undo_event(state, event_id, reversal_id):
    event = find(state, 'history', event_id)
    problem = undo_problem(state, event)
    if problem:
        fail(problem, 409)
    undo = event['undo']
    # Validate every target above before changing any target. The enclosing command
    # commits all restored lots, meal state and audit entries with one CAS write.
    for row in undo['lots']:
        lot = find(state, 'inventory', row['id'])
        amount = dec(row['before_quantity']) - dec(row['after_quantity'])
        lot['quantity'] = number(dec(lot['quantity']) + amount)
        if row['previous_change_id'] is None:
            lot.pop('change_id', None)
        else:
            lot['change_id'] = row['previous_change_id']
    if undo.get('meal'):
        snapshot = undo['meal']
        meal = find(state, 'meals', snapshot['id'])
        for key in ('status', 'used', 'cooked_at'):
            meal.pop(key, None)
        meal.update(deepcopy(snapshot['before']))
        if snapshot['previous_change_id'] is None:
            meal.pop('change_id', None)
        else:
            meal['change_id'] = snapshot['previous_change_id']
    event.update(undone_at=now(), undone_by=reversal_id)
    return f"기록 되돌림 · {event['summary']}"

def create_lot(state, body):
    manual = active(find(state,'manual',body['manual_id'])) if body['manual_id'] else None
    if manual and manual.get('received_lot_id'):
        fail('이미 재고에 반영한 장보기 항목입니다. 새 구매는 장보기 항목을 새로 추가하세요.',409)
    ing = (register_ingredient(state, body['new_ingredient'], reuse=True)
           if body['new_ingredient'] else find(state, 'ingredients', body['ingredient_id']))
    pack_size=None;pack_label='';estimated=body['estimated']
    if body['product_id']:
        product=find(state,'products',body['product_id'])
        if product['ingredient_id']!=ing['id'] or body['input_unit']!='pack': fail('선택한 제품과 재료·구입 단위가 일치하지 않습니다.')
        pack_size=product['pack_size'];pack_label=product['pack_label'];estimated=product['estimated']
        if not body['name']: body['name']=product['name']
    elif body['input_unit']=='pack':
        if body['pack_size'] is None: fail('1개 또는 1팩당 내용량을 입력하세요.')
        pack_size=converted(body['pack_size'],body['content_unit'],ing['unit']);pack_label=body['pack_label']
    quantity=number(dec(body['input_quantity'])*dec(pack_size)) if pack_size else converted(body['input_quantity'],body['input_unit'],ing['unit'])
    if quantity<=0: fail('환산한 수량이 너무 작습니다.')
    if body['save_product'] and pack_size and not body['product_id']:
        product=dict(id=uid(),ingredient_id=ing['id'],name=body['name'].strip() or ing['name'],pack_size=pack_size,pack_label=pack_label,estimated=estimated)
        same=next((p for p in state['products'] if all(p[k]==product[k] for k in ['ingredient_id','name','pack_size','pack_label','estimated'])),None)
        if not same: state['products'].append(product)
    lot=dict(id=uid(),ingredient_id=ing['id'],name=body['name'].strip(),quantity=quantity,unit=ing['unit'],storage=body['storage'],purchased_on=body['purchased_on'],expires_on=body['expires_on'],opened_on=body['opened_on'],pack_size=pack_size,pack_label=pack_label,estimated=estimated,archived=False,created_at=now())
    state['inventory'].append(lot)
    if manual:
        manual.update(checked=True,received_lot_id=lot['id'])
    return ing, quantity


def create_quick_lot(state, item):
    packed = item['unit'] == 'pack'
    base = {'g': 'g', 'kg': 'g', 'ml': 'ml', 'L': 'ml', 'count': 'count', 'pack': 'g'}[item['unit']]
    key = (canonical_name(item['name']), base)
    keys = stock_keys(state['ingredients'])
    if not packed and (item['product_id'] or item['pack_size']):
        fail('포장 재료에서만 포장 내용량과 제품을 선택할 수 있어요.')
    if item['product_id']:
        product = find(state, 'products', item['product_id'])
        if keys.get(product['ingredient_id']) != key or product.get('estimated') or item['pack_size']:
            fail('입력한 재료에 맞는 확인된 포장 제품을 선택하세요.')
        ingredient = find(state, 'ingredients', product['ingredient_id'])
    else:
        ingredient = next((row for row in state['ingredients'] if keys[row['id']] == key), None)
        if ingredient is None:
            name = item['name'].strip()
            names = {name_key(row['name']) for row in state['ingredients']}
            if name_key(name) in names:
                name = f"{name[:85]} ({unit_label(base)})"
                ordinal = 2
                while name_key(name) in names:
                    name = f"{item['name'].strip()[:85]} ({unit_label(base)} {ordinal})"
                    ordinal += 1
            ingredient = register_ingredient(state, dict(name=name, unit=base))
            if canonical_name(name) != key[0]:
                ingredient['canonical_name'] = key[0]
    lot = Lot(ingredient_id=ingredient['id'], product_id=item['product_id'], input_quantity=item['quantity'],
              input_unit=item['unit'], pack_size=item['pack_size'], pack_label=item['pack_label'],
              save_product=packed, content_unit='g', purchased_on=date.fromisoformat(today()))
    create_lot(state, lot.model_dump(mode='json'))
    return ingredient


def apply(original, action, raw):
    state=deepcopy(original)
    if action not in MODELS: fail('지원하지 않는 작업입니다.')
    body=MODELS[action].model_validate(raw).model_dump(mode='json')
    event_id=uid()
    pending = state['meal_followups'] = active_followups(original)
    summary=action
    if action=='ingredient.create':
        ingredient = register_ingredient(state, body)
        summary = f"재료 추가 · {ingredient['name']}"
    elif action=='recipe.save':
        if body['id']: active(find(state,'recipes',body['id']))
        body['name']=body['name'].strip()
        if not body['name']: fail('메뉴 이름을 입력하세요.')
        seen=set()
        for part in body['ingredients']:
            ing=find(state,'ingredients',part['ingredient_id'])
            if ing['id'] in seen: fail('같은 재료는 한 줄로 합쳐 입력하세요.')
            seen.add(ing['id']);part['quantity']=converted(part['quantity'],part['unit'],ing['unit']);part['unit']=ing['unit']
        key=body['id'] or uid();body['id']=key;body['archived']=False
        existing=next((i for i in state['recipes'] if i['id']==key),None)
        if existing: existing.update(body)
        else: state['recipes'].append(body)
        summary=f"메뉴 저장 · {body['name']} (기존 식사 계획은 유지)"
    elif action=='recipe.delete':
        recipe=find(state,'recipes',body['id'])
        state['recipes'].remove(recipe)
        summary=f"메뉴 삭제 · {recipe['name']}"
    elif action in ('recipe.archive','recipe.restore'):
        r=find(state,'recipes',body['id']);r['archived']=action.endswith('archive');summary=f"메뉴 {'보관' if r['archived'] else '복원'} · {r['name']}"
    elif action=='lot.create':
        ingredient, quantity = create_lot(state, body)
        summary = f"구매 등록 · {ingredient['name']} {quantity:g}{unit_label(ingredient['unit'])}"
    elif action=='lot.quick_add':
        names = [create_quick_lot(state, item)['name'] for item in body['items']]
        summary = '재고 추가 · ' + ', '.join(names)
    elif action=='lot.patch':
        lot=active(find(state,'inventory',body['id']))
        if body['purchased_on']>today() or (body['expires_on'] and body['expires_on']<body['purchased_on']) or (body['opened_on'] and not body['purchased_on']<=body['opened_on']<=today()): fail('구매일·소비기한·개봉일을 확인하세요.')
        previous=lot['quantity'];lot.update({k:v for k,v in body.items() if k!='id'});summary=f"재고 정정 · {find(state,'ingredients',lot['ingredient_id'])['name']} {previous:g} → {lot['quantity']:g}{unit_label(lot['unit'])}"
    elif action=='lot.use':
        lot=active(find(state,'inventory',body['id']))
        if number(body['quantity'])<=0: fail('처리할 수량은 0.000001 이상이어야 합니다.')
        if dec(body['quantity'])>dec(lot['quantity']): fail('남은 재고보다 많이 사용·폐기할 수 없습니다.',409)
        lot['quantity']=number(dec(lot['quantity'])-dec(body['quantity']));summary=f"{'사용' if body['reason']=='use' else '폐기'} · {find(state,'ingredients',lot['ingredient_id'])['name']} {body['quantity']:g}{unit_label(lot['unit'])}"
    elif action in ('lot.archive','lot.restore'):
        lot=find(state,'inventory',body['id']);lot['archived']=action.endswith('archive');summary=f"재고 {'숨김' if lot['archived'] else '복원'} · {find(state,'ingredients',lot['ingredient_id'])['name']}"
    elif action=='meal.save':
        editing=find(state,'meals',body['id']) if body['id'] else None
        previous_recipe_id = editing['recipe_id'] if editing else None
        source_id = body['after_eating_out']
        if source_id:
            slot = pending.get(source_id)
            if not slot or slot['target_id'] != body['id']:
                fail('다음 집밥 계획이 변경됐어요. 최신 식사 계획을 확인하세요.', 409)
            source = find(state, 'meals', source_id)
            if (body['date'] < today() or meal_order(body) <= meal_order(source)
                    or (editing and meal_order(body) != meal_order(slot)) or body['repeat_days'] != 1):
                fail('외식 이후의 예정 식사를 선택하세요.', 422)
            del pending[source_id]
        if editing and editing['recipe_id']==body['recipe_id']:
            recipe=editing['recipe']
        else:
            recipe_id = body['recipe_id']
            recipe = starter_recipe_for_plan(state, recipe_id)
            if recipe is None:
                recipe = active(find(state, 'recipes', recipe_id))
        dates=[day_after(body['date'],i) for i in range(body['repeat_days'])]
        if body['id']:
            meal=editing
            before_label=meal_summary(state,meal)
            if meal['status']!='planned' or body['repeat_days']!=1: fail('예정 식사만 수정할 수 있습니다.',409)
            # Same recipe keeps its original snapshot unless the menu is explicitly changed.
            if recipe['id']!=meal['recipe_id']: meal['recipe']=deepcopy(recipe)
            meal.update({k:body[k] for k in ['date','slot','recipe_id','servings']})
            summary=f"식사 수정 · {before_label} → {meal_summary(state,meal)}"
        else:
            for day in dates:
                if any(m['date']==day and m['slot']==body['slot'] and m['recipe_id']==recipe['id'] and m['status']=='planned' for m in state['meals']): fail('같은 날짜·시간에 같은 메뉴가 이미 있습니다. 기존 식사의 인분을 수정하세요.',409)
                state['meals'].append(dict(id=uid(),date=day,slot=body['slot'],recipe_id=recipe['id'],recipe=deepcopy(recipe),servings=body['servings'],status='planned',created_at=now()))
        if not body['id']: summary=f"식사 등록 · {body['date']} {recipe['name']} {body['servings']:g}인분 · {len(dates)}일"
        for key, slot in list(pending.items()):
            if slot['target_id'] and slot['target_id'] == body['id']:
                if source_id or recipe['id'] != previous_recipe_id:
                    del pending[key]
            elif not slot['target_id'] and slot['date'] in dates and slot['slot'] == body['slot']:
                del pending[key]
    elif action=='meal.state':
        meal=find(state,'meals',body['id'])
        if meal['status']=='cooked' or meal['status']==body['status'] or (meal['status']!='planned' and body['status']!='planned'): fail('현재 식사 상태에서는 변경할 수 없습니다.',409)
        status_labels={'planned':'예정','eating_out':'외식','cancelled':'취소'}
        old_status=meal['status'];meal['status']=body['status'];summary=f"식사 상태 변경 · {meal_summary(state,meal)} · {status_labels[old_status]} → {status_labels[body['status']]}"
        if body['status'] == 'eating_out':
            slot = next_home_slot(state, meal)
            if slot:
                pending[meal['id']] = slot
    elif action=='meal.skip_followup':
        if body['id'] not in pending:
            fail('이미 정리된 다음 집밥 안내입니다.', 409)
        del pending[body['id']]
        summary='다음 집밥 안내를 닫았어요.'
    elif action=='meal.copy':
        source=[m for m in state['meals'] if m['date']==body['source_date'] and m['status']=='planned']
        if not source: fail('복사할 예정 식사가 없습니다.')
        count=0
        for offset in range(1,body['days']+1):
            day=day_after(body['source_date'],offset)
            for original_meal in source:
                if any(m['date']==day and m['slot']==original_meal['slot'] and m['recipe_id']==original_meal['recipe_id'] and m['status']=='planned' for m in state['meals']): continue
                meal=deepcopy(original_meal);meal.update(id=uid(),date=day,created_at=now());state['meals'].append(meal);count+=1
        summary=f"예정 식사 복사 · {body['source_date']} 다음 {body['days']}일 · {count}건"
    elif action=='meal.cook':
        meal=find(state,'meals',body['id'])
        if meal['status']!='planned': fail('이미 처리한 식사입니다. 중복 차감하지 않습니다.',409)
        allowed={i['ingredient_id'] for i in meal['recipe']['ingredients']};seen=set();deductions=[]
        stock = {'inventory':state['inventory'], 'stock_keys':stock_keys(state['ingredients'])}
        for part in body['usage']:
            if part['ingredient_id'] not in allowed or part['ingredient_id'] in seen: fail('메뉴에 있는 재료를 중복 없이 선택하세요.')
            seen.add(part['ingredient_id']);ing=find(state,'ingredients',part['ingredient_id']);remain=dec(converted(part['quantity'],part['unit'],ing['unit']))
            for lot in ordered_lots(stock,ing['id'],today()):
                take=min(dec(lot['quantity']),remain)
                if take>0: deductions.append(dict(lot_id=lot['id'],ingredient_id=lot['ingredient_id'],quantity=number(take),unit=ing['unit']))
                lot['quantity']=number(dec(lot['quantity'])-take);remain-=take
            if remain>0: fail(f"재고 부족 · {ing['name']} {number(remain):g}{ing['unit']}. 소비기한 지난 재고와 숨긴 재고는 제외합니다.",409)
        meal.update(status='cooked',used=deductions,cooked_at=now());summary=f"조리 완료 · {meal_summary(state,meal)}"
    elif action=='shopping.add':
        body['name']=body['name'].strip()
        if not body['name']: fail('품목명을 입력하세요.')
        state['manual'].append(dict(id=uid(),**body,checked=False,archived=False));summary=f"장보기 추가 · {body['name']}"
    elif action=='shopping.check':
        item=active(find(state,'manual',body['id']));item['checked']=body['checked'];summary=f"장보기 체크 · {item['name']}"
    elif action in ('shopping.archive','shopping.restore'):
        item=find(state,'manual',body['id']);item['archived']=action.endswith('archive');summary=f"장보기 {'숨김' if item['archived'] else '복원'} · {item['name']}"
    elif action=='history.undo':
        summary=undo_event(state,body['id'],event_id)
    state['meal_followups'] = active_followups(state)
    if action!='history.undo':
        mark_changes(original,state,event_id)
    event=dict(id=event_id,at=now(),action=action,summary=summary)
    undo=reversal_data(original,state,action,body)
    if undo: event['undo']=undo
    if action=='history.undo': event['undo_of']=body['id']
    state['history'].insert(0,event)
    state['history']=state['history'][:500]
    if any(len(state[k])>10000 for k in ['ingredients','recipes','products','inventory','meals','manual']): fail('시연용 저장 한도(항목별 10,000개)를 초과했습니다.')
    return state, summary

def fingerprint(action, payload): return sha256(json.dumps([action,payload],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
