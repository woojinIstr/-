import {test} from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {unlink} from 'node:fs/promises';
import {JSDOM} from 'jsdom';

test('a visitor sees signup and login without sample recipes or account data requests',async()=>{
 const dom=new JSDOM('<html><body></body></html>',{url:'http://localhost/'});
 global.window=dom.window;global.document=dom.window.document;global.HTMLElement=dom.window.HTMLElement;
 global.IS_REACT_ACT_ENVIRONMENT=true;window.scrollTo=()=>{};
 const React=await import('react');
 const {render,screen,fireEvent,waitFor,cleanup}=await import('@testing-library/react');
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
  assert.ok(await screen.findByRole('button',{name:'로그인'}));
  assert.equal(screen.queryByRole('button',{name:'샘플로 먼저 체험하기'}),null);
  await waitFor(()=>{
   const signup=screen.getByRole('button',{name:'회원가입'});
   assert.equal(signup.disabled,false);
   fireEvent.click(signup);
  });
  assert.ok(await screen.findByRole('button',{name:'가입하기'}));
  assert.equal(screen.queryByRole('dialog'),null);
  assert.deepEqual(requests,['/app-config']);
  assert.equal(window.sessionStorage.length,0);
 } finally {
  global.fetch=originalFetch;cleanup();dom.window.close();await unlink(output).catch(()=>{});
 }
});
