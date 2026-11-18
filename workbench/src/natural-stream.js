/* Recorded coordinator events, never a fabricated token stream. */
(() => {
  'use strict';
  let current = null;
  const number = value => typeof value === 'number' && Number.isFinite(value);
  const list = value => Array.isArray(value) ? value : [];
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const elapsed = value => value < 1000 ? `${value.toFixed(3)} ms` : `${(value / 1000).toFixed(3)} s`;
  const clock = value => `${(value / 1000).toFixed(3)} s`;
  const serial = value => JSON.stringify(value ?? null, null, 2);
  const kindNames = {input:'输入',route:'路由',dispatch:'调用',candidate:'内部候选',delivery:'通过交付',state:'游戏状态',preference:'偏好',gate:'发送检查',memory:'记忆',plan:'规划',control:'协调器'};

  function download(text, name, type) {
    const url = URL.createObjectURL(new Blob([text], {type}));
    const a = document.createElement('a');
    a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function destroy() {
    if (!current) return;
    current.dead = true;
    cancelAnimationFrame(current.frame);
    current = null;
  }

  function render(root, round) {
    destroy();
    if (!root) return;
    const timeline = round.timeline;
    if (!timeline || !Array.isArray(timeline.events)) {
      root.innerHTML = '<div class="nsr-empty">本轮尚无可回放的时间线。原始候选仍可在“流程图”中查看；不会用打字动画补造流式数据。</div>';
      return;
    }
    const events = timeline.events.filter(e => number(e.at_ms) && e.at_ms >= 0)
      .map((e, i) => ({...e, originalIndex:i})).sort((a,b) => a.at_ms-b.at_ms || a.originalIndex-b.originalIndex);
    const eventById = new Map(events.map(e => [e.id,e]));
    // Only an accepted delivery event may become an assistant chat bubble.
    const segments = list(timeline.segments).filter(segment => number(segment.at_ms) && segment.at_ms >= 0 &&
      (segment.kind === 'user' || (segment.kind === 'assistant' && eventById.get(segment.event_id)?.type === 'delivery')))
      .map((segment,i) => ({...segment, originalIndex:i})).sort((a,b) => a.at_ms-b.at_ms || a.originalIndex-b.originalIndex);
    const duration = Math.max(0, number(timeline.duration_ms) ? timeline.duration_ms : 0,
      ...events.map(e=>e.at_ms), ...segments.map(segment=>segment.at_ms));
    const state = {dead:false,frame:0,time:0,speed:1,playing:false,lastFrame:0,visibleCount:-1,visibleSegments:-1};
    current = state;
    const prefix = 'nsr-';
    const id = suffix => prefix + suffix;
    const safeRound = String(round.id || 'round').replace(/[^a-zA-Z0-9_-]/g, '_');

    root.innerHTML = `
      <div class="nsr" aria-label="真实事件回放">
        <div class="nsr-heading"><div><p class="nsr-eyebrow">RECORDED EVENT STREAM</p><h3>${escape(round.title || round.id)}</h3></div><span class="nsr-recording">已记录事件 · 非直播</span></div>
        <div class="nsr-boundary"><strong>真实事件回放；逐 token 流未采集。</strong><span>模型候选按实际到达时间整条出现。只有通过发送检查的文字进入左侧交付区；被拦截候选保留在右侧日志。</span></div>
        <div class="nsr-controls" role="group" aria-label="回放控制">
          <button type="button" class="nsr-primary" id="${id('play')}">播放</button>
          <button type="button" id="${id('start')}">回到开始</button>
          <button type="button" id="${id('next')}">下一事件</button>
          <button type="button" id="${id('end')}">到结尾</button>
          <label class="nsr-speed-label" for="${id('speed')}">速度 <select id="${id('speed')}"><option value="1">1× 原始时间</option><option value="5">5×</option><option value="20">20×</option></select></label>
          <button type="button" class="nsr-download" id="${id('download')}">↓ 本轮 JSONL</button>
        </div>
        <div class="nsr-timebar"><div class="nsr-clock"><output id="${id('clock')}">0.000 s</output><span>/ ${clock(duration)}</span><span class="nsr-speed-badge" id="${id('speed-label')}">1× 原始时间</span></div><span class="nsr-count" id="${id('count')}"></span></div>
        <label class="nsr-sr-only" for="${id('seek')}">回放时间轴</label>
        <input class="nsr-seek" id="${id('seek')}" type="range" min="0" max="${Math.max(duration,0.001)}" step="any" value="0" aria-valuetext="0.000 秒">
        <p class="nsr-status" id="${id('status')}" role="status">尚未播放。点击“下一事件”可跳过等待，时间戳保持原始记录。</p>
        <div class="nsr-panes">
          <section class="nsr-conversation" aria-labelledby="${id('chat-title')}"><div class="nsr-pane-heading"><h4 id="${id('chat-title')}">交付内容</h4><span>本地发送检查已接受</span></div><p class="nsr-pane-note">此处重现允许交付的文字；真实游戏客户端何时显示未测。</p><div class="nsr-messages" id="${id('messages')}" aria-live="polite" aria-relevant="additions text"></div><p class="nsr-chat-state" id="${id('chat-state')}"></p></section>
          <section class="nsr-events" aria-labelledby="${id('events-title')}"><div class="nsr-pane-heading"><h4 id="${id('events-title')}">Agent / 协调器日志</h4><span id="${id('event-count')}"></span></div><p class="nsr-pane-note">按记录顺序展开；点事件查看 payload 与完整原始 JSONL。</p><div class="nsr-event-list" id="${id('event-list')}"></div><p class="nsr-log-state" id="${id('log-state')}"></p></section>
        </div>
        <div class="nsr-footnote"><span>相对时间：本轮进入协调器起算 · 绝对时间：上海 UTC+08:00</span><span>首字 / TTFT / token chunks：未采集</span></div>
      </div>`;

    const find = suffix => root.querySelector('#'+id(suffix));
    const messages = find('messages');
    const messageElements = segments.map(segment => {
      const element = document.createElement('article');
      element.className = 'nsr-message ' + (segment.kind === 'user' ? 'nsr-user' : 'nsr-assistant');
      element.hidden = true;
      element.innerHTML = `<div class="nsr-message-meta"><b>${segment.kind === 'user' ? '用户' : '陪伴精灵 · 已通过发送检查'}</b><time>+${elapsed(segment.at_ms)}</time></div><p>${escape(segment.text)}</p>`;
      messages.appendChild(element);
      return element;
    });
    const eventList = find('event-list');
    const eventElements = events.map(event => {
      const entry = document.createElement('details');
      entry.className = `nsr-event nsr-${event.level === 'error' ? 'error' : event.level === 'warning' ? 'warning' : 'info'}${event.type === 'candidate' ? ' nsr-candidate' : ''}${event.type === 'delivery' ? ' nsr-delivery' : ''}`;
      entry.hidden = true;
      const metadata = [event.job_id && `job ${event.job_id}`,event.turn_id && `turn ${event.turn_id}`].filter(Boolean);
      entry.innerHTML = `<summary><div class="nsr-event-top"><time>+${elapsed(event.at_ms)}</time><span class="nsr-event-kind">${escape(kindNames[event.type] || event.type)}</span><span class="nsr-event-actor">${escape(event.actor || '协调器')}</span></div><strong>${escape(event.label || event.raw_type)}</strong><p>${escape(event.summary || '')}</p><div class="nsr-event-bottom"><code>${escape(event.raw_type)}</code><span>展开 JSON</span></div></summary><div class="nsr-event-detail"><div class="nsr-event-fields"><span>上海时间</span><time>${escape(event.wall_time || '未记录')}</time><span>来源行号</span><span>${escape(event.source_line ?? '未记录')}</span><span>事件 ID</span><code>${escape(event.id)}</code>${metadata.length ? `<span>调用标识</span><code>${escape(metadata.join('\n'))}</code>` : ''}</div><h5>Payload</h5><pre class="nsr-json">${escape(serial(event.payload))}</pre><h5>原始 JSONL · 完整行</h5><pre class="nsr-json nsr-raw">${escape(typeof event.raw_line === 'string' ? event.raw_line : '没有原始行，不能重建逐字记录。')}</pre><button type="button" class="nsr-copy">复制原始行</button><span class="nsr-copy-result" role="status"></span></div>`;
      const copy = entry.querySelector('.nsr-copy');
      copy.disabled = typeof event.raw_line !== 'string';
      copy.addEventListener('click', async () => {
        const result = entry.querySelector('.nsr-copy-result');
        try {
          if (!navigator.clipboard?.writeText) throw new Error('clipboard unavailable');
          await navigator.clipboard.writeText(event.raw_line);
          result.textContent = '已复制';
        } catch (_) { result.textContent = '当前页面无法访问剪贴板，请用“本轮 JSONL”下载。'; }
      });
      eventList.appendChild(entry);
      return entry;
    });

    function update(force = false) {
      if (state.dead) return;
      find('clock').textContent = clock(state.time);
      find('seek').value = String(state.time);
      find('seek').setAttribute('aria-valuetext', `${(state.time/1000).toFixed(3)} 秒，共 ${(duration/1000).toFixed(3)} 秒`);
      const visible = events.filter(event => event.at_ms <= state.time + 1e-7).length;
      const shownSegments = segments.filter(segment => segment.at_ms <= state.time + 1e-7).length;
      if (force || visible !== state.visibleCount) {
        eventElements.forEach((element,i) => {
          element.hidden = i >= visible;
          element.classList.toggle('nsr-latest',i === visible-1);
        });
        find('count').textContent = `${visible} / ${events.length} 条事件`;
        find('event-count').textContent = `${visible} 条已到达`;
        const next = events[visible];
        find('log-state').textContent = next ? `下一条：+${elapsed(next.at_ms)} · ${next.label || next.raw_type}` : events.length ? '本轮已记录的事件全部显示。' : '本轮没有事件记录。';
        state.visibleCount = visible;
      }
      if (force || shownSegments !== state.visibleSegments) {
        messageElements.forEach((element,i) => {element.hidden = i >= shownSegments;});
        state.visibleSegments = shownSegments;
      }
      const assistants = segments.filter(segment => segment.kind === 'assistant' && segment.at_ms <= state.time+1e-7).length;
      const visibleEvents = events.slice(0,visible);
      const last = visibleEvents.at(-1);
      if (!assistants) {
        find('chat-state').textContent = state.time >= duration && events.length ? '本轮没有任何模型候选被接受为交付文字。内部候选与拒绝原因在右侧。' : '还没有通过发送检查的回复。等待期间不会插入占位话或模拟文字流。';
      } else {
        find('chat-state').textContent = `截至当前时刻，${assistants} 条回复通过本地发送检查。${state.time < duration ? '后台事件继续记录。' : ''}`;
      }
      find('next').disabled = !events.some(event => event.at_ms > state.time + 1e-7);
      find('end').disabled = state.time >= duration;
      find('start').disabled = state.time === 0 && !state.playing;
      find('play').disabled = duration <= 0;
      find('play').textContent = state.playing ? '暂停' : state.time >= duration && duration > 0 ? '重新播放' : '播放';
      root.dataset.replayTimeMs = String(state.time);
      root.dataset.replayEventCount = String(visible);
      root.dataset.replayPlaying = String(state.playing);
      root.dataset.replayLastEvent = last?.id || '';
    }

    function pause(message) {
      state.playing = false;
      cancelAnimationFrame(state.frame);
      if (message) find('status').textContent = message;
      update();
    }
    function seek(time, message) {
      pause();
      state.time = Math.max(0,Math.min(duration,time));
      if (message) find('status').textContent = message;
      update(true);
    }
    function tick(now) {
      if (state.dead || !state.playing) return;
      state.time = Math.min(duration, state.time+(now-state.lastFrame)*state.speed);
      state.lastFrame = now;
      update();
      if (state.time >= duration) pause('回放结束。所有时间与事件均来自本轮记录。');
      else state.frame = requestAnimationFrame(tick);
    }
    find('play').addEventListener('click', () => {
      if (state.playing) { pause('已暂停。可拖动时间轴或展开日志。'); return; }
      if (state.time >= duration) state.time = 0;
      state.playing = true; state.lastFrame = performance.now();
      find('status').textContent = `正在以 ${state.speed}× 回放真实事件。模型整条候选到达前不会显示逐字输出。`;
      update(true); state.frame = requestAnimationFrame(tick);
    });
    find('start').addEventListener('click',()=>seek(0,'已回到开始，未自动播放。'));
    find('end').addEventListener('click',()=>seek(duration,'已跳到结尾，显示本轮全部日志。'));
    find('next').addEventListener('click',()=>{
      const next=events.find(event=>event.at_ms>state.time+1e-7);
      if(next)seek(next.at_ms,`跳到 +${elapsed(next.at_ms)}：${next.label || next.raw_type}。`);
    });
    find('seek').addEventListener('input',event=>seek(Number(event.target.value),'已暂停并定位到所选时间。'));
    find('speed').addEventListener('change',event=>{
      if(state.playing){
        const now=performance.now();state.time=Math.min(duration,state.time+(now-state.lastFrame)*state.speed);state.lastFrame=now;
      }
      state.speed=Number(event.target.value);
      find('speed-label').textContent=state.speed===1?'1× 原始时间':`${state.speed}× 加速回放`;
      find('status').textContent=state.playing?`正在以 ${state.speed}× 回放真实事件。`:`已设为 ${state.speed}×，点击播放开始。`;
      update();
    });
    find('download').addEventListener('click',()=>{
      const recorded = new Map();
      for (const event of events) {
        if (typeof event.raw_line === 'string' && number(event.source_line) && !recorded.has(event.source_line)) recorded.set(event.source_line,event.raw_line);
      }
      const rows = [...recorded].sort((a,b)=>a[0]-b[0]).map(([,line])=>line);
      if(!rows.length){find('status').textContent='没有带原始行文本的日志，未生成下载文件。';return;}
      download(rows.join('\n')+'\n',`${safeRound}-original-events.jsonl`,'application/x-ndjson;charset=utf-8');
      find('status').textContent=`已下载 ${rows.length} 行原始 JSONL，保留原始纳秒时间戳精度。`;
    });
    update(true);
  }

  window.NaturalStreamReplay = Object.freeze({render,destroy});
})();
