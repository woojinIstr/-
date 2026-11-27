import React, {useEffect, useState} from 'react';
import {Button, Card, Field, formatAmount} from './integrated-ui';
import {slotLabels, unitLabels} from './workspace-client';
import RecommendationPanel from './RecommendationPanel';

export function missingLabel(part) {
  if (part.shortage == null || part.needs_unit) return part.name + ' (단위 확인 필요)';
  return part.name + ' ' + formatAmount(part.shortage) + (unitLabels[part.unit] || '');
}

function MenuCard({item, servings, editing, onChoose}) {
  return <Card title={item.name}>
    <p className="muted">{item.minutes}분 · {servings}인분{item.source === 'starter' && ' · 기본 메뉴'}</p>
    <p className={item.missing.length ? 'missing-parts' : 'ready-parts'}>
      {item.missing.length ? '더 필요한 재료 · ' + item.missing.map(missingLabel).join(', ') : '이 끼니는 지금 있는 재료로 만들 수 있어요'}
    </p>
    {item.ingredients.length > 0 && <details>
      <summary>{item.instructions ? '필요 재료와 조리 방법' : '필요 재료'}</summary>
      <ul className="finder-ingredients">{item.ingredients.map(part => <li key={part.ingredient_id}>
        {part.name} {part.required == null ? '(단위 확인 필요)' : formatAmount(part.required) + (unitLabels[part.unit] || '')}
      </li>)}</ul>
      {item.instructions && <p className="instructions">{item.instructions}</p>}
    </details>}
    <Button onClick={onChoose}>{editing ? '이 메뉴로 변경' : '식사에 추가'}</Button>
  </Card>;
}

export default function MenuFinder({workspace, onChoose, target, resuming, onLeaveTarget, onCreate, selection,
  onSelectionChange, revision, suggest, onRecommend, onQuickStock, onRefresh, loading=false}) {
  const [minutes, setMinutes] = useState('30');
  const [exclude, setExclude] = useState('');
  const [prefer, setPrefer] = useState('');
  const [onlyReady, setOnlyReady] = useState(true);
  const [source, setSource] = useState('all');
  const [outcome, setOutcome] = useState(null);
  const [retry, setRetry] = useState(0);
  const plan = target || selection;
  const servings = Number(plan.servings);
  const valid = Number.isFinite(servings) && servings >= 0.1 && servings <= 12 &&
    (!minutes || Number.isInteger(Number(minutes)) && Number(minutes) >= 1 && Number(minutes) <= 1440);
  const hasStock = workspace.inventory.some(lot => !lot.archived && lot.quantity > 0 &&
    (!lot.expires_on || lot.expires_on >= plan.date));
  const query = new URLSearchParams({
    target_date: plan.date, target_slot: plan.slot, servings: String(servings),
    ready_only: String(onlyReady), recipe_source: source, exclude: exclude.trim(), prefer: prefer.trim(), limit: '30',
    ...(minutes ? {max_minutes: minutes} : {}), ...(target ? {target_meal_id: target.id} : {}),
  }).toString();
  const result = outcome?.query === query && outcome.revision === revision && outcome.retry === retry ? outcome : null;

  useEffect(() => {
    if (!valid) return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const data = await suggest(query, controller.signal);
        if (!controller.signal.aborted) setOutcome({query, revision, retry, data});
      } catch (error) {
        if (!controller.signal.aborted) setOutcome({query, revision, retry, error});
      }
    }, 120);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query, revision, retry, suggest, valid]);

  const stale = result?.data && result.data.revision !== revision;
  const recipes = stale ? [] : result?.data?.recommendations || [];
  const emptyTitle = !hasStock ? '냉장고에 재료를 추가해 보세요' : '조건에 맞는 메뉴가 없어요';

  return <>
    <div className="page-head">
      <div><h1>재고로 메뉴 찾기</h1><p>앞선 끼니에 쓸 양을 빼고 남은 재료로 찾았어요.</p></div>
      <Button secondary onClick={onQuickStock}>재료 빠르게 추가</Button>
    </div>
    {resuming && <div className="finder-context">
      <strong>{plan.date} {slotLabels[plan.slot]} · {target ? target.recipe.name+' 변경' : '외식 후 다음 집밥 추가'}</strong>
      <button type="button" className="text-btn" onClick={onLeaveTarget}>새 식사로 찾기</button>
    </div>}
    <div className="finder-controls">
      <div className="finder-pills" role="group" aria-label="조리 시간">
        {[['15','15분'], ['20','20분'], ['30','30분'], ['','전체 시간']].map(([value, name]) =>
          <button type="button" key={name} aria-pressed={minutes === value} onClick={() => setMinutes(value)}>{name}</button>)}
      </div>
      <label className="check-row"><input type="checkbox" checked={onlyReady}
        onChange={event => setOnlyReady(event.target.checked)}/>있는 재료만</label>
      <details className="finder-settings">
        <summary>상세 조건 · {plan.date} {slotLabels[plan.slot]} · {plan.servings || '—'}인분</summary>
        <div className="toolbar" role="group" aria-label="계획할 식사와 조건">
          {!target && <>
            <Field label="식사 날짜"><input required type="date" value={plan.date}
              onChange={event => event.target.value && onSelectionChange({...plan, date: event.target.value})}/></Field>
            <Field label="식사 시간"><select value={plan.slot} onChange={event => onSelectionChange({...plan, slot: event.target.value})}>
              {Object.entries(slotLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select></Field>
            <Field label="먹을 인분"><input type="number" min="0.1" max="12" step="any" value={plan.servings}
              onChange={event => onSelectionChange({...plan, servings: event.target.value})}/></Field>
          </>}
          <Field label="최대 조리 시간(분)"><input type="number" min="1" max="1440" value={minutes}
            onChange={event => setMinutes(event.target.value)}/></Field>
          <Field label="제외 재료(쉼표 구분)"><input value={exclude} maxLength={300} onChange={event => setExclude(event.target.value)}/></Field>
          <Field label="우선 사용할 재료"><input value={prefer} maxLength={300} onChange={event => setPrefer(event.target.value)}/></Field>
          <Field label="메뉴 범위"><select value={source} onChange={event => setSource(event.target.value)}>
            <option value="all">전체</option><option value="personal">내 메뉴</option><option value="starter">기본 메뉴</option>
          </select></Field>
        </div>
      </details>
    </div>
    {!valid && <p role="status" className="muted">인분과 최대 조리 시간의 범위를 확인해 주세요.</p>}
    {valid && !result && <p role="status" className="muted">이 끼니에 쓸 수 있는 재료를 확인하고 있어요.</p>}
    {result?.error && <div role="alert" className="server-error">
      메뉴를 불러오지 못했어요. <Button secondary onClick={() => setRetry(retry + 1)}>다시 확인</Button>
    </div>}
    {stale && <p role="status">재고 또는 식사 계획이 바뀌었어요. <Button secondary onClick={onRefresh}>최신 내용 불러오기</Button></p>}
    {result?.data && !stale && !recipes.length && <Card title={emptyTitle}>
      {result.data.unit_checks?.length > 0 && <p>중량이나 단위를 확인할 재료 · {result.data.unit_checks.join(', ')}</p>}
      {hasStock && onlyReady && !result.data.unit_checks?.length && <p>이 시간 안에 만들 수 있는 등록 메뉴가 없어요. 부족한 재료를 확인해 보세요.</p>}
      <div className="toolbar">
        {!hasStock && <Button onClick={onQuickStock}>첫 재료 추가</Button>}
        {onlyReady && <Button secondary onClick={() => setOnlyReady(false)}>부족한 메뉴도 보기</Button>}
        {minutes && <Button secondary onClick={() => setMinutes('')}>시간 제한 풀기</Button>}
        {source === 'personal' && <Button secondary onClick={onCreate}>내 메뉴 등록</Button>}
      </div>
    </Card>}
    <div className="two-cols finder-results">
      {recipes.map(item => <MenuCard key={item.recipe_id} item={item} servings={servings} editing={Boolean(target)}
        onChoose={() => onChoose(item.recipe_id, {...plan, servings, revision})}/>)}
    </div>
    <details className="finder-ai">
      <summary>AI에 문장으로 물어보기</summary>
      <RecommendationPanel selection={plan} targetId={target?.id} readyOnly={onlyReady} recipeSource={source} revision={revision}
        valid={valid} minutes={minutes} exclude={exclude} prefer={prefer}
        ingredients={workspace.ingredients} onRecommend={onRecommend} onChoose={onChoose} loading={loading}/>
    </details>
  </>;
}
