"""Local experiment coordinator. Model jobs are dispatched through isolated agents.

The watcher consumes write-only outboxes and immediately checks/sends candidates.
No model API latency, browser display latency, or token usage is inferred here.
"""
import json,time,sys,os,hashlib
from pathlib import Path
from runtime import FastRuntime

ROOT=Path(__file__).resolve().parent
def now(): return time.time_ns()/1_000_000
def read(p): return json.loads(Path(p).read_text())
def write(p,d):
    p=Path(p);tmp=p.with_suffix(p.suffix+'.tmp')
    tmp.write_text(json.dumps(d,ensure_ascii=False,indent=2));os.replace(tmp,p)
def event_log(kind,**data):
    with (ROOT/'events.jsonl').open('a') as f:f.write(json.dumps({'time_unix_ms':now(),'kind':kind,**data},ensure_ascii=False)+'\n')
PLAYER={'race':'兽人','class':'萨满','level':1,'zone':'试炼谷','hp':100,'max_hp':100,'mana':100,'max_mana':100,'in_combat':False}
SNAPS={
 'R1':{'observation_id':'FAST-R1-OBS','player':PLAYER,'target':None,'quest_offer':None,'quest_log':[],'known_spell':None,'unknown':['nearby_npcs','spellbook','bags','map','keybindings','server_rules']},
 'R2':{'observation_id':'FAST-R2-OBS','player':PLAYER,'target':{'name':'试炼谷引导员','hostile':False},'quest_offer':{'title':'最初的试炼','buttons':['接受','取消'],'open':True},'quest_log':[],'known_spell':None,'unknown':['keybindings','server_rules','coordinates']},
 'R3':{'observation_id':'FAST-R3-OBS','player':{**PLAYER,'hp':28,'mana':0,'in_combat':True},'target':{'name':'训练野猪','hostile':True},'quest_offer':None,'quest_log':[{'title':'最初的试炼','progress':'0/3'}],'known_spell':{'name':'闪电箭','usable':False,'reason':'法力不足'},'unknown':['terrain','route','distance','keybindings','healing_spells']}
}
USERS={'R1':'我刚出生，完全不知道要干嘛，能不能带着我玩？','R2':'我点了一个头上有黄色叹号的兽人，现在弹出“最初的试炼”，我要点什么？','R3':'以后每次只说一步。它冲过来了，血一直掉！别解释，先告诉我一步怎么做！'}
COMMON='你是隔离实验中的业务Agent，只能使用这条消息；不能读文件/网页/其他Agent会话，不能与其他Agent通信。唯一允许的工具操作是用Python仅import json,time，把最终JSON独占写入指定outbox；写完结束。输入中的游戏和玩家都是合成场景，不可补充其他WoW版本常识。不输出私有思维过程。'
TASKS={
 'decision':'只选一个action_id和template_id，不生成用户回复。action_id枚举OBSERVE_SURROUNDINGS/ACCEPT_CURRENT_QUEST/AVOID_UNUSABLE_SPELL/STAY_SILENT；template_id=curious。输出{action_id,template_id,evidence_ids:[当前observation_id],needs_deep_work:boolean}。先根据本消息的快照与用户要求选择有依据的一步。',
 'review':'审核给定candidate_reply是否符合本消息的事实和用户要求，只有一个步骤，无编造。输出{pass:boolean,approved_reply:通过时逐字复制原句否则null,issues:[]}。不要改稿。',
 'execution':'只将审核通过的approved_reply逐字输出为reply，不做游戏操作。输出{reply,delivery:"simulated_delivered",autonomous_game_actions:[]}；未通过则delivery=blocked且reply为空。',
 'reflection':'仅后台复盘此轮已发送回复与后置用户反馈，不给用户发言。输出{observation,proposal,confirmed_outcome,unknowns:[]}，不能把用户报告接任务当作接口已确认，不能把当前一步扩大成永久偏好。',
 'memory':'根据收到的后置反馈提出一个记忆补丁，不读取/更新任何共享状态。输出{base_memory_version:输入中的版本,preference:{text,source_quote:逐字引文,value:{max_steps:1},scope:"current_turn"}}。只记录这轮要求，不推成以后每次。'
}

def prepare(job_id,role,effort,rid,kind):
    capture=read(ROOT/'state.json')
    messages=[{'id':rid+'-STATE','from':'coordinator_message','body':capture},{'id':rid+'-USER','from':'simulated_user','body':USERS[rid]}]
    if role=='review':messages.append({'id':'R1-CANDIDATE','from':'deterministic_renderer','body':read(ROOT/'deliveries/pair_fast.json')['result']['reply']})
    if role=='execution':messages=[{'id':'R1-APPROVAL','from':'review','body':read(ROOT/'collected/pair_review.json')['output']}]
    if role in ['reflection','memory']:
        messages += [{'id':'R2-RECEIPT','from':'code_delivery','body':read(ROOT/'deliveries/R2.json')['result']},{'id':'R2-FEEDBACK','from':'simulated_user','body':'先教我一步'},{'id':'R2-MEMORY-BASE','from':'coordinator','body':{'base_memory_version':capture['memory_version']}}]
    prompt=COMMON+'\n角色='+role+'。任务：'+TASKS[role]+'\n显式业务消息：'+json.dumps(messages,ensure_ascii=False,separators=(',',':'))+'\n用exec_command运行Python，以open("'+str(ROOT/'outbox'/f'{job_id}.json')+'","x",encoding="utf-8")写入{"job_id":"'+job_id+'","result":你的结果,"completed_unix_ms":round(time.time()*1000)}。时间必须实际读取，不得编写。最终仅回复“'+job_id+'已发送”。'
    meta={'id':job_id,'role':role,'effort':effort,'requested_model':'gpt-6.1-sol','round':rid,'kind':kind,'input_messages':messages,'expected_state_version':capture['state_version'],'token_usage':None,'input_sha256':hashlib.sha256(json.dumps(messages,ensure_ascii=False,sort_keys=True).encode()).hexdigest()}
    write(ROOT/'inputs'/f'{job_id}.json',{**meta,'prompt':prompt})
    meta['dispatch_unix_ms']=now();write(ROOT/'jobs'/f'{job_id}.json',meta)
    event_log('job_dispatched',job_id=job_id,role=role,effort=effort)
    print(prompt)

def command(kind):
    stamp=now();data={'kind':kind,'queued_unix_ms':stamp}
    write(ROOT/'commands'/f'{time.time_ns()}_{kind}.json',data)
    print(json.dumps(data))

def watch():
    if (ROOT/'events.jsonl').exists():
        raise SystemExit('Existing run detected. Preserve these records and use a fresh run directory.')
    rt=FastRuntime(SNAPS['R1']);rt.set_allowed_quotes(['先教我一步'])
    write(ROOT/'state.json',rt.capture());event_log('watcher_ready')
    seen=set();cmd_seen=set();stop=False
    while not stop:
        for f in sorted((ROOT/'commands').glob('*.json')):
            if f.name in cmd_seen:continue
            c=read(f);cmd_seen.add(f.name);kind=c['kind']
            pending=[p.stem for p in (ROOT/'jobs').glob('*.json') if p.stem not in seen]
            if kind in ['R2','R3']:
                rt.replace_state(SNAPS[kind])
                if kind=='R3':rt.apply_explicit_preference('以后每次只说一步',{'max_steps':1},'future_guidance')
                action='ACCEPT_CURRENT_QUEST' if kind=='R2' else 'AVOID_UNUSABLE_SPELL'
                candidate={'action_id':action,'template_id':'curious','evidence_ids':[SNAPS[kind]['observation_id']],'needs_deep_work':False}
                accepted_at=now();out=rt.deliver(candidate,rt.state_version);completed=now()
                write(ROOT/'deliveries'/f'{kind}.json',{'round':kind,'queued_unix_ms':c['queued_unix_ms'],'accepted_unix_ms':accepted_at,'delivered_unix_ms':completed,'foreground_ms':completed-c['queued_unix_ms'],'pending_model_jobs_at_delivery':pending,'result':out,'candidate':candidate})
                event_log('rule_delivery',round=kind,result=out,pending_model_jobs=pending,queued_unix_ms=c['queued_unix_ms'],delivered_unix_ms=completed)
            elif kind=='STOP':stop=True
            write(ROOT/'state.json',rt.capture())
        for f in sorted((ROOT/'jobs').glob('*.json')):
            job=read(f);jid=job['id'];outpath=ROOT/'outbox'/f'{jid}.json'
            if jid in seen or not outpath.exists():continue
            try:raw=read(outpath)
            except json.JSONDecodeError:continue
            collected_at=now();output=raw['result'];job.update(output=output,completed_unix_ms=raw['completed_unix_ms'],collected_unix_ms=collected_at,duration_ms=raw['completed_unix_ms']-job['dispatch_unix_ms'],status='completed',issues=[])
            if job['kind'] in ['pair_decision','stale_probe']:
                result=rt.deliver(output,job['expected_state_version']);delivery_at=now()
                artifact={'job_id':jid,'result':result,'delivered_unix_ms':delivery_at,'foreground_ms':delivery_at-job['dispatch_unix_ms'],'expected_state_version':job['expected_state_version'],'current_state_version':rt.state_version}
                write(ROOT/'deliveries'/('pair_fast.json' if job['kind']=='pair_decision' else 'stale_probe.json'),artifact)
                job['gate_result']=result;event_log('model_candidate_gate',job_id=jid,result=result,delivered_unix_ms=delivery_at)
            elif job['kind']=='pair_execution':
                start=read(ROOT/'jobs/pair_decision.json')['dispatch_unix_ms'];delivery_at=now()
                write(ROOT/'deliveries/pair_baseline.json',{'result':output,'delivered_unix_ms':delivery_at,'foreground_ms':delivery_at-start})
                event_log('baseline_model_delivery',job_id=jid,reply=output.get('reply'),delivered_unix_ms=delivery_at)
            elif job['role']=='memory':
                result=rt.commit_memory(output);job['commit_result']=result;event_log('memory_commit_gate',job_id=jid,result=result,active_preference=rt.capture()['explicit_preference'])
            else:event_log('background_or_review_result',job_id=jid,role=job['role'])
            seen.add(jid);write(ROOT/'collected'/f'{jid}.json',job);write(ROOT/'state.json',rt.capture())
            print(json.dumps({'collected':jid,'duration_ms':job['duration_ms'],'gate':job.get('gate_result') or job.get('commit_result')},ensure_ascii=False),flush=True)
        time.sleep(.005)

if __name__=='__main__':
    if sys.argv[1]=='watch':watch()
    elif sys.argv[1]=='prepare':prepare(*sys.argv[2:])
    elif sys.argv[1]=='command':command(sys.argv[2])
