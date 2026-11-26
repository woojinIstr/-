export const initialInventory = [
 {id:'i1',name:'닭가슴살',quantity:150,unit:'g',storage:'냉장'},
 {id:'i2',name:'닭가슴살',quantity:450,unit:'g',storage:'냉동'},
 {id:'i3',name:'시금치',quantity:100,unit:'g',storage:'냉장'},
 {id:'i4',name:'밥',quantity:420,unit:'g',storage:'냉장'},
 {id:'i5',name:'우유',quantity:750,unit:'mL',storage:'냉장'},
 {id:'i6',name:'파스타면',quantity:300,unit:'g',storage:'실온'}
];
export const recipes = [
 {id:'r1',name:'닭가슴살 시금치 리소토',minutes:15,ingredients:[{name:'닭가슴살',quantity:150,unit:'g'},{name:'시금치',quantity:100,unit:'g'},{name:'밥',quantity:210,unit:'g'},{name:'우유',quantity:150,unit:'mL'}],description:'닭가슴살과 시금치를 활용하는 간단한 한 끼'},
 {id:'r2',name:'닭가슴살 볶음밥',minutes:20,ingredients:[{name:'닭가슴살',quantity:150,unit:'g'},{name:'밥',quantity:210,unit:'g'},{name:'양파',quantity:100,unit:'g'}],description:'닭가슴살과 밥을 활용하는 볶음밥'},
 {id:'r3',name:'토마토 파스타',minutes:25,ingredients:[{name:'파스타면',quantity:100,unit:'g'},{name:'토마토 소스',quantity:150,unit:'g'},{name:'양파',quantity:100,unit:'g'}],description:'파스타면을 활용하는 기본 메뉴'},
 {id:'r4',name:'우유 리소토',minutes:15,ingredients:[{name:'밥',quantity:210,unit:'g'},{name:'우유',quantity:200,unit:'mL'},{name:'양파',quantity:50,unit:'g'}],description:'밥과 우유를 활용하는 부드러운 리소토'}
];
const day = new Date().toLocaleDateString('sv-SE');
export const initialMeals = [
 {id:'m1',date:day,slot:'아침',name:'계란밥',servings:1,status:'planned',recipeId:null},
 {id:'m2',date:day,slot:'점심',name:'닭가슴살 볶음밥',servings:1,status:'planned',recipeId:'r2'},
 {id:'m3',date:day,slot:'저녁',name:'토마토 파스타',servings:1,status:'planned',recipeId:'r3'}
];
export const initialManualShopping=[];
export const fmtQty=(n)=>Number.isInteger(Number(n))?String(Number(n)):Number(n).toFixed(1);
export const id=()=>typeof crypto!=='undefined'&&crypto.randomUUID?crypto.randomUUID():`${Date.now()}-${Math.random()}`;
export function requirements(meals){const map=new Map();for(const m of meals){if(m.status!=='planned'||!m.recipeId)continue;const recipe=recipes.find(r=>r.id===m.recipeId);if(!recipe)continue;for(const ing of recipe.ingredients){const key=ing.name+'|'+ing.unit;map.set(key,(map.get(key)||0)+ing.quantity*(Number(m.servings)||1));}}return [...map].map(([key,quantity])=>{const [name,unit]=key.split('|');return {name,unit,quantity};});}
export function shoppingNeeds(meals,inventory){const inv=new Map();for(const i of inventory){const key=i.name+'|'+i.unit;inv.set(key,(inv.get(key)||0)+Number(i.quantity));}return requirements(meals).map(req=>({...req,quantity:Math.max(0,req.quantity-(inv.get(req.name+'|'+req.unit)||0))})).filter(x=>x.quantity>0);}
export function shoppingDiff(before,after){const key=x=>x.name+'|'+x.unit;const a=new Map(before.map(x=>[key(x),x.quantity]));const b=new Map(after.map(x=>[key(x),x.quantity]));return [...new Set([...a.keys(),...b.keys()])].map(k=>{const [name,unit]=k.split('|');return {name,unit,before:a.get(k)||0,after:b.get(k)||0,delta:(b.get(k)||0)-(a.get(k)||0)};}).filter(x=>x.delta!==0);}
export function formatDate(date){return new Date(date+'T12:00:00').toLocaleDateString('ko-KR',{month:'long',day:'numeric',weekday:'long'});}
