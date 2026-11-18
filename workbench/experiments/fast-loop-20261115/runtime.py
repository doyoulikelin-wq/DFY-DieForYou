"""Deterministic coordinator for the fast-loop experiment; no model calls.

Each capture is an isolated JSON-compatible message. Only this coordinator owns
live state: messages cannot mutate it, and version checks reject stale work.
processing_ms measures this local gate only, never model or network latency.
"""

from copy import deepcopy
from threading import RLock
from time import perf_counter


class FastRuntime:
    ACTIONS = {
        "OBSERVE_SURROUNDINGS", "ACCEPT_CURRENT_QUEST",
        "AVOID_UNUSABLE_SPELL", "STAY_SILENT",
    }
    TEMPLATES = {"default", "curious"}
    # Structured field identifiers only; this is not a natural-language classifier.
    UNKNOWN_TARGET_FIELDS = {
        "target", "target.name", "npc", "npcs", "nearby_npc", "nearby_npcs",
        "nearby_entities", "target_or_npc", "surroundings",
    }
    CURRENT_ONLY_QUOTES = {"先教我一步", "先教我一步吧", "先教我一步就好"}
    CURRENT_SCOPES = {"current_step", "current_turn", "current_guidance"}
    SCOPES = CURRENT_SCOPES | {"future_guidance", "proposal"}

    def __init__(self, snapshot: dict, state_version: int = 1):
        if not isinstance(snapshot, dict):
            raise TypeError("snapshot must be a dict")
        if type(state_version) is not int or state_version < 1:
            raise ValueError("state_version must be a positive integer")
        self._lock = RLock()
        self._snapshot = deepcopy(snapshot)
        self._state_version = state_version
        self._memory_version = 0
        self._explicit_preference = None
        self._allowed_quotes = set()
        self._memory_records = []

    @property
    def state_version(self):
        with self._lock:
            return self._state_version

    @property
    def memory_version(self):
        with self._lock:
            return self._memory_version

    @property
    def memory_records(self):
        with self._lock:
            return deepcopy(self._memory_records)

    def replace_state(self, snapshot: dict):
        if not isinstance(snapshot, dict):
            raise TypeError("snapshot must be a dict")
        with self._lock:
            self._snapshot = deepcopy(snapshot)
            self._state_version += 1
            return self._state_version

    def apply_explicit_preference(self, text, value, scope="future_guidance"):
        if not isinstance(text, str) or not text.strip():
            raise ValueError("an exact, nonempty user quote is required")
        if not isinstance(value, dict):
            raise TypeError("preference value must be a dict")
        if scope not in self.SCOPES or scope == "proposal":
            raise ValueError("explicit preference requires a supported active scope")
        # This exact instruction cannot authorize a permanent preference.
        if self._current_only(text) and scope == "future_guidance":
            scope = "current_step"
        with self._lock:
            self._memory_version += 1
            self._explicit_preference = deepcopy({
                "text": text, "source_quote": text, "value": value, "scope": scope,
            })
            return self._memory_version

    def set_allowed_quotes(self, quotes: list):
        if not isinstance(quotes, list) or any(
            not isinstance(q, str) or not q.strip() for q in quotes
        ):
            raise ValueError("allowed_quotes must contain nonempty exact user quotes")
        with self._lock:
            self._allowed_quotes = set(quotes)

    def capture(self):
        """Return a detached message; later live changes cannot alter this capture."""
        with self._lock:
            return deepcopy({
                "snapshot": self._snapshot,
                "state_version": self._state_version,
                "memory_version": self._memory_version,
                "explicit_preference": self._explicit_preference,
            })

    @classmethod
    def _current_only(cls, quote):
        return quote.strip().rstrip("。！!？? ") in cls.CURRENT_ONLY_QUOTES

    def deliver(self, candidate: dict, expected_state_version: int):
        started = perf_counter()
        with self._lock:
            action = candidate.get("action_id") if isinstance(candidate, dict) else None

            def result(accepted, reason, reply=""):
                return {
                    "accepted": accepted, "reason": reason, "reply": reply,
                    "action_id": action, "state_version": self._state_version,
                    "processing_ms": (perf_counter() - started) * 1000,
                }

            if type(expected_state_version) is not int or expected_state_version != self._state_version:
                return result(False, "state_version_mismatch")
            pref = self._explicit_preference
            if pref and pref["value"].get("muted") is True:
                return result(False, "explicitly_muted")
            if not isinstance(candidate, dict):
                return result(False, "invalid_candidate")
            if not isinstance(action, str) or action not in self.ACTIONS:
                return result(False, "unknown_action")
            template = candidate.get("template_id", "default")
            if not isinstance(template, str) or template not in self.TEMPLATES:
                return result(False, "unknown_template")
            evidence = candidate.get("evidence_ids")
            observation = self._snapshot.get("observation_id")
            if not isinstance(evidence, list) or not evidence or not observation or observation not in evidence:
                return result(False, "missing_observation_evidence")

            state = self._snapshot
            player = state.get("player") or {}
            if action == "STAY_SILENT":
                return result(True, "accepted")
            if action == "OBSERVE_SURROUNDINGS":
                if player.get("in_combat") is not False:
                    return result(False, "observation_not_allowed_in_combat")
                unknown = state.get("unknown")
                has_unknown = isinstance(unknown, list) and any(
                    isinstance(field, str) and field in self.UNKNOWN_TARGET_FIELDS
                    for field in unknown
                )
                if state.get("target") is not None or not has_unknown:
                    return result(False, "target_information_known")
                return result(True, "accepted", "先看看附近有没有人或醒目的标记，告诉我你看到了什么，好吗？")
            if action == "ACCEPT_CURRENT_QUEST":
                offer = state.get("quest_offer") or {}
                buttons = offer.get("buttons")
                if offer.get("open") is not True or not isinstance(buttons, list) or "接受" not in buttons:
                    return result(False, "quest_accept_unavailable")
                return result(True, "accepted", "点“接受”就好呀。")
            if action == "AVOID_UNUSABLE_SPELL":
                spell = state.get("known_spell") or {}
                valid = (
                    player.get("in_combat") is True
                    and type(player.get("mana")) in (int, float)
                    and player.get("mana") == 0
                    and spell.get("usable") is False
                    and spell.get("reason") == "法力不足"
                    and isinstance(spell.get("name"), str)
                    and bool(spell["name"].strip())
                )
                if not valid:
                    return result(False, "spell_not_unusable_for_mana")
                return result(True, "accepted", f"蓝用完啦，先别施放{spell['name']}。")
            return result(False, "unknown_action")

    def commit_memory(self, patch: dict):
        """Commit sourced records by CAS, keeping explicit user preference authoritative.

        A patch may use preference.scope='proposal', or a top-level 'proposal'
        instead of 'preference'. Proposals are recorded but never become active.
        Accepted commits increment memory_version; rejects change nothing.
        """
        with self._lock:
            def result(accepted, reason):
                return {"accepted": accepted, "reason": reason, "memory_version": self._memory_version}

            if not isinstance(patch, dict):
                return result(False, "invalid_patch")
            base = patch.get("base_memory_version")
            if type(base) is not int or base != self._memory_version:
                return result(False, "memory_version_mismatch")
            proposal = "proposal" in patch and "preference" not in patch
            preference = patch.get("proposal") if proposal else patch.get("preference")
            if not isinstance(preference, dict):
                return result(False, "invalid_preference")
            quote = preference.get("source_quote")
            if not isinstance(quote, str) or not quote.strip():
                return result(False, "missing_source_quote")
            explicit = self._explicit_preference
            allowed = set(self._allowed_quotes)
            if explicit:
                allowed.add(explicit["source_quote"])
            if quote not in allowed:
                return result(False, "unverified_source_quote")
            scope = "proposal" if proposal else preference.get("scope")
            if not isinstance(scope, str) or scope not in self.SCOPES:
                return result(False, "invalid_scope")
            proposal = scope == "proposal"
            if self._current_only(quote) and scope == "future_guidance":
                return result(False, "scope_expansion")
            if not isinstance(preference.get("text"), str) or not preference["text"].strip():
                return result(False, "missing_preference_text")
            if not isinstance(preference.get("value"), dict):
                return result(False, "invalid_preference_value")
            if explicit and not proposal:
                if explicit["scope"] in self.CURRENT_SCOPES and scope == "future_guidance":
                    return result(False, "scope_expansion")
                if preference["value"] != explicit["value"]:
                    return result(False, "explicit_preference_conflict")
            record = deepcopy(preference)
            record["scope"] = scope
            self._memory_records.append(record)
            self._memory_version += 1
            return result(True, "proposal_recorded" if proposal else "memory_recorded")
