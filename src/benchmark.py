from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_advanced import AdvancedAgent
from agent_baseline import BaselineAgent
from config import load_config


@dataclass
class BenchmarkRow:
    agent_name: str
    agent_tokens_only: int
    prompt_tokens_processed: int
    recall_score: float
    response_quality: float
    memory_growth_bytes: int
    compactions: int


def load_conversations(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def recall_points(answer: str, expected: list[str]) -> float:
    if not expected:
        return 1.0
    hits = sum(1 for item in expected if item in answer)
    if hits == len(expected):
        return 1.0
    if hits > 0:
        return 0.5
    return 0.0


def heuristic_quality(answer: str, expected: list[str]) -> float:
    recall = recall_points(answer, expected)
    length_score = 1.0 if len(answer) <= 300 else 0.7
    return round(0.7 * recall + 0.3 * length_score, 3)


def run_agent_benchmark(
    agent_name: str, agent, conversations: list[dict[str, Any]], config
) -> BenchmarkRow:
    total_agent_tokens = 0
    total_prompt_tokens = 0
    total_recall = 0.0
    total_quality = 0.0
    recall_count = 0
    compactions = 0
    memory_growth = 0

    for conv in conversations:
        user_id = conv["user_id"]
        thread_id = conv["id"]

        for turn in conv["turns"]:
            agent.reply(user_id, thread_id, turn)

        total_agent_tokens += agent.token_usage(thread_id)
        total_prompt_tokens += agent.prompt_token_usage(thread_id)
        compactions += agent.compaction_count(thread_id)

        if hasattr(agent, "memory_file_size"):
            memory_growth = agent.memory_file_size(user_id)

        recall_thread_id = f"{thread_id}-recall"
        for rq in conv.get("recall_questions", []):
            result = agent.reply(user_id, recall_thread_id, rq["question"])
            answer = result["answer"]
            total_recall += recall_points(answer, rq["expected_contains"])
            total_quality += heuristic_quality(answer, rq["expected_contains"])
            recall_count += 1

        total_agent_tokens += agent.token_usage(recall_thread_id)
        total_prompt_tokens += agent.prompt_token_usage(recall_thread_id)
        compactions += agent.compaction_count(recall_thread_id)

    avg_recall = total_recall / recall_count if recall_count else 0.0
    avg_quality = total_quality / recall_count if recall_count else 0.0

    return BenchmarkRow(
        agent_name=agent_name,
        agent_tokens_only=total_agent_tokens,
        prompt_tokens_processed=total_prompt_tokens,
        recall_score=round(avg_recall, 3),
        response_quality=round(avg_quality, 3),
        memory_growth_bytes=memory_growth,
        compactions=compactions,
    )


def format_rows(rows: list[BenchmarkRow]) -> str:
    headers = [
        "Agent",
        "Agent tokens only",
        "Prompt tokens processed",
        "Cross-session recall",
        "Response quality",
        "Memory growth (bytes)",
        "Compactions",
    ]
    data = [
        [
            r.agent_name,
            r.agent_tokens_only,
            r.prompt_tokens_processed,
            r.recall_score,
            r.response_quality,
            r.memory_growth_bytes,
            r.compactions,
        ]
        for r in rows
    ]

    try:
        from tabulate import tabulate

        return tabulate(data, headers=headers, tablefmt="github")
    except ImportError:
        widths = [
            max(len(str(h)), *(len(str(row[i])) for row in data)) for i, h in enumerate(headers)
        ]
        lines = [" | ".join(str(h).ljust(widths[i]) for i, h in enumerate(headers))]
        lines.append(" | ".join("-" * w for w in widths))
        for row in data:
            lines.append(" | ".join(str(v).ljust(widths[i]) for i, v in enumerate(row)))
        return "\n".join(lines)


def main() -> None:
    config = load_config(Path(__file__).resolve().parent.parent)

    profiles_dir = config.state_dir / "profiles"
    if profiles_dir.exists():
        shutil.rmtree(profiles_dir)

    standard_convs = load_conversations(config.data_dir / "conversations.json")
    stress_convs = load_conversations(config.data_dir / "advanced_long_context.json")

    print("=== Standard Benchmark ===")
    baseline = BaselineAgent(config, force_offline=True)
    advanced = AdvancedAgent(config, force_offline=True)
    standard_rows = [
        run_agent_benchmark("Baseline", baseline, standard_convs, config),
        run_agent_benchmark("Advanced", advanced, standard_convs, config),
    ]
    print(format_rows(standard_rows))

    print()
    print("=== Long-Context Stress Benchmark ===")
    baseline_stress = BaselineAgent(config, force_offline=True)
    advanced_stress = AdvancedAgent(config, force_offline=True)
    stress_rows = [
        run_agent_benchmark("Baseline", baseline_stress, stress_convs, config),
        run_agent_benchmark("Advanced", advanced_stress, stress_convs, config),
    ]
    print(format_rows(stress_rows))


if __name__ == "__main__":
    main()
