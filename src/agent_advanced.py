from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config import LabConfig, load_config
from memory_store import (
    CompactMemoryManager,
    UserProfileStore,
    estimate_tokens,
    extract_profile_updates,
)
from model_provider import build_chat_model

_MERGE_KEYS = {"style", "interests"}


def _merge_descriptors(existing: str, new: str) -> str:
    items: list[str] = []
    for chunk in f"{existing},{new}".split(","):
        chunk = chunk.strip()
        if chunk and chunk not in items:
            items.append(chunk)
    return ", ".join(items)


@dataclass
class AgentContext:
    user_id: str
    memory_path: str


class AdvancedAgent:
    """Agent B: within-session memory + persistent `User.md` + compact memory."""

    def __init__(self, config: LabConfig | None = None, force_offline: bool = False) -> None:
        self.config = config or load_config()
        self.force_offline = force_offline
        self.profile_store = UserProfileStore(self.config.state_dir / "profiles")
        self.compact_memory = CompactMemoryManager(
            threshold_tokens=self.config.compact_threshold_tokens,
            keep_messages=self.config.compact_keep_messages,
        )
        self.thread_tokens: dict[str, int] = {}
        self.thread_prompt_tokens: dict[str, int] = {}

        self.langchain_agent = None if force_offline else self._maybe_build_langchain_agent()

    def reply(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        if self.langchain_agent is not None and not self.force_offline:
            try:
                return self._reply_live(user_id, thread_id, message)
            except Exception:
                pass
        return self._reply_offline(user_id, thread_id, message)

    def token_usage(self, thread_id: str) -> int:
        return self.thread_tokens.get(thread_id, 0)

    def prompt_token_usage(self, thread_id: str) -> int:
        return self.thread_prompt_tokens.get(thread_id, 0)

    def memory_file_size(self, user_id: str) -> int:
        return self.profile_store.file_size(user_id)

    def compaction_count(self, thread_id: str) -> int:
        return self.compact_memory.compaction_count(thread_id)

    def _reply_offline(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        updates = extract_profile_updates(message)
        existing_facts = self.profile_store.facts(user_id)
        for key, value in updates.items():
            if key in _MERGE_KEYS:
                merged = _merge_descriptors(existing_facts.get(key, ""), value)
                self.profile_store.upsert_fact(user_id, key, merged)
                existing_facts[key] = merged
            else:
                self.profile_store.upsert_fact(user_id, key, value)
                existing_facts[key] = value

        self.compact_memory.append(thread_id, "user", message)

        prompt_tokens = self._estimate_prompt_context_tokens(user_id, thread_id)
        self.thread_prompt_tokens[thread_id] = (
            self.thread_prompt_tokens.get(thread_id, 0) + prompt_tokens
        )

        answer = self._offline_response(user_id, thread_id, message)
        self.compact_memory.append(thread_id, "assistant", answer)

        agent_tokens = estimate_tokens(answer)
        self.thread_tokens[thread_id] = self.thread_tokens.get(thread_id, 0) + agent_tokens

        return {"answer": answer, "agent_tokens": agent_tokens, "prompt_tokens": prompt_tokens}

    def _estimate_prompt_context_tokens(self, user_id: str, thread_id: str) -> int:
        profile_text = self.profile_store.read_text(user_id)
        ctx = self.compact_memory.context(thread_id)
        summary = str(ctx.get("summary", ""))
        recent = ctx.get("messages", [])  # type: ignore[assignment]
        recent_text = " ".join(m["content"] for m in recent)  # type: ignore[union-attr]
        return (
            estimate_tokens(profile_text)
            + estimate_tokens(summary)
            + estimate_tokens(recent_text)
        )

    def _offline_response(self, user_id: str, thread_id: str, message: str) -> str:
        facts = self.profile_store.facts(user_id)
        low = message.lower()
        parts: list[str] = []

        if any(k in low for k in ["tên", "ai", "tóm tắt", "nhắc lại"]) and facts.get("name"):
            parts.append(facts["name"])
        if any(k in low for k in ["ở đâu", "nơi ở", "còn ở"]) and facts.get("location"):
            parts.append(facts["location"])
        if any(k in low for k in ["nghề", "công việc"]) and facts.get("profession"):
            parts.append(facts["profession"])
        if "đồ uống" in low and facts.get("drink"):
            parts.append(facts["drink"])
        if "món ăn" in low and facts.get("food"):
            parts.append(facts["food"])
        if "nuôi" in low and facts.get("pet"):
            parts.append(facts["pet"])
        if any(k in low for k in ["style", "trả lời", "phong cách"]) and facts.get("style"):
            parts.append(facts["style"])
        if "quan tâm" in low and facts.get("interests"):
            parts.append(facts["interests"])

        if not parts:
            return "Mình đã ghi nhận thông tin bạn vừa chia sẻ và sẽ lưu lại."

        return "Dựa trên thông tin đã lưu: " + "; ".join(parts) + "."

    def _reply_live(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        updates = extract_profile_updates(message)
        existing_facts = self.profile_store.facts(user_id)
        for key, value in updates.items():
            if key in _MERGE_KEYS:
                merged = _merge_descriptors(existing_facts.get(key, ""), value)
                self.profile_store.upsert_fact(user_id, key, merged)
            else:
                self.profile_store.upsert_fact(user_id, key, value)

        self.compact_memory.append(thread_id, "user", message)
        profile_text = self.profile_store.read_text(user_id)
        ctx = self.compact_memory.context(thread_id)
        recent = ctx.get("messages", [])  # type: ignore[assignment]

        history = [("system", profile_text), ("system", str(ctx.get("summary", "")))]
        history += [(m["role"], m["content"]) for m in recent]  # type: ignore[union-attr]

        prompt_text = profile_text + str(ctx.get("summary", "")) + " ".join(
            m["content"] for m in recent  # type: ignore[union-attr]
        )
        prompt_tokens = estimate_tokens(prompt_text)
        self.thread_prompt_tokens[thread_id] = (
            self.thread_prompt_tokens.get(thread_id, 0) + prompt_tokens
        )

        response = self.langchain_agent.invoke(history)
        answer = getattr(response, "content", str(response))
        self.compact_memory.append(thread_id, "assistant", answer)

        agent_tokens = estimate_tokens(answer)
        self.thread_tokens[thread_id] = self.thread_tokens.get(thread_id, 0) + agent_tokens

        return {"answer": answer, "agent_tokens": agent_tokens, "prompt_tokens": prompt_tokens}

    def _maybe_build_langchain_agent(self):
        try:
            if not self.config.model.api_key and self.config.model.provider != "ollama":
                return None
            return build_chat_model(self.config.model)
        except Exception:
            return None
