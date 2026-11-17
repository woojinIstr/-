import React from 'react';
import {Field, Options, formatAmount} from './integrated-ui';
import {dateNow, storageLabels, unitLabels} from './workspace-client';

const measuredUnits = {g: ['g', 'kg'], ml: ['ml', 'L'], count: ['count']};
const knownUnits = {g:'g', kg:'kg', ml:'ml', l:'L', '그램':'g', '킬로그램':'kg', '밀리리터':'ml', '리터':'L', '개':'count', count:'count'};
const baseOf = {g:'g', kg:'g', ml:'ml', L:'ml', count:'count'};
const individualCounts = new Set(['모', '알', '마리', '장']);
const baseLabels = {count:'개수로 관리', g:'무게(g)로 관리', ml:'부피(mL)로 관리'};
const keyOf = name => name.trim().replace(/ /g, '').toLowerCase();
const canonical = label => knownUnits[label?.trim().toLowerCase()] || null;

function purchaseUnits(sourceUnit, base) {
  const unit = canonical(sourceUnit);
  if (!sourceUnit) return {input_unit:base, content_unit:base, pack_size:'', pack_label:'팩', inferredPack:false};
  if (unit && baseOf[unit] === base)
    return {input_unit:unit, content_unit:base, pack_size:'', pack_label:'팩', inferredPack:false};
  // Known mass/volume cannot be treated as an unspecified package size.
  if (unit && unit !== 'count')
    return {input_unit:'', content_unit:base, pack_size:'', pack_label:'팩', inferredPack:false};
  const counted = base === 'count' && individualCounts.has(sourceUnit.trim());
  return {input_unit:'pack', content_unit:base, pack_label:sourceUnit, pack_size:counted ? 1 : '', inferredPack:counted};
}

export function purchaseDraft(workspace, {ingredientId, lot, manual, shortage}={}) {
  const matched = manual && workspace.ingredients.find(i => keyOf(i.name) === keyOf(manual.name));
  const ingredient = workspace.ingredients.find(i => i.id === (ingredientId || lot?.ingredient_id)) || matched;
  const newBase = baseOf[canonical(manual?.unit)] || 'count';
  const base = ingredient?.unit || newBase;
  const sourceUnit = manual?.unit || (shortage && unitLabels[shortage.unit]) || '';
  const units = purchaseUnits(sourceUnit, base);
  return {
    kind:'lot', id:lot?.id || null, ingredient_id:ingredient?.id || (manual ? 'new' : ''),
    new_name:manual?.name || '', new_base:newBase, sourceUnit,
    sourceLabel:manual ? manual.name+' '+formatAmount(manual.quantity)+manual.unit :
      shortage ? shortage.name+' '+formatAmount(shortage.shortage)+unitLabels[shortage.unit]+' 부족' : '',
    manual_id:manual?.id || null, original:lot, product_id:'', name:lot?.name || '',
    input_quantity:lot ? lot.quantity/(lot.pack_size || 1) : (units.input_unit ? (manual?.quantity ?? shortage?.shortage ?? '') : ''),
    save_product:true, estimated:lot?.estimated || false, storage:lot?.storage || 'fridge',
    purchased_on:lot?.purchased_on || dateNow(), expires_on:lot?.expires_on || '', opened_on:lot?.opened_on || '',
    ...units,
    ...(lot && {input_unit:lot.pack_size ? 'pack' : lot.unit, pack_size:lot.pack_size || '', pack_label:lot.pack_label || '팩'})
  };
}

export function purchaseCommand(form) {
  const dates = {purchased_on:form.purchased_on, expires_on:form.expires_on || null, opened_on:form.opened_on || null};
  const common = {name:form.name.trim(), storage:form.storage, ...dates};
  if (form.id) return {action:'lot.patch', payload:{...common, id:form.id, quantity:Number(form.input_quantity)*(form.original.pack_size || 1)}};
  const reference = form.ingredient_id === 'new'
    ? {new_ingredient:{name:form.new_name.trim(), unit:form.new_base}}
    : {ingredient_id:form.ingredient_id};
  return {action:'lot.create', payload:{
    ...common, ...reference, product_id:form.product_id || null, manual_id:form.manual_id,
    input_quantity:Number(form.input_quantity), input_unit:form.input_unit, content_unit:form.content_unit,
    pack_size:form.input_unit === 'pack' ? Number(form.pack_size) : null, pack_label:form.pack_label,
    save_product:form.input_unit === 'pack' && form.save_product, estimated:form.input_unit === 'pack' && form.estimated
  }};
}

export function PurchaseFields({form, setForm, workspace}) {
  const selected = workspace.ingredients.find(i => i.id === form.ingredient_id);
  const isNew = form.ingredient_id === 'new';
  const base = selected?.unit || form.new_base;
  const products = workspace.products.filter(p => p.ingredient_id === selected?.id);
  const hasIngredient = Boolean(selected || isNew);
  const packed = !form.id && hasIngredient && form.input_unit === 'pack';
  const simpleCount = packed && form.inferredPack;
  const change = fields => setForm(previous => ({...previous, ...fields}));
  function quantityFor(unit, label=form.pack_label) {
    return form.input_unit===unit && (unit!=='pack' || form.pack_label===label) ? form.input_quantity : '';
  }
  function selectIngredient(id, newBase=form.new_base) {
    const unit = workspace.ingredients.find(i => i.id === id)?.unit || newBase;
    const units = purchaseUnits(form.sourceUnit, unit);
    change({ingredient_id:id, new_base:newBase, product_id:'', name:'', estimated:false,
      input_quantity:quantityFor(units.input_unit,units.pack_label), ...units});
  }
  function pickProduct(id) {
    const p = products.find(product => product.id === id);
    if (!p) {
      const units=purchaseUnits(form.sourceUnit,base);
      change({product_id:'', name:'', estimated:false, input_quantity:quantityFor(units.input_unit,units.pack_label), ...units});
      return;
    }
    change({product_id:id, name:p.name, input_unit:'pack', pack_label:p.pack_label, pack_size:p.pack_size,
      input_quantity:quantityFor('pack',p.pack_label),content_unit:base, estimated:p.estimated, inferredPack:false});
  }
  function field(key, type='text', props={}) {
    return <input {...props} type={type} value={form[key]} onChange={e=>change({[key]:e.target.value})}/>;
  }
  const count = Number(form.input_quantity);
  const converted = count*Number(form.pack_size)*(['kg','L'].includes(form.content_unit) ? 1000 : 1);
  return <>
    {form.sourceLabel && <p className="purchase-source">장보기 · {form.sourceLabel}</p>}
    <Field label="재료"><select value={form.ingredient_id} required disabled={Boolean(form.id)} onChange={e=>selectIngredient(e.target.value)}>
      <option value="" disabled>재료 선택</option>
      <option value="new">{form.manual_id && form.new_name ? form.new_name+' 새 재료로 등록' : '새 재료 직접 등록'}</option>
      {workspace.ingredients.map(i=><option key={i.id} value={i.id}>{i.name} ({unitLabels[i.unit]})</option>)}
    </select></Field>
    {isNew && <div className="form-row">
      <Field label="새 재료 이름">{field('new_name','text',{required:true,maxLength:100})}</Field>
      <Field label="기준 단위"><select value={base} onChange={e=>selectIngredient('new', e.target.value)}><Options map={baseLabels}/></select></Field>
    </div>}
    {hasIngredient && <>
      {products.length > 0 && !form.id && <Field label="저장한 제품"><select value={form.product_id} onChange={e=>pickProduct(e.target.value)}>
        <option value="">직접 입력</option>
        {products.map(p=><option key={p.id} value={p.id}>{p.name} · 1{p.pack_label}당 {formatAmount(p.pack_size)}{unitLabels[base]}</option>)}
      </select></Field>}
      <div className="form-row">
        <Field label={form.id ? '남은 수량' : '구입 수량'}>{field('input_quantity','number',{required:true,min:form.id?0:0.000001,max:1e9,step:'any'})}</Field>
        <Field label="입력 단위">{form.id
          ? <input disabled value={form.original.pack_size ? form.original.pack_label : unitLabels[base]}/>
          : <select required disabled={Boolean(form.product_id)} value={form.input_unit} onChange={e=>{
            const value=e.target.value;
            change({input_unit:value, input_quantity:quantityFor(value), inferredPack:value==='pack' && form.inferredPack});
          }}>
            <option value="" disabled>단위 선택</option>
            {measuredUnits[base].map(unit=><option key={unit} value={unit}>{unitLabels[unit]}</option>)}
            <option value="pack">{form.sourceUnit && form.input_unit==='pack' ? form.pack_label+' 단위' : '팩·병 등 포장 단위'}</option>
          </select>}
        </Field>
      </div>
      {form.sourceUnit && !form.input_unit && <p className="fineprint">구입한 수량을 선택한 재료의 단위로 확인해 주세요.</p>}
      {simpleCount && <div className="count-note"><span>1{form.pack_label}를 재고 1개로 기록해요.</span>
        <button className="text-btn" type="button" onClick={()=>change({inferredPack:false,pack_size:''})}>포장당 개수 변경</button></div>}
      {packed && !simpleCount && <div className="form-row pack-fields">
        <Field label="포장 단위 이름">{field('pack_label','text',{required:true,maxLength:20,disabled:Boolean(form.product_id)})}</Field>
        <Field label="포장 1단위당 내용량">{field('pack_size','number',{required:true,min:0.000001,step:'any',disabled:Boolean(form.product_id)})}</Field>
        <Field label="내용량 단위"><select value={form.content_unit} disabled={Boolean(form.product_id)} onChange={e=>change({content_unit:e.target.value})}>
          {measuredUnits[base].map(unit=><option key={unit} value={unit}>{unitLabels[unit]}</option>)}
        </select></Field>
      </div>}
      {packed && count>0 && converted>0 && <p className="tip">{formatAmount(count)}{form.pack_label} × {formatAmount(form.pack_size)}{unitLabels[form.content_unit]} = {formatAmount(converted)}{unitLabels[base]}</p>}
      <details className="purchase-details" open={form.detailsOpen || undefined} onToggle={e=>{
        const open=e.currentTarget.open;
        if(open !== Boolean(form.detailsOpen)) change({detailsOpen:open});
      }}>
        <summary>상세 정보 · {storageLabels[form.storage]}</summary>
        <div className="form-stack">
          <Field label="보관 위치"><select value={form.storage} onChange={e=>change({storage:e.target.value})}><Options map={storageLabels}/></select></Field>
          <Field label="제품명·구분 메모">{field('name','text',{maxLength:100,placeholder:'제품명이나 구분할 내용을 입력하세요'})}</Field>
          <div className="form-row">
            <Field label="구매일">{field('purchased_on','date',{required:true,max:dateNow()})}</Field>
            <Field label="소비기한(선택)">{field('expires_on','date',{min:form.purchased_on})}</Field>
            <Field label="개봉일(선택)">{field('opened_on','date',{min:form.purchased_on,max:dateNow()})}</Field>
          </div>
          {packed && !form.product_id && <>
            <label className="check-row"><input type="checkbox" checked={form.save_product} onChange={e=>change({save_product:e.target.checked})}/>이 제품의 내용량을 다음에도 사용</label>
            <label className="check-row"><input type="checkbox" checked={form.estimated} onChange={e=>change({estimated:e.target.checked})}/>직접 정한 추정 내용량입니다</label>
          </>}
        </div>
      </details>
    </>}
  </>;
}
