"""Conservative Korean request parsing. Unclear constraints => ask for explicit inputs.

This is deliberately not an open-ended NLP parser: it never silently ignores
recognized constraint markers and never relies on model guesses for safety-critical
filtering. Conditions can also be submitted as explicit query parameters.
"""
import re
from datetime import date, timedelta
from decimal import Decimal

from app.workspace import today as workspace_today


class ConditionError(ValueError):
    pass


SERVINGS = re.compile(r'(?<![\w.])([+-]?\d+(?:\.\d+)?|한|두|세|네)\s*(?:인분|명)')
PERSON_WORDS = {'한': 1, '두': 2, '세': 3, '네': 4}
DURATION = re.compile(r'(?<![\d.])([+-]?\d+(?:\.\d+)?)\s*(분|시간)')
UPPER_BOUND = re.compile(r'\s*(?:이내|이하|안에|내에|내로)')
EXCLUSION = re.compile(r'제외|빼고|없이|안\s*넣고|넣지\s*말고|빼\s*(?:주세요|줘)')
EGG_NAMES = frozenset({'달걀', '계란', '에그'})


def _normalize(name):
    return re.sub(r'\s+', '', name).casefold()


def _ingredient_ids(name, ingredients):
    key = _normalize(name)
    accepted = EGG_NAMES if key in EGG_NAMES else {key}
    return [i['id'] for i in ingredients if _normalize(i['name']) in accepted]


def parse_conditions(text, ingredients, *, today=None, default_date=None, default_servings=1.0):
    today = today or date.fromisoformat(workspace_today())
    result = {'target_date': (default_date or today).isoformat(), 'servings': default_servings,
              'max_minutes': None, 'excluded_ids': []}
    used=[]
    persons = list(SERVINGS.finditer(text))
    if len(persons)>1:
        raise ConditionError('인분 표현이 여러 개입니다. 인분을 직접 선택해 주세요.')
    if persons:
        person = persons[0]
        value = person.group(1)
        v = float(PERSON_WORDS[value] if value in PERSON_WORDS else value)
        if not (0.1 <= v <= 12): raise ConditionError('인분은 0.1~12 사이에서 입력해 주세요.')
        result['servings']=v
        used.append(person.span())
    elif re.search(r'인분|\d+\s*명',text):
        raise ConditionError('인분을 직접 선택해 주세요.')

    # Require a single duration and an explicit upper bound.
    times = list(DURATION.finditer(text))
    if len(times)>1:
        raise ConditionError('조리 시간 조건은 최대 시간 하나로 입력해 주세요.')
    if times:
        duration = times[0]
        bound = UPPER_BOUND.match(text, duration.end())
        if not bound or re.search(r'\d\s*[~～–−-]\s*$', text[:duration.start()]):
            raise ConditionError('조리 시간 표현이 불명확합니다. 최대 시간을 직접 입력해 주세요.')
        mins = Decimal(duration.group(1)) * (60 if duration.group(2)=='시간' else 1)
        if not 1 <= mins <= 1440 or mins != mins.to_integral_value():
            raise ConditionError('조리 시간은 1~1440 사이의 분 단위로 입력해 주세요.')
        result['max_minutes'] = int(mins)
        used.append((duration.start(), bound.end()))
    elif re.search(r'\d+\s*(?:분|시간)|\b분\s*(?:이내|이하)',text):
        raise ConditionError('조리 시간 표현이 불명확합니다. 최대 시간을 직접 입력해 주세요.')
    # Interpret Korea-local relative or explicit dates. No guess for ambiguous dates.
    dates=[]
    for phrase,delta in [('모레',2),('내일',1),('오늘',0)]:
        if phrase in text: dates.append(today+timedelta(days=delta))
    for m in re.finditer(r'(?<!\d)(\d{4})[-./](\d{1,2})[-./](\d{1,2})(?!\d)',text):
        try: dates.append(date(int(m.group(1)),int(m.group(2)),int(m.group(3))))
        except ValueError: raise ConditionError('날짜가 올바르지 않습니다.')
    # Only month/day without year: choose next occurrence, not a past date.
    for m in re.finditer(r'(?<!\d)(?<![-./])(?<!\d)(\d{1,2})월\s*(\d{1,2})일',text):
        try:
            proposed=date(today.year,int(m.group(1)),int(m.group(2)))
            if proposed<today: proposed=date(today.year+1,int(m.group(1)),int(m.group(2)))
            dates.append(proposed)
        except ValueError: raise ConditionError('날짜가 올바르지 않습니다.')
    if len(dates)>1: raise ConditionError('날짜 조건이 여러 개입니다. 날짜를 직접 선택해 주세요.')
    if dates: result['target_date']=dates[0].isoformat()
    elif re.search(r'언제|이번\s*주|다음\s*주|월요일|화요일|수요일|목요일|금요일|토요일|일요일|\d+일',text):
        raise ConditionError('날짜를 YYYY-MM-DD 형식으로 직접 선택해 주세요.')
    for start, end in sorted(used, reverse=True):
        text = text[:start] + '|' + text[end:]
    cursor = 0
    for marker in EXCLUSION.finditer(text):
        segment = text[cursor:marker.start()].rsplit('|', 1)[-1].strip(' ,')
        cursor = marker.end()
        segment = re.sub(
            r'^(?:(?:오늘|내일|모레|아침|점심|저녁|그리고|또|저는|나는|일단|되도록|가능하면)\s+)*',
            '', segment,
        )
        candidates = re.split(r'[,·/]|(?:하고|이랑|랑|과|와|및)\s+', segment)
        for name in ([segment] if _ingredient_ids(segment, ingredients) else candidates):
            name = name.strip()
            ids = _ingredient_ids(name, ingredients)
            if not ids:
                ids = _ingredient_ids(re.sub(r'[은는을를]$', '', name).strip(), ingredients)
            if not ids:
                if not name:
                    raise ConditionError('제외할 재료를 목록에서 직접 선택해 주세요.')
                raise ConditionError(f'제외 재료 "{name}"를 확인할 수 없습니다. 목록에서 직접 선택해 주세요.')
            result['excluded_ids'].extend(ids)
    result['excluded_ids']=list(dict.fromkeys(result['excluded_ids']))
    return result
