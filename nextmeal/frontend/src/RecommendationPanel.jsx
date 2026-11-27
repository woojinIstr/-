import React, {useEffect, useState} from 'react';
import {Button, Card, Field, formatAmount} from './integrated-ui';
import {slotLabels, unitLabels} from './workspace-client';

function missingLabel(part) {
  if (part.shortage == null || part.needs_unit) return part.name + ' (단위 확인 필요)';
  return part.name + ' ' + formatAmount(part.shortage) + (unitLabels[part.unit] || '');
}

export default function RecommendationPanel({selection, targetId, readyOnly, recipeSource, revision,
  valid, minutes, exclude, prefer, ingredients, onRecommend, onChoose, loading=false}) {
  const [prompt, setPrompt] = useState('');
  const [result, setResult] = useState(null);
  const [retryUntil, setRetryUntil] = useState(0);
  const servings = Number(selection.servings);
  const selectionKey = JSON.stringify([selection.date, selection.slot, servings, targetId, readyOnly, recipeSource, minutes, exclude, prefer]);
  const advice = result?.selectionKey === selectionKey ? result.data : null;
  const current = advice?.revision === revision;
  const conditions = advice?.conditions;
  const label = id => advice?.condition_labels?.[id] || ingredients.find(item => item.id === id)?.name;
  const excluded = (conditions?.excluded_ids || []).map(label).filter(Boolean);
  const required = (conditions?.required_groups || [])
    .map(group => group.map(label).filter(Boolean).join(' 또는 ')).filter(Boolean);
  const coolingDown = retryUntil > Date.now();
  const canRequest = prompt.trim() && selection.date && valid && !coolingDown;
  useEffect(() => {
    if (!retryUntil) return;
    const timer = setTimeout(() => setRetryUntil(0), Math.max(0, retryUntil - Date.now()));
    return () => clearTimeout(timer);
  }, [retryUntil]);

  async function request(event) {
    event.preventDefault();
    if (!canRequest || loading) return;
    setResult(null);
    const data = await onRecommend({user_request: prompt.trim(), target_date: selection.date, target_slot: selection.slot,
      target_meal_id: targetId, servings, ready_only: readyOnly, recipe_source: recipeSource,
      max_minutes: minutes ? Number(minutes) : undefined, exclude: exclude.trim(), prefer: prefer.trim()});
    if (data) setResult({data, selectionKey});
    if (data?.reason_code === 'rate_limited') setRetryUntil(Date.now() + 20000);
  }

  return <Card title="문장으로 메뉴 추천받기">
    <form className="recommendation-form" onSubmit={request} aria-busy={loading}>
      <Field label="추천 조건">
        <input value={prompt} onChange={event => {
          setPrompt(event.target.value);
          setResult(null);
        }} disabled={loading} required maxLength={500} placeholder="예: 달걀과 양파를 활용한 20분 이내 메뉴"/>
      </Field>
      <Button type="submit" disabled={!canRequest || loading}>{loading ? '추천받는 중…' : coolingDown ? '잠시 후 다시 추천' : '추천받기'}</Button>
    </form>
    <p className="muted recommendation-hint">{targetId ? '변경할 식사의 날짜와 인분으로 찾습니다.'
      : '날짜와 인분을 문장에 적으면 추천 결과에 반영돼요.'}</p>
    {advice && !current && <p role="status" className="muted">재고나 메뉴가 업데이트됐어요. 추천을 다시 받아 주세요.</p>}
    {advice && current && <div className="recommendation-result" aria-label="추천 결과">
      <p role="status"><strong>{{
        gpt: 'AI 추천', rules: '기본 추천', needs_input: '조건을 확인해 주세요',
      }[advice.source]}</strong> · {advice.message}</p>
      {conditions && <p className="muted">
        {conditions.target_date} {slotLabels[selection.slot]} · {conditions.servings}인분
        {conditions.max_minutes != null && ' · 최대 ' + conditions.max_minutes + '분'}
        {conditions.ready_only && ' · 있는 재료만'}
        {excluded.length > 0 && ' · 제외 ' + excluded.join(', ')}
        {required.length > 0 && ' · 필수 ' + required.join(' + ')}
      </p>}
      {advice.recommendations.map(item => <section key={item.recipe_id} className="recommendation-menu">
        <div>
          <h3>{item.name}</h3>
          <p className="muted">{item.minutes}분</p>
          <p className={item.missing.length ? 'missing-parts' : 'ready-parts'}>
            {item.missing.length ? '더 필요한 재료 · ' + item.missing.map(missingLabel).join(', ')
              : '이 끼니는 지금 있는 재료로 만들 수 있어요'}
          </p>
        </div>
        {conditions && <Button secondary onClick={() => onChoose(item.recipe_id, {
          date: conditions.target_date, slot: selection.slot, servings: conditions.servings,
          revision: advice.revision,
        })}>추천 메뉴 추가</Button>}
      </section>)}
    </div>}
  </Card>;
}
