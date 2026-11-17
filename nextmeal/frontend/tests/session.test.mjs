import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createSession} from '../src/server-session.js';

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
