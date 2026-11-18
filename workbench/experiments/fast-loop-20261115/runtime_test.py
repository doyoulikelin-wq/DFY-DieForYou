"""Business-boundary tests. Async delays here are fault injection, not model timing."""

import asyncio
from copy import deepcopy
import unittest

from runtime import FastRuntime


def snapshot(observation_id="obs-1", **changes):
    value = {
        "observation_id": observation_id,
        "player": {"race": "human", "class": "mage", "level": 1, "zone": "start",
                   "hp": 100, "max_hp": 100, "mana": 100, "max_mana": 100, "in_combat": False},
        "target": None, "quest_offer": None, "quest_log": [], "known_spell": None,
        "unknown": ["target", "nearby_npcs"],
    }
    value.update(changes)
    return value


def candidate(action="OBSERVE_SURROUNDINGS", observation_id="obs-1", **changes):
    value = {"action_id": action, "template_id": "default", "evidence_ids": [observation_id],
             "needs_deep_work": False}
    value.update(changes)
    return value


class RuntimeBoundaries(unittest.TestCase):
    def test_only_reviewed_templates_are_delivered(self):
        runtime = FastRuntime(snapshot())
        for template in ("default", "curious"):
            reply = runtime.deliver(candidate(template_id=template, reply="invented dangerous instruction"), 1)
            self.assertTrue(reply["accepted"])
            self.assertEqual(reply["reply"], "先看看附近有没有人或醒目的标记，告诉我你看到了什么，好吗？")
        self.assertFalse(runtime.deliver(candidate(template_id="invented"), 1)["accepted"])
        self.assertFalse(runtime.deliver(candidate("INVENTED_ACTION"), 1)["accepted"])

    def test_accept_button_disappears(self):
        state = snapshot(quest_offer={"title": "First Steps", "open": True, "buttons": ["接受", "拒绝"]})
        runtime = FastRuntime(state)
        response = runtime.deliver(candidate("ACCEPT_CURRENT_QUEST"), 1)
        self.assertTrue(response["accepted"])
        self.assertEqual(response["reply"], "点“接受”就好呀。")
        state["quest_offer"]["buttons"] = ["关闭"]
        state["observation_id"] = "obs-2"
        runtime.replace_state(state)
        self.assertEqual(runtime.deliver(candidate("ACCEPT_CURRENT_QUEST"), 1)["reason"], "state_version_mismatch")
        response = runtime.deliver(candidate("ACCEPT_CURRENT_QUEST", "obs-2"), 2)
        self.assertEqual(response["reason"], "quest_accept_unavailable")
        self.assertEqual(response["reply"], "")

    def test_closed_quest_window_rejects_accept(self):
        runtime = FastRuntime(snapshot(quest_offer={"title": "First Steps", "open": False, "buttons": ["接受"]}))
        self.assertEqual(runtime.deliver(candidate("ACCEPT_CURRENT_QUEST"), 1)["reason"], "quest_accept_unavailable")

    def test_combat_blocks_both_old_and_current_observation_suggestion(self):
        state = snapshot()
        runtime = FastRuntime(state)
        old = runtime.capture()
        state["player"]["in_combat"] = True
        state["observation_id"] = "obs-2"
        runtime.replace_state(state)
        self.assertEqual(runtime.deliver(candidate(), old["state_version"])["reason"], "state_version_mismatch")
        self.assertEqual(runtime.deliver(candidate(observation_id="obs-2"), 2)["reason"], "observation_not_allowed_in_combat")

    def test_known_target_or_absent_unknown_information_blocks_observe(self):
        for state in (snapshot(target={"name": "Guide", "hostile": False}), snapshot(unknown=[])):
            with self.subTest(state=state):
                self.assertFalse(FastRuntime(state).deliver(candidate(), 1)["accepted"])

    def test_no_mana_rule_requires_exact_evidence_and_spell_state(self):
        state = snapshot(known_spell={"name": "寒冰箭", "usable": False, "reason": "法力不足"})
        state["player"].update(in_combat=True, mana=0)
        response = FastRuntime(state).deliver(candidate("AVOID_UNUSABLE_SPELL"), 1)
        self.assertTrue(response["accepted"])
        self.assertEqual(response["reply"], "蓝用完啦，先别施放寒冰箭。")
        for evidence in ([], ["another-observation"], "obs-1", None):
            with self.subTest(evidence=evidence):
                response = FastRuntime(state).deliver(candidate("AVOID_UNUSABLE_SPELL", evidence_ids=evidence), 1)
                self.assertFalse(response["accepted"])
        variants = []
        for field, value in (("usable", True), ("reason", "冷却中"), ("name", "")):
            changed = deepcopy(state)
            changed["known_spell"][field] = value
            variants.append(changed)
        for field, value in (("mana", 1), ("in_combat", False), ("mana", False)):
            changed = deepcopy(state)
            changed["player"][field] = value
            variants.append(changed)
        variants.append({**state, "known_spell": None})
        for changed in variants:
            with self.subTest(state=changed):
                self.assertFalse(FastRuntime(changed).deliver(candidate("AVOID_UNUSABLE_SPELL"), 1)["accepted"])

    def test_silence_still_requires_current_evidence(self):
        runtime = FastRuntime(snapshot())
        self.assertTrue(runtime.deliver(candidate("STAY_SILENT"), 1)["accepted"])
        self.assertEqual(runtime.deliver(candidate("STAY_SILENT"), 1)["reply"], "")
        self.assertFalse(runtime.deliver(candidate("STAY_SILENT", evidence_ids=[]), 1)["accepted"])

    def test_explicit_mute_wins_even_if_candidate_was_prepared_before_it(self):
        runtime = FastRuntime(snapshot())
        captured = runtime.capture()
        runtime.apply_explicit_preference("先别说话", {"muted": True})
        response = runtime.deliver(candidate(reply="model says keep talking"), captured["state_version"])
        self.assertEqual(response["reason"], "explicitly_muted")
        self.assertEqual(response["reply"], "")
        self.assertFalse(response["accepted"])

    def test_stale_memory_cannot_overwrite_new_explicit_preference(self):
        runtime = FastRuntime(snapshot())
        runtime.apply_explicit_preference("多给些建议", {"muted": False})
        old = runtime.capture()
        runtime.apply_explicit_preference("先别说话", {"muted": True})
        result = runtime.commit_memory({"base_memory_version": old["memory_version"], "preference": {
            "text": "User likes frequent guidance", "source_quote": "多给些建议",
            "value": {"muted": False}, "scope": "future_guidance"}})
        self.assertEqual(result["reason"], "memory_version_mismatch")
        self.assertEqual(runtime.capture()["explicit_preference"]["value"], {"muted": True})

    def test_even_current_memory_cannot_conflict_with_explicit_preference(self):
        runtime = FastRuntime(snapshot())
        runtime.apply_explicit_preference("先别说话", {"muted": True})
        result = runtime.commit_memory({"base_memory_version": 1, "preference": {
            "text": "Keep talking", "source_quote": "先别说话",
            "value": {"muted": False}, "scope": "future_guidance"}})
        self.assertEqual(result["reason"], "explicit_preference_conflict")
        self.assertEqual(runtime.memory_version, 1)

    def test_one_step_cannot_become_every_time(self):
        runtime = FastRuntime(snapshot())
        runtime.apply_explicit_preference("先教我一步", {"steps": 1}, scope="current_step")
        preference = {"text": "Always give just one step", "source_quote": "先教我一步",
                      "value": {"steps": 1}, "scope": "future_guidance"}
        self.assertEqual(runtime.commit_memory({"base_memory_version": 1, "preference": preference})["reason"], "scope_expansion")
        preference["scope"] = "current_step"
        self.assertTrue(runtime.commit_memory({"base_memory_version": 1, "preference": preference})["accepted"])
        self.assertEqual(runtime.capture()["explicit_preference"]["scope"], "current_step")

    def test_memory_requires_exact_user_source_and_proposals_are_inactive(self):
        runtime = FastRuntime(snapshot())
        runtime.set_allowed_quotes(["先教我一步"])
        base = {"text": "Possible preference", "value": {"steps": 1}, "scope": "proposal"}
        self.assertEqual(runtime.commit_memory({"base_memory_version": 0, "preference": base})["reason"], "missing_source_quote")
        base["source_quote"] = "made up quote"
        self.assertEqual(runtime.commit_memory({"base_memory_version": 0, "preference": base})["reason"], "unverified_source_quote")
        base["source_quote"] = "先教我一步"
        self.assertEqual(runtime.commit_memory({"base_memory_version": 0, "preference": base})["reason"], "proposal_recorded")
        self.assertIsNone(runtime.capture()["explicit_preference"])
        self.assertEqual(runtime.memory_records[0]["scope"], "proposal")

    def test_capture_and_input_mutations_do_not_leak(self):
        state = snapshot()
        runtime = FastRuntime(state)
        preference = {"muted": False, "nested": {"steps": [1]}}
        runtime.apply_explicit_preference("先教我一步", preference, "current_step")
        message = runtime.capture()
        state["player"]["mana"] = 999
        preference["nested"]["steps"].append(2)
        message["snapshot"]["player"]["mana"] = -1
        message["snapshot"]["unknown"].clear()
        message["explicit_preference"]["value"]["muted"] = True
        fresh = runtime.capture()
        self.assertEqual(fresh["snapshot"]["player"]["mana"], 100)
        self.assertEqual(fresh["snapshot"]["unknown"], ["target", "nearby_npcs"])
        self.assertEqual(fresh["explicit_preference"]["value"], {"muted": False, "nested": {"steps": [1]}})
        runtime.replace_state(snapshot("obs-2"))
        self.assertEqual(message["snapshot"]["observation_id"], "obs-1")


class ConcurrencyBoundaries(unittest.IsolatedAsyncioTestCase):
    async def test_pending_background_work_does_not_block_foreground_and_late_results_are_rejected(self):
        runtime = FastRuntime(snapshot())
        old_message = runtime.capture()
        started = asyncio.Event()
        release = asyncio.Event()
        events = []

        async def injected_background_work(message):
            # Explicit scheduling fault injection, not a model call or latency sample.
            started.set()
            await release.wait()
            events.append("background_finished")
            return candidate(), {"base_memory_version": message["memory_version"], "preference": {
                "text": "More advice", "source_quote": "多给些建议",
                "value": {"muted": False}, "scope": "future_guidance"}}

        task = asyncio.create_task(injected_background_work(old_message))
        try:
            await asyncio.wait_for(started.wait(), 1)
            state = snapshot("obs-2", known_spell={"name": "寒冰箭", "usable": False, "reason": "法力不足"})
            state["player"].update(in_combat=True, mana=0)
            runtime.replace_state(state)
            response = runtime.deliver(candidate("AVOID_UNUSABLE_SPELL", "obs-2"), 2)
            events.append("foreground_delivered")
            self.assertTrue(response["accepted"])
            self.assertFalse(task.done())
            runtime.apply_explicit_preference("先别说话", {"muted": True})
            release.set()
            old_candidate, old_patch = await asyncio.wait_for(task, 1)
            self.assertEqual(events, ["foreground_delivered", "background_finished"])
            self.assertEqual(runtime.deliver(old_candidate, old_message["state_version"])["reason"], "state_version_mismatch")
            self.assertEqual(runtime.commit_memory(old_patch)["reason"], "memory_version_mismatch")
            self.assertEqual(runtime.capture()["explicit_preference"]["value"], {"muted": True})
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass


if __name__ == "__main__":
    unittest.main(verbosity=2)
