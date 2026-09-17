// Exercise the real event handlers without a browser or third-party packages.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../assets/grid-review/app.js'),'utf8');
function setup(){
 const requests=[];
 function el(tag){return {tag,dataset:{},children:[],value:'',append(...v){this.children.push(...v)},replaceChildren(){this.children=[]},setAttribute(k,v){this[k]=v}};}
 const ids=Object.fromEntries(['title','nav','main','notice','refresh','validate'].map(k=>[k,el(k)]));
 const descendants=e=>[e,...e.children.flatMap(descendants)];
 const context=vm.createContext({URLSearchParams,location:{hash:'#token=test'},document:{getElementById:k=>ids[k],createElement:el,querySelectorAll:()=>descendants(ids.main).filter(e=>e.dataset.confirm)},window:{addEventListener(){}},setInterval(){},fetch:(url,options)=>new Promise(resolve=>requests.push({url,options,resolve}))});
 vm.runInContext(source,context);
 function state(revision='v1',text='original') {return {name:'test',revision,status:{director:'awaiting_confirmation'},stages:{director:{artifacts:[{path:'director.md',text,exists:true}]}}};}
 function set(value){context.input=value;vm.runInContext('state=input;render()',context);}
 function find(tag,text){return descendants(ids.main).find(e=>e.tag===tag&&(!text||e.textContent===text));}
 function edit(e,text){e.value=text;e.oninput();}
 function respond(index,value){requests[index].resolve({ok:true,json:async()=>value});}
 set(state());
 return {context,requests,ids,state,set,find,edit,respond,all:()=>descendants(ids.main)};
}
const flush=()=>new Promise(resolve=>setImmediate(resolve));
test('clearing feedback and restoring original text release confirmation',()=>{
 const s=setup();const feedback=s.all().find(e=>e.tag==='textarea'&&e.placeholder);
 s.edit(feedback,'change');assert.equal(s.find('button','确认本阶段当前版本').disabled,true);
 s.edit(feedback,'');assert.equal(s.find('button','确认本阶段当前版本').disabled,false);
 const director=s.all().find(e=>e.className==='director');s.edit(director,'changed');s.edit(director,'original');
 assert.equal(s.find('button','确认本阶段当前版本').disabled,false);
 s.edit(director,'changed');s.find('button','撤销本文件修改').onclick();
 assert.equal(s.all().find(e=>e.className==='director').value,'original');
});
test('manual refresh shows current text and requires explicit conflict merge',async()=>{
 const s=setup();s.edit(s.all().find(e=>e.className==='director'),'my draft');
 const p=vm.runInContext('refresh(true)',s.context);s.respond(1,s.state('v2','new server text'));await p;
 assert.equal(s.find('pre').textContent,'new server text');
 assert.equal(s.all().find(e=>e.className==='director').value,'my draft');
 s.find('button','保存导演稿').onclick();assert.equal(s.requests.length,2);
 s.find('button','已完成合并').onclick();s.find('button','保存导演稿').onclick();
 assert.equal(s.requests.length,3);assert.equal(JSON.parse(s.requests[2].options.body).revision,'v2');
});
test('an older polling response cannot replace the result of a save',async()=>{
 const s=setup();s.edit(s.all().find(e=>e.className==='director'),'saved');
 s.find('button','保存导演稿').onclick();s.respond(1,s.state('v2','saved'));await flush();
 s.respond(0,s.state('v1','original'));await flush();
 assert.equal(vm.runInContext('state.revision',s.context),'v2');
 assert.equal(s.all().find(e=>e.className==='director').value,'saved');
});
test('item confirmation uses the selected item and stale item stays disabled',()=>{
 const s=setup(),value=s.state();value.stages.grids={artifacts:[],items:{T1:{files:['one.png']},T2:{files:['two.png']}},item_status:{T1:'awaiting_confirmation',T2:'stale'}};value.status.grids='stale';s.set(value);
 assert.equal(s.find('button','确认 T1').disabled,false);assert.equal(s.find('button','确认 T2').disabled,true);
 s.find('button','确认 T1').onclick();assert.equal(s.requests[1].url,'/api/confirm-item');
 assert.equal(JSON.parse(s.requests[1].options.body).item,'T1');
});
test('typing during a pending save preserves the newer draft',async()=>{
 const s=setup();const area=s.all().find(e=>e.className==='director');
 s.edit(area,'submitted');s.find('button','保存导演稿').onclick();s.edit(area,'newer draft');
 s.respond(1,s.state('v2','submitted'));await flush();
 assert.equal(s.all().find(e=>e.className==='director').value,'newer draft');
 assert.equal(vm.runInContext('drafts.size',s.context),1);
});
