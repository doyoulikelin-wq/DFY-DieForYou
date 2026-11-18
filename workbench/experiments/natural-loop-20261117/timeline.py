"""Attach source-backed replay events. No synthesized tokens or delivery events."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
SHANGHAI=timezone(timedelta(hours=8))
TURN_EVENTS={'turn_started','local_delivery','silence_selected'}
JOB_EVENTS={'job_created','worker_dispatch_registered','model_candidate_received','model_delivery_gate','memory_commit'}
SESSION_EVENTS={'state_changed','preference_changed'}
ROLE_NAMES={'reply':'快速表达','planner':'规划 Agent','decision':'决策 Agent','reflection':'反思 Agent','memory':'记忆 Agent'}

def safe_ns(value,key=''):
    if isinstance(value,dict):return {k:safe_ns(v,k) for k,v in value.items()}
    if isinstance(value,list):return [safe_ns(x) for x in value]
    if isinstance(value,int) and (key.endswith('_ns') or abs(value)>9007199254740991):return str(value)
    return value

def clock_text(ns):
    seconds,nanos=divmod(ns,1000000000)
    return datetime.fromtimestamp(seconds,SHANGHAI).replace(microsecond=nanos//1000).isoformat(timespec='milliseconds')

def brief(value):return json.dumps(value,ensure_ascii=False,separators=(',',':'))

def enrich(report):
    report=deepcopy(report)
    report.setdefault('metadata',{})['default_round_id']='r9-stale-reply'
    report['metadata']['streaming_note']='真实事件流回放；上一轮没有采集逐token增量。候选与本地交付分别展示。'
    raw=json.loads((HERE/'run-03/results.json').read_text())
    lines=(HERE/'run-03/events.jsonl').read_text().splitlines()
    records=[(i+1,line,json.loads(line)) for i,line in enumerate(lines)]
    turns={t['id']:t for t in raw['turns']};jobs={j['id']:j for j in raw['jobs']}
    all_selected=set()
    for round in report['rounds']:
        rid=round['id'];turn=turns[rid]
        tids={rid,'r7-refresh-low'} if rid=='r7-conflict-low' else {rid}
        jids={j['id'] for j in jobs.values() if j.get('origin_turn') in tids}
        session_ids={turns[t]['session_id'] for t in tids}
        origin=turn['started_ns']
        next_starts={s:min([t['started_ns'] for t in turns.values() if t['session_id']==s and t['id'] not in tids and t['started_ns']>origin] or [float('inf')]) for s in session_ids}
        selected=[]
        for line_no,line,e in records:
            name=e['event'];d=e['data'];include=False
            if name in TURN_EVENTS:include=d.get('id') in tids
            elif name in JOB_EVENTS:include=d.get('id') in jids
            elif 'job_id' in d:include=d['job_id'] in jids
            elif name=='synthetic_game_read_completed':include=d.get('origin_turn') in tids
            elif name in SESSION_EVENTS:
                s=d.get('session_id');include=s in session_ids and origin<=e['mono_ns']<next_starts[s]
            elif name=='prompt_revision':include=rid in d.get('cases',[])
            if include:selected.append((line_no,line,e))
        selected.sort(key=lambda x:(x[2]['mono_ns'],x[0]))
        assert selected and all(e['mono_ns']>=origin for _,_,e in selected)
        events=[];segments=[]
        for line_no,line,e in selected:
            name=e['event'];d=e['data'];at=(e['mono_ns']-origin)/1e6
            jid=d.get('job_id') or (d.get('id') if d.get('id') in jids else None)
            job=jobs.get(jid,{})
            tid=d.get('id') if name in TURN_EVENTS else job.get('origin_turn',d.get('origin_turn'))
            item={'id':f'run-03:{line_no}','source_line':line_no,'at_ms':at,'wall_time':clock_text(e['wall_ns']),'raw_type':name,'type':'control','actor':'协调器','label':name,'summary':'','job_id':jid,'turn_id':tid,'level':'info','payload':safe_ns(d),'raw_event':safe_ns(e),'raw_line':line,'channel':'internal'}
            user_text=None;delivered_text=None
            if name=='turn_started':
                continuation=rid=='r7-conflict-low' and d['id']=='r7-refresh-low'
                item.update(type='control' if continuation else 'input',label='刷新结果进入续处理' if continuation else '收到输入并完成路由',summary=('同一用户请求的工具续处理；没有第二次用户发言。' if continuation else d['packet']['user_text'] or '收到主动事件')+f" 路径：{d['route']['route']}。")
                if not continuation and d['packet']['user_text']:
                    user_text=d['packet']['user_text'];item['channel']='user_input'
            elif name=='job_created':
                item.update(label='建立独立任务',summary=f"{ROLE_NAMES.get(d['kind'],d['kind'])} · {d['requested_model']} · {d['effort']}；收到显式信息包。")
            elif name=='worker_dispatch_registered':
                item.update(type='dispatch',label='登记任务下发',summary=f"{jid} · {d['effort']}。等待完整候选；未记录模型内部进度。")
            elif name=='model_candidate_received':
                c=d['candidate'];kind=job.get('kind');item.update(type='candidate',actor=ROLE_NAMES.get(kind,'Agent'),label='收到完整候选',summary=c.get('utterance') or c.get('assessment') or c.get('decision_brief') or brief(c))
                if kind=='planner':item.update(type='plan',label='规划器返回链路')
                if kind=='decision':item['summary']=('选择不补发。' if c.get('should_deliver') is False else '')+c.get('reason','')
                if kind=='memory':item['summary']='记忆候选：'+brief(c)
            elif name in {'model_delivery_gate','local_delivery'}:
                gate=d['gate'];accepted=gate.get('accepted') is True
                item.update(type='delivery' if accepted else 'gate',label='本地发送检查接受' if accepted else '本地发送检查拦截',summary=gate.get('reply','') if accepted else gate.get('reason','未通过'),level='info' if accepted else 'warning',channel='user_delivery' if accepted else 'internal')
                if accepted and gate.get('reply'):delivered_text=gate['reply']
            elif name=='silence_selected':item.update(type='gate',label='主动事件保持沉默',summary=d['gate'].get('reason','proactive_disabled'))
            elif name=='dispatch_scheduling_limit':item.update(label='排队诊断（事后补记）',summary='第一次启动触及并发槽位限制；此时刻是补记时间，不是排队开始时间。',level='warning')
            elif name=='synthetic_game_read_completed':item.update(type='state',actor='模拟游戏接口',label='只读接口返回',summary=d['api']+' → '+brief(d['result']),channel='world_update')
            elif name=='before_state_invalidation':item.update(label='记录在途候选状态',summary='候选尚未收到：'+str(d['candidate_pending']))
            elif name=='state_changed':item.update(type='state',label='游戏状态更新',summary=brief(d['fields']),channel='world_update')
            elif name=='planner_dag_validated':item.update(type='plan',label='规划依赖检查通过',summary=f"{d['node_count']} 个节点；顺序 {brief(d['topological_order'])}；不计划新增交付。")
            elif name=='explicit_user_preference_arrived_while_candidate_pending':
                user_text=d['user_text'];item.update(type='input',actor='模拟用户',label='新明确偏好到达',summary=user_text+'；旧候选尚未收到。',channel='user_input')
            elif name=='preference_changed':item.update(type='preference',label='明确偏好立即生效',summary=brief(d['value'])+'；范围 '+d['scope'])
            elif name=='memory_commit':
                result=d['result'];item.update(type='memory',label='记忆提交接受' if result['accepted'] else '记忆提交拒绝',summary=result['reason'],level='info' if result['accepted'] else 'warning')
            elif name=='prompt_revision':item.update(label='提示修订记录',summary='提示 '+d['version']+'；原失败保留，当前是同样本复测。')
            events.append(item);all_selected.add(line_no)
            if user_text is not None:segments.append({'id':item['id']+':user','at_ms':at,'text':user_text,'event_id':item['id'],'kind':'user'})
            if delivered_text is not None:segments.append({'id':item['id']+':assistant','at_ms':at,'text':delivered_text,'event_id':item['id'],'kind':'assistant'})
        first_turn_event=next(e for _,_,e in selected if e['event']=='turn_started' and e['data']['id']==rid)
        round['timeline']={'logical_turn_id':'r7-conflict-low' if rid=='r7-refresh-low' else rid,'view_turn_id':rid,'origin_mono_ns':str(origin),'origin_wall_ns':str(first_turn_event['wall_ns']),'wall_origin_note':'turn_started日志时刻，非用户键盘输入时刻。','time_origin':'turn.started_ns','duration_ms':max(round.get('full_loop_ms') or 0,events[-1]['at_ms']),'reported_loop_ms':round.get('full_loop_ms'),'stream_capture':'not_recorded','token_stream_available':False,'stream_kind':'recorded_coordinator_events','events':events,'segments':segments,'note':'按日志记录时间回放。候选完整到达前无token记录；本地接受不证明客户端已经呈现。'}
        # Fix the earlier substring-based module logs using exact event/job ownership.
        for node in round.get('nodes',[]):
            nid=node['id'];kind={'plan':'planner','decide':'decision','reflect':'reflection','memory':'memory'}.get(nid)
            if nid=='generate':owned={turn.get('job_id')}
            elif nid=='refresh_reply':owned={'r7-refresh-low-model'}
            elif kind:owned={j for j in jids if jobs[j]['kind']==kind}
            else:owned=set()
            filtered=[]
            for item in events:
                use=item['job_id'] in owned if owned else False
                if nid=='input':use=item['type'] in {'input','state','preference'}
                if nid=='route':use=item['raw_type']=='turn_started' and item['turn_id']==rid
                if nid=='gate':use=item['raw_type'] in {'model_delivery_gate','local_delivery','silence_selected'}
                if nid=='generate' and not turn.get('job_id'):use=item['raw_type'] in {'local_delivery','silence_selected'} and item['turn_id']==rid
                if use:filtered.append({**item['raw_event'],'relative_ms':item['at_ms'],'wall_time_shanghai':item['wall_time'],'source_line':item['source_line']})
            node['logs']=filtered
    report['recording']={'event_count':len(records),'mapped_event_count':len(all_selected),'source':'run-03/events.jsonl','token_stream_available':False,'delta_count':None,'api_ttft_ms':None,'client_visible_ms':None,'raw_download_preserves_source_lines':True,'global_events':[safe_ns(e) for _,_,e in records if e['event'] in {'experiment_started','experiment_completed'}]}
    return report

if __name__=='__main__':
    path=HERE/'report-data.json';result=enrich(json.loads(path.read_text()));path.write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps({'rounds':len(result['rounds']),'events':result['recording']['event_count']}))
