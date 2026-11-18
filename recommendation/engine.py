"""Deterministic recipe eligibility (never writes inventory or meals)."""
from datetime import datetime
from zoneinfo import ZoneInfo
from decimal import Decimal, InvalidOperation


def recommend(workspace, target_date=None, servings=1, max_minutes=None,
              excluded_ids=None, preferred_ids=None, limit=10):
    target_date = target_date or datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
    excluded = set(excluded_ids or [])
    preferred = set(preferred_ids or [])
    ingredients = {i['id']: i for i in workspace.get('ingredients', [])}
    serving = Decimal(str(servings))
    if not serving.is_finite() or not (Decimal('0.1') <= serving <= Decimal('12')):
        raise ValueError('인분은 0.1~12 사이여야 합니다.')
    available = {}
    for lot in workspace.get('inventory', []):
        if lot.get('archived') or lot.get('ingredient_id') not in ingredients:
            continue
        if lot.get('purchased_on') and lot['purchased_on'] > target_date:
            continue
        if lot.get('expires_on') and lot['expires_on'] < target_date:
            continue
        iid = lot['ingredient_id']
        if lot.get('unit') != ingredients[iid]['unit']:
            continue
        try: qty = Decimal(str(lot.get('quantity', 0)))
        except InvalidOperation: continue
        if not qty.is_finite() or qty <= 0: continue
        available[iid] = available.get(iid, Decimal(0)) + qty
    results = []
    for recipe in workspace.get('recipes', []):
        if recipe.get('archived') or not recipe.get('ingredients'):
            continue
        if max_minutes is not None and (not isinstance(recipe.get('minutes'), (int,float)) or recipe['minutes'] > max_minutes):
            continue
        parts=recipe['ingredients']
        if any(p.get('ingredient_id') in excluded for p in parts):
            continue
        base=Decimal(str(recipe.get('base_servings',1)))
        if not base.is_finite() or base <= 0: continue
        missing=[]; details=[]; matched=0; preferred_count=0
        for part in parts:
            iid=part.get('ingredient_id')
            ing=ingredients.get(iid)
            if not ing or part.get('unit') != ing.get('unit'):
                missing.append({'ingredient_id':iid,'name':ing['name'] if ing else '미등록 재료','shortage':None})
                details.append({'ingredient_id':iid,'name':ing['name'] if ing else '미등록 재료','unit':part.get('unit'),'required':None,'available':None})
                continue
            required=Decimal(str(part['quantity']))*serving/base
            have=available.get(iid,Decimal(0))
            details.append({'ingredient_id':iid,'name':ing['name'],'unit':ing['unit'],'required':float(required),'available':float(have)})
            if have >= required:
                matched += 1
                if iid in preferred: preferred_count += 1
            else:
                missing.append({'ingredient_id':iid,'name':ing['name'],'shortage':float(required-have),'unit':ing['unit']})
        score=round(100*matched/len(parts)+8*preferred_count,1)
        results.append({'recipe_id':recipe['id'],'name':recipe['name'],'minutes':recipe.get('minutes'),
                        'score':score,'missing':missing,'ingredients':details,'ready':not missing,
                        'reason':'보유 재료만으로 조리 가능' if not missing else f'부족 재료 {len(missing)}종'})
    results.sort(key=lambda x:(len(x['missing']),-x['score'],x['recipe_id']))
    return results[:limit]
