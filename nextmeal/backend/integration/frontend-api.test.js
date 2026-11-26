import test from 'node:test';
import assert from 'node:assert/strict';
import {inventoryToView,recipeToView,mealToView,mealCreateBody,inventoryCreateBody,createMealApi} from './frontend-api.js';
const ingredients=[{ingredient_id:'milk',ingredient_name:'우유'}];
test('inventory uses server UUID, canonical ml and freezer mapping',()=>{
 const row=inventoryToView({inventory_id:'uuid',ingredient_id:'milk',quantity:150,unit:'ml',storage_location:'freezer'},ingredients);
 assert.equal(row.id,'uuid');assert.equal(row.unit,'mL');assert.equal(row.storage,'냉동');
});
test('recipe amounts converted to per serving for existing A calculations',()=>{
 const r=recipeToView({recipe_id:'r',recipe_name:'리소토',base_servings:2,cooking_time_minutes:15,ingredients:[{ingredient_id:'milk',required_quantity:300,unit:'ml'}]},ingredients);
 assert.equal(r.ingredients[0].quantity,150);
});
test('meal state and version mapped without changing API contract',()=>{
 const row=mealToView({meal_id:'m',recipe_id:'r',meal_date:'2026-11-13',meal_slot:'dinner',meal_status:'eating_out',servings:1,version:2},[{recipe_id:'r',recipe_name:'리소토'}]);
 assert.equal(row.status,'eaten_out');assert.equal(row.slot,'저녁');assert.equal(row.version,2);
 assert.deepEqual(mealCreateBody(row),{meal_date:'2026-11-13',meal_slot:'dinner',recipe_id:'r',servings:1});
});
test('kg normalizes to grams; packs require explicit quantity conversion',()=>{
 assert.equal(inventoryCreateBody({quantity:0.5,unit:'kg',storage:'냉장'},'id').quantity,500);
 assert.throws(()=>inventoryCreateBody({quantity:1,unit:'팩',storage:'냉장'},'id'));
});
test('API sends user token and expected_version; preserves 409',async()=>{
 const original=globalThis.fetch;let captured;
 try{
  globalThis.fetch=async(url,init)=>{captured={url,init};return new Response(JSON.stringify({detail:'식사가 변경되었습니다.'}),{status:409});};
  const api=createMealApi('http://localhost:8000/',()=> 'test-token');
  await assert.rejects(api.eatOut('m',2),e=>e.status===409);
  assert.equal(captured.init.headers.Authorization,'Bearer test-token');assert.deepEqual(JSON.parse(captured.init.body),{expected_version:2});
 }finally{globalThis.fetch=original;}
});
