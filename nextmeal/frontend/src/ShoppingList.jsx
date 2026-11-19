import React from 'react';
import {Button, Card, formatAmount} from './integrated-ui';
import {dateNow, unitLabels} from './workspace-client';

export default function ShoppingList({workspace,shopping,onAdd,onPurchase,onArchive,onRestore,onPlan}) {
  const active=workspace.manual.filter(item=>!item.archived);
  const received=active.filter(item=>item.received_lot_id);
  const pending=active.filter(item=>!item.received_lot_id);
  const planned=workspace.meals.filter(meal=>meal.status==='planned'&&meal.date>=dateNow());
  function row(item) {
    return <div className="shop-row" key={item.id}>
      <div><b>{item.name} {formatAmount(item.quantity)}{item.unit}</b>
        {item.checked&&<small>이전 구매 체크 · 재고 반영 확인 필요</small>}
      </div>
      <Button onClick={()=>onPurchase(null,null,item.id)}>구매 완료</Button>
      <Button secondary onClick={()=>onArchive(item.id)}>목록에서 빼기</Button>
    </div>;
  }
  return <>
    <div className="page-head"><div><h1>장보기 목록</h1><p>구입한 항목은 ‘구매 완료’에서 실제 수량을 확인하면 냉장고에 함께 반영돼요.</p></div>
      <Button onClick={onAdd}>직접 추가</Button>
    </div>
    <Card title="식사에 필요한 재료">
      {shopping.map(item=><div className="shop-row" key={item.ingredient_id}>
        <div><b>{item.name}</b><small>{formatAmount(item.shortage)}{unitLabels[item.unit]} 부족</small></div>
        <Button onClick={()=>onPurchase(item.ingredient_id,null,null,item)}>구매 완료</Button>
      </div>)}
      {!shopping.length&&(planned.length
        ? <p className="muted">예정한 식사에 필요한 재료가 모두 있어요.</p>
        : <div className="empty-action"><p>예정한 식사가 없어요. 메뉴를 고르면 더 필요한 재료를 알려드려요.</p><Button secondary onClick={onPlan}>한 끼 고르기</Button></div>)}
    </Card>
    <Card title="직접 적은 장보기">
      {pending.map(row)}
      {!pending.length&&<p className="muted">직접 추가한 구매 예정 품목이 없어요.</p>}
    </Card>
    {received.length>0&&<Card title="구매 완료 · 냉장고 반영됨">
      {received.map(item=><div className="shop-row" key={item.id}>
        <span>{item.name} <small>재고 반영 완료</small></span>
        <Button secondary onClick={()=>onArchive(item.id)}>목록에서 빼기</Button>
      </div>)}
    </Card>}
    <details><summary>목록에서 뺀 항목</summary>
      {workspace.manual.filter(item=>item.archived).map(item=><div className="shop-row" key={item.id}><span>{item.name}</span>
        <Button secondary onClick={()=>onRestore(item.id)}>복원</Button></div>)}
    </details>
  </>;
}
