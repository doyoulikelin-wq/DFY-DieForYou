"""Focused v3 regressions for snapshot provenance and explicit preference updates.

Run: python -m unittest discover -s experiments/natural-loop-20261117 \
    -p 'runtime_v3_test.py' -v
Synthetic user messages in these tests are test inputs, not inferred user history.
"""

from copy import deepcopy
import json
from pathlib import Path
import unittest

from runtime_v3 import CompanionRuntime


def update(value, quote, scope="current_turn"):
    return {"value": value, "scope": scope, "source_quote": quote}


class PreferenceScopeV3Tests(unittest.TestCase):
    def setUp(self):
        fixtures = json.loads(Path(__file__).with_name("fixtures.json").read_text())
        self.fixture = next(case for case in fixtures["cases"]
                            if case["id"] == "temporary_preference_correction")
        self.history = deepcopy(self.fixture["preferences"])

    def fixture_args(self):
        keys = ("user_text", "world", "preferences", "recent_messages", "evidence", "unknowns")
        return {**{key: deepcopy(self.fixture[key]) for key in keys},
                "turn_id": self.fixture["id"]}

    def test_original_fixture_snapshot_stays_session_across_turns(self):
        runtime = CompanionRuntime()
        first = runtime.begin_turn(**self.fixture_args())
        self.assertEqual(first["preferences"], self.history)
        state = runtime.snapshot()
        self.assertEqual(state["session_preferences"], self.history)
        self.assertEqual(state["current_turn_preferences"], {})
        # Provenance is intentionally checked: no historical verbatim quote is
        # available in this fixture, so the current user text cannot replace it.
        self.assertTrue(runtime._session_origins)
        self.assertTrue(all(origin["source_quote"] == ""
                            for origin in runtime._session_origins.values()))
        second = runtime.begin_turn("继续。", turn_id="next")
        self.assertEqual(second["preferences"], self.history)

    def test_explicit_current_turn_short_overlay_expires_to_history(self):
        runtime = CompanionRuntime()
        short = {"response_detail": "本次回答简短"}
        first = runtime.begin_turn(**self.fixture_args(), preference_updates=[
            update(short, self.fixture["user_text"]),
        ])
        self.assertEqual(first["preferences"]["response_detail"], "本次回答简短")
        self.assertEqual(runtime.snapshot()["session_preferences"], self.history)
        self.assertEqual(runtime.snapshot()["current_turn_preferences"], short)
        second = runtime.begin_turn("继续。", turn_id="next")
        self.assertEqual(second["preferences"], self.history)
        self.assertEqual(runtime.snapshot()["current_turn_preferences"], {})

    def test_old_snapshots_cannot_rollback_explicit_session_preferences(self):
        runtime = CompanionRuntime()
        runtime.begin_turn(**self.fixture_args())
        quote = "以后先说结论，再解释原因。"
        new_value = {"response_detail": "先结论后原因"}
        runtime.begin_turn(quote, preference_updates=[update(new_value, quote, "session")])
        replay = runtime.begin_turn("继续。", preferences=deepcopy(self.history))
        self.assertEqual(replay["preferences"]["response_detail"], new_value["response_detail"])
        # Initialization also must not replace an explicit session preference
        # already established before the first nonempty snapshot arrives.
        existing = CompanionRuntime()
        existing.begin_turn(quote, preference_updates=[update(new_value, quote, "session")])
        first_snapshot = existing.begin_turn("继续。", preferences=deepcopy(self.history))
        self.assertEqual(first_snapshot["preferences"]["response_detail"], new_value["response_detail"])

    def test_forged_source_rejected_without_changing_epoch_or_state(self):
        runtime = CompanionRuntime({"location": "camp"})
        runtime.begin_turn("在这里等等。", turn_id="before")
        before = runtime.snapshot()
        with self.assertRaises((ValueError, TypeError)):
            runtime.begin_turn("继续。", world={"location": "forest"},
                               preferences=deepcopy(self.history), turn_id="rejected",
                               preference_updates=[update({"max_chars": 4}, "从未观察过的用户原话")])
        self.assertEqual(runtime.snapshot(), before)

    def test_batch_prevalidation_is_atomic_after_a_valid_first_update(self):
        runtime = CompanionRuntime({"location": "camp"})
        runtime.begin_turn("这次简短。", preference_updates=[
            update({"max_chars": 8}, "这次简短。"),
        ])
        before = runtime.snapshot()
        current = "以后稍微详细一点。"
        with self.assertRaises((ValueError, TypeError)):
            runtime.begin_turn(current, world={"location": "forest"},
                               preference_updates=[
                                   update({"max_chars": 80}, current, "session"),
                                   update({"response_detail": "伪造"}, "没有看见过的来源", "session"),
                               ])
        self.assertEqual(runtime.snapshot(), before)
        self.assertEqual(runtime.snapshot()["current_turn_preferences"], {"max_chars": 8})

    def test_new_current_update_is_captured_before_gate(self):
        runtime = CompanionRuntime()
        quote = "这次最多四个字。"
        packet = runtime.begin_turn(quote, preference_updates=[update({"max_chars": 4}, quote)])
        self.assertEqual(packet["preferences"]["max_chars"], 4)
        self.assertEqual(packet["preference_version"], runtime.snapshot()["preference_version"])
        captured = runtime.capture(packet, "fast")
        accepted = runtime.gate(captured, {"utterance": "先交任务", "evidence_refs": []})
        self.assertTrue(accepted["accepted"])
        rejected = runtime.gate(captured, {"utterance": "现在先交任务", "evidence_refs": []})
        self.assertEqual(rejected["reason"], "max_chars_exceeded")

    def test_session_updates_apply_before_current_turn_regardless_of_list_order(self):
        runtime = CompanionRuntime()
        history_quote = "以后最多八十个字。"
        runtime.begin_turn(history_quote)
        current_quote = "这次最多四个字。"
        packet = runtime.begin_turn(current_quote, preference_updates=[
            update({"max_chars": 4}, current_quote, "current_turn"),
            update({"max_chars": 80}, history_quote, "session"),
        ])
        self.assertEqual(packet["preferences"]["max_chars"], 4)
        self.assertEqual(runtime.snapshot()["session_preferences"]["max_chars"], 80)
        self.assertEqual(runtime.begin_turn("继续。")["preferences"]["max_chars"], 80)

    def test_real_history_is_allowed_but_empty_and_proactive_sources_are_not(self):
        runtime = CompanionRuntime()
        observed = "以后最多六十个字。"
        runtime.begin_turn(observed)
        packet = runtime.begin_turn("继续。", preference_updates=[update({"max_chars": 60}, observed, "session")])
        self.assertEqual(packet["preferences"]["max_chars"], 60)
        recent_quote = "以后最多五十个字。"
        packet = runtime.begin_turn("按之前说的。", recent_messages=[
            {"role": "user", "content": recent_quote},
        ], preference_updates=[update({"max_chars": 50}, recent_quote, "session")])
        self.assertEqual(packet["preferences"]["max_chars"], 50)
        before = runtime.snapshot()
        for quote, proactive in (("", False), ("自动生成的提醒", True)):
            with self.subTest(quote=quote, proactive=proactive):
                with self.assertRaises((ValueError, TypeError)):
                    runtime.begin_turn("自动生成的提醒", proactive=proactive,
                                       preference_updates=[update({"max_chars": 2}, quote)])
                self.assertEqual(runtime.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
