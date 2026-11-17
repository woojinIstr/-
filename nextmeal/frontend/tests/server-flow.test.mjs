import {test} from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {unlink} from 'node:fs/promises';
import {JSDOM} from 'jsdom';

test('server screen sends confirmed changes, handles conflict, preserves inventory and clears account data', async()=>{
  const dom=new JSDOM('<!doctype html><html><body></body></html>',{url:'http://localhost:5173'});
  global.window=dom.window;global.document=dom.window.document;global.HTMLElement=dom.window.HTMLElement;global.IS_REACT_ACT_ENVIRONMENT=true;
  const React=await import('react');
  const {render,screen,fireEvent,waitFor,cleanup}=await import('@testing-library/react');
  const output=new URL('./.server-ui-generated.mjs',import.meta.url);
  await build({entryPoints:['src/ServerApp.jsx'],outfile:output.pathname,bundle:true,platform:'node',format:'esm',external:['react','lucide-react'],define:{'import.meta.env.VITE_SUPABASE_URL':'"https://test-project.supabase.co"','import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY':'"sb_publishable_test"','import.meta.env.VITE_API_BASE_URL':'"http://localhost:8000"'}});
  const App=(await import(output.href)).default;
  const originalFetch=global.fetch;
  let inventory=[],meals=[],creates=0,writes=0,conflict=false,unauthorized=false;
  const ingredients=[{ingredient_id:'ingredient-1',ingredient_name:'닭가슴살',unit:'g'}];
  const recipes=[{recipe_id:'recipe-1',recipe_name:'닭가슴살 볶음밥',cooking_time_minutes:20,description:'테스트 메뉴',base_servings:1,ingredients:[{ingredient_id:'ingredient-1',required_quantity:150,unit:'g'}]}];
  global.fetch=async(url,options={})=>{
    const result=(data,status=200)=>({ok:status<400,status,json:async()=>structuredClone(data)});
    if(url.startsWith('https://')) return result({access_token:'test-token',refresh_token:'test-refresh',expires_in:3600,user:{email:'test@example.com'}});
    assert.equal(options.headers.Authorization,'Bearer test-token');
    if(unauthorized) return result({detail:'unauthorized'},401);
    const path=new URL(url).pathname,method=options.method,body=options.body?JSON.parse(options.body):null;
    if(method==='GET')return result(path==='/ingredients'?ingredients:path==='/recipes'?recipes:path==='/inventory'?inventory:meals);
    writes++;
    if(path==='/inventory') {inventory=[{...body,inventory_id:'inventory-1'}];return result(inventory[0],201);}
    if(path.startsWith('/inventory/')) {if(method==='DELETE'){inventory=[];return result(null,204);}inventory[0]={...inventory[0],...body};return result(inventory[0]);}
    if(path==='/meals'){creates++;const meal={...body,meal_id:`meal-${creates}`,meal_status:'planned',version:0};meals.push(meal);return result(meal,201);}
    if(conflict) return result({detail:'version conflict'},409);
    assert.equal(body.expected_version,meals[0].version);
    meals[0]={...meals[0],...body,meal_status:path.endsWith('/eat-out')?'eating_out':path.endsWith('/cancel')?'cancelled':'planned',version:meals[0].version+1};return result(meals[0]);
  };
  const click=async name=>{const button=await screen.findByRole('button',{name,exact:true});await waitFor(()=>assert.equal(button.disabled,false));fireEvent.click(button);};
  const input=(label,value)=>fireEvent.change(screen.getByLabelText(label,{exact:true}),{target:{value}});
  const settle=async()=>waitFor(()=>assert.equal(screen.getByRole('button',{name:'로그아웃',exact:true}).disabled,false));
  try {
    render(React.createElement(App));
    input('이메일','test@example.com');input('비밀번호','password');await click('로그인');await settle();
    await click('식재료');await click('식재료 추가');input('수량 (g)','300');await click('저장');await screen.findByText('300 g');
    await click('수정');input('수량 (g)','250');await click('저장');await screen.findByText('250 g');
    await click('식사 계획');await click('식사 계획 추가');await click('변경 확인');assert.equal(creates,0);await click('돌아가기');assert.equal(creates,0);
    await click('식사 계획 추가');await click('변경 확인');await click('확인 및 저장');await screen.findByRole('button',{name:'계획 수정',exact:true});assert.equal(creates,1);
    await click('계획 수정');input('인분','2');await click('변경 확인');await click('확인 및 저장');await screen.findByText('2인분');
    conflict=true;await click('외식 기록');await click('확인 및 저장');await waitFor(()=>assert.ok(screen.getAllByText('식사 상태가 이미 변경되었습니다. 새로고침 후 다시 확인하세요.').length));assert.equal(meals[0].meal_status,'planned');await click('돌아가기');
    conflict=false;await click('식사 취소');await click('확인 및 저장');await settle();assert.equal(meals[0].meal_status,'cancelled');assert.equal(inventory[0].quantity,250);
    await click('식사 계획 추가');await click('변경 확인');await click('확인 및 저장');await settle();
    // Out action on the newly created planned meal: adjust mock target to its ID.
    meals.reverse();await click('외식 기록');await click('확인 및 저장');await settle();assert.equal(meals[0].meal_status,'eating_out');assert.equal(inventory[0].quantity,250);
    await click('식재료');window.confirm=()=>true;await click('삭제');await screen.findByText('등록된 재고가 없습니다.');
    unauthorized=true;await click('서버 새로고침');await screen.findByText('로그인을 확인할 수 없습니다. 로그아웃 후 다시 로그인하세요.');
    assert.deepEqual(Object.keys(window.localStorage),[]);assert.ok(writes>=7);
    await click('로그아웃');await screen.findByRole('button',{name:'로그인',exact:true});assert.equal(document.body.textContent.includes('test@example.com'),false);
  } finally {cleanup();global.fetch=originalFetch;dom.window.close();await unlink(output);}
});
