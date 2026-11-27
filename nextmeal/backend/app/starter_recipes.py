"""Shared recipes. A pantry or personal cookbook starts empty."""
from uuid import NAMESPACE_URL, uuid5
from .ingredient_names import ALIASES, canonical_name, name_key as _name_key


INGREDIENTS = {
    '삼겹살': ('g', ()),
    '달걀': ('count', ALIASES['달걀']),
    '밥': ('g', ALIASES['밥']),
    '양파': ('g', ()),
    '두부': ('g', ()),
    '감자': ('g', ()),
    '고구마': ('g', ()),
    '당근': ('g', ()),
    '닭가슴살': ('g', ()),
    '우유': ('ml', ()),
    '양배추': ('g', ()),
    '토마토': ('g', ()),
    '김치': ('g', ALIASES['김치']),
    '참치캔': ('g', ALIASES['참치캔']),
    '대파': ('g', ()),
    '스팸': ('g', ALIASES['스팸']),
    '식빵': ('count', ()),
    '치즈': ('count', ('슬라이스치즈',)),
}

RECIPES = (
    ('pork', '삼겹살구이', 15, {'삼겹살': 150},
     '달군 팬에 삼겹살을 겹치지 않게 놓고, 뒤집어 속까지 익혀요.'),
    ('pork-rice', '삼겹살 덮밥', 20, {'삼겹살': 120, '밥': 180, '양파': 50},
     '삼겹살을 한입 크기로 구워 익힌 뒤 채 썬 양파를 함께 볶아요. 따뜻한 밥에 올려요.'),
    ('boiled-eggs', '삶은 달걀', 15, {'달걀': 2},
     '달걀을 물에 담가 끓여 익힌 뒤 찬물에 식혀 껍질을 벗겨요.'),
    ('egg-rice', '달걀밥', 15, {'달걀': 2, '밥': 180},
     '달걀을 삶아 익힌 뒤 껍질을 벗겨 으깨고 따뜻한 밥과 섞어요.'),
    ('tofu', '따뜻한 두부', 10, {'두부': 150},
     '두부를 먹기 좋게 썰고 끓는 물에 데운 뒤 물기를 빼요.'),
    ('tofu-cabbage', '두부 양배추찜', 15, {'두부': 150, '양배추': 100},
     '썬 양배추에 두부를 올리고, 뚜껑을 덮어 수증기로 양배추가 부드러워질 때까지 익혀요.'),
    ('potato', '찐 감자', 20, {'감자': 200},
     '감자를 한입 크기로 잘라 찜기에 올려 젓가락이 부드럽게 들어갈 때까지 익혀요.'),
    ('sweet-potato', '찐 고구마', 20, {'고구마': 200},
     '고구마를 작게 썰어 찜기에서 부드러워질 때까지 익혀요.'),
    ('potato-carrot', '감자 당근찜', 20, {'감자': 150, '당근': 80},
     '감자와 당근을 비슷한 크기로 썰고 찜기에서 부드럽게 익혀요.'),
    ('chicken-onion', '닭가슴살 양파찜', 20, {'닭가슴살': 150, '양파': 70},
     '닭가슴살을 얇게 썰고 양파와 함께 찜기에 올려 속까지 익혀요.'),
    ('milk-rice', '우유죽', 15, {'밥': 160, '우유': 200},
     '냄비에 밥과 우유를 넣고 약한 불에서 저으면서 원하는 농도가 될 때까지 끓여요.'),
    ('tomato-egg', '토마토 달걀국', 15, {'토마토': 150, '달걀': 2},
     '토마토를 썰어 물에 넣고 끓인 뒤, 푼 달걀을 둘러 넣고 익혀요.'),
    ('kimchi-tuna-rice', '김치참치덮밥', 15, {'김치': 80, '참치캔': 80, '밥': 180},
     '김치를 잘게 썰어 참치캔 내용물과 함께 팬에 넣고 물을 조금 더해 익혀요. 따뜻한 밥 위에 올려요.'),
    ('kimchi-egg-rice', '김치달걀덮밥', 15, {'김치': 80, '달걀': 1, '밥': 180},
     '김치를 썰어 팬에 물을 조금 넣고 볶듯이 익혀요. 달걀을 넣고 완전히 익힌 뒤 따뜻한 밥 위에 올려요.'),
    ('tofu-kimchi', '두부김치', 15, {'두부': 150, '김치': 80},
     '두부는 데쳐서 썰어요. 김치는 물을 조금 넣고 익혀 두부와 함께 담아요.'),
    ('scallion-egg', '대파달걀국', 10, {'대파': 20, '달걀': 1},
     '대파를 썰어 물에 넣고 끓여요. 달걀을 풀어 넣고 충분히 익혀요.'),
    ('spam-rice', '스팸덮밥', 10, {'스팸': 80, '밥': 180},
     '햄을 작게 썰어 팬에 구운 뒤 따뜻한 밥 위에 올려요.'),
    ('cheese-toast', '치즈 토스트', 10, {'식빵': 2, '치즈': 1},
     '식빵에 슬라이스 치즈를 넣고 팬에 앞뒤로 구워 치즈를 녹여요.'),
    ('egg-toast', '달걀 토스트', 10, {'식빵': 2, '달걀': 1},
     '달걀을 앞뒤로 충분히 익혀 구운 식빵 사이에 넣어요.'),
    ('tofu-egg', '두부 달걀 스크램블', 15, {'두부': 150, '달걀': 1},
     '두부를 으깨 팬에서 물기를 날리고, 푼 달걀을 섞어 충분히 익혀요.'),
)


def _id(key):
    return str(uuid5(NAMESPACE_URL, 'nextmeal:starter:' + key))


def _ingredients(workspace):
    existing = {(_name_key(item['name']), item['unit']): item for item in workspace['ingredients']}
    used_names = {_name_key(item['name']) for item in workspace['ingredients']}
    active_stock = {
        lot['ingredient_id'] for lot in workspace['inventory']
        if lot['quantity'] > 0 and not lot.get('archived')
    }
    result = {}
    for name, (unit, aliases) in INGREDIENTS.items():
        key = _id(name)
        matches = [item for (_, base), item in existing.items()
                   if base == unit and canonical_name(item.get('canonical_name', item['name'])) == canonical_name(name)]
        matches.extend(existing[(_name_key(alias), unit)] for alias in aliases
                       if (_name_key(alias), unit) in existing and existing[(_name_key(alias), unit)] not in matches)
        has_default = next((item for item in workspace['ingredients'] if item['id'] == key), None)
        item = next((item for item in matches if item['id'] in active_stock), None)
        if item or matches or has_default:
            result[name] = item or (matches[0] if matches else has_default)
            continue
        label = name
        if _name_key(name) in used_names:
            unit_label = {'g': 'g', 'ml': 'mL', 'count': '개'}[unit]
            label = f'{name} ({unit_label})'
            suffix = 2
            while _name_key(label) in used_names:
                label = f'{name} ({unit_label} {suffix})'
                suffix += 1
        result[name] = {'id': key, 'name': label, 'unit': unit, 'canonical_name': name}
    return result


def _recipe(row, ingredients):
    key, name, minutes, parts, instructions = row
    return {
        'id': _id(key), 'name': name, 'minutes': minutes, 'base_servings': 1,
        'description': '', 'instructions': instructions, 'archived': False, 'source': 'starter',
        'ingredients': [
            {'ingredient_id': ingredients[name]['id'], 'quantity': quantity, 'unit': ingredients[name]['unit']}
            for name, quantity in parts.items()
        ],
    }


def expand_for_recommendation(workspace):
    ingredients = _ingredients(workspace)
    existing = {item['id'] for item in workspace['ingredients']}
    return {
        **workspace,
        'ingredients': [*workspace['ingredients'], *(item for item in ingredients.values() if item['id'] not in existing)],
        'recipes': [*workspace['recipes'], *(_recipe(row, ingredients) for row in RECIPES)],
    }


def starter_recipe_for_plan(workspace, recipe_id):
    """Resolve shared recipe IDs and save only the metadata a plan requires."""
    row = next((row for row in RECIPES if _id(row[0]) == recipe_id), None)
    if row is None:
        return None
    ingredients = _ingredients(workspace)
    existing = {item['id'] for item in workspace['ingredients']}
    workspace['ingredients'].extend(ingredients[name] for name in row[3] if ingredients[name]['id'] not in existing)
    return _recipe(row, ingredients)
