"""Checks that playback cannot invent deliveries or merge unrelated loops."""
import json
from pathlib import Path
import unittest
from timeline import enrich

HERE=Path(__file__).resolve().parent

class RecordedTimelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=enrich(json.loads((HERE/'report-data.json').read_text()))
        cls.rounds={r['id']:r for r in cls.report['rounds']}
        cls.source=(HERE/'run-03/events.jsonl').read_text().splitlines()

    def test_rejected_candidate_never_becomes_delivery(self):
        t=self.rounds['r9-stale-reply']['timeline']
        self.assertTrue(any(e['type']=='candidate' for e in t['events']))
        self.assertFalse(any(s['kind']=='assistant' for s in t['segments']))
        self.assertTrue(any(e['raw_type']=='model_delivery_gate' and e['payload']['gate']['accepted'] is False for e in t['events']))

    def test_refresh_is_continuation_not_second_user_message(self):
        t=self.rounds['r7-conflict-low']['timeline']
        self.assertEqual(len([s for s in t['segments'] if s['kind']=='user']),1)
        self.assertEqual(len([s for s in t['segments'] if s['kind']=='assistant']),2)
        self.assertEqual({e['job_id'] for e in t['events'] if e['job_id']},{'r7-conflict-low-model','r7-refresh-low-model'})

    def test_background_has_new_user_input_and_no_spoken_reflection(self):
        t=self.rounds['r10-background']['timeline']
        self.assertEqual([s['text'] for s in t['segments'] if s['kind']=='user'],['以后不要主动提醒','以后可以主动提醒我'])
        self.assertEqual(len([s for s in t['segments'] if s['kind']=='assistant']),1)
        self.assertEqual(t['events'][-1]['raw_type'],'memory_commit')
        self.assertEqual(t['events'][-1]['payload']['result']['reason'],'newer_explicit_preference_conflict')

    def test_shared_session_does_not_merge_different_turns(self):
        for rid in ['s3-mute','s4-muted-proactive']:
            events=self.rounds[rid]['timeline']['events']
            self.assertEqual({e['turn_id'] for e in events},{rid})

    def test_background_jobs_link_by_origin_even_without_session(self):
        t=self.rounds['r8-complex-low']['timeline']
        self.assertEqual({e['job_id'] for e in t['events'] if e['job_id']},{'r8-complex-low-model','r8-planner-medium','r8-decision-low'})

    def test_raw_download_and_nanoseconds_preserve_source(self):
        for r in self.rounds.values():
            origin=int(r['timeline']['origin_mono_ns'])
            for e in r['timeline']['events']:
                self.assertEqual(e['raw_line'],self.source[e['source_line']-1])
                original=json.loads(e['raw_line'])
                self.assertEqual(e['raw_event']['wall_ns'],str(original['wall_ns']))
                self.assertAlmostEqual(e['at_ms'],(original['mono_ns']-origin)/1e6,places=8)

    def test_real_coordination_gap_and_missing_token_stream_remain_visible(self):
        t=self.rounds['r10-background']['timeline']
        reflection=next(e for e in t['events'] if e['raw_type']=='model_candidate_received' and e['job_id']=='r10-reflection-high')
        memory=next(e for e in t['events'] if e['raw_type']=='worker_dispatch_registered' and e['job_id']=='r10-memory-low')
        self.assertGreater(memory['at_ms']-reflection['at_ms'],50000)
        self.assertFalse(t['token_stream_available'])
        self.assertIsNone(self.report['recording']['delta_count'])
        self.assertTrue(all('delta' not in e['raw_type'] for e in t['events']))

if __name__=='__main__':unittest.main()
