const authMethods=new Set(['jwks','remote-legacy','remote-forced','remote-fallback','jwt-rejected','local-demo']);
function timingHeaders(response){
  const stages={};
  for(const part of (response?.headers?.get('Server-Timing')||'').split(',')){
    const match=part.trim().match(/^(auth|db_read|db_write|compute|total);dur=([\d.]+)$/);
    if(match&&Number.isFinite(Number(match[2])))stages[match[1]]=Number(match[2]);
  }
  const method=response?.headers?.get('X-Auth-Verification');
  const count=response?.headers?.get('X-Upstream-Requests');
  return {server:stages,auth_method:authMethods.has(method)?method:'unknown',upstream_requests:count!==null&&count!==undefined&&/^\d+$/.test(count)?Number(count):null};
}
export function createWorkspaceClient(base, auth, local=false, onTiming=null) {
  async function request(path,body) {
    const started=performance.now();let response,timer;
    try {
      const token=local?'':await auth.accessToken();
      if(!local && !token)throw Object.assign(new Error('다시 로그인하세요.'),{status:401});
      const controller=new AbortController();timer=setTimeout(()=>controller.abort(),45000);
      response=await fetch(base+path,{method:body?'POST':'GET',signal:controller.signal,headers:{...(token?{Authorization:'Bearer '+token}:{}),...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});
      const data=await response.json();
      if(!response.ok)throw Object.assign(new Error(typeof data.detail==='string'?data.detail:'입력값과 단위를 확인하세요.'),{
        status:response.status,
        revisionConflict:response.status===409 && response.headers?.get('X-Conflict-Reason')==='revision'
      });
      return data;
    } finally {
      clearTimeout(timer);
      // Diagnostic failure must never make a completed save look unsuccessful.
      if(onTiming)try{onTiming({path,method:body?'POST':'GET',status:response?.status||0,browser_ms:Number((performance.now()-started).toFixed(2)),...timingHeaders(response)});}catch{}
    }
  }
  return {load:()=>request('/v3/workspace'),preview:c=>request('/v3/preview?compact=true',c),commit:c=>request('/v3/commands',c)};
}
export const dateNow=()=>new Date().toLocaleDateString('sv-SE',{timeZone:'Asia/Seoul'});
export function offsetDate(day,n){const d=new Date(day+'T12:00:00');d.setDate(d.getDate()+n);return d.toLocaleDateString('sv-SE');}
export const unitLabels={g:'g',kg:'kg',ml:'mL',L:'L',count:'개',pack:'포장 단위'};
export const storageLabels={fridge:'냉장',freezer:'냉동',pantry:'실온'};
export const slotLabels={breakfast:'아침',lunch:'점심',dinner:'저녁'};
export const statusLabels={planned:'예정',eating_out:'외식',cancelled:'취소',cooked:'조리 완료'};
export function quantityLabel(lot){const n=x=>Number(x.toFixed(3)).toLocaleString('ko-KR');return lot.pack_size?`${n(lot.quantity/lot.pack_size)}${lot.pack_label} · ${n(lot.quantity)}${unitLabels[lot.unit]}`:`${n(lot.quantity)}${unitLabels[lot.unit]}`;}
export function scaledParts(meal){return meal.recipe.ingredients.map(i=>({...i,quantity:Number((i.quantity*meal.servings/meal.recipe.base_servings).toFixed(6))}));}
