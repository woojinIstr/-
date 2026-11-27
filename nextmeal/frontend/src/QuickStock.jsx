import React, {useState} from 'react';
import {Button, Field} from './integrated-ui';
import {unitLabels} from './workspace-client';

const staples = [['달걀', 'count'], ['밥', 'g'], ['삼겹살', 'g'], ['두부', 'g'],
  ['김치', 'g'], ['참치캔', 'g'], ['햇반', 'pack'], ['양파', 'g']];
const units = ['g', 'kg', 'ml', 'L', 'count', 'pack'];
const unitByText = {g:'g', kg:'kg', ml:'ml', l:'L', 그램:'g', 킬로그램:'kg', 밀리리터:'ml', 리터:'L',
  개:'count', 알:'count', 장:'count', 모:'pack', 팩:'pack', 통:'pack', 캔:'pack', 봉:'pack'};
const weightPacks = new Set(['밥', '흰밥', '햇반', '즉석밥', '두부', '참치캔', '캔참치', '스팸']);
const riceNames = new Set(['밥', '흰밥', '햇반', '즉석밥']);
const productKey = name => riceNames.has(normalized(name)) ? '밥' : normalized(name);


export const emptyStockRow = () => ({key: crypto.randomUUID(), name: '', quantity: '', unit: 'g'});
const normalized = name => name.trim().replace(/\s+/g, '').toLowerCase();

function parseStockLine(line) {
  const parts = line.split(/[,，;\n]/).map(part => part.trim()).filter(Boolean);
  if (!parts.length) throw new Error('재료와 수량을 한 가지 이상 입력해 주세요.');
  if (parts.length > 12) throw new Error('한 번에 재료 12개까지 입력할 수 있어요.');
  return parts.map(part => {
    const match = part.match(/^(.*?[^\s+\-\d.])\s*(\d+(?:\.\d+)?)\s*([a-z가-힣]+)(?:\s*[（(]\s*(\d+(?:\.\d+)?)\s*g\s*[)）])?$/i);
    if (!match || !unitByText[match[3].toLowerCase()] || !(Number(match[2]) > 0) ||
        match[1].trim().length > 100 || /\d\s*(?:개|알|모|팩|통|캔|봉|g|ml)\s+/i.test(match[1]))
      throw new Error('‘'+part+'’의 수량 또는 단위를 확인해 주세요. 예: 달걀 2개, 김치 100g');
    const [, name, quantity, label, size] = match;
    let unit = unitByText[label.toLowerCase()];
    if (unit === 'count' && weightPacks.has(normalized(name))) unit = 'pack';
    if (size && (unit !== 'pack' || !(Number(size) > 0)))
      throw new Error('괄호 안에는 1팩당 중량을 적어 주세요. 예: 두부 1모(300g)');
    return {...emptyStockRow(), name:name.trim(), quantity, unit, packLabel:label, packSize:size || ''};
  });
}

export default function QuickStock({rows, onChange, ingredients, products}) {
  const [line,setLine] = useState('');
  const [error,setError] = useState('');
  function review() {
    try {
      const additions = parseStockLine(line);
      const retained = rows.filter(row => row.name.trim() || row.quantity);
      if (retained.length + additions.length > 12) throw new Error('재료는 모두 12개까지 담을 수 있어요.');
      onChange([...retained, ...additions]);
      setLine('');
      setError('');
    } catch (error) {
      setError(error.message);
    }
  }

  const known = new Map(staples.map(([name, unit]) => [normalized(name), unit]));
  known.set('계란', 'count');
  known.set('흰밥', 'g');
  known.set('햇반', 'pack');
  known.set('즉석밥', 'pack');
  for (const item of ingredients) known.set(normalized(item.name), item.unit);
  const choices = [...new Map([...ingredients.map(item => [item.name, item.unit]), ...staples]).entries()].slice(0, 8);

  function change(index, patch) {
    onChange(rows.map((row, i) => i === index ? {...row, ...patch} : row));
  }

  function pick(name, unit) {
    const existing = rows.findIndex(row => normalized(row.name) === normalized(name));
    const empty = rows.findIndex(row => !row.name.trim());
    const index = existing >= 0 ? existing : empty >= 0 ? empty : rows.length;
    if (index === 12) return;
    if (existing < 0) {
      if (index === rows.length) onChange([...rows, {...emptyStockRow(), name, unit}]);
      else change(index, {name, unit});
    }
    window.requestAnimationFrame(() => document.getElementById('quick-quantity-' + index)?.focus());
  }

  return <>
    <div className="form-stack quick-stock-parse">
      <Field label="재료 한 줄 입력">
        <textarea rows="2" maxLength={800} value={line} placeholder="예: 달걀 2개, 김치 100g, 햇반 1개"
          onChange={event=>{setLine(event.target.value);setError('');}}
          onKeyDown={event=>{if((event.ctrlKey || event.metaKey) && event.key==='Enter'){event.preventDefault();if(line.trim())review();}}}/>
      </Field>
      <Button secondary disabled={!line.trim()} onClick={review}>수량 확인하기</Button>
      {error && <p role="alert" className="server-error">{error}</p>}
    </div>
    <div className="quick-stock-picks" aria-label="자주 쓰는 재료">
      {choices.map(([name, unit]) => <Button secondary key={name} onClick={() => pick(name, known.get(normalized(name)) || unit)}>
        {name}
      </Button>)}
    </div>
    <div className="quick-stock-list">
      {rows.map((row, index) => {
        const options = products.filter(product => {
          const ingredient = ingredients.find(item => item.id === product.ingredient_id);
          return ingredient?.unit === 'g' && !product.estimated &&
            productKey(ingredient.canonical_name || ingredient.name) === productKey(row.name);
        });
        return <div className="quick-stock-row" key={row.key}>
        <Field label={'재료 ' + (index + 1)}>
          <input required maxLength={100} placeholder="예: 삼겹살" value={row.name} onChange={event => {
            const name = event.target.value;
            change(index, {name, unit: known.get(normalized(name)) || row.unit, productId:'', packSize:''});
          }}/>
        </Field>
        <Field label={'수량 ' + (index + 1)}>
          <input id={'quick-quantity-' + index} required type="number" inputMode="decimal" min="0.000001"
            max="1000000000" step="any" value={row.quantity} onChange={event => change(index, {quantity: event.target.value})}/>
        </Field>
        <Field label={'단위 ' + (index + 1)}>
          <select value={row.unit} onChange={event => change(index, {unit: event.target.value, productId:'',packSize:''})}>
            {units.map(unit => <option key={unit} value={unit}>{unit === 'pack' ? '포장(모·팩·캔)' : unitLabels[unit]}</option>)}
          </select>
        </Field>
        <Button secondary disabled={rows.length === 1} aria-label={`재료 ${index + 1} 빼기`}
          onClick={() => onChange(rows.filter(item => item.key !== row.key))}>빼기</Button>
        {normalized(row.name) === '참치' && <div className="quick-stock-more toolbar">
          <span>통조림이면 참치캔으로 등록하세요.</span>
          <Button secondary onClick={()=>change(index,{name:'참치캔',productId:''})}>참치캔으로 바꾸기</Button>
        </div>}
        {row.unit === 'pack' && <div className="quick-stock-more form-row">
          {options.length > 0 && <Field label={'저장한 포장 ' + (index + 1)}>
            <select value={row.productId || ''} onChange={event=>change(index,{productId:event.target.value,packSize:''})}>
              <option value="">중량 직접 입력</option>
              {options.map(product=><option key={product.id} value={product.id}>{product.name} · {product.pack_size}g</option>)}
            </select>
          </Field>}
          {!row.productId && <Field label={'포장 1개당 중량 ' + (index + 1) + ' (g)'}>
            <input required type="number" inputMode="decimal" min="0.000001" max="1000000000" step="any"
              value={row.packSize || ''} onChange={event=>change(index,{packSize:event.target.value})}/>
          </Field>}
        </div>}
      </div>;
      })}
    </div>
    {rows.length < 12 && <Button secondary onClick={() => onChange([...rows, emptyStockRow()])}>재료 한 줄 추가</Button>}
    <p className="fineprint">오늘 등록한 냉장 재고로 저장해요. 보관 위치와 소비기한은 냉장고에서 수정할 수 있어요.</p>
  </>;
}
