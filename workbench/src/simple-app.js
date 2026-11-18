(function(){
  'use strict';
  const data=window.CompanionSimpleData;
  const $=s=>document.querySelector(s);
  const esc=v=>String(v==null?'':v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const icons={planning:'M5 4h14v5H5z M5 15h5v5H5z M14 15h5v5h-5z M12 9v3H7v3 M12 12h5v3',decision:'M12 3v5 M12 8l-7 7m7-7 7 7 M5 11v4h4m6 0h4v-4 M12 8v13',review:'M12 3l8 4v5c0 5-8 9-8 9s-8-4-8-9V7z M8 12l3 3 5-6',execution:'M13 3L4 14h7l-1 7 10-12h-7z',reflection:'M4 10a8 8 0 1 1 1 7 M4 4v6h6 M12 8v5l3 2',memory:'M4 5c0-2 16-2 16 0v14c0 2-16 2-16 0z M4 5c0 2 16 2 16 0 M4 12c0 2 16 2 16 0'};
  const icon=id=>`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${icons[id]}"></path></svg>`;
  const shortTitle=id=>data.agents.find(a=>a.id===id).title.replace(' Agent','');
  let seed={};try{seed=JSON.parse($('#document-seed').textContent)||{};}catch(_){}
  const docId=typeof seed.docId==='string'?seed.docId:'companion-flow-v2';
  const storageKey='companion-simple:'+docId;
  let modelNames={...(seed.models||{})},storageAvailable=true,selected='planning';
  try{const stored=JSON.parse(localStorage.getItem(storageKey)||'null');if(stored&&stored.models&&typeof stored.models==='object')modelNames={...modelNames,...stored.models};}catch(_){storageAvailable=false;}
  const modelName=id=>typeof modelNames[id]==='string'?modelNames[id].trim().slice(0,180):'';
  const tokens=v=>typeof v==='number'&&Number.isFinite(v)&&v>=0?v.toLocaleString('zh-CN'):'—';
  function save(){try{localStorage.setItem(storageKey,JSON.stringify({models:modelNames}));storageAvailable=true;}catch(_){storageAvailable=false;}$('#save-status').textContent=storageAvailable?'模型配置已保存于当前浏览器':'请下载 HTML 保存当前配置';}
  function drawNodes(){
    $('#nodes').innerHTML=data.agents.map((a,i)=>`<button type="button" class="node ${a.id===selected?'selected':''}" style="--node-color:${a.color}" data-agent="${a.id}" aria-label="查看${esc(a.title)}详情" aria-pressed="${a.id===selected}"><div class="node-head"><span class="node-symbol">${icon(a.id)}</span><span class="node-number">0${i+1}</span></div><h3>${esc(shortTitle(a.id))}</h3><p>${esc(a.subtitle)}</p><div class="node-meta"><span data-model-label="${a.id}">${esc(modelName(a.id)||'基座模型待选择')}</span><b>${a.id==='planning'?'按需调用':a.id==='decision'?'轻 / 重':a.id==='review'?'规则优先':a.id==='execution'?'轻执行':a.id==='reflection'?'重思考':'轻整理'}</b></div></button>`).join('');
  }
  function list(items){return`<ul class="detail-list">${items.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`;}
  function links(items,kind){return`<div class="link-list">${items.map(x=>`<div class="link-item"><div class="link-name">${esc(x[kind])}</div><p>${esc(x.data)}</p></div>`).join('')}</div>`;}
  function renderDetails(){
    const a=data.agents.find(a=>a.id===selected);
    const total=typeof a.tokens.input==='number'&&typeof a.tokens.output==='number'?a.tokens.input+a.tokens.output:null;
    const idx=data.agents.indexOf(a)+1;
    $('#detail-panel').innerHTML=`<div class="detail-header"><div class="module-type">MODULE 0${idx} · 模块详情</div><div class="detail-title"><h2 id="detail-title">${esc(a.title)}</h2><button type="button" class="close-panel" aria-label="关闭详情"><svg viewBox="0 0 24 24"><path d="M6 6l12 12M6 18L18 6"/></svg></button></div><p>${esc(a.summary)}</p><div class="route-tag">${esc(a.thinking)}</div></div>
      <section class="section"><div class="section-title"><h3>职责与权限</h3></div>${list(a.duties)}<div class="permission-box"><div class="mini-label">可以做什么</div>${list(a.powers)}</div><div class="boundaries"><b>权限边界</b> · ${a.limits.map(esc).join(' ')}</div></section>
      <section class="section"><div class="section-title"><h3><label for="model-name">基座模型</label></h3><span class="section-hint" id="model-save-state">可填写，自动保存</span></div><input class="model-input" id="model-name" type="text" maxlength="180" value="${esc(modelName(a.id))}" placeholder="${esc(a.model.name)} · 填写模型名称" autocomplete="off"><p class="model-note">${esc(a.model.route)}</p></section>
      <section class="section"><div class="section-title"><h3>Token 消耗</h3><span class="section-hint">本次调用</span></div><div class="token-grid"><div class="token-box"><b>${tokens(a.tokens.input)}</b><span>输入 Token</span></div><div class="token-box"><b>${tokens(a.tokens.output)}</b><span>输出 Token</span></div><div class="token-box"><b>${tokens(total)}</b><span>合计</span></div></div><p class="no-record">${esc(a.tokens.source)}，暂不显示估算数值。</p></section>
      <section class="section"><div class="section-title"><h3>信息链路</h3></div><div class="mini-label">输入来自</div>${links(a.inputs,'from')}<div class="output-list"><div class="mini-label">输出给谁</div>${links(a.outputs,'to')}</div><div class="parallel-note">${esc(a.parallel)}</div></section>
      <section class="section"><div class="section-title"><h3>运行日志 <span style="color:#a3adba;font-weight:400">Log</span></h3><span class="demo-badge">格式示例</span></div>${a.logs.length?a.logs.map(l=>`<div class="log-row"><div class="log-time">${esc(l.time)} · ${esc(l.level.toUpperCase())}</div><p>${esc(l.message)}</p></div>`).join(''):'<p class="empty-state">暂无运行日志。</p>'}<p class="no-record">示例记录 ${esc(a.logs[0]?.run||'')}，不代表真实调用。</p></section>
      <section class="section"><div class="section-title"><h3>错误历史</h3><span class="demo-badge">格式示例</span></div>${a.errors.length?a.errors.map(e=>`<details class="error-card"><summary><span class="error-dot"></span><span>${esc(e.message)}</span><span class="error-chevron">›</span></summary><div class="error-detail"><div class="error-code">${esc(e.time)} · ${esc(e.code)}</div><dl><dt>原因</dt><dd>${esc(e.cause)}</dd><dt>处理</dt><dd>${esc(e.fix)}</dd><dt>状态</dt><dd>${esc(e.status)}</dd></dl></div></details>`).join(''):'<p class="empty-state">暂无错误记录。</p>'}</section>`;
    $('#detail-panel').scrollTop=0;
  }
  function highlight(){
    const a=data.agents.find(a=>a.id===selected);document.documentElement.style.setProperty('--accent',a.color);
    document.querySelectorAll('.node').forEach(n=>{n.classList.toggle('selected',n.dataset.agent===selected);n.setAttribute('aria-pressed',String(n.dataset.agent===selected));});
    document.querySelectorAll('.edge').forEach(e=>{const active=e.dataset.link.split(' ').includes(selected);e.classList.toggle('active',active);e.setAttribute('marker-end',active?'url(#active-arrow)':'url(#arrow)');});
  }
  function select(id,open=true){if(!data.agents.some(a=>a.id===id))return;selected=id;highlight();renderDetails();if(open)document.body.classList.add('panel-open');}
  function close(){document.body.classList.remove('panel-open');const n=document.querySelector(`.node[data-agent="${selected}"]`);if(n)n.focus({preventScroll:true});}
  function fit(){if(window.innerWidth<=600){$('#graph-plane').style.transform='none';$('#graph-wrap').style.height='auto';return;}const w=$('#graph-wrap').clientWidth;const scale=Math.min(w/900,1.15);$('#graph-plane').style.transform=`translateX(${Math.max(0,(w-900*scale)/2)}px) scale(${scale})`;$('#graph-wrap').style.height=`${640*scale}px`;}
  function toast(text){const el=document.createElement('div');el.className='toast';el.textContent=text;$('#toast-root').appendChild(el);setTimeout(()=>el.remove(),3800);}
  function download(){
    const root=document.documentElement.cloneNode(true);
    root.querySelector('#experiment-link')?.remove();
    root.querySelector('#document-seed').textContent=JSON.stringify({docId:'flow-'+Date.now().toString(36),models:modelNames}).replace(/</g,'\\u003c');
    root.querySelector('body').classList.remove('panel-open');root.querySelector('#toast-root').innerHTML='';
    const blob=new Blob(['<!doctype html>\n'+root.outerHTML],{type:'text/html;charset=utf-8'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='陪伴精灵-Agent流程图.html';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('已下载 HTML，包含当前模型配置。');
  }
  document.addEventListener('click',e=>{const node=e.target.closest('[data-agent]');if(node)select(node.dataset.agent);if(e.target.closest('.close-panel')||e.target.id==='mobile-backdrop')close();});
  document.addEventListener('input',e=>{if(e.target.id!=='model-name')return;modelNames[selected]=e.target.value.slice(0,180);save();const label=document.querySelector(`[data-model-label="${selected}"]`);if(label)label.textContent=modelName(selected)||'基座模型待选择';$('#model-save-state').textContent=storageAvailable?'已保存':'下载 HTML 可保存';});
  document.addEventListener('keydown',e=>{if(e.key==='Escape')close();});
  $('#download-html').addEventListener('click',download);
  drawNodes();select('planning',false);fit();
  if(typeof ResizeObserver!=='undefined'){new ResizeObserver(fit).observe($('#graph-wrap'));}else window.addEventListener('resize',fit);
  if(!storageAvailable)$('#save-status').textContent='请下载 HTML 保存当前配置';
}());
