"""Local experiment coordinator. Synthetic game data; no game or model API.

Real model candidates arrive through explicit per-job HTTP messages from isolated
Sol workers. Timings include collaboration/worker/tool overhead, not API TTFT.
"""
import argparse
import json
import threading
import time
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from runtime_v2 import CompanionRuntime


class Experiment:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        if (self.directory / 'events.jsonl').exists():
            raise RuntimeError('Refusing to overwrite an existing experiment')
        self.lock = threading.RLock()
        self.sessions = {}
        self.jobs = {}
        self.turns = []
        self.event('experiment_started', {
            'synthetic_game': True, 'model_transport': 'isolated_collaboration_workers',
            'direct_api': False, 'token_telemetry': None, 'provider_resolved_model': None,
        })

    def event(self, name, data):
        record = {'event': name, 'wall_ns': time.time_ns(),
                  'mono_ns': time.perf_counter_ns(), 'data': deepcopy(data)}
        with (self.directory / 'events.jsonl').open('a') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
        return record

    def save(self):
        content = {'jobs': list(self.jobs.values()), 'turns': self.turns,
                   'session_states': {k:v.snapshot() for k,v in self.sessions.items()},
                   'direct_api': False, 'api_ttft_ms': None, 'cached_tokens': None,
                   'client_visible_ms': None, 'production_p95_ms': None}
        tmp = self.directory / 'results.json.tmp'
        tmp.write_text(json.dumps(content, ensure_ascii=False, indent=2))
        tmp.replace(self.directory / 'results.json')

    def apply(self, path, data):
        with self.lock:
            if path == '/turn':
                started = time.perf_counter_ns()
                session_id = data.get('session_id', data['id'])
                if session_id not in self.sessions:
                    self.sessions[session_id] = CompanionRuntime()
                runtime = self.sessions[session_id]
                kwargs = {key: data[key] for key in
                          ['user_text','world','preferences','recent_messages','evidence','unknowns','proactive','needed_fields']
                          if key in data}
                kwargs['turn_id'] = data['id']
                packet = runtime.begin_turn(**kwargs)
                route = runtime.route(packet)
                self.event('turn_started', {'id':data['id'],'session_id':session_id,
                                          'packet':packet,'route':route})
                turn = {'id':data['id'],'session_id':session_id,'started_ns':started,
                        'packet':packet,'route':route,'classification':'runtime_selected',
                        'first_useful_ms':None,'api_ttft_ms':None,'client_visible_ms':None}
                self.turns.append(turn)
                if route['route'] == 'skill':
                    candidate = {'utterance':route['reply'],
                                 'evidence_refs':[e['id'] for e in packet.get('evidence',[])],
                                 'segment_id':data['id']+'-1'}
                    gate = runtime.gate(packet, candidate)
                    end = time.perf_counter_ns()
                    turn.update({'candidate':candidate,'gate':gate,
                                 'local_turn_to_gate_ms':(end-started)/1e6,
                                 'foreground_done_ns':end,'full_loop_ms':(end-started)/1e6})
                    self.event('local_delivery', turn)
                elif route['route'] == 'silent':
                    end=time.perf_counter_ns()
                    turn.update({'gate':{'accepted':False,'reason':route.get('reason'),'reply':''},
                                 'foreground_done_ns':end,'full_loop_ms':(end-started)/1e6})
                    self.event('silence_selected',turn)
                else:
                    jid=data.get('job_id',data['id']+'-model')
                    job=self.new_job(jid,'reply',runtime.capture(packet,role=data.get('role','fast')),
                                     session_id,data.get('effort','low'),data['id'])
                    turn['job_id']=jid
                self.save()
                return deepcopy(turn | ({'job':job} if route['route']=='model' else {}))
            if path == '/job':
                job=self.new_job(data['id'],data['kind'],data['packet'],data.get('session_id'),
                                 data.get('effort','low'),data.get('origin_turn'))
                self.save(); return deepcopy(job)
            if path == '/dispatch':
                job=self.jobs[data['id']]
                if job.get('dispatch_ns') is not None:raise ValueError('already dispatched')
                job['dispatch_ns']=time.perf_counter_ns();job['dispatch_wall_ns']=time.time_ns()
                self.event('worker_dispatch_registered',{'id':job['id'],'effort':job['effort']})
                self.save();return deepcopy(job)
            if path == '/result':
                job=self.jobs[data['id']]
                if job.get('received_ns') is not None:raise ValueError('first result already retained')
                received=time.perf_counter_ns()
                job.update({'received_ns':received,'received_wall_ns':time.time_ns(),
                            'candidate':deepcopy(data['candidate']), 'status':'received',
                            'dispatch_to_candidate_ms': (received-job['dispatch_ns'])/1e6
                            if job.get('dispatch_ns') else None})
                self.event('model_candidate_received',{'id':job['id'],'candidate':job['candidate']})
                # Persist the original arrival before coordinator processing.
                # Pass copies onward so even a failing processor cannot rewrite it.
                self.save()
                phase='result_processing'
                try:
                    if job['kind']=='reply':
                        phase='gate'
                        gate=self.sessions[job['session_id']].gate(
                            job['packet'],deepcopy(job['candidate']))
                        phase='reply_recording'
                        end=time.perf_counter_ns();job['gate']=gate;job['gate_done_ns']=end
                        job['dispatch_to_gate_ms']=((end-job['dispatch_ns'])/1e6
                                                    if job.get('dispatch_ns') else None)
                        for turn in self.turns:
                            if turn.get('job_id')==job['id']:
                                turn.update({'candidate':deepcopy(job['candidate']),'gate':gate,'foreground_done_ns':end,
                                             'turn_to_gate_ms':(end-turn['started_ns'])/1e6,
                                             'dispatch_to_gate_ms':job['dispatch_to_gate_ms'],
                                             'full_loop_ms':(end-turn['started_ns'])/1e6})
                        self.event('model_delivery_gate',{'id':job['id'],'gate':gate})
                    elif job['kind']=='memory':
                        phase='memory_commit'
                        candidate=deepcopy(job['candidate'])
                        job['memory_commit']=self.sessions[job['session_id']].commit_memory(
                            candidate['base_version'],candidate['record'])
                        phase='memory_recording'
                        self.event('memory_commit',{'id':job['id'],'result':job['memory_commit']})
                except Exception as exc:
                    error={'phase':phase,'error':type(exc).__name__,'message':str(exc),
                           'failed_ns':time.perf_counter_ns()}
                    job.update({'status':'coordinator_error','coordinator_error':error})
                    for turn in self.turns:
                        if turn.get('job_id')==job['id']:
                            turn.update({'candidate':deepcopy(job['candidate']),
                                         'status':'coordinator_error','coordinator_error':deepcopy(error)})
                    self.event('coordinator_error',{'id':job['id'],'kind':job['kind'],**error})
                finally:
                    self.save()
                return {'received':True,'id':job['id'],'gate':job.get('gate'),
                        'memory_commit':job.get('memory_commit'),
                        'coordinator_error':job.get('coordinator_error')}
            if path == '/state':
                runtime=self.sessions[data['session_id']]
                result=runtime.set_state(data['fields'])
                self.event('state_changed',data);self.save();return {'result':result,'snapshot':runtime.snapshot()}
            if path == '/preference':
                runtime=self.sessions[data['session_id']]
                result=runtime.set_preference(data['value'],scope=data.get('scope','session'),
                                              source_quote=data['source_quote'])
                self.event('preference_changed',data);self.save();return {'result':result,'snapshot':runtime.snapshot()}
            if path == '/mark':
                self.event(data['name'],data.get('data',{}));self.save();return {'recorded':True}
            raise ValueError('unknown route')

    def new_job(self,jid,kind,packet,session_id,effort,origin_turn):
        if jid in self.jobs:raise ValueError('duplicate job')
        job={'id':jid,'kind':kind,'packet':deepcopy(packet),'session_id':session_id,
             'origin_turn':origin_turn,'requested_model':'gpt-6.1-sol','effort':effort,
             'provider_resolved_model':None,'usage':None,'api_ttft_ms':None,
             'status':'pending','created_ns':time.perf_counter_ns()}
        self.jobs[jid]=job;self.event('job_created',job);return job


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--directory',required=True)
    parser.add_argument('--port',type=int,default=8766)
    parser.add_argument('--mailbox', action='store_true');args=parser.parse_args()
    experiment=Experiment(args.directory)
    if args.mailbox:
        incoming=experiment.directory/'inbox';incoming.mkdir(exist_ok=True)
        receipts=experiment.directory/'receipts';receipts.mkdir(exist_ok=True)
        print(json.dumps({'status':'listening','transport':'explicit_file_messages','directory':args.directory}),flush=True)
        while True:
            for request in sorted(incoming.glob('*.json')):
                try:
                    data=json.loads(request.read_text())
                    if data['path']=='/stop':
                        experiment.save();return
                    result=experiment.apply(data['path'],data['data'])
                except Exception as exc:
                    result={'error':type(exc).__name__,'message':str(exc)}
                    experiment.event('coordinator_error', {'request_file':request.name,'error':result})
                    experiment.save()
                receipt=receipts/request.name
                tmp=receipt.with_suffix('.tmp');tmp.write_text(json.dumps(result,ensure_ascii=False));tmp.replace(receipt)
                request.unlink()
            time.sleep(0.01)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            with experiment.lock:
                if self.path == '/status':
                    result={'jobs':list(experiment.jobs.values()),'turns':experiment.turns,
                            'states':{k:v.snapshot() for k,v in experiment.sessions.items()}}
                else: result={'error':'not found'}
                self.respond(result)
        def do_POST(self):
            try:
                size=int(self.headers.get('Content-Length','0'))
                if size>1000000:raise ValueError('request too large')
                data=json.loads(self.rfile.read(size))
                result=experiment.apply(self.path,data);self.respond(result)
            except Exception as exc:
                self.respond({'error':type(exc).__name__,'message':str(exc)},400)
        def respond(self,result,status=200):
            encoded=json.dumps(result,ensure_ascii=False).encode()
            self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Content-Length',str(len(encoded)));self.end_headers();self.wfile.write(encoded)
    print(json.dumps({'status':'listening','url':f'http://127.0.0.1:{args.port}',
                      'directory':args.directory}),flush=True)
    ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()

if __name__=='__main__':main()
