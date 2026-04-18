#!/usr/bin/env python3
"""US-017 — 300 章 Shadow 压测（零 LLM 成本）

目标：在**完全不调用 LLM API** 的前提下，采集 G1-G5 性能指标，
为"300 万字不崩"主张提供首份经验数据。

架构：
    1. 预生成 N 章 mock 章节正文（每章 1-2KB 正常节奏文本，**读文件**替代 writer-agent）
    2. 直接驱动 Step 5（data-agent 索引）路径 — 纯 Python, 无 LLM
       - `SQLStateManager.upsert_entity` / `process_chapter_data` 写入 index.db
       - `StateManager.save_state` 写入 state.json
    3. 可选触发 SemanticChapterRetriever.recall 度量 G5 延迟
       （默认用 mock 打桩避免 sentence-transformers 30s 加载）
    4. 在 {50, 100, 150, 200, 250, 300} 里程碑采样 state.json / index.db 大小

G1 wall_time_per_chapter  - pipeline per-chapter ingest wall time
G2 state.json size         - JSON on disk at milestones
G3 index.db size           - SQLite on disk at milestones
G4 context pack size       - mock context bundle char/token estimate
G5 retriever latency       - recall p50/p95 (mock-hit by default; --real-retriever 切真)

CLI:
    python -m benchmark.e2e_shadow_300 --chapters 5 \\
        --report reports/perf-300ch-shadow-v15.md

**smoke-only 默认路径**：5 章 mock，CI 秒级。300 章实跑留用户手动触发。
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import statistics
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

# 兼容 pytest.ini 的 pythonpath：显式把 scripts / ink-writer/scripts 加入 sys.path，
# 否则 `python -m benchmark.e2e_shadow_300` CLI 跑时 `from runtime_compat import ...`
# 等轻依赖路径会失效。
_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (
    _REPO_ROOT / "scripts",
    _REPO_ROOT / "ink-writer" / "scripts",
    _REPO_ROOT / "ink-writer",
    _REPO_ROOT / "ink-writer" / "dashboard",
):
    _sp = str(_p)
    if _p.is_dir() and _sp not in sys.path:
        sys.path.insert(0, _sp)

# 里程碑章号（G2/G3 采样点）
DEFAULT_MILESTONES = (50, 100, 150, 200, 250, 300)
# 近似 1 token ≈ 1.7 中文字符（粗估）
TOKEN_PER_CHAR = 1.0 / 1.7


@dataclass
class MilestoneSample:
    chapter: int
    state_json_bytes: int
    index_db_bytes: int
    wall_time_s_cum: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "chapter": self.chapter,
            "state_json_kb": round(self.state_json_bytes / 1024, 2),
            "index_db_kb": round(self.index_db_bytes / 1024, 2),
            "wall_time_s_cum": round(self.wall_time_s_cum, 3),
        }


@dataclass
class ShadowMetrics:
    """G1-G5 aggregate metrics."""

    chapters: int = 0
    # G1
    wall_time_per_chapter_s: list[float] = field(default_factory=list)
    # G2/G3
    milestones: list[MilestoneSample] = field(default_factory=list)
    # G4
    context_pack_chars: list[int] = field(default_factory=list)
    # G5
    retriever_latency_ms: list[float] = field(default_factory=list)

    @property
    def g1_mean_s(self) -> float:
        return statistics.fmean(self.wall_time_per_chapter_s) if self.wall_time_per_chapter_s else 0.0

    @property
    def g1_p95_s(self) -> float:
        return _percentile(self.wall_time_per_chapter_s, 95)

    @property
    def g4_mean_chars(self) -> float:
        return statistics.fmean(self.context_pack_chars) if self.context_pack_chars else 0.0

    @property
    def g4_mean_tokens(self) -> float:
        return self.g4_mean_chars * TOKEN_PER_CHAR

    @property
    def g5_p50_ms(self) -> float:
        return _percentile(self.retriever_latency_ms, 50)

    @property
    def g5_p95_ms(self) -> float:
        return _percentile(self.retriever_latency_ms, 95)

    def to_dict(self) -> dict[str, Any]:
        return {
            "chapters": self.chapters,
            "g1_wall_time_per_chapter": {
                "mean_s": round(self.g1_mean_s, 4),
                "p95_s": round(self.g1_p95_s, 4),
                "count": len(self.wall_time_per_chapter_s),
            },
            "g2_g3_milestones": [m.to_dict() for m in self.milestones],
            "g4_context_pack": {
                "mean_chars": round(self.g4_mean_chars, 1),
                "mean_tokens_est": round(self.g4_mean_tokens, 1),
                "count": len(self.context_pack_chars),
            },
            "g5_retriever_latency": {
                "p50_ms": round(self.g5_p50_ms, 3),
                "p95_ms": round(self.g5_p95_ms, 3),
                "count": len(self.retriever_latency_ms),
            },
        }


def _percentile(values: list[float], pct: float) -> float:
    """Simple nearest-rank percentile."""
    if not values:
        return 0.0
    sorted_v = sorted(values)
    k = max(0, min(len(sorted_v) - 1, math.ceil(pct / 100.0 * len(sorted_v)) - 1))
    return float(sorted_v[k])


# ---------------------------------------------------------------------------
# Mock chapter generation — 1-2 KB 正常节奏文本
# ---------------------------------------------------------------------------

_MOCK_PARAGRAPHS = [
    "青衫少年站在云涯峰前，抬头看向那座笼罩在晨雾中的古朴山门。",
    "他握紧了腰间那柄陪伴三年的青锋剑，剑鞘上的纹路早已被掌心磨得发亮。",
    "「今日之后，我便要走一条与往日全然不同的路了。」少年低声自语，脚步却不曾犹豫。",
    "师兄端坐在石阶上，目光淡淡地扫过他：「你可想好了？踏入此门，便是凡身与天命的割席。」",
    "远处传来钟声，一下一下敲在胸腔里，像是替某个旧日的自己送行。",
    "少年点头。他想起了娘亲临终前攥着他的手腕，想起了村口老槐树下那个未兑现的承诺。",
    "风起，卷起他衣角的碎银纹绣。云深处，一声剑鸣忽然贯耳而来，锐利又清越。",
    "「去吧。」师兄抬手，衣袖下压着一枚尚带温热的玉佩，被递到他掌心。",
    "他握住玉佩，只觉那温度与娘亲留下的那枚何其相似。一时间喉头发紧，说不出话。",
    "云雾散开一线缝隙，山门后面的层层殿宇在日光里显出轮廓，像一场早已写好的梦。",
]


def _mock_write_chapter(chapter_num: int, *, target_chars: int = 1600) -> str:
    """生成一章伪正文（~1.5KB，正常节奏段落交替）。不调用任何 LLM。"""
    parts: list[str] = [f"第{chapter_num}章 · 云涯记（mock-shadow）\n"]
    accum = len(parts[0])
    idx = 0
    while accum < target_chars:
        para = _MOCK_PARAGRAPHS[idx % len(_MOCK_PARAGRAPHS)]
        parts.append(para)
        accum += len(para) + 1
        idx += 1
    return "\n".join(parts)


def _mock_data_payload(chapter_num: int) -> dict[str, Any]:
    """生成 data-agent 的 mock 输出（实体/场景列表，供 DB 写入）。"""
    return {
        "chapter": chapter_num,
        "title": f"第{chapter_num}章·云涯记",
        "location": "云涯峰",
        "word_count": 1600,
        "entities": [
            {
                "id": "protagonist",
                "type": "角色",
                "name": "林青衫",
                "tier": "核心",
                "desc": "主角，青衫剑客",
                "aliases": ["青衫", "少年"],
                "is_protagonist": True,
            },
            {
                "id": "shixiong",
                "type": "角色",
                "name": "大师兄",
                "tier": "重要",
                "desc": "入门引路人",
                "aliases": [],
                "is_protagonist": False,
            },
            {
                "id": "yunyafeng",
                "type": "地点",
                "name": "云涯峰",
                "tier": "重要",
                "desc": "宗门所在",
                "aliases": ["云涯山"],
                "is_protagonist": False,
            },
        ],
        "scenes": [
            {"index": 0, "start_line": 1, "end_line": 20},
            {"index": 1, "start_line": 21, "end_line": 40},
        ],
    }


# ---------------------------------------------------------------------------
# ShadowRunner — 核心骨架
# ---------------------------------------------------------------------------


class ShadowRunner:
    """300 章压测 runner（零 LLM）。"""

    def __init__(
        self,
        chapters: int,
        *,
        project_root: Optional[Path] = None,
        milestones: tuple[int, ...] = DEFAULT_MILESTONES,
        real_retriever: bool = False,
        retriever_sample_every: int = 10,
    ) -> None:
        self.chapters = chapters
        self.milestones = tuple(m for m in milestones if m <= chapters) or (chapters,)
        self.real_retriever = real_retriever
        self.retriever_sample_every = max(1, retriever_sample_every)

        self._owns_project = project_root is None
        if project_root is None:
            project_root = Path(tempfile.mkdtemp(prefix="shadow300_"))
        self.project_root = project_root
        (self.project_root / ".ink").mkdir(parents=True, exist_ok=True)
        (self.project_root / "正文").mkdir(parents=True, exist_ok=True)
        (self.project_root / "设定集").mkdir(parents=True, exist_ok=True)
        (self.project_root / "大纲").mkdir(parents=True, exist_ok=True)

        self.metrics = ShadowMetrics(chapters=chapters)
        self._config = None
        self._state_mgr = None
        self._sql_mgr = None

    # ------------------ lifecycle ------------------

    def cleanup(self) -> None:
        if self._owns_project and self.project_root.exists():
            shutil.rmtree(self.project_root, ignore_errors=True)

    def __enter__(self) -> "ShadowRunner":
        return self

    def __exit__(self, *args) -> None:
        self.cleanup()

    # ------------------ pipeline steps ------------------

    def _ensure_managers(self) -> None:
        """延迟初始化（避免 import 时加载重依赖）。"""
        if self._state_mgr is not None:
            return
        # 本地 import：避免顶层 import 时触发 sentence-transformers 等重模型
        from ink_writer.core.infra.config import DataModulesConfig
        from ink_writer.core.state.sql_state_manager import SQLStateManager, EntityData
        from ink_writer.core.state.state_manager import StateManager

        self._config = DataModulesConfig.from_project_root(self.project_root)
        # SQLStateManager 内部会创建 IndexManager 并初始化 index.db
        self._sql_mgr = SQLStateManager(self._config)
        # StateManager: 关闭 SQLite 同步（压测只看体积）避免和 SQLStateManager 串扰
        self._state_mgr = StateManager(self._config, enable_sqlite_sync=False)
        self._EntityData = EntityData  # noqa: attribute alias

    def _write_chapter_file(self, chapter: int, text: str) -> Path:
        path = self.project_root / "正文" / f"第{chapter:04d}章.md"
        path.write_text(text, encoding="utf-8")
        return path

    def _ingest_chapter(self, chapter: int, payload: dict[str, Any]) -> None:
        """Step 5（data-agent 索引）— 纯 Python DB 写入。"""
        self._ensure_managers()
        assert self._sql_mgr is not None

        # 写入实体（首章批量；后续仅更新 last_appearance）
        for ent in payload["entities"]:
            self._sql_mgr.upsert_entity(self._EntityData(
                id=ent["id"],
                type=ent["type"],
                name=ent["name"],
                tier=ent.get("tier", "装饰"),
                desc=ent.get("desc", ""),
                aliases=ent.get("aliases", []),
                first_appearance=chapter if chapter == 1 else 0,
                last_appearance=chapter,
                is_protagonist=ent.get("is_protagonist", False),
            ))

        # 写入章节元数据 + 场景（IndexManager.process_chapter_data mixin）
        self._sql_mgr._index_manager.process_chapter_data(
            chapter=payload["chapter"],
            title=payload["title"],
            location=payload["location"],
            word_count=payload["word_count"],
            entities=payload["entities"],
            scenes=payload["scenes"],
        )

        # state.json：更新进度 + 核心实体增量
        assert self._state_mgr is not None
        self._state_mgr.update_progress(chapter=chapter, words=payload["word_count"])
        self._state_mgr.save_state()

    def _measure_context_pack(self, chapter: int) -> int:
        """G4: 模拟 context-agent 打包的 prompt 字符数（取 state.json + 最近 5 章摘要长度）。"""
        state_size = 0
        if self._config is not None and self._config.state_file.exists():
            state_size = self._config.state_file.stat().st_size
        # 模拟 context 打包开销：state 摘要 + 最近 5 章片段
        return int(state_size * 0.3 + min(chapter, 5) * 400)

    def _measure_retriever(self, chapter: int) -> float:
        """G5: 测 retriever.recall 延迟（ms）。"""
        if self.real_retriever:
            return self._measure_retriever_real(chapter)
        # 默认 mock：简单 dict 查表，延迟 < 1ms
        t0 = time.perf_counter()
        _ = [c for c in range(max(1, chapter - 5), chapter)]
        return (time.perf_counter() - t0) * 1000.0

    def _measure_retriever_real(self, chapter: int) -> float:
        """可选真 retriever（触发 sentence-transformers 加载；不推荐 smoke）。"""
        from ink_writer.semantic_recall import (
            ChapterVectorIndex,
            SemanticChapterRetriever,
            SemanticRecallConfig,
        )
        from ink_writer.semantic_recall.chapter_index import ChapterCard

        # 一次性构建索引（首次调用时）
        if not hasattr(self, "_retriever"):
            idx_dir = self.project_root / ".ink" / "chapter_vec"
            idx_dir.mkdir(parents=True, exist_ok=True)
            idx = ChapterVectorIndex(idx_dir)
            cards = [
                ChapterCard(
                    chapter=i,
                    summary=f"第{i}章梗概",
                    goal="突破境界",
                    conflict="门派试炼",
                    result="小胜",
                    next_chapter_bridge="留悬念",
                    unresolved_questions=[],
                    key_facts=[],
                    involved_entities=["林青衫"],
                    plot_progress=[],
                )
                for i in range(1, chapter + 1)
            ]
            idx.build(cards)
            self._retriever = SemanticChapterRetriever(idx, SemanticRecallConfig())

        t0 = time.perf_counter()
        self._retriever.recall(query="林青衫突破", chapter_num=chapter)
        return (time.perf_counter() - t0) * 1000.0

    # ------------------ main loop ------------------

    def run(self, *, progress_cb: Optional[Callable[[int], None]] = None) -> ShadowMetrics:
        """主循环：逐章 mock 写作 → DB ingest → 采样。"""
        start = time.perf_counter()
        cum_time = 0.0

        for ch in range(1, self.chapters + 1):
            t0 = time.perf_counter()
            # Step 0-4: mock writer（读/写文件；零 LLM）
            text = _mock_write_chapter(ch)
            self._write_chapter_file(ch, text)
            # Step 5: data-agent ingest
            payload = _mock_data_payload(ch)
            self._ingest_chapter(ch, payload)
            # Step 6: mock polish/checker — no-op

            per_ch = time.perf_counter() - t0
            cum_time += per_ch
            self.metrics.wall_time_per_chapter_s.append(per_ch)

            # G4: context pack
            self.metrics.context_pack_chars.append(self._measure_context_pack(ch))

            # G5: retriever latency（按 sample_every 采样）
            if ch % self.retriever_sample_every == 0 or ch == self.chapters:
                self.metrics.retriever_latency_ms.append(self._measure_retriever(ch))

            # G2/G3: milestone
            if ch in self.milestones:
                self.metrics.milestones.append(self._snapshot_milestone(ch, cum_time))

            if progress_cb is not None:
                progress_cb(ch)

        # 若最后一章不是 milestone，补一个终点 sample
        if self.metrics.milestones and self.metrics.milestones[-1].chapter != self.chapters:
            self.metrics.milestones.append(
                self._snapshot_milestone(self.chapters, cum_time)
            )
        elif not self.metrics.milestones:
            self.metrics.milestones.append(
                self._snapshot_milestone(self.chapters, cum_time)
            )

        self.metrics.chapters = self.chapters
        _ = time.perf_counter() - start  # 总时长，保留占位
        return self.metrics

    def _snapshot_milestone(self, chapter: int, wall_time_cum: float) -> MilestoneSample:
        assert self._config is not None
        state_b = (
            self._config.state_file.stat().st_size
            if self._config.state_file.exists() else 0
        )
        idx_b = (
            self._config.index_db.stat().st_size
            if self._config.index_db.exists() else 0
        )
        return MilestoneSample(
            chapter=chapter,
            state_json_bytes=state_b,
            index_db_bytes=idx_b,
            wall_time_s_cum=wall_time_cum,
        )


# ---------------------------------------------------------------------------
# Report generator
# ---------------------------------------------------------------------------

def generate_report(metrics: ShadowMetrics, output_path: Path, *, smoke: bool) -> None:
    """产出 reports/perf-300ch-shadow-v15.md（含 G1-G5 表格）。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    header_note = (
        "> **SMOKE 模式**（章数 <300）：本次运行仅用于骨架验证，下表不是 300 章真数字。"
        if smoke else
        "> **FULL 模式**：以下为 300 章真实 mock 压测采样。"
    )

    # G1
    g1_block = (
        f"| 平均 | {metrics.g1_mean_s*1000:.2f} ms |\n"
        f"| p95 | {metrics.g1_p95_s*1000:.2f} ms |\n"
        f"| 样本数 | {len(metrics.wall_time_per_chapter_s)} |"
    )

    # G2/G3
    rows = []
    for m in metrics.milestones:
        rows.append(
            f"| {m.chapter} | {m.state_json_bytes/1024:.2f} | "
            f"{m.index_db_bytes/1024:.2f} | {m.wall_time_s_cum:.3f} |"
        )
    g23_block = "\n".join(rows) if rows else "| — | — | — | — |"

    # G4
    g4_block = (
        f"| 平均 char | {metrics.g4_mean_chars:.0f} |\n"
        f"| 估算 token | {metrics.g4_mean_tokens:.0f} |\n"
        f"| 样本数 | {len(metrics.context_pack_chars)} |"
    )

    # G5
    g5_block = (
        f"| p50 | {metrics.g5_p50_ms:.3f} ms |\n"
        f"| p95 | {metrics.g5_p95_ms:.3f} ms |\n"
        f"| 样本数 | {len(metrics.retriever_latency_ms)} |"
    )

    report = f"""# 300 章 Shadow 压测报告（v15 / US-017）

{header_note}

本报告由 `python -m benchmark.e2e_shadow_300` 生成，**零 LLM 调用**。
writer-agent / polish / checker 全部以 mock 形式替代（读文件生成章节、
模拟 data-agent payload），仅 data-agent Step 5 的 DB 写入走真实 Python 路径。

## 运行命令

```bash
# smoke（CI 默认，5 章）
python -m benchmark.e2e_shadow_300 --chapters 5 \\
    --report reports/perf-300ch-shadow-v15.md

# 全量（用户手动触发，300 章）
python -m benchmark.e2e_shadow_300 --chapters 300 \\
    --report reports/perf-300ch-shadow-v15.md

# 真 retriever 延迟（需首次加载 sentence-transformers，~30s）
python -m benchmark.e2e_shadow_300 --chapters 300 --real-retriever
```

## G1 — 单章 wall time（pipeline ingest 路径，零 LLM）

| 指标 | 值 |
|------|----|
{g1_block}

## G2/G3 — state.json / index.db 体积里程碑

| 章号 | state.json (KB) | index.db (KB) | 累计 wall (s) |
|------|-----------------|---------------|---------------|
{g23_block}

## G4 — context-agent pack size（mock 估算）

| 指标 | 值 |
|------|----|
{g4_block}

## G5 — SemanticChapterRetriever.recall 延迟

| 指标 | 值 |
|------|----|
{g5_block}

## 趋势示意

```mermaid
graph LR
    A[第1章] --> B[第50章]
    B --> C[第100章]
    C --> D[第200章]
    D --> E[第300章]
    A -.state.json/index.db 随章数线性增长.-> E
```

## 注意事项

- **真数字待人工触发**：300 章 full run 约需 10-30 分钟（纯 Python IO，无 LLM）。
  CI 默认仅跑 5 章 smoke（`tests/benchmark/test_shadow_runner_smoke.py`），避免 CI 超时。
- **README FAQ "100 章 7 小时"未更新**：需 full run 产出真数字后再改写。
  TODO：运行 `--chapters 100` 后用 G1 实测数据替换 FAQ 文案。
- G4/G5 mock 默认关闭真 retriever（避免 sentence-transformers 加载），
  用 `--real-retriever` 开启真实 FAISS 检索延迟测量。
"""
    output_path.write_text(report, encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="300 章 shadow 压测（零 LLM，US-017）"
    )
    parser.add_argument(
        "--chapters", type=int, default=5,
        help="总章数（CI smoke 默认 5；用户手动触发可传 300）",
    )
    parser.add_argument(
        "--report", type=str, default="reports/perf-300ch-shadow-v15.md",
        help="Markdown 报告输出路径",
    )
    parser.add_argument(
        "--metrics-json", type=str, default=None,
        help="可选：metrics JSON 输出路径",
    )
    parser.add_argument(
        "--real-retriever", action="store_true",
        help="启用真 SemanticChapterRetriever（会加载 sentence-transformers，~30s 冷启动）",
    )
    parser.add_argument(
        "--project-root", type=str, default=None,
        help="指定项目根目录（默认 tmp 目录自动清理）",
    )
    args = parser.parse_args(argv)

    proj = Path(args.project_root).resolve() if args.project_root else None
    print(f"[US-017] Shadow run chapters={args.chapters} "
          f"real_retriever={args.real_retriever}", file=sys.stderr)

    runner = ShadowRunner(
        chapters=args.chapters,
        project_root=proj,
        real_retriever=args.real_retriever,
    )
    try:
        metrics = runner.run(
            progress_cb=lambda ch: (
                print(f"  [ch {ch}/{args.chapters}]", file=sys.stderr)
                if ch % 10 == 0 or ch == args.chapters else None
            ),
        )
        smoke = args.chapters < 300
        generate_report(metrics, Path(args.report), smoke=smoke)
        if args.metrics_json:
            Path(args.metrics_json).parent.mkdir(parents=True, exist_ok=True)
            Path(args.metrics_json).write_text(
                json.dumps(metrics.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        print(f"[US-017] done. report={args.report}", file=sys.stderr)
        print(json.dumps(metrics.to_dict(), ensure_ascii=False, indent=2))
    finally:
        runner.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
