'use strict';
const $ = id => document.getElementById(id);
const fields = ['purpose','framing','camera','description','action','dialogue','continuity','psychology','performance','delivery','rhythm','duration'];
const labels = {purpose:'叙事目的',description:'场景',framing:'景别与机位',action:'人物运动',camera:'镜头运动',dialogue:'台词与文字',continuity:'连续性',psychology:'心理变化',performance:'可见表演',delivery:'逐句台词语气',rhythm:'节奏安排',duration:'时长（秒）'};
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
  const done=key==='storyboard'?(state.shots.length>0&&state.shots.every(s=>s.status==='approved')):key==='assets'?state.production?.complete:state.stage_status[key];
  const item=el('div',undefined,'stage'+(done?' done':''));
  const skipped=key==='previs'&&done&&state.previs.required===false;
  item.append(el('b',name),el('span',key==='assets'?(done?'已完成':state.pending.length?'待前置确认':`已完成 ${state.production?.completed??0} / ${state.production?.total??0}`):skipped?'已跳过（未验证）':done?'✓':'待完成'));
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
  }else if(['analysis','layout'].includes(key)&&!done){const button=el('button','确认','secondary');button.type='button';button.disabled=busy||!state.initialized||(key!=='analysis'&&(!state.stage_status.analysis||!state.shots.every(s=>s.status==='approved')));button.onclick=()=>guard(()=>confirmStage(key));item.append(button);}
  box.append(item);
 }
}
async function choosePrevis(choice){try{busy=true;state=await api('/api/previs-choice',{choice,revision:state.revision});render();notice(choice==='skip'?'已记录跳过预演；动态空间未验证，可继续资产流程。':'已选择生成预演。回当前 Codex 对话说“继续预演”；渲染在后台执行。');}catch(e){notice(e.message,true);}finally{busy=false;stagebar();updateDirty();}}
async function confirmStage(stage){try{busy=true;state=await api('/api/confirm-stage',{stage,revision:state.revision});render();notice('已记录本阶段确认。');}catch(e){notice(e.message,true);}finally{busy=false;stagebar();updateDirty();}}
function renderDiff(){const s=shot(),index=Number($('historySelect').value),history=s.history[index];const box=$('diff');box.replaceChildren();$('oldTarget').textContent='';$('newTarget').textContent='';if(!history){box.append(el('p','暂无历史版本。保存修改后会自动记录。','muted'));return;}const old=history.snapshot;let count=0;for(const field of fields){if((old.zh[field]??(field==='duration'?null:''))===(s.zh[field]??(field==='duration'?null:'')))continue;count++;const row=el('div',undefined,'diffRow');row.append(el('strong',labels[field]),el('div',String(old.zh[field]??'未设置'),'before'),el('div',String(s.zh[field]??'未设置'),'after'));box.append(row);}if(!count)box.append(el('p','中文内容与此版本相同。','muted'));$('oldTarget').textContent=old.target.text||'该版本尚未编译系统文本';$('newTarget').textContent=s.target.text||'当前尚未编译系统文本';}
function resources(){const box=$('resources');box.replaceChildren();for(const r of state.resources){if(r.path.includes('/shots/')&&!r.path.includes('/shots/'+sid+'/'))continue;if(r.kind==='layout'&&!r.path.endsWith('floor-plan.png')&&!r.path.endsWith('.gltf')&&!r.shots?.includes(sid))continue;if(r.path.endsWith('.json'))continue;const card=el('div',undefined,'resource');const url=`/api/file?path=${encodeURIComponent(r.path)}&token=${encodeURIComponent(token)}`;if(!r.path.startsWith('previs/')&&/\.(png|jpe?g|webp)$/i.test(r.path)){const img=el('img');img.src=url;img.alt=r.label;img.loading='lazy';card.append(img);}else if(/\.(mp4|webm|mov)$/i.test(r.path)){card.append(el('span','预演结果 · 点击链接查看，不在页面自动展示','muted'));}else card.append(el('span',r.kind==='layout'?'空间资料':r.kind==='analysis'?'分析资料':'项目资料','muted'));const a=el('a',r.label);a.href=url;a.target='_blank';a.rel='noopener noreferrer';card.append(a);box.append(card);}}
function render(){
$('projectTitle').textContent=state.name;$('targetLabel').textContent=`${state.system.name} · ${state.system.mode}`;
document.querySelector('main').hidden=!state.shots.length;
if(!state.shots.length){stagebar();renderOverview();return;}
if(!sid||!state.shots.some(s=>s.id===sid))sid=state.shots[0].id;const s=shot();$('projectTitle').textContent=state.name;$('targetLabel').textContent=`${state.system.name} · ${state.system.mode}`;stagebar();renderOverview();list();$('shotId').textContent=s.id;$('shotTitle').textContent=s.zh.purpose||'中文分镜';$('version').textContent=`中文 v${s.revision}`;$('shotStatus').textContent=statuses[s.status];$('targetState').textContent=s.status==='pending_sync'?'待同步':state.system.format==='generic'?'通用稿':'逐镜适配稿';fill(s.zh);dirty=false;$('recovery').hidden=true;const draft=sessionStorage.getItem(draftKey());if(draft){try{const d=JSON.parse(draft);if(d.base_revision===s.revision){fill(d.zh);notice('已恢复当前镜头尚未保存的本地编辑。');}else {$('recovery').hidden=false;$('recoveryText').textContent=JSON.stringify(d.zh,null,2);notice('发现旧版本未保存草稿，已保留在中文编辑区下方，可展开复制并合并。',true);}}catch(_){sessionStorage.removeItem(draftKey());}}
$('targetText').textContent=s.target.text||'尚未编译目标系统文本。\n\n中文已从现有分镜导入。请在 Codex 对话中说“同步修改”，由 skill 根据目标系统规则生成对应文本。';$('targetTranslation').textContent=s.target.translation_zh||'尚未补齐系统原文的中文对照。请回 Codex 说“同步修改”。';$('targetHelp').textContent=s.status==='pending_sync'&&s.target.text?'以下系统原文及中文对照均为旧版，尚未反映本次中文修改，不能确认。':'系统原文和下方中文对照绑定同一版本；左侧中文导演稿可编辑。';$('targetNote').textContent=s.target.note||'';$('sources').replaceChildren();for(const url of state.system.sources){const a=el('a','目标系统参考指南 ↗');a.href=url;a.target='_blank';a.rel='noopener noreferrer';$('sources').append(a,document.createElement('br'));}
const impact=$('impact');impact.replaceChildren();if(s.impact){for(const [key,name] of [['shots','相邻镜头'],['layouts','关联布局'],['assets','候选资产']])impact.append(el('p',`${name}：${s.impact[key]?.join('、')||'无'}`));impact.append(el('p',s.impact.review_note||s.impact.note||'等待 Codex 检查','muted'));}else impact.append(el('p','同步时检查动作、位置、台词时长及关联资产。','muted'));
$('historySelect').replaceChildren();s.history.forEach((h,i)=>{const opt=el('option',`v${h.snapshot.revision} · ${h.event==='chinese_edit'?'中文修改前':h.event==='director_review'?'导演检查前':'系统同步前'} · ${new Date(h.at).toLocaleTimeString('zh-CN',{hour12:false})}`);opt.value=i;$('historySelect').append(opt);});if(s.history.length){const latestEdit=s.history.map(h=>h.event).lastIndexOf('chinese_edit');$('historySelect').value=latestEdit>=0?latestEdit:s.history.length-1;}renderDiff();resources();renderQuality();renderGroups();updateDirty();}
function guard(action){if(busy)return;if(!dirty){action();return;}nextAction=action;$('unsaved').showModal();}
async function saveEdit(){if(!$('editor').reportValidity())return false;try{busy=true;$('save').disabled=true;const key=draftKey();const result=await api('/api/edit',{id:sid,zh:values(),revision:state.revision});sessionStorage.removeItem(key);state=result;dirty=false;render();notice('中文修改已保存。请回 Codex 说“同步修改”；同步后在此查看差异并确认。');return true;}catch(e){notice(e.message+' 当前输入已保留。',true);return false;}finally{busy=false;updateDirty();stagebar();}}
async function refresh(){try{state=await api('/api/state');render();notice('已读取项目最新版本。'+(state.production?.next_action||'请查看当前阶段。'));}catch(e){notice(e.message,true);}}
$('editor').addEventListener('input',()=>{if(state)updateDirty();});$('editor').addEventListener('submit',e=>{e.preventDefault();saveEdit();});$('refresh').onclick=()=>guard(refresh);$('filter').onchange=()=>{if(state?.shots.length)list();};$('historySelect').onchange=renderDiff;$('revert').onclick=()=>{sessionStorage.removeItem(draftKey());fill(shot().zh);updateDirty();};$('approve').onclick=async()=>{try{busy=true;state=await api('/api/confirm-shot',{id:sid,revision:state.revision});render();notice(`${sid} 当前版本已确认。`);}catch(e){notice(e.message,true);}finally{busy=false;updateDirty();stagebar();}};
$('stay').onclick=()=>{$('unsaved').close();nextAction=null;};$('discardAndGo').onclick=()=>{sessionStorage.removeItem(draftKey());dirty=false;$('unsaved').close();const go=nextAction;nextAction=null;go?.();};$('saveAndGo').onclick=async()=>{if(await saveEdit()){$('unsaved').close();const go=nextAction;nextAction=null;go?.();}};
window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue='';}});
refresh();
function hasLocalEdits(){
 if(dirty||document.activeElement?.matches('input,textarea,select'))return true;
 for(let i=0;i<sessionStorage.length;i++){
  const key=sessionStorage.key(i);
  if(['svd-draft:','svd-group-draft:','svd-director-draft:'].some(prefix=>key.startsWith(prefix+state.name+':')))return true;
 }
 return false;
}
async function readLatestSafely(){
 const incoming=await api('/api/state');
 const changed=incoming.revision!==state.revision||incoming.display_fingerprint!==state.display_fingerprint;
 if(changed&&!busy&&!hasLocalEdits()){
  const openIds=[...document.querySelectorAll('details[id][open]')].map(node=>node.id);
  state=incoming;render();for(const id of openIds)if($(id))$(id).open=true;
  return true;
 }
 if(changed)notice('项目有新版本。已保留未保存草稿，请保存或复制编辑后点击“刷新项目”。');
 return !changed;
}
async function navigateSection(id,label){
 if(busy)return;
 try{
  const current=await readLatestSafely();
  const target=$(id);
  let message='已定位：'+label;
  if(!target||target.closest('[hidden]'))message=current?'尚未生成'+label+'。请在当前 Codex 对话中继续制作。':'项目已有更新；请先保存或复制编辑，再刷新项目查看'+label+'。';
  else{
   for(let node=target;node;node=node.parentElement)if(node.tagName==='DETAILS')node.open=true;
   target.tabIndex=-1;target.focus({preventScroll:true});target.scrollIntoView({behavior:'smooth',block:'start'});
   target.classList.remove('navigationTarget');void target.offsetWidth;target.classList.add('navigationTarget');
   if(id==='assetGallery'&&!state.production?.total)message='资产尚未生成；这里会展示基准图与扩展资产。';
  }
  $('navigationStatus').textContent=message;notice(message);
 }catch(e){$('navigationStatus').textContent='读取失败：'+e.message;notice(e.message,true);}
}
setInterval(async()=>{if(!state||busy||document.hidden)return;try{await readLatestSafely();}catch(_){}},15000);

function renderQuality(){
 const q=shot().quality,box=$('quality');box.replaceChildren();
 if(!q){box.append(el('p','服务需要重启以启用导演检查。','muted'));$('approve').disabled=true;return;}
 box.append(el('strong',q.ready?'文字导演检查已通过，待你确认':q.review_status==='stale'?'上下文已改变，需要重新检查':'导演稿尚待完善与检查'));
 for(const msg of q.errors)box.append(el('p',msg,'qualityError'));
 for(const f of q.findings||[]){const item=el('details');item.open=true;item.append(el('summary',`${sid} · ${f.rule} · ${labels[f.field]||f.field}`),el('pre',f.excerpt),el('p','修改建议：'+f.suggestion));box.append(item);}
 for(const msg of q.warnings)box.append(el('p','检查提示：'+msg,'muted'));
 if(q.review){box.append(el('p','全段节奏：'+q.review.sequence_note));const names={narrative:'叙事与信息',character:'人物心理与差异',performance:'表演与逐句语气',pacing:'节奏与时间',continuity:'动作与空间衔接',adaptation:'目标文本与对照',standards:'直白表达、镜头顺序与官方格式'};for(const [k,c] of Object.entries(q.review.checks))box.append(el('p',names[k]+' · '+({pass:'通过',revise:'需修改',not_applicable:'不适用'}[c.status])+'：'+c.note));}
 box.append(el('p','检查范围：剧情、人物、表演语气、节奏、连续性、目标适配、写作规范。通过仅代表当前版本文字审阅；未验证H3实际生成效果与三维空间。','muted'));
 box.append(el('p','保存后回 Codex 说“同步修改并检查节奏和表演”。字段完整不代表艺术质量；导演检查依据可在此查看。','muted'));
}


function renderGroups(){
 const box=$('generationGroups');box.replaceChildren();box.append(el('h3','导演组与视频段任务'));
 const data=state.generation_groups;
 if(!data){box.append(el('p','尚未建立分组方案。可回 Codex 说“整理生成分组”。','muted'));return;}
 box.append(el('p',`分组 v${data.revision} · ${data.adapter} · ${data.approved?'方案已确认':'待同步或确认'}`));
 box.append(el('p','导演组对应一次合并输出，可为53秒、48秒或更长；内部视频段分别生成。H3的15秒预算只检查内部任务。修改后回 Codex 说“同步分组”。','muted'));
 renderDirectorGroups(box,data);
 for(const msg of data.pending)box.append(el('p',msg,'qualityError'));
 for(const group of data.schedule){
  const row=el('details');row.open=group.shots.includes(sid);row.append(el('summary',`视频段任务 ${group.id} · ${group.title} · ${group.duration}秒 · ${group.shots.join('、')}`));
  const inputs={};const storageKey=`svd-group-draft:${state.name}:${group.id}`;let savedDraft=null;try{savedDraft=JSON.parse(sessionStorage.getItem(storageKey));}catch(_){}
  for(const [key,label,value] of [['title','视频段名称',group.title],['shots','镜头编号（逗号分隔，须保持全段顺序）',group.shots.join(',')],['intent_zh','本段在导演组中的作用',group.intent_zh],['continuity_in','承接上一段',group.continuity_in],['continuity_out','交给下一段',group.continuity_out]]){
   const wrap=el('label',label),input=el('textarea');input.rows=key==='shots'?1:2;input.value=savedDraft?.revision===data.revision?(savedDraft.values[key]??value):value;inputs[key]=input;input.oninput=()=>sessionStorage.setItem(storageKey,JSON.stringify({revision:data.revision,values:Object.fromEntries(Object.entries(inputs).map(([k,v])=>[k,v.value]))}));wrap.append(input);row.append(wrap);
  }
  if(savedDraft&&savedDraft.revision!==data.revision){const stale=el('details');stale.append(el('summary','旧版分组未保存草稿（可复制后合并）'),el('pre',JSON.stringify(savedDraft.values,null,2)));row.append(stale);}
  row.append(el('p',group.cuts.map((c,i)=>`镜${i+1} ${c.shot}：组内${c.local_start}秒 / 原片${c.original_start}秒`).join('；'),'muted'));
  const target=data.compiled[group.id];row.append(el('h4','本任务系统原文'),el('pre',target?.text||'待编译'),el('h4','完整中文对照'),el('pre',target?.translation_zh||'待同步'));
  const save=el('button','保存本任务修改','secondary');save.type='button';save.onclick=()=>guard(async()=>{
   try{busy=true;const plan=data.groups.map(g=>({...g,references:g.references.map(r=>({...r})),shots:[...g.shots]}));const selected=plan.find(g=>g.id===group.id);
    for(const key of ['title','intent_zh','continuity_in','continuity_out'])selected[key]=inputs[key].value;
    selected.shots=inputs.shots.value.split(/[,，\s]+/).filter(Boolean);
    state=await api('/api/groups-plan',{revision:data.revision,project_revision:state.revision,adapter:data.adapter,shared_references:data.shared_references,groups:plan,...(data.director_groups?.length?{director_groups:data.director_groups}:{})});sessionStorage.removeItem(storageKey);render();notice('分组修改已保存，请回 Codex 说“同步分组”。');
   }catch(e){notice(e.message+' 当前分组输入保留。',true);}finally{busy=false;}
  });row.append(save);box.append(row);
 }
 const confirm=el('button','确认导演组、视频段与中英文本');confirm.type='button';confirm.disabled=busy||data.pending.length>0||data.approved;
 confirm.onclick=()=>guard(async()=>{try{busy=true;state=await api('/api/groups-confirm',{revision:data.revision,project_revision:state.revision});render();notice('已记录分组确认，素材与目标导入检查仍单独进行。');}catch(e){notice(e.message,true);}finally{busy=false;}});box.append(confirm);
}

function renderOverview(){
 const box=$('projectOverview'),p=state.production;box.replaceChildren();
 box.append(el('h2','项目进度与成果'),el('p',p?.next_action||'读取阶段进度中'));
 if(state.series){box.append(el('p',`剧集：${state.series.name} · 本集：${state.series.episode} · 继承记录 ${state.series.items.length} 项（锁定版本）`));
  for(const issue of state.series.verification.errors)box.append(el('p',issue,'qualityError'));
 }else box.append(el('p','剧集共享资产：尚未绑定。制作后续集时，可在 Codex 指定共享库并选择要继承的版本。','muted'));
 const phases=el('div',undefined,'actions');
 for(const [label,value] of [
  ['剧情分析',state.stage_status.analysis?'已确认':'待确认'],
  ['分镜',`${state.shots.filter(s=>s.status==='approved').length}/${state.shots.length} 已确认`],
  ['导演组 / 视频段',state.generation_groups?`${state.generation_groups.director_schedule?.length??0}组 / ${state.generation_groups.schedule.length}段 · ${state.generation_groups.approved?'已确认':'待确认'}`:'待规划'],
  ['布局',state.stage_status.layout?'已确认':'待确认'],
  ['预演',state.stage_status.previs?(state.previs.required?'已确认':'已跳过'):'待选择／完成／确认'],
  ['基准与扩展资产',p?.total?`${p.completed}/${p.total} 已完成`:'尚未登记'],
  ['交付',p?.complete?'待核对导出说明':'待前置完成']])phases.append(el('span',`${label}：${value}`,'tag'));
 box.append(phases);
 box.append(el('p','每次确认后回当前 Codex 对话说“继续”。页面不会自动调用模型。资产与交付资料覆盖整个项目，不随当前镜头筛选。','muted'));
 const nav=el('div',undefined,'actions');
 for(const [id,label] of [['shotList','分镜'],['generationGroups','生成分组'],['allResources','布局、预演与交付'],['assetGallery','资产审阅']]){const button=el('button',label,'secondary');button.type='button';button.onclick=()=>navigateSection(id,label);nav.append(button);}box.append(nav);
 const issues=el('details');issues.id='projectIssues';
 const problemShots=state.shots.filter(s=>!s.quality?.ready);
 issues.append(el('summary',`全片导演检查 · ${problemShots.length} 镜待处理 / ${state.shots.length} 镜`));
 for(const s of problemShots){const row=el('div');row.append(el('strong',s.id));for(const msg of s.quality?.errors||[])row.append(el('p',msg,'qualityError'));for(const f of s.quality?.findings||[])row.append(el('pre',f.excerpt),el('p','修改建议：'+f.suggestion));for(const [key,c] of Object.entries(s.quality?.review?.checks||{}))if(c.status==='revise')row.append(el('p',key+'：'+c.note,'qualityError'));if(!s.quality?.errors?.length)row.append(el('p','当前版本仍需完整导演检查，查看逐镜检查依据。','muted'));issues.append(row);}box.append(issues);
 const navigationStatus=el('p',undefined,'muted');navigationStatus.id='navigationStatus';navigationStatus.setAttribute('role','status');box.append(navigationStatus);
 const gallery=el('details');gallery.id='assetGallery';gallery.open=state.pending.length===0;
 gallery.append(el('summary',`资产审阅 · 已完成 ${p?.completed??0} / ${p?.total??0}`));
 if(!p?.total)gallery.append(el('p','尚未登记资产需求。前置阶段确认完毕后，由 Codex 整理清单并生成基准图。','muted'));
 const cards=el('div',undefined,'resources');
 const names={planned:'待生成',prompt_ready:'提示词就绪',generated:'已生成',failed:'生成失败',current:'当前有效',stale:'依赖已过期',superseded:'已替代',pending:'待确认',approved:'已确认',rejected:'需修改',not_required:'无需单独确认',passed:'已检查',needs_revision:'需修改'};
 for(const a of p?.assets||[]){const card=el('div',undefined,'resource');card.append(el('strong',`${a.name} · ${a.id} · v${a.version}`));
  if(a.file){const url=resourceUrl(a.file),link=el('a');link.href=url;link.target='_blank';link.rel='noopener noreferrer';const img=el('img');img.src=url;img.alt=a.name;img.loading='lazy';link.append(img);card.append(link);}
  card.append(el('p',`${names[a.production]} · ${names[a.validity]} · 检查：${a.review.status==='pending'?'待检查':names[a.review.status]} · 用户：${names[a.approval.status]}`));
  card.append(el('p',`关联镜头：${a.shots.join('、')}`,'muted'));
  if(a.inheritance){const origin=a.inheritance;card.append(el('p',`继承自 ${origin.source_episode} · ${origin.library_asset}@${origin.library_version} · ${origin.mode==='reuse'?'同图复用':'参考候选'}`));card.append(el('p',origin.continuity_note,'muted'));}
  if(a.review.note)card.append(el('p',a.review.note));
  for(const reason of a.blocked_by)card.append(el('p',reason,'qualityError'));
  cards.append(card);
 }gallery.append(cards,el('p','确认基准时，请回 Codex 指明资产名称或编号及版本；确认会登记到项目，再解锁依赖它的扩展图。','muted'));box.append(gallery);
 const files=el('details');files.id='allResources';files.open=state.stage_status.layout;
 files.append(el('summary','全项目资料 · 分析、布局、逐镜／分组预演与交付文件'));
 const links=el('div',undefined,'resources'),technical=el('details'),techLinks=el('div',undefined,'resources'),seen=new Set();technical.append(el('summary','版本历史与技术文件'));
 for(const item of state.resources){if(item.kind==='asset'||seen.has(item.path))continue;seen.add(item.path);const card=el('div',undefined,'resource');
  const title=resourceTitle(item.path);const a=el('a',title||item.label);a.href=resourceUrl(item.path);a.title=item.path;a.target='_blank';a.rel='noopener noreferrer';card.append(a);(title?links:techLinks).append(card);
 }technical.append(techLinks);files.append(links,technical,el('p','视频点击后查看；文件存在仅代表已产出，是否确认、是否为草稿及缺失项以阶段状态和交付说明为准。','muted'));box.append(files);
}
function resourceUrl(path){return `/api/file?path=${encodeURIComponent(path)}&token=${encodeURIComponent(token)}`;}

function resourceTitle(path){
 const name=path.split('/').pop(),scope=path.match(/(?:shots|groups)\/(?:[^/]+\/)?(SHOT_\d+|[GTD]\d+)\//)?.[1]||path.match(/\/(SHOT_\d+|[GTD]\d+)\//)?.[1]||'';
 const names={'creative-treatment.md':'电影化改编稿','source.md':'原始剧本','narrative-analysis.md':'剧情与节奏分析','character-analysis.md':'角色心理分析','visual-guide.md':'美术风格方案','spatial-plan.md':'空间布局说明','director-review.md':'导演检查说明','floor-plan.png':'场景平面图','layout-overview.png':'布局总览','escape-routes.png':'人物路线图','key-cameras.png':'关键机位图','review-notes.md':'预演检查与待修改项'};
 if(names[name])return names[name];
 if(path.endsWith('.zip'))return (path.includes('draft')?'交付草稿 · ':'交付文件 · ')+name;
 if(/\.(mp4|webm|mov)$/i.test(path)&&scope.startsWith('D'))return `${scope} · 整组节奏审核视频（不作单次参考）`;
 if(/\.(mp4|webm|mov)$/i.test(path))return `${scope||'串联片'} · ${/reference/.test(name)?'摄影机参考视频':'预演审核视频'}`;
 if(path==='README.md')return '项目说明与当前交付范围';
 if(path==='groups/review.md')return '分组方案与完整中文对照';
 return null;
}

function renderDirectorGroups(box,data){
 box.append(el('h4','导演组 · 每组一次合并输出'));
 if(!data.director_schedule?.length)box.append(el('p','当前为旧版短任务列表，尚未划分导演组。回 Codex 说“按剧情组织导演组”；保留原任务和镜头。','qualityError'));
 for(const group of data.director_schedule||[]){
  const row=el('details');row.open=group.shots.includes(sid);
  row.append(el('summary',`${group.id} · ${group.title} · 合并 ${group.duration} 秒 → ${group.output_file}`));
  const inputs={};const key=`svd-director-draft:${state.name}:${group.id}`;
  let draft=null;try{draft=JSON.parse(sessionStorage.getItem(key));}catch(_){}
  for(const [field,label] of [['title','导演组名称'],['tasks','内部视频段任务（按合并顺序）'],['intent_zh','完整段落：观众体验与情绪起伏'],['continuity_in','段落进入状态'],['continuity_out','段落结束与悬念']]){
   const wrap=el('label',label),input=el('textarea');input.rows=2;
   input.value=draft?.revision===data.revision?draft.values[field]:(field==='tasks'?group.tasks.join(','):group[field]);inputs[field]=input;
   input.oninput=()=>sessionStorage.setItem(key,JSON.stringify({revision:data.revision,values:Object.fromEntries(Object.entries(inputs).map(([k,v])=>[k,v.value]))}));wrap.append(input);row.append(wrap);
  }
  if(draft&&draft.revision!==data.revision){const old=el('details');old.append(el('summary','旧版本未保存导演组草稿'),el('pre',JSON.stringify(draft.values,null,2)));row.append(old);}
  row.append(el('p',group.segments.map(t=>`${t.id}：组内 ${t.start}–${t.start+t.duration} 秒`).join('；'),'muted'));
  const save=el('button','保存导演组修改','secondary');save.type='button';save.onclick=()=>guard(async()=>{
   try{busy=true;const directors=data.director_groups.map(g=>({...g,tasks:[...g.tasks]}));const selected=directors.find(g=>g.id===group.id);
    for(const field of ['title','intent_zh','continuity_in','continuity_out'])selected[field]=inputs[field].value;
    selected.tasks=inputs.tasks.value.split(/[,，\s]+/).filter(Boolean);
    state=await api('/api/groups-plan',{revision:data.revision,project_revision:state.revision,adapter:data.adapter,shared_references:data.shared_references,groups:data.groups,director_groups:directors});sessionStorage.removeItem(key);render();notice('导演组已保存，回 Codex 同步内部任务文本和衔接。');
   }catch(e){notice(e.message+' 当前输入已保留。',true);}finally{busy=false;}
  });row.append(save);box.append(row);
 }
 box.append(el('h4','内部视频段 · 一段一次生成任务'));
}
