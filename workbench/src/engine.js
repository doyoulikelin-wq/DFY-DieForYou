(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.CompanionEngine = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const clone = value => JSON.parse(JSON.stringify(value));
  const DEFAULTS = {
    maxParallel: 3, heavySlots: 1, activeCooldownMinutes: 30,
    maxProbesPerSession: 2, retryLimit: 1, replyDeadlineMs: 8000,
    modelTimeScale: 1
  };
  const ROLES = {
    system: { id: 'system', name: '程序调度', label: '程序调度', color: '#6d7b8f', thought: 'rule', purpose: '统一状态、额度、取消与唯一发布出口', input: '事件、状态版本、运行额度', output: '可执行状态与不可跳过的门控', permissions: '立即停止、取消过期任务、管理并发；不生成新人格' },
    planning: { id: 'planning', name: '规划 Agent', label: '规划', color: '#8b5cf6', thought: 'heavy', purpose: '定义互动目标并组织需要的任务链路', input: '当前目标、情境快照、相关记忆', output: '带依赖、预算、停止条件和有效期的计划', permissions: '可选择可选任务、增加依赖；不可删除硬性门控' },
    review: { id: 'review', name: '审核 Agent', label: '审核', color: '#ef9e35', thought: 'light', purpose: '检查具体内容及更新依据', input: '实际草稿、明确偏好、规则与证据', output: '通过、修改或取消及其依据', permissions: '可否决和要求修改；不能自行放宽边界' },
    decision: { id: 'decision', name: '决策 Agent', label: '决策', color: '#3184f5', thought: 'light', purpose: '选择此刻最合适的行动及思考路由', input: '计划、事实、人格、剩余时间', output: '单个行动意图、思考档位与截止时间', permissions: '选择、推迟或放弃行动；沉默也是有效选择' },
    execution: { id: 'execution', name: '执行 Agent', label: '执行', color: '#12a991', thought: 'light', purpose: '只读获取资料并按意图准备表达', input: '已明确的读取任务或行动意图', output: '原始证据、具体草稿或送达回执', permissions: '可以读取获准资料；对外发布必须经过审核和状态复核' },
    reflection: { id: 'reflection', name: '反馈反思 Agent', label: '反馈反思', color: '#d866b4', thought: 'heavy', purpose: '后台解释实际反馈并提出待验证改进', input: '已送达行为、用户反馈、替代解释', output: '证据、解释、适用范围与改进建议', permissions: '只提建议；不能自行发言或直接覆盖偏好' },
    memory: { id: 'memory', name: '记忆整理 Agent', label: '记忆整理', color: '#6374db', thought: 'light', purpose: '分别整理事实、明确偏好和推测', input: '事件事实、原话、反思建议与版本', output: '有来源和适用范围的记忆更新', permissions: '版本检查后单写入；推测不得转为已确认事实' }
  };
  const BASE_INPUT = {
    kind: 'simple', complexity: 2, uncertainty: 1, hasPlan: false,
    inCombat: false, quietMode: false, pendingProbe: false,
    minutesSinceActive: 40, probesUsed: 0, failedNoReplyCount: 0, allowProactive: true,
    feedback: 'positive', explicitPreference: false,
    stateVersion: 1, memoryVersion: 1
  };
  const SCENARIOS = [
    { id: 'simple', title: '普通回应', description: '复用已有规则与记忆，跳过重规划和重反思。', input: { ...BASE_INPUT, kind: 'simple', complexity: 2, uncertainty: 1, hasPlan: true } },
    { id: 'complex', title: '复杂战斗复盘', description: '战斗记录、机制资料与方案规划并发，决策等待证据齐备。', input: { ...BASE_INPUT, kind: 'complex', complexity: 5, uncertainty: 4 } },
    { id: 'probe', title: '主动互动试探', description: '先检查打扰额度，围绕一个未知偏好设计低负担试探。', input: { ...BASE_INPUT, kind: 'probe', complexity: 3, uncertainty: 3, feedback: 'explicit', explicitPreference: true } },
    { id: 'quiet', title: '立即保持安静', description: '直接取消待发言任务，无需等待重度思考。', input: { ...BASE_INPUT, kind: 'quiet', quietMode: true, feedback: 'explicit', explicitPreference: true } },
    { id: 'conflict', title: '偏好发生冲突', description: '当前明确要求优先生效，后台根据证据整理冲突。', input: { ...BASE_INPUT, kind: 'conflict', complexity: 4, uncertainty: 5, feedback: 'explicit', explicitPreference: true } }
  ];
  function settingsFor(settings) { return { ...DEFAULTS, ...(settings || {}) }; }
  function inputFor(input) {
    const obj = typeof input === 'string' ? { kind: input } : (input || {});
    return { ...BASE_INPUT, ...obj, kind: obj.kind || obj.scenario || obj.taskType || 'simple' };
  }
  function probeBlockers(input, settings) {
    const i = inputFor(input), s = settingsFor(settings), reasons = [];
    if (!i.allowProactive) reasons.push('主动互动已关闭');
    if (i.quietMode) reasons.push('用户要求安静，时间流逝不会自动恢复');
    if (i.inCombat) reasons.push('当前处于战斗，高负担窗口不试探');
    if (i.pendingProbe) reasons.push('已有一个试探等待回应');
    if (Number(i.failedNoReplyCount) >= 2) reasons.push('连续两次未回应，本会话暂停试探；这不代表长期偏好');
    if (Number(i.minutesSinceActive) < Number(s.activeCooldownMinutes)) reasons.push('主动互动冷却尚未结束');
    if (Number(i.probesUsed) >= Number(s.maxProbesPerSession)) reasons.push('本会话试探额度已用完');
    return reasons;
  }
  function makeNode(id, label, role, phase, thought, duration, required, reason, extra) {
    return { id, label, role, phase, thought, duration, required, enabled: true, reason, ...(extra || {}) };
  }
  function makeEdge(from, to, reason, hard = true) { return { from, to, hard, reason }; }
  function plan(input, settings) {
    const i = inputFor(input), s = settingsFor(settings), nodes = [], edges = [], skipped = [], rationale = [];
    const add = (...args) => { const n = makeNode(...args); nodes.push(n); return n; };
    const link = (a, b, reason, hard) => edges.push(makeEdge(a, b, reason, hard));
    const omit = (id, label, reason) => skipped.push({ id, label, reason });
    const quiet = i.kind === 'quiet';
    const blockedReasons = i.kind === 'probe' ? probeBlockers(i, s) : [];
    if (quiet) {
      add('cancel', '立即取消待发言', 'system', 'front', 'rule', 20, true, '明确安静指令优先，立即中止待发言队列');
      add('receipt', '记录取消回执', 'system', 'front', 'rule', 30, true, '记录取消结果，无语音或消息发布');
      add('facts', '保存明确要求', 'memory', 'back', 'light', 120, true, '用户原话与当前生效范围分别保存');
      add('updateReview', '检查更新范围', 'review', 'back', 'light', 100, true, '只改变用户指令明确指向的范围');
      add('memoryCommit', '版本校验后提交', 'memory', 'back', 'rule', 60, true, '只在版本一致时写入', { resource: 'memory-write' });
      link('cancel', 'receipt', '先取消，再记录实际结果');
      link('receipt', 'facts', '保存已生效的要求');
      link('facts', 'updateReview', '审核基于原话整理的更新');
      link('updateReview', 'memoryCommit', '审核通过后才可持久提交');
      omit('planner', '重度方案规划', '明确停止无需规划');
      omit('decision', '模型决策', '直接执行停止要求');
      omit('draft', '准备表达', '不新增对外发言');
      omit('reflection', '重度反馈反思', '先立即生效；仅在以后出现冲突时再分析');
      rationale.push('安静要求走直接路线；当前状态立即改变，长期整理在后台完成。');
    } else {
      add('snapshot', '读取情境与记忆', 'memory', 'front', 'light', 120, true, '读取同一份人格、偏好和状态快照');
      add('precheck', '规则与额度预检', 'system', 'front', 'rule', 50, true, '在耗费思考前检查明确边界');
      if (blockedReasons.length) {
        add('cancel', '取消本次试探', 'system', 'front', 'rule', 20, true, blockedReasons.join('；'));
        add('receipt', '记录未执行原因', 'system', 'front', 'rule', 30, true, '未执行不消耗试探额度，不产生用户评价');
        link('snapshot', 'cancel', '保留判定时的场景依据');
        link('precheck', 'cancel', '不满足试探条件即停止');
        link('cancel', 'receipt', '记录具体取消原因');
        ['planner', 'decision', 'draft', 'review', 'reflection', 'memoryCommit'].forEach(id => omit(id, ({ planner: '重度方案规划', decision: '模型决策', draft: '准备表达', review: '内容审核', reflection: '重度反馈反思', memoryCommit: '长期偏好提交' })[id], '试探预检未通过，不启动后续链路'));
        rationale.push('当前试探被阻止：' + blockedReasons.join('；') + '。');
      } else {
        const needPlan = !i.hasPlan && (i.kind !== 'simple' || Number(i.complexity) >= 4 || Number(i.uncertainty) >= 4);
        const heavyDecision = i.kind === 'complex' || i.kind === 'conflict' || Number(i.complexity) >= 4 || Number(i.uncertainty) >= 4;
        if (needPlan) {
          add('planner', '重度方案规划', 'planning', 'front', 'heavy', 1700, false, '缺少可复用计划，需要明确目标、候选路径和停止条件');
          link('snapshot', 'planner', '规划需要同一版本的情境与记忆');
          link('precheck', 'planner', '明确边界通过后才投入重度思考');
        } else omit('planner', '重度方案规划', i.hasPlan ? '已有有效计划，直接复用' : '当前问题简单，不需要重度方案规划');
        if (i.kind === 'complex') {
          add('battleRead', '读取战斗记录', 'execution', 'front', 'light', 900, true, '复盘需要实际战斗证据；只读任务可并发');
          add('mechanicsRead', '读取机制资料', 'execution', 'front', 'light', 1400, true, '读取可核对的机制依据；与记录读取相互独立');
          ['battleRead', 'mechanicsRead'].forEach(id => { link('snapshot', id, '读取同一事件对应的资料'); link('precheck', id, '资料访问必须符合允许范围'); });
        } else {
          omit('battleRead', '读取战斗记录', '本次任务不需要战斗证据');
          omit('mechanicsRead', '读取机制资料', '本次任务不需要机制检索');
        }
        add('decision', '选择下一步行动', 'decision', 'front', heavyDecision ? 'heavy' : 'light', heavyDecision ? 1100 : 420, true, heavyDecision ? '复杂度或不确定性较高，聚合证据后作出决定' : '熟悉场景使用轻路线；人格影响行为选择');
        link('snapshot', 'decision', '决策需要当前情境与偏好');
        link('precheck', 'decision', '不可在规则预检前选择对外行动');
        if (needPlan) link('planner', 'decision', '决策等待计划完成');
        if (i.kind === 'complex') {
          link('battleRead', 'decision', '等待战斗记录完成，不使用尚未返回的证据');
          link('mechanicsRead', 'decision', '等待机制资料完成，再综合判断');
        }
        add('draft', '准备表达与动作', 'execution', 'front', 'light', 220, true, '落实已确定的行动意图，不扩大目的');
        add('review', '审核具体内容', 'review', 'front', 'light', 180, true, '审核实际草稿与边界，不只审核行动名称');
        add('recheck', '发布前状态复核', 'system', 'front', 'rule', 40, true, '确认没有新安静指令、场景变化或任务过期');
        add('publish', '唯一出口发布', 'execution', 'front', 'rule', 90, true, '只有已通过审核且仍有效的内容可发布', { resource: 'voice-output' });
        add('receipt', '记录送达回执', 'system', 'front', 'rule', 30, true, '区分实际送达、被打断与未送达');
        add('feedback', '观察实际反馈', 'system', 'back', 'rule', 600, true, '演示反馈窗口；未回复保持未知，不视为负反馈');
        add('facts', '整理事实与原话', 'memory', 'back', 'light', 360, true, '事实整理可与反思并发，不把推测写成事实');
        const needReflection = i.kind !== 'simple' || i.feedback === 'negative' || i.explicitPreference;
        if (needReflection) {
          add('reflection', '后台反馈反思', 'reflection', 'back', 'heavy', 1900, false, '分析反馈范围、替代解释与可验证的调整');
          link('feedback', 'reflection', '只分析实际行为之后的反馈');
        } else omit('reflection', '后台反馈反思', '普通回应未触发复杂反馈，保留记录即可');
        add('merge', '汇总更新建议', 'memory', 'back', 'light', 120, true, '等待事实及所需反思完成，明确证据与假设');
        add('updateReview', '审核记忆与策略更新', 'review', 'back', 'light', 150, true, '检查依据、适用范围和是否覆盖新指令');
        add('memoryCommit', '版本校验后提交', 'memory', 'back', 'rule', 70, true, '单写入并校验版本；冲突建议重新整理', { resource: 'memory-write' });
        [['decision', 'draft', '先决定意图，再生成表达'], ['draft', 'review', '必须审核实际准备发出的内容'], ['review', 'recheck', '审核通过后再核对当前状态'], ['recheck', 'publish', '状态仍有效才允许发布'], ['publish', 'receipt', '记录实际发布结果'], ['receipt', 'feedback', '只有实际送达才能解释用户反馈'], ['feedback', 'facts', '整理真实事件及反馈'], ['facts', 'merge', '汇总须等待事实整理'], ['merge', 'updateReview', '审核完整更新建议'], ['updateReview', 'memoryCommit', '通过审核并校验版本后才提交']].forEach(x => link(...x));
        if (needReflection) link('reflection', 'merge', '需要反思时，汇总等待反思完成');
        rationale.push(needPlan ? '本次启用重度方案规划；其余任务按明确依赖执行。' : '复用有效规则或计划，跳过重度方案规划。');
        if (i.kind === 'complex') rationale.push('方案规划、战斗记录和机制资料相互独立，可在资源允许时并发；综合决策等待三者齐备。');
        rationale.push(heavyDecision ? '决策使用重思考：由复杂度与不确定性触发。' : '决策使用轻思考：当前信息足以选择行动。');
        if (needReflection) rationale.push('事实整理与反馈反思可以并发；记忆提交等待汇总审核，保持单写入。');
        if (i.kind === 'probe') rationale.push('本次只验证一个偏好问题；额度仅在实际送达时消耗。');
        if (i.kind === 'conflict') rationale.push('当前明确要求优先生效；后台冲突整理不能覆盖更新的指令。');
      }
    }
    const graph = {
      version: 1, simulation: true, nodes, edges, skipped, rationale, input: i, settings: s,
      entryIds: quiet ? ['cancel'] : ['snapshot', 'precheck'],
      blockedReasons,
      requiredNodeIds: nodes.filter(n => n.required).map(n => n.id),
      requiredEdges: edges.filter(e => e.hard).map(clone),
      disabledIds: []
    };
    graph._baseNodes = clone(nodes); graph._baseEdges = clone(edges); graph._baseSkipped = clone(skipped);
    if (Array.isArray(i.skipNodes)) i.skipNodes.forEach(id => { if (graph.nodes.some(n => n.id === id && !n.required)) Object.assign(graph, toggleNode(graph, id, false)); });
    return graph;
  }
  function activeNodes(graph) { return (graph.nodes || []).filter(n => n.enabled !== false); }
  function adjacency(graph) {
    const nodes = activeNodes(graph), ids = new Set(nodes.map(n => n.id)), next = {}, prev = {};
    nodes.forEach(n => { next[n.id] = []; prev[n.id] = []; });
    (graph.edges || []).forEach(e => { if (ids.has(e.from) && ids.has(e.to) && !next[e.from].includes(e.to)) { next[e.from].push(e.to); prev[e.to].push(e.from); } });
    return { nodes, ids, next, prev };
  }
  function reaches(start, end, next) {
    const stack = [start], seen = new Set();
    while (stack.length) { const id = stack.pop(); if (id === end) return true; if (seen.has(id)) continue; seen.add(id); (next[id] || []).forEach(x => stack.push(x)); }
    return false;
  }
  function validate(graph) {
    if (!graph || !Array.isArray(graph.nodes) || !Array.isArray(graph.edges)) return [{ severity: 'error', code: 'GRAPH_SHAPE', message: '链路必须包含任务节点和依赖列表。', nodeIds: [] }];
    const issues = [], a = adjacency(graph), add = (severity, code, message, nodeIds = []) => issues.push({ severity, code, message, nodeIds });
    const counts = {};
    graph.nodes.forEach(n => {
      counts[n.id] = (counts[n.id] || 0) + 1;
      if (!n.id || !Number.isFinite(Number(n.duration)) || Number(n.duration) < 0) add('error', 'NODE_INVALID', '任务标识或演示时长无效。', [n.id]);
      if (!['rule', 'light', 'heavy'].includes(n.thought)) add('error', 'THOUGHT_INVALID', '思考档位须为规则、轻思考或重思考。', [n.id]);
      if (!['front', 'back'].includes(n.phase)) add('error', 'PHASE_INVALID', '任务须属于前台互动或后台学习。', [n.id]);
    });
    Object.keys(counts).filter(k => counts[k] > 1).forEach(id => add('error', 'DUPLICATE_NODE', '任务标识重复：' + id, [id]));
    (graph.requiredNodeIds || graph.nodes.filter(n => n.required).map(n => n.id)).forEach(id => { if (!a.ids.has(id)) add('error', 'MISSING_REQUIRED_NODE', '不能删除必需任务：' + id, [id]); });
    const edgeKeys = new Set();
    graph.edges.forEach(e => {
      if (!a.ids.has(e.from) || !a.ids.has(e.to)) add('error', 'DANGLING_EDGE', '依赖引用了缺失或停用的任务。', [e.from, e.to]);
      const key = e.from + '>' + e.to;
      if (edgeKeys.has(key)) add('warning', 'DUPLICATE_EDGE', '存在重复依赖，可删除多余连线。', [e.from, e.to]);
      edgeKeys.add(key);
      const from = a.nodes.find(n => n.id === e.from), to = a.nodes.find(n => n.id === e.to);
      if (from && to && from.phase === 'back' && to.phase === 'front') add('error', 'FRONT_WAITS_BACKGROUND', '前台互动不能等待本轮后台学习完成。', [e.from, e.to]);
    });
    (graph.requiredEdges || []).forEach(e => {
      if (a.ids.has(e.from) && a.ids.has(e.to) && !reaches(e.from, e.to, a.next)) add('error', 'MISSING_DEPENDENCY', '缺少必须先后关系：' + e.from + ' → ' + e.to, [e.from, e.to]);
    });
    const degree = Object.fromEntries(a.nodes.map(n => [n.id, a.prev[n.id].length]));
    const queue = a.nodes.filter(n => degree[n.id] === 0).map(n => n.id), visited = [];
    while (queue.length) { const id = queue.shift(); visited.push(id); a.next[id].forEach(to => { if (--degree[to] === 0) queue.push(to); }); }
    if (visited.length !== a.nodes.length) add('error', 'CYCLE', '依赖形成循环，任务将相互等待。', a.nodes.filter(n => !visited.includes(n.id)).map(n => n.id));
    const entries = (graph.entryIds || a.nodes.filter(n => a.prev[n.id].length === 0).map(n => n.id)).filter(id => a.ids.has(id));
    a.nodes.forEach(n => { if (!entries.some(id => reaches(id, n.id, a.next))) add('error', 'UNREACHABLE', '任务无法从本次入口到达：' + n.label, [n.id]); });
    if (a.ids.has('publish')) {
      ['precheck', 'decision', 'draft', 'review', 'recheck', 'receipt', 'feedback'].forEach(id => { if (!a.ids.has(id)) add('error', id === 'review' ? 'MISSING_REVIEW' : 'MISSING_DELIVERY_GATE', '发布链路缺少关键任务：' + id, [id, 'publish']); });
      [['precheck', 'decision'], ['decision', 'draft'], ['draft', 'review'], ['review', 'recheck'], ['recheck', 'publish'], ['publish', 'receipt'], ['receipt', 'feedback']].forEach(([from, to]) => {
        if (a.ids.has(from) && a.ids.has(to) && !reaches(from, to, a.next)) add('error', 'DELIVERY_ORDER', '发布链路先后关系不完整：' + from + ' → ' + to, [from, to]);
      });
      if (graph.input && graph.input.kind === 'quiet') add('error', 'QUIET_HAS_PUBLISH', '立即安静链路不得包含对外发布。', ['publish']);
    }
    if (a.ids.has('memoryCommit')) {
      if (!a.ids.has('updateReview') || !reaches('updateReview', 'memoryCommit', a.next)) add('error', 'UNREVIEWED_MEMORY', '记忆提交必须等待更新审核。', ['updateReview', 'memoryCommit']);
      if (a.ids.has('reflection') && !reaches('reflection', 'memoryCommit', a.next)) add('error', 'UNJOINED_REFLECTION', '启用反思后，提交必须等待其结果汇总。', ['reflection', 'memoryCommit']);
      if (a.ids.has('facts') && !reaches('facts', 'memoryCommit', a.next)) add('error', 'UNJOINED_FACTS', '记忆提交必须有已整理的事实依据。', ['facts', 'memoryCommit']);
    }
    if (graph.input && graph.input.kind === 'complex' && !a.ids.has('planner') && !graph.input.hasPlan) add('warning', 'HEAVY_PLAN_SKIPPED', '复杂任务已跳过重规划；请确认当前决策拥有足够计划。', ['decision']);
    const s = settingsFor(graph.settings);
    if (!Number.isInteger(Number(s.maxParallel)) || Number(s.maxParallel) < 1 || Number(s.maxParallel) > 12) add('error', 'PARALLEL_LIMIT', '总并发上限应为 1–12 的整数。');
    if (!Number.isInteger(Number(s.heavySlots)) || Number(s.heavySlots) < 1 || Number(s.heavySlots) > Number(s.maxParallel)) add('error', 'HEAVY_LIMIT', '重思考并发应至少为 1，且不超过总并发。');
    if (!Number.isFinite(Number(s.activeCooldownMinutes)) || Number(s.activeCooldownMinutes) < 0) add('error', 'COOLDOWN_INVALID', '主动冷却应为非负分钟数。');
    if (!Number.isInteger(Number(s.maxProbesPerSession)) || Number(s.maxProbesPerSession) < 0) add('error', 'PROBE_LIMIT_INVALID', '会话试探上限应为非负整数。');
    if (!Number.isInteger(Number(s.retryLimit)) || Number(s.retryLimit) < 0 || Number(s.retryLimit) > 5) add('error', 'RETRY_LIMIT_INVALID', '审核修改上限应为 0–5 的整数。');
    if (!Number.isFinite(Number(s.replyDeadlineMs)) || Number(s.replyDeadlineMs) <= 0) add('error', 'DEADLINE_INVALID', '回应截止时间应为正的有限毫秒数。');
    if (!Number.isFinite(Number(s.modelTimeScale)) || Number(s.modelTimeScale) < 0.01 || Number(s.modelTimeScale) > 20) add('error', 'TIME_SCALE_INVALID', '演示时长倍率应介于 0.01 与 20 之间。');
    if (graph.input) {
      ['complexity', 'uncertainty'].forEach(key => {
        if (!Number.isFinite(Number(graph.input[key])) || Number(graph.input[key]) < 1 || Number(graph.input[key]) > 5) add('error', 'INPUT_LEVEL_INVALID', '复杂度和不确定性应介于 1 与 5 之间。');
      });
      ['minutesSinceActive', 'probesUsed', 'failedNoReplyCount'].forEach(key => {
        if (graph.input[key] !== undefined && (!Number.isFinite(Number(graph.input[key])) || Number(graph.input[key]) < 0)) add('error', 'INPUT_BUDGET_INVALID', '互动间隔与计数应为非负有限数。');
      });
    }
    return issues.filter((x, index, arr) => arr.findIndex(y => y.code === x.code && y.nodeIds.join() === x.nodeIds.join()) === index);
  }
  function schedule(graph, settings) {
    const s = settingsFor({ ...(graph.settings || {}), ...(settings || {}) }), a = adjacency(graph);
    const cap = Math.max(1, Math.min(12, Math.floor(Number(s.maxParallel) || 1)));
    const heavyCap = Math.max(1, Math.min(cap, Math.floor(Number(s.heavySlots) || 1)));
    const scale = Math.max(0.01, Math.min(20, Number(s.modelTimeScale) || 1));
    const tasks = [], running = [], done = new Map(), started = new Set(), laneFree = Array(cap).fill(true);
    const durationFor = n => Math.max(1, Math.round((Number.isFinite(Number(n.duration)) ? Math.max(0, Number(n.duration)) : 0) * (n.thought === 'rule' ? 1 : scale)));
    let time = 0, maxConcurrency = 0, iterations = 0;
    while (done.size < a.nodes.length && iterations++ < a.nodes.length * 5 + 20) {
      for (let p = running.length - 1; p >= 0; p--) {
        if (running[p].end <= time) { const task = running.splice(p, 1)[0]; done.set(task.id, task.end); laneFree[task.lane] = true; }
      }
      const ready = a.nodes.filter(n => !started.has(n.id) && a.prev[n.id].every(id => done.has(id))).sort((x, y) => {
        if (x.phase !== y.phase) return x.phase === 'front' ? -1 : 1;
        return a.nodes.indexOf(x) - a.nodes.indexOf(y);
      });
      for (const node of ready) {
        if (running.length >= cap) break;
        if (node.thought === 'heavy' && running.filter(t => t.thought === 'heavy').length >= heavyCap) continue;
        if (node.resource && running.some(t => t.resource === node.resource)) continue;
        const lane = laneFree.findIndex(Boolean), task = { id: node.id, label: node.label, start: time, end: time + durationFor(node), lane, phase: node.phase, thought: node.thought, resource: node.resource || null };
        tasks.push(task); running.push(task); started.add(node.id); laneFree[lane] = false;
        maxConcurrency = Math.max(maxConcurrency, running.length);
      }
      if (running.length) time = Math.min(...running.map(t => t.end));
      else if (done.size < a.nodes.length) break;
    }
    const blocked = a.nodes.filter(n => !started.has(n.id)).map(n => n.id);
    const ordered = tasks.slice().sort((x, y) => x.end - y.end), best = {}, predecessor = {};
    ordered.forEach(t => {
      let parent = null, max = 0;
      (a.prev[t.id] || []).forEach(p => { if ((best[p] || 0) > max) { max = best[p]; parent = p; } });
      best[t.id] = max + t.end - t.start; predecessor[t.id] = parent;
    });
    let tail = Object.keys(best).reduce((id, x) => !id || best[x] > best[id] ? x : id, null), criticalPath = [];
    while (tail) { criticalPath.unshift(tail); tail = predecessor[tail]; }
    return {
      tasks, duration: tasks.length ? Math.max(...tasks.map(t => t.end)) : 0,
      frontDuration: tasks.filter(t => t.phase === 'front').reduce((max, t) => Math.max(max, t.end), 0),
      criticalPath, criticalDuration: criticalPath.reduce((sum, id) => { const t = tasks.find(x => x.id === id); return sum + (t ? t.end - t.start : 0); }, 0),
      maxConcurrency, blocked, simulated: true,
      note: '时长为预设演示值；调度遵循真实依赖和资源上限，非实测模型性能。'
    };
  }
  function toggleNode(graph, id, enabled) {
    const g = clone(graph), allNodes = g._baseNodes || clone(g.nodes), allEdges = g._baseEdges || clone(g.edges);
    g.nodes.forEach(current => { const index = allNodes.findIndex(n => n.id === current.id); if (index >= 0) allNodes[index] = clone(current); else allNodes.push(clone(current)); });
    const node = allNodes.find(n => n.id === id);
    if (!node) throw new Error('此链路没有该任务：' + id);
    if (node.required && !enabled) throw new Error('该任务为当前链路的必需步骤，不能关闭。');
    const disabled = new Set(g.disabledIds || []);
    if (enabled) disabled.delete(id); else disabled.add(id);
    const currentSoft = g.edges.filter(e => !e.hard && !e.viaSkipped);
    const baseSoft = allEdges.filter(e => !e.hard && ((g.disabledIds || []).includes(e.from) || (g.disabledIds || []).includes(e.to)));
    const retained = allEdges.filter(e => e.hard).concat(currentSoft, baseSoft);
    let edges = retained.map(clone);
    for (const skip of disabled) {
      const incoming = edges.filter(e => e.to === skip), outgoing = edges.filter(e => e.from === skip);
      edges = edges.filter(e => e.from !== skip && e.to !== skip);
      incoming.forEach(before => outgoing.forEach(after => {
        if (before.from !== after.to) edges.push({ from: before.from, to: after.to, hard: before.hard || after.hard, viaSkipped: true, reason: '跳过可选任务后保留必要先后关系' });
      }));
    }
    const unique = new Map();
    edges.forEach(e => { const key = e.from + '>' + e.to; if (!unique.has(key) || e.hard) unique.set(key, e); });
    g.nodes = allNodes.filter(n => !disabled.has(n.id)); g.edges = [...unique.values()]; g.disabledIds = [...disabled];
    g.requiredEdges = g.edges.filter(e => e.hard).map(clone);
    g.skipped = clone(g._baseSkipped || []).concat(allNodes.filter(n => disabled.has(n.id)).map(n => ({ id: n.id, label: n.label, reason: '在当前方案中手动跳过；系统已连接其必要前后依赖' })));
    g._baseNodes = allNodes; g._baseEdges = allEdges.filter(e => e.hard).concat(currentSoft, baseSoft);
    return g;
  }
  function simulate(graph, settings, faults) {
    const s = settingsFor({ ...(graph.settings || {}), ...(settings || {}) }), i = inputFor(graph.input), f = faults || {};
    const effective = { ...graph, settings: s }, issues = validate(effective), timeline = schedule(effective, s), events = [];
    const errors = issues.filter(x => x.severity === 'error');
    const emptyMetrics = { simulated: true, frontDurationMs: 0, totalDurationMs: 0, maxConcurrency: 0, heavyCalls: 0, plannedFrontDurationMs: timeline.frontDuration, plannedTotalDurationMs: timeline.duration, plannedHeavyCalls: graph.nodes.filter(n => n.thought === 'heavy').length, retries: 0, probesConsumed: 0, rewardEligible: false, preferenceUpdates: 0, policyVersionApplied: false, immediateInstructionApplied: false };
    if (errors.length || timeline.blocked.length) return { events: [], outcome: '链路不合法，禁止运行', delivered: false, probesIncrement: 0, feedbackSampleValid: false, feedbackClass: 'not_observed', memoryOutcome: '未提交', violations: errors, metrics: emptyMetrics, schedule: timeline, nodeStates: {}, cancelled: true };
    const taskById = Object.fromEntries(timeline.tasks.map(t => [t.id, t]));
    const nodeStates = Object.fromEntries(graph.nodes.map(n => [n.id, 'done']));
    let delivered = !!taskById.publish, feedbackClass = 'unknown', memoryOutcome = taskById.memoryCommit ? '仅归档事实，未新增偏好' : '未提交', outcome = '模拟完成', stopId = null, reason = '', retries = 0;
    let reviewRetry = null;
    const feedback = f.feedback || i.feedback || 'none';
    const runtimeBlockers = i.kind === 'probe' ? probeBlockers(i, s) : [];
    if (i.kind === 'quiet') { delivered = false; outcome = '已立即保持安静'; memoryOutcome = f.staleMemory || f.writeConflict ? '提交冲突，保留当前安静状态' : '明确要求已即时生效并归档'; }
    else if ((graph.blockedReasons || []).length || runtimeBlockers.length) {
      delivered = false; outcome = '主动试探被取消'; reason = (runtimeBlockers.length ? runtimeBlockers : graph.blockedReasons).join('；'); stopId = taskById.precheck ? 'precheck' : 'cancel';
    } else if (f.reviewFail) {
      retries = Math.max(0, Math.min(5, Number(s.retryLimit) || 0));
      if (f.reviewRecovers && retries > 0) { retries = 1; outcome = '修改后通过审核并发布'; }
      else { stopId = 'review'; delivered = false; outcome = '审核未通过，停止发布'; reason = '达到修改上限仍未通过，不再循环重试'; }
      if (retries && taskById.review && taskById.draft) {
        const draftMs = taskById.draft.end - taskById.draft.start, reviewMs = taskById.review.end - taskById.review.start;
        const cost = retries * (draftMs + reviewMs), baseEnd = taskById.review.end, next = adjacency(graph).next;
        reviewRetry = { baseEnd, draftMs, reviewMs, cost };
        timeline.tasks.forEach(t => {
          if (t.id !== 'review' && reaches('review', t.id, next)) { t.start += cost; t.end += cost; }
        });
        taskById.review.end += cost;
        timeline.frontDuration += cost; timeline.duration += cost; timeline.criticalDuration += cost;
        timeline.retryDurationMs = cost;
      }
    }
    if (!stopId && delivered && (f.newQuiet || f.stateChanged)) {
      stopId = 'recheck'; delivered = false; outcome = f.newQuiet ? '新安静要求已生效，取消发布' : '场景已变化，取消过期行动'; reason = '发布前复核取消了已过期的行动意图';
    }
    if (!stopId && delivered && timeline.frontDuration > Number(s.replyDeadlineMs)) {
      stopId = 'recheck'; delivered = false; outcome = '已超过回应截止时间，取消过期发布'; reason = '演示前台耗时超过配置的截止时间';
    }
    if (!stopId && delivered && f.undelivered) { delivered = false; stopId = 'receipt'; outcome = '未送达，反馈不进入体验学习'; reason = '没有实际曝光，不解释用户反应，也不消耗试探额度'; }
    if (delivered) {
      feedbackClass = feedback === 'none' ? 'unknown' : feedback === 'explicit' ? 'explicit_preference' : feedback === 'negative' ? 'negative_contextual' : 'positive_contextual';
      if (feedbackClass === 'explicit_preference') memoryOutcome = '明确偏好在对应情境内生效';
      else if (feedbackClass === 'negative_contextual') memoryOutcome = '保存情境反馈与待验证假设';
      else memoryOutcome = '仅归档事实，未新增长期偏好';
    } else feedbackClass = 'not_observed';
    if (i.kind === 'quiet') feedbackClass = 'explicit_instruction';
    if (f.staleMemory || f.writeConflict) { if (taskById.memoryCommit) { nodeStates.memoryCommit = 'blocked'; memoryOutcome = '版本冲突，阻止覆盖并保留待整理建议'; } }
    if (stopId) {
      const afterStop = new Set(), stack = [...(adjacency(graph).next[stopId] || [])];
      while (stack.length) { const id = stack.pop(); if (afterStop.has(id)) continue; afterStop.add(id); (adjacency(graph).next[id] || []).forEach(x => stack.push(x)); }
      afterStop.forEach(id => { nodeStates[id] = 'skipped'; });
      nodeStates[stopId] = stopId === 'receipt' ? 'failed' : 'cancelled';
      if (taskById.receipt && stopId !== 'receipt') {
        nodeStates.receipt = 'done';
        const receiptDuration = taskById.receipt.end - taskById.receipt.start;
        taskById.receipt.start = taskById[stopId] ? taskById[stopId].end : taskById.receipt.start;
        taskById.receipt.end = taskById.receipt.start + receiptDuration;
      }
      if (i.kind !== 'quiet') memoryOutcome = '仅记录未执行原因；不写入用户偏好';
    }
    timeline.tasks.forEach(t => {
      const state = nodeStates[t.id];
      if (state === 'skipped') { events.push({ time: taskById[stopId] ? taskById[stopId].end : t.start, nodeId: t.id, state: 'skipped', detail: '前置条件已取消，此任务不运行' }); return; }
      events.push({ time: t.start, nodeId: t.id, state: 'running', detail: t.label + '开始；演示时长 ' + (t.end - t.start) + ' ms' });
      let detail = t.label + '完成';
      if (t.id === stopId) detail = reason;
      if (t.id === 'publish') detail = delivered ? '已通过审核与状态复核，由唯一出口模拟发布' : (f.undelivered ? '模拟发布已尝试，等待送达回执' : detail);
      if (t.id === 'feedback') detail = feedbackClass === 'unknown' ? '未获得明确回应，标记为未知；不产生负奖励' : '反馈类型：' + feedbackClass;
      if (t.id === 'facts') detail = i.kind === 'quiet' ? '保存用户明确的安静要求及适用范围' : '分别保存事件事实、用户原话和待验证推测';
      if (t.id === 'reflection') detail = '后台分析适用范围与替代解释，不向用户发言';
      if (t.id === 'memoryCommit') detail = memoryOutcome;
      events.push({ time: t.end, nodeId: t.id, state, detail });
    });
    if (reviewRetry) {
      for (let r = 1; r <= retries; r++) {
        const start = reviewRetry.baseEnd + (r - 1) * (reviewRetry.draftMs + reviewRetry.reviewMs);
        events.push({ time: start, nodeId: 'review', state: 'retry', detail: '开始第 ' + r + ' 次有界修改，草稿和复核耗时均计入预算' });
        events.push({ time: start, nodeId: 'draft', state: 'running', detail: '第 ' + r + ' 次修改具体表达' });
        events.push({ time: start + reviewRetry.draftMs, nodeId: 'draft', state: 'done', detail: '修改后的草稿交付重新审核' });
        events.push({ time: start + reviewRetry.draftMs, nodeId: 'review', state: 'running', detail: '审核第 ' + r + ' 次修改后的具体内容' });
      }
    }
    if (delivered && feedbackClass === 'explicit_preference') events.push({ time: taskById.feedback ? taskById.feedback.end : timeline.frontDuration, nodeId: 'feedback', state: 'applied', detail: '当前明确要求立即生效；长期归档不阻塞当前响应' });
    events.sort((x, y) => x.time - y.time || (x.state === 'running' ? 1 : -1));
    const duration = events.reduce((max, e) => e.state === 'skipped' ? max : Math.max(max, e.time), 0);
    const actualFrontDuration = events.reduce((max, e) => e.state !== 'skipped' && taskById[e.nodeId] && taskById[e.nodeId].phase === 'front' ? Math.max(max, e.time) : max, 0);
    const actualTasks = timeline.tasks.filter(t => nodeStates[t.id] !== 'skipped');
    const heavyCalls = actualTasks.filter(t => t.thought === 'heavy').length + retries * ['draft', 'review'].filter(id => taskById[id] && taskById[id].thought === 'heavy').length;
    return {
      events, outcome, delivered, probesIncrement: delivered && i.kind === 'probe' ? 1 : 0, feedbackSampleValid: delivered && feedbackClass !== 'unknown', feedbackClass, memoryOutcome, violations: [], nodeStates, cancelled: !!stopId || i.kind === 'quiet', schedule: timeline,
      metrics: {
        ...emptyMetrics, frontDurationMs: actualFrontDuration, totalDurationMs: duration, maxConcurrency: concurrencyPeak(actualTasks), heavyCalls, retryDurationMs: reviewRetry ? reviewRetry.cost : 0, retries, probesConsumed: delivered && i.kind === 'probe' ? 1 : 0,
        rewardEligible: delivered && feedbackClass !== 'unknown',
        preferenceUpdates: delivered && feedbackClass === 'explicit_preference' && !f.staleMemory && !f.writeConflict ? 1 : 0,
        policyVersionApplied: delivered && feedbackClass === 'explicit_preference' && !f.staleMemory && !f.writeConflict,
        immediateInstructionApplied: i.kind === 'quiet' || !!f.newQuiet || (delivered && feedbackClass === 'explicit_preference')
      }
    };
  }
  function acceptance(settings) {
    const s = settingsFor(settings), checks = [];
    const add = (id, title, owner, expected, actual, pass, evidence, adjustment) => checks.push({ id, title, owner, expected, actual, pass: !!pass, evidence, adjustment });
    const get = kind => clone(SCENARIOS.find(x => x.id === kind).input);
    const g = plan(get('complex'), s), v = validate(g), sch = schedule(g, s), t = Object.fromEntries(sch.tasks.map(x => [x.id, x]));
    add('A01', '完整链路可执行', '规划', '无循环、缺依赖或缺必需任务', v.filter(x => x.severity === 'error').length + ' 个结构错误', !v.some(x => x.severity === 'error'), 'validate(复杂复盘链路)', '检查节点开关、硬性依赖与入口');
    const broken = clone(g); broken.edges.push(makeEdge('decision', 'snapshot', '故障注入：形成循环', false)); const bv = validate(broken);
    add('A02', '循环依赖被拦截', '审核', '禁止相互等待的链路运行', bv.some(x => x.code === 'CYCLE') ? '已检测并阻止循环' : '未识别循环', bv.some(x => x.code === 'CYCLE'), '注入 决策→情境读取 的反向依赖', '补充有向图环检测');
    const noReview = clone(g); noReview.nodes = noReview.nodes.filter(x => x.id !== 'review'); noReview.edges = noReview.edges.filter(x => x.from !== 'review' && x.to !== 'review'); noReview.edges.push(makeEdge('draft', 'recheck', '故障注入：跳过审核', false)); const nv = validate(noReview);
    add('A03', '内容审核不可跳过', '审核', '草稿未审核时禁止发布', nv.some(x => x.code === 'MISSING_REVIEW') ? '缺审核已被拦截' : '未拦截', nv.some(x => x.code === 'MISSING_REVIEW'), '移除 review，再连接 draft→recheck', '恢复不可跳过的审核任务');
    const joined = t.decision && ['battleRead', 'mechanicsRead', 'planner'].every(id => !t[id] || t.decision.start >= t[id].end);
    add('A04', '综合决策等待全部证据', '决策', '记录、机制与规划完成后才开始决策', joined ? '所有必要证据均已汇合' : '发生过早决策', joined, ['battleRead', 'mechanicsRead', 'planner', 'decision'].map(id => t[id] ? id + ': ' + t[id].start + '–' + t[id].end + ' ms' : id + ': 跳过').join('；'), '补齐决策的全部前置依赖');
    const independent = ['planner', 'battleRead', 'mechanicsRead'].map(id => t[id]).filter(Boolean);
    const overlap = independent.some((a, idx) => independent.slice(idx + 1).some(b => Math.max(a.start, b.start) < Math.min(a.end, b.end)));
    add('A05', '独立工作获得可用并发', '程序调度', '并发上限至少为 2 时，独立规划或资料任务有重叠', overlap ? '独立任务已并行；其余任务按资源槽位等待' : '当前独立任务全部串行', Number(s.maxParallel) >= 2 && overlap, '总并发上限 ' + s.maxParallel + '；规划和两项读取互不依赖', '将总并发调到至少 2；移除不必要的独立任务间依赖');
    const capOkay = sch.maxConcurrency <= Number(s.maxParallel);
    add('A06', '资源上限受到约束', '程序调度', '总并发及重思考并发均不超过配置', '峰值总并发 ' + sch.maxConcurrency + '；配置 ' + s.maxParallel + '/' + s.heavySlots, capOkay && concurrencyPeak(sch.tasks.filter(x => x.thought === 'heavy')) <= Number(s.heavySlots), '按任务开始/完成时间核算重叠，非按拓扑层计数', '检查资源槽位释放与任务选择');
    const simple = plan(get('simple'), s); add('A07', '简单问题跳过重度环节', '规划', '不启动重规划与重反思', simple.nodes.filter(n => n.thought === 'heavy').length + ' 次重思考', !simple.nodes.some(n => ['planner', 'reflection'].includes(n.id)), simple.skipped.filter(n => ['planner', 'reflection'].includes(n.id)).map(n => n.reason).join('；'), '修正按复杂度与反馈触发的路由');
    const quiet = simulate(plan(get('quiet'), s), s); add('A08', '安静指令立即生效', '程序调度', '取消发言并保留明确指令', quiet.outcome, !quiet.delivered && quiet.metrics.immediateInstructionApplied && quiet.metrics.frontDurationMs <= 100, '直接取消链路；前台演示耗时 ' + quiet.metrics.frontDurationMs + ' ms', '让停止指令绕过重思考并取消队列');
    const combatInput = { ...get('probe'), inCombat: true }; const combat = simulate(plan(combatInput, s), s); add('A09', '高负担窗口禁止试探', '审核', '战斗时不发布、不消耗试探额度', combat.outcome, !combat.delivered && combat.metrics.probesConsumed === 0, '主动试探输入 inCombat=true', '把战斗状态纳入硬性预检');
    const exhaustedInput = { ...get('probe'), probesUsed: Math.max(0, Number(s.maxProbesPerSession)) }; const exhausted = simulate(plan(exhaustedInput, s), s); add('A10', '额度用完后停止试探', '程序调度', '额度用完时不继续探索', exhausted.outcome, !exhausted.delivered, 'probesUsed=maxProbesPerSession', '所有主动输出共用预算入口');
    const probeInput = { ...get('probe'), minutesSinceActive: Number(s.activeCooldownMinutes) + 1, probesUsed: 0 };
    const usableProbeSettings = { ...s, maxProbesPerSession: Math.max(1, Number(s.maxProbesPerSession)), replyDeadlineMs: Math.max(10000, Number(s.replyDeadlineMs)) };
    const missing = simulate(plan(probeInput, usableProbeSettings), usableProbeSettings, { feedback: 'none' }); add('A11', '未回复保持未知', '反馈反思', '实际送达后，无回应不产生负奖励或偏好更新', missing.feedbackClass + '；偏好更新 ' + missing.metrics.preferenceUpdates, missing.delivered && missing.feedbackClass === 'unknown' && !missing.metrics.rewardEligible && missing.metrics.preferenceUpdates === 0, '模拟试探已送达，feedback=none；保证测试前置额度可用', '区分未知反馈与明确拒绝');
    const stale = simulate(g, { ...s, replyDeadlineMs: Math.max(10000, Number(s.replyDeadlineMs)) }, { newQuiet: true }); add('A12', '发布前新指令优先', '程序调度', '草稿完成后出现安静要求也必须取消', stale.outcome, !stale.delivered && stale.metrics.immediateInstructionApplied, '故障注入 newQuiet=true', '在实际发布前再次核对最新状态');
    const undelivered = simulate(plan(probeInput, usableProbeSettings), usableProbeSettings, { undelivered: true, feedback: 'positive' }); add('A13', '未送达不进入体验学习', '反馈反思', '未曝光不消耗试探额度、不产生奖励', undelivered.outcome, !undelivered.delivered && !undelivered.metrics.rewardEligible && undelivered.metrics.probesConsumed === 0, '故障注入 undelivered=true，忽略假定正反馈', '让送达回执成为学习的前置条件');
    const conflict = simulate(plan(get('conflict'), { ...s, replyDeadlineMs: 20000 }), { ...s, replyDeadlineMs: 20000 }, { staleMemory: true, feedback: 'explicit' }); add('A14', '旧建议不能覆盖新记忆', '记忆整理', '版本冲突阻止持久提交，当前明确指令仍生效', conflict.memoryOutcome, conflict.nodeStates.memoryCommit === 'blocked' && conflict.metrics.preferenceUpdates === 0 && conflict.metrics.immediateInstructionApplied, '故障注入 staleMemory=true；明确指令先即时执行', '以版本为条件提交，冲突重新整理');
    const fail = simulate(g, s, { reviewFail: true }); add('A15', '审核失败有重试上限', '审核', '到达修改次数上限后停止发布', '重试 ' + fail.metrics.retries + ' 次；' + fail.outcome, !fail.delivered && fail.metrics.retries <= Number(s.retryLimit), '故障注入审核持续不通过', '设定有限修改次数及取消出口');
    const backEdge = clone(g); backEdge.edges.push(makeEdge('reflection', 'decision', '故障注入：前台等待后台', false)); const be = validate(backEdge); add('A16', '前台不等待本轮反思', '规划', '禁止后台学习反向阻塞当前互动', be.some(x => x.code === 'FRONT_WAITS_BACKGROUND') ? '已阻止错误前后依赖' : '未阻止', be.some(x => x.code === 'FRONT_WAITS_BACKGROUND'), '注入 reflection→decision', '将学习成果用于后续事件');
    add('A17', '前台回应满足演示预算', '决策', '复杂复盘演示前台耗时不超过配置预算', sch.frontDuration + ' / ' + s.replyDeadlineMs + ' ms', sch.frontDuration <= Number(s.replyDeadlineMs), '所有耗时为可调整的预设演示值，不代表真实模型时延', '复用计划、提升可用并发或调整合适的回应截止时间');
    const mini = { nodes: [makeNode('a', '短读取', 'execution', 'front', 'light', 20, true, ''), makeNode('b', '长读取', 'execution', 'front', 'light', 100, true, ''), makeNode('c', '仅依赖短读取', 'decision', 'front', 'light', 10, true, '')], edges: [makeEdge('a', 'c', '')], settings: { ...s, maxParallel: 2 } };
    const ms = schedule(mini, { ...s, maxParallel: 2 }), mt = Object.fromEntries(ms.tasks.map(x => [x.id, x])); add('A18', '调度没有全局层级屏障', '程序调度', '短任务的下游可以早于无关长任务完成启动', '下游启动 ' + mt.c.start + ' ms；无关任务完成 ' + mt.b.end + ' ms', mt.c.start < mt.b.end, '独立小图：a→c，b 独立；测试并发上限固定为 2', '按依赖完成事件调度，不按整层结束调度');
    const gateTestSettings = { ...DEFAULTS, activeCooldownMinutes: Math.max(1, Number(s.activeCooldownMinutes) || 0), maxProbesPerSession: Math.max(1, Number(s.maxProbesPerSession) || 0), replyDeadlineMs: 10000 };
    const gateInput = { ...get('probe'), minutesSinceActive: gateTestSettings.activeCooldownMinutes + 1, probesUsed: 0, failedNoReplyCount: 0, pendingProbe: false, quietMode: false, inCombat: false };
    const isolation = '规则隔离用例：采用默认资源与演示耗时、10 秒截止、至少 1 次可用会话额度，避免其他配置干扰；';
    const coldInput = { ...gateInput, minutesSinceActive: gateTestSettings.activeCooldownMinutes - 1 };
    const coldGraph = plan(coldInput, gateTestSettings), coldRun = simulate(coldGraph, gateTestSettings);
    add('A19', '主动互动总冷却约束试探', '程序调度', '主动试探也必须等待总冷却结束；本用例实际检查 kind=probe', coldRun.outcome + '；额度消耗 ' + coldRun.probesIncrement, !coldRun.delivered && coldRun.probesIncrement === 0 && coldGraph.blockedReasons.some(x => x.includes('冷却')), isolation + 'kind=probe；距离上次主动互动 ' + coldInput.minutesSinceActive + ' 分钟，要求 ' + gateTestSettings.activeCooldownMinutes + ' 分钟；零冷却配置在本例隔离为 1 分钟', '所有主动互动进入共用冷却检查，未执行不消耗额度');
    const pendingGraph = plan({ ...gateInput, pendingProbe: true }, gateTestSettings), pendingRun = simulate(pendingGraph, gateTestSettings);
    add('A20', '已有待回应试探时不叠加', '程序调度', '已有一个等待回应的试探时，取消新的试探', pendingRun.outcome + '；新试探额度消耗 ' + pendingRun.probesIncrement, !pendingRun.delivered && pendingRun.probesIncrement === 0 && pendingGraph.blockedReasons.some(x => x.includes('等待回应')), isolation + 'kind=probe、pendingProbe=true，其余试探条件满足', '保留单个等待回应的试探，不追加追问');
    const noReplyRun = simulate(plan(gateInput, gateTestSettings), gateTestSettings, { feedback: 'none' });
    const twiceGraph = plan({ ...gateInput, failedNoReplyCount: 2 }, gateTestSettings), twiceRun = simulate(twiceGraph, gateTestSettings);
    add('A21', '两次未回应暂停，偏好仍未知', '反馈反思', '两次未回应会暂停本会话试探；沉默不写成厌恶或负反馈', '沉默反馈 ' + noReplyRun.feedbackClass + '；偏好更新 ' + noReplyRun.metrics.preferenceUpdates + '；' + twiceRun.outcome, noReplyRun.delivered && noReplyRun.feedbackClass === 'unknown' && !noReplyRun.metrics.rewardEligible && noReplyRun.metrics.preferenceUpdates === 0 && !twiceRun.delivered && twiceGraph.blockedReasons.some(x => x.includes('连续两次')), isolation + '分别检查已送达且 feedback=none，以及 failedNoReplyCount=2 的暂停状态；计数作为明确输入，不伪装成自动递增', '把暂停打扰的运行控制与长期偏好推断分开');
    const writeGraph = { nodes: [makeNode('writeA', '记忆写入一', 'memory', 'back', 'rule', 100, true, '', { resource: 'memory-write' }), makeNode('writeB', '记忆写入二', 'memory', 'back', 'rule', 80, true, '', { resource: 'memory-write' }), makeNode('readOnly', '独立只读任务', 'execution', 'back', 'rule', 120, true, '')], edges: [], settings: { ...DEFAULTS, maxParallel: 3 } };
    const writeSchedule = schedule(writeGraph, writeGraph.settings), writeTasks = writeSchedule.tasks.filter(x => x.resource === 'memory-write');
    const writePeak = concurrencyPeak(writeTasks);
    add('A22', '相同记忆写入资源保持串行', '记忆整理', '即使有多个并发槽位，memory-write 同时最多一项写入', '写入峰值并发 ' + writePeak + '；总任务峰值并发 ' + writeSchedule.maxConcurrency, writeTasks.length === 2 && writePeak === 1 && writeSchedule.maxConcurrency >= 2, '隔离资源锁测试：固定总并发为 3，两个无依赖的 memory-write 任务加一个独立只读任务；' + writeTasks.map(x => x.id + ': ' + x.start + '–' + x.end + ' ms').join('；'), '对记忆提交使用同一写入资源锁，读取仍可并发');
    const requestGraph = plan({ ...get('simple'), quietMode: true }, gateTestSettings), requestRun = simulate(requestGraph, gateTestSettings);
    add('A23', '安静模式仍回应主动请求', '决策', 'quietMode 限制主动打扰，用户主动请求应正常回应', requestRun.outcome + '；' + (requestRun.delivered ? '已回应用户' : '未回应'), requestRun.delivered && !requestRun.cancelled && requestRun.probesIncrement === 0, isolation + 'kind=simple、quietMode=true；不注入代表当下明确停止的 newQuiet；kind=quiet 的立即停止由 A08 验证', '将持续安静偏好与当下明确停止指令分别处理');
    return checks;
  }
  function concurrencyPeak(tasks) {
    const points = [];
    tasks.forEach(t => { points.push([t.start, 1]); points.push([t.end, -1]); });
    points.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    let count = 0, max = 0; points.forEach(p => { count += p[1]; max = Math.max(max, count); }); return max;
  }
  return { DEFAULTS, ROLES, SCENARIOS, plan, validate, schedule, simulate, acceptance, toggleNode, probeBlockers, concurrencyPeak };
});
