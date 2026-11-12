'use strict';
const $ = id => document.getElementById(id);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const nodeDisplayName = value => String(value ?? '').replace(/[\u{1F1E6}-\u{1F1FF}]/gu, '').trim();
const iconPaths = {
  logo: '<path d="M4 17V7l5 6 3-6 3 6 5-6v10"/><path d="M4 20h16" opacity=".5"/>',
  server: '<rect x="3" y="3" width="18" height="7" rx="2"/><rect x="3" y="14" width="18" height="7" rx="2"/><path d="M7 6.5h.01M7 17.5h.01M15 6.5h3M15 17.5h3"/>',
  globe: '<circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18"/>',
  layers: '<path d="m12 3 9 5-9 5-9-5 9-5ZM3 12l9 5 9-5M3 16l9 5 9-5"/>',
  history: '<path d="M3 11a9 9 0 1 1 2.5 7M3 4v7h7M12 7v5l3 2"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>',
  lock: '<rect x="5" y="10" width="14" height="11" rx="3"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3"/>',
  logout: '<path d="M9 4H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h4M14 8l4 4-4 4M9 12h12"/>',
  shield: '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z"/><path d="m8 12 3 3 5-6"/>',
  route: '<circle cx="6" cy="5" r="2"/><circle cx="18" cy="19" r="2"/><path d="M6 7v9a3 3 0 0 0 3 3h7M18 17V8a3 3 0 0 0-3-3h-3M13 2l-3 3 3 3"/>',
  refresh: '<path d="M20 7v5h-5M4 17v-5h5"/><path d="M6 6a8 8 0 0 1 13 2l1 4M4 12l1 4a8 8 0 0 0 13 2"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  activity: '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  x: '<path d="m6 6 12 12M6 18 18 6"/>',
  sparkles: '<path d="m12 3 2.6 6.4L21 12l-6.4 2.6L12 21l-2.6-6.4L3 12l6.4-2.6L12 3ZM20 3v4M18 5h4"/>',
  tag: '<path d="M3 12V4h8l10 10-8 8L3 12Z"/><circle cx="7.5" cy="8" r="1"/>',
  terminal: '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="m7 9 3 3-3 3M13 15h4"/>',
  copy: '<rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
  'arrow-right': '<path d="M4 12h16m-6-6 6 6-6 6"/>',
  arrow: '<path d="M6 18 18 6M6 6h12v12"/>',
  edit: '<path d="m15 4 5 5M4 20l5-1L21 7a2.1 2.1 0 0 0-4-4L5 15l-1 5Z"/>',
  more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
  power: '<path d="M12 2v10M6.3 5.7a8 8 0 1 0 11.4 0"/>',
  trash: '<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  'chevron-down': '<path d="m6 9 6 6 6-6"/>'
};
const icon = name => `<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${iconPaths[name] || iconPaths.globe}</svg>`;
document.querySelectorAll('[data-icon]').forEach(el => el.innerHTML=icon(el.dataset.icon));

const regionSearchTerms = {
  '印度':['IN','India','yindu','yd'], '菲律宾':['PH','Philippines','feilvbin','flb'],
  '香港':['HK','Hong Kong','xianggang','xg'], '日本':['JP','Japan','riben','rb'],
  '美国':['US','USA','United States','meiguo','mg'], '新加坡':['SG','Singapore','xinjiapo','xjp'],
  '台湾':['TW','Taiwan','taiwan'], '韩国':['KR','Korea','hanguo','hg'],
  '英国':['UK','GB','United Kingdom','yingguo','yg'], '德国':['DE','Germany','deguo','dg'],
  '加拿大':['CA','Canada','jianada','jnd'], '澳大利亚':['AU','Australia','aodaliya','adly'],
  '法国':['FR','France','faguo','fg'], '荷兰':['NL','Netherlands','helan','hl'],
  '马来西亚':['MY','Malaysia','malaixiya','mlxy'], '泰国':['TH','Thailand','taiguo','tg'],
  '越南':['VN','Vietnam','yuenan','yn'], '印度尼西亚':['ID','Indonesia','yindunixiya','ydnxy'],
  '俄罗斯':['RU','Russia','eluosi','els'], '其他':['Other','qita','qt']
};
const regionAliases = value => Object.hasOwn(regionSearchTerms,value) ? regionSearchTerms[value] : [];
const normalizeSearch = value => String(value ?? '').normalize('NFKD').toLowerCase().replace(/[^\p{L}\p{N}]/gu, '');
function searchScore(values, query) {
  const tokens=String(query ?? '').trim().split(/\s+/).map(normalizeSearch).filter(Boolean);
  if (!tokens.length) return 0;
  const candidates=(Array.isArray(values)?values:[values]).map(normalizeSearch);
  let score=0;
  for (const token of tokens) {
    let best=Infinity;
    for (const text of candidates) {
      const index=text.indexOf(token);
      if (index>=0) { best=Math.min(best,text===token?0:index===0?1:2+index/100); continue; }
      if (token.length<2) continue;
      let cursor=0, start=-1, end=-1;
      for (const char of token) {
        const found=text.indexOf(char,cursor);
        if (found<0) { end=-1; break; }
        if (start<0) start=found;
        end=found; cursor=found+1;
      }
      if (end>=0) best=Math.min(best,5+(end-start-token.length+1)/100);
    }
    if (!Number.isFinite(best)) return Infinity;
    score+=best;
  }
  return score;
}

// Keep native values as the form's source of truth; add a searchable popover.
const searchableSelects=new Map();
let openSearchSelect=null;
class SearchableSelect {
  constructor(select) {
    this.select=select; this.label=select.getAttribute('aria-label')||'选项'; this.highlighted=-1;
    this.wrapper=document.createElement('div'); this.wrapper.className='search-select';
    this.trigger=document.createElement('button'); this.trigger.type='button'; this.trigger.className='search-select-trigger';
    this.trigger.id=select.id+'-trigger'; this.trigger.setAttribute('role','combobox');
    this.trigger.setAttribute('aria-haspopup','listbox'); this.trigger.setAttribute('aria-expanded','false');
    this.trigger.setAttribute('aria-controls',select.id+'-options');
    this.trigger.innerHTML='<span class="search-select-value"></span>'+icon('chevron-down');
    select.before(this.wrapper); this.wrapper.append(select,this.trigger);
    select.classList.add('search-select-native'); select.tabIndex=-1; select.setAttribute('aria-hidden','true');
    this.popup=document.createElement('div'); this.popup.className='search-select-popup'; this.popup.hidden=true;
    this.popup.id=select.id+'-popup';
    this.popup.innerHTML=`<div class="search-select-input">${icon('search')}<input type="search" autocomplete="off" spellcheck="false" placeholder="输入关键词搜索…" aria-label="搜索${escapeHTML(this.label.replace(/^所属|^筛选/,''))}" aria-autocomplete="list" aria-controls="${select.id}-options"></div><div class="search-select-options" id="${select.id}-options" role="listbox" aria-label="${escapeHTML(this.label)}"></div><div class="search-select-empty" role="status" hidden>没有找到匹配项</div>`;
    this.input=this.popup.querySelector('input'); this.list=this.popup.querySelector('[role=listbox]');
    this.trigger.addEventListener('click',()=>this.popup.hidden?this.open():this.close());
    this.trigger.addEventListener('keydown',event=>{
      if (event.key==='ArrowDown'||event.key==='ArrowUp') { event.preventDefault(); this.open(event.key==='ArrowUp'); }
    });
    this.input.addEventListener('input',()=>this.render());
    this.popup.addEventListener('keydown',event=>{
      if (event.isComposing) return;
      if (event.key==='Escape') { event.preventDefault(); event.stopPropagation(); this.close(); }
      else if (event.key==='Tab') this.close();
      else if (event.key==='ArrowDown'||event.key==='ArrowUp') {
        event.preventDefault();
        if (this.results.length) this.highlight((this.highlighted+(event.key==='ArrowDown'?1:-1)+this.results.length)%this.results.length);
      } else if (event.key==='Enter') {
        event.preventDefault();
        if (this.highlighted>=0) this.choose(this.results[this.highlighted].option.value);
      }
    });
    this.list.addEventListener('pointerdown',event=>event.preventDefault());
    this.list.addEventListener('click',event=>{
      const option=event.target.closest('[role=option]'); if(option)this.choose(option.dataset.value);
    });
    select.addEventListener('change',()=>this.sync());
    select.closest('form')?.addEventListener('reset',()=>queueMicrotask(()=>this.sync()));
    new MutationObserver(()=>this.sync()).observe(select,{childList:true,subtree:true,attributes:true,attributeFilter:['disabled','selected','label']});
    searchableSelects.set(select,this); this.sync();
  }
  sync() {
    const text=this.select.selectedOptions[0]?.textContent||this.label;
    this.trigger.querySelector('.search-select-value').textContent=text;
    this.trigger.setAttribute('aria-label',this.label+'：'+text); this.trigger.title=text;
    this.trigger.disabled=this.select.disabled;
    if (!this.popup.hidden) this.render();
  }
  open(fromEnd=false) {
    if (this.trigger.disabled) return;
    openSearchSelect?.close(false); openSearchSelect=this;
    (this.select.closest('dialog')||document.body).append(this.popup);
    this.input.value=''; this.popup.hidden=false; this.trigger.setAttribute('aria-expanded','true');
    this.render();
    const selected=this.results.findIndex(item=>item.option.value===this.select.value);
    this.highlight(fromEnd?this.results.length-1:Math.max(0,selected));
    this.input.focus({preventScroll:true}); this.position();
  }
  close(restoreFocus=true) {
    this.popup.hidden=true; this.trigger.setAttribute('aria-expanded','false'); this.input.removeAttribute('aria-activedescendant');
    if(openSearchSelect===this)openSearchSelect=null;
    if(restoreFocus)this.trigger.focus({preventScroll:true});
  }
  render() {
    const previous=this.results?.[this.highlighted]?.option.value;
    this.results=Array.from(this.select.options).filter(option=>!option.disabled).map((option,index)=>({option,index,score:searchScore([option.textContent,...regionAliases(option.textContent)],this.input.value)})).filter(item=>Number.isFinite(item.score)).sort((a,b)=>a.score-b.score||a.index-b.index);
    this.list.innerHTML=this.results.map(({option},index)=>`<div class="search-select-option" id="${this.select.id}-option-${index}" role="option" aria-selected="${option.value===this.select.value}" data-value="${escapeHTML(option.value)}">${icon('check')}<span>${escapeHTML(option.textContent)}</span></div>`).join('');
    this.popup.querySelector('.search-select-empty').hidden=this.results.length>0;
    const current=this.results.findIndex(item=>item.option.value===previous);
    this.highlight(current>=0?current:0); this.position();
  }
  highlight(index) {
    this.highlighted=this.results.length?index:-1;
    this.list.querySelectorAll('[role=option]').forEach((option,i)=>option.classList.toggle('highlighted',i===this.highlighted));
    const current=this.list.children[this.highlighted];
    if(current) {
      this.input.setAttribute('aria-activedescendant',current.id);
      this.list.scrollTop=Math.max(0,Math.min(this.list.scrollTop,current.offsetTop-this.list.offsetTop));
      if(current.offsetTop+current.offsetHeight>this.list.offsetTop+this.list.scrollTop+this.list.clientHeight)this.list.scrollTop=current.offsetTop-this.list.offsetTop+current.offsetHeight-this.list.clientHeight;
    } else this.input.removeAttribute('aria-activedescendant');
  }
  position() {
    if(this.popup.hidden)return;
    const rect=this.trigger.getBoundingClientRect(), viewport=window.visualViewport;
    const top=viewport?.offsetTop||0, left=viewport?.offsetLeft||0, width=viewport?.width||innerWidth, height=viewport?.height||innerHeight;
    const below=top+height-rect.bottom-12, above=rect.top-top-12, upwards=below<220&&above>below;
    const space=Math.max(90,upwards?above:below);
    this.popup.style.width=Math.min(Math.max(rect.width,220),width-24)+'px';
    this.list.style.maxHeight=Math.max(40,Math.min(230,space-55))+'px';
    this.popup.style.left=Math.max(left+12,Math.min(rect.left,left+width-this.popup.offsetWidth-12))+'px';
    this.popup.style.top=(upwards?Math.max(top+8,rect.top-this.popup.offsetHeight-6):Math.min(rect.bottom+6,top+height-this.popup.offsetHeight-8))+'px';
  }
  choose(value) {
    this.select.value=value;
    this.select.dispatchEvent(new Event('input',{bubbles:true}));
    this.select.dispatchEvent(new Event('change',{bubbles:true}));
    this.close();
  }
}
document.addEventListener('pointerdown',event=>{
  if(openSearchSelect&&!openSearchSelect.wrapper.contains(event.target)&&!openSearchSelect.popup.contains(event.target))openSearchSelect.close(false);
});
document.addEventListener('scroll',event=>{if(openSearchSelect&&!openSearchSelect.popup.contains(event.target))openSearchSelect.position();},true);
window.addEventListener('resize',()=>openSearchSelect?.position());
window.visualViewport?.addEventListener('resize',()=>openSearchSelect?.position());
window.visualViewport?.addEventListener('scroll',()=>openSearchSelect?.position());

let state = null, activeTab = 'services', serviceFilter = 'all', toastTimer, confirmationResolve;
const serviceActionStates=new Map();
const descriptions = {
  services: ['代理服务', '管理连接入口，随时切换出口节点。'],
  nodes: ['节点', '按订阅、地区或标签，找到合适的出口。'],
  subscriptions: ['订阅', '集中管理你的节点来源。'],
  activity: ['操作记录', '查看最近的管理操作。']
};
const actionLabels = {'admin.login':'管理员登录','admin.password':'修改登录密码','subscription.create':'添加订阅','subscription.edit':'编辑订阅','subscription.refresh':'更新订阅','subscription.delete':'删除订阅','service.apply':'应用服务配置','service.start':'启动服务','service.stop':'停止服务','service.restart':'重启服务','service.delete':'删除服务','service.credentials':'查看连接信息','service.test':'测试服务'};

async function api(path, method='GET', body) {
  const response = await fetch('/api' + path, {method, credentials:'same-origin', headers:{'Content-Type':'application/json','X-Requested-With':'MihomoPanel'}, body:body === undefined ? undefined : JSON.stringify(body)});
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && path !== '/login') showLogin();
    throw new Error(typeof data.detail === 'string' ? data.detail : response.status === 422 ? '请检查必填字段和输入格式' : '请求失败，请重试');
  }
  return data;
}
function toast(text, tone='success') {
  const el=$('toast'); el.dataset.tone=tone; el.setAttribute('role',tone==='error'?'alert':'status');
  (Array.from(document.querySelectorAll('dialog[open]')).at(-1)||document.body).appendChild(el);
  el.innerHTML=icon(tone==='error'?'x':tone==='info'?'info':tone==='warning'?'info':'check')+`<span>${escapeHTML(text)}</span>`;
  el.hidden=false; clearTimeout(toastTimer); toastTimer=setTimeout(()=>el.hidden=true,4500);
}
function date(value) { return value ? new Date(value).toLocaleString('zh-CN', {hour12:false}) : '尚未更新'; }
function showLogin() { openSearchSelect?.close(false); serviceActionStates.clear(); state=null; $('dashboard').hidden=true; $('login-view').hidden=false; document.querySelectorAll('dialog[open]').forEach(d=>d.close()); }
function info(title, content, note='') { $('info-title').textContent=title; $('info-content').textContent=content; $('info-note').textContent=note; if (!$('info-dialog').open) $('info-dialog').showModal(); }
function confirmAction({title,message,label,tone='warning',symbol='power'}) {
  if(confirmationResolve)return Promise.resolve(false);
  openSearchSelect?.close(false);
  $('confirm-title').textContent=title; $('confirm-description').textContent=message;
  $('confirm-symbol').innerHTML=icon(symbol); $('confirm-symbol').className='confirm-symbol '+tone;
  $('confirm-accept').textContent=label; $('confirm-accept').className=tone==='danger'?'destructive':'confirm-warning';
  $('confirm-dialog').returnValue='cancel';
  return new Promise(resolve=>{
    confirmationResolve=resolve; $('confirm-dialog').showModal(); $('confirm-cancel').focus();
  });
}
$('confirm-cancel').addEventListener('click',()=>$('confirm-dialog').close('cancel'));
$('confirm-accept').addEventListener('click',()=>$('confirm-dialog').close('accept'));
$('confirm-dialog').addEventListener('close',()=>{
  const resolve=confirmationResolve; confirmationResolve=null; resolve?.($('confirm-dialog').returnValue==='accept');
});
async function busy(button, fn) { const before=button.innerHTML, label=button.textContent.trim(); button.disabled=true; button.setAttribute('aria-busy','true'); button.innerHTML='<span class="spinner" aria-hidden="true"></span>'+escapeHTML(label); try { return await fn(); } finally { button.disabled=false; button.removeAttribute('aria-busy'); button.innerHTML=before; } }
async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    try { await navigator.clipboard.writeText(text); return; } catch (_) { /* Try the compatible clipboard path below. */ }
  }
  const field=document.createElement('textarea');
  field.value=text; field.readOnly=true; field.className='clipboard-buffer';
  const previous=document.activeElement;
  (previous?.closest('dialog[open]')||document.body).appendChild(field);
  try {
    field.focus(); field.select(); field.setSelectionRange(0,field.value.length);
    if (!document.execCommand('copy')) throw new Error('浏览器不允许自动复制，请选中内容手动复制');
  } finally { field.remove(); previous?.focus(); }
}
function selectOptions(id, entries, label, previous) {
  const select=$(id), value=previous ?? select.value;
  select.innerHTML=`<option value="">${escapeHTML(label)}</option>` + entries.map(([v,n])=>`<option value="${escapeHTML(v)}">${escapeHTML(n)}</option>`).join('');
  select.value=value;
  if (select.selectedIndex<0) select.value='';
  searchableSelects.get(select)?.sync();
}
function filterOptions(prefix) {
  selectOptions(prefix+'sub', state.subscriptions.map(s=>[s.id,s.name]), '全部订阅');
  selectOptions(prefix+'country', [...new Set(state.nodes.filter(n=>n.available).map(n=>n.country))].sort().map(c=>[c,c]), '全部地区');
  selectOptions(prefix+'tag', [...new Set(state.nodes.flatMap(n=>n.tags))].sort().map(t=>[t,t]), '全部标签');
}
function matchingNodes(prefix, includeUnavailable=false) {
  const sub=$(prefix+'sub').value, country=$(prefix+'country').value, tag=$(prefix+'tag').value, search=$(prefix+'search').value.trim();
  const nodes=state.nodes.filter(n=>(includeUnavailable || n.available) && (!sub || String(n.subscription_id)===sub) && (!country || n.country===country) && (!tag || n.tags.includes(tag)));
  return search ? nodes.map(node=>({node,score:searchScore([node.name,node.country,node.subscription,...node.tags,...regionAliases(node.country)],search)})).filter(item=>Number.isFinite(item.score)).sort((a,b)=>a.score-b.score).map(item=>item.node) : nodes;
}
async function reload() {
  state=await api('/state'); $('login-view').hidden=true; $('dashboard').hidden=false;
  renderServices(); filterOptions('filter-'); renderNodes(); renderSubscriptions();
  $('activity-rows').innerHTML=state.events.map(e=>`<tr><td>${escapeHTML(date(e.at))}</td><td>${escapeHTML(actionLabels[e.action]||e.action)}</td><td>${escapeHTML(e.detail)}</td></tr>`).join('') || '<tr><td colspan="3" class="table-empty">暂无操作记录</td></tr>';
  setTab(activeTab);
}
async function runServiceAction(id, action) {
  if(serviceActionStates.get(id)?.phase==='pending')return;
  const operation={action,phase:'pending'};
  serviceActionStates.set(id,operation); renderServices();
  try {
    await api(`/services/${id}/action`,'POST',{action}); await reload();
    operation.phase='success';
    toast(({start:'服务已开启',stop:'服务已停止',restart:'服务已重启'})[action]);
    setTimeout(()=>{
      if(serviceActionStates.get(id)===operation){serviceActionStates.delete(id);if(state)renderServices();}
    },1800);
  } finally {
    if(operation.phase==='pending'&&serviceActionStates.get(id)===operation)serviceActionStates.delete(id);
    if(state)renderServices();
  }
}
function setTab(tab) {
  activeTab=tab;
  for (const name of Object.keys(descriptions)) $(name+'-view').hidden=name!==tab;
  document.querySelectorAll('[data-tab]').forEach(b=>{b.classList.toggle('active',b.dataset.tab===tab); if(b.dataset.tab===tab)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});
  $('page-title').textContent=descriptions[tab][0];
  $('page-description').textContent=descriptions[tab][1];
  document.title=`${descriptions[tab][0]} · Mihomo`;
  $('main-action').hidden=tab==='activity';
  $('main-action').dataset.action=tab==='subscriptions'?'create-subscription':'create-service';
  $('main-action').innerHTML=icon('plus')+(tab==='subscriptions'?'添加订阅':'新建服务');
  document.querySelectorAll('.more-menu[open]').forEach(menu=>menu.open=false);
}
function countryCode(country) {
  return ({'印度':'IN','菲律宾':'PH','香港':'HK','日本':'JP','美国':'US','新加坡':'SG','台湾':'TW','韩国':'KR','英国':'UK','德国':'DE','加拿大':'CA','澳大利亚':'AU','法国':'FR','荷兰':'NL','马来西亚':'MY','泰国':'TH','越南':'VN','印度尼西亚':'ID'})[country] || icon('globe');
}
function renderServices() {
  const runningCount=state.services.filter(s=>s.status.ActiveState==='active').length;
  $('service-total').textContent=state.services.length;
  $('service-running').textContent=runningCount;
  $('service-stopped').textContent=state.services.filter(s=>s.status.ActiveState && s.status.ActiveState!=='active').length;
  document.querySelectorAll('[data-service-filter]').forEach(button=>{
    const selected=button.dataset.serviceFilter===serviceFilter;
    button.classList.toggle('active',selected); button.setAttribute('aria-pressed',String(selected));
  });
  const search=$('service-search').value.toLowerCase().trim();
  const services=state.services.filter(s=>(serviceFilter==='all' || (serviceFilter==='running' ? s.status.ActiveState==='active' : s.status.ActiveState && s.status.ActiveState!=='active')) && Number.isFinite(searchScore([s.name,s.port,s.node_name,s.country,s.subscription,...regionAliases(s.country)],search)));
  $('service-result-count').textContent=services.length ? `共 ${state.services.length} 个服务${services.length!==state.services.length?`，当前显示 ${services.length} 个`:''}` : '';
  $('service-list').innerHTML=services.length ? services.map(s=>{
    const running=s.status.ActiveState==='active', known=Boolean(s.status.ActiveState), p=s.last_probe, id=escapeHTML(s.id);
    const operation=serviceActionStates.get(s.id), working=operation?.phase==='pending';
    const switching=working&&operation.action!=='restart', restarting=working&&operation.action==='restart';
    const restarted=operation?.phase==='success'&&operation.action==='restart';
    const toggleFeedback=operation?.phase==='success'?(operation.action==='start'?' just-enabled':operation.action==='stop'?' just-disabled':''):'';
    const powerText=switching?(operation.action==='stop'?'停止中':'开启中'):running?'已开启':known?'已停止':'开启';
    const disabled=working?'disabled':'';
    const exit=p?.tcp ? [p.ip,p.country,p.city].filter(Boolean).map(escapeHTML).join(' · ') : '连接失败，点击测试查看详情';
    const udpTested=p?.udp!==null && p?.udp!==undefined;
    return `<article class="service-card ${working?'is-working':''}" aria-busy="${working}"><div class="service-card-top"><div class="service-identity"><span class="country-mark" aria-hidden="true">${countryCode(s.country)}</span><div><h3>${escapeHTML(s.name)}</h3><span class="service-type">SOCKS5</span></div></div><span class="badge ${working?'amber':running?'green':known?'gray':'amber'}"><span class="badge-dot"></span>${working?({start:'正在开启',stop:'正在停止',restart:'正在重启'})[operation.action]:running?'运行中':known?'已停止':'状态未知'}</span></div>
      <div class="endpoint-block"><span class="field-caption">地址</span><div class="endpoint mono">${escapeHTML(state.public_ip)}<span class="endpoint-port">:${s.port}</span></div></div>
      <div class="service-node-row"><span class="node-caption">出口</span><div class="node-detail"><span class="service-node-name" title="${escapeHTML(s.node_name)}">${escapeHTML(nodeDisplayName(s.node_name))}</span><span class="subnote">${escapeHTML(s.subscription)} · ${escapeHTML(s.country)}</span></div></div>
      ${!s.available?'<p class="inline-warning">节点已移除，当前保留原配置</p>':s.update_available?'<p class="inline-warning">节点已更新，重新保存即可应用</p>':''}
      ${p?`<div class="probe-summary"><div class="probe-heading"><span class="field-caption">上次测试</span><span class="probe-status ${p.tcp?'passed':'failed'}">${icon(p.tcp?'check':'x')}TCP ${p.tcp?'通过':'失败'}</span><span class="probe-status ${udpTested?(p.udp?'passed':'failed'):'muted'}">${icon(udpTested?(p.udp?'check':'x'):'clock')}UDP ${udpTested?(p.udp?'通过':'异常'):'未测试'}</span></div><div class="probe-exit mono">${exit}</div></div>`:`<div class="probe-summary untested">${icon('activity')}<span>尚未测试出口</span></div>`}
      <div class="service-actions"><button class="service-power ${switching?'is-changing':running?'is-on':'is-off'}${toggleFeedback}" data-action="${running?'stop':'start'}" data-id="${id}" role="switch" aria-checked="${running}" aria-busy="${switching}" aria-label="${running?'停止':'开启'}${escapeHTML(s.name)}" title="点击${running?'停止':'开启'}服务" ${disabled}>${switching?'<span class="spinner" aria-hidden="true"></span>':'<span class="switch-track" aria-hidden="true"><span class="switch-thumb"></span></span>'}<span>${powerText}</span></button><button class="service-restart ${restarting?'is-restarting':restarted?'is-done':''}" data-action="restart" data-id="${id}" aria-label="重启${escapeHTML(s.name)}" aria-busy="${restarting}" ${disabled}>${icon(restarted?'check':'refresh')}<span>${restarting?'重启中':restarted?'已重启':'重启'}</span></button><details class="more-menu" ${working?'inert':''}><summary aria-label="更多服务操作" title="更多操作" aria-disabled="${working}">${icon('more')}</summary><div class="more-menu-panel"><button data-action="login-info" data-id="${id}" ${disabled}>${icon('user')}登录信息</button><button data-action="credentials" data-id="${id}" ${disabled}>${icon('copy')}连接信息</button><button data-action="edit-service" data-id="${id}" ${disabled}>${icon('route')}切换节点 / 编辑</button><button data-action="test-service" data-id="${id}" ${disabled}>${icon('activity')}测试连接</button><button data-action="logs" data-id="${id}" ${disabled}>${icon('terminal')}日志</button><div class="menu-separator"></div><button class="danger" data-action="delete-service" data-id="${id}" ${disabled}>${icon('trash')}删除服务</button></div></details></div></article>`;
  }).join('') : state.services.length ? `<div class="empty"><span class="empty-icon">${icon('search')}</span><h3>没有找到服务</h3><p>试试其他关键词，或调整服务状态。</p><button data-action="clear-service-filters">清除筛选</button></div>` : `<div class="empty"><span class="empty-icon">${icon('server')}</span><h3>创建你的第一个服务</h3><p>选择一个出口节点，自动生成连接账号。</p><button class="primary" data-action="create-service">${icon('plus')}新建服务</button></div>`;
}
function renderNodes() {
  const rows=matchingNodes('filter-', $('filter-available').value==='all');
  $('nodes-count').textContent=`${rows.length} 个节点`;
  $('node-rows').innerHTML=rows.length ? rows.map(n=>`<tr><td><div class="node-name-cell"><span class="node-name-icon">${icon('globe')}</span><div>${escapeHTML(nodeDisplayName(n.name))}${!n.available?'<span class="subnote">已从订阅移除</span>':''}</div></div></td><td><span class="subscription-label">${escapeHTML(n.subscription)}</span></td><td><span class="country-label">${escapeHTML(n.country)}</span><div>${n.tags.map(t=>`<span class="tag">${escapeHTML(t)}</span>`).join('')}</div></td><td><div class="actions"><button class="text-button" data-action="edit-node" data-id="${n.id}">分类</button><button class="text-button" data-action="test-node" data-id="${n.id}" ${n.available?'':'disabled'}>测试</button><button class="use-node" data-action="use-node" data-id="${n.id}" ${n.available?'':'disabled'}>新建服务 ${icon('arrow')}</button></div></td></tr>`).join('') : '<tr><td colspan="4" class="table-empty">没有符合筛选条件的节点，试试调整筛选条件。</td></tr>';
}
function renderSubscriptions() {
  $('subscription-list').innerHTML=state.subscriptions.map(s=>`<article class="panel subscription-card"><div class="subscription-title"><div class="service-identity"><span class="subscription-mark">${icon('layers')}</span><h3>${escapeHTML(s.name)}</h3></div><span class="badge ${s.last_error?'amber':'gray'}">${s.last_error?'更新失败':s.remote?(s.enabled?'自动更新':'手动更新'):'本地导入'}</span></div><div class="subscription-node-count"><strong>${s.node_count}</strong><span>个可用节点</span></div><p class="subscription-updated">${icon('clock')}${s.remote?`上次更新 ${escapeHTML(date(s.last_refresh))}`:'从现有服务导入'}</p>${s.last_error?`<p class="error subscription-error" title="${escapeHTML(s.last_error)}">${escapeHTML(s.last_error)}</p>`:''}<div class="subscription-actions">${s.remote?`<button data-action="refresh-subscription" data-id="${s.id}">${icon('refresh')}更新订阅</button>`:''}<button class="text-button" data-action="edit-subscription" data-id="${s.id}">${icon('edit')}编辑</button><button class="icon-button danger" data-action="delete-subscription" data-id="${s.id}" aria-label="删除 ${escapeHTML(s.name)}" title="删除订阅">${icon('trash')}</button></div></article>`).join('') || `<div class="empty"><span class="empty-icon">${icon('layers')}</span><h3>添加你的订阅</h3><p>支持多个 Clash 订阅，节点会按来源分类。</p><button class="primary" data-action="create-subscription">${icon('plus')}添加订阅</button></div>`;
}
function renderPicker(selected) {
  const value=selected ?? $('service-node').value;
  let nodes=matchingNodes('pick-');
  const current=state.services.find(s=>s.id===$('service-id').value);
  if (current && !state.nodes.find(n=>n.id===current.node_id)?.available && !nodes.some(n=>n.id===current.node_id)) {
    const old=state.nodes.find(n=>n.id===current.node_id); if(old) nodes=[old,...nodes];
  }
  const groups=new Map();
  for (const node of nodes) { if (!groups.has(node.subscription)) groups.set(node.subscription,[]); groups.get(node.subscription).push(node); }
  $('service-node').innerHTML=[...groups].map(([group,items])=>`<optgroup label="${escapeHTML(group)}">${items.map(n=>`<option value="${n.id}">${escapeHTML(n.country)} · ${escapeHTML(nodeDisplayName(n.name))}${!n.available?'（保留原配置）':''}</option>`).join('')}</optgroup>`).join('');
  $('service-node').value=String(value||'');
  $('pick-count').textContent=`${nodes.length} 个可选节点`;
  updatePickerSelection();
}
function updatePickerSelection() {
  const selected=state.nodes.find(n=>String(n.id)===$('service-node').value);
  $('selected-node-label').textContent=selected?`已选：${selected.country}`:'请选择节点';
  document.querySelector('[data-action=test-selected-node]').disabled=!selected?.available;
}
async function serviceForm(id, nodeId) {
  const service=state.services.find(s=>s.id===id);
  $('service-form').reset(); $('service-advanced').open=false; $('service-error').textContent=''; $('service-id').value=id||'';
  $('service-title').textContent=service?'编辑服务':'新建服务';
  $('service-name').value=service?.name||'';
  let port=40003; const used=new Set(state.services.map(s=>s.port)); while(used.has(port))port++;
  $('service-port').value=service?.port||port;
  $('service-user').value=service?.username||''; $('service-password').value=''; $('service-password').type='password';
  $('service-password').placeholder=service?'留空保留当前密码':'至少 16 个字符';
  $('service-password').required=!service;
  document.querySelector('[data-action=toggle-secret]').textContent='显示';
  $('service-enabled').checked=service?.enabled??true;
  for(const id of ['pick-sub','pick-country','pick-tag','pick-search'])$(id).value='';
  filterOptions('pick-'); renderPicker(nodeId||service?.node_id||'');
  $('service-dialog').showModal();
  if (!service) { const c=await api('/credentials/generate','POST',{}); if($('service-dialog').open && !$('service-id').value){$('service-user').value=c.username; $('service-password').value=c.password;} }
}
function subscriptionForm(id) {
  const sub=state.subscriptions.find(s=>String(s.id)===String(id));
  $('subscription-form').reset(); document.querySelector('#subscription-dialog .advanced').open=false; $('subscription-error').textContent=''; $('subscription-id').value=id||'';
  $('subscription-title').textContent=sub?'编辑订阅':'添加订阅'; $('subscription-name').value=sub?.name||''; $('subscription-url').value=''; $('subscription-url').required=!sub;
  $('subscription-interval').value=sub?.interval_hours||24; $('subscription-enabled').checked=sub?.enabled??true;
  $('subscription-dialog').showModal();
}
function formatProbe(p) {
  return [`TCP 代理：${p.tcp?'通过':'失败'}`, ...(p.udp!==null&&p.udp!==undefined?[`UDP 转发：${p.udp?'通过':'失败'}`]:[]), p.ip?`出口 IP：${p.ip}`:'', p.country?`出口地区：${p.country} ${p.city||''}`:'', `耗时：${(p.duration_ms/1000).toFixed(1)} 秒`, p.warning, p.udp_warning, p.error, p.udp_error, ...(p.upstream_errors||[])].filter(Boolean).join('\n');
}
async function showCredentials(id, created=false) {
  const c=await api(`/services/${id}/credentials`,'POST',{});
  info('SOCKS5 连接信息', `服务器：${c.host}\n端口：${c.port}\n用户名：${c.username}\n密码：${c.password}\n\n${c.uri}`, created?`服务已保存。请确认云安全组已放行 ${c.port} 的 TCP 和 UDP。`:'仅向需要使用此代理的人提供连接信息。');
}
async function showServiceLogin(id) {
  const c=await api(`/services/${id}/credentials`,'POST',{});
  if(!state)return;
  $('service-login-description').textContent=state.services.find(s=>s.id===id)?.name||'SOCKS5 服务';
  $('service-login-user').value=c.username; $('service-login-password').value=c.password;
  if(!$('service-login-dialog').open)$('service-login-dialog').showModal();
}

$('login-form').addEventListener('submit',async event=>{
  event.preventDefault(); $('login-error').textContent='';
  try { await busy(event.submitter,async()=>{await api('/login','POST',{username:$('login-user').value,password:$('login-password').value}); $('login-password').value=''; await reload();}); }
  catch(error){$('login-error').textContent=error.message;}
});
$('service-form').addEventListener('submit',async event=>{
  event.preventDefault(); $('service-error').textContent='';
  try {await busy(event.submitter,async()=>{
    const id=$('service-id').value;
    const body={name:$('service-name').value,port:Number($('service-port').value),username:$('service-user').value,password:$('service-password').value,node_id:Number($('service-node').value),enabled:$('service-enabled').checked};
    const result=await api(id?`/services/${id}`:'/services',id?'PUT':'POST',body);
    $('service-dialog').close(); $('service-password').value=''; await reload(); await showCredentials(result.id,true);
  });}catch(error){$('service-error').textContent=error.message;}
});
$('subscription-form').addEventListener('submit',async event=>{
  event.preventDefault(); $('subscription-error').textContent='';
  try {await busy(event.submitter,async()=>{
    const id=$('subscription-id').value;
    const result=await api(id?`/subscriptions/${id}`:'/subscriptions',id?'PUT':'POST',{name:$('subscription-name').value,url:$('subscription-url').value,interval_hours:Number($('subscription-interval').value),enabled:$('subscription-enabled').checked});
    $('subscription-dialog').close(); $('subscription-url').value=''; await reload(); toast(result.warning||'订阅已保存',result.warning?'warning':'success');
  });}catch(error){$('subscription-error').textContent=error.message;}
});
$('node-form').addEventListener('submit',async event=>{
  event.preventDefault();
  try{await busy(event.submitter,async()=>{await api(`/nodes/${$('node-id').value}`,'PUT',{country:$('node-country').value,tags:$('node-tags').value.split(/[,，]/)});$('node-dialog').close();await reload();toast('节点分类已保存');});}catch(error){$('node-error').textContent=error.message;}
});
$('password-form').addEventListener('submit',async event=>{
  event.preventDefault();
  try{await busy(event.submitter,async()=>{await api('/admin/password','POST',{current:$('password-current').value,password:$('password-new').value});$('password-form').reset();$('password-dialog').close();showLogin();toast('登录密码已更新，请重新登录');});}catch(error){$('password-error').textContent=error.message;}
});
for(const id of ['filter-sub','filter-country','filter-tag','filter-search','filter-available'])$(id).addEventListener('input',renderNodes);
for(const id of ['pick-sub','pick-country','pick-tag','pick-search'])$(id).addEventListener('input',()=>renderPicker());
$('service-node').addEventListener('change',updatePickerSelection);
$('service-search').addEventListener('input',renderServices);
document.addEventListener('click',async event=>{
  document.querySelectorAll('.more-menu[open]').forEach(menu=>{if(!menu.contains(event.target)||event.target.closest('button'))menu.open=false;});
  const button=event.target.closest('button'); if(!button || button.disabled)return;
  if(button.dataset.close){$(button.dataset.close).close();return;}
  if(button.dataset.tab){openSearchSelect?.close(false);setTab(button.dataset.tab);return;}
  if(button.dataset.serviceFilter){serviceFilter=button.dataset.serviceFilter;renderServices();return;}
  const action=button.dataset.action,id=button.dataset.id;
  if(!action)return;
  try{
    if(action==='clear-service-filters'){$('service-search').value='';serviceFilter='all';renderServices();return;}
    if(action==='create-service')return await serviceForm();
    if(action==='edit-service')return await serviceForm(id);
    if(action==='use-node')return await serviceForm(null,Number(id));
    if(action==='create-subscription')return subscriptionForm();
    if(action==='edit-subscription')return subscriptionForm(id);
    if(action==='toggle-secret'){$('service-password').type=$('service-password').type==='password'?'text':'password';button.textContent=$('service-password').type==='password'?'显示':'隐藏';return;}
    if(action==='password'){$('password-form').reset();$('password-error').textContent='';$('password-dialog').showModal();return;}
    if(action==='edit-node'){const n=state.nodes.find(n=>String(n.id)===id);$('node-id').value=id;$('node-name').textContent=nodeDisplayName(n.name);$('node-country').value=n.country;$('node-tags').value=n.tags.join(', ');$('node-error').textContent='';$('node-dialog').showModal();return;}
    const serviceName=state?.services.find(s=>s.id===id)?.name||'此服务';
    if(action==='delete-service' && !await confirmAction({title:'删除服务？',message:`将删除「${serviceName}」，该端口的连接会立即停止。`,label:'删除服务',tone:'danger',symbol:'trash'}))return;
    if(action==='delete-subscription' && !await confirmAction({title:'删除订阅？',message:'订阅及其节点将被删除。正在被服务使用的订阅无法删除。',label:'删除订阅',tone:'danger',symbol:'trash'}))return;
    if(action==='stop' && !await confirmAction({title:'停止服务？',message:`「${serviceName}」的连接将中断，同时关闭开机自启。`,label:'停止服务'}))return;
    if(['start','stop','restart'].includes(action))return await runServiceAction(id,action);
    if(['copy-info','copy-login-user','copy-login-password'].includes(action)){
      const text=action==='copy-info'?$('info-content').textContent:$(action==='copy-login-user'?'service-login-user':'service-login-password').value;
      await copyText(text);
      toast(action==='copy-info'?'已复制':action==='copy-login-user'?'用户名已复制':'密码已复制');
      return;
    }
    await busy(button,async()=>{
      if(action==='reload'){await reload();toast('状态已刷新');}
      else if(action==='logout'){await api('/logout','POST',{});showLogin();}
      else if(action==='generate-credentials'){const c=await api('/credentials/generate','POST',{});$('service-user').value=c.username;$('service-password').value=c.password;toast('已生成新账号，保存后生效');}
      else if(action==='credentials')await showCredentials(id);
      else if(action==='login-info')await showServiceLogin(id);
      else if(action==='logs'){const r=await api(`/services/${id}/logs`);info('服务日志',r.logs);}
      else if(action==='test-service'){toast('正在测试出口和 UDP，可能需要几十秒…','info');const r=await api(`/services/${id}/test`,'POST',{});info('服务测试结果',formatProbe(r));await reload();}
      else if(action==='test-node'||action==='test-selected-node'){const node=action==='test-node'?id:$('service-node').value;if(!node)throw new Error('请先选择节点');toast('正在连接所选节点并查询出口…','info');const r=await api(`/nodes/${node}/test`,'POST',{});info('节点测试结果',formatProbe(r));}
      else if(action==='delete-service'){await api(`/services/${id}`,'DELETE');await reload();toast('服务已删除');}
      else if(action==='delete-subscription'){await api(`/subscriptions/${id}`,'DELETE');await reload();toast('订阅已删除');}
      else if(action==='refresh-subscription'){const r=await api(`/subscriptions/${id}/refresh`,'POST',{});await reload();toast(`更新成功：${r.count} 个节点${r.skipped?`，跳过 ${r.skipped} 个不支持的节点`:''}`);}
    });
  }catch(error){toast(error.message,'error');}
});
for(const dialog of document.querySelectorAll('dialog'))dialog.addEventListener('close',()=>{
  if(dialog.contains($('toast')))(Array.from(document.querySelectorAll('dialog[open]')).at(-1)||document.body).appendChild($('toast'));
  if(openSearchSelect&&dialog.contains(openSearchSelect.select))openSearchSelect.close(false);
  if(dialog.id==='info-dialog')$('info-content').textContent='';
  if(dialog.id==='service-login-dialog'){
    $('service-login-user').value=''; $('service-login-password').value=''; $('service-login-description').textContent='';
  }
  if(dialog.id==='service-dialog')$('service-password').value='';
  if(dialog.id==='subscription-dialog')$('subscription-url').value='';
});
document.addEventListener('keydown',event=>{if(event.key==='Escape')document.querySelectorAll('.more-menu[open]').forEach(menu=>{menu.open=false;menu.querySelector('summary').focus();});});
const formErrors={'login-form':'login-error','service-form':'service-error','subscription-form':'subscription-error','node-form':'node-error','password-form':'password-error'};
const fieldLabels={'login-password':'登录密码','service-name':'服务名称','service-port':'端口','service-node':'出口节点','service-user':'用户名','service-password':'密码','subscription-name':'订阅名称','subscription-url':'订阅链接','subscription-interval':'更新间隔','node-country':'地区','node-tags':'标签','password-current':'当前密码','password-new':'新密码'};
for(const [id,errorId] of Object.entries(formErrors)) {
  const form=$(id); form.noValidate=true;
  form.addEventListener('submit',event=>{
    const field=Array.from(form.elements).find(el=>el.willValidate&&!el.validity.valid);
    if(!field)return;
    event.preventDefault(); event.stopImmediatePropagation();
    const label=fieldLabels[field.id]||'内容'; let message=`请检查${label}的格式`;
    if(field.validity.valueMissing)message=(field.tagName==='SELECT'?'请选择':'请填写')+label;
    else if(field.validity.typeMismatch)message=`请输入有效的${label}`;
    else if(field.validity.tooShort)message=`${label}至少需要 ${field.minLength} 个字符`;
    else if(field.validity.tooLong)message=`${label}最多允许 ${field.maxLength} 个字符`;
    else if(field.validity.rangeUnderflow||field.validity.rangeOverflow)message=`${label}需在 ${field.min}～${field.max} 之间`;
    $(errorId).textContent=message; field.setAttribute('aria-invalid','true');
    const section=field.closest('details');if(section)section.open=true;
    field.focus();
  },true);
  form.addEventListener('input',event=>{event.target.removeAttribute('aria-invalid');$(errorId).textContent='';});
  form.addEventListener('reset',()=>{form.querySelectorAll('[aria-invalid]').forEach(el=>el.removeAttribute('aria-invalid'));$(errorId).textContent='';});
}
document.querySelectorAll('select:not([size])').forEach(select=>new SearchableSelect(select));
reload().catch(()=>showLogin());
setInterval(()=>{if(state&&!document.hidden&&!document.querySelector('dialog[open]'))reload().catch(()=>{});},30000);
