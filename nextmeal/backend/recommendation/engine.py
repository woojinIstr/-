
"""Deterministic recipe eligibility (never writes inventory or meals)."""

from decimal import Decimal, InvalidOperation

from app.workspace import stock_for_meal, today as workspace_today, usable
from app.ingredient_names import stock_keys


def recommend(
    workspace,
    target_date=None,
    servings=1,
    max_minutes=None,
    excluded_ids=None,
    preferred_ids=None,
    limit=10,
    required_ids=None,
    required_groups=None,
    exclusive_groups=None,
    target_slot='dinner',
    target_meal_id=None,
    ready_only=False,
    recipe_source='all',
):
    target_date = target_date or workspace_today()

    keys = stock_keys(workspace.get('ingredients', []))
    def group(ids):
        return {keys.get(ingredient_id, ingredient_id) for ingredient_id in ids}

    excluded = group(excluded_ids or [])
    preferred = group(preferred_ids or [])
    if required_groups is None:
        required_groups = [[ingredient_id] for ingredient_id in (required_ids or [])]
    required = [group(ids) for ids in required_groups]
    exclusive = [[group(option) for option in options] for options in (exclusive_groups or [])]

    ingredients = {
        item['id']: item
        for item in workspace.get('ingredients', [])
    }

    serving = Decimal(str(servings))

    if (
        not serving.is_finite()
        or not (
            Decimal('0.1') <= serving <= Decimal('12')
        )
    ):
        raise ValueError(
            '인분은 0.1~12 사이여야 합니다.'
        )

    # Calculate inventory available on the selected date.
    available = {}

    for lot in stock_for_meal(workspace, target_date, target_slot, target_meal_id):
        if (
            not usable(lot, target_date)
            or lot.get('ingredient_id') not in ingredients
        ):
            continue

        ingredient_id = lot['ingredient_id']

        if lot.get('unit') != ingredients[ingredient_id]['unit']:
            continue

        try:
            quantity = Decimal(
                str(lot.get('quantity', 0))
            )
        except InvalidOperation:
            continue

        if not quantity.is_finite() or quantity <= 0:
            continue

        key = keys[ingredient_id]
        available[key] = available.get(key, Decimal(0)) + quantity

    results = []

    # Evaluate recipes before sending candidates to AI.
    for recipe in workspace.get('recipes', []):
        if (
            recipe.get('archived')
            or not recipe.get('ingredients')
        ):
            continue
        source = recipe.get('source', 'personal')
        if recipe_source != 'all' and recipe_source != source:
            continue

        if max_minutes is not None:
            minutes = recipe.get('minutes')

            if (
                not isinstance(minutes, (int, float))
                or minutes > max_minutes
            ):
                continue

        parts = recipe['ingredients']

        recipe_ingredient_ids = group(part.get('ingredient_id') for part in parts)

        # Excluded ingredients must never appear.
        if recipe_ingredient_ids & excluded:
            continue

        # Every group must be present. Each group can contain aliases or alternatives.
        if any(group.isdisjoint(recipe_ingredient_ids) for group in required):
            continue
        if any(sum(not option.isdisjoint(recipe_ingredient_ids) for option in group) != 1
               for group in exclusive):
            continue

        base = Decimal(
            str(recipe.get('base_servings', 1))
        )

        if not base.is_finite() or base <= 0:
            continue

        missing = []
        details = []
        matched = 0
        preferred_count = 0
        used = {}

        for part in parts:
            ingredient_id = part.get('ingredient_id')
            ingredient = ingredients.get(ingredient_id)

            if (
                not ingredient
                or part.get('unit') != ingredient.get('unit')
            ):
                name = (
                    ingredient['name']
                    if ingredient
                    else '미등록 재료'
                )

                missing.append({
                    'ingredient_id': ingredient_id,
                    'name': name,
                    'shortage': None,
                })

                details.append({
                    'ingredient_id': ingredient_id,
                    'name': name,
                    'unit': part.get('unit'),
                    'required': None,
                    'available': None,
                })

                continue

            required_quantity = (
                Decimal(str(part['quantity']))
                * serving
                / base
            ).quantize(Decimal('0.000001'))

            key = keys[ingredient_id]
            have = available.get(key, Decimal(0)) - used.get(key, Decimal(0))
            used[key] = used.get(key, Decimal(0)) + min(have, required_quantity)

            details.append({
                'ingredient_id': ingredient_id,
                'name': ingredient['name'],
                'unit': ingredient['unit'],
                'required': float(required_quantity),
                'available': float(have),
            })

            if have >= required_quantity:
                matched += 1

                if key in preferred:
                    preferred_count += 1

            else:
                missing.append({
                    'ingredient_id': ingredient_id,
                    'name': ingredient['name'],
                    'shortage': float(
                        required_quantity - have
                    ),
                    'unit': ingredient['unit'],
                    'needs_unit': any(name == key[0] and unit != key[1] for name, unit in available),
                })

        if ready_only and missing:
            continue

        score = round(
            100 * matched / len(parts)
            + 8 * preferred_count,
            1,
        )

        results.append({
            'recipe_id': recipe['id'],
            'name': recipe['name'],
            'minutes': recipe.get('minutes'),
            'source': source,
            'instructions': recipe.get('instructions', ''),
            'score': score,
            'missing': missing,
            'ingredients': details,
            'ready': not missing,
            'reason': (
                '보유 재료만으로 조리 가능'
                if not missing
                else f'부족 재료 {len(missing)}종'
            ),
        })

    # Prefer recipes needing fewer extra ingredients.
    results.sort(
        key=lambda item: (
            len(item['missing']),
            -item['score'],
            item['source'] == 'starter',
            item['recipe_id'],
        )
    )

    return results[:limit]
