from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from config import LabConfig, load_config
from memory_store import estimate_tokens
from model_provider import build_chat_model


@dataclass
class SessionState:
    messages: list[dict[str, str]] = field(default_factory=list)
    token_usage: int = 0
    prompt_tokens_processed: int = 0


class BaselineAgent:
    """Agent A: within-session memory only, no persistent `User.md`."""

    def __init__(self, config: LabConfig | None = None, force_offline: bool = False) -> None:
        self.config = config or load_config()
        self.force_offline = force_offline
        self.sessions: dict[str, SessionState] = {}

        self.langchain_agent = None if force_offline else self._maybe_build_langchain_agent()

    def reply(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        if self.langchain_agent is not None and not self.force_offline:
            try:
                return self._reply_live(thread_id, message)
            except Exception:
                pass
        return self._reply_offline(thread_id, message)

    def token_usage(self, thread_id: str) -> int:
        session = self.sessions.get(thread_id)
        return session.token_usage if session else 0

    def prompt_token_usage(self, thread_id: str) -> int:
        session = self.sessions.get(thread_id)
        return session.prompt_tokens_processed if session else 0

    def compaction_count(self, thread_id: str) -> int:
        return 0

    def _reply_offline(self, thread_id: str, message: str) -> dict[str, Any]:
        session = self.sessions.setdefault(thread_id, SessionState())
        session.messages.append({"role": "user", "content": message})

        prompt_tokens = sum(estimate_tokens(m["content"]) for m in session.messages)
        session.prompt_tokens_processed += prompt_tokens

        answer = (
            "Mình không có đủ thông tin để nhớ lại điều đó vì mình chỉ nhớ "
            "trong cùng thread hiện tại."
        )
        for m in session.messages[:-1]:
            if m["role"] == "user":
                answer = f"Trong thread này mình thấy bạn từng nói: {m['content'][:80]}"
                break

        session.messages.append({"role": "assistant", "content": answer})
        agent_tokens = estimate_tokens(answer)
        session.token_usage += agent_tokens

        return {"answer": answer, "agent_tokens": agent_tokens, "prompt_tokens": prompt_tokens}

    def _reply_live(self, thread_id: str, message: str) -> dict[str, Any]:
        session = self.sessions.setdefault(thread_id, SessionState())
        session.messages.append({"role": "user", "content": message})

        history = [(m["role"], m["content"]) for m in session.messages]
        prompt_text = "\n".join(f"{role}: {content}" for role, content in history)
        prompt_tokens = estimate_tokens(prompt_text)
        session.prompt_tokens_processed += prompt_tokens

        response = self.langchain_agent.invoke(history)
        answer = getattr(response, "content", str(response))

        session.messages.append({"role": "assistant", "content": answer})
        agent_tokens = estimate_tokens(answer)
        session.token_usage += agent_tokens

        return {"answer": answer, "agent_tokens": agent_tokens, "prompt_tokens": prompt_tokens}

    def _maybe_build_langchain_agent(self):
        try:
            if not self.config.model.api_key and self.config.model.provider != "ollama":
                return None
            return build_chat_model(self.config.model)
        except Exception:
            return None
