(function(){
'use strict';
const D=window.FastExperiment||{},C=window.CompanionSimpleData||{agents:[]};
const $=s=>document.querySelector(s),arr=v=>Array.isArray(v)?v:[];
const esc=v=>String(v==null?'—':v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const plain=v=>v==null?'—':typeof v==='string'?v:JSON.stringify(v,null,2);
const duration=v=>Number.isFinite(v)?(v>=1000?(v/1000).toLocaleString('zh-CN',{maximumFractionDigits:2})+' s':v.toLocaleString('zh-CN',{maximumFractionDigits:3})+' ms'):'—';
const clock=v=>Number.isFinite(v)?new Date(v).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false})+' 北京时间':'—';
const definitions=[
 {id:'decision',title:'决策',subtitle:'按场景选择模型或规则',summary:'读取显式场景与已有计划，生成本轮候选表达。规则场景按既定条件选择动作。',duties:['决定是否介入，选择本轮行为与候选表达。','仅使用传入消息；候选表达交给审核后才可发送。']},
 {id:'review',title:'规则审核',subtitle:'检查候选内容与状态',summary:'在前台用确定性规则检查候选表达、权限与状态，记录通过或拒绝结果。',duties:['检查当前候选表达、权限、停止指令与状态。','内容变更后重新检查；不自行扩大发送权限。']},
 {id:'execution',title:'代码交付',subtitle:'形成本机交付记录',summary:'由代码生成已批准的具体表达与本机交付记录；本轮未连接游戏客户端。',duties:['保持交付内容与审核通过版本一致。','记录本机交付结果；真实客户端展示尚未测量。']},
 {id:'planning',title:'规划',subtitle:'后台更新下一轮计划',summary:'在后台整理后续目标、模块选择与可复用计划；本轮首个有效交付不等待它。',duties:['根据已交付结果与显式消息更新后续计划。','标记依赖、适用范围、停止条件与可复用结果。']},
 {id:'reflection',title:'反馈反思',subtitle:'后台分析反馈与证据',summary:'根据实际输出和明确反馈提出改进建议，保留不确定性。',duties:['区分明确反馈、未回应与推测。','提出下一轮可验证的建议，不直接修改长期偏好。']},
 {id:'memory',title:'记忆整理',subtitle:'后台整理事实与版本',summary:'整理带来源的事实和更新建议，经检查后形成下一轮显式记忆消息。',duties:['区分事实、明确偏好和待核实推测。','记录来源与适用范围，检查版本后提交。']}
].map((a,i)=>({...C.agents.find(x=>x.id===a.id),...a,color:C.agents.find(x=>x.id===a.id)?.color||['#3184f5','#e5a037','#12a991','#8b5cf6','#d866b4','#6374db'][i]}));
const icons={decision:'M12 3v5 M12 8l-7 7m7-7 7 7 M5 11v4h4m6 0h4v-4 M12 8v13',review:'M12 3l8 4v5c0 5-8 9-8 9s-8-4-8-9V7z M8 12l3 3 5-6',execution:'M13 3L4 14h7l-1 7 10-12h-7z',planning:'M5 4h14v5H5z M5 15h5v5H5z M14 15h5v5h-5z M12 9v3H7v3 M12 12h5v3',reflection:'M4 10a8 8 0 1 1 1 7 M4 4v6h6 M12 8v5l3 2',memory:'M4 5c0-2 16-2 16 0v14c0 2-16 2-16 0z M4 5c0 2 16 2 16 0 M4 12c0 2 16 2 16 0'};
const rounds=Array.from({length:Math.max(3,arr(D.rounds).length)},(_,i)=>arr(D.rounds)[i]||{id:'pending-'+i,title:'场景 '+(i+1),pending:true});
let roundIndex=0,selected='decision';
try{const seed=JSON.parse($('#document-seed')?.textContent||'{}');if(Number.isInteger(seed.roundIndex)&&rounds[seed.roundIndex])roundIndex=seed.roundIndex;if(definitions.some(a=>a.id===seed.selected))selected=seed.selected;}catch(_){}
const current=()=>rounds[roundIndex];
const records=id=>arr(current().nodes).filter(n=>n.role===id);
const total=nn=>nn.length&&nn.every(n=>Number.isFinite(n.duration_ms))?nn.reduce((s,n)=>s+n.duration_ms,0):null;
const modelCall=n=>typeof n.requested_model==='string'&&n.requested_model.trim()&&!/^(code|rules?|python|javascript|none|n\/a|—)$/i.test(n.requested_model.trim());
const config=n=>modelCall(n)?[n.requested_model,n.effort].filter(Boolean).join(' · '):n.implementation||n.requested_model||'确定性代码';
const ruleScope='规则节点仅测本机处理；首条交付计时止于闸门返回，不含记录写盘、网络和界面展示。';
const modelScope='模型路径包含真实独立会话的调度与工具开销，不是纯 API 时延。';
function packet(title,value,open=false){return `<details class="fast-packet" ${open?'open':''}><summary>${esc(title)}</summary><pre>${esc(plain(value))}</pre></details>`;}
function notes(values){return arr(values).map(v=>`<p class="fast-note">${esc(plain(v))}</p>`).join('');}
function setup(){
 document.querySelectorAll('#fast-controls,#fast-metrics,#fast-sections').forEach(e=>e.remove());
 document.body.classList.add('fast-page');document.title='陪伴精灵 · 快速交付实测';
 $('.brand p').textContent='FAST DELIVERY · REPLAY';
 $('.source-status').textContent=arr(D.rounds).length?'独立 Sol 任务 · 合成游戏场景':'等待实测结果';
 const link=$('#experiment-link');if(link){link.textContent='历史实测回放';link.href='experiment.html';}
 $('.flow-heading').innerHTML='<div><div class="eyebrow">FOREGROUND FIRST · BACKGROUND LATER</div><h2>快速交付实测</h2><p>前台先交付，后台按需处理。本次调用反思、记忆，未调用规划。</p></div><div class="legend"><span><i></i>前台先后</span><span><i class="dashed"></i>后台 / 下一轮</span></div>';
 for(const [id,cls] of [['fast-controls','fast-controls'],['fast-metrics','fast-metrics']]){const el=document.createElement('div');el.id=id;el.className=cls;$('.canvas').before(el);}
 const sections=document.createElement('div');sections.id='fast-sections';sections.className='fast-sections';$('.canvas').after(sections);
 $('#graph-plane').innerHTML=`<div class="background-group" aria-hidden="true"></div><div class="group-title">后台 · 不阻塞首个交付</div><div class="fast-front-label">前台</div>
 <svg class="graph-svg" viewBox="0 0 900 590" aria-hidden="true"><defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M1 1l5 3-5 3" fill="none" stroke="#b7c2d0" stroke-width="1.3"/></marker><marker id="active-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M1 1l5 3-5 3" fill="none" stroke="var(--accent)" stroke-width="1.3"/></marker></defs>
 <path class="edge" data-link="decision" d="M173 79V124" marker-end="url(#arrow)"/><path class="edge" data-link="decision review" d="M274 202H338" marker-end="url(#arrow)"/><path class="edge" data-link="review execution" d="M548 202H612" marker-end="url(#arrow)"/>
 <path class="edge background" data-link="execution planning" d="M721 272V314H173V380" marker-end="url(#arrow)"/><path class="edge background" data-link="execution reflection" d="M447 314V380" marker-end="url(#arrow)"/><path class="edge background" data-link="execution memory" d="M721 314V380" marker-end="url(#arrow)"/>
 <path class="edge background" data-link="memory decision" d="M721 528V559H35V202H64" marker-end="url(#arrow)"/>
 <text class="edge-label" x="306" y="188" text-anchor="middle">候选表达</text><text class="edge-label" x="584" y="188" text-anchor="middle">批准版本</text><text class="edge-label" x="730" y="298">交付后</text><text class="edge-label small" x="449" y="578" text-anchor="middle">后台结果经检查后，以显式消息供下一轮读取</text>
 </svg><div class="trigger">用户 / 场景事件</div><div class="phase-note">模型或规则决策 → 规则审核 → 代码交付</div><div id="nodes"></div><div class="mobile-loop">后台模块按需执行；结果经检查后，供下一轮显式读取。</div>`;
 $('.graph-help span').textContent='点击任一模块查看实际调用、输入消息、原始输出与错误。灰色模块表示本轮没有对应执行记录。';
 $('.footer-note').innerHTML='<span>仅展示已记录结果；首个有效交付时间不等于完整后台耗时。</span><button class="fast-text-button" id="download-json" type="button">下载原始 JSON</button>';
 $('#download-html').textContent='下载实测 HTML';
}
function render(){
 const r=current();
 $('#fast-controls').innerHTML=rounds.map((v,i)=>`<button type="button" class="fast-round ${i===roundIndex?'active':''}" data-round="${i}" aria-pressed="${i===roundIndex}"><span>${String(i+1).padStart(2,'0')}</span>${esc(v.title||'场景 '+(i+1))}</button>`).join('');
 $('#fast-metrics').innerHTML=`<div class="fast-primary"><span>首条交付记录耗时</span><b>${duration(r.foreground_ms)}</b><small>${esc(r.timing_scope||(r.route==='rules'?'仅进程内处理，不含网络和界面':r.route==='model'?'含独立会话、调度与工具开销':'等待计时记录'))}</small></div><div><span>本轮前台路径</span><b class="fast-route">${r.route==='rules'?'规则直达':r.route==='model'?'模型决策':'—'}</b><small>规则审核 · 代码交付</small></div><div><span>交付后后台耗时</span><b>${duration(r.background_ms)}</b><small>本轮完整 Loop：${duration(r.full_loop_ms)}；不含故障探针</small></div>`;
 $('#nodes').innerHTML=definitions.map((a,i)=>{const nn=records(a.id),count=nn.filter(modelCall).length,latest=nn.at(-1);return `<button type="button" class="node ${nn.length?'':'not-called'} ${selected===a.id?'selected':''}" style="--node-color:${a.color}" data-agent="${a.id}" aria-label="查看${a.title}详情" aria-pressed="${selected===a.id}"><div class="node-head"><span class="node-symbol"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="${icons[a.id]}"/></svg></span><span class="node-number">${nn.length?nn.length+' 次执行':!Array.isArray(r.nodes)?'待记录':'无执行记录'}</span></div><h3>${a.title}</h3><p>${nn.length?esc(config(latest)):a.subtitle}</p><div class="node-meta"><span>${nn.length?count+' 次模型任务':!Array.isArray(r.nodes)?'—':'0 次模型任务'}</span><b>${duration(total(nn))}</b></div></button>`;}).join('');
 $('#fast-sections').innerHTML=renderPair()+renderEvidence();
 renderDetails();highlight();fit();
}
function renderPair(){
 const p=D.pair||{};
 return `<section class="fast-box"><div class="fast-box-heading"><h3>同一决策产出的分支对照</h3><span>单次工具链实测</span></div><p class="fast-note">两个分支使用同一个真实决策产出的候选表达，分别记录代码路径与后续模型审核、模型执行的追加耗时。不是生产 API A/B。</p><div class="fast-pair"><div><span>规则审核 + 代码交付</span><b>${duration(p.fast_ms)}</b></div><div><span>LLM 审核 + LLM 执行</span><b>${duration(p.baseline_ms)}</b></div></div><p class="fast-note">${esc(p.scope||'等待配对计时口径。')}</p>${packet('共同候选表达与完整配对记录',p)}${notes(p.notes)}</section>`;
}
function renderEvidence(){
 const checks=[...arr(D.checks),...arr(current().checks)],failed=checks.filter(c=>c.pass===false).length;
 const bench=arr(D.rule_benchmark);
 return `<section class="fast-box"><details class="fast-disclosure"><summary><span>真实检查与事件日志</span><small>${checks.length?checks.filter(c=>c.pass===true).length+' 项通过 · '+failed+' 项需检查':'暂无检查记录'}</small></summary><div class="fast-checks">${checks.length?checks.map(c=>`<div class="fast-check ${c.pass===false?'failed':''}"><span>${c.pass===true?'通过':c.pass===false?'未通过':'待核实'}</span><div><b>${esc(c.title||c.id)}</b><p>${esc(plain(c.evidence))}</p></div></div>`).join(''):'<p class="fast-note">—</p>'}</div>${packet('原始事件日志',D.event_log)}${packet('本轮补充记录',current().notes)}</details></section>
 <section class="fast-box"><details class="fast-disclosure"><summary><span>计时口径与规则基准</span><small>${bench.length?bench.length+' 组规则样本':'查看测量边界'}</small></summary><p class="fast-note">${ruleScope}</p><p class="fast-note">${modelScope}</p><p class="fast-note">${esc(D.meta?.token_note||'Token 用量未提供，保持空值。')}</p>${bench.length?'<div class="fast-table-wrap"><table class="fast-table"><thead><tr><th>规则场景</th><th>次数</th><th>中位数</th><th>P95</th><th>最大值</th></tr></thead><tbody>'+bench.map(b=>`<tr><td>${esc(b.case)}</td><td>${esc(b.n)}</td><td>${duration(b.median_ms)}</td><td>${duration(b.p95_ms)}</td><td>${duration(b.max_ms)}</td></tr>`).join('')+'</tbody></table></div>':''}${packet('原始规则基准与口径',D.rule_benchmark)}${packet('完整实验方法',D.meta)}${notes(D.notes)}</details></section>`;
}
function renderDetails(){
 const a=definitions.find(v=>v.id===selected),r=current(),nn=records(selected),count=nn.filter(modelCall).length;
 $('#detail-panel').innerHTML=`<div class="fast-result"><div class="eyebrow">${esc(r.title||r.id)} · 本轮交付</div><div class="fast-user"><b>玩家</b><p>${esc(r.user_input)}</p></div><div class="fast-reply"><b>陪伴精灵</b><p>${esc(r.reply)}</p></div></div>
 <div class="detail-header"><div class="module-type">${selected.toUpperCase()} · ${['planning','reflection','memory'].includes(selected)?'后台模块':'前台模块'}</div><div class="detail-title"><h2>${a.title}</h2><button type="button" class="close-panel" aria-label="关闭详情"><svg viewBox="0 0 24 24"><path d="M6 6l12 12M6 18L18 6"/></svg></button></div><p>${a.summary}</p></div>
 <section class="section"><div class="section-title"><h3>职责与边界</h3></div><ul class="detail-list">${a.duties.map(v=>'<li>'+esc(v)+'</li>').join('')}</ul></section>
 <section class="section"><div class="section-title"><h3>模型 / 代码与实际调用</h3></div><div class="fast-detail-metrics"><div><b>${!Array.isArray(r.nodes)?'—':nn.length}</b><span>执行记录</span></div><div><b>${!Array.isArray(r.nodes)?'—':count}</b><span>模型任务</span></div><div><b>${duration(total(nn))}</b><span>累计节点耗时</span></div></div>${nn.length?nn.map(n=>`<p class="fast-config">${esc(config(n))}<span>${esc(n.status||'状态未记录')}</span></p>`).join(''):'<p class="fast-note">本轮没有对应执行记录，不能据此推断后台任务已完成。</p>'}<p class="fast-note">${count?modelScope:ruleScope}</p><p class="fast-note">${esc(D.meta?.token_note||'Token 未提供。')}</p></section>
 <section class="section"><div class="section-title"><h3>显式输入与原始输出</h3></div>${nn.length?nn.map((n,i)=>`<div class="fast-record-label">${esc(n.id||'记录 '+(i+1))}</div>${packet('完整输入消息',n.input_messages)}${packet('原始输出',n.output,true)}${packet('完整节点记录',n)}`).join(''):'<p class="fast-note">—</p>'}</section>
 <section class="section"><div class="section-title"><h3>运行时间与错误</h3></div>${nn.map(n=>`<div class="fast-log"><b>${esc(n.id)}</b><p>调度：${esc(clock(n.dispatch_unix_ms))}</p><p>完成：${esc(clock(n.completed_unix_ms))}</p><p>耗时：${duration(n.duration_ms)}</p></div>`).join('')}${nn.flatMap(n=>arr(n.issues)).length?nn.flatMap(n=>arr(n.issues)).map(e=>packet(typeof e==='string'?e:e.code||'错误 / 检查记录',e,true)).join(''):`<p class="fast-note">${nn.length?'该模块未记录错误；内容正确性以真实检查证据为准。':'暂无记录。'}</p>`}</section>`;
 $('#detail-panel').scrollTop=0;
}
function highlight(){const a=definitions.find(v=>v.id===selected);document.documentElement.style.setProperty('--accent',a.color);document.querySelectorAll('.node').forEach(n=>{n.classList.toggle('selected',n.dataset.agent===selected);n.setAttribute('aria-pressed',String(n.dataset.agent===selected));});document.querySelectorAll('.edge').forEach(e=>{const active=e.dataset.link.split(' ').includes(selected);e.classList.toggle('active',active);e.setAttribute('marker-end',active?'url(#active-arrow)':'url(#arrow)');});}
function fit(){const wrap=$('#graph-wrap'),plane=$('#graph-plane');if(window.innerWidth<=600){plane.style.transform='none';wrap.style.height='auto';return;}const scale=Math.min(wrap.clientWidth/900,1.1);plane.style.transform=`translateX(${Math.max(0,(wrap.clientWidth-900*scale)/2)}px) scale(${scale})`;wrap.style.height=590*scale+'px';}
function close(){document.body.classList.remove('panel-open');}
function download(value,type,name){const u=URL.createObjectURL(new Blob([value],{type})),a=document.createElement('a');a.href=u;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),1000);}
function exportHTML(){const root=document.documentElement.cloneNode(true);root.querySelector('#document-seed').textContent=JSON.stringify({roundIndex,selected}).replace(/</g,'\\u003c');root.querySelector('#fast-results').textContent='window.FastExperiment='+JSON.stringify(D).replace(/</g,'\\u003c')+';';root.querySelector('#toast-root').innerHTML='';root.querySelector('#experiment-link')?.remove();root.querySelector('body').classList.remove('panel-open');download('<!doctype html>\n'+root.outerHTML,'text/html;charset=utf-8','陪伴精灵-快速交付实测.html');}
document.addEventListener('click',e=>{const target=e.target instanceof Element?e.target:null;if(!target)return;const round=target.closest('[data-round]');if(round){roundIndex=Number(round.dataset.round);selected='decision';render();return;}const node=target.closest('[data-agent]');if(node){selected=node.dataset.agent;highlight();renderDetails();document.body.classList.add('panel-open');return;}if(target.closest('.close-panel')||target.id==='mobile-backdrop')close();if(target.closest('#download-json'))download(JSON.stringify(D,null,2),'application/json;charset=utf-8','fast-loop-results.json');if(target.closest('#download-html'))exportHTML();});
document.addEventListener('keydown',e=>{if(e.key==='Escape')close();});
setup();render();if(typeof ResizeObserver!=='undefined')new ResizeObserver(fit).observe($('#graph-wrap'));else window.addEventListener('resize',fit);
}());
