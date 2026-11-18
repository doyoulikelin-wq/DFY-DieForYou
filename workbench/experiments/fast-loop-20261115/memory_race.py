"""Actual delayed model result checked against a newer explicit preference.

The preference is changed only after the root reports the worker was spawned.
No artificial model time is inserted. The model sees only the old message.
"""
import json,time,sys
from pathlib import Path
from runtime import FastRuntime
from driver import SNAPS,write,now
P=Path(__file__).resolve().parent
if sys.argv[1]=='watch':
    if any((P/name).exists() for name in ['memory_race_spawned.json','memory_race_result.json','outbox/memory_race.json']):
        raise SystemExit('Existing race records detected. Use a fresh run directory; do not overwrite history.')
    rt=FastRuntime(SNAPS['R2']);rt.set_allowed_quotes(['先教我一步'])
    job={'id':'memory_race','role':'memory','effort':'medium','requested_model':'gpt-6.1-sol','kind':'memory_concurrency_probe','round':'R2','input_messages':[{'id':'OLD-PREFERENCE','from':'simulated_user','body':{'source_quote':'先教我一步','base_memory_version':0,'scope':'current_turn'}}],'token_usage':None,'dispatch_unix_ms':now()}
    write(P/'jobs/memory_race.json',job)
    write(P/'inputs/memory_race.json',job)
    while not (P/'memory_race_spawned.json').exists():time.sleep(.005)
    rt.apply_explicit_preference('以后每次只说一步',{'max_steps':1},'future_guidance');changed=now()
    write(P/'memory_race_changed.json',{'changed_unix_ms':changed,'state':rt.capture()})
    while not (P/'outbox/memory_race.json').exists():time.sleep(.005)
    while True:
        try:raw=json.loads((P/'outbox/memory_race.json').read_text());break
        except json.JSONDecodeError:time.sleep(.005)
    commit=rt.commit_memory(raw['result']);done=now()
    job.update(output=raw['result'],completed_unix_ms=raw['completed_unix_ms'],collected_unix_ms=done,duration_ms=raw['completed_unix_ms']-job['dispatch_unix_ms'],status='completed',issues=[],commit_result=commit)
    write(P/'collected/memory_race.json',job)
    overlap=changed<raw['completed_unix_ms']
    proof={'job_id':'memory_race','new_preference_unix_ms':changed,'model_completed_unix_ms':raw['completed_unix_ms'],'new_preference_arrived_before_model_result':overlap,'commit_result':commit,'final_state':rt.capture(),'scope':'模型结果生成之前收到新偏好，提交旧补丁时检查版本。' if overlap else '模型结果已经生成、尚未提交时收到新偏好；本次验证提交时的版本冲突，未观察到模型计算期间的偏好更新。'}
    write(P/'memory_race_result.json',proof);print(json.dumps(proof,ensure_ascii=False),flush=True)
elif sys.argv[1]=='spawned':write(P/'memory_race_spawned.json',{'spawn_ack_recorded_unix_ms':now()})
