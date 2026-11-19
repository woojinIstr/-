import React, {useMemo, useState} from 'react';
import {recipes as examples, initialInventory} from './data';
import {Button, Modal, formatAmount} from './integrated-ui';
import MenuFinder from './MenuFinder';

const names = [...new Set(examples.flatMap(recipe=>recipe.ingredients.map(part=>part.name)))];
const samples = names.map(name=>{
  const parts=examples.flatMap(recipe=>recipe.ingredients).filter(part=>part.name===name);
  const amount=initialInventory.filter(item=>item.name===name).reduce((sum,item)=>sum+item.quantity,0);
  return {name,quantity:amount || Math.max(...parts.map(part=>part.quantity)),unit:parts[0].unit};
});

export default function QuickTry({onClose}) {
  const [selected,setSelected]=useState(['밥','우유','양파']);
  const [chosen,setChosen]=useState('');
  const workspace=useMemo(()=>({
    ingredients:samples.map(item=>({id:item.name,name:item.name,unit:item.unit==='mL'?'ml':item.unit})),
    inventory:samples.filter(item=>selected.includes(item.name)).map(item=>({
      ingredient_id:item.name,quantity:item.quantity,unit:item.unit==='mL'?'ml':item.unit
    })),
    recipes:examples.map(recipe=>({...recipe,base_servings:1,ingredients:recipe.ingredients.map(part=>({
      ingredient_id:part.name,quantity:part.quantity,unit:part.unit==='mL'?'ml':part.unit
    }))}))
  }),[selected]);
  function toggle(name) {
    setChosen('');
    setSelected(current=>current.includes(name)?current.filter(item=>item!==name):[...current,name]);
  }
  return <Modal title="샘플 냉장고로 체험하기" onClose={onClose}
    footer={<Button onClick={onClose}>내 계정으로 시작하기</Button>}>
    <p className="muted">예시 수량의 재료를 골라 메뉴와 부족량이 어떻게 달라지는지 확인하세요.</p>
    <div className="sample-ingredients">{samples.map(item=><label key={item.name} className="sample-choice">
      <input type="checkbox" checked={selected.includes(item.name)} onChange={()=>toggle(item.name)}/>
      <span>{item.name}<small>{formatAmount(item.quantity)}{item.unit}</small></span>
    </label>)}</div>
    {chosen&&<p role="status" className="tip">{chosen} 선택 · 내 식사에 저장하려면 계정으로 로그인하세요.</p>}
    <MenuFinder workspace={workspace} onChoose={id=>setChosen(examples.find(recipe=>recipe.id===id).name)} chooseLabel="이 메뉴 선택"/>
  </Modal>;
}
