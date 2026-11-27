import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createSession,readAuthCallback,clearAuthCallback} from '../src/server-session.js';

test('expired access token is refreshed once across concurrent requests, and clear removes it',async()=>{
  const original=global.fetch;let calls=0;
  global.fetch=async(url,options)=>{calls++;const grant=new URL(url).searchParams.get('grant_type');assert.equal(options.headers.apikey,'test-key');if(grant==='password')return {ok:true,json:async()=>({access_token:'old',refresh_token:'refresh',expires_in:1,user:{email:'test@example.com'}})};assert.deepEqual(JSON.parse(options.body),{refresh_token:'refresh'});return {ok:true,json:async()=>({access_token:'new',refresh_token:'next',expires_in:3600})};};
  try {const auth=createSession('https://test-project.supabase.co','test-key');await auth.signIn('test@example.com','test-password');assert.deepEqual(await Promise.all([auth.accessToken(),auth.accessToken()]),['new','new']);assert.equal(calls,2);auth.clear();assert.equal(await auth.accessToken(),null);}finally{global.fetch=original;}
});

test('tab session restores after reload and logout clears persisted credentials',async()=>{
 const original=global.fetch;const values=new Map();const storage={getItem:k=>values.get(k)||null,setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)};
 global.fetch=async()=>({ok:true,json:async()=>({access_token:'token',refresh_token:'refresh',expires_in:3600,user:{email:'test@example.com'}})});
 try {const a=createSession('https://test.supabase.co','key',storage);await a.signIn('test@example.com','password');const b=createSession('https://test.supabase.co','key',storage);assert.equal(await b.accessToken(),'token');assert.equal(b.user().email,'test@example.com');b.clear();assert.equal(values.size,0);a.setPersistence(false);await a.signIn('test@example.com','password');assert.equal(values.size,0);}finally{global.fetch=original;}
});

function tabStorage() {
 const values=new Map();
 return {getItem:key=>values.get(key)||null,setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)};
}

test('callback parsing and cleanup preserve navigation and remove auth credentials',()=>{
 const href='https://app.example.test/?page=inventory&auth=recovery#access_token=test-access&refresh_token=test-refresh&type=recovery&expires_in=120';
 const callback=readAuthCallback(href);
 assert.equal(callback.type,'recovery');assert.equal(callback.expires_in,120);
 let cleaned;
 clearAuthCallback(href,{state:null,replaceState:(_state,_title,url)=>{cleaned=new URL(url);}});
 assert.equal(cleaned.search,'?page=inventory');assert.equal(cleaned.hash,'');
 const expired=readAuthCallback('https://app.example.test/?auth=recovery#error=access_denied&error_code=otp_expired');
 assert.deepEqual(expired,{type:'recovery',error:'otp_expired'});
 assert.equal(readAuthCallback('https://app.example.test/?page=home'),null);
});

test('recovery callback persists across reload, remains separate from login and clears after reset',async()=>{
 const original=global.fetch,storage=tabStorage();const calls=[];
 global.fetch=async(url,options)=>{
  calls.push({url,options});
  assert.equal(options.headers.Authorization,'Bearer recovery-access');
  if(options.method==='GET'){assert.equal(options.body,undefined);return new Response(JSON.stringify({id:'user-1',email:'test@example.test'}));}
  assert.equal(options.method,'PUT');assert.deepEqual(JSON.parse(options.body),{password:'new-password-1'});
  return new Response('{}');
 };
 try {
  const first=createSession('https://auth.example.test','public-key',storage);
  await first.acceptCallback({type:'recovery',access_token:'recovery-access',expires_in:120});
  assert.equal(await first.accessToken(),null);
  const reloaded=createSession('https://auth.example.test','public-key',storage);
  assert.equal(reloaded.hasRecovery(),true);await reloaded.restoreRecovery();
  await reloaded.resetRecoveryPassword('new-password-1');
  assert.equal(reloaded.hasRecovery(),false);
  assert.equal(storage.getItem('nextmeal-recovery:https://auth.example.test'),null);
  assert.equal(calls.length,3);
 }finally{global.fetch=original;}
});

test('verified token hash is exchanged once and an expired recovery asks for a new email',async()=>{
 const original=global.fetch,now=Date.now,storage=tabStorage();let exchanges=0;
 global.fetch=async(url,options)=>{
  assert.ok(url.endsWith('/verify'));exchanges++;
  assert.deepEqual(JSON.parse(options.body),{token_hash:'test-hash',type:'recovery'});
  return new Response(JSON.stringify({access_token:'recovery-access',expires_in:60,user:{id:'user-1'}}));
 };
 try {
  const auth=createSession('https://auth.example.test','key',storage);
  await auth.acceptCallback({type:'recovery',token_hash:'test-hash'});
  const deadline=JSON.parse(storage.getItem('nextmeal-recovery:https://auth.example.test')).expires_at;
  Date.now=()=>deadline+1;
  const reloaded=createSession('https://auth.example.test','key',storage);
  await assert.rejects(reloaded.restoreRecovery(),error=>error.recoveryExpired&&error.code==='otp_expired');
  assert.equal(reloaded.hasRecovery(),false);assert.equal(exchanges,1);
 }finally{global.fetch=original;Date.now=now;}
});

test('signup callback uses a server-verified user and can restore a normal session',async()=>{
 const original=global.fetch,storage=tabStorage();
 global.fetch=async(url,options)=>{
  assert.equal(url,'https://auth.example.test/auth/v1/user');
  assert.equal(options.method,'GET');assert.equal(options.headers.Authorization,'Bearer signup-access');
  return new Response(JSON.stringify({id:'verified-user',email:'verified@example.test'}));
 };
 try {
  const auth=createSession('https://auth.example.test','key',storage);
  await auth.acceptCallback({type:'signup',access_token:'signup-access',refresh_token:'signup-refresh',expires_in:3600});
  const reloaded=createSession('https://auth.example.test','key',storage);
  assert.equal(reloaded.user().id,'verified-user');assert.equal(await reloaded.accessToken(),'signup-access');
  reloaded.clear();assert.equal(storage.getItem('nextmeal-session:https://auth.example.test'),null);
 }finally{global.fetch=original;}
});

test('resend and recover send supported fields and expose actionable fixed errors',async()=>{
 const original=global.fetch;const requests=[];
 global.fetch=async(url,options)=>{
  requests.push({url,body:JSON.parse(options.body)});
  return new Response(JSON.stringify({error_code:'over_email_send_rate_limit',msg:'provider detail'}),{status:429});
 };
 try {
  const auth=createSession('https://auth.example.test','key');
  await assert.rejects(auth.resendSignup(' test@example.test ','https://app.example.test/?auth=signup'),/메일을 너무 자주/);
  await assert.rejects(auth.recover(' test@example.test ','https://app.example.test/?auth=recovery'),/메일을 너무 자주/);
  assert.deepEqual(requests[0].body,{type:'signup',email:'test@example.test'});
  assert.deepEqual(requests[1].body,{email:'test@example.test'});
  assert.equal(new URL(requests[0].url).searchParams.get('redirect_to'),'https://app.example.test/?auth=signup');
 }finally{global.fetch=original;}
});

test('clearing a session cancels an in-flight callback and avoids restoring its credentials',async()=>{
 const original=global.fetch,storage=tabStorage();let respond;
 global.fetch=()=>new Promise(resolve=>{respond=resolve;});
 try {
  const auth=createSession('https://auth.example.test','key',storage);
  const pending=auth.acceptCallback({type:'recovery',access_token:'test-token',expires_in:60});
  auth.clear();respond(new Response(JSON.stringify({id:'user-1'})));
  await assert.rejects(pending,/인증이 취소/);assert.equal(auth.hasRecovery(),false);
  assert.equal(storage.getItem('nextmeal-recovery:https://auth.example.test'),null);
 }finally{global.fetch=original;}
});
