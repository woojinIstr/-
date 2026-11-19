// Copy into A's src/ when wiring server mode. No tokens are stored here.
const unitToView = {g:'g',ml:'mL',count:'개'};
const storageToView = {fridge:'냉장',freezer:'냉동',pantry:'실온'};
const slotToView = {breakfast:'아침',lunch:'점심',dinner:'저녁'};
const statusToView = {planned:'planned',eating_out:'eaten_out',cancelled:'skipped'};
const reverse = object => Object.fromEntries(Object.entries(object).map(([k,v])=>[v,k]));
function required(map,value){if(!(value in map))throw new Error(`지원하지 않는 값: ${value}`);return map[value];}
export function inventoryToView(row,ingredients){
 const ingredient=ingredients.find(i=>i.ingredient_id===row.ingredient_id);
 if(!ingredient)throw new Error('재료 목록을 먼저 조회하세요.');
 return {id:row.inventory_id,ingredientId:row.ingredient_id,name:ingredient.ingredient_name,quantity:row.quantity,unit:required(unitToView,row.unit),storage:required(storageToView,row.storage_location)};
}
export function recipeToView(row,ingredients){
 return {id:row.recipe_id,name:row.recipe_name,minutes:row.cooking_time_minutes,description:row.description,
  ingredients:row.ingredients.map(i=>{
   const found=ingredients.find(item=>item.ingredient_id===i.ingredient_id);
   if(!found)throw new Error('메뉴 재료가 공통 목록에 없습니다.');
   return {name:found.ingredient_name,quantity:i.required_quantity/row.base_servings,unit:required(unitToView,i.unit)};
  })};
}
export function mealToView(row,recipes){
 const recipe=recipes.find(r=>r.recipe_id===row.recipe_id);
 if(!recipe)throw new Error('메뉴 목록을 먼저 조회하세요.');
 return {id:row.meal_id,date:row.meal_date,slot:required(slotToView,row.meal_slot),name:recipe.recipe_name,recipeId:row.recipe_id,servings:row.servings,status:required(statusToView,row.meal_status),version:row.version};
}
export function mealCreateBody(form){
 return {meal_date:form.date,meal_slot:required(reverse(slotToView),form.slot),recipe_id:form.recipeId,servings:Number(form.servings)};
}
export function inventoryCreateBody(form,ingredientId){
 let quantity=Number(form.quantity),unit=form.unit;
 if(unit==='kg'){quantity*=1000;unit='g';}
 if(unit==='L'){quantity*=1000;unit='mL';}
 return {ingredient_id:ingredientId,quantity,unit:required(reverse(unitToView),unit),storage_location:required(reverse(storageToView),form.storage)};
}
export function createMealApi(baseUrl,getAccessToken){
 const base=baseUrl.replace(/\/$/,'');
 async function request(path,{method='GET',body}={}){
  const token=await getAccessToken();
  if(!token)throw new Error('로그인 후 사용하세요.');
  const response=await fetch(base+path,{method,headers:{Authorization:`Bearer ${token}`,...(body===undefined?{}:{'Content-Type':'application/json'})},...(body===undefined?{}:{body:JSON.stringify(body)})});
  const data=response.status===204?null:await response.json();
  if(!response.ok){const error=new Error(typeof data?.detail==='string'?data.detail:'요청을 처리하지 못했습니다.');error.status=response.status;throw error;}
  return data;
 }
 async function list(path){
  const rows=[];let offset=0;
  while(true){const page=await request(`${path}${path.includes('?')?'&':'?'}limit=100&offset=${offset}`);rows.push(...page);if(page.length<100)return rows;offset+=page.length;}
 }
 return {
  ingredients:()=>list('/ingredients'), inventory:()=>list('/inventory'), recipes:()=>list('/recipes'),
  meals:date=>list('/meals'+(date?'?meal_date='+encodeURIComponent(date):'')),
  createMeal:body=>request('/meals',{method:'POST',body}),
  patchMeal:(id,version,changes)=>request('/meals/'+encodeURIComponent(id),{method:'PATCH',body:{...changes,expected_version:version}}),
  eatOut:(id,version)=>request('/meals/'+encodeURIComponent(id)+'/eat-out',{method:'POST',body:{expected_version:version}}),
  cancelMeal:(id,version)=>request('/meals/'+encodeURIComponent(id)+'/cancel',{method:'POST',body:{expected_version:version}}),
 };
}
