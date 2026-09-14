'use strict';
const $ = id => document.getElementById(id);
const fields = ['purpose','description','framing','action','camera','dialogue','continuity','psychology','performance','delivery','rhythm','duration'];
const labels = {purpose:'叙事目的',description:'画面描述',framing:'景别',action:'动作起止',camera:'运镜',dialogue:'台词与文字',continuity:'连续性',psychology:'心理变化',performance:'可见表演',delivery:'逐句台词语气',rhythm:'节奏安排',duration:'时长（秒）'};
const statuses = {pending_sync:'待同步',review:'待确认',needs_direction:'待导演检查',approved:'已确认'};
const token = new URLSearchParams(location.hash.slice(1)).get('token') || '';
let state = null, sid = null, dirty = false, busy = false, nextAction = null;
function el(tag,text,cls){ const node=document.createElement(tag); if(text!==undefined)node.textContent=text; if(cls)node.className=cls; return node; }
function notice(text,error=false){ $('notice').textContent=text; $('notice').classList.toggle('error',error); }
async function api(path,data){const response=await fetch(path,{method:data?'POST':'GET',headers:{'X-Review-Token':token,...(data?{'Content-Type':'application/json'}:{})},body:data?JSON.stringify(data):undefined});const result=await response.json();if(!response.ok)throw Error(result.error||'请求失败');return result;}
function shot(){return state.shots.find(s=>s.id===sid);}
function values(){const zh={};for(const f of fields)zh[f]=f==='duration'?($('duration').value===''?null:Number($('duration').value)):$(f).value;return zh;}
function draftKey(){return `svd-draft:${state.name}:${sid}`;}
function updateDirty(){dirty=JSON.stringify(values())!==JSON.stringify(Object.fromEntries(fields.map(f=>[f,shot().zh[f]??(f==='duration'?null:'')])));
$('saveState').textContent=dirty?'有未保存修改 · 切换镜头前请保存':'已保存到本地项目';
$('save').disabled=!dirty||busy; $('approve').disabled=dirty||busy||shot().status!=='review'||!state.stage_status.analysis||!shot().quality?.ready;
if(dirty)sessionStorage.setItem(draftKey(),JSON.stringify({base_revision:shot().revision,zh:values()}));else {const saved=sessionStorage.getItem(draftKey());if(!saved||JSON.parse(saved).base_revision===shot().revision)sessionStorage.removeItem(draftKey());}
}
function fill(zh){for(const f of fields)$(f).value=zh[f]??'';}
function list(){ $('count').textContent=`${state.shots.filter(s=>s.status==='approved').length} / ${state.shots.length} 已确认`;const filter=$('filter').value; $('shotList').replaceChildren();for(const s of state.shots){if(filter!=='all'&&s.status!==filter)continue;const b=el('button',undefined,'shotItem'+(s.id===sid?' active':'')); b.type='button';b.setAttribute('aria-label',`${s.id} ${s.zh.purpose} ${statuses[s.status]}`);b.setAttribute('aria-current',String(s.id===sid));b.append(el('span',`${s.id} · v${s.revision}`),el('strong',s.zh.purpose||s.zh.description.slice(0,30)),el('small',`${s.zh.duration??'待定'} 秒 · ${statuses[s.status]}`));b.onclick=()=>guard(()=>{sid=s.id;render();});$('shotList').append(b);}}
function stagebar(){
 const box=$('stages');box.replaceChildren();
 const entries=[['analysis','① 剧情分析'],['storyboard','② 中文分镜 / 系统文本'],['layout','③ 平面布局'],['previs','④ 白模预演'],['assets','⑤ 资产生产']];
 for(const [key,name] of entries){
  const done=key==='storyboard'?state.shots.every(s=>s.status==='approved'):key==='assets'?state.pending.length===0:state.stage_status[key];
  const item=el('div',undefined,'stage'+(done?' done':''));
  const skipped=key==='previs'&&done&&state.previs.required===false;
  item.append(el('b',name),el('span',key==='assets'?(done?'可开始':'待前置确认'):skipped?'已跳过（未验证）':done?'✓':'待完成'));
  if(key==='previs'){
   const ready=state.stage_status.layout&&state.shots.every(s=>s.status==='approved');
   item.append(el('small','后台生成；仅按需打开结果视频'));
   if(state.previs_run&&!done){const names={running:'后台运行中',failed:'运行失败，请查看日志',smoke_frames_rendered_awaiting_review:'少量帧已生成，待检查',video_rendered_awaiting_review:'视频已生成，待检查',blend_built:'白模已建立'};item.append(el('small',names[state.previs_run.status]||'预演结果待检查'));}
   if(!done||skipped){
    const generate=el('button',skipped?'改为生成预演':'生成预演','secondary');generate.type='button';generate.disabled=busy||!ready;
    generate.onclick=()=>guard(()=>choosePrevis('generate'));item.append(generate);
   }
   if(!skipped){const skip=el('button','跳过预演，继续资产','secondary');skip.type='button';skip.disabled=busy||!ready;skip.onclick=()=>guard(()=>choosePrevis('skip'));item.append(skip);}
   if(!done&&state.previs.required&&state.previs.files.length){const confirm=el('button','确认已查看的预演','secondary');confirm.type='button';confirm.disabled=busy||!ready;confirm.onclick=()=>guard(()=>confirmStage('previs'));item.append(confirm);}
  }else if(['analysis','layout'].includes(key)&&!done){const button=el('button','确认','secondary');button.type='button';button.disabled=busy||(key!=='analysis'&&(!state.stage_status.analysis||!state.shots.every(s=>s.status==='approved')));button.onclick=()=>guard(()=>confirmStage(key));item.append(button);}
  box.append(item);
 }
}
async function choosePrevis(choice){try{busy=true;state=await api('/api/previs-choice',{choice,revision:state.revision});render();notice(choice==='skip'?'已记录跳过预演；动态空间未验证，可继续资产流程。':'已选择生成预演。回当前 Codex 对话说“继续预演”；渲染在后台执行。');}catch(e){notice(e.message,true);}finally{busy=false;stagebar();updateDirty();}}
async function confirmStage(stage){try{busy=true;state=await api('/api/confirm-stage',{stage,revision:state.revision});render();notice('已记录本阶段确认。');}catch(e){notice(e.message,true);}finally{busy=false;stagebar();updateDirty();}}
function renderDiff(){const s=shot(),index=Number($('historySelect').value),history=s.history[index];const box=$('diff');box.replaceChildren();$('oldTarget').textContent='';$('newTarget').textContent='';if(!history){box.append(el('p','暂无历史版本。保存修改后会自动记录。','muted'));return;}const old=history.snapshot;let count=0;for(const field of fields){if((old.zh[field]??(field==='duration'?null:''))===(s.zh[field]??(field==='duration'?null:'')))continue;count++;const row=el('div',undefined,'diffRow');row.append(el('strong',labels[field]),el('div',String(old.zh[field]??'未设置'),'before'),el('div',String(s.zh[field]??'未设置'),'after'));box.append(row);}if(!count)box.append(el('p','中文内容与此版本相同。','muted'));$('oldTarget').textContent=old.target.text||'该版本尚未编译系统文本';$('newTarget').textContent=s.target.text||'当前尚未编译系统文本';}
function resources(){const box=$('resources');box.replaceChildren();for(const r of state.resources){if(r.path.includes('/shots/')&&!r.path.includes('/shots/'+sid+'/'))continue;if(r.kind==='layout'&&!r.path.endsWith('floor-plan.png')&&!r.path.endsWith('.gltf')&&!r.shots?.includes(sid))continue;if(r.path.endsWith('.json'))continue;const card=el('div',undefined,'resource');const url=`/api/file?path=${encodeURIComponent(r.path)}&token=${encodeURIComponent(token)}`;if(!r.path.startsWith('previs/')&&/\.(png|jpe?g|webp)$/i.test(r.path)){const img=el('img');img.src=url;img.alt=r.label;img.loading='lazy';card.append(img);}else if(/\.(mp4|webm|mov)$/i.test(r.path)){card.append(el('span','预演结果 · 点击链接查看，不在页面自动展示','muted'));}else card.append(el('span',r.kind==='layout'?'空间资料':r.kind==='analysis'?'分析资料':'项目资料','muted'));const a=el('a',r.label);a.href=url;a.target='_blank';a.rel='noopener noreferrer';card.append(a);box.append(card);}}
function render(){if(!sid||!state.shots.some(s=>s.id===sid))sid=state.shots[0].id;const s=shot();$('projectTitle').textContent=state.name;$('targetLabel').textContent=`${state.system.name} · ${state.system.mode}`;stagebar();list();$('shotId').textContent=s.id;$('shotTitle').textContent=s.zh.purpose||'中文分镜';$('version').textContent=`中文 v${s.revision}`;$('shotStatus').textContent=statuses[s.status];$('targetState').textContent=s.status==='pending_sync'?'待同步':state.system.format==='generic'?'通用稿':'逐镜适配稿';fill(s.zh);dirty=false;$('recovery').hidden=true;const draft=sessionStorage.getItem(draftKey());if(draft){try{const d=JSON.parse(draft);if(d.base_revision===s.revision){fill(d.zh);notice('已恢复当前镜头尚未保存的本地编辑。');}else {$('recovery').hidden=false;$('recoveryText').textContent=JSON.stringify(d.zh,null,2);notice('发现旧版本未保存草稿，已保留在中文编辑区下方，可展开复制并合并。',true);}}catch(_){sessionStorage.removeItem(draftKey());}}
$('targetText').textContent=s.target.text||'尚未编译目标系统文本。\n\n中文已从现有分镜导入。请在 Codex 对话中说“同步修改”，由 skill 根据目标系统规则生成对应文本。';$('targetTranslation').textContent=s.target.translation_zh||'尚未补齐系统原文的中文对照。请回 Codex 说“同步修改”。';$('targetHelp').textContent=s.status==='pending_sync'&&s.target.text?'以下系统原文及中文对照均为旧版，尚未反映本次中文修改，不能确认。':'系统原文和下方中文对照绑定同一版本；左侧中文导演稿可编辑。';$('targetNote').textContent=s.target.note||'';$('sources').replaceChildren();for(const url of state.system.sources){const a=el('a','目标系统参考指南 ↗');a.href=url;a.target='_blank';a.rel='noopener noreferrer';$('sources').append(a,document.createElement('br'));}
const impact=$('impact');impact.replaceChildren();if(s.impact){for(const [key,name] of [['shots','相邻镜头'],['layouts','关联布局'],['assets','候选资产']])impact.append(el('p',`${name}：${s.impact[key]?.join('、')||'无'}`));impact.append(el('p',s.impact.review_note||s.impact.note||'等待 Codex 检查','muted'));}else impact.append(el('p','同步时检查动作、位置、台词时长及关联资产。','muted'));
$('historySelect').replaceChildren();s.history.forEach((h,i)=>{const opt=el('option',`v${h.snapshot.revision} · ${h.event==='chinese_edit'?'中文修改前':h.event==='director_review'?'导演检查前':'系统同步前'} · ${new Date(h.at).toLocaleTimeString('zh-CN',{hour12:false})}`);opt.value=i;$('historySelect').append(opt);});if(s.history.length){const latestEdit=s.history.map(h=>h.event).lastIndexOf('chinese_edit');$('historySelect').value=latestEdit>=0?latestEdit:s.history.length-1;}renderDiff();resources();renderQuality();renderGroups();updateDirty();}
function guard(action){if(busy)return;if(!dirty){action();return;}nextAction=action;$('unsaved').showModal();}
async function saveEdit(){if(!$('editor').reportValidity())return false;try{busy=true;$('save').disabled=true;const key=draftKey();const result=await api('/api/edit',{id:sid,zh:values(),revision:state.revision});sessionStorage.removeItem(key);state=result;dirty=false;render();notice('中文修改已保存。请回 Codex 说“同步修改”；同步后在此查看差异并确认。');return true;}catch(e){notice(e.message+' 当前输入已保留。',true);return false;}finally{busy=false;updateDirty();stagebar();}}
async function refresh(){try{state=await api('/api/state');render();notice('已读取项目最新版本。修改中文后保存，再回 Codex 说“同步修改”。');}catch(e){notice(e.message,true);}}
$('editor').addEventListener('input',()=>{if(state)updateDirty();});$('editor').addEventListener('submit',e=>{e.preventDefault();saveEdit();});$('refresh').onclick=()=>guard(refresh);$('filter').onchange=list;$('historySelect').onchange=renderDiff;$('revert').onclick=()=>{sessionStorage.removeItem(draftKey());fill(shot().zh);updateDirty();};$('approve').onclick=async()=>{try{busy=true;state=await api('/api/confirm-shot',{id:sid,revision:state.revision});render();notice(`${sid} 当前版本已确认。`);}catch(e){notice(e.message,true);}finally{busy=false;updateDirty();stagebar();}};
$('stay').onclick=()=>{$('unsaved').close();nextAction=null;};$('discardAndGo').onclick=()=>{sessionStorage.removeItem(draftKey());dirty=false;$('unsaved').close();const go=nextAction;nextAction=null;go?.();};$('saveAndGo').onclick=async()=>{if(await saveEdit()){$('unsaved').close();const go=nextAction;nextAction=null;go?.();}};
window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue='';}});
refresh();
setInterval(async()=>{if(!state||busy||document.hidden)return;try{const incoming=await api('/api/state');if(incoming.revision!==state.revision){notice('项目有新版本。请先保存或复制当前编辑，再点击“刷新项目”查看。');}else if(JSON.stringify(incoming.previs_run)!==JSON.stringify(state.previs_run)){state.previs_run=incoming.previs_run;stagebar();}}catch(_){}},15000);

function renderQuality(){
 const q=shot().quality,box=$('quality');box.replaceChildren();
 if(!q){box.append(el('p','服务需要重启以启用导演检查。','muted'));$('approve').disabled=true;return;}
 box.append(el('strong',q.ready?'导演检查已通过，待你确认':q.review_status==='stale'?'上下文已改变，需要重新检查':'导演稿尚待完善与检查'));
 for(const msg of q.errors)box.append(el('p',msg,'qualityError'));
 for(const msg of q.warnings)box.append(el('p','检查提示：'+msg,'muted'));
 if(q.review){box.append(el('p','全段节奏：'+q.review.sequence_note));const names={narrative:'叙事与信息',character:'人物心理与差异',performance:'表演与逐句语气',pacing:'节奏与时间',continuity:'动作与空间衔接',adaptation:'目标文本与对照'};for(const [k,c] of Object.entries(q.review.checks))box.append(el('p',names[k]+' · '+({pass:'通过',revise:'需修改',not_applicable:'不适用'}[c.status])+'：'+c.note));}
 box.append(el('p','保存后回 Codex 说“同步修改并检查节奏和表演”。字段完整不代表艺术质量；导演检查依据可在此查看。','muted'));
}


function renderGroups(){
 const box=$('generationGroups');box.replaceChildren();box.append(el('h3','生成分组'));
 const data=state.generation_groups;
 if(!data){box.append(el('p','尚未建立分组方案。可回 Codex 说“整理生成分组”。','muted'));return;}
 box.append(el('p',`分组 v${data.revision} · ${data.adapter} · ${data.approved?'方案已确认':'待同步或确认'}`));
 box.append(el('p','按剧情组织连续镜头；修改会撤销分组确认。保存后回 Codex 说“同步分组”。这不代表素材已齐备或模型已验证。','muted'));
 for(const msg of data.pending)box.append(el('p',msg,'qualityError'));
 for(const group of data.schedule){
  const row=el('details');row.open=group.shots.includes(sid);row.append(el('summary',`${group.id} · ${group.title} · ${group.duration}秒 · ${group.shots.join('、')}`));
  const inputs={};const storageKey=`svd-group-draft:${state.name}:${group.id}`;let savedDraft=null;try{savedDraft=JSON.parse(sessionStorage.getItem(storageKey));}catch(_){}
  for(const [key,label,value] of [['title','组名',group.title],['shots','镜头编号（逗号分隔，须保持全段顺序）',group.shots.join(',')],['intent_zh','本组导演意图',group.intent_zh],['continuity_in','承接上一组',group.continuity_in],['continuity_out','交给下一组',group.continuity_out]]){
   const wrap=el('label',label),input=el('textarea');input.rows=key==='shots'?1:2;input.value=savedDraft?.revision===data.revision?(savedDraft.values[key]??value):value;inputs[key]=input;input.oninput=()=>sessionStorage.setItem(storageKey,JSON.stringify({revision:data.revision,values:Object.fromEntries(Object.entries(inputs).map(([k,v])=>[k,v.value]))}));wrap.append(input);row.append(wrap);
  }
  if(savedDraft&&savedDraft.revision!==data.revision){const stale=el('details');stale.append(el('summary','旧版分组未保存草稿（可复制后合并）'),el('pre',JSON.stringify(savedDraft.values,null,2)));row.append(stale);}
  row.append(el('p',group.cuts.map((c,i)=>`镜${i+1} ${c.shot}：组内${c.local_start}秒 / 原片${c.original_start}秒`).join('；'),'muted'));
  const target=data.compiled[group.id];row.append(el('h4','本组系统原文'),el('pre',target?.text||'待编译'),el('h4','完整中文对照'),el('pre',target?.translation_zh||'待同步'));
  const save=el('button','保存本组修改','secondary');save.type='button';save.onclick=()=>guard(async()=>{
   try{busy=true;const plan=data.groups.map(g=>({...g,references:g.references.map(r=>({...r})),shots:[...g.shots]}));const selected=plan.find(g=>g.id===group.id);
    for(const key of ['title','intent_zh','continuity_in','continuity_out'])selected[key]=inputs[key].value;
    selected.shots=inputs.shots.value.split(/[,，\s]+/).filter(Boolean);
    state=await api('/api/groups-plan',{revision:data.revision,project_revision:state.revision,adapter:data.adapter,shared_references:data.shared_references,groups:plan});sessionStorage.removeItem(storageKey);render();notice('分组修改已保存，请回 Codex 说“同步分组”。');
   }catch(e){notice(e.message+' 当前分组输入保留。',true);}finally{busy=false;}
  });row.append(save);box.append(row);
 }
 const confirm=el('button','确认分组方案与中英文本');confirm.type='button';confirm.disabled=busy||data.pending.length>0||data.approved;
 confirm.onclick=()=>guard(async()=>{try{busy=true;state=await api('/api/groups-confirm',{revision:data.revision,project_revision:state.revision});render();notice('已记录分组确认，素材与目标导入检查仍单独进行。');}catch(e){notice(e.message,true);}finally{busy=false;}});box.append(confirm);
}
