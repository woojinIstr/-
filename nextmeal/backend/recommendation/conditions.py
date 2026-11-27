
"""Conservative Korean request parsing.

Unclear constraints require explicit inputs rather than model guesses.
"""

import re
from datetime import date, timedelta
from decimal import Decimal

from app.workspace import today as workspace_today
from app.ingredient_names import ALIASES, canonical_name


class ConditionError(ValueError):
    pass


SERVINGS = re.compile(
    r'(?<![\w.])([+-]?\d+(?:\.\d+)?|한|두|세|네)\s*(?:인분|명)'
)
PERSON_WORDS = {'한': 1, '두': 2, '세': 3, '네': 4}

DURATION = re.compile(
    r'(?<![\d.])([+-]?\d+(?:\.\d+)?)\s*(분|시간)'
)
UPPER_BOUND = re.compile(
    r'\s*(?:이내|이하|안에|내에|내로)'
)

EXCLUSION = re.compile(
    r'제외|빼고|없이|안\s*넣고|넣지\s*말고|빼\s*(?:주세요|줘)'
)
PANTRY_ONLY = re.compile(
    r'냉장고(?:에|에서)\s*(?:바로\s*)?만들\s*수\s*있는'
    r'|(?:냉장고(?:에|에서)?\s*)?(?:현재\s*|지금\s*)?'
    r'(?:있는|보유한|가진|남은)\s*(?:식재료|재료)(?:들)?\s*'
    r'(?:만(?:으로|을)?(?:\s*(?:사용해서|이용해서|써서))?|(?:으로|로)\s*만들\s*수\s*있는)'
    r'|추가\s*(?:구매|장보기)\s*(?:없이|안\s*하고)'
)

INGREDIENT_NAMES = {label for name, aliases in ALIASES.items() for label in (name, *aliases)}
INGREDIENT_JOIN = re.compile(
    r'(?:(?P<or>/\s*|(?:또는|혹은|이나|나)\s+)'
    r'|(?P<and>[,·]\s*|(?:하고|이랑|랑|과|와|및|그리고)\s+))$'
)
REQUIRED_CHOICE = re.compile(r'(중\s*하나(?:만)?|둘\s*다|모두)\s*$')
INGREDIENT_PARTICLE = r'(?:을|를|이|가|으로|로|도)'
REQUIRED_USE = (
    r'(?:활용|사용|이용|포함)(?:하고|하되|한|해서|하여|하는)?'
    r'|들어(?:있는|가는|간)|넣(?:어서|은|고)|만(?:든|드는)'
)


def _ingredient_ids(name, ingredients):
    key = canonical_name(name)
    return [item['id'] for item in ingredients
            if canonical_name(item.get('canonical_name', item['name'])) == key]


def _required_ingredients(text, ingredients):
    """Return ingredient groups; a recipe needs one match from every group."""
    names = sorted(
        {item['name'] for item in ingredients} | INGREDIENT_NAMES,
        key=lambda name: (-len(name), name),
    )
    catalog = '|'.join(re.escape(name) for name in names)
    item = re.compile(
        rf'(?<![가-힣A-Za-z0-9])(?:(?P<known>{catalog}){INGREDIENT_PARTICLE}?'
        r'|(?P<other>[가-힣A-Za-z0-9][가-힣A-Za-z0-9_()-]*))\s*$',
        re.IGNORECASE,
    )
    verbs = re.compile(rf'(?:{REQUIRED_USE})(?![가-힣A-Za-z0-9])')
    # Prevent a negated verb such as '안 넣고' from registering a requirement.
    text = EXCLUSION.sub(lambda marker: '|' * len(marker[0]), text)
    groups, exclusive, used = [], [], []
    cursor = 0
    for verb in verbs.finditer(text):
        clause = text[cursor:verb.start()]
        choice = REQUIRED_CHOICE.search(clause)
        end = choice.start() if choice else len(clause)
        part = item.search(clause, 0, end)
        if not part:
            cursor = verb.end()
            continue

        terms, operators = [], set()
        start = part.start()
        while part:
            terms.append(part.group('known') or part.group('other'))
            start = part.start()
            join = INGREDIENT_JOIN.search(clause, 0, start)
            if not join:
                break
            previous = item.search(clause, 0, join.start())
            if not previous or previous[0].strip() in {'오늘', '내일', '모레', '아침', '점심', '저녁'}:
                break
            operators.add(join.lastgroup)
            part = previous

        start += cursor
        cursor = verb.end()
        if len(terms) == 1 and re.fullmatch(
            rf'(?:재료|식재료|재고|것|걸){INGREDIENT_PARTICLE}?', terms[0]
        ):
            continue
        if len(operators) > 1 and not choice:
            raise ConditionError('모두 넣을 재료와 둘 중 하나만 넣을 재료를 나누어 입력해 주세요.')

        alternatives = choice[1].startswith('중') if choice else operators == {'or'}
        if alternatives and len(terms) < 2:
            raise ConditionError('둘 중 하나를 고르려면 재료 이름을 두 개 이상 입력해 주세요.')

        condition_groups = []
        for name in reversed(terms):
            ids = _ingredient_ids(name, ingredients)
            if not ids:
                cleaned = re.sub(r'(?:을|를|이|가|으로|로)$', '', name) or name
                raise ConditionError(f'필수 재료 “{cleaned}”를 등록한 식재료에서 찾을 수 없어요. 이름을 확인해 주세요.')
            condition_groups.append(ids)
        if alternatives:
            if choice and choice[1].endswith('만'):
                distinct_options = list(dict.fromkeys(tuple(group) for group in condition_groups))
                exclusive.append([list(option) for option in distinct_options])
            condition_groups = [list(dict.fromkeys(i for group in condition_groups for i in group))]
        groups.extend(condition_groups)
        used.append((start, verb.end()))
    return groups, exclusive, used


def parse_conditions(
    text,
    ingredients,
    *,
    today=None,
    default_date=None,
    default_servings=1.0,
):
    today = today or date.fromisoformat(workspace_today())

    result = {
        'target_date': (default_date or today).isoformat(),
        'servings': default_servings,
        'max_minutes': None,
        'excluded_ids': [],
        'required_ids': [],
        'required_groups': [],
        'exclusive_groups': [],
    }

    pantry_phrases = list(PANTRY_ONLY.finditer(text))
    result['ready_only'] = bool(pantry_phrases)
    used = [match.span() for match in pantry_phrases]

    # 1. Servings
    persons = list(SERVINGS.finditer(text))

    if len(persons) > 1:
        raise ConditionError(
            '인분 표현이 여러 개입니다. 인분을 직접 선택해 주세요.'
        )

    if persons:
        person = persons[0]
        value = person.group(1)
        servings = float(
            PERSON_WORDS[value] if value in PERSON_WORDS else value
        )

        if not (0.1 <= servings <= 12):
            raise ConditionError(
                '인분은 0.1~12 사이에서 입력해 주세요.'
            )

        result['servings'] = servings
        used.append(person.span())

    elif re.search(r'인분|\d+\s*명', text):
        raise ConditionError(
            '인분을 직접 선택해 주세요.'
        )

    # 2. Maximum cooking time
    times = list(DURATION.finditer(text))

    if len(times) > 1:
        raise ConditionError(
            '조리 시간 조건은 최대 시간 하나로 입력해 주세요.'
        )

    if times:
        duration = times[0]
        bound = UPPER_BOUND.match(text, duration.end())

        if (
            not bound
            or re.search(
                r'\d\s*[~～–−-]\s*$',
                text[:duration.start()],
            )
        ):
            raise ConditionError(
                '조리 시간 표현이 불명확합니다. '
                '최대 시간을 직접 입력해 주세요.'
            )

        minutes = Decimal(duration.group(1)) * (
            60 if duration.group(2) == '시간' else 1
        )

        if (
            not 1 <= minutes <= 1440
            or minutes != minutes.to_integral_value()
        ):
            raise ConditionError(
                '조리 시간은 1~1440 사이의 분 단위로 입력해 주세요.'
            )

        result['max_minutes'] = int(minutes)
        used.append((duration.start(), bound.end()))

    elif re.search(
        r'\d+\s*(?:분|시간)|\b분\s*(?:이내|이하)',
        text,
    ):
        raise ConditionError(
            '조리 시간 표현이 불명확합니다. '
            '최대 시간을 직접 입력해 주세요.'
        )

    # 3. Date
    dates = []

    for phrase, delta in [
        ('모레', 2),
        ('내일', 1),
        ('오늘', 0),
    ]:
        if phrase in text:
            dates.append(today + timedelta(days=delta))

    for match in re.finditer(
        r'(?<!\d)(\d{4})[-./](\d{1,2})[-./](\d{1,2})(?!\d)',
        text,
    ):
        try:
            dates.append(
                date(
                    int(match.group(1)),
                    int(match.group(2)),
                    int(match.group(3)),
                )
            )
        except ValueError:
            raise ConditionError(
                '날짜가 올바르지 않습니다.'
            )

    for match in re.finditer(
        r'(?<!\d)(?<![-./])(\d{1,2})월\s*(\d{1,2})일',
        text,
    ):
        try:
            proposed = date(
                today.year,
                int(match.group(1)),
                int(match.group(2)),
            )

            if proposed < today:
                proposed = date(
                    today.year + 1,
                    int(match.group(1)),
                    int(match.group(2)),
                )

            dates.append(proposed)

        except ValueError:
            raise ConditionError(
                '날짜가 올바르지 않습니다.'
            )

    if len(dates) > 1:
        raise ConditionError(
            '날짜 조건이 여러 개입니다. '
            '날짜를 직접 선택해 주세요.'
        )

    if dates:
        result['target_date'] = dates[0].isoformat()

    elif re.search(
        r'언제|이번\s*주|다음\s*주|'
        r'월요일|화요일|수요일|목요일|금요일|토요일|일요일|'
        r'\d+일',
        text,
    ):
        raise ConditionError(
            '날짜를 YYYY-MM-DD 형식으로 직접 선택해 주세요.'
        )

    required_text = text
    for start, end in used:
        suffix = re.match(r'(?:으로|로)(?:는)?', text[end:])
        if suffix:
            end += suffix.end()
        required_text = required_text[:start] + '|' * (end - start) + required_text[end:]
    required_groups, exclusive_groups, required_spans = _required_ingredients(required_text, ingredients)
    used.extend(required_spans)

    # Exclusions parse only text outside recognized positive conditions.
    remaining_text = text

    for start, end in sorted(used, reverse=True):
        remaining_text = (
            remaining_text[:start]
            + '|'
            + remaining_text[end:]
        )

    # 5. Excluded ingredients
    cursor = 0

    for marker in EXCLUSION.finditer(remaining_text):
        segment = (
            remaining_text[cursor:marker.start()]
            .rsplit('|', 1)[-1]
            .strip(' ,')
        )

        cursor = marker.end()

        segment = re.sub(
            r'^(?:(?:오늘|내일|모레|아침|점심|저녁|'
            r'그리고|또|저는|나는|일단|되도록|가능하면)\s+)*',
            '',
            segment,
        )

        candidates = re.split(
            r'[,·/]|(?:하고|이랑|랑|과|와|및)\s+',
            segment,
        )

        names_to_check = (
            [segment]
            if _ingredient_ids(segment, ingredients)
            else candidates
        )

        for name in names_to_check:
            name = name.strip()

            ids = _ingredient_ids(name, ingredients)

            if not ids:
                cleaned = re.sub(
                    r'[은는을를]$',
                    '',
                    name,
                ).strip()
                ids = _ingredient_ids(cleaned, ingredients)

            if not ids:
                if not name:
                    raise ConditionError(
                        '제외할 재료를 목록에서 직접 선택해 주세요.'
                    )

                raise ConditionError(
                    f'제외 재료 "{name}"를 확인할 수 없습니다. '
                    '목록에서 직접 선택해 주세요.'
                )

            result['excluded_ids'].extend(ids)

    result['excluded_ids'] = list(
        dict.fromkeys(result['excluded_ids'])
    )

    excluded = set(result['excluded_ids'])
    required_groups = [[i for i in group if i not in excluded] for group in required_groups]
    if any(not group for group in required_groups):
        raise ConditionError(
            '같은 재료를 필수 재료와 제외 재료로 '
            '동시에 지정할 수 없습니다.'
        )

    result['required_groups'] = required_groups
    result['exclusive_groups'] = exclusive_groups
    result['required_ids'] = list(dict.fromkeys(i for group in required_groups for i in group))
    return result
