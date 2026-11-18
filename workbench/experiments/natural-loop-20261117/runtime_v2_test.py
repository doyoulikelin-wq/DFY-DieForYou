"""Behavioral tests for the coordinator, not a language-quality benchmark.

Run: python -m unittest discover -s experiments/natural-loop-20261117 \
    -p 'runtime_v2_test.py' -v
"""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import unittest

from runtime_v2 import CompanionRuntime


QUEST = {
    "quest_dialog_open": True, "can_accept": True, "in_combat": False,
    "has_choice": False, "has_cost": False, "custom_conditions_known": True,
}
MANA = {
    "in_combat": True, "mana": 0, "spell_mana_cost": 10,
    "spell_unusable_reason": "insufficient_mana",
}
EVIDENCE = [{"id": "obs-1", "source": "world", "details": {"visible": True}}]


def candidate(text="我先陪你看看。", **kwargs):
    return {"utterance": text, "evidence_refs": ["obs-1"], **kwargs}


class CompanionRuntimeTests(unittest.TestCase):
    def test_detached_worker_packets_inputs_memory_and_debug(self):
        world = {"nested": {"values": [1]}}
        evidence = deepcopy(EVIDENCE)
        runtime = CompanionRuntime(world)
        packet = runtime.begin_turn("记住这句话", evidence=evidence,
                                    preferences={"voice": {"speed": 1}})
        fast, slow = runtime.capture(packet), runtime.capture(packet, "slow")
        world["nested"]["values"].append(9)
        evidence[0]["details"]["visible"] = False
        fast["world"]["nested"]["values"].append(2)
        fast["preferences"]["voice"]["speed"] = 3
        fast["evidence"][0]["details"]["visible"] = False
        self.assertEqual(slow["world"]["nested"]["values"], [1])
        self.assertTrue(slow["evidence"][0]["details"]["visible"])
        snapshot = runtime.snapshot()
        snapshot["world"]["nested"]["values"].append(8)
        self.assertEqual(runtime.snapshot()["world"]["nested"]["values"], [1])
        record = {"source_quote": "记住这句话", "scope": "session", "value": {"tag": ["original"]}}
        self.assertTrue(runtime.commit_memory(0, record)["accepted"])
        record["value"]["tag"].append("changed")
        saved = runtime.memory_records
        saved[0]["value"]["tag"].append("changed_again")
        self.assertEqual(runtime.memory_records[0]["value"]["tag"], ["original"])

    def test_only_changed_fields_receive_versions_including_type_changes(self):
        runtime = CompanionRuntime({"mana": 0, "nested": {"flag": True}})
        initial = runtime.snapshot()["state_dependency_versions"]
        self.assertEqual(runtime.set_state({"mana": 0}), initial)
        changed = runtime.set_state({"mana": 1})
        self.assertEqual(changed["mana"], initial["mana"] + 1)
        self.assertEqual(changed["nested"], initial["nested"])
        typed = runtime.set_state({"nested": {"flag": 1}})
        self.assertEqual(typed["nested"], initial["nested"] + 1)

    def test_exact_user_authorization_and_no_scenario_label_routing(self):
        runtime = CompanionRuntime(QUEST)
        packet = runtime.begin_turn("帮我接一下这个任务。")
        self.assertEqual(runtime.route(packet)["action_id"], "ACCEPT_CURRENT_QUEST")
        for text in ("这个任务值得接吗？", "先别接这个任务", "如果接这个任务会怎样？", "quest_accept_safe"):
            with self.subTest(text=text):
                packet = runtime.begin_turn(text)
                self.assertEqual(runtime.route(packet)["route"], "model")
                result = runtime.gate(packet, {
                    "utterance": "点接受。", "evidence_refs": [],
                    "action_id": "ACCEPT_CURRENT_QUEST",
                })
                self.assertFalse(result["accepted"])

    def test_quest_window_combat_choices_cost_and_unknown_conditions(self):
        unsafe_values = {
            "quest_dialog_open": False, "can_accept": False, "in_combat": True,
            "has_choice": True, "has_cost": True, "custom_conditions_known": False,
        }
        for field, unsafe in unsafe_values.items():
            for missing in (False, True):
                with self.subTest(field=field, missing=missing):
                    world = dict(QUEST)
                    if missing:
                        world.pop(field)
                    else:
                        world[field] = unsafe
                    runtime = CompanionRuntime(world)
                    packet = runtime.begin_turn("接这个任务")
                    self.assertEqual(runtime.route(packet)["route"], "model")
                    self.assertFalse(runtime.gate(packet, {
                        "utterance": "点接受。", "evidence_refs": [],
                        "action_id": "ACCEPT_CURRENT_QUEST",
                    })["accepted"])

    def test_new_observation_replaces_world_so_missing_fields_stay_unknown(self):
        runtime = CompanionRuntime(QUEST)
        runtime.begin_turn("接这个任务")
        incomplete = {"quest_dialog_open": True}
        packet = runtime.begin_turn("接这个任务", world=incomplete)
        self.assertEqual(packet["world"], incomplete)
        self.assertEqual(runtime.route(packet)["route"], "model")
        self.assertGreater(packet["state_dependency_versions"]["can_accept"], 1)

    def test_no_mana_skill_needs_all_facts_and_matching_user_question(self):
        runtime = CompanionRuntime(MANA)
        self.assertEqual(runtime.route(runtime.begin_turn("技能怎么放不出来？"))["action_id"], "EXPLAIN_NO_MANA")
        worlds = []
        for field in MANA:
            world = dict(MANA)
            world.pop(field)
            worlds.append(world)
        worlds.extend([
            {**MANA, "spell_mana_cost": 0}, {**MANA, "mana": False},
            {**MANA, "in_combat": False},
            {**MANA, "spell_unusable_reason": "out_of_range"},
        ])
        for world in worlds:
            with self.subTest(world=world):
                packet = runtime.begin_turn("技能怎么放不出来？", world=world)
                self.assertEqual(runtime.route(packet)["route"], "model")
        packet = runtime.begin_turn("我有点紧张", world=MANA)
        self.assertEqual(runtime.route(packet)["route"], "model")

    def test_explicit_unknowns_prevent_a_conflicting_skill(self):
        runtime = CompanionRuntime(QUEST)
        packet = runtime.begin_turn("接这个任务", unknowns=["has_cost"])
        self.assertEqual(runtime.route(packet)["route"], "model")
        packet = runtime.begin_turn("技能放不出来", world=MANA,
                                    unknowns=["spell_unusable_reason"])
        self.assertEqual(runtime.route(packet)["route"], "model")

    def test_gate_preserves_text_and_does_not_claim_semantic_fact_verification(self):
        runtime = CompanionRuntime({"mana": 0})
        packet = runtime.begin_turn("聊聊", evidence=EVIDENCE)
        # This deliberately false sentence passes mechanical checks. A valid
        # evidence ID is not proof that a generated claim is true or supported.
        text = "  现在法力是九十九。\n这仍然只是候选文本。  "
        result = runtime.gate(packet, candidate(text))
        self.assertTrue(result["accepted"])
        self.assertEqual(result["reply"], text)
        self.assertGreaterEqual(result["processing_ms"], 0)

    def test_default_dependencies_detect_changed_added_and_removed_state(self):
        for mutation in ({"mana": 1}, {"weather": "rain"}, {"new_field": True}):
            with self.subTest(mutation=mutation):
                runtime = CompanionRuntime({"mana": 0, "weather": "sun"})
                packet = runtime.begin_turn("聊聊", evidence=EVIDENCE)
                runtime.set_state(mutation)
                self.assertEqual(runtime.gate(packet, candidate())["reason"], "state_dependency_mismatch")
        runtime = CompanionRuntime({"mana": 0, "weather": "sun"})
        packet = runtime.begin_turn("聊聊", turn_id="t", evidence=EVIDENCE)
        runtime.begin_turn("聊聊", turn_id="t", world={"mana": 0})
        self.assertEqual(runtime.gate(packet, candidate())["reason"], "state_dependency_mismatch")

    def test_trusted_dependency_declaration_ignores_unrelated_change(self):
        runtime = CompanionRuntime({**MANA, "weather": "sun"})
        packet = runtime.begin_turn("技能放不出来", evidence=EVIDENCE,
                                    needed_fields=sorted(runtime.MANA_FIELDS))
        output = candidate("现在法力不足。", action_id="EXPLAIN_NO_MANA",
                           dependencies=sorted(runtime.MANA_FIELDS))
        runtime.set_state({"weather": "rain"})
        self.assertTrue(runtime.gate(packet, output)["accepted"])
        runtime.set_state({"mana": 10})
        self.assertEqual(runtime.gate(packet, output)["reason"], "state_dependency_mismatch")

    def test_worker_cannot_narrow_dependencies_or_forge_fresh_versions(self):
        runtime = CompanionRuntime({"mana": 0, "weather": "sun"})
        packet = runtime.begin_turn("聊聊", evidence=EVIDENCE)
        runtime.set_state({"mana": 2})
        self.assertFalse(runtime.gate(packet, candidate(dependencies=[]))["accepted"])
        forged = deepcopy(packet)
        forged["state_dependency_versions"] = runtime.snapshot()["state_dependency_versions"]
        forged["needed_fields"] = []
        self.assertEqual(runtime.gate(forged, candidate())["reason"], "invalid_or_modified_packet")
        with self.assertRaises(ValueError):
            runtime.capture(forged)

    def test_known_action_cannot_omit_necessary_dependencies(self):
        runtime = CompanionRuntime(QUEST)
        packet = runtime.begin_turn("接这个任务", evidence=EVIDENCE, needed_fields=["can_accept"])
        result = runtime.gate(packet, candidate("点接受。", action_id="ACCEPT_CURRENT_QUEST"))
        self.assertEqual(result["reason"], "required_dependency_not_declared")
        packet = runtime.begin_turn("接这个任务", evidence=EVIDENCE)
        result = runtime.gate(packet, candidate("点接受。", action_id="ACCEPT_CURRENT_QUEST", dependencies=[]))
        self.assertEqual(result["reason"], "missing_required_dependencies")
        result = runtime.gate(packet, candidate(dependencies=["imaginary_key"]))
        self.assertEqual(result["reason"], "dependency_not_declared")

    def test_new_user_turn_cancels_old_work_but_same_turn_and_proactive_do_not(self):
        runtime = CompanionRuntime()
        first = runtime.begin_turn("先看看", turn_id="user-1", evidence=EVIDENCE)
        repeated = runtime.begin_turn("先看看", turn_id="user-1", evidence=EVIDENCE)
        proactive = runtime.begin_turn("环境变化", proactive=True, evidence=EVIDENCE)
        self.assertEqual(first["reply_epoch"], repeated["reply_epoch"])
        self.assertEqual(first["reply_epoch"], proactive["reply_epoch"])
        self.assertTrue(runtime.gate(first, candidate())["accepted"])
        runtime.begin_turn("等等，先停下", turn_id="user-2")
        self.assertEqual(runtime.gate(first, candidate())["reason"], "reply_epoch_mismatch")
        with self.assertRaises(ValueError):
            runtime.begin_turn("同编号却是另一句话", turn_id="user-2")

    def test_new_explicit_preference_invalidates_pending_reply_and_persists(self):
        runtime = CompanionRuntime()
        packet = runtime.begin_turn("聊聊", evidence=EVIDENCE)
        runtime.set_preference({"max_chars": 15}, scope="session")
        self.assertEqual(runtime.gate(packet, candidate())["reason"], "preference_version_mismatch")
        self.assertEqual(runtime.begin_turn("再聊聊")["preferences"]["max_chars"], 15)

    def test_current_turn_preference_expires_without_erasing_session_preference(self):
        runtime = CompanionRuntime()
        runtime.set_preference({"max_chars": 80}, "session")
        runtime.begin_turn("这次只说短句")
        runtime.set_preference({"max_chars": 8}, "session", "这次只说短句")
        self.assertEqual(runtime.snapshot()["preferences"]["max_chars"], 8)
        record = {"source_quote": "这次只说短句", "scope": "session", "value": {"max_chars": 8}}
        self.assertEqual(runtime.commit_memory(0, record)["reason"], "scope_expansion")
        record["scope"] = "current_turn"
        self.assertTrue(runtime.commit_memory(0, record)["accepted"])
        packet = runtime.begin_turn("继续聊聊")
        self.assertEqual(packet["preferences"]["max_chars"], 80)
        self.assertEqual(runtime.memory_records[0]["scope"], "current_turn")
        packet = runtime.begin_turn("这次再短点", preferences={"max_chars": 4})
        self.assertEqual(packet["preferences"]["max_chars"], 4)
        self.assertEqual(runtime.begin_turn("接着聊")["preferences"]["max_chars"], 80)
        runtime.begin_turn("回答短点")
        runtime.set_preference({"max_chars": 6}, "current_turn", "回答短点")
        runtime.begin_turn("继续")
        unbounded = {"source_quote": "回答短点", "scope": "session", "value": {"max_chars": 6}}
        self.assertEqual(runtime.commit_memory(1, unbounded)["reason"], "scope_expansion")

    def test_silence_only_blocks_proactive_and_this_time_is_not_permanent(self):
        runtime = CompanionRuntime()
        packet = runtime.begin_turn("这次别主动提醒我", evidence=EVIDENCE)
        self.assertEqual(runtime.route(packet)["route"], "skill")
        self.assertTrue(runtime.gate(packet, candidate("好。"))["accepted"])
        spontaneous = runtime.begin_turn("想提醒一下", proactive=True, evidence=EVIDENCE)
        self.assertEqual(runtime.route(spontaneous)["route"], "silent")
        self.assertEqual(runtime.gate(spontaneous, candidate())["reason"], "proactive_disabled")
        next_packet = runtime.begin_turn("现在这个技能怎么用？", evidence=EVIDENCE)
        self.assertTrue(runtime.gate(next_packet, candidate())["accepted"])
        self.assertNotIn("proactive_allowed", next_packet["preferences"])
        runtime.begin_turn("以后别主动说话")
        runtime.begin_turn("但我问你时可以答")
        self.assertFalse(runtime.snapshot()["preferences"]["proactive_allowed"])

    def test_missing_malformed_and_unknown_references_are_rejected(self):
        runtime = CompanionRuntime()
        packet = runtime.begin_turn("聊聊", evidence=EVIDENCE)
        for output in (
            {"utterance": "好。"}, {"utterance": "好。", "evidence_refs": "obs-1"},
            {"utterance": "好。", "evidence_refs": [None]},
            {"utterance": "好。", "evidence_refs": ["made-up"]},
        ):
            with self.subTest(output=output):
                self.assertFalse(runtime.gate(packet, output)["accepted"])
        self.assertTrue(runtime.gate(packet, {"utterance": "你好。", "evidence_refs": []})["accepted"])
        malformed = runtime.begin_turn("聊聊", evidence={"id": None, "source": "world"})
        output = {"utterance": "好。", "evidence_refs": ["source"]}
        self.assertEqual(runtime.gate(malformed, output)["reason"], "unknown_evidence_ref")

    def test_format_and_max_chars_reject_without_rewriting(self):
        runtime = CompanionRuntime()
        packet = runtime.begin_turn("短一点", preferences={"max_chars": 4}, evidence=EVIDENCE)
        self.assertEqual(runtime.gate(packet, candidate("一二三四五"))["reason"], "max_chars_exceeded")
        self.assertEqual(runtime.gate(packet, candidate("一二三四"))["reply"], "一二三四")
        for text in ("", "   ", None, ["hello"]):
            with self.subTest(text=text):
                self.assertEqual(runtime.gate(packet, candidate(text))["reason"], "invalid_utterance")
        self.assertEqual(runtime.gate(packet, candidate("好", action_id="EXECUTE_ANYTHING"))["reason"], "unknown_action")
        before = runtime.snapshot()
        for invalid in ({"preferences": {"max_chars": 0}}, {"world": {1: True}}, {"unknowns": [{}]}):
            with self.subTest(invalid=invalid), self.assertRaises((ValueError, TypeError)):
                runtime.begin_turn("无效输入", **invalid)
        self.assertEqual(runtime.snapshot(), before)

    def test_duplicate_segment_delivery_is_atomic_and_resets_per_user_turn(self):
        runtime = CompanionRuntime()
        packet = runtime.begin_turn("聊聊", evidence=EVIDENCE)
        output = candidate(segment_id="opening")
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: runtime.gate(packet, output), range(2)))
        self.assertEqual(sum(item["accepted"] for item in results), 1)
        self.assertIn("duplicate_segment", [item["reason"] for item in results])
        next_packet = runtime.begin_turn("继续", evidence=EVIDENCE)
        self.assertTrue(runtime.gate(next_packet, output)["accepted"])

    def test_memory_cas_allows_only_one_concurrent_writer(self):
        runtime = CompanionRuntime()
        runtime.begin_turn("叫我小林")
        record = {"source_quote": "叫我小林", "scope": "session", "value": {"name": "小林"}}
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: runtime.commit_memory(0, record), range(2)))
        self.assertEqual(sum(item["accepted"] for item in results), 1)
        self.assertEqual(runtime.memory_version, 1)
        self.assertEqual(runtime.commit_memory(False, record)["reason"], "memory_version_mismatch")
        self.assertEqual(len(runtime.memory_records), 1)

    def test_memory_quote_must_be_exact_observed_user_text(self):
        runtime = CompanionRuntime()
        runtime.begin_turn("我希望你叫我小林")
        for quote in (None, "", "叫我小林", "用户没说过的话"):
            with self.subTest(quote=quote):
                record = {"source_quote": quote, "scope": "session", "value": {"name": "小林"}}
                self.assertFalse(runtime.commit_memory(0, record)["accepted"])
        runtime.set_preference({"style": "brief"}, source_quote="协调器传入但用户没说过")
        record = {"source_quote": "协调器传入但用户没说过", "scope": "session", "value": {"style": "brief"}}
        self.assertEqual(runtime.commit_memory(0, record)["reason"], "unverified_source_quote")

    def test_late_memory_cannot_override_newer_explicit_preference(self):
        runtime = CompanionRuntime()
        runtime.begin_turn("以后回答详细一点")
        runtime.set_preference({"detail": "long"}, source_quote="以后回答详细一点")
        runtime.begin_turn("改成简短回答")
        runtime.set_preference({"detail": "short"}, source_quote="改成简短回答")
        old = {"source_quote": "以后回答详细一点", "scope": "session", "value": {"detail": "long"}}
        self.assertEqual(runtime.commit_memory(0, old)["reason"], "newer_explicit_preference_conflict")
        new = {"source_quote": "改成简短回答", "scope": "session", "value": {"detail": "short"}}
        self.assertTrue(runtime.commit_memory(0, new)["accepted"])
        self.assertEqual(runtime.snapshot()["preferences"]["detail"], "short")
        # Arbitrary memory content remains a sourced record, not an instruction
        # that can mutate preferences or obtain access to coordinator state.
        record = {"source_quote": "改成简短回答", "scope": "session", "text": "历史备注"}
        self.assertTrue(runtime.commit_memory(1, record)["accepted"])
        self.assertEqual(runtime.snapshot()["preferences"]["detail"], "short")


if __name__ == "__main__":
    unittest.main()
