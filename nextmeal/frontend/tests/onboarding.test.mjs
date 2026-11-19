import {test} from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {unlink} from 'node:fs/promises';
import {JSDOM} from 'jsdom';

test('a visitor tries sample meals without login or any account data request',async()=>{
 const dom=new JSDOM('<html><body></body></html>',{url:'http://localhost/'});
 global.window=dom.window;global.document=dom.window.document;global.HTMLElement=dom.window.HTMLElement;
 global.IS_REACT_ACT_ENVIRONMENT=true;window.scrollTo=()=>{};
 const React=await import('react');
 const {render,screen,fireEvent,within,cleanup}=await import('@testing-library/react');
 const output=new URL('./.onboarding-generated.mjs',import.meta.url);
 const originalFetch=global.fetch,requests=[];
 global.fetch=async url=>{
  requests.push(String(url));
  assert.equal(url,'/app-config');
  return {ok:true,json:async()=>({mode:'supabase',url:'https://example.supabase.co',key:'test-key',api:''})};
 };
 try {
  await build({entryPoints:['src/IntegratedApp.jsx'],outfile:output.pathname,bundle:true,platform:'node',format:'esm',external:['react','lucide-react'],define:{'import.meta.env':'{}'}});
  const App=(await import(output.href)).default;render(React.createElement(App));
  fireEvent.click(await screen.findByRole('button',{name:'샘플로 먼저 체험하기'}));
  const trial=within(screen.getByRole('dialog',{name:'샘플 냉장고로 체험하기'}));
  const milk=trial.getByRole('checkbox',{name:/우유/});
  assert.equal(milk.checked,true);fireEvent.click(milk);
  fireEvent.click(trial.getAllByRole('button',{name:'이 메뉴 선택'})[0]);
  assert.match(trial.getByRole('status').textContent,/내 식사에 저장하려면/);
  fireEvent.click(trial.getByRole('button',{name:'내 계정으로 시작하기'}));
  assert.equal(screen.queryByRole('dialog'),null);
  assert.deepEqual(requests,['/app-config']);
  assert.equal(window.sessionStorage.length,0);
 } finally {
  global.fetch=originalFetch;cleanup();dom.window.close();await unlink(output).catch(()=>{});
 }
});
