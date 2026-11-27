import React,{useEffect,useMemo,useRef,useState} from 'react';
import {ChefHat,House,Refrigerator,CalendarDays,Sparkles,ShoppingBasket,History,Menu,ChevronRight} from 'lucide-react';
import {createSession,readAuthCallback,clearAuthCallback} from './server-session';
import {createWorkspaceClient,dateNow,offsetDate,unitLabels as U,storageLabels as S,slotLabels as Slots,statusLabels as Status,quantityLabel,scaledParts} from './workspace-client';

import {Button, Field, Card, Modal, Options, ChangeSummary, MealPlanReview, formatAmount as fmt} from './integrated-ui';
import {PurchaseFields, purchaseDraft, purchaseCommand} from './PurchaseFields';
import MenuFinder from './MenuFinder';
import ShoppingList from './ShoppingList';
import HistoryList from './HistoryList';
import QuickStock, {emptyStockRow} from './QuickStock';

const tabs=[['home','홈',House],['inventory','식재료',Refrigerator],['recipes','내 메뉴',ChefHat],['meals','식사 계획',CalendarDays],['recommend','메뉴 찾기',Sparkles],['shopping','장보기',ShoppingBasket],['history','변경 이력',History]];
const validPage=p=>tabs.some(t=>t[0]===p)?p:'home';
const urlPage=()=>validPage(new URLSearchParams(window.location.search).get('page'));
const resumeIdFromUrl=()=>new URLSearchParams(window.location.search).get('after');
function pageUrl(page, resumeId=null) {
 const url=new URL(window.location.href);
 url.searchParams.set('page',page);
 if(resumeId) url.searchParams.set('after',resumeId);
 else url.searchParams.delete('after');
 return url;
}
const readStored=k=>{try{return JSON.parse(window.sessionStorage.getItem(k)||'null')}catch{return null}};
const writeStored=(k,v)=>{try{if(v===null)window.sessionStorage.removeItem(k);else window.sessionStorage.setItem(k,JSON.stringify(v));}catch{}};
const directActions=new Set(['ingredient.create','shopping.add','shopping.check','lot.create','lot.quick_add','recipe.save','meal.save','meal.skip_followup']);
const newRecipePart=()=>({ingredient_id:'',quantity:'',unit:'g'});
export default function IntegratedApp(){
 const [config,setConfig]=useState(null),[configError,setConfigError]=useState(''),[user,setUser]=useState(null),[view,setView]=useState(null);
 const [page,setPage]=useState(urlPage),[sidebar,setSidebar]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
 const [email,setEmail]=useState(''),[password,setPassword]=useState(''),[remember,setRemember]=useState(true);
 const [authCallback,setAuthCallback]=useState(()=>readAuthCallback(window.location.href));
 const [authMode,setAuthMode]=useState(()=>authCallback?.type==='recovery'?'reset':'login'),[confirmPassword,setConfirmPassword]=useState('');
 const [form,setForm]=useState(null),[pending,setPending]=useState(null),[date,setDate]=useState(dateNow()),[week,setWeek]=useState(false);
 const [query,setQuery]=useState(''),[location,setLocation]=useState(''),[showEmpty,setShowEmpty]=useState(false),[sort,setSort]=useState('expiry'),[archivedRecipes,setArchivedRecipes]=useState(false);
 const debugTiming=new URLSearchParams(window.location.search).get('debug')==='performance';
 const [requestTimings,setRequestTimings]=useState([]);
 const [weekStart,setWeekStart]=useState(date);
 const [needsRefresh,setNeedsRefresh]=useState(false);
 const [resumeId,setResumeId]=useState(resumeIdFromUrl);
 const [mealTarget,setMealTarget]=useState({date:dateNow(),slot:'dinner',servings:1});
 const ws=view?.workspace;
 const followups=ws?.meal_followups || {};
 const resume=page==='recommend' && resumeId && followups[resumeId];
 const nextMeal=resume?.target_id ? ws.meals.find(meal=>meal.id===resume.target_id) : null;
 const selection=resume && mealTarget.after!==resumeId ? {date:resume.date,slot:resume.slot,servings:1} : mealTarget;
 const lock=useRef(false),started=useRef(false);
 useEffect(()=>{let alive=true;fetch('/app-config').then(r=>{if(!r.ok)throw Error();return r.json();}).then(c=>{if(alive)setConfig(c);}).catch(()=>{if(!alive)return;const env=import.meta.env;if(env.VITE_SUPABASE_URL&&env.VITE_SUPABASE_PUBLISHABLE_KEY)setConfig({mode:env.VITE_APP_MODE==='local'?'local':'supabase',url:env.VITE_SUPABASE_URL,key:env.VITE_SUPABASE_PUBLISHABLE_KEY,api:env.VITE_API_BASE_URL||'http://127.0.0.1:8000'});else setConfigError('통합 실행 파일로 실행하세요. /app-config 설정을 불러오지 못했습니다.');});return()=>{alive=false;};},[]);
 const auth=useMemo(()=>{if(!config)return null;let storage=null;try{storage=window.sessionStorage;}catch{}return createSession(config.url,config.key,storage);},[config]);
 const api=useMemo(()=>config?createWorkspaceClient(config.api||'',auth,config.mode==='local',debugTiming?record=>setRequestTimings(previous=>[record,...previous].slice(0,20)):null):null,[config,auth,debugTiming]);
 const scope=user?(config.mode==='local'?'local':user.id||user.email):null;
 const draftKey=scope?'nextmeal-draft-v1:'+scope:null;
 const positionKey=scope?'nextmeal-position-v1:'+scope:null;
 const skipDraft=useRef(false),hydrated=useRef(null),scrollTarget=useRef(null);
 useEffect(()=>{if(!draftKey){hydrated.current=null;return;}if(hydrated.current===draftKey)return;hydrated.current=draftKey;skipDraft.current=true;const d=readStored(draftKey);const pos=readStored(positionKey);if(pos?.date)setDate(pos.date);if(pos?.weekStart)setWeekStart(pos.weekStart);if(typeof pos?.week==='boolean')setWeek(pos.week);if(d?.form&&['ingredient','recipe','lot','use','meal','manual','copy','cook','quickStock'].includes(d.form.kind)){setForm(d.form);setMessage('작성 중이던 초안을 복구했습니다. 저장 전에 내용을 확인하세요.');}scrollTarget.current=pos?.page===page?pos.y:0;},[draftKey]);
 useEffect(()=>{if(!draftKey||hydrated.current!==draftKey)return;if(skipDraft.current){skipDraft.current=false;return;}writeStored(draftKey,form?{form}:null);},[draftKey,form]);
 useEffect(()=>{if(!positionKey)return;const save=()=>{if(scrollTarget.current!==null)return;writeStored(positionKey,{page,date,week,weekStart,y:window.scrollY});writeStored(positionKey+':'+page,{y:window.scrollY});};const restore=scrollTarget.current;const raf=restore==null?null:window.requestAnimationFrame(()=>{scrollTarget.current=null;window.scrollTo(0,restore);});window.addEventListener('scroll',save,{passive:true});window.addEventListener('pagehide',save);return()=>{if(raf!==null)window.cancelAnimationFrame(raf);window.removeEventListener('scroll',save);window.removeEventListener('pagehide',save);};},[positionKey,page,date,week,weekStart]);
 useEffect(()=>{const pop=()=>{const next=urlPage();scrollTarget.current=readStored(positionKey+':'+next)?.y||0;setPage(next);setSidebar(false);setResumeId(resumeIdFromUrl());};window.addEventListener('popstate',pop);return()=>window.removeEventListener('popstate',pop);},[positionKey]);
 const ingredient=id=>ws?.ingredients.find(i=>i.id===id);
 const name=id=>ingredient(id)?.name || '알 수 없는 재료';
 function navigate(page, after=null) {
  if(urlPage()!==page || resumeIdFromUrl()!==after){if(positionKey)writeStored(positionKey+':'+urlPage(),{y:window.scrollY});window.history.pushState(null,'',pageUrl(page,after));} setResumeId(after); setPage(page); setSidebar(false); setError(''); setMessage(''); setNeedsRefresh(false);
  window.scrollTo({top:0,behavior:'smooth'});
 }
 function closeEditor() {
  setForm(form?.returnToRecipe ?? null); setError(''); setNeedsRefresh(false);
 }
 async function run(action) {
  if(lock.current) return;
  lock.current=true; setBusy(true); setError(''); setMessage('');
  try { await action(); }
  catch(e) {
   if(e.status===401) {
    auth?.clear(); setUser(null); setView(null); setForm(null); setPending(null); setResumeId(null); setNeedsRefresh(false);
   }
   if(e.recoveryExpired) {
    auth?.clearRecovery(); setAuthMode('recover'); setPassword(''); setConfirmPassword('');
   }
   if(e.revisionConflict) setNeedsRefresh(true);
   setError(e.name==='AbortError'?'응답 시간이 초과되었습니다. 다시 확인해 주세요.':e.message||'연결을 확인하세요.');
  } finally { lock.current=false; setBusy(false); }
 }
 async function reload(){setView(await api.load());}
 useEffect(()=>{
  if(!api||started.current)return;
  started.current=true;
  run(async()=>{
   if(config.mode==='local'){await reload();setUser({email:'내 컴퓨터 시연 모드'});return;}
   if(authCallback){
    let verifiedUser;
    try {
     verifiedUser=await auth.acceptCallback(authCallback);
    } catch(error) {
     setAuthMode(authCallback.type==='recovery'?'recover':'resend');
     throw error;
    } finally {
     clearAuthCallback(window.location.href,window.history);setAuthCallback(null);
    }
    if(authCallback.type==='recovery')setAuthMode('reset');
    else {
     await reload();setUser(verifiedUser||auth.user());
     setAuthMode('login');setMessage('이메일 인증이 완료되어 로그인했어요.');
    }
    return;
   }
   if(auth.hasRecovery()){await auth.restoreRecovery();setAuthMode('reset');return;}
   if(await auth.accessToken()){await reload();setUser(auth.user()||{email:'로그인된 계정'});}
  });
 },[api]);
 function login(e){e.preventDefault();run(async()=>{auth.setPersistence(remember);const u=await auth.signIn(email,password);setPassword('');await reload();setUser(u||{email});});}
 function logout(){if(draftKey)writeStored(draftKey,null);if(positionKey){writeStored(positionKey,null);for(const [tab] of tabs)writeStored(positionKey+':'+tab,null);}window.history.replaceState(null,'',pageUrl('home'));auth.clear();setUser(null);setView(null);setForm(null);setPending(null);setError('');setMessage('');setRequestTimings([]);setResumeId(null);setNeedsRefresh(false);setPage('home');setAuthMode('login');setPassword('');setConfirmPassword('');}
 function switchAuth(mode){if(mode!=='reset')auth?.clearRecovery();setAuthMode(mode);setPassword('');setConfirmPassword('');setError('');setMessage('');}
 function authSubmit(e){
  if(authMode==='login')return login(e);
  e.preventDefault();
  run(async()=>{
   const redirect=new URL(window.location.pathname,window.location.origin);
   redirect.searchParams.set('auth',authMode==='recover'?'recovery':'signup');
   if(authMode==='recover'){
    await auth.recover(email,redirect.href);
    setMessage('등록된 이메일이라면 비밀번호 재설정 안내가 발송됩니다.');return;
   }
   if(authMode==='resend'){
    await auth.resendSignup(email,redirect.href);
    setMessage('인증이 필요한 이메일이라면 확인 메일을 다시 보냈어요. 메일함을 확인해 주세요.');return;
   }
   if(password.length<8||password!==confirmPassword)throw Error('비밀번호는 8자 이상이며 확인 값과 일치해야 합니다.');
   if(authMode==='signup'){
    await auth.signUp(email,password,redirect.href);
    if(auth.user()){
     await reload();setUser(auth.user());setAuthMode('login');setPassword('');setConfirmPassword('');
     setMessage('회원가입이 완료되어 로그인했어요.');
    } else {
     switchAuth('resend');setMessage('가입 요청을 받았어요. 이메일 인증이 필요하면 메일의 링크를 눌러 주세요.');
    }
   } else {
    await auth.resetRecoveryPassword(password);auth.clear();switchAuth('login');
    setMessage('비밀번호를 변경했습니다. 다시 로그인하세요.');
   }
  });
 }
 function update(key,value){setForm(f=>({...f,[key]:value}));}
 async function prepare(action,payload,forcePreview=false) {
  await run(async()=>{
   const command={request_id:crypto.randomUUID(),expected_revision:view.revision,action,payload};
   if (forcePreview || !directActions.has(action)) {
    const preview=await api.preview(command);
    setPending({command,...preview});
    return;
   }
   try {
    const result=await api.commit(command);
    applyResult(result,command);
   } catch(e) {
    if(!e.status || e.status>=500) setPending({command,uncertain:true,direct:true,summary:'저장 결과를 확인해 주세요.'});
    throw e;
   }
  });
 }
 function backFromPreview() {
  if(pending?.uncertain) return;
  setPending(null); setError('');
 }
 async function refreshDraft() {
  await run(async()=>{
   const latest=await api.load();
   setView(latest); setNeedsRefresh(false);
   if (form || pending?.direct) {
    setPending(null);
    setMessage(form ? '입력값을 유지했어요. 최신 내용으로 다시 확인하세요.' : '최신 내용을 불러왔어요.');
   } else if (pending) {
    const command={...pending.command,request_id:crypto.randomUUID(),expected_revision:latest.revision};
    setPending(null);
    const preview=await api.preview(command);
    setPending({command,...preview});
   } else setMessage('최신 데이터를 불러왔습니다.');
  });
 }
 async function commit() {
  await run(async()=>{
   const {command}=pending;
   let result;
   try { result=await api.commit(command); }
   catch(e) {
    if (!e.status || e.status>=500) setPending(p=>({...p,uncertain:true}));
    else setPending(p=>({...p,uncertain:false}));
    throw e;
   }
   applyResult(result,command);
  });
 }
 function applyResult(result,command) {
  setView(result); setPending(null); setForm(null); setNeedsRefresh(false);
  if(command.action==='ingredient.create'&&form?.returnToRecipe) {
   const draft=form.returnToRecipe;
   const added=result.workspace.ingredients.find(item=>item.name===command.payload.name.trim());
   const rows=[...draft.ingredients];
   const empty=rows.findIndex(part=>!part.ingredient_id);
   rows[empty<0?rows.length:empty]={...(rows[empty]||newRecipePart()),ingredient_id:added.id,unit:added.unit};
   setForm({...draft,ingredients:rows});
  }
  if(command.action==='lot.quick_add'&&form?.goToMenus) openMenuPicker();
  if(command.action==='meal.save') {
   const day=command.payload.date;
   setDate(day); setWeekStart(day); setWeek(false); navigate('meals');
  }
  setMessage(result.summary||'저장했습니다.');
 }
 function mealForm(recipeId=null,meal=null,defaultDate=dateNow(),defaultSlot='dinner') {
  const recipe=recipeId || meal?.recipe_id || ws.recipes.find(r=>!r.archived)?.id;
  setForm({kind:'meal',id:meal?.id||null,date:meal?.date||defaultDate,slot:meal?.slot||defaultSlot,
   recipe_id:recipe,servings:meal?.servings||1,repeat_days:1});
 }
 function openMenuPicker(day=dateNow(),slot='dinner') {
  setMealTarget({date:day,slot,servings:1});
  navigate('recommend');
 }
 async function requestRecommendation(body) {
  let result;
  await run(async()=>{
   result=await api.recommend(body);
   if(result.revision!==view.revision) await reload();
  });
  return result;
 }
 function chooseMenu(recipeId, recommendation=null) {
  if(recommendation && recommendation.revision!==view.revision) return;
  const plan=nextMeal||recommendation||selection;
  prepare('meal.save',{
   id:nextMeal?.id||null,date:plan.date,slot:plan.slot,
   ...(resume ? {after_eating_out:resumeId} : {}),
   recipe_id:recipeId,servings:Number(plan.servings),repeat_days:1
  },true);
 }
 function openQuickStock(goToMenus=false){setForm({kind:"quickStock",rows:[emptyStockRow()],goToMenus});}
 function lotForm(ingredientId=null,lot=null,manualId=null,shortage=null) {
  const manual=ws.manual.find(i=>i.id===manualId);
  setForm(purchaseDraft(ws,{ingredientId,lot,manual,shortage}));
 }
 function recipeForm(recipe=null){setForm({kind:'recipe',id:recipe?.id||null,name:recipe?.name||'',base_servings:recipe?.base_servings||1,minutes:recipe?.minutes||15,description:recipe?.description||'',instructions:recipe?.instructions||'',ingredients:recipe?recipe.ingredients.map(i=>({...i})): [newRecipePart()]});}
 function openCook(meal){setForm({kind:'cook',id:meal.id,meal,usage:scaledParts(meal)});}
 function saveForm(e){e.preventDefault();if(needsRefresh)return;let action,payload;
  if(form.kind==='ingredient'){action='ingredient.create';payload={name:form.name,unit:form.unit};}
  if(form.kind==='recipe'){action='recipe.save';payload={id:form.id,name:form.name,base_servings:Number(form.base_servings),minutes:Number(form.minutes),description:form.description,instructions:form.instructions,ingredients:form.ingredients.map(i=>({...i,quantity:Number(i.quantity)}))};}
  if(form.kind==='lot') ({action,payload}=purchaseCommand(form));
  if(form.kind==='quickStock'){
   action='lot.quick_add';
   payload={items:form.rows.map(row=>({name:row.name.trim(),quantity:Number(row.quantity),unit:row.unit,
    ...(row.unit==='pack' ? {pack_label:row.packLabel||'팩',pack_size:row.productId?null:Number(row.packSize),product_id:row.productId||null} : {})}))};
  }
  if(form.kind==='use'){action='lot.use';payload={id:form.id,quantity:Number(form.quantity)*(form.pack_size||1),reason:form.reason};}
  if(form.kind==='meal'){action='meal.save';payload={id:form.id,date:form.date,slot:form.slot,recipe_id:form.recipe_id,servings:Number(form.servings),repeat_days:Number(form.repeat_days)};}
  if(form.kind==='copy'){action='meal.copy';payload={source_date:date,days:Number(form.days)};}
  if(form.kind==='cook'){
   action='meal.cook';payload={id:form.id,usage:form.usage.filter(i=>Number(i.quantity)>0).map(i=>({...i,quantity:Number(i.quantity)}))};
   if(!payload.usage.length){setError('사용한 재료의 양을 한 가지 이상 입력하세요.');return;}
  }
  if(form.kind==='manual'){action='shopping.add';payload={name:form.name,quantity:Number(form.quantity),unit:form.unit};}
  prepare(action,payload,e.nativeEvent.submitter?.value==='preview');
 }
 const input=(key,type='text',opts={})=><input {...opts} type={type} value={form[key]} onChange={e=>update(key,e.target.value)}/>;
 const mealDates=week ? Array.from({length:7},(_,i)=>offsetDate(weekStart,i)) : [date];
 function selectDate(value) {
  if(!value) return;
  setDate(value);
  if(!week || value<weekStart || value>offsetDate(weekStart,6)) setWeekStart(value);
 }
 function moveDate(direction) {
  if(week) setWeekStart(offsetDate(weekStart,direction*7));
  setDate(offsetDate(date,direction*(week?7:1)));
 }
 function openHomeCard(destination) {
  if(destination==='inventory') { setQuery(''); setLocation(''); setShowEmpty(false); }
  if(destination==='meals') { setDate(dateNow()); setWeek(false); setWeekStart(dateNow()); }
  navigate(destination);
 }

 const visibleLots=ws?.inventory.filter(l=>(showEmpty||(!l.archived&&l.quantity>0))&&(!location||l.storage===location)&&(name(l.ingredient_id)+' '+l.name).includes(query.trim()))||[];
 const visibleRecipes=ws?.recipes.filter(recipe=>archivedRecipes||!recipe.archived)||[];
 const lotsByIngredient=Object.values(visibleLots.reduce((map,l)=>{(map[l.ingredient_id]||={ingredient:ingredient(l.ingredient_id),lots:[]}).lots.push(l);return map;},{}));
 lotsByIngredient.sort((a,b)=>sort==='name'?a.ingredient.name.localeCompare(b.ingredient.name,'ko'):((a.lots.map(l=>l.expires_on||'9999').sort()[0]).localeCompare(b.lots.map(l=>l.expires_on||'9999').sort()[0])));
 const expired=l=>l.expires_on&&l.expires_on<dateNow();
 const near=l=>l.expires_on&&!expired(l)&&l.expires_on<=offsetDate(dateNow(),3);
 const reviewingMenu=pending?.command.action==='meal.save'&&!pending.direct&&!form;
 const deletingMenu=pending?.command.action==='recipe.delete';
 const editingMealRecipe=form?.kind==='meal'&&ws?.meals.find(meal=>meal.id===form.id)?.recipe;
 if(!config)return <main className="server-login"><Card title="다음한끼">{configError||'설정을 확인하고 있습니다…'}</Card></main>;
 if(!user||!ws)return (
  <main className="server-login"><Card title="있는 재료로 다음 한 끼를 골라보세요">
   <p className="muted">메뉴를 고르면 부족한 재료를 알려드리고, 요리한 만큼 냉장고에 반영해요.</p>
   <hr className="login-divider"/><h2>{{login:'내 계정으로 로그인',signup:'회원가입',resend:'인증 메일 다시 받기',recover:'비밀번호 찾기',reset:'새 비밀번호 설정'}[authMode]}</h2>
   {config.mode==='local'?<Button disabled={busy} onClick={()=>run(async()=>{await reload();setUser({email:'내 컴퓨터 시연 모드'});})}>시연 데이터 열기</Button>:
    <form className="form-stack" onSubmit={authSubmit}>
     {authMode!=='reset'&&<Field label="이메일"><input required type="email" autoComplete="username" value={email} onChange={e=>setEmail(e.target.value)}/></Field>}
     {['login','signup','reset'].includes(authMode)&&<Field label="비밀번호"><input required type="password" autoComplete={authMode==='login'?'current-password':'new-password'} minLength={authMode==='login'?undefined:8} value={password} onChange={e=>setPassword(e.target.value)}/></Field>}
     {['signup','reset'].includes(authMode)&&<Field label="비밀번호 확인"><input required type="password" autoComplete="new-password" value={confirmPassword} onChange={e=>setConfirmPassword(e.target.value)}/></Field>}
     {authMode==='login'&&<label className="check-row"><input type="checkbox" checked={remember} onChange={e=>setRemember(e.target.checked)}/>이 탭에서 로그인 유지</label>}
     <Button type="submit" disabled={busy}>{busy?'연결 중…':{login:'로그인',signup:'가입하기',resend:'인증 메일 다시 보내기',recover:'재설정 메일 보내기',reset:'비밀번호 변경'}[authMode]}</Button>
     <div className="toolbar">{authMode==='login'?<><Button secondary disabled={busy} onClick={()=>switchAuth('signup')}>회원가입</Button><Button secondary disabled={busy} onClick={()=>switchAuth('recover')}>비밀번호 찾기</Button><Button secondary disabled={busy} onClick={()=>switchAuth('resend')}>인증 메일 다시 받기</Button></>:<><Button secondary disabled={busy} onClick={()=>switchAuth('login')}>로그인으로 돌아가기</Button>{authMode==='reset'&&<Button secondary disabled={busy} onClick={()=>switchAuth('recover')}>재설정 메일 다시 받기</Button>}</>}</div>
    </form>}
   {message&&<p role="status" className="tip">{message}</p>}
   {error&&<p role="alert" className="server-error">{error}</p>}
   <p className="fineprint">이메일 인증 설정에 따라 가입 확인 메일이 필요할 수 있어요. 공용 컴퓨터에서는 사용 후 로그아웃하세요.</p>
  </Card></main>
 );

 return <div className="app">
  <aside className={`sidebar ${sidebar?'open':''}`}><div className="brand"><span className="brand-icon"><ChefHat/></span><div><strong>다음한끼</strong><small>내 식재료로 이어가는 집밥</small></div></div><nav aria-label="전체 메뉴">{tabs.map(([key,label,Icon])=><button key={key} className={`nav-item ${page===key?'active':''}`} aria-current={page===key?'page':undefined} onClick={()=>key==='recommend'?openMenuPicker():navigate(key)}><Icon size={19}/>{label}</button>)}</nav><div className="sidebar-foot"><b>{config.mode==='local'?'내 컴퓨터 시연 모드':'내 계정에 저장 중'}</b><p>필요한 만큼 계획하고, 사용한 만큼 기록해요.</p></div></aside>
  {sidebar&&<button className="mobile-shade" aria-label="메뉴 닫기" onClick={()=>setSidebar(false)}/>}
  <nav className="bottom-nav" aria-label="자주 쓰는 메뉴">
    {[['inventory','냉장고',Refrigerator],['meals','오늘 식사',CalendarDays],['shopping','장보기',ShoppingBasket]].map(([key,label,Icon])=>
     <button type="button" key={key} aria-label={label+'로 이동'} aria-current={page===key?'page':undefined}
      disabled={busy} onClick={()=>key==='meals'?openHomeCard('meals'):navigate(key)}><Icon size={22}/><span>{label}</span></button>)}
  </nav>
  <main className="main"><header className="topbar"><button className="menu-toggle" aria-label="메뉴 열기" onClick={()=>setSidebar(true)}><Menu/></button><div className="crumb">다음한끼 / {tabs.find(t=>t[0]===page)?.[1]}</div><Button secondary onClick={logout} disabled={busy}>로그아웃</Button></header><div className="content">
   <div className="server-session"><span>{user.email}</span><Button secondary disabled={busy} onClick={refreshDraft}>새로고침</Button></div>
   {busy&&<p role="status" className="tip">{pending?'변경을 처리하고 있습니다…':'데이터를 확인하고 있습니다…'}</p>}{message&&!form&&!pending&&<p role="status" className="tip">{message}</p>}
   {error&&!form&&!pending&&<div role="alert" className="server-error">{error} {needsRefresh&&<Button secondary onClick={refreshDraft}>최신 내용 불러오기</Button>}</div>}
   <fieldset className="server-workspace" disabled={busy}>
   {(page==='home'||page==='meals')&&!pending&&!form&&ws.meals.filter(meal=>followups[meal.id]).map(source=>{
    const next=followups[source.id];
    const planned=next.target_id && ws.meals.find(meal=>meal.id===next.target_id);
    return <section key={source.id} className="finder-context" aria-label={source.date+' '+Slots[source.slot]+' 외식 후 다음 집밥'}>
     <div><strong>{source.date} {Slots[source.slot]} 외식 후 다음 집밥</strong>
      <p>{next.date} {Slots[next.slot]} · {planned?planned.recipe.name:'새 식사 계획'}</p></div>
     <div className="toolbar"><Button onClick={()=>navigate('recommend',source.id)}>다음 집밥 고르기</Button>
      <Button secondary onClick={()=>prepare('meal.skip_followup',{id:source.id})}>안내 닫기</Button></div>
    </section>;
   })}
   {page==='home'&&<><div className="page-head"><div className="eyebrow">MY KITCHEN<h1>오늘 한 끼, 무엇을 먹을까요?</h1></div><Button onClick={()=>openMenuPicker()}>한 끼 고르기</Button></div>
    {!ws.inventory.some(l=>!l.archived&&l.quantity>0)&&<div className="first-step">
     <p>냉장고에 있는 재료를 적으면 바로 만들 수 있는 메뉴를 찾아드려요.</p>
     <Button onClick={()=>openQuickStock(true)}>재료 추가하고 메뉴 찾기</Button>
    </div>}
    <div className="stats">
    {[
     ['보유 식재료',new Set(ws.inventory.filter(l=>!l.archived&&l.quantity>0).map(l=>l.ingredient_id)).size,'종','inventory'],
     ['오늘 예정 식사',ws.meals.filter(m=>m.date===dateNow()&&m.status==='planned').length,'끼','meals'],
     ['장볼 재료',view.shopping.length,'종','shopping']
    ].map(([label,count,unit,destination])=><button type="button" className="stat stat-link" key={destination} onClick={()=>openHomeCard(destination)}>
     <span>{label}</span><strong>{count}<small>{unit}</small></strong><ChevronRight aria-hidden="true" size={18}/>
    </button>)}
   </div><div className="two-cols"><Card title="먼저 확인할 재료">{ws.inventory.filter(l=>!l.archived&&l.quantity>0&&(near(l)||expired(l))).map(l=><div className="compare-line" key={l.id}><span>{name(l.ingredient_id)} · {l.name}</span><strong>{expired(l)?'소비기한 지남':l.expires_on+'까지'}</strong></div>)}{!ws.inventory.some(l=>!l.archived&&l.quantity>0&&(near(l)||expired(l)))&&<p className="muted">등록한 소비기한 중 3일 안에 확인할 재료가 없어요.</p>}<p className="fineprint">날짜는 직접 입력한 소비기한 기준입니다. 기한이 지난 재고는 자동 조리 차감과 부족량 계산에서 제외합니다.</p></Card><Card title="오늘 예정 식사">{!ws.meals.some(m=>m.date===dateNow()&&m.status==='planned')&&<p className="muted">아직 오늘 식사가 없어요. 한 끼를 골라 계획해 보세요.</p>}{ws.meals.filter(m=>m.date===dateNow()&&m.status==='planned').map(m=><div className="meal-mini" key={m.id}><span>{Slots[m.slot]}</span><strong>{m.recipe.name} · {m.servings}인분</strong></div>)}<Button secondary onClick={()=>{openHomeCard('meals');}}>식사 계획 열기</Button></Card></div></>}
   {page==='inventory'&&<><div className="page-head"><div><h1>내 냉장고</h1><p>구매한 단위로 입력하고, 제품별 잔량을 확인하세요.</p></div><div className="toolbar"><Button secondary onClick={()=>setForm({kind:'ingredient',name:'',unit:'g'})}>새 재료 종류</Button><Button secondary onClick={()=>lotForm()}>식재료 추가</Button><Button onClick={()=>openQuickStock()}>재료 빠르게 추가</Button></div></div><div className="toolbar"><Field label="재료·제품 검색"><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="예: 양파, 닭가슴살"/></Field><Field label="보관 위치"><select value={location} onChange={e=>setLocation(e.target.value)}><option value="">전체</option><Options map={S}/></select></Field><Field label="정렬"><select value={sort} onChange={e=>setSort(e.target.value)}><option value="expiry">소비기한순</option><option value="name">이름순</option></select></Field><label className="check-row"><input type="checkbox" checked={showEmpty} onChange={e=>setShowEmpty(e.target.checked)}/>소진·숨긴 재고 포함</label></div>
    {lotsByIngredient.map(group=><Card key={group.ingredient.id} title={`${group.ingredient.name} · 총 ${fmt(group.lots.filter(l=>!l.archived).reduce((a,l)=>a+l.quantity,0))}${U[group.ingredient.unit]}`} action={<Button secondary onClick={()=>lotForm(group.ingredient.id)}>구매 추가</Button>}><details open><summary>구매분 {group.lots.length}건</summary>{group.lots.sort((a,b)=>(a.expires_on||'9999').localeCompare(b.expires_on||'9999')).map(l=><div className={`lot-row ${expired(l)?'expired':''}`} key={l.id}><div><b>{l.name||group.ingredient.name}{l.archived?' · 숨김':''}</b><p>{quantityLabel(l)}{l.estimated?' (기준량 추정)':''} · {S[l.storage]}</p><small>구매 {l.purchased_on||'미입력'} · 소비기한 {l.expires_on||'미입력'}{l.opened_on?' · 개봉 '+l.opened_on:''}</small></div><div className="toolbar">{l.archived?<Button secondary onClick={()=>prepare('lot.restore',{id:l.id})}>복원</Button>:<><Button secondary onClick={()=>lotForm(null,l)}>정정</Button>{l.quantity>0&&<Button secondary onClick={()=>setForm({kind:'use',id:l.id,quantity:'',pack_size:l.pack_size,pack_label:l.pack_label,unit:l.unit,reason:'use'})}>사용·폐기</Button>}<Button secondary onClick={()=>prepare('lot.archive',{id:l.id})}>숨기기</Button></>}</div></div>)}</details></Card>)}{!lotsByIngredient.length&&<Card title="표시할 재고가 없습니다"><p className="muted">재료를 등록하거나 검색·필터 조건을 바꿔보세요.</p></Card>}</>}
   {page==='recipes'&&<><div className="page-head"><div><h1>내 메뉴</h1><p>필요한 재료와 기준 인분을 등록하세요.</p></div><Button onClick={()=>recipeForm()}>메뉴 추가</Button></div><label className="check-row"><input type="checkbox" checked={archivedRecipes} onChange={e=>setArchivedRecipes(e.target.checked)}/>보관한 메뉴 포함</label><div className="two-cols">{visibleRecipes.map(r=><Card key={r.id} title={r.name+(r.archived?' · 보관됨':'')}><p className="muted">{r.minutes}분 · 기준 {r.base_servings}인분</p><p>{r.description}</p><div className="ingredient-tags">{r.ingredients.map(i=><span key={i.ingredient_id}>{name(i.ingredient_id)} {fmt(i.quantity)}{U[i.unit]}</span>)}</div>{r.instructions&&<details><summary>조리 방법</summary><p className="instructions">{r.instructions}</p></details>}<div className="toolbar">{r.archived?<Button secondary onClick={()=>prepare('recipe.restore',{id:r.id})}>복원</Button>:<><Button onClick={()=>mealForm(r.id)}>식사에 추가</Button><Button secondary onClick={()=>recipeForm(r)}>수정</Button><Button secondary onClick={()=>prepare('recipe.archive',{id:r.id})}>보관</Button></>}<Button secondary onClick={()=>prepare('recipe.delete',{id:r.id})}>삭제</Button></div></Card>)}</div>{!visibleRecipes.length&&<Card title="등록된 메뉴가 없어요"><p className="muted">메뉴를 추가하면 재고에 맞춰 추천받을 수 있어요.</p></Card>}</>}
   {page==='meals'&&<><div className="page-head"><div><h1>식사 계획</h1><p>일간·주간 계획을 관리하고 조리한 양만 차감하세요.</p></div><Button onClick={()=>openMenuPicker(date)}>식사 추가</Button></div><div className="date-row"><div><Button secondary onClick={()=>moveDate(-1)}>이전</Button><input aria-label="조회 날짜" type="date" value={date} onChange={e=>selectDate(e.target.value)}/><Button secondary onClick={()=>moveDate(1)}>다음</Button></div><div className="toolbar"><Button secondary onClick={()=>selectDate(dateNow())}>오늘</Button><Button secondary onClick={()=>{setWeekStart(date);setWeek(!week);}}>{week?'일간 보기':'주간 보기'}</Button><Button secondary onClick={()=>setForm({kind:'copy',days:1})}>예정 식사 복사</Button></div></div>{week&&<div className="week-picker" role="group" aria-label="주간 날짜 선택">
     {mealDates.map(day=><button type="button" key={day} aria-label={day} aria-pressed={day===date}
      onClick={()=>setDate(day)}><span>{new Date(day+'T12:00:00').toLocaleDateString('ko-KR',{weekday:'short'})}</span><strong>{Number(day.slice(-2))}</strong>
      <small>{ws.meals.filter(m=>m.date===day&&m.status==='planned').length}끼</small></button>)}
    </div>}
    {mealDates.map(day=><div key={day} className={week&&day!==date?'week-other-day':undefined}><h2 className="section-subtitle">{day}</h2><div className="meal-grid">{Object.entries(Slots).map(([slot,label])=><Card key={slot} title={label}>{ws.meals.filter(m=>m.date===day&&m.slot===slot).map(m=><div className="meal-card" key={m.id}><strong>{m.recipe.name}</strong><div className="meal-meta"><span>{m.servings}인분</span><span className="chip">{Status[m.status]}</span></div><details><summary>{m.recipe.instructions?'필요 재료와 조리 방법':'필요 재료'}</summary>{scaledParts(m).map(i=><p className="fineprint" key={i.ingredient_id}>{name(i.ingredient_id)} {fmt(i.quantity)}{U[i.unit]}</p>)}{m.recipe.instructions&&<p className="instructions">{m.recipe.instructions}</p>}</details><div className="meal-actions">{m.status==='planned'?<><button onClick={()=>mealForm(null,m)}>계획 수정</button><button onClick={()=>prepare('meal.state',{id:m.id,status:'eating_out'})}>외식</button><button onClick={()=>prepare('meal.state',{id:m.id,status:'cancelled'})}>취소</button><button onClick={()=>openCook(m)}>조리 완료</button></>:m.status!=='cooked'?<button onClick={()=>prepare('meal.state',{id:m.id,status:'planned'})}>예정으로 복원</button>:<p className="fineprint">사용량 기록 완료</p>}</div></div>)}{!ws.meals.some(m=>m.date===day&&m.slot===slot)&&<div className="empty-action"><p>예정된 식사가 없습니다.</p><Button secondary onClick={()=>openMenuPicker(day,slot)}>{label} 메뉴 고르기</Button></div>}</Card>)}</div></div>)}</>}
   {page==='recommend'&&resumeId&&!resume&&<Card title="이 외식의 다음 집밥 안내가 종료됐어요"><Button onClick={()=>navigate('meals')}>식사 계획 보기</Button></Card>}
   {page==='recommend'&&(!resumeId||resume)&&<MenuFinder key={resumeId||'new'} workspace={ws} target={nextMeal} resuming={Boolean(resume)} onChoose={chooseMenu} selection={selection}
    onSelectionChange={value=>setMealTarget({...value,after:resumeId})}
    revision={view.revision} suggest={api.suggest} onRecommend={requestRecommendation} loading={busy}
    onQuickStock={()=>openQuickStock()} onRefresh={refreshDraft}
    onLeaveTarget={()=>openMenuPicker()} onCreate={()=>{navigate('recipes');recipeForm();}}/>}
   {page==='shopping'&&<ShoppingList workspace={ws} shopping={view.shopping}
    onAdd={()=>setForm({kind:'manual',name:'',quantity:1,unit:'개'})} onPurchase={lotForm}
    onArchive={id=>prepare('shopping.archive',{id})} onRestore={id=>prepare('shopping.restore',{id})}
    onPlan={()=>openMenuPicker()}/>}
   {page==='history'&&<HistoryList history={ws.history} onUndo={id=>prepare('history.undo',{id})}/>}
   </fieldset>
   {debugTiming&&<Card title="개발용 요청 성능" action={<Button secondary onClick={()=>setRequestTimings([])}>측정 기록 비우기</Button>}><p className="fineprint">이 탭의 최근 20개 요청입니다. 응답 수신은 토큰 갱신·API 통신·JSON 처리를 포함하며 화면 그리기는 제외합니다. 서버 시간은 Server-Timing 기준입니다. 숫자 단위는 ms입니다.</p><div className="performance-scroll"><table aria-label="개발용 요청 성능"><thead><tr><th>요청</th><th>HTTP</th><th>응답 수신</th><th>서버</th><th>인증</th><th>DB 조회</th><th>DB 저장</th><th>외부 요청</th><th>인증 방식</th></tr></thead><tbody>{requestTimings.map((r,i)=><tr key={i}><td>{r.method} {r.path}</td><td>{r.status||'연결 실패'}</td><td>{r.browser_ms}</td><td>{r.server.total??'—'}</td><td>{r.server.auth??'—'}</td><td>{r.server.db_read??'—'}</td><td>{r.server.db_write??'—'}</td><td>{r.upstream_requests??'—'}</td><td>{r.auth_method}</td></tr>)}</tbody></table></div><p className="fineprint">jwks: 공개키 검증 · remote-legacy: 기존 HS256 인증 · remote-forced: 직접 확인 설정 · remote-fallback: 인증 서버로 확인. 여기에는 토큰·이메일·입력 내용을 기록하지 않습니다.</p></Card>}
  </div></main>
  {form&&!pending&&<Modal key={form.kind} title={{ingredient:'새 재료 종류',lot:'구매분·재고 등록',quickStock:'재료 빠르게 추가',recipe:'메뉴 저장',meal:'식사 계획',use:'사용·폐기',cook:'조리 완료',copy:'예정 식사 복사',manual:'장보기 직접 추가'}[form.kind]} busy={busy} onClose={closeEditor}
   footer={<><Button secondary disabled={busy} onClick={closeEditor}>{form.returnToRecipe?'메뉴 작성으로 돌아가기':'닫기'}</Button>
    {needsRefresh ? <Button disabled={busy} onClick={refreshDraft}>입력 유지하고 새로고침</Button> :
     <Button type="submit" form="workspace-editor" disabled={busy||(form.kind==='recipe'&&!ws.ingredients.length)}>{busy?'처리 중…':form.kind==='quickStock'?(form.goToMenus?'저장하고 메뉴 찾기':'재고에 추가'):['ingredient','manual','recipe','meal'].includes(form.kind)?'저장':form.kind==='lot'&&!form.id?'구매 완료 및 재고 반영':form.kind==='cook'&&!form.editUsage?'이대로 사용':'변경 미리보기'}</Button>}</>}>
   <form id="workspace-editor" onSubmit={saveForm}><fieldset disabled={busy} className="server-workspace form-stack">
   {message&&<p role="status" className="tip">{message}</p>}
   {['lot','recipe','meal'].includes(form.kind)&&!(form.kind==='lot'&&form.id)&&!(form.kind==='recipe'&&!ws.ingredients.length)&&
    <button type="submit" className="text-btn optional-preview" name="intent" value="preview">변경 미리보기</button>}
   {form.kind==='ingredient'&&<><Field label="재료 이름">{input('name','text',{required:true,maxLength:100})}</Field><Field label="기준 단위"><select value={form.unit} onChange={e=>update('unit',e.target.value)}><Options map={{g:'무게(g)',ml:'부피(mL)',count:'개수(개)'}}/></select></Field><p className="fineprint">양파 무게를 모르면 ‘개수’로 등록할 수 있습니다. 다른 단위로 된 같은 이름의 기존 재료가 있으면 ‘양파(개수)’처럼 구분해 주세요. 무게·부피·개수는 임의 환산하지 않습니다.</p></>}
   {form.kind==='lot'&&<PurchaseFields form={form} setForm={setForm} workspace={ws}/>}
   {form.kind==='quickStock'&&<QuickStock rows={form.rows} onChange={rows=>update('rows',rows)} ingredients={ws.ingredients} products={ws.products}/>}
   {form.kind==='recipe'&&<><Field label="메뉴 이름">{input('name','text',{required:true,maxLength:100})}</Field><div className="form-row"><Field label="기준 인분">{input('base_servings','number',{required:true,min:0.1,max:100,step:'any'})}</Field><Field label="조리 시간(분)">{input('minutes','number',{required:true,min:1,max:1440})}</Field></div><b>기준 인분에 필요한 재료</b>
    {!ws.ingredients.length&&<p className="fineprint">등록된 재료가 없어요. 이 메뉴에 쓸 재료를 먼저 등록하세요.</p>}
    <Button secondary onClick={()=>setForm({kind:'ingredient',name:'',unit:'g',returnToRecipe:form})}>새 재료 등록</Button>
    {ws.ingredients.length>0&&form.ingredients.map((part,index)=><div className="part-row" key={index}><Field label={`재료 ${index+1}`}><select required value={ingredient(part.ingredient_id)?part.ingredient_id:''} onChange={e=>setForm(f=>({...f,ingredients:f.ingredients.map((p,i)=>i===index?{...p,ingredient_id:e.target.value,unit:ingredient(e.target.value)?.unit||'g'}:p)}))}><option value="">재료 선택</option>{ws.ingredients.map(i=><option key={i.id} value={i.id}>{i.name} ({U[i.unit]})</option>)}</select></Field><Field label={`필요량 ${index+1}`}><input required type="number" min="0.000001" step="any" value={part.quantity} onChange={e=>setForm(f=>({...f,ingredients:f.ingredients.map((p,i)=>i===index?{...p,quantity:e.target.value}:p)}))}/></Field><Button secondary disabled={form.ingredients.length===1} onClick={()=>update('ingredients',form.ingredients.filter((_,i)=>i!==index))}>줄 삭제</Button></div>)}{ws.ingredients.length>0&&<Button secondary onClick={()=>update('ingredients',[...form.ingredients,newRecipePart()])}>재료 줄 추가</Button>}<details className="purchase-details"><summary>설명과 조리 방법 (선택)</summary>
    <Field label="설명">{input('description','text',{maxLength:1000})}</Field>
    <Field label="조리 방법(선택)"><textarea rows="4" maxLength="10000" value={form.instructions} onChange={e=>update('instructions',e.target.value)}/></Field>
    </details><p className="fineprint">메뉴를 수정해도 기존 식사 계획의 재료 구성은 유지됩니다. 새 구성을 쓰려면 새 식사로 등록하세요.</p></>}
   {form.kind==='meal'&&<><Field label="날짜">{input('date','date',{required:true})}</Field><Field label="식사 시간"><select value={form.slot} onChange={e=>update('slot',e.target.value)}><Options map={Slots}/></select></Field><Field label="메뉴"><select required value={form.recipe_id} onChange={e=>update('recipe_id',e.target.value)}>{editingMealRecipe&&!ws.recipes.some(recipe=>recipe.id===editingMealRecipe.id)&&<option value={editingMealRecipe.id}>{editingMealRecipe.name} (기존 식사)</option>}{ws.recipes.filter(r=>!r.archived||r.id===form.recipe_id).map(r=><option value={r.id} key={r.id}>{r.name}</option>)}</select></Field><Field label="인분">{input('servings','number',{required:true,min:0.1,max:12,step:'any'})}</Field>{!form.id&&<Field label="연속 등록 일수(오늘 선택 포함)">{input('repeat_days','number',{required:true,min:1,max:31})}</Field>}</>}
   {form.kind==='copy'&&<><p>{date}의 예정 식사를 다음 날부터 복사합니다. 같은 날짜·시간·메뉴가 있는 계획은 중복 추가하지 않습니다.</p><Field label="복사할 일수">{input('days','number',{required:true,min:1,max:31})}</Field></>}
   {form.kind==='use'&&<><Field label="처리 종류"><select value={form.reason} onChange={e=>update('reason',e.target.value)}><option value="use">사용</option><option value="waste">폐기</option></select></Field><Field label={`처리할 수량 (${form.pack_size?form.pack_label:U[form.unit]})`}>{input('quantity','number',{required:true,min:0.000001,step:'any'})}</Field><p className="fineprint">입력한 양만 잔량에서 뺍니다. 1팩의 절반은 0.5팩으로 입력할 수 있습니다.</p></>}
   {form.kind==='cook'&&<><p>{form.meal.recipe.name} · {form.meal.servings}인분</p>
    {form.editUsage?<p className="fineprint">사용하지 않은 재료는 0으로 입력하세요.</p>:
     <Button secondary onClick={()=>update('editUsage',true)}>양 수정</Button>}
    {form.usage.map((part,index)=>form.editUsage?
     <Field key={part.ingredient_id} label={name(part.ingredient_id)+' ('+U[part.unit]+')'}>
      <input required type="number" min="0" step="any" value={part.quantity} onChange={e=>update('usage',form.usage.map((x,i)=>i===index?{...x,quantity:e.target.value}:x))}/>
     </Field>:<p className="fineprint" key={part.ingredient_id}>{name(part.ingredient_id)} {fmt(part.quantity)}{U[part.unit]}</p>)}
   </>}
   {form.kind==='manual'&&<><Field label="품목명">{input('name','text',{required:true,maxLength:100})}</Field><Field label="수량">{input('quantity','number',{required:true,min:0.000001,step:'any'})}</Field><Field label="단위">{input('unit','text',{required:true,maxLength:20})}</Field></>}
   {error&&<p role="alert" className="server-error">{error}</p>}
  </fieldset></form></Modal>}
  {pending&&<Modal title={deletingMenu?'메뉴 삭제 확인':reviewingMenu?'식사 계획 확인':'변경 확인'} busy={busy} onClose={pending.uncertain?undefined:backFromPreview}
   footer={<>
    {!pending.uncertain&&<Button secondary disabled={busy} onClick={backFromPreview}>{reviewingMenu?'메뉴 다시 고르기':form?'입력 수정':'닫기'}</Button>}
    {needsRefresh ? <Button disabled={busy} onClick={refreshDraft}>{form?'입력 유지하고 새로고침':'최신 내용 불러오기'}</Button> :
     <Button disabled={busy} onClick={commit}>{busy?'저장 중…':pending.uncertain?'같은 요청으로 재확인':deletingMenu?'메뉴 삭제':reviewingMenu?'이대로 적용':'확인 및 저장'}</Button>}
   </>}>
   {reviewingMenu?<MealPlanReview preview={pending} workspace={ws}/>:<>
    <p><strong>{pending.summary}</strong></p>
    {pending.command.action==='history.undo'&&<p className="fineprint">실제로 차감했던 구매분의 수량만 복원합니다. 조리 기록이라면 식사도 예정으로 돌아갑니다. 날짜와 소비기한은 유지됩니다.</p>}
    {deletingMenu?<p className="fineprint">삭제한 메뉴는 복원할 수 없어요. 이미 등록한 식사 계획과 조리 기록은 유지됩니다.</p>:!pending.direct&&<ChangeSummary preview={pending}/>}
   </>}
   {pending.uncertain&&<p className="fineprint">이미 저장됐을 수 있어요. 같은 요청으로 결과를 확인할 수 있어요.</p>}
   {error&&<p role="alert" className="server-error">{error}</p>}
  </Modal>}
 </div>;
}
