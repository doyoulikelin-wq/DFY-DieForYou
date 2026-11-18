(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const sourceElement = $('streaming-data');
  let data;
  try { data = JSON.parse(sourceElement.textContent); }
  catch (error) { $('footer-note').textContent = '数据暂时无法读取，请重新打开完整 HTML 文件。'; return; }
  const sources = new Map((data.sources || []).map(s => [s.id, s]));
  const modules = new Map((data.modules || []).map(m => [m.id, m]));
  let selectedModule = 'route';
  let scenarioIndex = 0;
  let currentMs = 0;
  let playing = false;
  let animation = null;
  let previousFrame = null;
  let renderedCount = -1;
  let timelineWidth = 720;
  const maxMs = () => Math.max(1, Number(scenario().duration_ms) || 1);
  const scenario = () => (data.scenarios || [])[scenarioIndex] || {events: [], segments: [], nodes: []};
  const fmt = value => {
    if (value === null || value === undefined || !Number.isFinite(Number(value))) return '—';
    const n = Number(value);
    return `${(n / 1000).toFixed(n < 1000 ? 3 : n < 10000 ? 2 : 1)} s`;
  };
  const text = (tag, value, cls) => {
    const el = document.createElement(tag);
    el.textContent = value == null ? '' : String(value);
    if (cls) el.className = cls;
    return el;
  };
  const array = value => Array.isArray(value) ? value : value == null ? [] : [value];
  const list = values => { const el = document.createElement('ul'); array(values).forEach(v => el.append(text('li', v))); return el; };
  const safeLink = (label, value) => {
    const el = text('a', label);
    try {
      const base = /^https?:$/.test(location.protocol) ? location.href : 'https://companion-agent-studio-nov15.mylssssdddd.chatgpt.site/';
      const url = new URL(value, base);
      if (['http:', 'https:'].includes(url.protocol)) { el.href = url.href; el.target = '_blank'; el.rel = 'noopener noreferrer'; }
    } catch (_) {}
    return el;
  };
  const setList = (id, values) => { const el = $(id); el.replaceChildren(...array(values).map(v => text('li', v))); };
  const laneName = lane => ({user: '玩家可见', foreground: '前台内部', background: '后台静默'}[lane] || lane || '前台内部');
  const announce = value => { $('live-status').textContent = value; };
  $('data-date').textContent = data.meta && data.meta.date ? `资料核对：${data.meta.date}` : '';
  $('footer-note').textContent = data.meta?.note || '本页展示设计预算与既有证据；预演不会调用模型 API 或游戏接口。';
  if (data.meta?.title) document.title = data.meta.title;

  function setupTabs() {
    const buttons = Array.from(document.querySelectorAll('[data-tab]'));
    function select(name, focus) {
      for (const button of buttons) {
        const active = button.dataset.tab === name;
        button.setAttribute('aria-selected', String(active));
        button.tabIndex = active ? 0 : -1;
        $(`panel-${button.dataset.tab}`).hidden = !active;
        if (active && focus) button.focus();
      }
      if (name === 'plan') requestAnimationFrame(drawEdges);
      else pause();
    }
    buttons.forEach((button, index) => {
      button.addEventListener('click', () => select(button.dataset.tab, false));
      button.addEventListener('keydown', event => {
        let next;
        if (event.key === 'ArrowRight') next = (index + 1) % buttons.length;
        if (event.key === 'ArrowLeft') next = (index + buttons.length - 1) % buttons.length;
        if (event.key === 'Home') next = 0;
        if (event.key === 'End') next = buttons.length - 1;
        if (next != null) { event.preventDefault(); select(buttons[next].dataset.tab, true); }
      });
    });
    select('plan', false);
  }

  function renderBaseline() {
    const target = $('baseline-metrics'); target.replaceChildren();
    for (const metric of data.baseline?.metrics || []) {
      const box = text('article', '', 'metric');
      if (metric.kind) box.append(text('span', metric.kind, `tag ${/未测|未采集|未知/.test(metric.kind) ? 'unknown-tag' : /预算|目标/.test(metric.kind) ? 'planned-tag' : 'measured-tag'}`));
      box.append(text('div', metric.value, 'metric-value'), text('h3', metric.label), text('p', metric.detail));
      if (metric.href) box.append(safeLink('查看证据 ↗', metric.href));
      target.append(box);
    }
    const rows = $('baseline-rows'); rows.replaceChildren();
    for (const row of data.baseline?.rows || []) {
      const tr = document.createElement('tr');
      tr.append(text('td', row.scenario), text('td', fmt(row.candidate_ms)), text('td', fmt(row.loop_ms)));
      rows.append(tr);
    }
    setList('baseline-limits', data.baseline?.limits || []);
    const issues = $('difficulties-list'); issues.replaceChildren();
    for (const item of data.difficulties || []) {
      const row = text('article', '', 'issue'); row.append(text('h3', item.title), text('p', item.evidence), text('p', item.change, 'issue-change')); issues.append(row);
    }
  }

  function renderResearch() {
    const target = $('research-list'); target.replaceChildren();
    (data.research || []).forEach((item, index) => {
      const row = text('article', '', 'research-item');
      const heading = document.createElement('div');
      heading.append(text('span', `${String(index + 1).padStart(2, '0')} · ${item.priority || '研究方案'}`, 'research-number'), text('h3', item.title));
      const links = text('div', '', 'research-links');
      array(item.source_ids).forEach(id => { const s = sources.get(id); if (s) links.append(safeLink(s.publisher || s.title, s.url)); });
      heading.append(links);
      const body = text('div', '', 'research-body');
      [['机制', item.mechanism, ''], ['用于本项目', item.fit, ''], ['适用边界', item.limit, 'research-limit']].forEach(([label, value, cls]) => {
        const p = text('p', '', cls); p.append(text('b', label), document.createTextNode(value || '')); body.append(p);
      });
      row.append(heading, body); target.append(row);
    });
    const refs = $('sources-list'); refs.replaceChildren();
    for (const source of data.sources || []) {
      const li = document.createElement('li'); li.id = `source-${source.id}`;
      li.append(safeLink(source.title, source.url), text('small', `${source.publisher || ''}${source.checked ? ` · 核对 ${source.checked}` : ''}`)); refs.append(li);
    }
  }

  function renderModule(id) {
    selectedModule = id;
    const module = modules.get(id); if (!module) return;
    const target = $('module-detail'); target.replaceChildren();
    const overview = text('div', '', 'module-overview');
    overview.append(text('p', '模块详情 · 点击流程切换', 'inspector-type'));
    const title = text('h3', module.title); title.id = 'inspector-title'; overview.append(title);
    const model = text('div', '', 'inspector-model'); model.append(text('b', module.model || '应用代码'), document.createTextNode(module.effort ? ` · ${module.effort}` : '')); overview.append(model, text('p', module.role, 'role')); target.append(overview);
    function section(title, values, disclosure) {
      const box = text('section', '', 'inspector-section');
      if (disclosure) { const details = document.createElement('details'); details.append(text('summary', title), list(values)); box.append(details); }
      else { box.append(text('h4', title), list(values)); }
      target.append(box);
    }
    section('职责与权能', module.rights);
    const budget = text('section', '', 'inspector-section inspector-budget'); budget.append(text('h4', '预期消耗 · 规划预算'));
    [['TOKEN', module.token_budget], ['时间', module.latency_budget]].forEach(([label, value]) => { const p = document.createElement('p'); p.append(text('strong', label), document.createTextNode(value || '尚待确定')); budget.append(p); }); target.append(budget);
    section('接收的信息包', module.inputs);
    section('交出的成果', module.outputs);
    section('先后与并行', [...array(module.depends).map(v => `先后：${v}`), ...array(module.parallel).map(v => `并行：${v}`)]);
    section('Log · 应记录什么', module.logs, true);
    section('错误历史与防线', module.errors, true);
    updateNodeState();
  }

  const edgeDefinitions = [
    ['input', 'route', 'vertical'], ['route', 'instant', 'branch'], ['route', 'fast', 'branch'], ['route', 'plan', 'branch'], ['route', 'tools', 'branch', false, true],
    ['instant', 'gate', 'join'], ['fast', 'gate', 'join'], ['plan', 'fast', 'side'], ['plan', 'tools', 'side'], ['tools', 'fast', 'return'],
    ['gate', 'deliver', 'vertical'], ['deliver', 'reflect', 'branch', true], ['reflect', 'memory', 'side', true]
  ];
  function drawEdges() {
    const flow = $('flow'), svg = $('flow-lines'), target = $('flow-edges');
    if (!flow || flow.offsetWidth === 0) return;
    target.replaceChildren(); svg.setAttribute('viewBox', `0 0 ${flow.offsetWidth} ${flow.offsetHeight}`);
    const flowRect = flow.getBoundingClientRect();
    const get = id => {
      const el = flow.querySelector(`[data-node="${id}"]`); if (!el) return null;
      const r = el.getBoundingClientRect(); return {x:r.left-flowRect.left,y:r.top-flowRect.top,w:r.width,h:r.height};
    };
    for (const [from, to, shape, background, optional] of edgeDefinitions) {
      const a = get(from), b = get(to); if (!a || !b) continue;
      const path = document.createElementNS('http://www.w3.org/2000/svg','path');
      let d;
      if (shape === 'return') {
        // Tool results return under the whole branch row, then enter the
        // decision node from its left edge without crossing the planner.
        const x1=a.x+a.w*.72, y1=a.y+a.h, x2=b.x, y2=b.y+b.h/2;
        const rail=y1+30, left=x2-7;
        d=`M ${x1} ${y1} L ${x1} ${rail-5} Q ${x1} ${rail} ${x1-5} ${rail} L ${left+5} ${rail} Q ${left} ${rail} ${left} ${rail-5} L ${left} ${y2+5} Q ${left} ${y2} ${left+5} ${y2} L ${x2} ${y2}`;
      } else if (shape === 'side') {
        const rightward = b.x > a.x;
        const x1 = rightward ? a.x+a.w : a.x, x2 = rightward ? b.x : b.x+b.w;
        const y = a.y+a.h/2;
        d = `M ${x1} ${y} L ${x2} ${y}`;
      } else {
        const x1 = a.x+a.w/2, y1 = a.y+a.h, x2=b.x+b.w/2, y2=b.y;
        const middle = y1+(y2-y1)/2;
        d=`M ${x1} ${y1} L ${x1} ${middle} L ${x2} ${middle} L ${x2} ${y2}`;
      }
      path.setAttribute('d',d); path.setAttribute('class',`flow-edge${background ? ' is-background' : ''}${optional ? ' is-optional' : ''}`); path.dataset.from=from; path.dataset.to=to; target.append(path);
    }
    updateNodeState();
  }

  function updateNodeState() {
    const nodes = new Set(scenario().nodes || []);
    const currentEvent = array(scenario().events).filter(e => e.at <= currentMs).at(-1);
    document.querySelectorAll('[data-node]').forEach(button => {
      const id = button.dataset.node;
      button.classList.toggle('selected', id === selectedModule);
      button.classList.toggle('is-route', nodes.has(id));
      button.classList.toggle('is-outside', nodes.size > 0 && !nodes.has(id));
      button.classList.toggle('is-now', currentMs > 0 && currentEvent?.node === id);
      button.setAttribute('aria-pressed', String(id === selectedModule));
    });
    document.querySelectorAll('.flow-edge').forEach(edge => {
      let active=nodes.has(edge.dataset.from) && nodes.has(edge.dataset.to);
      // With planning selected, tool requests and the final decision depend
      // on its DAG/packet. The direct refresh shortcut is inactive.
      if(nodes.has('plan') && edge.dataset.from==='route' && ['tools','fast'].includes(edge.dataset.to))active=false;
      edge.classList.toggle('is-route',active);
    });
  }

  function setupDiagram() {
    document.querySelectorAll('[data-node]').forEach(button => {
      const module=modules.get(button.dataset.node); if (!module) return;
      button.querySelector('b').textContent=module.title;
      button.querySelector('small').textContent=module.subtitle || module.model || '';
      button.type='button'; button.setAttribute('aria-label',`查看${module.title}的职责与预算`);
      button.addEventListener('click',()=>{renderModule(button.dataset.node);announce(`已切换到${module.title}`);});
    });
    renderModule(selectedModule);
    if (typeof ResizeObserver !== 'undefined') new ResizeObserver(drawEdges).observe($('flow'));
    else window.addEventListener('resize',drawEdges);
    requestAnimationFrame(drawEdges);
  }

  function metricsForScenario(s) {
    return [
      ['对话流首个非空 delta', s.first_delta_ms, s.first_delta_ms == null ? '不调用模型' : '相对本轮输入', false],
      ['第一有用交付', s.first_useful_ms, s.first_useful_ms == null ? '静默正确 · 不适用' : '用户已收到可用内容', true],
      ['前台完成', s.foreground_ms, '本轮可见交付完成', false],
      ['后台完成', s.background_ms, s.background_ms == null ? '本轮跳过' : '不阻塞前台', false]
    ];
  }

  function selectScenario(index) {
    pause(); scenarioIndex = Number(index) || 0; currentMs = 0; renderedCount = -1;
    const s = scenario(); $('scenario-select').value = String(scenarioIndex);
    $('scenario-kind').textContent = s.kind || '预算预演';
    $('scenario-user').textContent = s.user || '游戏事件触发';
    $('scenario-context').textContent = s.context || '仅使用本轮显式传入的信息。';
    $('token-summary').textContent = s.token_summary || '待确定';
    $('token-detail').textContent = s.token_detail || '';
    $('scenario-output').textContent = s.output || '';
    setList('scenario-conditions', s.conditions || []);
    const metrics=$('timing-metrics'); metrics.replaceChildren();
    for (const [label,value,detail,key] of metricsForScenario(s)) {
      const box=text('div','',`timing-metric${key?' key-metric':''}`);
      const displayed=value==null ? (label==='后台完成'?'跳过':label==='第一有用交付'?'静默':'无需') : fmt(value);
      box.append(text('h4',label),text('b',displayed),text('small',detail)); metrics.append(box);
    }
    $('scrubber').max=String(maxMs()); $('scrubber').value='0';
    $('total-time').textContent=`/ ${fmt(maxMs())}`;
    $('jump-useful').disabled=s.first_useful_ms==null;
    $('jump-background').disabled=s.background_ms==null;
    $('jump-foreground').disabled=s.foreground_ms==null;
    buildTimeline(); renderPlayback(true); updateNodeState();
    $('timeline-scroll').scrollLeft=0;
  }

  function timelineLayout(segments) {
    const laneIds=['user','foreground','background'];
    const lanes={}, placements={};
    let top=34;
    for(const lane of laneIds){
      const rows=[];
      const items=(Array.isArray(segments)?segments:[]).map((segment,index)=>({segment,index}))
        .filter(item=>(laneIds.includes(item.segment.lane)?item.segment.lane:'foreground')===lane)
        .sort((a,b)=>Number(a.segment.start)-Number(b.segment.start)||Number(a.segment.end)-Number(b.segment.end)||a.index-b.index);
      for(const {segment,index} of items){
        const start=Number(segment.start)||0, end=Math.max(start+1,Number(segment.end)||start);
        let row=rows.findIndex(previousEnd=>previousEnd<=start);
        if(row<0){row=rows.length;rows.push(end);}else rows[row]=end;
        placements[index]={lane,row,top:top+24+row*33};
      }
      const tracks=Math.max(1,rows.length),height=32+tracks*33;
      lanes[lane]={top,height,tracks,eventTop:top+height-10};
      top+=height+2;
    }
    return {lanes,placements,height:top+10};
  }

  function buildTimeline() {
    const target=$('timeline'); target.replaceChildren();
    const duration=maxMs();
    const segments=array(scenario().segments), layout=timelineLayout(segments);
    timelineWidth=Math.max(720,Math.min(6500,duration/12));
    target.style.width=`${timelineWidth}px`;
    target.style.height=`${layout.height}px`;
    ['user','foreground','background'].forEach((lane,index)=>{
      const box=text('div','',`timeline-lane ${['user-lane','front-lane','back-lane'][index]}`);
      box.style.top=`${layout.lanes[lane].top}px`;box.style.height=`${layout.lanes[lane].height}px`;
      box.append(text('span',laneName(lane),'lane-name'));target.append(box);
    });
    let step = duration <= 500 ? 100 : duration <= 2000 ? 250 : duration <= 6000 ? 1000 : duration <= 20000 ? 2000 : duration <= 60000 ? 5000 : 10000;
    for(let t=0;t<=duration;t+=step){const tick=text('div','', 'timeline-tick');tick.style.left=`${t/duration*100}%`;tick.style.height=`${layout.height-12}px`;tick.append(text('span',fmt(t)));target.append(tick);}
    segments.forEach((segment,index)=>{
      const start=Math.max(0,Math.min(duration,Number(segment.start)||0));
      const end=Math.max(start,Math.min(duration,Number(segment.end)||start));
      const bar=text('button',segment.label||modules.get(segment.node)?.title||segment.node,`segment ${segment.lane||'foreground'}`);
      bar.type='button'; bar.style.left=`${start/duration*100}%`;bar.style.width=`${(end-start)/duration*100}%`;
      bar.style.top=`${layout.placements[index].top}px`;bar.dataset.subtrack=String(layout.placements[index].row);
      bar.dataset.start=String(start);bar.dataset.end=String(end);bar.dataset.segment=String(index);bar.dataset.module=segment.node;
      bar.title=`${segment.label||segment.node} · ${fmt(start)} → ${fmt(end)}`;
      bar.setAttribute('aria-label',`查看${segment.label||segment.node}，${fmt(start)}至${fmt(end)}`);
      bar.addEventListener('click',()=>{pause();currentMs=start;renderModule(segment.node);renderPlayback(true);});target.append(bar);
    });
    for(const event of array(scenario().events)){
      const lane=layout.lanes[event.lane]?event.lane:'foreground';
      const dot=text('span','',`event-mark ${lane}`);dot.style.left=`${Math.max(0,Math.min(duration,event.at))/duration*100}%`;dot.style.top=`${layout.lanes[lane].eventTop}px`;dot.title=`${fmt(event.at)} ${event.type}`;target.append(dot);
    }
    const head=text('div','', 'playhead');head.id='playhead';target.append(head);
  }

  function eventRow(event) {
    const row=text('div','',`event-row ${event.lane||'foreground'}`);
    row.append(text('time',fmt(event.at)),text('span',laneName(event.lane),'event-lane'));
    const content=text('div','', 'event-content');content.append(text('b',event.type||'event'),text('p',event.text||''));
    const details=document.createElement('details');details.append(text('summary','展开事件数据'));
    details.append(text('pre',JSON.stringify({at_ms:event.at,lane:event.lane,node:event.node,type:event.type,payload:event.payload||{}},null,2)));content.append(details);row.append(content);return row;
  }

  function renderConversation(events) {
    const target=$('chat-messages'),position=target.scrollTop,wasNearBottom=target.scrollHeight-target.scrollTop-target.clientHeight<30;target.replaceChildren();
    function bubble(role,value){const item=text('div','',`chat-item ${role}`);item.append(text('span',role==='user'?'玩家':'大肥鱼','speaker'),text('p',value,'bubble'));target.append(item);}
    if(scenario().user) bubble('user',scenario().user);
    const messages=[];const byId=new Map();
    for(const event of events){
      if(typeof event.delivery_text !== 'string' || event.delivery_text.length===0)continue;
      const id=event.delivery_id||`event-${event.at}-${messages.length}`;
      const existing=byId.get(id);
      if(existing) existing.value+=event.delivery_text;
      else {const entry={id,value:event.delivery_text,role:event.payload?.delivery_role==='user'?'user':'assistant'};byId.set(id,entry);messages.push(entry);}
    }
    messages.forEach(m=>bubble(m.role,m.value));
    if(wasNearBottom||playing)target.scrollTop=target.scrollHeight;else target.scrollTop=position;
    const s=scenario();
    if(currentMs>=maxMs())$('chat-status').textContent=s.first_useful_ms==null?'本轮静默结束。没有给玩家额外打扰。':'本轮预演结束。';
    else if(s.foreground_ms!=null&&currentMs>=s.foreground_ms)$('chat-status').textContent=s.background_ms!=null&&currentMs<s.background_ms?(events.some(e=>e.lane==='background'&&/enqueued|request_sent|started/.test(e.type))?'可见交付已完成，后台仍在继续。':'可见交付已完成；后台任务尚未开始。'):'可见交付已完成。';
    else if(messages.length)$('chat-status').textContent='已通过审核的内容正在交付。';
    else $('chat-status').textContent=s.first_useful_ms==null?'当前情境选择静默。':'尚未发布内容。';
  }

  function renderPlayback(force=false) {
    const duration=maxMs();currentMs=Math.max(0,Math.min(duration,currentMs));
    $('current-time').textContent=fmt(currentMs);$('scrubber').value=String(Math.round(currentMs));
    $('scrubber').setAttribute('aria-valuetext',`${fmt(currentMs)}，总时长${fmt(duration)}`);
    const head=$('playhead');if(head)head.style.left=`${currentMs/duration*100}%`;
    document.querySelectorAll('.segment').forEach(bar=>{
      const start=Number(bar.dataset.start),end=Number(bar.dataset.end);
      bar.classList.toggle('future',currentMs<start);bar.classList.toggle('active',currentMs>=start&&currentMs<end);bar.classList.toggle('complete',currentMs>=end);bar.classList.toggle('selected-segment',bar.dataset.module===selectedModule);
    });
    const events=array(scenario().events).filter(e=>Number(e.at)<=currentMs);
    if(force||events.length!==renderedCount){
      renderedCount=events.length;
      const log=$('event-log');const position=log.scrollTop;const atBottom=log.scrollHeight-log.scrollTop-log.clientHeight<30;
      log.replaceChildren(...events.map(eventRow));
      if(!events.length)log.append(text('p','点击播放或下一事件，查看这条路径的具体设计事件。','log-empty'));
      if(playing||atBottom)log.scrollTop=log.scrollHeight;else log.scrollTop=position;
      $('event-count').textContent=`${events.length} / ${array(scenario().events).length}`;
      renderConversation(events);updateNodeState();
    }
    $('next-event').disabled=currentMs>=duration;
    if(playing){const viewport=$('timeline-scroll');const x=currentMs/duration*timelineWidth;if(x>viewport.scrollLeft+viewport.clientWidth-55)viewport.scrollLeft=Math.max(0,x-viewport.clientWidth*.6);}
  }

  function pause() {
    playing=false;previousFrame=null;if(animation!=null)cancelAnimationFrame(animation);animation=null;
    if($('play-pause'))$('play-pause').textContent='播放预演';
  }
  function tick(now) {
    if(!playing)return;
    if(previousFrame!=null)currentMs+=(now-previousFrame)*Number($('play-speed').value||1);
    previousFrame=now;renderPlayback();
    if(currentMs>=maxMs()){pause();renderPlayback(true);announce('本轮预演结束。');return;}
    animation=requestAnimationFrame(tick);
  }
  function play(){if(currentMs>=maxMs()){currentMs=0;renderedCount=-1;renderPlayback(true);$('timeline-scroll').scrollLeft=0;}playing=true;previousFrame=null;$('play-pause').textContent='暂停';animation=requestAnimationFrame(tick);}
  function jump(value){if(value==null)return;pause();currentMs=value;renderPlayback(true);const view=$('timeline-scroll');view.scrollLeft=Math.max(0,currentMs/maxMs()*timelineWidth-view.clientWidth*.45);}

  function setupPlayback() {
    const select=$('scenario-select');select.replaceChildren();
    (data.scenarios||[]).forEach((s,index)=>{const option=text('option',s.title);option.value=String(index);select.append(option);});
    select.addEventListener('change',()=>{selectScenario(select.value);announce(`已选择${scenario().title}，预演已重置。`);});
    $('play-pause').addEventListener('click',()=>playing?pause():play());
    $('restart').addEventListener('click',()=>selectScenario(scenarioIndex));
    $('next-event').addEventListener('click',()=>{const next=array(scenario().events).find(e=>e.at>currentMs);jump(next?next.at:maxMs());});
    $('scrubber').addEventListener('input',()=>{pause();currentMs=Number($('scrubber').value);renderPlayback(true);});
    $('jump-useful').addEventListener('click',()=>jump(scenario().first_useful_ms));
    $('jump-foreground').addEventListener('click',()=>jump(scenario().foreground_ms));
    $('jump-background').addEventListener('click',()=>jump(scenario().background_ms));
    document.addEventListener('visibilitychange',()=>{if(document.hidden)pause();});
    selectScenario(0);
  }

  function renderAcceptance() {
    const rows=$('acceptance-rows');rows.replaceChildren();
    for(const item of data.acceptance||[]){const tr=document.createElement('tr');['stage','deliverable','gate','adjust'].forEach(key=>tr.append(text('td',item[key])));rows.append(tr);}
    setList('architecture-notes',data.architecture_notes||[]);setList('token-notes',data.token_notes||[]);
  }
  function download(content,type,name){const url=URL.createObjectURL(new Blob([content],{type}));const anchor=document.createElement('a');anchor.href=url;anchor.download=name;document.body.append(anchor);anchor.click();anchor.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  $('download-json').addEventListener('click',()=>download(JSON.stringify(data,null,2),'application/json;charset=utf-8','dafeyu-streaming-plan.json'));
  $('download-html').addEventListener('click',()=>{pause();download('<!doctype html>\n'+document.documentElement.outerHTML,'text/html;charset=utf-8','dafeyu-streaming-plan.html');announce('已下载自包含 HTML。');});

  renderBaseline();renderResearch();renderAcceptance();setupTabs();setupPlayback();setupDiagram();
})();
