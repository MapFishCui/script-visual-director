const token=new URLSearchParams(location.hash.slice(1)).get('token')||'';
const stages={director:'中文导演稿',characters:'人物四视图与合图',grids:'九宫格关键画面',prompts:'提示词与中文对照'};
const labels={confirmed:'已确认',stale:'文件变更，待重新登记',waiting_upstream:'等待上游确认',awaiting_confirmation:'待确认',pending:'待制作',needs_revision:'待修改'};
let state=null,busy=false;const drafts=new Map();
const $=id=>document.getElementById(id);
function el(tag,text){const e=document.createElement(tag);if(text)e.textContent=text;return e;}
async function api(path,data){const r=await fetch(path,{method:data?'POST':'GET',headers:{'X-Review-Token':token,...(data?{'Content-Type':'application/json'}:{})},body:data?JSON.stringify(data):undefined});const v=await r.json();if(!r.ok)throw Error(v.error);return v;}
function note(text){$('notice').textContent=text;}
async function act(path,data,key){if(busy)return;busy=true;try{const next=await api(path,{...data,revision:state.revision});if(key)drafts.delete(key);state=next;render();note('已保存。需要生成或同步内容时，请回当前对话继续。');}catch(e){note(e.message+'；未保存输入仍保留。');}finally{busy=false;}}
function render(){
 $('title').textContent=state.name+' · 九宫格制作审核';$('nav').replaceChildren();$('main').replaceChildren();
 for(const [stage,title]of Object.entries(stages)){
  const a=el('a',title+' · '+labels[state.status[stage]]);a.href='#token='+encodeURIComponent(token)+'&stage='+stage;a.onclick=e=>{e.preventDefault();document.getElementById(stage).scrollIntoView({behavior:'smooth'});};$('nav').append(a);
  const section=el('section');section.id=stage;section.append(el('h2',title+' · '+labels[state.status[stage]]));
  const row=state.stages[stage];
  if(!row){section.append(el('p','尚未生成。请回当前对话继续。'));$('main').append(section);continue;}
  for(const f of row.artifacts){
   const url='/api/file?path='+encodeURIComponent(f.path)+'&token='+encodeURIComponent(token);const link=el('a',f.path);link.href=url;link.target='_blank';link.rel='noreferrer';section.append(link);
   if(!f.exists){section.append(el('p','文件缺失'));continue;}
   if(/\.(png|jpe?g|webp)$/i.test(f.path)){const im=el('img');im.src=url;im.alt=f.path;section.append(im);}
   if(f.text!==undefined){
    if(stage==='director'&&/\.(md|txt)$/i.test(f.path)){
     const key=stage+':'+f.path,t=el('textarea');t.className='director';t.setAttribute('aria-label','编辑 '+f.path);t.value=drafts.get(key)??f.text;t.oninput=()=>{drafts.set(key,t.value);disableConfirm();};section.append(t);
     const b=el('button','保存导演稿');b.onclick=()=>act('/api/edit',{stage,file:f.path,text:t.value},key);section.append(b);
    }else section.append(el('pre',f.text));
   }
  }
  if(row.feedback)section.append(el('p','修改意见：'+row.feedback));
  const key='feedback:'+stage,t=el('textarea');t.placeholder='需要调整什么？保存后由助手处理。';t.setAttribute('aria-label',title+'修改意见');t.value=drafts.get(key)||'';t.oninput=()=>{drafts.set(key,t.value);disableConfirm();};section.append(t);
  const feedback=el('button','提交修改意见');feedback.onclick=()=>act('/api/feedback',{stage,text:t.value},key);section.append(feedback);
  const confirm=el('button','确认本阶段当前版本');confirm.dataset.confirm=stage;confirm.onclick=()=>act('/api/confirm',{stage});section.append(confirm);section.append(el('small','修改上游内容会撤销下游确认。目标模型生成效果仍需实测。'));$('main').append(section);
 }disableConfirm();
}
function disableConfirm(){document.querySelectorAll('[data-confirm]').forEach(b=>b.disabled=drafts.size>0||state.status[b.dataset.confirm]!=='awaiting_confirmation');}
async function refresh(manual=false){if(busy)return;try{const next=await api('/api/state');if(!state||next.revision!==state.revision){if(drafts.size&&!manual){note('成果已有更新，未覆盖你的输入；请先保留草稿，再点击刷新合并。');return;}state=next;render();if(drafts.size)note('已刷新；你的草稿保留在编辑框，请与最新内容核对后保存。');}else if(manual)note('当前已是最新版本。');}catch(e){note('更新失败：'+e.message);}}
$('refresh').onclick=()=>refresh(true);window.addEventListener('beforeunload',e=>{if(drafts.size){e.preventDefault();e.returnValue='';}});refresh();setInterval(()=>refresh(),3000);
