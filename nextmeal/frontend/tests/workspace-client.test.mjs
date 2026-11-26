import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createWorkspaceClient} from '../src/workspace-client.js';

test('request diagnostics expose timings without tokens, headers or user data',async()=>{
 const original=global.fetch,records=[];
 global.fetch=async(url,options)=>{
  assert.equal(options.headers.Authorization,'Bearer PRIVATE-TOKEN');
  return new Response(JSON.stringify({workspace:{name:'PRIVATE-FOOD',email:'PRIVATE-EMAIL'}}),{headers:{'Server-Timing':'auth;dur=0.41, db_read;dur=201.32, db_write;dur=0, compute;dur=2, total;dur=208.12','X-Auth-Verification':'jwks','X-Upstream-Requests':'1','X-Private':'PRIVATE-HEADER'}});
 };
 try{
  const api=createWorkspaceClient('',{accessToken:async()=>'PRIVATE-TOKEN'},false,r=>records.push(r));
  assert.equal((await api.load()).workspace.name,'PRIVATE-FOOD');
  assert.equal(records.length,1);
  assert.deepEqual(records[0].server,{auth:0.41,db_read:201.32,db_write:0,compute:2,total:208.12});
  assert.equal(records[0].upstream_requests,1);assert.equal(records[0].auth_method,'jwks');
  assert.ok(records[0].browser_ms>=0);assert.equal(JSON.stringify(records).includes('PRIVATE'),false);
 }finally{global.fetch=original;}
});

test('a diagnostic callback failure never turns a completed save into failure',async()=>{
 const original=global.fetch;let calls=0;
 global.fetch=async()=>{calls++;return new Response(JSON.stringify({revision:1,summary:'saved'}));};
 try{
  const api=createWorkspaceClient('',null,true,()=>{throw Error('diagnostic error');});
  assert.equal((await api.commit({action:'shopping.add',payload:{name:'test'}})).revision,1);
  assert.equal(calls,1);
 }finally{global.fetch=original;}
});

test('failed requests are recorded without automatic command retries',async()=>{
 const original=global.fetch,records=[];let calls=0;
 global.fetch=async()=>{calls++;throw new TypeError('network error');};
 try{
  const api=createWorkspaceClient('',null,true,r=>records.push(r));
  await assert.rejects(api.commit({action:'shopping.check'}),TypeError);
  assert.equal(calls,1);assert.equal(records[0].status,0);assert.deepEqual(records[0].server,{});
 }finally{global.fetch=original;}
});
