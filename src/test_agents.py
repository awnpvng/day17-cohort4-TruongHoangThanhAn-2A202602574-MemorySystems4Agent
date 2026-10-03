from __future__ import annotations

from pathlib import Path

from agent_advanced import AdvancedAgent
from agent_baseline import BaselineAgent
from config import LabConfig
from memory_store import CompactMemoryManager, UserProfileStore
from model_provider import ProviderConfig


def make_config(tmp_path: Path) -> LabConfig:
    state_dir = tmp_path / "state"
    data_dir = tmp_path / "data"
    state_dir.mkdir(parents=True, exist_ok=True)
    offline_provider = ProviderConfig(provider="offline", model_name="offline-test", temperature=0.0)
    return LabConfig(
        base_dir=tmp_path,
        data_dir=data_dir,
        state_dir=state_dir,
        compact_threshold_tokens=80,
        compact_keep_messages=2,
        model=offline_provider,
        judge_model=offline_provider,
    )


def test_user_markdown_read_write_edit(tmp_path: Path) -> None:
    store = UserProfileStore(tmp_path / "profiles")

    store.write_text("u1", "# User Profile\n\n## Facts\n- name: DũngCT\n")
    content = store.read_text("u1")
    assert "DũngCT" in content

    changed = store.edit_text("u1", "DũngCT", "DũngCT Edited")
    assert changed is True
    assert "DũngCT Edited" in store.read_text("u1")

    assert store.file_size("u1") > 0

    store.upsert_fact("u1", "location", "Huế")
    assert store.facts("u1")["location"] == "Huế"

    store.upsert_fact("u1", "location", "Đà Nẵng")
    assert store.facts("u1")["location"] == "Đà Nẵng"


def test_compact_trigger(tmp_path: Path) -> None:
    manager = CompactMemoryManager(threshold_tokens=20, keep_messages=1)

    long_text = "Đây là một đoạn tin dài để ép token vượt ngưỡng compact nhanh hơn. " * 3
    for i in range(6):
        manager.append("thread-1", "user", f"{long_text} lượt {i}")

    assert manager.compaction_count("thread-1") > 0
    ctx = manager.context("thread-1")
    assert len(ctx["messages"]) <= 1
    assert ctx["summary"]


def test_cross_session_recall(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    baseline = BaselineAgent(config, force_offline=True)
    advanced = AdvancedAgent(config, force_offline=True)

    baseline.reply("u1", "thread-1", "Chào bạn, mình tên là DũngCT.")
    advanced.reply("u1", "thread-1", "Chào bạn, mình tên là DũngCT.")

    baseline_answer = baseline.reply("u1", "thread-2", "Mình tên gì?")["answer"]
    advanced_answer = advanced.reply("u1", "thread-2", "Mình tên gì?")["answer"]

    assert "DũngCT" not in baseline_answer
    assert "DũngCT" in advanced_answer


def test_compact_reduces_prompt_load_on_long_thread(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    baseline = BaselineAgent(config, force_offline=True)
    advanced = AdvancedAgent(config, force_offline=True)

    long_text = (
        "Đây là một đoạn hội thoại dài được lặp lại nhiều lần để làm phình ngữ cảnh "
        "và kiểm tra việc compact memory có giúp giảm tải prompt hay không. "
    ) * 3

    for i in range(10):
        message = f"{long_text} lượt {i}"
        baseline.reply("u1", "thread-long", message)
        advanced.reply("u1", "thread-long", message)

    assert advanced.compaction_count("thread-long") > 0
    assert advanced.prompt_token_usage("thread-long") < baseline.prompt_token_usage("thread-long")
