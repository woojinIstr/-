"""Conservative Korean request parsing. Unclear constraints => ask for explicit inputs.

This is deliberately not an open-ended NLP parser: it never silently ignores
recognized constraint markers and never relies on model guesses for safety-critical
filtering. Conditions can also be submitted as explicit query parameters.
"""
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo


class ConditionError(ValueError):
    pass


def _kst_today():
    return datetime.now(ZoneInfo('Asia/Seoul')).date()


def parse_conditions(text, ingredients, *, today=None):
    today = today or _kst_today()
    result = {'target_date':today.isoformat(),'servings':1.0,'max_minutes':None,'excluded_ids':[]}
    used=[]
    # Parse servings: numeric N인분, N명, or Korean small numerals.
    persons=list(re.finditer(r'(?<!\w)(\d+(?:\.\d+)?)\s*(인분|명)(?!\w)',text))
    if not persons:
        for word,n in [('한',1),('두',2),('세',3),('네',4)]:
            persons += list(re.finditer(rf'{word}\s*(명|인분)',text))
            if persons: break
        person_value=float(n) if persons else None
    else:
        person_value=None
    if len(persons)>1: raise ConditionError('인분 표현이 여러 개입니다. 인분을 직접 선택해 주세요.')
    if persons:
        try: v=person_value if person_value is not None else float(persons[0].group(1))
        except (ValueError,TypeError): raise ConditionError('인분을 확인해 주세요.')
        if not (0.1 <= v <= 12): raise ConditionError('인분은 0.1~12 사이에서 입력해 주세요.')
        result['servings']=v
    elif re.search(r'인분|\d+\s*명',text):
        raise ConditionError('인분을 직접 선택해 주세요.')
    # Parse time only for clear upper bound, not statements like '10분 이상'.
    times=list(re.finditer(r'(\d+)\s*(분|시간)\s*(이내|이하|안에|내에|내로)',text))
    if len(times)>1: raise ConditionError('조리 시간 조건이 여러 개입니다. 시간을 직접 선택해 주세요.')
    if times:
        m=times[0]; mins=int(m.group(1))*(60 if m.group(2)=='시간' else 1)
        if not 1 <= mins <= 1440: raise ConditionError('조리 시간은 1~1440분 사이로 입력해 주세요.')
        result['max_minutes']=mins
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
    # Exclusion is strictly name matching, with common explicit alias.
    normalized={re.sub(r'\s+','',i['name']).casefold():i['id'] for i in ingredients}
    alias={'달걀':'계란','에그':'계란'}
    names=sorted({i['name'] for i in ingredients}|set(alias),key=len,reverse=True)
    markers=r'(?:제외|빼고|없이|안\s*넣고|넣지\s*말고)'
    exclusions=list(re.finditer(rf'([가-힣A-Za-z][가-힣A-Za-z0-9\s,·/]*?)\s*(?:은|는|을|를)?\s*{markers}',text))
    for m in exclusions:
        segment=re.sub(r'(?:오늘|내일|모레|저녁|점심|아침|추천|메뉴|요리|만들어|해줘|해주세요|\d+\s*(?:분|시간|인분|명|이내|이하))+',' ',m.group(1))
        # Remove common leading connectors.
        segment=re.sub(r'^(?:그리고|또|그냥|저는|나는|일단|되도록|가능하면|음식은|재료는)\s*','',segment.strip())
        candidates=[p.strip() for p in re.split(r'[,·/]|\s*(?:하고|이랑|랑|과|와|및)\s*',segment) if p.strip()]
        if not candidates: raise ConditionError('제외할 재료를 직접 선택해 주세요.')
        for p in candidates:
            p=re.sub(r'(?:은|는|을|를)$','',p).strip()
            canonical=alias.get(p,p)
            iid=normalized.get(re.sub(r'\s+','',canonical).casefold())
            if iid is None: raise ConditionError(f'제외 재료 "{p}"를 확인할 수 없습니다. 목록에서 직접 선택해 주세요.')
            result['excluded_ids'].append(iid)
    if re.search(markers,text) and not exclusions:
        raise ConditionError('제외할 재료를 목록에서 직접 선택해 주세요.')
    result['excluded_ids']=list(dict.fromkeys(result['excluded_ids']))
    return result
