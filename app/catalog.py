"""Development fixtures adapted from A's data.js (source commit in docs)."""

def ingredient_id(n): return f'10000000-0000-4000-8000-{n:012d}'
def recipe_id(n): return f'20000000-0000-4000-8000-{n:012d}'

EXTRA_INGREDIENTS = [
    {'ingredient_id':ingredient_id(n),'ingredient_name':name,'unit':unit}
    for n,name,unit in [(4,'밥','g'),(5,'우유','ml'),(6,'파스타면','g'),(7,'양파','g'),(8,'토마토 소스','g')]
]
RECIPE_FIXTURES = [
    (1,'닭가슴살 시금치 리소토',15,'닭가슴살과 시금치를 활용하는 간단한 한 끼',[(1,150,'g'),(2,100,'g'),(4,210,'g'),(5,150,'ml')]),
    (2,'닭가슴살 볶음밥',20,'닭가슴살과 밥을 활용하는 볶음밥',[(1,150,'g'),(4,210,'g'),(7,100,'g')]),
    (3,'토마토 파스타',25,'파스타면을 활용하는 기본 메뉴',[(6,100,'g'),(8,150,'g'),(7,100,'g')]),
    (4,'우유 리소토',15,'밥과 우유를 활용하는 부드러운 리소토',[(4,210,'g'),(5,200,'ml'),(7,50,'g')]),
]
RECIPES = [dict(recipe_id=recipe_id(n),recipe_name=name,base_servings=1,cooking_time_minutes=minutes,description=description) for n,name,minutes,description,ings in RECIPE_FIXTURES]
RECIPE_INGREDIENTS = [dict(recipe_id=recipe_id(n),ingredient_id=ingredient_id(i),required_quantity=q,unit=unit) for n,name,minutes,description,ings in RECIPE_FIXTURES for i,q,unit in ings]
