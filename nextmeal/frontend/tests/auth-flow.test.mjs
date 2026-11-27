import {test,beforeEach,afterEach,after} from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {unlink} from 'node:fs/promises';
import {JSDOM} from 'jsdom';

const dom=new JSDOM('<!doctype html><html><body></body></html>',{
 url:'http://localhost:8000',pretendToBeVisual:true,
});
global.window=dom.window;global.document=window.document;global.HTMLElement=window.HTMLElement;
global.IS_REACT_ACT_ENVIRONMENT=true;
window.scrollTo=()=>{};
const React=await import('react');
const {render,screen,fireEvent,waitFor,cleanup}=await import('@testing-library/react');
const output=new URL('./.auth-ui-generated.mjs',import.meta.url);
await build({entryPoints:['src/IntegratedApp.jsx'],outfile:output.pathname,bundle:true,platform:'node',format:'esm',
 external:['react','lucide-react'],define:{'import.meta.env':'{}'}});
const App=(await import(output.href)).default;
const realFetch=global.fetch;
const project='https://auth.example.test';
const user={id:'test-user',email:'test@example.test'};
const workspace={revision:0,today:'2026-11-20',shopping:[],workspace:{
 ingredients:[],inventory:[],recipes:[],meals:[],manual:[],history:[],products:[],
}};
let mode,requests,failures,immediateSignup;

beforeEach(()=>{
 window.history.replaceState(null,'','/');window.sessionStorage.clear();
 mode='supabase';requests=[];failures=new Map();immediateSignup=false;
 global.fetch=async(url,options={})=>{
  if(url==='/app-config')return new Response(JSON.stringify({mode,url:project,key:'public-test-key',api:'http://api.example.test'}));
  if(url==='http://api.example.test/v3/workspace')return new Response(JSON.stringify(workspace));
  const parsed=new URL(url);
  assert.equal(parsed.origin,project);
  const body=options.body?JSON.parse(options.body):null;
  requests.push({path:parsed.pathname,url:parsed,method:options.method,headers:options.headers,body});
  const failure=failures.get(parsed.pathname);
  if(failure)return new Response(JSON.stringify({error_code:failure.code}),{status:failure.status});
  if(parsed.pathname==='/auth/v1/verify')return new Response(JSON.stringify({
   access_token:'verified-access',refresh_token:'verified-refresh',expires_in:3600,user,
  }));
  if(parsed.pathname==='/auth/v1/user')return new Response(JSON.stringify(user));
  if(parsed.pathname==='/auth/v1/signup'&&immediateSignup)return new Response(JSON.stringify({
   user,access_token:'immediate-access',refresh_token:'immediate-refresh',expires_in:3600,
  }));
  return new Response(JSON.stringify({user}));
 };
});
afterEach(()=>{cleanup();global.fetch=realFetch;});
after(async()=>{dom.window.close();await unlink(output);});
const show=()=>render(React.createElement(React.StrictMode,null,React.createElement(App)));
const fill=(label,value)=>fireEvent.change(screen.getByLabelText(label,{exact:true}),{target:{value}});
async function click(name){
 const button=await screen.findByRole('button',{name,exact:true});
 await waitFor(()=>assert.equal(button.disabled,false));fireEvent.click(button);
}

test('recovery survives a clean-URL reload and completes a password change',async()=>{
 window.history.replaceState(null,'','/?auth=recovery#access_token=recovery-access&refresh_token=recovery-refresh&type=recovery&expires_in=3600');
 show();await screen.findByRole('heading',{name:'새 비밀번호 설정',exact:true});
 await waitFor(()=>assert.equal(window.location.hash,''));
 assert.ok(window.sessionStorage.getItem('nextmeal-recovery:'+project));
 cleanup();show();
 await screen.findByRole('heading',{name:'새 비밀번호 설정',exact:true});
 fill('비밀번호','new-password-1');fill('비밀번호 확인','new-password-1');
 await click('비밀번호 변경');
 await screen.findByText('비밀번호를 변경했습니다. 다시 로그인하세요.');
 assert.equal(window.sessionStorage.getItem('nextmeal-recovery:'+project),null);
 const reset=requests.filter(r=>r.path==='/auth/v1/user'&&r.method==='PUT');
 assert.equal(reset.length,1);assert.equal(reset[0].headers.Authorization,'Bearer recovery-access');
 assert.deepEqual(reset[0].body,{password:'new-password-1'});
});

test('expired recovery links show a reason and allow requesting a fresh email',async()=>{
 window.history.replaceState(null,'','/?auth=recovery#error=access_denied&error_code=otp_expired');
 show();await screen.findByRole('heading',{name:'비밀번호 찾기',exact:true});
 assert.match((await screen.findByRole('alert')).textContent,/만료/);
 assert.equal(window.location.hash,'');
 fill('이메일','test@example.test');await click('재설정 메일 보내기');
 await screen.findByText('등록된 이메일이라면 비밀번호 재설정 안내가 발송됩니다.');
 const mail=requests.find(r=>r.path==='/auth/v1/recover');
 assert.deepEqual(mail.body,{email:'test@example.test'});
 assert.equal(new URL(mail.url.searchParams.get('redirect_to')).searchParams.get('auth'),'recovery');
});

test('an expired stored recovery returns to the email request screen',async()=>{
 window.sessionStorage.setItem('nextmeal-recovery:'+project,JSON.stringify({access_token:'expired-token',expires_at:Date.now()-1}));
 show();await screen.findByRole('heading',{name:'비밀번호 찾기',exact:true});
 assert.match((await screen.findByRole('alert')).textContent,/만료/);
 assert.equal(window.sessionStorage.getItem('nextmeal-recovery:'+project),null);
 assert.equal(requests.length,0);
});

test('signup callbacks establish the verified account, clean URLs and show completion',async()=>{
 window.history.replaceState(null,'','/?page=inventory#access_token=signup-access&refresh_token=signup-refresh&type=signup&expires_in=3600');
 show();await screen.findByRole('heading',{name:'내 냉장고',exact:true});
 await screen.findByText('이메일 인증이 완료되어 로그인했어요.');
 assert.equal(window.location.hash,'');assert.equal(window.location.search,'?page=inventory');
 const session=JSON.parse(window.sessionStorage.getItem('nextmeal-session:'+project));
 assert.equal(session.user.id,user.id);assert.equal(session.access_token,'signup-access');
 assert.equal(requests.filter(r=>r.path==='/auth/v1/user').length,1);
 await click('로그아웃');await screen.findByRole('heading',{name:'내 계정으로 로그인',exact:true});
 assert.equal(window.sessionStorage.getItem('nextmeal-session:'+project),null);
});

test('signup offers verification resend and rate-limit failures keep a retry path',async()=>{
 show();await click('회원가입');
 await screen.findByRole('heading',{name:'회원가입',exact:true});
 fill('이메일','test@example.test');fill('비밀번호','example-password-1');fill('비밀번호 확인','example-password-1');
 await click('가입하기');await screen.findByRole('heading',{name:'인증 메일 다시 받기',exact:true});
 assert.equal(screen.queryByLabelText('비밀번호',{exact:true}),null);
 failures.set('/auth/v1/resend',{status:429,code:'over_email_send_rate_limit'});
 await click('인증 메일 다시 보내기');
 assert.match((await screen.findByRole('alert')).textContent,/메일을 너무 자주/);
 failures.clear();await click('인증 메일 다시 보내기');
 await screen.findByText('인증이 필요한 이메일이라면 확인 메일을 다시 보냈어요. 메일함을 확인해 주세요.');
 assert.deepEqual(requests.filter(r=>r.path==='/auth/v1/resend').at(-1).body,{type:'signup',email:'test@example.test'});
});

test('ingredient drafts restore after reload and closing the editor clears the saved draft',async()=>{
 mode='local';window.history.replaceState(null,'','/?page=inventory');
 window.sessionStorage.setItem('nextmeal-draft-v1:local',JSON.stringify({form:{kind:'ingredient',name:'초안당근',unit:'count'}}));
 show();await screen.findByRole('dialog',{name:'새 재료 종류',exact:true});
 assert.equal(screen.getByLabelText('재료 이름',{exact:true}).value,'초안당근');
 fill('재료 이름','수정한 당근');
 await waitFor(()=>assert.equal(JSON.parse(window.sessionStorage.getItem('nextmeal-draft-v1:local')).form.name,'수정한 당근'));
 cleanup();show();await screen.findByRole('dialog',{name:'새 재료 종류',exact:true});
 assert.equal(screen.getByLabelText('재료 이름',{exact:true}).value,'수정한 당근');
 fireEvent.click(screen.getAllByRole('button',{name:'닫기',exact:true}).at(-1));
 await waitFor(()=>assert.equal(window.sessionStorage.getItem('nextmeal-draft-v1:local'),null));
});

test('signup without required email confirmation adopts the returned session',async()=>{
 immediateSignup=true;
 show();await click('회원가입');
 await screen.findByRole('heading',{name:'회원가입',exact:true});
 fill('이메일','test@example.test');fill('비밀번호','example-password-1');fill('비밀번호 확인','example-password-1');
 await click('가입하기');await screen.findByRole('heading',{name:'오늘 한 끼, 무엇을 먹을까요?',exact:true});
 await screen.findByText('회원가입이 완료되어 로그인했어요.');
 assert.equal(JSON.parse(window.sessionStorage.getItem('nextmeal-session:'+project)).access_token,'immediate-access');
});

test('a verified recovery hash is reused when retrying a rejected new password',async()=>{
 window.history.replaceState(null,'','/?type=recovery&token_hash=test-recovery-hash');
 show();await screen.findByRole('heading',{name:'새 비밀번호 설정',exact:true});
 await waitFor(()=>assert.equal(window.location.search,''));
 failures.set('/auth/v1/user',{status:400,code:'weak_password'});
 fill('비밀번호','new-password-1');fill('비밀번호 확인','new-password-1');await click('비밀번호 변경');
 assert.match((await screen.findByRole('alert')).textContent,/더 강한 비밀번호/);
 failures.clear();fill('비밀번호','new-strong-password-2');fill('비밀번호 확인','new-strong-password-2');
 await click('비밀번호 변경');await screen.findByText('비밀번호를 변경했습니다. 다시 로그인하세요.');
 assert.equal(requests.filter(r=>r.path==='/auth/v1/verify').length,1);
 assert.equal(requests.filter(r=>r.path==='/auth/v1/user'&&r.method==='PUT').length,2);
});
