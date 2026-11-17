
from datetime import date
from decimal import Decimal


def recommend(workspace, target_date=None, servings=1,
              max_minutes=None, excluded_ids=None,
              preferred_ids=None, limit=10):

    target_date = target_date or date.today().isoformat()
    excluded = set(excluded_ids or [])
    preferred = set(preferred_ids or [])

    ingredients = {
        item["id"]: item
        for item in workspace.get("ingredients", [])
    }

    available = {}

    for lot in workspace.get("inventory", []):
        if lot.get("archived"):
            continue

        if lot.get("purchased_on") and lot["purchased_on"] > target_date:
            continue

        if lot.get("expires_on") and lot["expires_on"] < target_date:
            continue

        ingredient_id = lot["ingredient_id"]

        if ingredient_id not in ingredients:
            continue

        if lot.get("unit") != ingredients[ingredient_id]["unit"]:
            continue

        quantity = Decimal(str(lot.get("quantity", 0)))

        if quantity <= 0:
            continue

        available[ingredient_id] = (
            available.get(ingredient_id, Decimal(0)) + quantity
        )

    results = []

    for recipe in workspace.get("recipes", []):
        if recipe.get("archived"):
            continue

        if max_minutes is not None:
            if recipe.get("minutes", 99999) > max_minutes:
                continue

        parts = recipe.get("ingredients", [])

        if not parts:
            continue

        if any(p["ingredient_id"] in excluded for p in parts):
            continue

        missing = []
        matched = 0
        preferred_count = 0

        base = Decimal(str(recipe.get("base_servings", 1)))

        if base <= 0:
            continue

        for part in parts:
            ingredient_id = part["ingredient_id"]

            if ingredient_id not in ingredients:
                missing.append({
                    "ingredient_id": ingredient_id,
                    "name": "미등록 재료",
                    "shortage": None
                })
                continue

            ingredient = ingredients[ingredient_id]
            required = (
                Decimal(str(part["quantity"]))
                * Decimal(str(servings))
                / base
            )

            have = available.get(ingredient_id, Decimal(0))

            if part.get("unit") != ingredient.get("unit"):
                missing.append({
                    "ingredient_id": ingredient_id,
                    "name": ingredient["name"],
                    "shortage": None
                })
                continue

            if have >= required:
                matched += 1

                if ingredient_id in preferred:
                    preferred_count += 1
            else:
                missing.append({
                    "ingredient_id": ingredient_id,
                    "name": ingredient["name"],
                    "shortage": float(required - have),
                    "unit": ingredient["unit"]
                })

        score = round(
            100 * matched / len(parts) + 8 * preferred_count,
            1
        )

        results.append({
            "recipe_id": recipe["id"],
            "name": recipe["name"],
            "minutes": recipe.get("minutes"),
            "score": score,
            "missing": missing,
            "ready": len(missing) == 0,
            "reason": (
                "보유 재료만으로 조리 가능"
                if not missing
                else f"부족 재료 {len(missing)}종"
            )
        })

    results.sort(
        key=lambda item: (
            len(item["missing"]),
            -item["score"]
        )
    )

    return results[:limit]
