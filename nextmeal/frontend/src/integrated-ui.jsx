import React, {useLayoutEffect, useRef} from 'react';
import {X} from 'lucide-react';
import {unitLabels,statusLabels} from './workspace-client';

export const formatAmount = value => Number(value).toLocaleString('ko-KR', {maximumFractionDigits: 6});

export function Button({children, secondary=false, ...props}) {
  return <button type="button" className={secondary ? 'btn btn-secondary' : 'btn'} {...props}>{children}</button>;
}

export function Field({label, children}) {
  return <label className="field"><span>{label}</span>{children}</label>;
}

export function Card({title, action, children}) {
  return <section className="card"><div className="card-heading"><h2>{title}</h2>{action}</div>{children}</section>;
}

export function Options({map}) {
  return Object.entries(map).map(([value, label]) => <option key={value} value={value}>{label}</option>);
}

export function Modal({title, busy, onClose, children, footer}) {
  const panel = useRef(null);
  const onDismiss = useRef(onClose);
  onDismiss.current = busy ? null : onClose;

  useLayoutEffect(() => {
    const dialog = panel.current;
    const opener = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    const overlay = dialog.closest('.overlay');
    const background = [...overlay.parentElement.children].filter(el => el !== overlay);
    const previouslyInert = background.map(el => el.inert);
    background.forEach(el => { el.inert = true; });
    document.body.style.overflow = 'hidden';

    function visibleControls() {
      return [...dialog.querySelectorAll('button, input, select, textarea, summary, a[href]')].filter(el => {
        const closed = el.closest('details:not([open])');
        return !el.matches(':disabled') && !el.hidden && (!closed || closed.querySelector('summary') === el);
      });
    }
    const firstField = visibleControls().find(el => el.matches('input,select,textarea'));
    (firstField || dialog).focus({preventScroll: true});

    function handleKey(event) {
      if (event.key === 'Escape') {
        event.preventDefault();
        onDismiss.current?.();
      } else if (event.key === 'Tab') {
        const controls = visibleControls();
        const boundary = event.shiftKey ? controls[0] : controls.at(-1);
        if (document.activeElement === boundary || !controls.includes(document.activeElement)) {
          event.preventDefault();
          (event.shiftKey ? controls.at(-1) : controls[0])?.focus();
        }
      }
    }
    document.addEventListener('keydown', handleKey);
    return () => {
      document.removeEventListener('keydown', handleKey);
      background.forEach((el, index) => { el.inert = previouslyInert[index]; });
      document.body.style.overflow = previousOverflow;
      if (opener?.isConnected) opener.focus({preventScroll: true});
    };
  }, []);

  return <div className="overlay">
    <section ref={panel} tabIndex={-1} role="dialog" aria-modal="true" aria-label={title} className="modal integrated-modal">
      <div className="modal-top">
        <h2>{title}</h2>
        {onClose && <button type="button" className="icon-btn" aria-label="닫기" onClick={onClose} disabled={busy}><X/></button>}
      </div>
      <div className="dialog-scroll">{children}</div>
      <div className="modal-actions dialog-footer">{footer}</div>
    </section>
  </div>;
}

export function ChangeSummary({preview}) {
  const previous = preview.before_shopping || [];
  const next = preview.after_shopping || [];
  const changes = new Map(previous.map(row => [row.ingredient_id, {...row, before: row.shortage, after: 0}]));
  for (const row of next) {
    const before = changes.get(row.ingredient_id)?.before || 0;
    changes.set(row.ingredient_id, {...row, before, after: row.shortage});
  }
  const groups = [
    ['재고', preview.inventory_changes || []],
    ['장보기', [...changes.values()].filter(row => row.before !== row.after)]
  ];
  return <div className="change-summary">{groups.map(([label, rows]) =>
    <section key={label}>
      {rows.length ? <>
        <h3>{label} 변화</h3>
        <ul>{rows.map(row => <li key={row.ingredient_id}>
          <b>{row.name}</b>
          <span>{formatAmount(row.before)}{unitLabels[row.unit]} → <strong>{formatAmount(row.after)}{unitLabels[row.unit]}</strong></span>
        </li>)}</ul>
      </> : <p>{label} 변동 없음</p>}
    </section>
  )}{Boolean(preview.meal_changes?.length)&&<section><h3>식사 상태 변화</h3><ul>{preview.meal_changes.map(row=>
    <li key={row.id}><b>{row.date} {row.name}</b><span>{statusLabels[row.before]} → <strong>{statusLabels[row.after]}</strong></span></li>
  )}</ul></section>}</div>;
}
