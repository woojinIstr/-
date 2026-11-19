import React, {useMemo, useRef, useState} from 'react';
import {ChefHat, House, Refrigerator, CalendarDays, Sparkles, ShoppingBasket, Menu, X} from 'lucide-react';
import {createMealApi, inventoryToView, recipeToView, mealToView, mealCreateBody} from './frontend-api';
import {createSession} from './server-session';
import {fmtQty} from './data';

const today = () => new Date().toLocaleDateString('sv-SE');
const tabs = [['home','홈',House],['inventory','식재료',Refrigerator],['meals','식사 계획',CalendarDays],['recipes','메뉴',ChefHat],['recommend','AI 추천',Sparkles],['shopping','장보기 목록',ShoppingBasket]];
const units = {g:'g', ml:'mL', count:'개'};
const status = {planned:'예정', eaten_out:'외식', skipped:'취소'};
function Button({children, secondary, ...props}) { return <button className={`btn ${secondary?'btn-secondary':''}`} {...props}>{children}</button>; }
function Field({label, children}) { return <label className="field"><span>{label}</span>{children}</label>; }
function Card({title, children}) { return <section className="card"><div className="card-heading"><h2>{title}</h2></div>{children}</section>; }

export default function ServerApp() {
  const config = useMemo(() => ({url:import.meta.env.VITE_SUPABASE_URL || '', key:import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY || '', api:import.meta.env.VITE_API_BASE_URL || ''}), []);
  const configured = config.url.startsWith('https://') && !config.url.includes('YOUR_PROJECT') && config.key && !config.key.includes('YOUR_KEY') && config.api;
  const auth = useMemo(() => createSession(config.url, config.key), [config]);
  const api = useMemo(() => createMealApi(config.api, () => auth.accessToken()), [auth, config]);
  const [user,setUser] = useState(null), [page,setPage] = useState('home'), [sidebar,setSidebar] = useState(false);
  const [busy,setBusy] = useState(false), [ready,setReady] = useState(false), [message,setMessage] = useState(''), [error,setError] = useState('');
  const [data,setData] = useState({ingredients:[],recipes:[],inventory:[],meals:[]});
  const [email,setEmail] = useState(''), [password,setPassword] = useState('');
  const [form,setForm] = useState(null), [pending,setPending] = useState(null), [date,setDate] = useState(today());
  const lock = useRef(false);
  const recipes = data.recipes.map(r => recipeToView(r,data.ingredients));
  const inventory = data.inventory.map(i => inventoryToView(i,data.ingredients));
  const meals = data.meals.map(m => mealToView(m,data.recipes));

  async function load() {
    const [ingredients,recipes,inventory,meals] = await Promise.all([api.ingredients(),api.recipes(),api.inventory(),api.meals()]);
    // Validate a complete response before replacing the screen's previous snapshot.
    recipes.forEach(r => recipeToView(r,ingredients));
    inventory.forEach(i => inventoryToView(i,ingredients));
    meals.forEach(m => mealToView(m,recipes));
    setData({ingredients,recipes,inventory,meals}); setReady(true);
  }
  async function run(action) {
    if (lock.current) return;
    lock.current=true; setBusy(true); setError(''); setMessage('');
    try { await action(); }
    catch(e) { setError(e.status===409?'식사 상태가 이미 변경되었습니다. 새로고침 후 다시 확인하세요.' : e.status===401?'로그인을 확인할 수 없습니다. 로그아웃 후 다시 로그인하세요.' : e.status===422?'입력값이 올바르지 않습니다. 수량·날짜·선택한 항목을 확인하세요.' : e.message || '서버에 연결할 수 없습니다.'); }
    finally {lock.current=false;setBusy(false);}
  }
  function logout() {auth.clear();setUser(null);setReady(false);setData({ingredients:[],recipes:[],inventory:[],meals:[]});setForm(null);setPending(null);setPassword('');setError('');setMessage('');}
  function login(e) {e.preventDefault();run(async()=>{const result=await auth.signIn(email,password);setPassword('');setUser(result || {email});setPage('home');await load();});}
  function openItem(item) {setForm({kind:'inventory',id:item?.id,ingredient_id:item?.ingredientId || data.ingredients[0]?.ingredient_id || '',quantity:item?.quantity ?? '',storage_location:({냉장:'fridge',냉동:'freezer',실온:'pantry'})[item?.storage] || 'fridge'});}
  function saveItem(e) {e.preventDefault();run(async()=>{
    const ingredient=data.ingredients.find(i=>i.ingredient_id===form.ingredient_id);
    const quantity=Number(form.quantity);
    if(!ingredient || form.quantity==='' || !Number.isFinite(quantity) || quantity<0) throw new Error('재료와 0 이상의 수량을 입력하세요.');
    const body={quantity,storage_location:form.storage_location};
    if(form.id) await api.patchInventory(form.id,body);
    else await api.createInventory({...body,ingredient_id:ingredient.ingredient_id,unit:ingredient.unit});
    setForm(null);setReady(false);setMessage('저장했습니다.');await load();
  });}
  function openMeal(meal) {setForm({kind:'meal',id:meal?.id,version:meal?.version,date:meal?.date || date,slot:meal?.slot || '저녁',recipeId:meal?.recipeId || recipes[0]?.id || '',servings:meal?.servings || 1});}
  function reviewMeal(e) {e.preventDefault();setPending({kind:form.id?'edit':'create',form:{...form},label:form.id?'식사 계획 수정':'새 식사 등록'});setForm(null);}
  function approve() {run(async()=>{
    const action=pending;
    if(action.kind==='create') {
      // Never repeat a creation automatically: a lost response could still mean success.
      setPending(null);
      try {await api.createMeal(mealCreateBody(action.form));}
      catch(e) {if(!e.status) throw new Error('등록 결과를 확인할 수 없습니다. 새로고침하여 식사 목록을 확인한 뒤 다시 시도하세요.');throw e;}
    } else if(action.kind==='edit') {
      await api.patchMeal(action.form.id,action.form.version,mealCreateBody(action.form));
    } else if(action.kind==='out') await api.eatOut(action.meal.id,action.meal.version);
    else await api.cancelMeal(action.meal.id,action.meal.version);
    setPending(null);setReady(false);setMessage('변경을 저장했습니다.');await load();
  });}
  function removeItem(item) {if(window.confirm(`${item.name} 재고를 삭제할까요?`)) run(async()=>{await api.deleteInventory(item.id);setReady(false);setMessage('삭제했습니다.');await load();});}
  const update = (key,value) => setForm(f=>({...f,[key]:value}));

  if(!user) return <main className="server-login"><Card title="다음한끼 로그인"><p className="muted">실제 서버에 저장된 내 재료와 식사 계획을 확인하세요.</p>{!configured?<div role="alert" className="server-error">설정이 필요합니다. .env.example을 .env로 복사하고 API 주소와 Supabase 프로젝트 URL·Publishable key를 입력한 뒤 개발 서버를 다시 실행하세요.</div>:<form className="form-stack" onSubmit={login}><Field label="이메일"><input type="email" autoComplete="username" required value={email} onChange={e=>setEmail(e.target.value)} /></Field><Field label="비밀번호"><input type="password" autoComplete="current-password" required value={password} onChange={e=>setPassword(e.target.value)} /></Field><Button disabled={busy}>{busy?'로그인 중…':'로그인'}</Button></form>}{error&&<p role="alert" className="server-error">{error}</p>}<p className="fineprint">기존 Supabase 테스트 계정으로 로그인하세요. 새로고침하거나 탭을 닫으면 다시 로그인해야 합니다.</p></Card></main>;

  return <div className="app">
    <aside className={`sidebar ${sidebar?'open':''}`}><div className="brand"><span className="brand-icon"><ChefHat/></span><div><strong>다음한끼</strong><small>내 식재료로 이어가는 집밥</small></div></div><nav>{tabs.map(([key,label,Icon])=><button key={key} className={`nav-item ${page===key?'active':''}`} onClick={()=>{setPage(key);setSidebar(false);}}><Icon size={19}/>{label}</button>)}</nav><div className="sidebar-foot"><div className="demo-mark">실제 서버 연결 모드</div><p>변경 내용은 내 계정에 저장됩니다.</p></div></aside>
    {sidebar&&<button className="mobile-shade" aria-label="메뉴 닫기" onClick={()=>setSidebar(false)}/>}
    <main className="main"><header className="topbar"><button className="menu-toggle" aria-label="메뉴 열기" onClick={()=>setSidebar(true)}><Menu/></button><div className="crumb">다음한끼 / {tabs.find(t=>t[0]===page)?.[1]}</div><Button secondary disabled={busy} onClick={logout}>로그아웃</Button></header><div className="content">
      <div className="server-session"><span>{user.email || email}</span><Button secondary disabled={busy} onClick={()=>run(load)}>{busy?'처리 중…':'서버 새로고침'}</Button></div>
      {error&&<div role="alert" className="server-error">{error}</div>}{message&&<p role="status" className="tip">{message}</p>}
      {!ready&&<p className="tip">서버 데이터를 확인해야 합니다. 새로고침이 성공하면 편집할 수 있습니다.</p>}
      <fieldset className="server-workspace" disabled={busy || !ready}>
      {page==='home'&&<><div className="page-head"><div><div className="eyebrow">MY KITCHEN</div><h1>오늘도, 다음한끼를 준비해요</h1><p>내 계정의 식재료와 식사 계획을 관리하세요.</p></div><span className="chip">서버 연결</span></div><div className="stats">{[['보유 재고',inventory.length],['오늘 예정 식사',meals.filter(m=>m.date===today()&&m.status==='planned').length],['등록 메뉴',recipes.length]].map(([title,n])=><div className="stat" key={title}><div>{title}</div><strong>{n}<small>건</small></strong></div>)}</div><Card title="오늘의 식사">{meals.filter(m=>m.date===today()).map(m=><div className="meal-mini" key={m.id}><span>{m.slot}</span><strong>{m.name} · {m.servings}인분</strong><span className="chip">{status[m.status]}</span></div>)}{!meals.some(m=>m.date===today())&&<p className="muted">오늘 등록된 식사가 없습니다.</p>}</Card></>}
      {page==='inventory'&&<><div className="page-head"><div><h1>내 냉장고</h1><p>공통 재료 목록에서 선택해 재고를 등록하세요.</p></div><Button disabled={!data.ingredients.length} onClick={()=>openItem()}>식재료 추가</Button></div><Card title="보유 식재료"><div className="table-wrap"><table><thead><tr><th>재료</th><th>수량</th><th>보관 위치</th><th>관리</th></tr></thead><tbody>{inventory.map(i=><tr key={i.id}><td>{i.name}</td><td>{fmtQty(i.quantity)} {i.unit}</td><td>{i.storage}</td><td><div className="row-actions"><button onClick={()=>openItem(i)}>수정</button><button onClick={()=>removeItem(i)}>삭제</button></div></td></tr>)}</tbody></table></div>{!inventory.length&&<p className="empty">등록된 재고가 없습니다.</p>}</Card></>}
      {page==='recipes'&&<><div className="page-head"><div><h1>메뉴 목록</h1><p>서버에 등록된 메뉴와 1인분 기준 재료입니다.</p></div></div><div className="two-cols">{recipes.map(r=><Card key={r.id} title={r.name}><p className="muted">{r.minutes}분 · {r.description}</p><div className="ingredient-tags">{r.ingredients.map(i=><span key={i.name}>{i.name} {fmtQty(i.quantity)}{i.unit}</span>)}</div></Card>)}</div></>}
      {page==='meals'&&<><div className="page-head"><div><h1>식사 계획</h1><p>등록·수정·외식·취소는 확인 후 저장합니다.</p></div><Button disabled={!recipes.length} onClick={()=>openMeal()}>식사 계획 추가</Button></div><div className="date-row"><input aria-label="조회 날짜" type="date" value={date} onChange={e=>setDate(e.target.value)}/><Button secondary onClick={()=>setDate(today())}>오늘</Button></div><div className="meal-grid">{['아침','점심','저녁'].map(slot=><Card key={slot} title={slot}>{meals.filter(m=>m.date===date&&m.slot===slot).map(m=><div className="meal-card" key={m.id}><div className="meal-name"><strong>{m.name}</strong></div><div className="meal-meta"><span>{m.servings}인분</span><span className="chip">{status[m.status]}</span></div>{m.status==='planned'&&<div className="meal-actions"><button onClick={()=>openMeal(m)}>계획 수정</button><button onClick={()=>setPending({kind:'out',meal:m,label:'외식 처리'})}>외식 기록</button><button onClick={()=>setPending({kind:'cancel',meal:m,label:'식사 취소'})}>식사 취소</button><button disabled title="백엔드 기능 준비 중">조리 완료 · 준비 중</button></div>}</div>)}{!meals.some(m=>m.date===date&&m.slot===slot)&&<p className="empty">등록된 식사가 없습니다.</p>}</Card>)}</div><p className="tip">계획 변경·외식·취소로 재고가 차감되지는 않습니다.</p></>}
      {['recommend','shopping'].includes(page)&&<Card title={page==='recommend'?'AI 추천 준비 중':'장보기 목록 준비 중'}><p className="muted">이 기능은 서버 연결을 준비하고 있습니다. 현재는 식재료와 식사 계획을 관리할 수 있습니다.</p></Card>}
      </fieldset>
    </div></main>
    {form&&<div className="overlay"><section className="modal" role="dialog" aria-modal="true" aria-label={form.kind==='inventory'?'재고 저장':'식사 계획 저장'}><div className="modal-top"><h2>{form.kind==='inventory'?'재고 저장':'식사 계획 저장'}</h2><button disabled={busy} className="icon-btn" aria-label="닫기" onClick={()=>setForm(null)}><X/></button></div><form onSubmit={form.kind==='inventory'?saveItem:reviewMeal}><fieldset className="server-workspace form-stack" disabled={busy || !ready}>{form.kind==='inventory'?<>
      <Field label="재료"><select disabled={!!form.id} value={form.ingredient_id} onChange={e=>update('ingredient_id',e.target.value)}>{data.ingredients.map(i=><option key={i.ingredient_id} value={i.ingredient_id}>{i.ingredient_name} ({units[i.unit]})</option>)}</select></Field>
      <Field label={`수량 (${units[data.ingredients.find(i=>i.ingredient_id===form.ingredient_id)?.unit] || ''})`}><input required type="number" min="0" max="1000000000" step="any" value={form.quantity} onChange={e=>update('quantity',e.target.value)}/></Field>
      <Field label="보관 위치"><select value={form.storage_location} onChange={e=>update('storage_location',e.target.value)}><option value="fridge">냉장</option><option value="freezer">냉동</option><option value="pantry">실온</option></select></Field>
    </>:<>
      <Field label="날짜"><input required type="date" value={form.date} onChange={e=>update('date',e.target.value)}/></Field>
      <Field label="식사 시간"><select value={form.slot} onChange={e=>update('slot',e.target.value)}>{['아침','점심','저녁'].map(s=><option key={s}>{s}</option>)}</select></Field>
      <Field label="메뉴"><select required value={form.recipeId} onChange={e=>update('recipeId',e.target.value)}>{recipes.map(r=><option key={r.id} value={r.id}>{r.name}</option>)}</select></Field>
      <Field label="인분"><input required type="number" min="0.1" max="12" step="any" value={form.servings} onChange={e=>update('servings',e.target.value)}/></Field>
    </>}<div className="modal-actions"><Button secondary type="button" onClick={()=>setForm(null)}>취소</Button><Button type="submit">{form.kind==='inventory'?'저장':'변경 확인'}</Button></div></fieldset></form></section></div>}
    {pending&&<div className="overlay"><section className="modal" role="dialog" aria-modal="true" aria-label="변경 확인"><h2>{pending.label}</h2><p className="muted">{pending.form?`${pending.form.date} ${pending.form.slot} · ${recipes.find(r=>r.id===pending.form.recipeId)?.name} ${pending.form.servings}인분`:`${pending.meal.date} ${pending.meal.slot} · ${pending.meal.name}`}</p><p className="tip">확인하면 서버에 저장됩니다. 재고는 그대로 유지됩니다.</p><div className="modal-actions"><Button secondary disabled={busy} onClick={()=>setPending(null)}>돌아가기</Button><Button disabled={busy || !ready} onClick={approve}>{busy?'저장 중…':'확인 및 저장'}</Button></div></section></div>}
    {(form || pending)&&error&&<div role="alert" className="toast">{error}</div>}
  </div>;
}
