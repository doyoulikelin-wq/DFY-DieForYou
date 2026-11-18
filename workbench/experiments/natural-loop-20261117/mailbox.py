"""Explicit message transport for the experiment; no cross-agent reads.

Used by the coordinator operator. Business workers write only their own result
message to the inbox; the prompt supplies their complete authorized input packet.
"""
import json
import time
import uuid
from pathlib import Path

RUN=Path(__file__).parent/'run-03'

def send(path,data,wait=True):
    request_id=f'{time.time_ns()}-{uuid.uuid4().hex}.json'
    incoming=RUN/'inbox'/request_id
    tmp=incoming.with_suffix('.tmp')
    tmp.write_text(json.dumps({'path':path,'data':data},ensure_ascii=False))
    tmp.replace(incoming)
    if not wait:return request_id
    receipt=RUN/'receipts'/request_id
    deadline=time.monotonic()+15
    while not receipt.exists():
        if time.monotonic()>deadline:raise TimeoutError('coordinator did not acknowledge message')
        time.sleep(.01)
    result=json.loads(receipt.read_text())
    if 'error' in result:raise RuntimeError(result)
    return result
