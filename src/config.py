from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from model_provider import ProviderConfig, normalize_provider


@dataclass
class LabConfig:
    """Shared configuration for the lab."""

    base_dir: Path
    data_dir: Path
    state_dir: Path
    compact_threshold_tokens: int
    compact_keep_messages: int
    model: ProviderConfig
    judge_model: ProviderConfig


def load_config(base_dir: Path | None = None) -> LabConfig:
    """Load environment variables (optionally from `.env`) and return a LabConfig."""

    root = (base_dir or Path(__file__).resolve().parent.parent).resolve()

    try:
        from dotenv import load_dotenv

        load_dotenv(root / ".env")
    except ImportError:
        pass

    data_dir = root / "data"
    state_dir = root / "state"
    state_dir.mkdir(parents=True, exist_ok=True)

    provider = normalize_provider(os.getenv("LLM_PROVIDER", "offline"))
    model_name = os.getenv("LLM_MODEL", "gpt-4o-mini")
    api_key = (
        os.getenv("OPENAI_API_KEY")
        or os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("GEMINI_API_KEY")
        or os.getenv("OPENROUTER_API_KEY")
        or os.getenv("CUSTOM_API_KEY")
    )
    base_url = os.getenv("CUSTOM_BASE_URL") or os.getenv("OLLAMA_BASE_URL")

    model = ProviderConfig(
        provider=provider,
        model_name=model_name,
        temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
        api_key=api_key,
        base_url=base_url,
    )

    judge_provider = normalize_provider(os.getenv("JUDGE_LLM_PROVIDER", provider))
    judge_model_name = os.getenv("JUDGE_LLM_MODEL", model_name)
    judge_model = ProviderConfig(
        provider=judge_provider,
        model_name=judge_model_name,
        temperature=float(os.getenv("JUDGE_LLM_TEMPERATURE", "0.0")),
        api_key=api_key,
        base_url=base_url,
    )

    compact_threshold_tokens = int(os.getenv("COMPACT_THRESHOLD_TOKENS", "300"))
    compact_keep_messages = int(os.getenv("COMPACT_KEEP_MESSAGES", "4"))

    return LabConfig(
        base_dir=root,
        data_dir=data_dir,
        state_dir=state_dir,
        compact_threshold_tokens=compact_threshold_tokens,
        compact_keep_messages=compact_keep_messages,
        model=model,
        judge_model=judge_model,
    )
