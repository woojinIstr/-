"""Names that refer to the same ingredient at the same base unit."""

ALIASES = {
    '달걀': ('계란', '에그'),
    '밥': ('흰밥', '햇반', '즉석밥'),
    '김치': ('배추김치',),
    '참치캔': ('캔참치', '통조림참치', '참치통조림'),
    '스팸': ('스팸햄',),
    '치즈': ('슬라이스치즈',),
}


def name_key(name):
    return ''.join(name.split()).casefold()


_CANONICAL = {name_key(alias): name for name, aliases in ALIASES.items() for alias in (name, *aliases)}


def canonical_name(name):
    key = name_key(name)
    return _CANONICAL.get(key, key)


def stock_keys(ingredients):
    return {item['id']: (canonical_name(item.get('canonical_name', item['name'])), item['unit']) for item in ingredients}
