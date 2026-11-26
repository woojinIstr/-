
"""Deterministic recipe eligibility (never writes inventory or meals)."""

from decimal import Decimal, InvalidOperation

from app.workspace import today as workspace_today


def recommend(
    workspace,
    target_date=None,
    servings=1,
    max_minutes=None,
    excluded_ids=None,
    preferred_ids=None,
    limit=10,
    required_ids=None,
):
    target_date = target_date or workspace_today()

    excluded = set(excluded_ids or [])
    preferred = set(preferred_ids or [])
    required_ingredients = set(required_ids or [])

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

    for lot in workspace.get('inventory', []):
        if (
            lot.get('archived')
            or lot.get('ingredient_id') not in ingredients
        ):
            continue

        if (
            lot.get('purchased_on')
            and lot['purchased_on'] > target_date
        ):
            continue

        if (
            lot.get('expires_on')
            and lot['expires_on'] < target_date
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

        available[ingredient_id] = (
            available.get(ingredient_id, Decimal(0))
            + quantity
        )

    results = []

    # Evaluate recipes before sending candidates to AI.
    for recipe in workspace.get('recipes', []):
        if (
            recipe.get('archived')
            or not recipe.get('ingredients')
        ):
            continue

        if max_minutes is not None:
            minutes = recipe.get('minutes')

            if (
                not isinstance(minutes, (int, float))
                or minutes > max_minutes
            ):
                continue

        parts = recipe['ingredients']

        recipe_ingredient_ids = {
            part.get('ingredient_id')
            for part in parts
        }

        # Excluded ingredients must never appear.
        if recipe_ingredient_ids & excluded:
            continue

        # At least one matching ID from the required group
        # must exist in the recipe.
        # This also supports aliases such as 달걀/계란.
        if (
            required_ingredients
            and not (
                recipe_ingredient_ids & required_ingredients
            )
        ):
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

            have = available.get(
                ingredient_id,
                Decimal(0),
            )

            details.append({
                'ingredient_id': ingredient_id,
                'name': ingredient['name'],
                'unit': ingredient['unit'],
                'required': float(required_quantity),
                'available': float(have),
            })

            if have >= required_quantity:
                matched += 1

                if ingredient_id in preferred:
                    preferred_count += 1

            else:
                missing.append({
                    'ingredient_id': ingredient_id,
                    'name': ingredient['name'],
                    'shortage': float(
                        required_quantity - have
                    ),
                    'unit': ingredient['unit'],
                })

        score = round(
            100 * matched / len(parts)
            + 8 * preferred_count,
            1,
        )

        results.append({
            'recipe_id': recipe['id'],
            'name': recipe['name'],
            'minutes': recipe.get('minutes'),
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
            item['recipe_id'],
        )
    )

    return results[:limit]
