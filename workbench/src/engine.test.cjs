const assert = require('node:assert/strict');
const E = require('./engine.js');
const clone = x => JSON.parse(JSON.stringify(x));
let assertions = 0;
const check = (condition, message) => { assert.ok(condition, message); assertions++; };

for (const scene of E.SCENARIOS) {
  const g = E.plan(scene.input, E.DEFAULTS);
  check(!E.validate(g).some(x => x.severity === 'error'), scene.id + ': valid graph');
  const schedule = E.schedule(g);
  check(schedule.blocked.length === 0, scene.id + ': all tasks scheduled');
  const tasks = Object.fromEntries(schedule.tasks.map(t => [t.id, t]));
  for (const edge of g.edges) check(tasks[edge.to].start >= tasks[edge.from].end, scene.id + ': dependency enforced ' + edge.from + '>' + edge.to);
  check(E.concurrencyPeak(schedule.tasks) <= E.DEFAULTS.maxParallel, scene.id + ': global resources');
  check(E.concurrencyPeak(schedule.tasks.filter(t => t.thought === 'heavy')) <= E.DEFAULTS.heavySlots, scene.id + ': heavy resources');
}
const suite = E.acceptance();
check(suite.length === 23, 'acceptance coverage includes the requested 23 visible cases');
check(suite.every(x => x.pass), 'default acceptance: ' + suite.filter(x => !x.pass).map(x => x.id + ' ' + x.actual).join('; '));
for (const id of ['A19', 'A20', 'A21', 'A22', 'A23']) check(suite.some(x => x.id === id && x.pass && x.evidence), id + ': engine-backed visible acceptance with evidence');
check(E.acceptance({replyDeadlineMs:1,maxProbesPerSession:0,activeCooldownMinutes:0}).filter(x=>['A19','A20','A21','A22','A23'].includes(x.id)).every(x=>x.pass), 'five isolated rule cases are not confounded by unrelated deadline or empty budget');
check(E.acceptance({ maxParallel: 1, heavySlots: 1 }).some(x => !x.pass && x.id === 'A05'), 'acceptance is not hardcoded pass');
check(E.acceptance({ maxParallel: 2, heavySlots: 1 }).find(x => x.id === 'A05').pass, 'two slots provide valid partial concurrency');
check(E.acceptance({ replyDeadlineMs: 200 }).some(x => !x.pass && x.id === 'A17'), 'time target responds to settings');
const complex = E.plan('complex');
complex.nodes.find(n => n.id === 'draft').duration = 333;
const withoutPlan = E.toggleNode(complex, 'planner', false);
check(!withoutPlan.nodes.some(n => n.id === 'planner'), 'optional removed');
check(withoutPlan.nodes.find(n => n.id === 'draft').duration === 333, 'duration edit survives toggle');
check(!E.validate(withoutPlan).some(x => x.severity === 'error'), 'bypassed dependencies remain valid');
const restored = E.toggleNode(withoutPlan, 'planner', true);
check(restored.nodes.some(n => n.id === 'planner'), 'optional restored');
check(!E.validate(restored).some(x => x.severity === 'error'), 'restored graph valid');
const expanded = clone(complex);
expanded.nodes.push({id:'customRead',label:'补充资料',role:'execution',phase:'front',thought:'light',duration:200,required:false});
expanded.edges.push({from:'snapshot',to:'customRead',hard:false},{from:'customRead',to:'decision',hard:false});
const customPreserved = E.toggleNode(expanded,'reflection',false);
check(customPreserved.nodes.some(x=>x.id==='customRead'), 'custom task survives other toggle');
check(!E.validate(customPreserved).some(x=>x.severity==='error'), 'custom dependencies remain valid');
assert.throws(() => E.toggleNode(complex, 'review', false)); assertions++;
const noReflect = E.toggleNode(complex, 'reflection', false);
check(!E.validate(noReflect).some(x => x.severity === 'error'), 'reflection optional with dependency repair');
const cycle = clone(complex); cycle.edges.push({from:'memoryCommit',to:'snapshot',hard:false});
check(E.validate(cycle).some(x => x.code === 'CYCLE'), 'cycle detection');
check(!E.simulate(cycle).delivered, 'invalid graph blocked');
for (const patch of [{ inCombat: true }, { quietMode: true }, { pendingProbe: true }, { minutesSinceActive: 0 }, { probesUsed: 2 }, { failedNoReplyCount: 2 }, { allowProactive: false }]) {
  const g = E.plan({ kind: 'probe', ...patch });
  const run = E.simulate(g);
  check(!run.delivered, 'probe blocked ' + JSON.stringify(patch));
  check(run.probesIncrement === 0, 'blocked probe not consumed');
  check(!run.feedbackSampleValid, 'blocked probe no feedback');
}
const probe = E.plan({kind:'probe'});
const unknown = E.simulate(probe, null, {feedback:'none'});
check(unknown.delivered && unknown.feedbackClass === 'unknown', 'delivered silence stays unknown');
check(!unknown.metrics.rewardEligible && unknown.metrics.preferenceUpdates === 0, 'unknown no reward or preference');
const miss = E.simulate(probe, null, {undelivered:true, feedback:'positive'});
check(!miss.feedbackSampleValid && miss.probesIncrement === 0, 'no exposure no learning');
const stale = E.simulate(probe, null, {staleMemory:true,feedback:'explicit'});
check(stale.nodeStates.memoryCommit === 'blocked' && stale.metrics.preferenceUpdates === 0, 'stale commit blocked');
check(stale.metrics.immediateInstructionApplied, 'explicit instruction immediate despite archive conflict');
const stopped = E.simulate(probe, null, {newQuiet:true});
check(!stopped.delivered && stopped.metrics.immediateInstructionApplied, 'new quiet supersedes plan');
const requestedInQuietMode = E.simulate(E.plan({kind:'simple',quietMode:true}));
check(requestedInQuietMode.delivered && !requestedInQuietMode.cancelled, 'quiet mode suppresses proactive probes but allows user-requested replies');
check(stopped.metrics.heavyCalls < stopped.metrics.plannedHeavyCalls, 'cancelled reflection not counted as actual heavy call');
check(stopped.metrics.frontDurationMs < stopped.metrics.plannedFrontDurationMs, 'cancelled publish not counted in actual front time');
const reject = E.simulate(probe, {retryLimit:2}, {reviewFail:true});
check(!reject.delivered && reject.metrics.retries === 2, 'finite retries');
const recovered = E.simulate(probe, {retryLimit:1}, {reviewFail:true,reviewRecovers:true});
check(recovered.delivered && recovered.metrics.retries === 1, 'bounded revision success');
const cleanRun = E.simulate(probe);
check(recovered.metrics.frontDurationMs > cleanRun.metrics.frontDurationMs, 'revision consumes time budget');
const tightened = E.simulate(probe, {retryLimit:1,replyDeadlineMs:cleanRun.metrics.frontDurationMs + 100}, {reviewFail:true,reviewRecovers:true});
check(!tightened.delivered && tightened.outcome.includes('截止时间'), 'revision can exceed deadline');
const quiet = E.simulate(E.plan('quiet'), null, {staleMemory:true});
check(!quiet.delivered && quiet.metrics.immediateInstructionApplied, 'quiet unaffected by persistence');
const custom = {
  nodes:[
    {id:'a',label:'a',phase:'back',thought:'light',duration:30,resource:'memory-write'},
    {id:'b',label:'b',phase:'back',thought:'light',duration:20,resource:'memory-write'},
    {id:'c',label:'c',phase:'front',thought:'light',duration:10}
  ], edges:[]
};
const lock = E.schedule(custom, {maxParallel:3});
check(E.concurrencyPeak(lock.tasks.filter(t => t.resource==='memory-write')) === 1, 'memory writes mutex');
const invalidDeadline=E.plan('complex',{replyDeadlineMs:-1});
check(E.validate(invalidDeadline).some(x=>x.code==='DEADLINE_INVALID'),'invalid deadline rejected');
const invalidThought=E.plan('simple');invalidThought.nodes[0].thought='ultra';
check(E.validate(invalidThought).some(x=>x.code==='THOUGHT_INVALID'),'unknown thought rejected');
const invalidScale=E.plan('simple',{modelTimeScale:NaN});
check(E.validate(invalidScale).some(x=>x.code==='TIME_SCALE_INVALID'),'invalid time scale rejected');
console.log(JSON.stringify({assertions, acceptance: suite.map(x=>({id:x.id,pass:x.pass})), scenarios:E.SCENARIOS.map(x=>{const g=E.plan(x.input);const s=E.schedule(g);return {id:x.id,nodes:g.nodes.length,frontMs:s.frontDuration,totalMs:s.duration,concurrency:s.maxConcurrency};})},null,2));
