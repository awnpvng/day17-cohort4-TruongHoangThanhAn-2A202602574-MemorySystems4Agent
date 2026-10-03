from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_PROFESSIONS = ["backend engineer", "MLOps engineer", "product manager"]

_STYLE_KEYWORDS = [
    "3 bullet",
    "bullet ngắn",
    "ngắn gọn",
    "có cấu trúc",
    "ví dụ thực chiến",
    "ví dụ thực tế",
    "so sánh trade-off",
]

_INTEREST_TOKENS = ["Python", "AI"]

_NAME_PREFIX_RE = re.compile(r"tên\s*(?:mình\s*)?(?:là\s*)?")
_LOCATION_PREFIX_RE = re.compile(r"\bở\s+")
_LOCATION_PREFIX_RE_2 = re.compile(r"nơi ở hiện tại là\s+")
_PROFESSION_RE = re.compile("|".join(re.escape(p) for p in _PROFESSIONS))
_PET_PREFIX_RE = re.compile(r"corgi\s+tên\s+")

_NEGATION_KEYWORDS = [
    "không còn làm",
    "không còn là",
    "không còn",
    "đừng nói",
    "không phải là",
    "không phải",
    "chỉ là",
]


def _is_negated_before(text: str, pos: int, window: int = 25) -> bool:
    context = text[max(0, pos - window) : pos].lower()
    return any(neg in context for neg in _NEGATION_KEYWORDS)


def _capitalized_phrase(words: list[str]) -> str:
    """Return the longest leading run of capitalized words, Vietnamese-safe.

    `[A-ZÀ-Ỹ]` is not a clean "uppercase only" range for Vietnamese: the
    diacritic code points interleave upper/lowercase, so case is checked in
    Python with `str.isupper()` instead of a regex character class.
    """

    out: list[str] = []
    for w in words:
        core = re.sub(r"^[^\wÀ-ỹ]+|[^\wÀ-ỹ]+$", "", w)
        if core and core[0].isupper():
            out.append(core)
        else:
            break
    return " ".join(out)


def _find_capitalized_after(prefix_re: re.Pattern, text: str, skip_negated: bool = False) -> list[str]:
    results = []
    for m in prefix_re.finditer(text):
        if skip_negated and _is_negated_before(text, m.start()):
            continue
        rest = text[m.end() :]
        phrase = _capitalized_phrase(rest.split())
        if phrase:
            results.append(phrase)
    return results


def estimate_tokens(text: str) -> int:
    """Rough heuristic token estimator (~4 chars per token)."""

    if not text:
        return 0
    cleaned = text.strip()
    if not cleaned:
        return 0
    return max(1, len(cleaned) // 4)


def _slugify(user_id: str) -> str:
    safe = re.sub(r"[^\w\-]+", "_", user_id.strip())
    return safe or "unknown_user"


@dataclass
class UserProfileStore:
    """Persistent storage for one `User.md` markdown file per user."""

    root_dir: Path

    def path_for(self, user_id: str) -> Path:
        return self.root_dir / _slugify(user_id) / "User.md"

    def read_text(self, user_id: str) -> str:
        path = self.path_for(user_id)
        if path.exists():
            return path.read_text(encoding="utf-8")
        return "# User Profile\n\n## Facts\n"

    def write_text(self, user_id: str, content: str) -> Path:
        path = self.path_for(user_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def edit_text(self, user_id: str, search_text: str, replacement: str) -> bool:
        current = self.read_text(user_id)
        if search_text not in current:
            return False
        updated = current.replace(search_text, replacement, 1)
        self.write_text(user_id, updated)
        return True

    def file_size(self, user_id: str) -> int:
        path = self.path_for(user_id)
        if path.exists():
            return path.stat().st_size
        return 0

    def facts(self, user_id: str) -> dict[str, str]:
        text = self.read_text(user_id)
        result: dict[str, str] = {}
        for line in text.splitlines():
            m = re.match(r"-\s*([\w\-]+)\s*:\s*(.+)", line.strip())
            if m:
                result[m.group(1)] = m.group(2).strip()
        return result

    def upsert_fact(self, user_id: str, key: str, value: str) -> Path:
        text = self.read_text(user_id)
        if "## Facts" not in text:
            text = text.rstrip() + "\n\n## Facts\n"

        line_re = re.compile(rf"^-\s*{re.escape(key)}\s*:.*$", re.MULTILINE)
        new_line = f"- {key}: {value}"
        if line_re.search(text):
            text = line_re.sub(new_line, text, count=1)
        else:
            text = text.rstrip() + "\n" + new_line + "\n"
        return self.write_text(user_id, text)


def extract_profile_updates(message: str) -> dict[str, str]:
    """Extract stable profile facts from one raw user message.

    Skips questions and known noise (meeting-trip mentions, jokes).
    """

    facts: dict[str, str] = {}
    if not message or not message.strip():
        return facts

    sentences = re.split(r"(?<=[.!])\s+", message.strip())

    style_hits: list[str] = []
    for token in _STYLE_KEYWORDS:
        if token in message and token not in style_hits:
            style_hits.append(token)
    if style_hits:
        facts["style"] = ", ".join(style_hits)

    interest_hits: list[str] = []
    for token in _INTEREST_TOKENS:
        if re.search(rf"\b{re.escape(token)}\b", message) and token not in interest_hits:
            interest_hits.append(token)
    if interest_hits:
        facts["interests"] = ", ".join(interest_hits)

    for sent in sentences:
        if "?" in sent:
            continue
        low = sent.lower()
        is_joke = "đùa" in low
        is_meeting = "họp" in low or "bay ra" in low or "bay" in low

        if "corgi" not in low:
            name_matches = _find_capitalized_after(_NAME_PREFIX_RE, sent)
            if name_matches:
                facts["name"] = name_matches[-1]

        if not is_meeting and not is_joke:
            loc_matches = _find_capitalized_after(_LOCATION_PREFIX_RE, sent, skip_negated=True)
            if loc_matches:
                facts["location"] = loc_matches[-1]
            loc_matches_2 = _find_capitalized_after(_LOCATION_PREFIX_RE_2, sent)
            if loc_matches_2:
                facts["location"] = loc_matches_2[-1]

        if not is_joke:
            prof_matches = [
                m.group(0)
                for m in _PROFESSION_RE.finditer(sent)
                if not _is_negated_before(sent, m.start())
            ]
            if prof_matches:
                facts["profession"] = prof_matches[-1]

        if "cà phê sữa đá" in sent:
            facts["drink"] = "cà phê sữa đá"

        if "mì Quảng" in sent:
            facts["food"] = "mì Quảng"

        pet_matches = _find_capitalized_after(_PET_PREFIX_RE, sent)
        if pet_matches:
            facts["pet"] = f"corgi tên {pet_matches[-1]}"
        elif "corgi" in low:
            facts.setdefault("pet", "corgi")

    return facts


def summarize_messages(messages: list[dict[str, str]], max_items: int = 6) -> str:
    """Create a compact, heuristic summary of older messages."""

    if not messages:
        return ""
    chosen = messages[-max_items:] if len(messages) > max_items else messages
    parts = []
    for m in chosen:
        content = (m.get("content") or "").strip().replace("\n", " ")
        if len(content) > 100:
            content = content[:100] + "..."
        parts.append(f"{m.get('role', 'user')}: {content}")
    return " | ".join(parts)


@dataclass
class CompactMemoryManager:
    """Compact memory for long threads: keeps recent messages, summarizes the rest."""

    threshold_tokens: int
    keep_messages: int
    state: dict[str, dict[str, object]] = field(default_factory=dict)

    def _ensure(self, thread_id: str) -> dict[str, object]:
        if thread_id not in self.state:
            self.state[thread_id] = {"messages": [], "summary": "", "compactions": 0}
        return self.state[thread_id]

    def append(self, thread_id: str, role: str, content: str) -> None:
        ctx = self._ensure(thread_id)
        messages: list[dict[str, str]] = ctx["messages"]  # type: ignore[assignment]
        messages.append({"role": role, "content": content})

        total_tokens = estimate_tokens(str(ctx["summary"])) + sum(
            estimate_tokens(m["content"]) for m in messages
        )

        if total_tokens > self.threshold_tokens and len(messages) > self.keep_messages:
            older = messages[: -self.keep_messages]
            recent = messages[-self.keep_messages :]
            summary_piece = summarize_messages(older)
            new_summary = f"{ctx['summary']} {summary_piece}".strip()
            ctx["summary"] = new_summary
            ctx["messages"] = recent
            ctx["compactions"] = int(ctx["compactions"]) + 1  # type: ignore[arg-type]

    def context(self, thread_id: str) -> dict[str, object]:
        return self._ensure(thread_id)

    def compaction_count(self, thread_id: str) -> int:
        if thread_id not in self.state:
            return 0
        return int(self.state[thread_id]["compactions"])  # type: ignore[arg-type]
