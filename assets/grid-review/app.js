const token = new URLSearchParams(location.hash.slice(1)).get('token') || '';
const stages = {director: '中文导演稿', characters: '人物四视图与合图', grids: '九宫格关键画面', prompts: '提示词与中文对照'};
const labels = {confirmed: '已确认', stale: '文件或依赖变更，待重新登记', waiting_upstream: '等待上游确认', awaiting_confirmation: '待确认', pending: '待制作', needs_revision: '待修改'};
let state = null, busy = false, requestVersion = 0;
const drafts = new Map();
const $ = id => document.getElementById(id);
function el(tag, text) {
  const element = document.createElement(tag);
  if (text) element.textContent = text;
  return element;
}
function button(text, action) {
  const element = el('button', text);
  element.onclick = action;
  return element;
}
function note(text) { $('notice').textContent = text; }
async function api(path, data) {
  const response = await fetch(path, {
    method: data ? 'POST' : 'GET',
    headers: {'X-Review-Token': token, ...(data ? {'Content-Type': 'application/json'} : {})},
    body: data ? JSON.stringify(data) : undefined
  });
  const value = await response.json();
  if (!response.ok) throw Error(value.error);
  return value;
}
async function act(path, data, key) {
  if (busy) return;
  busy = true;
  requestVersion++;
  try {
    const next = await api(path, {...data, revision: state.revision});
    if (key && drafts.get(key)?.text === data.text) drafts.delete(key);
    state = next;
    render();
    note('已保存。需要生成或同步内容时，请回当前对话继续。');
  } catch (error) {
    note(error.message + '；未保存输入仍保留。');
  } finally {
    busy = false;
  }
}
function editor(container, stage, file) {
  const key = stage + ':' + file.path, area = el('textarea');
  area.className = 'director';
  area.setAttribute('aria-label', '编辑 ' + file.path);
  area.value = drafts.get(key)?.text ?? file.text;
  area.oninput = () => {
    if (area.value === file.text) drafts.delete(key);
    else drafts.set(key, {text: area.value, base: drafts.get(key)?.base ?? file.text});
    disableConfirm();
  };
  container.append(area);
  const draft = drafts.get(key);
  if (draft && draft.base !== file.text) {
    const conflict = el('details');
    conflict.open = true;
    conflict.append(el('summary', '文件已更新：请对照最新正文合并草稿'), el('pre', file.text));
    container.append(conflict);
  }
  container.append(button('保存导演稿', () => {
    const current = drafts.get(key);
    if (current && current.base !== file.text) {
      note('请先对照最新正文合并，点击“已完成合并”再保存。');
      return;
    }
    act('/api/edit', {stage, file: file.path, text: area.value}, key);
  }));
  if (draft && draft.base !== file.text) {
    container.append(button('已完成合并', () => {
      drafts.set(key, {text: area.value, base: file.text});
      render();
    }));
  }
  container.append(button('撤销本文件修改', () => { drafts.delete(key); render(); }));
}
function artifact(container, stage, file) {
  const url = '/api/file?path=' + encodeURIComponent(file.path) + '&token=' + encodeURIComponent(token);
  const link = el('a', file.path);
  link.href = url; link.target = '_blank'; link.rel = 'noreferrer';
  container.append(link);
  if (!file.exists) { container.append(el('p', '文件缺失')); return; }
  if (/\.(png|jpe?g|webp)$/i.test(file.path)) {
    const image = el('img');
    image.src = url; image.alt = file.path; image.loading = 'lazy';
    container.append(image);
  }
  if (file.text === undefined) return;
  if (stage === 'director' && /\.(md|txt)$/i.test(file.path)) {
    editor(container, stage, file);
    return;
  }
  if (/\.json$/i.test(file.path)) {
    let data;
    try { data = JSON.parse(file.text); } catch (_) { /* Show invalid JSON for correction. */ }
    if (data && typeof data.text === 'string' && typeof data.translation_zh === 'string') {
      container.append(el('h4', '系统提示词'), el('pre', data.text), el('h4', '中文对照'), el('pre', data.translation_zh));
      return;
    }
    if (data && Array.isArray(data.panels)) {
      const timeline = el('details');
      timeline.append(el('summary', '九格画面与时间'));
      for (const panel of data.panels) {
        timeline.append(el('p', `第 ${panel.panel} 格 · ${panel.time_seconds} 秒 · ${panel.shot_id}：${panel.description}`));
      }
      container.append(timeline);
      return;
    }
    const details = el('details');
    details.append(el('summary', '查看素材与制作记录'), el('pre', file.text));
    container.append(details);
    return;
  }
  container.append(el('pre', file.text));
}
function controls(container, stage, row, item) {
  if (row.feedback) container.append(el('p', '修改意见：' + row.feedback));
  const key = item ? `item-feedback:${stage}:${item}` : 'feedback:' + stage;
  const area = el('textarea');
  area.placeholder = item ? '仅修改此人物或任务' : '需要调整什么？保存后由助手处理。';
  area.setAttribute('aria-label', stages[stage] + (item ? ' ' + item : '') + '修改意见');
  area.value = drafts.get(key)?.text || '';
  area.oninput = () => {
    if (area.value.trim()) drafts.set(key, {text: area.value});
    else drafts.delete(key);
    disableConfirm();
  };
  const data = item ? {stage, item} : {stage};
  container.append(area, button(item ? '提交此项修改意见' : '提交修改意见', () =>
    act(item ? '/api/feedback-item' : '/api/feedback', {...data, text: area.value}, key)));
  container.append(button('清空未提交意见', () => { drafts.delete(key); render(); }));
  const confirm = button(item ? '确认 ' + item : '确认本阶段当前版本', () =>
    act(item ? '/api/confirm-item' : '/api/confirm', data));
  confirm.dataset.confirm = stage;
  if (item) confirm.dataset.item = item;
  container.append(confirm);
}
function render() {
  $('title').textContent = state.name + ' · 九宫格制作审核';
  $('nav').replaceChildren();
  $('main').replaceChildren();
  for (const [stage, title] of Object.entries(stages)) {
    const link = el('a', title + ' · ' + labels[state.status[stage]]);
    link.href = '#token=' + encodeURIComponent(token) + '&stage=' + stage;
    link.onclick = event => { event.preventDefault(); document.getElementById(stage).scrollIntoView({behavior: 'smooth'}); };
    $('nav').append(link);
    const section = el('section'); section.id = stage;
    section.append(el('h2', title + ' · ' + labels[state.status[stage]]));
    const row = state.stages[stage];
    if (!row) {
      section.append(el('p', '尚未生成。请回当前对话继续。'));
    } else if (row.items) {
      for (const [item, value] of Object.entries(row.items)) {
        const card = el('article');
        card.append(el('h3', item + ' · ' + labels[row.item_status[item]]));
        for (const file of row.artifacts.filter(file => value.files.includes(file.path))) artifact(card, stage, file);
        controls(card, stage, value, item);
        section.append(card);
      }
    } else {
      for (const file of row.artifacts) artifact(section, stage, file);
      controls(section, stage, row);
    }
    section.append(el('small', '修改后，相关下游内容需重新核对。目标模型生成效果仍需实测。'));
    $('main').append(section);
  }
  disableConfirm();
}
function disableConfirm() {
  document.querySelectorAll('[data-confirm]').forEach(button => {
    const status = button.dataset.item ? state.stages[button.dataset.confirm].item_status[button.dataset.item] : state.status[button.dataset.confirm];
    button.disabled = drafts.size > 0 || status !== 'awaiting_confirmation';
  });
}
async function refresh(manual = false) {
  if (busy) return;
  const version = ++requestVersion;
  try {
    const next = await api('/api/state');
    if (busy || version !== requestVersion) return;
    if (!state || next.revision !== state.revision) {
      if (drafts.size && !manual) {
        note('成果已有更新，未覆盖你的输入；请先保留草稿，再点击刷新合并。');
        return;
      }
      state = next;
      render();
      if (drafts.size) note('已刷新；你的草稿保留在编辑框，请与最新内容核对后保存。');
    } else if (manual) note('当前已是最新版本。');
  } catch (error) { note('更新失败：' + error.message); }
}
$('refresh').onclick = () => refresh(true);
$('validate').onclick = async () => {
  try {
    const report = await api('/api/validate');
    note(report.ok ? '材料和当前确认齐备，可导出交付包；目标视频仍待实测。' : '尚不可正式交付：' + [...report.errors, ...report.pending].join('；'));
  } catch (error) { note(error.message); }
};
window.addEventListener('beforeunload', event => {
  if (drafts.size) { event.preventDefault(); event.returnValue = ''; }
});
refresh();
setInterval(() => refresh(), 3000);
