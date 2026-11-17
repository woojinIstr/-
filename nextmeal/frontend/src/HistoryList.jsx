import React from 'react';
import {Button,Card} from './integrated-ui';

export default function HistoryList({history,onUndo}) {
 return <Card title="최근 변경 이력 · 최대 500건">
  <p className="muted">조리·사용·폐기를 잘못 기록했다면 여기서 되돌릴 수 있어요. 차감된 구매분으로 수량이 돌아가며, 조리한 식사는 예정으로 바뀌어요.</p>
  {history.map(h=><article className="history-row history-entry" key={h.id} aria-label={h.summary}>
   <div><b>{h.summary}</b><p>{new Date(h.at).toLocaleString('ko-KR')}</p>
    {h.undone_at ? <p className="chip">되돌림 완료</p> : ['lot.use','meal.cook'].includes(h.action)&&
     (h.can_undo ? <Button secondary onClick={()=>onUndo(h.id)}>기록 되돌리기</Button> :
      <p className="fineprint">{h.undo_reason||'이전 버전의 기록이라 자동으로 되돌릴 수 없어요. 재고를 확인해 정정해 주세요.'}</p>)}
   </div>
  </article>)}
  {!history.length&&<p className="muted">아직 기록이 없습니다.</p>}
  <p className="fineprint">이후 같은 재고를 변경했다면 더 최근 기록부터 되돌리세요. 정정·숨김 등으로 변경한 재고는 자동 복원하지 않습니다. 소비기한은 바뀌지 않아요. 외식·취소는 식사 계획에서 복원할 수 있습니다.</p>
 </Card>;
}
