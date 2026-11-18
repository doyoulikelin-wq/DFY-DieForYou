"""Isolated packets and a local output coordinator; Python standard library only.

This is NOT a semantic fact checker. The gate validates provenance identifiers,
versions, a few explicit skill preconditions, and mechanical output constraints.
It cannot prove that arbitrary model text follows from its cited evidence.
Accepted text is returned verbatim, and action identifiers never execute a game
action. ``processing_ms`` measures this local gate, not model/network latency.

Only the coordinator owns live state. ``begin_turn`` and ``capture`` return deep
copies; pass those messages, never the runtime object, to independent workers.
World passed to begin_turn replaces the observation; set_state applies a patch.
By default every observed world field is a dependency, including key additions
and deletions. A trusted caller can set needed_fields in begin_turn to declare a
smaller business dependency set. Candidate dependencies cannot narrow that set.
Known skills additionally require their complete declared precondition fields.
Memory is append-only and never changes the active explicit preferences.
"""

from copy import deepcopy
from math import isfinite
from threading import RLock
from time import perf_counter


class CompanionRuntime:
    QUEST_FIELDS = frozenset({
        "quest_dialog_open", "can_accept", "in_combat", "has_choice",
        "has_cost", "custom_conditions_known",
    })
    MANA_FIELDS = frozenset({
        "in_combat", "mana", "spell_mana_cost", "spell_unusable_reason",
    })
    ACTION_FIELDS = {
        "ACCEPT_CURRENT_QUEST": QUEST_FIELDS,
        "EXPLAIN_NO_MANA": MANA_FIELDS,
        "SET_PROACTIVE_POLICY": frozenset(),
    }
    ACCEPT_REQUESTS = frozenset({
        "接这个任务", "接这个任务吧", "接受这个任务", "接受这个任务吧",
        "接下这个任务", "帮我接这个任务", "帮我接一下这个任务",
        "把这个任务接了", "这个任务接了吧", "接任务", "接受任务",
    })
    MANA_QUESTIONS = frozenset({
        "技能放不出来", "技能放不出来了", "这个技能放不出来",
        "为什么技能放不出来", "技能为什么放不出来", "技能怎么放不出来",
        "这个技能为什么放不出来", "这个技能怎么放不出来",
        "为什么这个技能放不出来", "为啥这个技能放不出来",
        "为什么放不出技能", "怎么放不出技能", "怎么放不出这个技能",
        "技能怎么用不了", "为什么放不了技能",
    })
    SILENCE_REQUESTS = frozenset({
        "别主动说话", "不要主动说话", "不用主动说话",
        "别主动提醒", "不要主动提醒", "不用主动提醒",
        "别主动提醒我", "不要主动提醒我", "禁止主动发言",
    })
    SCOPES = frozenset({"session", "current_turn"})
    PROTECTED_PACKET_FIELDS = (
        "packet_id", "turn_id", "reply_epoch", "state_dependency_versions",
        "preference_version", "user_text", "world", "preferences",
        "recent_messages", "evidence", "unknowns", "proactive",
        "needed_fields", "dependency_mode",
    )

    def __init__(self, world=None):
        if world is not None and not isinstance(world, dict):
            raise TypeError("world must be a dict")
        self._lock = RLock()
        self._world = deepcopy(world or {})
        self._check_keys(self._world)
        self._state_versions = {key: 1 for key in self._world}
        self._session_preferences = {}
        self._turn_preferences = {}
        self._session_origins = {}
        self._turn_origins = {}
        self._preference_version = 0
        self._reply_epoch = 0
        self._turn_id = None
        self._user_text = None
        self._packet_counter = 0
        self._event_counter = 0
        self._packets = {}
        self._seen_quotes = {}
        self._delivered_segments = set()
        self._memory_version = 0
        self._memory_records = []

    @staticmethod
    def _check_keys(value):
        if any(not isinstance(key, str) or not key for key in value):
            raise ValueError("field names must be nonempty strings")

    @classmethod
    def _equal(cls, left, right):
        # bool and int compare equal in Python, but are different observations.
        if type(left) is not type(right):
            return False
        if isinstance(left, dict):
            return left.keys() == right.keys() and all(
                cls._equal(left[key], right[key]) for key in left
            )
        if isinstance(left, (list, tuple)):
            return len(left) == len(right) and all(
                cls._equal(a, b) for a, b in zip(left, right)
            )
        return left == right

    @staticmethod
    def _normalized(text):
        return text.strip().rstrip("。！!？? ")

    @classmethod
    def _silence_scope(cls, text):
        text = cls._normalized(text)
        for prefix in ("这次", "这一轮", "本轮", "暂时", "现在", "先"):
            if text.startswith(prefix) and text[len(prefix):] in cls.SILENCE_REQUESTS:
                return "current_turn"
        for prefix in ("以后", "今后", "一直"):
            if text.startswith(prefix) and text[len(prefix):] in cls.SILENCE_REQUESTS:
                return "session"
        return "session" if text in cls.SILENCE_REQUESTS else None

    @staticmethod
    def _current_only(quote):
        lowered = quote.lower()
        return any(marker in lowered for marker in (
            "这次", "这一次", "这一轮", "本轮", "当前轮", "暂时", "先别",
            "先不要", "先教我", "this time", "this turn", "for now",
        ))

    def _preferences(self):
        return {**self._session_preferences, **self._turn_preferences}

    @staticmethod
    def _muted(preferences):
        return (preferences.get("proactive_allowed") is False
                or preferences.get("proactive") is False
                or preferences.get("muted") is True)

    @classmethod
    def _check_preference(cls, value):
        if not isinstance(value, dict):
            raise TypeError("preference value must be a dict")
        cls._check_keys(value)
        if "max_chars" in value and (
            type(value["max_chars"]) is not int or value["max_chars"] < 1
        ):
            raise ValueError("max_chars must be a positive integer")

    def set_state(self, fields):
        """Patch live world; only changed fields receive a new version."""
        if not isinstance(fields, dict):
            raise TypeError("fields must be a dict")
        self._check_keys(fields)
        with self._lock:
            for key, value in fields.items():
                if key not in self._world or not self._equal(self._world[key], value):
                    self._world[key] = deepcopy(value)
                    self._state_versions[key] = self._state_versions.get(key, 0) + 1
            return deepcopy(self._state_versions)

    def _replace_world(self, world):
        self._check_keys(world)
        for key in self._world.keys() - world.keys():
            self._state_versions[key] = self._state_versions.get(key, 0) + 1
        old_keys = set(self._world)
        self.set_state(world)
        for key in old_keys - world.keys():
            del self._world[key]

    def set_preference(self, value, scope="session", source_quote=""):
        """Apply a trusted explicit preference; a bounded quote stays bounded.

        source_quote does not create user evidence. Only observed user messages
        authorize memory records. Return the updated preference version.
        """
        self._check_preference(value)
        if not isinstance(scope, str) or scope not in self.SCOPES:
            raise ValueError("scope must be session or current_turn")
        if not isinstance(source_quote, str):
            raise TypeError("source_quote must be a string")
        if source_quote and self._current_only(source_quote):
            scope = "current_turn"
        with self._lock:
            if not value:
                return self._preference_version
            self._event_counter += 1
            self._preference_version += 1
            if source_quote in self._seen_quotes:
                self._seen_quotes[source_quote].setdefault("preference_scopes", set()).add(scope)
            target = self._session_preferences if scope == "session" else self._turn_preferences
            origins = self._session_origins if scope == "session" else self._turn_origins
            for key, item in value.items():
                target[key] = deepcopy(item)
                origins[key] = {
                    "source_quote": source_quote, "scope": scope,
                    "event": self._event_counter, "reply_epoch": self._reply_epoch,
                }
                # A newer session instruction supersedes an older turn overlay.
                if scope == "session":
                    self._turn_preferences.pop(key, None)
                    self._turn_origins.pop(key, None)
            return self._preference_version

    def _observe_quote(self, quote):
        if isinstance(quote, str) and quote.strip():
            self._event_counter += 1
            self._seen_quotes[quote] = {
                "event": self._event_counter, "reply_epoch": self._reply_epoch,
                "turn_id": self._turn_id,
            }

    def begin_turn(self, user_text, world=None, preferences=None,
                   recent_messages=None, evidence=None, unknowns=None,
                   turn_id=None, proactive=False, needed_fields=None):
        if not isinstance(user_text, str):
            raise TypeError("user_text must be a string")
        if type(proactive) is not bool:
            raise TypeError("proactive must be a bool")
        if turn_id is not None and (not isinstance(turn_id, str) or not turn_id):
            raise ValueError("turn_id must be a nonempty string")
        if world is not None and not isinstance(world, dict):
            raise TypeError("world must be a dict")
        if world is not None:
            self._check_keys(world)
        if preferences is not None:
            self._check_preference(preferences)
        if recent_messages is not None and not isinstance(recent_messages, list):
            raise TypeError("recent_messages must be a list")
        if evidence is not None and not isinstance(evidence, (list, dict)):
            raise TypeError("evidence must be a list or dict")
        if unknowns is not None and not isinstance(unknowns, list):
            raise TypeError("unknowns must be a list")
        if unknowns is not None:
            self._check_keys(unknowns)
        if needed_fields is not None:
            if not isinstance(needed_fields, (list, tuple, set, frozenset)):
                raise TypeError("needed_fields must contain field names")
            self._check_keys(needed_fields)
        with self._lock:
            new_turn = not proactive and (turn_id is None or turn_id != self._turn_id)
            if not new_turn and not proactive and user_text != self._user_text:
                raise ValueError("an existing turn_id cannot identify different user text")
            if new_turn:
                self._reply_epoch += 1
                self._turn_id = turn_id or f"turn-{self._reply_epoch}"
                self._user_text = user_text
                if self._turn_preferences:
                    self._turn_preferences.clear()
                    self._turn_origins.clear()
                    self._preference_version += 1
                self._observe_quote(user_text)
            if world is not None:
                self._replace_world(world)
            for message in recent_messages or []:
                if isinstance(message, dict) and message.get("role") == "user":
                    # Historical quotes are seen evidence, but are not newer
                    # than the live turn or its explicit preferences.
                    content = message.get("content")
                    if isinstance(content, str) and content.strip() and content not in self._seen_quotes:
                        self._seen_quotes[content] = {
                            "event": -1, "reply_epoch": None, "turn_id": None,
                        }
            if preferences is not None:
                self.set_preference(preferences, source_quote=user_text if not proactive else "")
            silence_scope = self._silence_scope(user_text) if not proactive else None
            if silence_scope:
                self.set_preference({"proactive_allowed": False}, silence_scope, user_text)
            self._packet_counter += 1
            versions = deepcopy(self._state_versions)
            fields = None if needed_fields is None else sorted(set(needed_fields))
            for key in fields or []:
                versions.setdefault(key, 0)
            packet = {
                "packet_id": f"packet-{self._packet_counter}",
                "turn_id": turn_id or self._turn_id or "proactive-0",
                "reply_epoch": self._reply_epoch,
                "state_dependency_versions": versions,
                "preference_version": self._preference_version,
                "user_text": user_text, "world": deepcopy(self._world),
                "preferences": deepcopy(self._preferences()),
                "recent_messages": deepcopy(recent_messages or []),
                "evidence": deepcopy(evidence if evidence is not None else []),
                "unknowns": deepcopy(unknowns or []), "proactive": proactive,
                "needed_fields": fields,
                "dependency_mode": "all" if fields is None else "declared",
            }
            self._packets[packet["packet_id"]] = deepcopy(packet)
            return packet

    def _canonical(self, packet):
        if not isinstance(packet, dict) or not isinstance(packet.get("packet_id"), str):
            return None
        canonical = self._packets.get(packet["packet_id"])
        if canonical is None or any(
            key not in packet or not self._equal(packet[key], canonical[key])
            for key in self.PROTECTED_PACKET_FIELDS
        ):
            return None
        return canonical

    def capture(self, packet, role="fast"):
        if not isinstance(role, str) or not role:
            raise ValueError("role must be a nonempty string")
        with self._lock:
            canonical = self._canonical(packet)
            if canonical is None:
                raise ValueError("packet is unknown or was modified")
            captured = deepcopy(canonical)
            captured["role"] = role
            return captured

    @staticmethod
    def _evidence_ids(evidence):
        if isinstance(evidence, dict):
            single_id = evidence.get("id", evidence.get("evidence_id"))
            if "id" in evidence or "evidence_id" in evidence:
                return {single_id} if isinstance(single_id, str) and single_id else set()
            return {key for key in evidence if isinstance(key, str) and key}
        ids = set()
        for item in evidence:
            identifier = item if isinstance(item, str) else (
                item.get("id", item.get("evidence_id")) if isinstance(item, dict) else None
            )
            if isinstance(identifier, str) and identifier:
                ids.add(identifier)
        return ids

    @classmethod
    def _quest_ok(cls, packet):
        world = packet["world"]
        return (
            cls._normalized(packet["user_text"]) in cls.ACCEPT_REQUESTS
            and not cls.QUEST_FIELDS.intersection(packet["unknowns"])
            and world.get("quest_dialog_open") is True
            and world.get("can_accept") is True
            and world.get("in_combat") is False
            and world.get("has_choice") is False
            and world.get("has_cost") is False
            and world.get("custom_conditions_known") is True
        )

    @classmethod
    def _mana_ok(cls, packet):
        world = packet["world"]
        mana, cost = world.get("mana"), world.get("spell_mana_cost")
        return (
            cls._normalized(packet["user_text"]) in cls.MANA_QUESTIONS
            and not cls.MANA_FIELDS.intersection(packet["unknowns"])
            and world.get("in_combat") is True
            and type(mana) in (int, float) and isfinite(mana) and mana == 0
            and type(cost) in (int, float) and isfinite(cost) and cost > 0
            and world.get("spell_unusable_reason") == "insufficient_mana"
        )

    def route(self, packet):
        """A deliberately narrow allowlist of natural user wording, never labels."""
        with self._lock:
            packet = self._canonical(packet)
            if packet is None:
                return {"route": "model", "reason": "invalid_packet"}
            if packet["proactive"] and self._muted(packet["preferences"]):
                return {"route": "silent", "reason": "proactive_disabled", "reply": ""}
            silence_scope = self._silence_scope(packet["user_text"])
            if silence_scope and not packet["proactive"]:
                reply = ("好，这一轮我不主动提醒。" if silence_scope == "current_turn"
                         else "好，这段会话里我不主动提醒。")
                return {"route": "skill", "reason": "explicit_proactive_preference",
                        "action_id": "SET_PROACTIVE_POLICY", "reply": reply, "dependencies": []}
            if self._quest_ok(packet):
                return {"route": "skill", "reason": "verified_quest_accept",
                        "action_id": "ACCEPT_CURRENT_QUEST", "reply": "点“接受”就好。",
                        "dependencies": sorted(self.QUEST_FIELDS)}
            if self._mana_ok(packet):
                return {"route": "skill", "reason": "verified_insufficient_mana",
                        "action_id": "EXPLAIN_NO_MANA",
                        "reply": "现在没有法力，这个技能又需要法力，所以暂时放不出来。",
                        "dependencies": sorted(self.MANA_FIELDS)}
            return {"route": "model", "reason": "needs_model_judgment"}

    def gate(self, packet, candidate):
        started = perf_counter()
        with self._lock:
            def result(accepted, reason, reply=""):
                return {"accepted": accepted, "reason": reason, "reply": reply,
                        "processing_ms": (perf_counter() - started) * 1000}

            canonical = self._canonical(packet)
            if canonical is None:
                return result(False, "invalid_or_modified_packet")
            packet = canonical
            if packet["reply_epoch"] != self._reply_epoch:
                return result(False, "reply_epoch_mismatch")
            if packet["preference_version"] != self._preference_version:
                return result(False, "preference_version_mismatch")
            if not isinstance(candidate, dict):
                return result(False, "invalid_candidate")
            utterance = candidate.get("utterance")
            if not isinstance(utterance, str) or not utterance.strip():
                return result(False, "invalid_utterance")
            action = candidate.get("action_id")
            if action is not None and (not isinstance(action, str) or action not in self.ACTION_FIELDS):
                return result(False, "unknown_action")
            fields = (set(packet["state_dependency_versions"]) if packet["needed_fields"] is None
                      else set(packet["needed_fields"]))
            required = self.ACTION_FIELDS.get(action, frozenset())
            if not required.issubset(fields):
                return result(False, "required_dependency_not_declared")
            declared = candidate.get("dependencies")
            if declared is not None:
                if not isinstance(declared, list) or any(
                    not isinstance(field, str) or not field for field in declared
                ):
                    return result(False, "invalid_dependencies")
                if not set(declared).issubset(fields):
                    return result(False, "dependency_not_declared")
                if not required.issubset(declared):
                    return result(False, "missing_required_dependencies")
            if packet["needed_fields"] is None:
                stale = packet["state_dependency_versions"] != self._state_versions
            else:
                stale = any(packet["state_dependency_versions"].get(field, 0)
                            != self._state_versions.get(field, 0) for field in fields)
            if stale:
                return result(False, "state_dependency_mismatch")
            evidence_refs = candidate.get("evidence_refs")
            if not isinstance(evidence_refs, list) or any(
                not isinstance(ref, str) or not ref for ref in evidence_refs
            ):
                return result(False, "invalid_evidence_refs")
            if not set(evidence_refs).issubset(self._evidence_ids(packet["evidence"])):
                return result(False, "unknown_evidence_ref")
            if packet["proactive"] and self._muted(self._preferences()):
                return result(False, "proactive_disabled")
            limit = self._preferences().get("max_chars")
            if limit is not None and len(utterance) > limit:
                return result(False, "max_chars_exceeded")
            # These checks cover only the three supported structured skills.
            # Free text without an action_id receives no semantic certification.
            if action == "ACCEPT_CURRENT_QUEST" and not self._quest_ok(packet):
                return result(False, "quest_preconditions_not_met")
            if action == "EXPLAIN_NO_MANA" and not self._mana_ok(packet):
                return result(False, "mana_preconditions_not_met")
            if action == "SET_PROACTIVE_POLICY" and not self._silence_scope(packet["user_text"]):
                return result(False, "preference_instruction_not_explicit")
            segment_id = candidate.get("segment_id")
            if segment_id is not None:
                if not isinstance(segment_id, str) or not segment_id:
                    return result(False, "invalid_segment_id")
                segment_key = (self._reply_epoch, segment_id)
                if segment_key in self._delivered_segments:
                    return result(False, "duplicate_segment")
                self._delivered_segments.add(segment_key)
            return result(True, "accepted", utterance)

    @property
    def memory_version(self):
        with self._lock:
            return self._memory_version

    @property
    def memory_records(self):
        with self._lock:
            return deepcopy(self._memory_records)

    def commit_memory(self, base_version, record):
        """CAS append; exact seen user quotes and bounded scope are mandatory."""
        with self._lock:
            def result(accepted, reason):
                return {"accepted": accepted, "reason": reason,
                        "memory_version": self._memory_version}

            if type(base_version) is not int or base_version != self._memory_version:
                return result(False, "memory_version_mismatch")
            if not isinstance(record, dict):
                return result(False, "invalid_record")
            quote = record.get("source_quote", record.get("quote"))
            if not isinstance(quote, str) or not quote.strip():
                return result(False, "missing_source_quote")
            if quote not in self._seen_quotes:
                return result(False, "unverified_source_quote")
            if "quote" in record and "source_quote" in record and record["quote"] != quote:
                return result(False, "conflicting_source_quotes")
            scope = record.get("scope")
            if not isinstance(scope, str) or scope not in self.SCOPES:
                return result(False, "invalid_scope")
            source = self._seen_quotes[quote]
            if scope == "session" and (self._current_only(quote)
                    or "current_turn" in source.get("preference_scopes", ())):
                return result(False, "scope_expansion")
            value = record.get("value", {})
            if not isinstance(value, dict):
                return result(False, "invalid_memory_value")
            if not value and not (isinstance(record.get("text"), str) and record["text"].strip()):
                return result(False, "empty_memory_record")
            active = self._preferences()
            origins = {**self._session_origins, **self._turn_origins}
            for key, item in value.items():
                if (key in origins and origins[key]["event"] >= source["event"]
                        and not self._equal(item, active[key])):
                    return result(False, "newer_explicit_preference_conflict")
            stored = deepcopy(record)
            stored["source_quote"] = quote
            stored["scope"] = scope
            stored["source_turn_id"] = source["turn_id"]
            stored["source_reply_epoch"] = source["reply_epoch"]
            self._memory_records.append(stored)
            self._memory_version += 1
            return result(True, "memory_recorded")

    def snapshot(self):
        """Detached coordinator diagnostics; do not send this to workers."""
        with self._lock:
            return deepcopy({
                "world": self._world, "state_dependency_versions": self._state_versions,
                "preferences": self._preferences(),
                "session_preferences": self._session_preferences,
                "current_turn_preferences": self._turn_preferences,
                "preference_version": self._preference_version,
                "reply_epoch": self._reply_epoch, "turn_id": self._turn_id,
                "memory_version": self._memory_version,
                "memory_records": self._memory_records,
            })
