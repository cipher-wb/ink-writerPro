"""M4 P0 测试书端到端驱动（US-014）。

由于 ``ink_writer.planning_review.{ink_init,ink_plan}_review`` 的 CLI 调用
``anthropic.Anthropic()``，需要 ``ANTHROPIC_API_KEY``；本机 ``.zshrc`` 默认
unset 该 key（CLAUDE.md 已声明），无法直接跑真实 LLM。本脚本作为 fixture
驱动跑一遍策划期审查，使用预定义的 "高分通过" LLM 响应模拟真实 LLM 调用，
最终在 ``data/test-book-m4/planning_evidence_chain.json`` 写出与真实运行
等价的 evidence chain（phase=planning + stages={ink-init, ink-plan} +
total_checkers=7）。

用途：US-014 e2e 验收 — 在没有线上 LLM 的环境下也能产出 M4 P0 全链路的
evidence_chain.json，与单元测试的 in-memory 路径形成磁盘冗余校验。

CLI::

    python3 scripts/run_m4_test_book.py [--book test-book-m4]

退出码：0 = effective_blocked False；1 = blocked
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ink_writer.planning_review.ink_init_review import run_ink_init_review  # noqa: E402
from ink_writer.planning_review.ink_plan_review import run_ink_plan_review  # noqa: E402

try:
    sys.path.insert(0, str(REPO_ROOT / "ink-writer" / "scripts"))
    from runtime_compat import enable_windows_utf8_stdio  # noqa: E402

    enable_windows_utf8_stdio()
except ImportError:
    pass


# ---------------------------------------------------------------------------
# 最小 anthropic-shape stub（与 tests/checkers/conftest.FakeLLMClient 同构）
# ---------------------------------------------------------------------------


@dataclass
class _Content:
    text: str


@dataclass
class _Response:
    content: list[_Content]


@dataclass
class _Messages:
    responders: list[str] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)
    _idx: int = 0

    def create(self, **kwargs: Any) -> _Response:
        self.calls.append(kwargs)
        if not self.responders:
            raise RuntimeError("FixtureLLMClient: no responder configured")
        idx = min(self._idx, len(self.responders) - 1)
        text = self.responders[idx]
        self._idx += 1
        return _Response(content=[_Content(text=text)])


class FixtureLLMClient:
    """anthropic-shape 的预设响应客户端，仅用于 e2e 驱动。"""

    def __init__(self, responders: list[str]) -> None:
        self.messages = _Messages(responders=list(responders))


def _ink_init_responders() -> list[str]:
    """top200 空 → genre 跳 LLM；naming 纯规则；只调 spec + motive。"""
    return [
        json.dumps(
            {
                "clarity": 0.85,
                "falsifiability": 0.80,
                "boundary": 0.85,
                "growth_curve": 0.80,
                "notes": "万道归一规格清晰、有可证伪边界",
            },
            ensure_ascii=False,
        ),
        json.dumps(
            {
                "resonance": 0.85,
                "specific_goal": 0.80,
                "inner_conflict": 0.85,
                "notes": "战争遗孤动机扎实、内心冲突鲜明",
            },
            ensure_ascii=False,
        ),
    ]


def _ink_plan_responders() -> list[str]:
    """timing regex 命中前 3 章 → 跳 LLM；agency + density 各调一次。"""
    return [
        json.dumps(
            [
                {"chapter_idx": 1, "agency_score": 0.85, "reason": "主动出击"},
                {"chapter_idx": 2, "agency_score": 0.78, "reason": "主动试招"},
                {"chapter_idx": 3, "agency_score": 0.82, "reason": "主动追查"},
                {"chapter_idx": 4, "agency_score": 0.86, "reason": "主动救人"},
                {"chapter_idx": 5, "agency_score": 0.84, "reason": "主动闯阵"},
            ],
            ensure_ascii=False,
        ),
        json.dumps(
            [
                {"chapter_idx": 1, "hook_strength": 0.82, "reason": "破解阵法悬念"},
                {"chapter_idx": 2, "hook_strength": 0.78, "reason": "首次试招"},
                {"chapter_idx": 3, "hook_strength": 0.85, "reason": "并肩闯阵"},
                {"chapter_idx": 4, "hook_strength": 0.80, "reason": "反噬危机"},
                {"chapter_idx": 5, "hook_strength": 0.82, "reason": "屠村令真相"},
            ],
            ensure_ascii=False,
        ),
    ]


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="scripts.run_m4_test_book",
        description="M4 P0 测试书 e2e 驱动",
    )
    p.add_argument("--book", default="test-book-m4")
    p.add_argument(
        "--base-dir",
        type=Path,
        default=REPO_ROOT / "data",
        help="evidence chain 写盘根目录（默认 <repo>/data）",
    )
    p.add_argument(
        "--counter",
        type=Path,
        default=None,
        help="dry-run 计数器路径；未传则用真实 mode（写入 5）",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    book_dir = args.base_dir / args.book
    setting_path = book_dir / "setting.json"
    outline_path = book_dir / "outline.json"
    if not setting_path.exists() or not outline_path.exists():
        print(
            f"missing {setting_path} or {outline_path}; "
            f"please prepare data/{args.book}/{{setting,outline}}.json first",
            file=sys.stderr,
        )
        return 2

    with open(setting_path, encoding="utf-8") as fh:
        setting = json.load(fh)
    with open(outline_path, encoding="utf-8") as fh:
        outline = json.load(fh)

    # 真模式（防止 dry-run 永过遮蔽 blocked）
    counter_path = args.counter or (args.base_dir / ".planning_dry_run_counter")
    counter_path.parent.mkdir(parents=True, exist_ok=True)
    counter_path.write_text("5", encoding="utf-8")

    init_client = FixtureLLMClient(responders=_ink_init_responders())
    init_result = run_ink_init_review(
        book=args.book,
        setting=setting,
        llm_client=init_client,
        base_dir=args.base_dir,
        dry_run_counter_path=counter_path,
    )
    print("[ink-init]", json.dumps(init_result, ensure_ascii=False, indent=2))

    plan_client = FixtureLLMClient(responders=_ink_plan_responders())
    plan_result = run_ink_plan_review(
        book=args.book,
        outline=outline,
        llm_client=plan_client,
        base_dir=args.base_dir,
        dry_run_counter_path=counter_path,
    )
    print("[ink-plan]", json.dumps(plan_result, ensure_ascii=False, indent=2))

    blocked = init_result["effective_blocked"] or plan_result["effective_blocked"]
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
