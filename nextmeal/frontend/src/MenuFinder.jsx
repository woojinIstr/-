import React, {useMemo, useState} from 'react';
import {Button, Card, Field, formatAmount} from './integrated-ui';
import {dateNow, unitLabels, slotLabels} from './workspace-client';
import RecommendationPanel from './RecommendationPanel';

export function nextHomeMeal(meals, date, slot, excludedId) {
  const slots = Object.keys(slotLabels);
  return meals.filter(m => m.status === 'planned' && m.id !== excludedId &&
    (m.date > date || (m.date === date && slots.indexOf(m.slot) > slots.indexOf(slot))))
    .sort((a,b)=>a.date.localeCompare(b.date) || slots.indexOf(a.slot)-slots.indexOf(b.slot) || a.id.localeCompare(b.id))[0];
}

export default function MenuFinder({workspace, onChoose, target, onLeaveTarget, onCreate, selection,
  onSelectionChange, chooseLabel, revision, onRecommend, loading=false}) {
  const [minutes, setMinutes] = useState('30');
  const [exclude, setExclude] = useState('');
  const [prefer, setPrefer] = useState('');
  const today = dateNow();
  const recipes = useMemo(() => {
    const stocks = new Map();
    for (const lot of workspace.inventory) {
      if (lot.archived || lot.quantity<=0 || (lot.expires_on && lot.expires_on<today) || (lot.purchased_on && lot.purchased_on>today)) continue;
      stocks.set(lot.ingredient_id,(stocks.get(lot.ingredient_id) || 0)+lot.quantity);
    }
    const names = new Map(workspace.ingredients.map(i=>[i.id,i.name]));
    const excluded = exclude.split(',').map(s=>s.trim()).filter(Boolean);
    const wanted = prefer.trim();
    return workspace.recipes.filter(r=>!r.archived).flatMap(recipe => {
      let coverage = 0, preferred = false;
      const missing = [];
      for (const part of recipe.ingredients) {
        const name = names.get(part.ingredient_id);
        if (excluded.some(word=>name.includes(word))) return [];
        const need = part.quantity*(target?.servings || selection?.servings || 1)/recipe.base_servings;
        const have = stocks.get(part.ingredient_id) || 0;
        const amount = Number((need-have).toFixed(6));
        if (amount>0) missing.push({name,amount,unit:part.unit});
        if (wanted && name.includes(wanted)) preferred = true;
        coverage += Math.min(1,have/need);
      }
      return [{recipe,preferred,coverage:coverage/recipe.ingredients.length,missing}];
    }).sort((a,b)=>Number(b.preferred)-Number(a.preferred) || b.coverage-a.coverage);
  }, [workspace, today, exclude, prefer, target?.servings, selection?.servings]);
  const available = recipes.filter(({recipe})=>!minutes || recipe.minutes<=Number(minutes));
  const shortest = recipes.reduce((min,{recipe})=>Math.min(min,recipe.minutes),Infinity);
  return <>
    <div className="page-head"><div><h1>재고로 메뉴 찾기</h1><p>메뉴를 골라 한 끼를 계획하고 더 필요한 재료를 확인하세요.</p></div></div>
    {target && <div className="finder-context">
      <strong>{target.date} {slotLabels[target.slot]} · {target.recipe.name} 변경</strong>
      <button type="button" className="text-btn" onClick={onLeaveTarget}>새 식사로 찾기</button>
    </div>}
    {selection&&!target&&<div className="selection-context" role="group" aria-label="계획할 식사">
      <Field label="식사 날짜"><input required type="date" value={selection.date} onChange={e=>e.target.value&&onSelectionChange({...selection,date:e.target.value})}/></Field>
      <Field label="식사 시간"><select value={selection.slot} onChange={e=>onSelectionChange({...selection,slot:e.target.value})}>
        {Object.entries(slotLabels).map(([value,label])=><option key={value} value={value}>{label}</option>)}
      </select></Field>
      <Field label="먹을 인분"><input type="number" min="0.1" max="12" step="any" value={selection.servings}
        onChange={e=>onSelectionChange({...selection,servings:e.target.value})}/></Field>
    </div>}
    {onRecommend && selection && !target && <RecommendationPanel selection={selection} revision={revision}
      ingredients={workspace.ingredients} onRecommend={onRecommend} onChoose={onChoose} loading={loading}/>}
    <div className="toolbar">
      <Field label="최대 조리 시간(분)"><input type="number" min="1" max="1440" value={minutes} onChange={e=>setMinutes(e.target.value)}/></Field>
      <Field label="제외 재료(쉼표 구분)"><input value={exclude} onChange={e=>setExclude(e.target.value)}/></Field>
      <Field label="우선 사용할 재료"><input value={prefer} onChange={e=>setPrefer(e.target.value)}/></Field>
    </div>
    {!available.length && <Card title="조건에 맞는 메뉴가 없어요">
      {Number.isFinite(shortest) ? <Button secondary onClick={()=>setMinutes(String(shortest))}>{shortest}분으로 늘리기</Button>
        : exclude.trim() ? <Button secondary onClick={()=>setExclude('')}>제외 재료 지우기</Button>
        : onCreate&&<Button secondary onClick={onCreate}>메뉴 추가</Button>}
    </Card>}
    <div className="two-cols finder-results">{available.map(({recipe,missing})=><Card key={recipe.id} title={recipe.name}>
      <p className="muted">{recipe.minutes}분 · {target?.servings || selection?.servings || 1}인분 기준</p>
      <p className={missing.length ? 'missing-parts' : 'ready-parts'}>{missing.length
        ? '더 필요한 재료 · '+missing.map(i=>i.name+' '+formatAmount(i.amount)+unitLabels[i.unit]).join(', ')
        : '지금 있는 재료로 만들 수 있어요'}</p>
      <Button disabled={Boolean(selection)&&(!Number(selection.servings)||Number(selection.servings)<0.1||Number(selection.servings)>12)}
        onClick={()=>onChoose(recipe.id)}>{chooseLabel || (target ? '이 메뉴로 변경' : '식사에 추가')}</Button>
    </Card>)}</div>
  </>;
}
