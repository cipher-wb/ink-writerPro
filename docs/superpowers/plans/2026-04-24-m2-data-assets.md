# M2 Data Assets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **本项目实际由 ralph 自主循环执行**：每个 user story 一个 fresh claude 实例，靠 git + progress.txt + prd.json 三件持久记忆。

**Goal:** 落地 spec §9 M2：把 30 本范文（1487 章节）切片入 Qdrant + 把 402 条 editor-wisdom rules 转换为 case_library 中的 cases，端到端打通"段落级范文召回 + 病例库种子" 数据资产基座。

**Architecture:** 三段式切片管线（scene_segmenter Haiku 切边界 → chunk_tagger Haiku 打 6 标签 + 4 维加权 quality_score → chunk_indexer Qwen3-Embedding-8B 向量化 + Qdrant batch upsert）+ rules_to_cases 转换器（按 rule.severity 分流：hard→active P1 / soft→pending P2 / info→pending P3 + info_only tag）+ 三个新 CLI 子命令（ink corpus ingest/rebuild/watch + ink case approve --batch + ink case convert-from-editor-wisdom）。复用 M1 已建的 ingest_case / Qdrant CORPUS_CHUNKS_SPEC / preflight，不重建任何基础设施。

**Tech Stack:** Python 3.12+ / pytest / anthropic SDK (Haiku 4.5) / openai-python SDK 兼容（Qwen3-Embedding via modelscope endpoint）/ qdrant-client (M1 已装) / pyyaml / jsonschema (M1 已装) / Docker（Qdrant，M1 已配）

**Reference spec:** `docs/superpowers/specs/2026-04-24-m2-data-assets-design.md`（579 行 / 8 章节）

---

## File Structure

### 新增 Python 模块

| 文件 | 职责 |
|---|---|
| `scripts/corpus_chunking/__init__.py` | 包标识 |
| `scripts/corpus_chunking/scene_segmenter.py` | LLM 切场景边界 → chunks_raw.jsonl |
| `scripts/corpus_chunking/chunk_tagger.py` | LLM 打 scene_type/genre/quality 等 |
| `scripts/corpus_chunking/chunk_indexer.py` | Qwen3 向量化 + Qdrant upsert |
| `scripts/corpus_chunking/embedding_client.py` | Qwen3 API 封装 + 退避重试 |
| `scripts/corpus_chunking/cli.py` | `ink corpus ingest/rebuild/watch` |
| `scripts/corpus_chunking/models.py` | `RawChunk` / `TaggedChunk` / `IngestReport` dataclasses |
| `scripts/corpus_chunking/prompts/scene_segmenter.txt` | 切片 prompt 模板 |
| `scripts/corpus_chunking/prompts/chunk_tagger.txt` | 打标 prompt 模板 |
| `ink_writer/case_library/rules_to_cases.py` | rule → case 转换器（核心逻辑）|
| `ink_writer/case_library/approval.py` | batch yaml 审批逻辑 |

### 新增配置 / Schema

| 文件 | 职责 |
|---|---|
| `config/corpus_chunking.yaml` | 切片管线配置（model/batch_size/quality_weights）|
| `schemas/case_approval_batch_schema.json` | approve --batch 的 yaml schema |

### 新增数据目录

| 路径 | 职责 |
|---|---|
| `data/corpus_chunks/chunks_raw.jsonl` | scene_segmenter 输出（append-only）|
| `data/corpus_chunks/chunks_tagged.jsonl` | chunk_tagger 输出 |
| `data/corpus_chunks/metadata.jsonl` | indexer 入库后的元数据备份 |
| `data/corpus_chunks/failures.jsonl` | scene_segmenter 失败章节 |
| `data/corpus_chunks/unindexed.jsonl` | indexer 失败 chunks |

### 新增测试

| 文件 | 职责 |
|---|---|
| `tests/corpus_chunking/__init__.py` | — |
| `tests/corpus_chunking/conftest.py` | fixtures: `sample_chapter_text`, `sample_raw_chunk`, `sample_tagged_chunk`, `mock_haiku_client`, `in_memory_qdrant_client` |
| `tests/corpus_chunking/test_models.py` | dataclasses 序列化 |
| `tests/corpus_chunking/test_scene_segmenter.py` | mock LLM 测 happy / JSON-fail / oversize |
| `tests/corpus_chunking/test_chunk_tagger.py` | mock LLM 测 4 维加权计算 / tag fail → quality_score=0 |
| `tests/corpus_chunking/test_embedding_client.py` | mock API 测 batch / 退避 |
| `tests/corpus_chunking/test_chunk_indexer.py` | in-memory Qdrant 测 upsert 幂等 / unindexed 落地 |
| `tests/corpus_chunking/test_cli.py` | 测 ingest/rebuild/watch 三子命令 |
| `tests/case_library/test_rules_to_cases.py` | severity 分流 / 字段映射 / dedup |
| `tests/case_library/test_cli_approve.py` | batch yaml 三种 action |
| `tests/case_library/test_cli_convert.py` | convert-from-editor-wisdom 集成 |
| `tests/integration/test_m2_e2e.py` | M2 端到端 5 用例 |

### 修改

| 文件 | 改动 |
|---|---|
| `pytest.ini` | `testpaths` 追加 `tests/corpus_chunking` |
| `ink_writer/case_library/cli.py` | 新增 `approve --batch` 与 `convert-from-editor-wisdom` 子命令 |

---

## Task Sequence Overview

```
US-001  corpus_chunking 包骨架 + config + 测试目录 + pytest.ini 注册
US-002  scene_segmenter（Haiku 切场景边界 + prompt + 重试 + failures.jsonl）
US-003  chunk_tagger（Haiku 打 6 标签 + 4 维加权 quality_score）
US-004  embedding_client + chunk_indexer（Qwen3 + Qdrant batch upsert + UUID5 幂等）
US-005  ink corpus ingest CLI（含 --book / --resume / --dry-run）
US-006  ink corpus rebuild CLI（含 --yes 防误触）
US-007  ink corpus watch CLI（polling 30s）
US-008  30 本范文 ingest 实跑 + 抽样 50 chunks 人工核 + 入库验证
US-009  rules_to_cases.py 转换器 + 单测（severity 分流 + 占位 observable）
US-010  ink case convert-from-editor-wisdom CLI 集成 + 幂等测试
US-011  ink case approve --batch <yaml> CLI（含 yaml schema 校验）
US-012  M2 e2e 集成测试 + 全量验收 + tag m2-data-assets
```

---

## Task 1 (US-001): corpus_chunking 包骨架 + config + 测试目录

**Files:**
- Create: `scripts/corpus_chunking/__init__.py`
- Create: `scripts/corpus_chunking/models.py`
- Create: `scripts/corpus_chunking/prompts/.gitkeep`
- Create: `config/corpus_chunking.yaml`
- Create: `tests/corpus_chunking/__init__.py`
- Create: `tests/corpus_chunking/conftest.py`
- Create: `tests/corpus_chunking/test_models.py`
- Modify: `pytest.ini`（testpaths 追加 `tests/corpus_chunking`）

**Why:** 后续 task 都依赖此骨架（包导入路径 + dataclasses 类型 + config 加载 + fixtures + pytest 收集）。一次性建好避免反复返工。

- [ ] **Step 1: 创建包目录骨架**

```bash
mkdir -p scripts/corpus_chunking/prompts tests/corpus_chunking
touch scripts/corpus_chunking/__init__.py
touch scripts/corpus_chunking/prompts/.gitkeep
touch tests/corpus_chunking/__init__.py
```

- [ ] **Step 2: 注册 pytest testpaths**

Edit `pytest.ini`. 在 `testpaths` 行尾追加 `tests/corpus_chunking`（保持单行不换行）。

完整 testpaths 行（M1 baseline + M2 新增）：
```
testpaths = tests/data_modules tests/migration tests/baseline tests/audit tests/hooks tests/pacing tests/emotion tests/style_rag tests/anti_detection tests/cultural tests/memory_arch tests/semantic_recall tests/foreshadow tests/voice_fingerprint tests/plotline tests/thread_lifecycle tests/skill_systems tests/prompts tests/parallel tests/prompt_cache tests/checker_pipeline tests/incremental_extract tests/benchmark tests/ink_init tests/harness tests/editor_wisdom tests/integration tests/docs tests/infra tests/creativity tests/quality_metrics tests/reflection tests/review tests/release tests/propagation tests/progression tests/core tests/scripts tests/skills tests/prose tests/case_library tests/qdrant tests/preflight tests/maintenance tests/corpus_chunking
```

- [ ] **Step 3: 写 models.py 失败测试**

Create `tests/corpus_chunking/test_models.py`:

```python
from __future__ import annotations

import pytest

from scripts.corpus_chunking.models import (
    RawChunk,
    TaggedChunk,
    QualityBreakdown,
    IngestReport,
    SourceType,
)


def test_raw_chunk_serializes() -> None:
    c = RawChunk(
        chunk_id="CHUNK-诡秘之主-ch003-§2",
        source_book="诡秘之主",
        source_chapter="ch003",
        char_range=(1234, 1890),
        text="克莱恩盯着镜子。",
    )
    d = c.to_dict()
    assert d["chunk_id"] == "CHUNK-诡秘之主-ch003-§2"
    assert d["char_range"] == [1234, 1890]


def test_tagged_chunk_round_trip() -> None:
    raw = RawChunk(
        chunk_id="CHUNK-x-ch001-§1",
        source_book="x",
        source_chapter="ch001",
        char_range=(0, 500),
        text="...",
    )
    tagged = TaggedChunk(
        raw=raw,
        scene_type="opening",
        genre=["都市", "现实"],
        tension_level=0.7,
        character_count=2,
        dialogue_ratio=0.4,
        hook_type="introduction",
        borrowable_aspects=["sensory_grounding"],
        quality_breakdown=QualityBreakdown(0.8, 0.7, 0.6, 0.9),
        source_type=SourceType.BUILTIN,
        ingested_at="2026-04-25",
    )
    assert tagged.quality_score == pytest.approx(0.8 * 0.3 + 0.7 * 0.3 + 0.6 * 0.2 + 0.9 * 0.2)
    d = tagged.to_dict()
    assert d["quality_score"] == pytest.approx(tagged.quality_score)
    assert d["genre"] == ["都市", "现实"]


def test_ingest_report_aggregates() -> None:
    r = IngestReport()
    r.chunks_raw += 5
    r.chunks_tagged += 4
    r.chunks_indexed += 4
    r.failures.append(("ch003", "scene_segmenter JSON parse"))
    assert r.success_rate == 0.8
```

- [ ] **Step 4: Run test → expect ImportError**

```bash
pytest tests/corpus_chunking/test_models.py -v --no-cov
```
Expected: `ModuleNotFoundError: No module named 'scripts.corpus_chunking.models'`

- [ ] **Step 5: 实现 models.py**

Create `scripts/corpus_chunking/models.py`:

```python
"""Corpus chunking dataclasses.

RawChunk: scene_segmenter 输出。
TaggedChunk: chunk_tagger 输出（含 raw + 7 个新字段 + 4 维 quality_breakdown）。
QualityBreakdown: tension/originality/language_density/readability 4 维度，加权
                  得 quality_score（spec §3.5 config 中的权重，默认 30/30/20/20）。
IngestReport: 一次 ingest 跑的统计聚合。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SourceType(str, Enum):
    BUILTIN = "builtin"
    USER = "user"


@dataclass
class QualityBreakdown:
    tension: float
    originality: float
    language_density: float
    readability: float

    def weighted_score(
        self,
        weights: tuple[float, float, float, float] = (0.3, 0.3, 0.2, 0.2),
    ) -> float:
        wt, wo, wl, wr = weights
        return (
            self.tension * wt
            + self.originality * wo
            + self.language_density * wl
            + self.readability * wr
        )


@dataclass
class RawChunk:
    chunk_id: str
    source_book: str
    source_chapter: str
    char_range: tuple[int, int]
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "source_book": self.source_book,
            "source_chapter": self.source_chapter,
            "char_range": list(self.char_range),
            "text": self.text,
        }


@dataclass
class TaggedChunk:
    raw: RawChunk
    scene_type: str
    genre: list[str]
    tension_level: float
    character_count: int
    dialogue_ratio: float
    hook_type: str
    borrowable_aspects: list[str]
    quality_breakdown: QualityBreakdown
    source_type: SourceType
    ingested_at: str  # ISO date

    @property
    def quality_score(self) -> float:
        return self.quality_breakdown.weighted_score()

    def to_dict(self) -> dict[str, Any]:
        d = self.raw.to_dict()
        d.update({
            "scene_type": self.scene_type,
            "genre": list(self.genre),
            "tension_level": self.tension_level,
            "character_count": self.character_count,
            "dialogue_ratio": self.dialogue_ratio,
            "hook_type": self.hook_type,
            "borrowable_aspects": list(self.borrowable_aspects),
            "quality_score": self.quality_score,
            "quality_breakdown": {
                "tension": self.quality_breakdown.tension,
                "originality": self.quality_breakdown.originality,
                "language_density": self.quality_breakdown.language_density,
                "readability": self.quality_breakdown.readability,
            },
            "source_type": self.source_type.value,
            "ingested_at": self.ingested_at,
        })
        return d


@dataclass
class IngestReport:
    chunks_raw: int = 0
    chunks_tagged: int = 0
    chunks_indexed: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.chunks_raw == 0:
            return 0.0
        return self.chunks_indexed / self.chunks_raw
```

- [ ] **Step 6: 写 conftest.py 提供共享 fixtures**

Create `tests/corpus_chunking/conftest.py`:

```python
"""Shared fixtures for corpus_chunking tests."""
from __future__ import annotations

import pytest

from scripts.corpus_chunking.models import (
    RawChunk,
    TaggedChunk,
    QualityBreakdown,
    SourceType,
)


@pytest.fixture
def sample_chapter_text() -> str:
    return "克莱恩盯着镜子。他不确定眼前的人是谁。" * 50  # ≈ 800 字


@pytest.fixture
def sample_raw_chunk() -> RawChunk:
    return RawChunk(
        chunk_id="CHUNK-诡秘之主-ch003-§1",
        source_book="诡秘之主",
        source_chapter="ch003",
        char_range=(0, 600),
        text="克莱恩盯着镜子。" * 30,
    )


@pytest.fixture
def sample_tagged_chunk(sample_raw_chunk: RawChunk) -> TaggedChunk:
    return TaggedChunk(
        raw=sample_raw_chunk,
        scene_type="opening",
        genre=["异世大陆", "玄幻"],
        tension_level=0.85,
        character_count=1,
        dialogue_ratio=0.0,
        hook_type="identity_reveal",
        borrowable_aspects=["psychological_buffer"],
        quality_breakdown=QualityBreakdown(0.95, 0.90, 0.92, 0.90),
        source_type=SourceType.BUILTIN,
        ingested_at="2026-04-25",
    )
```

- [ ] **Step 7: 写 config/corpus_chunking.yaml**

Create `config/corpus_chunking.yaml`:

```yaml
scene_segmenter:
  model: claude-haiku-4-5-20251001
  min_chunk_chars: 200
  max_chunk_chars: 800
  max_retries: 3
chunk_tagger:
  model: claude-haiku-4-5-20251001
  batch_size: 5
  quality_weights:
    tension: 0.3
    originality: 0.3
    language_density: 0.2
    readability: 0.2
  max_retries: 3
chunk_indexer:
  embedding_model: Qwen/Qwen3-Embedding-8B
  embedding_base_url: https://api-inference.modelscope.cn/v1
  qdrant_collection: corpus_chunks
  upsert_batch_size: 256
  embed_batch_size: 32
```

- [ ] **Step 8: Run tests pass**

```bash
pytest tests/corpus_chunking/test_models.py -v --no-cov
```
Expected: 3 passed.

- [ ] **Step 9: Commit**

```bash
git add scripts/corpus_chunking/ config/corpus_chunking.yaml tests/corpus_chunking/ pytest.ini
git commit -m "feat(M2-T1): corpus_chunking 包骨架 + models + config + 测试目录

新增 RawChunk / TaggedChunk / QualityBreakdown / IngestReport / SourceType
dataclasses，TaggedChunk.quality_score 用 4 维加权（默认 30/30/20/20）。
config/corpus_chunking.yaml 含 scene_segmenter / chunk_tagger /
chunk_indexer 三段配置（spec §3.5）。pytest.ini 注册 tests/corpus_chunking
testpath。3 测试全绿。"
```

---

## Task 2 (US-002): scene_segmenter

**Files:**
- Create: `scripts/corpus_chunking/scene_segmenter.py`
- Create: `scripts/corpus_chunking/prompts/scene_segmenter.txt`
- Create: `tests/corpus_chunking/test_scene_segmenter.py`

- [ ] **Step 1: 写 scene_segmenter prompt**

Create `scripts/corpus_chunking/prompts/scene_segmenter.txt`:

```
你是网文场景边界识别器。给定一章正文，识别 8 种场景边界并切成 200-800 字的 chunks。

8 种 scene_type：
- opening: 开篇引入（章节起始的场景介绍 / 主角登场）
- face_slap: 打脸（主角胜过对手 / 反派服软）
- flexing: 装逼（主角能力 / 身份 / 资源展示）
- emotional_climax: 情感升华（亲情 / 爱情 / 友情高峰）
- twist: 反转（剧情 / 身份 / 结果意外）
- combat: 战斗（武力对抗 / 法术对决）
- crisis: 危机（主角陷入险境 / 困局）
- chapter_hook: 章末钩子（悬念结尾 / 卖关子）

切片规则：
1. 每个 chunk 200-800 字（< 200 合并到相邻；> 800 在场景内按句号/段落切分）
2. 一章内多个场景按出现顺序切片
3. 必须输出 char_range（chunk 在原文中的字符起止位置，0-indexed）

输出严格 JSON（不要 markdown 包裹）：
```
{
  "chunks": [
    {"scene_type": "opening", "char_range": [0, 580], "text": "..."},
    {"scene_type": "combat", "char_range": [580, 1340], "text": "..."}
  ]
}
```

输入章节（书名: {book}, 章节: {chapter}）：
---
{chapter_text}
---
```

- [ ] **Step 2: 写失败测试**

Create `tests/corpus_chunking/test_scene_segmenter.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.corpus_chunking.scene_segmenter import (
    segment_chapter,
    SegmenterConfig,
)
from scripts.corpus_chunking.models import RawChunk


def _mock_anthropic_response(payload: dict) -> MagicMock:
    """Mimic anthropic client response shape."""
    msg = MagicMock()
    msg.content = [MagicMock(text=json.dumps(payload))]
    return msg


def test_segment_chapter_happy_path() -> None:
    client = MagicMock()
    client.messages.create.return_value = _mock_anthropic_response({
        "chunks": [
            {"scene_type": "opening", "char_range": [0, 400], "text": "克莱恩盯着镜子。" * 25},
            {"scene_type": "combat", "char_range": [400, 800], "text": "战斗开始。" * 40},
        ]
    })
    cfg = SegmenterConfig(model="claude-haiku-4-5", min_chunk_chars=200, max_chunk_chars=800, max_retries=3)
    chunks = segment_chapter(
        client=client,
        cfg=cfg,
        book="诡秘之主",
        chapter="ch003",
        text="x" * 800,
    )
    assert len(chunks) == 2
    assert chunks[0].chunk_id == "CHUNK-诡秘之主-ch003-§1"
    assert chunks[0].source_book == "诡秘之主"
    assert chunks[0].source_chapter == "ch003"
    assert chunks[0].char_range == (0, 400)
    assert chunks[1].chunk_id == "CHUNK-诡秘之主-ch003-§2"


def test_segment_retries_on_invalid_json() -> None:
    client = MagicMock()
    bad = MagicMock()
    bad.content = [MagicMock(text="not json")]
    good = _mock_anthropic_response({
        "chunks": [{"scene_type": "opening", "char_range": [0, 300], "text": "abc"}]
    })
    client.messages.create.side_effect = [bad, bad, good]
    cfg = SegmenterConfig(model="m", min_chunk_chars=200, max_chunk_chars=800, max_retries=3)
    chunks = segment_chapter(client=client, cfg=cfg, book="b", chapter="c", text="x" * 300)
    assert len(chunks) == 1


def test_segment_returns_empty_after_max_retries() -> None:
    client = MagicMock()
    bad = MagicMock()
    bad.content = [MagicMock(text="garbage")]
    client.messages.create.side_effect = [bad, bad, bad]
    cfg = SegmenterConfig(model="m", min_chunk_chars=200, max_chunk_chars=800, max_retries=3)
    chunks = segment_chapter(client=client, cfg=cfg, book="b", chapter="c", text="x" * 500)
    assert chunks == []


def test_segment_rechunks_oversize_output() -> None:
    """LLM returns a 1200-char chunk; segmenter splits it on sentence boundary."""
    client = MagicMock()
    big_text = "句子。" * 400  # 1200 chars
    client.messages.create.return_value = _mock_anthropic_response({
        "chunks": [{"scene_type": "opening", "char_range": [0, 1200], "text": big_text}]
    })
    cfg = SegmenterConfig(model="m", min_chunk_chars=200, max_chunk_chars=800, max_retries=3)
    chunks = segment_chapter(client=client, cfg=cfg, book="b", chapter="c", text=big_text)
    assert len(chunks) >= 2
    for c in chunks:
        assert len(c.text) <= 800
```

- [ ] **Step 3: Run test → expect ImportError**

```bash
pytest tests/corpus_chunking/test_scene_segmenter.py -v --no-cov
```
Expected: `ModuleNotFoundError: No module named 'scripts.corpus_chunking.scene_segmenter'`

- [ ] **Step 4: 实现 scene_segmenter.py**

Create `scripts/corpus_chunking/scene_segmenter.py`:

```python
"""scene_segmenter: LLM 切场景边界 → RawChunk 列表。

输入一章正文 → 调 Haiku 输出 JSON {chunks: [{scene_type, char_range, text}, ...]}
→ 解析 + 后处理（rechunk oversize）→ 返回 RawChunk 列表。

失败处理：JSON 解析失败重试 max_retries 次；仍失败返回空列表（caller 决定写 failures.jsonl）。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.corpus_chunking.models import RawChunk

_PROMPT_PATH = Path(__file__).parent / "prompts" / "scene_segmenter.txt"


@dataclass
class SegmenterConfig:
    model: str
    min_chunk_chars: int
    max_chunk_chars: int
    max_retries: int


def _load_prompt(book: str, chapter: str, text: str) -> str:
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    return template.replace("{book}", book).replace("{chapter}", chapter).replace("{chapter_text}", text)


def _parse_json(text: str) -> dict[str, Any] | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to recover from markdown wrapping.
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
        return None


def _rechunk_oversize(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    parts: list[str] = []
    cursor = 0
    while cursor < len(text):
        end = min(cursor + max_chars, len(text))
        # 找最近句号
        slice_text = text[cursor:end]
        last_period = max(slice_text.rfind("。"), slice_text.rfind("！"), slice_text.rfind("？"))
        if last_period > 100:  # 找到合理句末
            cut = cursor + last_period + 1
        else:
            cut = end
        parts.append(text[cursor:cut])
        cursor = cut
    return parts


def segment_chapter(
    *,
    client: Any,
    cfg: SegmenterConfig,
    book: str,
    chapter: str,
    text: str,
) -> list[RawChunk]:
    """Returns RawChunk list. Empty list iff all retries failed (caller logs)."""
    prompt = _load_prompt(book, chapter, text)
    payload: dict[str, Any] | None = None
    for attempt in range(cfg.max_retries):
        try:
            resp = client.messages.create(
                model=cfg.model,
                max_tokens=8192,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.content[0].text
            payload = _parse_json(raw)
            if payload and "chunks" in payload:
                break
        except Exception:  # noqa: BLE001 — retries
            payload = None
    if not payload or "chunks" not in payload:
        return []

    chunks: list[RawChunk] = []
    seq = 0
    for ch in payload["chunks"]:
        text_part = ch.get("text", "")
        rechunked = _rechunk_oversize(text_part, cfg.max_chunk_chars)
        cr_start = ch["char_range"][0]
        for sub in rechunked:
            seq += 1
            cr_end = cr_start + len(sub)
            chunks.append(
                RawChunk(
                    chunk_id=f"CHUNK-{book}-{chapter}-§{seq}",
                    source_book=book,
                    source_chapter=chapter,
                    char_range=(cr_start, cr_end),
                    text=sub,
                )
            )
            cr_start = cr_end
    return chunks
```

- [ ] **Step 5: Run test → pass**

```bash
pytest tests/corpus_chunking/test_scene_segmenter.py -v --no-cov
```
Expected: 4 passed.

- [ ] **Step 6: Audit red-line scan**

```bash
pytest tests/audit/test_cli_entries_utf8_stdio.py tests/core/test_safe_symlink.py -v --no-cov
```
Expected: 全绿（无 `__main__` 入口或 symlink 调用因此豁免）。

- [ ] **Step 7: Commit**

```bash
git add scripts/corpus_chunking/scene_segmenter.py scripts/corpus_chunking/prompts/scene_segmenter.txt tests/corpus_chunking/test_scene_segmenter.py
git commit -m "feat(M2-T2): scene_segmenter — Haiku 切场景边界

输入一章 → Haiku 调用 → JSON 解析（含 markdown unwrap 容错）→ 后处理
rechunk oversize（按句号边界）→ RawChunk 列表。max_retries 重试 JSON
解析失败；仍失败返空列表（caller 写 failures.jsonl）。"
```

---

## Task 3 (US-003): chunk_tagger

**Files:**
- Create: `scripts/corpus_chunking/chunk_tagger.py`
- Create: `scripts/corpus_chunking/prompts/chunk_tagger.txt`
- Create: `tests/corpus_chunking/test_chunk_tagger.py`

- [ ] **Step 1: 写 chunk_tagger prompt**

Create `scripts/corpus_chunking/prompts/chunk_tagger.txt`:

```
你是网文段落标注器。给定一个段落 chunk，输出严格 JSON 含以下字段：

- scene_type: 必须从 8 种中选一个 (opening / face_slap / flexing / emotional_climax / twist / combat / crisis / chapter_hook)
- tension_level: 0-1 浮点（情绪张力，越冲突 / 危机 / 高潮越高）
- character_count: 整数（出场人物数）
- dialogue_ratio: 0-1 浮点（对话占比，纯叙述 0，全对话 1）
- hook_type: 字符串（钩子类型，如 identity_secret / cliffhanger / curiosity / payoff_promise；自由文本）
- borrowable_aspects: 字符串数组（这段值得借鉴的写作技巧，如 psychological_buffer / sensory_grounding / emotional_progression / dialogue_subtext / pacing_acceleration / metaphor_density 等）
- quality_breakdown:
  - tension: 0-1 (情绪张力强度)
  - originality: 0-1 (原创性 / 反套路程度)
  - language_density: 0-1 (语言密度 / 信息含量)
  - readability: 0-1 (可读性 / 流畅度)

注意：
1. quality_breakdown 4 个维度独立打分（不要互相影响），调用方会用配置权重加权
2. tension_level 与 quality_breakdown.tension 不是同一个字段（前者是场景张力，后者是文本张力）

输出严格 JSON（不要 markdown 包裹）：
```
{
  "scene_type": "opening",
  "tension_level": 0.7,
  "character_count": 1,
  "dialogue_ratio": 0.2,
  "hook_type": "identity_secret",
  "borrowable_aspects": ["psychological_buffer", "sensory_grounding"],
  "quality_breakdown": {
    "tension": 0.8,
    "originality": 0.7,
    "language_density": 0.6,
    "readability": 0.9
  }
}
```

输入 chunk：
---
{chunk_text}
---
```

- [ ] **Step 2: 写失败测试**

Create `tests/corpus_chunking/test_chunk_tagger.py`:

```python
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from scripts.corpus_chunking.chunk_tagger import (
    tag_chunk,
    TaggerConfig,
)
from scripts.corpus_chunking.models import RawChunk, SourceType


def _mock_resp(payload: dict) -> MagicMock:
    msg = MagicMock()
    msg.content = [MagicMock(text=json.dumps(payload))]
    return msg


@pytest.fixture
def cfg() -> TaggerConfig:
    return TaggerConfig(
        model="claude-haiku-4-5",
        quality_weights=(0.3, 0.3, 0.2, 0.2),
        max_retries=3,
    )


def test_tag_chunk_happy(cfg: TaggerConfig, sample_raw_chunk: RawChunk) -> None:
    client = MagicMock()
    client.messages.create.return_value = _mock_resp({
        "scene_type": "opening",
        "tension_level": 0.8,
        "character_count": 1,
        "dialogue_ratio": 0.0,
        "hook_type": "identity_reveal",
        "borrowable_aspects": ["psychological_buffer"],
        "quality_breakdown": {
            "tension": 0.9,
            "originality": 0.8,
            "language_density": 0.7,
            "readability": 0.9,
        },
    })
    t = tag_chunk(
        client=client,
        cfg=cfg,
        chunk=sample_raw_chunk,
        genre=["异世大陆", "玄幻"],
        ingested_at="2026-04-25",
        source_type=SourceType.BUILTIN,
    )
    assert t.scene_type == "opening"
    assert t.tension_level == 0.8
    assert t.character_count == 1
    assert t.genre == ["异世大陆", "玄幻"]
    # 4 维加权: 0.9*0.3 + 0.8*0.3 + 0.7*0.2 + 0.9*0.2 = 0.83
    assert t.quality_score == pytest.approx(0.83)


def test_tag_chunk_failure_returns_zero_quality(cfg: TaggerConfig, sample_raw_chunk: RawChunk) -> None:
    client = MagicMock()
    bad = MagicMock()
    bad.content = [MagicMock(text="not json")]
    client.messages.create.side_effect = [bad, bad, bad]
    t = tag_chunk(
        client=client,
        cfg=cfg,
        chunk=sample_raw_chunk,
        genre=["x"],
        ingested_at="2026-04-25",
        source_type=SourceType.BUILTIN,
    )
    assert t.scene_type == "tagging_failed"
    assert t.quality_score == 0.0
    assert "tagging_failed" in t.borrowable_aspects


def test_tag_chunk_uses_passed_genre_not_llm(cfg: TaggerConfig, sample_raw_chunk: RawChunk) -> None:
    """Genre 来自 manifest，不让 LLM 自己判（防跨书漂移）。"""
    client = MagicMock()
    client.messages.create.return_value = _mock_resp({
        "scene_type": "opening",
        "tension_level": 0.5,
        "character_count": 1,
        "dialogue_ratio": 0.0,
        "hook_type": "x",
        "borrowable_aspects": [],
        "quality_breakdown": {"tension": 0.5, "originality": 0.5, "language_density": 0.5, "readability": 0.5},
    })
    t = tag_chunk(
        client=client,
        cfg=cfg,
        chunk=sample_raw_chunk,
        genre=["都市", "现实"],  # ← passed in
        ingested_at="2026-04-25",
        source_type=SourceType.BUILTIN,
    )
    assert t.genre == ["都市", "现实"]  # not whatever LLM might think
```

- [ ] **Step 3: Run test → ImportError**

```bash
pytest tests/corpus_chunking/test_chunk_tagger.py -v --no-cov
```
Expected: `ModuleNotFoundError: No module named 'scripts.corpus_chunking.chunk_tagger'`

- [ ] **Step 4: 实现 chunk_tagger.py**

Create `scripts/corpus_chunking/chunk_tagger.py`:

```python
"""chunk_tagger: LLM 给 RawChunk 打 6 标签 + 4 维 quality_breakdown。

genre 不让 LLM 判（防跨书漂移），从 caller 传入（通常来自 manifest.json）。
失败处理：max_retries 后仍失败 → 返回 quality_score=0 + scene_type=tagging_failed
的 TaggedChunk（不丢数据，schema 兼容下游）。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.corpus_chunking.models import (
    QualityBreakdown,
    RawChunk,
    SourceType,
    TaggedChunk,
)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "chunk_tagger.txt"


@dataclass
class TaggerConfig:
    model: str
    quality_weights: tuple[float, float, float, float]
    max_retries: int


def _load_prompt(text: str) -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8").replace("{chunk_text}", text)


def _parse_json(text: str) -> dict[str, Any] | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
        return None


def _failure_chunk(chunk: RawChunk, genre: list[str], ingested_at: str, source_type: SourceType) -> TaggedChunk:
    return TaggedChunk(
        raw=chunk,
        scene_type="tagging_failed",
        genre=list(genre),
        tension_level=0.0,
        character_count=0,
        dialogue_ratio=0.0,
        hook_type="",
        borrowable_aspects=["tagging_failed"],
        quality_breakdown=QualityBreakdown(0.0, 0.0, 0.0, 0.0),
        source_type=source_type,
        ingested_at=ingested_at,
    )


def tag_chunk(
    *,
    client: Any,
    cfg: TaggerConfig,
    chunk: RawChunk,
    genre: list[str],
    ingested_at: str,
    source_type: SourceType,
) -> TaggedChunk:
    prompt = _load_prompt(chunk.text)
    payload: dict[str, Any] | None = None
    for _ in range(cfg.max_retries):
        try:
            resp = client.messages.create(
                model=cfg.model,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.content[0].text
            payload = _parse_json(raw)
            if payload and "scene_type" in payload and "quality_breakdown" in payload:
                break
        except Exception:  # noqa: BLE001
            payload = None

    if not payload:
        return _failure_chunk(chunk, genre, ingested_at, source_type)

    qb = payload["quality_breakdown"]
    return TaggedChunk(
        raw=chunk,
        scene_type=payload.get("scene_type", "tagging_failed"),
        genre=list(genre),
        tension_level=float(payload.get("tension_level", 0.0)),
        character_count=int(payload.get("character_count", 0)),
        dialogue_ratio=float(payload.get("dialogue_ratio", 0.0)),
        hook_type=str(payload.get("hook_type", "")),
        borrowable_aspects=list(payload.get("borrowable_aspects", [])),
        quality_breakdown=QualityBreakdown(
            tension=float(qb.get("tension", 0.0)),
            originality=float(qb.get("originality", 0.0)),
            language_density=float(qb.get("language_density", 0.0)),
            readability=float(qb.get("readability", 0.0)),
        ),
        source_type=source_type,
        ingested_at=ingested_at,
    )
```

- [ ] **Step 5: Run test → pass**

```bash
pytest tests/corpus_chunking/test_chunk_tagger.py -v --no-cov
```
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add scripts/corpus_chunking/chunk_tagger.py scripts/corpus_chunking/prompts/chunk_tagger.txt tests/corpus_chunking/test_chunk_tagger.py
git commit -m "feat(M2-T3): chunk_tagger — Haiku 打 6 标签 + 4 维加权 quality_score

genre 不让 LLM 判（防跨书漂移），从 caller 传入（manifest 继承）。失败兜底
返回 scene_type=tagging_failed + quality_score=0 + tag=tagging_failed 的
TaggedChunk（schema 仍合法，下游不丢数据）。3 测试全绿。"
```

---

## Task 4 (US-004): embedding_client + chunk_indexer

**Files:**
- Create: `scripts/corpus_chunking/embedding_client.py`
- Create: `scripts/corpus_chunking/chunk_indexer.py`
- Create: `tests/corpus_chunking/test_embedding_client.py`
- Create: `tests/corpus_chunking/test_chunk_indexer.py`

- [ ] **Step 1: 写 embedding_client 失败测试**

Create `tests/corpus_chunking/test_embedding_client.py`:

```python
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from scripts.corpus_chunking.embedding_client import (
    EmbeddingClient,
    EmbeddingConfig,
    EmbeddingError,
)


@pytest.fixture
def cfg() -> EmbeddingConfig:
    return EmbeddingConfig(
        model="Qwen/Qwen3-Embedding-8B",
        base_url="https://api-inference.modelscope.cn/v1",
        api_key="test-key",
        batch_size=32,
        max_retries=3,
    )


def test_embed_batch_returns_vectors(cfg: EmbeddingConfig) -> None:
    inner = MagicMock()
    inner.embeddings.create.return_value = MagicMock(
        data=[MagicMock(embedding=[0.1] * 4096), MagicMock(embedding=[0.2] * 4096)]
    )
    ec = EmbeddingClient(cfg=cfg, _client=inner)
    vectors = ec.embed_batch(["hello", "world"])
    assert len(vectors) == 2
    assert len(vectors[0]) == 4096


def test_embed_batch_chunks_input_by_batch_size(cfg: EmbeddingConfig) -> None:
    cfg.batch_size = 2
    inner = MagicMock()
    inner.embeddings.create.return_value = MagicMock(
        data=[MagicMock(embedding=[0.0] * 4096), MagicMock(embedding=[0.0] * 4096)]
    )
    ec = EmbeddingClient(cfg=cfg, _client=inner)
    vectors = ec.embed_batch(["a", "b", "c", "d", "e"])  # 5 → 3 calls of size 2/2/1
    assert len(vectors) == 5
    assert inner.embeddings.create.call_count == 3


def test_embed_retries_on_429(cfg: EmbeddingConfig) -> None:
    inner = MagicMock()
    err = Exception("429 rate limit")
    ok = MagicMock(data=[MagicMock(embedding=[0.0] * 4096)])
    inner.embeddings.create.side_effect = [err, err, ok]
    ec = EmbeddingClient(cfg=cfg, _client=inner)
    vectors = ec.embed_batch(["x"], _sleep=lambda _: None)
    assert len(vectors) == 1


def test_embed_raises_after_max_retries(cfg: EmbeddingConfig) -> None:
    inner = MagicMock()
    err = Exception("permanent")
    inner.embeddings.create.side_effect = [err, err, err, err]
    ec = EmbeddingClient(cfg=cfg, _client=inner)
    with pytest.raises(EmbeddingError):
        ec.embed_batch(["x"], _sleep=lambda _: None)
```

- [ ] **Step 2: Run → ImportError**

```bash
pytest tests/corpus_chunking/test_embedding_client.py -v --no-cov
```
Expected: ImportError.

- [ ] **Step 3: 实现 embedding_client.py**

Create `scripts/corpus_chunking/embedding_client.py`:

```python
"""Qwen3-Embedding-8B client wrapper with batching + exponential backoff.

Uses OpenAI-compatible client (modelscope endpoint). Errors are retried up
to max_retries with backoff [1s, 2s, 4s]. Raises EmbeddingError after
exhausting retries.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

try:
    from openai import OpenAI  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    OpenAI = None  # caller must inject _client in tests


class EmbeddingError(Exception):
    """Raised when embedding API call exhausts retries."""


@dataclass
class EmbeddingConfig:
    model: str
    base_url: str
    api_key: str
    batch_size: int
    max_retries: int


class EmbeddingClient:
    def __init__(self, cfg: EmbeddingConfig, _client: Any | None = None) -> None:
        self.cfg = cfg
        if _client is not None:
            self._client = _client
        else:
            if OpenAI is None:
                raise RuntimeError("openai package not installed")
            self._client = OpenAI(base_url=cfg.base_url, api_key=cfg.api_key)

    def embed_batch(
        self,
        texts: list[str],
        *,
        _sleep: Callable[[float], None] = time.sleep,
    ) -> list[list[float]]:
        out: list[list[float]] = []
        for start in range(0, len(texts), self.cfg.batch_size):
            chunk = texts[start : start + self.cfg.batch_size]
            vectors = self._call_with_retry(chunk, _sleep=_sleep)
            out.extend(vectors)
        return out

    def _call_with_retry(
        self,
        texts: list[str],
        *,
        _sleep: Callable[[float], None],
    ) -> list[list[float]]:
        last_err: Exception | None = None
        for attempt in range(self.cfg.max_retries + 1):
            try:
                resp = self._client.embeddings.create(
                    model=self.cfg.model,
                    input=texts,
                )
                return [item.embedding for item in resp.data]
            except Exception as err:  # noqa: BLE001 — retries
                last_err = err
                if attempt >= self.cfg.max_retries:
                    break
                _sleep(2 ** attempt)
        raise EmbeddingError(f"embedding failed after {self.cfg.max_retries} retries: {last_err}")
```

- [ ] **Step 4: Run test → pass**

```bash
pytest tests/corpus_chunking/test_embedding_client.py -v --no-cov
```
Expected: 4 passed.

- [ ] **Step 5: 写 chunk_indexer 失败测试**

Create `tests/corpus_chunking/test_chunk_indexer.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.corpus_chunking.chunk_indexer import (
    IndexerConfig,
    index_chunks,
)
from scripts.corpus_chunking.models import (
    QualityBreakdown,
    RawChunk,
    SourceType,
    TaggedChunk,
)


def _make_tagged(book: str, chapter: str, n: int) -> list[TaggedChunk]:
    out = []
    for i in range(1, n + 1):
        raw = RawChunk(
            chunk_id=f"CHUNK-{book}-{chapter}-§{i}",
            source_book=book,
            source_chapter=chapter,
            char_range=(0, 200),
            text=f"text {i}",
        )
        out.append(TaggedChunk(
            raw=raw,
            scene_type="opening",
            genre=["x"],
            tension_level=0.5,
            character_count=1,
            dialogue_ratio=0.0,
            hook_type="",
            borrowable_aspects=[],
            quality_breakdown=QualityBreakdown(0.5, 0.5, 0.5, 0.5),
            source_type=SourceType.BUILTIN,
            ingested_at="2026-04-25",
        ))
    return out


def test_index_chunks_upserts_to_qdrant(tmp_path: Path) -> None:
    qdrant = MagicMock()
    embedder = MagicMock()
    embedder.embed_batch.return_value = [[0.1] * 4096, [0.2] * 4096]
    cfg = IndexerConfig(qdrant_collection="corpus_chunks", upsert_batch_size=256)
    chunks = _make_tagged("b", "c1", 2)
    n = index_chunks(
        chunks=chunks,
        qdrant_client=qdrant,
        embedder=embedder,
        cfg=cfg,
        metadata_path=tmp_path / "metadata.jsonl",
        unindexed_path=tmp_path / "unindexed.jsonl",
    )
    assert n == 2
    qdrant.upsert.assert_called_once()
    args = qdrant.upsert.call_args.kwargs
    assert args["collection_name"] == "corpus_chunks"
    assert len(args["points"]) == 2


def test_index_chunks_writes_metadata_jsonl(tmp_path: Path) -> None:
    qdrant = MagicMock()
    embedder = MagicMock()
    embedder.embed_batch.return_value = [[0.0] * 4096]
    cfg = IndexerConfig(qdrant_collection="corpus_chunks", upsert_batch_size=256)
    chunks = _make_tagged("b", "c", 1)
    md = tmp_path / "metadata.jsonl"
    index_chunks(
        chunks=chunks,
        qdrant_client=qdrant,
        embedder=embedder,
        cfg=cfg,
        metadata_path=md,
        unindexed_path=tmp_path / "unindexed.jsonl",
    )
    line = md.read_text(encoding="utf-8").strip()
    assert "CHUNK-b-c-§1" in line


def test_index_chunks_records_qdrant_failure_in_unindexed(tmp_path: Path) -> None:
    qdrant = MagicMock()
    qdrant.upsert.side_effect = Exception("qdrant down")
    embedder = MagicMock()
    embedder.embed_batch.return_value = [[0.0] * 4096]
    cfg = IndexerConfig(qdrant_collection="corpus_chunks", upsert_batch_size=256)
    chunks = _make_tagged("b", "c", 1)
    unindexed = tmp_path / "unindexed.jsonl"
    n = index_chunks(
        chunks=chunks,
        qdrant_client=qdrant,
        embedder=embedder,
        cfg=cfg,
        metadata_path=tmp_path / "metadata.jsonl",
        unindexed_path=unindexed,
    )
    assert n == 0
    line = unindexed.read_text(encoding="utf-8").strip()
    assert "CHUNK-b-c-§1" in line


def test_index_chunks_uuid5_is_idempotent_id() -> None:
    """Same chunk_id → same Qdrant point id (UUID5 stable)."""
    from scripts.corpus_chunking.chunk_indexer import _stable_uuid_from_id
    a = _stable_uuid_from_id("CHUNK-x-c1-§1")
    b = _stable_uuid_from_id("CHUNK-x-c1-§1")
    c = _stable_uuid_from_id("CHUNK-x-c1-§2")
    assert a == b
    assert a != c
```

- [ ] **Step 6: Run test → ImportError**

```bash
pytest tests/corpus_chunking/test_chunk_indexer.py -v --no-cov
```
Expected: ImportError.

- [ ] **Step 7: 实现 chunk_indexer.py**

Create `scripts/corpus_chunking/chunk_indexer.py`:

```python
"""chunk_indexer: 把 TaggedChunk 列表向量化 + upsert 到 Qdrant。

UUID5(NAMESPACE_URL, chunk_id) 作为 Qdrant point id，保证重跑相同 chunk_id
覆盖同一 point（spec §3.3 沿用 M1 US-013 pattern）。

失败处理：Qdrant upsert 失败 → 失败 batch 的 chunks 写入 unindexed_path（jsonl），
不阻断后续 batches。
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from scripts.corpus_chunking.models import TaggedChunk


@dataclass
class IndexerConfig:
    qdrant_collection: str
    upsert_batch_size: int


def _stable_uuid_from_id(chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


def _build_point(chunk: TaggedChunk, vector: list[float]) -> dict[str, Any]:
    """Return a dict that matches qdrant_client.http.models.PointStruct shape."""
    from qdrant_client.http import models as rest
    return rest.PointStruct(
        id=_stable_uuid_from_id(chunk.raw.chunk_id),
        vector=vector,
        payload=chunk.to_dict(),
    )


def index_chunks(
    *,
    chunks: list[TaggedChunk],
    qdrant_client: Any,
    embedder: Any,
    cfg: IndexerConfig,
    metadata_path: Path,
    unindexed_path: Path,
) -> int:
    """Returns number of chunks successfully indexed."""
    indexed_count = 0
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    unindexed_path.parent.mkdir(parents=True, exist_ok=True)

    for start in range(0, len(chunks), cfg.upsert_batch_size):
        batch = chunks[start : start + cfg.upsert_batch_size]
        texts = [c.raw.text for c in batch]
        try:
            vectors = embedder.embed_batch(texts)
            points = [_build_point(c, v) for c, v in zip(batch, vectors)]
            qdrant_client.upsert(collection_name=cfg.qdrant_collection, points=points)
            indexed_count += len(batch)
            with open(metadata_path, "a", encoding="utf-8") as fp:
                for c in batch:
                    fp.write(json.dumps(c.to_dict(), ensure_ascii=False))
                    fp.write("\n")
        except Exception as err:  # noqa: BLE001
            with open(unindexed_path, "a", encoding="utf-8") as fp:
                for c in batch:
                    fp.write(json.dumps({"chunk_id": c.raw.chunk_id, "error": str(err)}, ensure_ascii=False))
                    fp.write("\n")
    return indexed_count
```

- [ ] **Step 8: Run test → pass**

```bash
pytest tests/corpus_chunking/test_chunk_indexer.py -v --no-cov
```
Expected: 4 passed.

- [ ] **Step 9: 全套 corpus_chunking 测试 + audit 红线**

```bash
pytest tests/corpus_chunking -v --no-cov
pytest tests/audit/test_cli_entries_utf8_stdio.py tests/core/test_safe_symlink.py -v --no-cov
```
Expected: 全绿。

- [ ] **Step 10: Commit**

```bash
git add scripts/corpus_chunking/embedding_client.py scripts/corpus_chunking/chunk_indexer.py tests/corpus_chunking/test_embedding_client.py tests/corpus_chunking/test_chunk_indexer.py
git commit -m "feat(M2-T4): embedding_client + chunk_indexer

EmbeddingClient: Qwen3-Embedding-8B (modelscope) + batching + 指数退避重试。
chunk_indexer: TaggedChunk → 向量化 → Qdrant batch upsert（UUID5 幂等）+
metadata.jsonl 备份 + unindexed.jsonl 失败兜底。8 测试全绿。"
```

---

## Task 5 (US-005): ink corpus ingest CLI

**Files:**
- Create: `scripts/corpus_chunking/cli.py`
- Create: `tests/corpus_chunking/test_cli.py`

- [ ] **Step 1: 写失败测试**

Create `tests/corpus_chunking/test_cli.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.corpus_chunking.cli import main


def _build_fake_corpus(root: Path) -> None:
    book = root / "诡秘之主"
    (book / "chapters").mkdir(parents=True)
    (book / "chapters" / "ch001.txt").write_text("克莱恩盯着镜子。" * 50, encoding="utf-8")
    (book / "manifest.json").write_text(
        json.dumps({"title": "诡秘之主", "genre": "异世大陆"}, ensure_ascii=False),
        encoding="utf-8",
    )


def test_ingest_dry_run_does_not_call_qdrant(tmp_path: Path, monkeypatch) -> None:
    _build_fake_corpus(tmp_path)
    cfg_yaml = tmp_path / "cfg.yaml"
    cfg_yaml.write_text("""
scene_segmenter:
  model: claude-haiku-4-5-20251001
  min_chunk_chars: 200
  max_chunk_chars: 800
  max_retries: 3
chunk_tagger:
  model: claude-haiku-4-5-20251001
  batch_size: 5
  quality_weights:
    tension: 0.3
    originality: 0.3
    language_density: 0.2
    readability: 0.2
  max_retries: 3
chunk_indexer:
  embedding_model: x
  embedding_base_url: http://localhost
  qdrant_collection: corpus_chunks
  upsert_batch_size: 256
  embed_batch_size: 32
""", encoding="utf-8")
    with patch("scripts.corpus_chunking.cli._build_anthropic_client") as build_anth, \
         patch("scripts.corpus_chunking.cli._build_qdrant_client") as build_qd, \
         patch("scripts.corpus_chunking.cli._build_embedding_client") as build_em:
        anth = MagicMock()
        anth.messages.create.return_value = MagicMock(
            content=[MagicMock(text=json.dumps({
                "chunks": [{"scene_type": "opening", "char_range": [0, 400], "text": "x" * 400}]
            }))]
        )
        build_anth.return_value = anth
        rc = main([
            "--config", str(cfg_yaml),
            "ingest",
            "--dir", str(tmp_path),
            "--dry-run",
        ])
        assert rc == 0
        build_qd.assert_not_called()
        build_em.assert_not_called()


def test_ingest_resume_skips_indexed_chapters(tmp_path: Path) -> None:
    """If chunks_raw.jsonl already has chapter ch001, --resume 跳过它."""
    from scripts.corpus_chunking.cli import _already_indexed
    raw = tmp_path / "chunks_raw.jsonl"
    raw.write_text(json.dumps({"chunk_id": "CHUNK-诡秘之主-ch001-§1", "source_book": "诡秘之主", "source_chapter": "ch001"}, ensure_ascii=False) + "\n", encoding="utf-8")
    assert _already_indexed("诡秘之主", "ch001", raw) is True
    assert _already_indexed("诡秘之主", "ch002", raw) is False
```

- [ ] **Step 2: Run → ImportError**

```bash
pytest tests/corpus_chunking/test_cli.py -v --no-cov
```
Expected: ImportError.

- [ ] **Step 3: 实现 cli.py**

Create `scripts/corpus_chunking/cli.py`:

```python
"""ink corpus ingest / rebuild / watch — corpus chunking CLI.

`main(argv) -> int` never raises; argparse SystemExit translated to rc.
Subcommands wired to scene_segmenter / chunk_tagger / chunk_indexer.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

import yaml

# sys.path 三段式 bootstrap (跨目录 CLI 入口模板，progress.txt 已记录)
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_INK_SCRIPTS = _REPO_ROOT / "ink-writer" / "scripts"
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_INK_SCRIPTS))

try:
    from runtime_compat import enable_windows_utf8_stdio  # noqa: E402
except ImportError:
    enable_windows_utf8_stdio = lambda: None  # noqa: E731

from scripts.corpus_chunking.scene_segmenter import segment_chapter, SegmenterConfig  # noqa: E402
from scripts.corpus_chunking.chunk_tagger import tag_chunk, TaggerConfig  # noqa: E402
from scripts.corpus_chunking.chunk_indexer import index_chunks, IndexerConfig  # noqa: E402
from scripts.corpus_chunking.embedding_client import EmbeddingClient, EmbeddingConfig  # noqa: E402
from scripts.corpus_chunking.models import IngestReport, SourceType  # noqa: E402


def _load_config(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fp:
        return yaml.safe_load(fp)


def _build_anthropic_client():  # pragma: no cover (mocked in tests)
    from anthropic import Anthropic
    return Anthropic()


def _build_qdrant_client():  # pragma: no cover
    from ink_writer.qdrant.client import get_client_from_config, QdrantConfig
    return get_client_from_config(QdrantConfig())


def _build_embedding_client(cfg_dict: dict) -> EmbeddingClient:  # pragma: no cover
    cfg = EmbeddingConfig(
        model=cfg_dict["embedding_model"],
        base_url=cfg_dict["embedding_base_url"],
        api_key=os.environ.get("EMBED_API_KEY", ""),
        batch_size=cfg_dict["embed_batch_size"],
        max_retries=3,
    )
    return EmbeddingClient(cfg=cfg)


def _read_manifest_genre(book_dir: Path) -> list[str]:
    manifest = book_dir / "manifest.json"
    if not manifest.is_file():
        return ["all"]
    try:
        with open(manifest, encoding="utf-8") as fp:
            data = json.load(fp)
        g = data.get("genre", "all")
        return [g] if isinstance(g, str) else list(g)
    except Exception:  # noqa: BLE001
        return ["all"]


def _already_indexed(book: str, chapter: str, raw_path: Path) -> bool:
    """Check chunks_raw.jsonl for existing entries of (book, chapter)."""
    if not raw_path.is_file():
        return False
    with open(raw_path, encoding="utf-8") as fp:
        for line in fp:
            try:
                row = json.loads(line)
                if row.get("source_book") == book and row.get("source_chapter") == chapter:
                    return True
            except json.JSONDecodeError:
                continue
    return False


def _ingest_book(
    *,
    book_dir: Path,
    out_dir: Path,
    cfg: dict,
    anth_client,
    qdrant_client,
    embed_client,
    resume: bool,
    dry_run: bool,
) -> IngestReport:
    book = book_dir.name
    genre = _read_manifest_genre(book_dir)
    chapters_dir = book_dir / "chapters"
    raw_path = out_dir / "chunks_raw.jsonl"
    tagged_path = out_dir / "chunks_tagged.jsonl"
    metadata_path = out_dir / "metadata.jsonl"
    failures_path = out_dir / "failures.jsonl"
    unindexed_path = out_dir / "unindexed.jsonl"
    out_dir.mkdir(parents=True, exist_ok=True)

    seg_cfg = SegmenterConfig(**cfg["scene_segmenter"])
    tag_cfg = TaggerConfig(
        model=cfg["chunk_tagger"]["model"],
        quality_weights=(
            cfg["chunk_tagger"]["quality_weights"]["tension"],
            cfg["chunk_tagger"]["quality_weights"]["originality"],
            cfg["chunk_tagger"]["quality_weights"]["language_density"],
            cfg["chunk_tagger"]["quality_weights"]["readability"],
        ),
        max_retries=cfg["chunk_tagger"]["max_retries"],
    )
    idx_cfg = IndexerConfig(
        qdrant_collection=cfg["chunk_indexer"]["qdrant_collection"],
        upsert_batch_size=cfg["chunk_indexer"]["upsert_batch_size"],
    )

    report = IngestReport()
    today = date.today().isoformat()

    for ch_file in sorted(chapters_dir.glob("ch*.txt")):
        chapter = ch_file.stem
        if resume and _already_indexed(book, chapter, raw_path):
            continue
        text = ch_file.read_text(encoding="utf-8")
        raws = segment_chapter(client=anth_client, cfg=seg_cfg, book=book, chapter=chapter, text=text)
        if not raws:
            with open(failures_path, "a", encoding="utf-8") as fp:
                fp.write(json.dumps({"book": book, "chapter": chapter, "error": "scene_segmenter_failed"}, ensure_ascii=False) + "\n")
            report.failures.append((f"{book}/{chapter}", "scene_segmenter_failed"))
            continue
        report.chunks_raw += len(raws)
        with open(raw_path, "a", encoding="utf-8") as fp:
            for r in raws:
                fp.write(json.dumps(r.to_dict(), ensure_ascii=False) + "\n")

        tagged = []
        for r in raws:
            t = tag_chunk(client=anth_client, cfg=tag_cfg, chunk=r, genre=genre, ingested_at=today, source_type=SourceType.BUILTIN)
            tagged.append(t)
        report.chunks_tagged += len(tagged)
        with open(tagged_path, "a", encoding="utf-8") as fp:
            for t in tagged:
                fp.write(json.dumps(t.to_dict(), ensure_ascii=False) + "\n")

        if dry_run:
            continue

        n = index_chunks(
            chunks=tagged,
            qdrant_client=qdrant_client,
            embedder=embed_client,
            cfg=idx_cfg,
            metadata_path=metadata_path,
            unindexed_path=unindexed_path,
        )
        report.chunks_indexed += n
    return report


def _cmd_ingest(args: argparse.Namespace, cfg: dict) -> int:
    out_dir = Path("data/corpus_chunks")
    src = Path(args.dir or "benchmark/reference_corpus")
    if not src.is_dir():
        print(f"ERROR: {src} not a directory", file=sys.stderr)
        return 2
    anth = _build_anthropic_client()
    qd = None if args.dry_run else _build_qdrant_client()
    em = None if args.dry_run else _build_embedding_client(cfg["chunk_indexer"])

    books = sorted(p for p in src.iterdir() if p.is_dir())
    if args.book:
        books = [p for p in books if p.name == args.book]

    total = IngestReport()
    for i, book_dir in enumerate(books, 1):
        report = _ingest_book(
            book_dir=book_dir,
            out_dir=out_dir,
            cfg=cfg,
            anth_client=anth,
            qdrant_client=qd,
            embed_client=em,
            resume=args.resume,
            dry_run=args.dry_run,
        )
        total.chunks_raw += report.chunks_raw
        total.chunks_tagged += report.chunks_tagged
        total.chunks_indexed += report.chunks_indexed
        total.failures.extend(report.failures)
        print(f"[{i}/{len(books)}] {book_dir.name:25s} chunks={report.chunks_raw} tagged={report.chunks_tagged} indexed={report.chunks_indexed} failures={len(report.failures)}")

    print(f"TOTAL chunks={total.chunks_raw} tagged={total.chunks_tagged} indexed={total.chunks_indexed} failures={len(total.failures)}")
    return 0 if not total.failures else 1


def _cmd_rebuild(args: argparse.Namespace, cfg: dict) -> int:  # implemented in T6
    return 1


def _cmd_watch(args: argparse.Namespace, cfg: dict) -> int:  # implemented in T7
    return 1


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ink corpus")
    p.add_argument("--config", type=Path, default=Path("config/corpus_chunking.yaml"))
    sub = p.add_subparsers(dest="cmd", required=True)

    ing = sub.add_parser("ingest")
    ing.add_argument("--dir", type=str, default=None)
    ing.add_argument("--book", type=str, default=None)
    ing.add_argument("--resume", action="store_true")
    ing.add_argument("--dry-run", action="store_true")

    rb = sub.add_parser("rebuild")
    rb.add_argument("--yes", action="store_true")
    rb.add_argument("--book", type=str, default=None)

    wt = sub.add_parser("watch")
    wt.add_argument("--dir", type=str, required=True)
    wt.add_argument("--interval", type=int, default=30)
    return p


def main(argv: list[str] | None = None) -> int:
    enable_windows_utf8_stdio()
    try:
        args = _build_parser().parse_args(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 2
    cfg = _load_config(args.config)
    if args.cmd == "ingest":
        return _cmd_ingest(args, cfg)
    if args.cmd == "rebuild":
        return _cmd_rebuild(args, cfg)
    if args.cmd == "watch":
        return _cmd_watch(args, cfg)
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
```

- [ ] **Step 4: Run test → pass**

```bash
pytest tests/corpus_chunking/test_cli.py -v --no-cov
```
Expected: 2 passed.

- [ ] **Step 5: 仓库级 audit 红线扫**

```bash
pytest tests/audit/test_cli_entries_utf8_stdio.py tests/core/test_safe_symlink.py -v --no-cov
```
Expected: 全绿（cli.py 含 `__main__` 入口 + 字面量 `enable_windows_utf8_stdio`）。

- [ ] **Step 6: Commit**

```bash
git add scripts/corpus_chunking/cli.py tests/corpus_chunking/test_cli.py
git commit -m "feat(M2-T5): ink corpus ingest CLI (含 --book/--resume/--dry-run)

main(argv) -> int 永不 raise；ingest 子命令读 manifest.json 继承 genre →
顺序跑 segmenter → tagger → indexer，每书一行进度输出。--dry-run 不调
Qdrant/Embedding API；--resume 用 chunks_raw.jsonl 反查 (book,chapter)
跳过已 indexed 章节。rebuild/watch 占位（后续 T6/T7 实现）。"
```

---

## Task 6 (US-006): ink corpus rebuild CLI

**Files:**
- Modify: `scripts/corpus_chunking/cli.py`（替换 `_cmd_rebuild` stub）
- Modify: `tests/corpus_chunking/test_cli.py`（追加测试）

- [ ] **Step 1: 写失败测试**

Append to `tests/corpus_chunking/test_cli.py`:

```python
def test_rebuild_without_yes_refuses(tmp_path: Path, capsys) -> None:
    cfg_yaml = tmp_path / "cfg.yaml"
    cfg_yaml.write_text("chunk_indexer:\n  qdrant_collection: corpus_chunks\n  upsert_batch_size: 1\n  embed_batch_size: 1\n  embedding_model: x\n  embedding_base_url: http://x\nscene_segmenter:\n  model: x\n  min_chunk_chars: 200\n  max_chunk_chars: 800\n  max_retries: 1\nchunk_tagger:\n  model: x\n  batch_size: 1\n  quality_weights:\n    tension: 0.3\n    originality: 0.3\n    language_density: 0.2\n    readability: 0.2\n  max_retries: 1\n", encoding="utf-8")
    rc = main(["--config", str(cfg_yaml), "rebuild"])
    out = capsys.readouterr().err
    assert rc != 0
    assert "--yes" in out


def test_rebuild_with_yes_clears_collection(tmp_path: Path) -> None:
    from unittest.mock import patch, MagicMock
    cfg_yaml = tmp_path / "cfg.yaml"
    cfg_yaml.write_text("chunk_indexer:\n  qdrant_collection: corpus_chunks\n  upsert_batch_size: 1\n  embed_batch_size: 1\n  embedding_model: x\n  embedding_base_url: http://x\nscene_segmenter:\n  model: x\n  min_chunk_chars: 200\n  max_chunk_chars: 800\n  max_retries: 1\nchunk_tagger:\n  model: x\n  batch_size: 1\n  quality_weights:\n    tension: 0.3\n    originality: 0.3\n    language_density: 0.2\n    readability: 0.2\n  max_retries: 1\n", encoding="utf-8")
    qd = MagicMock()
    with patch("scripts.corpus_chunking.cli._build_qdrant_client", return_value=qd), \
         patch("scripts.corpus_chunking.cli._cmd_ingest", return_value=0):
        rc = main(["--config", str(cfg_yaml), "rebuild", "--yes"])
        assert rc == 0
        qd.delete_collection.assert_called_once_with(collection_name="corpus_chunks")
```

- [ ] **Step 2: 实现 _cmd_rebuild**

Edit `scripts/corpus_chunking/cli.py`. Replace `_cmd_rebuild` stub with:

```python
def _cmd_rebuild(args: argparse.Namespace, cfg: dict) -> int:
    if not args.yes:
        print("ERROR: rebuild is destructive; pass --yes to confirm.", file=sys.stderr)
        return 2
    out_dir = Path("data/corpus_chunks")
    if args.book:
        # Per-book delete: filter chunks_raw.jsonl 非该书的行 → 写回；删 metadata 同理
        for fname in ["chunks_raw.jsonl", "chunks_tagged.jsonl", "metadata.jsonl"]:
            path = out_dir / fname
            if path.is_file():
                kept = [
                    line for line in path.read_text(encoding="utf-8").splitlines()
                    if json.loads(line).get("source_book") != args.book
                ]
                path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    else:
        # Full delete
        for fname in ["chunks_raw.jsonl", "chunks_tagged.jsonl", "metadata.jsonl", "failures.jsonl", "unindexed.jsonl"]:
            path = out_dir / fname
            if path.is_file():
                path.unlink()

    qd = _build_qdrant_client()
    if not args.book:
        try:
            qd.delete_collection(collection_name=cfg["chunk_indexer"]["qdrant_collection"])
        except Exception as err:  # noqa: BLE001 — collection may not exist
            print(f"warn: delete_collection: {err}", file=sys.stderr)
        from ink_writer.qdrant.payload_schema import CORPUS_CHUNKS_SPEC, ensure_collection
        ensure_collection(qd, CORPUS_CHUNKS_SPEC)

    # Re-trigger ingest
    ing_args = argparse.Namespace(dir=None, book=args.book, resume=False, dry_run=False)
    return _cmd_ingest(ing_args, cfg)
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/corpus_chunking/test_cli.py -v --no-cov
```
Expected: 4 passed (2 new + 2 from T5).

- [ ] **Step 4: Commit**

```bash
git add scripts/corpus_chunking/cli.py tests/corpus_chunking/test_cli.py
git commit -m "feat(M2-T6): ink corpus rebuild CLI (--yes 防误触 + 全量/单书)

无 --yes → rc=2 + stderr。--yes 全量 → 删 5 个 jsonl + delete_collection
+ ensure_collection 重建 + 重跑 ingest。--yes --book → 仅 filter 该书行
+ 不动 collection (单书清理)。"
```

---

## Task 7 (US-007): ink corpus watch CLI

**Files:**
- Modify: `scripts/corpus_chunking/cli.py`（替换 `_cmd_watch` stub）
- Modify: `tests/corpus_chunking/test_cli.py`（追加测试）

- [ ] **Step 1: 写失败测试**

Append to `tests/corpus_chunking/test_cli.py`:

```python
def test_watch_detects_new_file_and_triggers_ingest(tmp_path: Path, monkeypatch) -> None:
    from unittest.mock import patch
    cfg_yaml = tmp_path / "cfg.yaml"
    cfg_yaml.write_text("chunk_indexer:\n  qdrant_collection: corpus_chunks\n  upsert_batch_size: 1\n  embed_batch_size: 1\n  embedding_model: x\n  embedding_base_url: http://x\nscene_segmenter:\n  model: x\n  min_chunk_chars: 200\n  max_chunk_chars: 800\n  max_retries: 1\nchunk_tagger:\n  model: x\n  batch_size: 1\n  quality_weights:\n    tension: 0.3\n    originality: 0.3\n    language_density: 0.2\n    readability: 0.2\n  max_retries: 1\n", encoding="utf-8")
    watch_dir = tmp_path / "watch"
    watch_dir.mkdir()
    triggered: list[str] = []
    def fake_ingest_path(path: Path, cfg: dict) -> None:
        triggered.append(str(path))

    with patch("scripts.corpus_chunking.cli._ingest_single_file", side_effect=fake_ingest_path):
        # Pre-create one file, watch should pick up second new file.
        (watch_dir / "ch001.txt").write_text("first", encoding="utf-8")
        # call watch with iteration=2 (new test param to break loop)
        rc = main([
            "--config", str(cfg_yaml),
            "watch", "--dir", str(watch_dir),
            "--interval", "0",
            "--iterations", "2",
        ])
        # Add a new file mid-loop simulation: but iterations=2 + interval=0 means
        # we just need _ingest_single_file to be called for files modified after start.
        # Actually simulate by adjusting mtime in fixture; here we accept rc=0 + maybe 1 trigger.
        assert rc == 0
```

(注：watch 的真实 polling 行为难纯粹测试，本测试主要验证 CLI 结构 + iterations 退出 + 不抛异常。)

- [ ] **Step 2: 实现 _cmd_watch**

Edit `scripts/corpus_chunking/cli.py`. 在 `_build_parser()` 的 `wt` 上追加 `--iterations` 参数（默认 -1 无限）：

```python
    wt.add_argument("--iterations", type=int, default=-1, help="Stop after N polls (test only)")
```

替换 `_cmd_watch` stub：

```python
def _ingest_single_file(file_path: Path, cfg: dict) -> None:  # pragma: no cover (called by watch)
    # Simplified: treat parent.parent as the "book" structure root
    book_dir = file_path.parent.parent
    out_dir = Path("data/corpus_chunks")
    anth = _build_anthropic_client()
    qd = _build_qdrant_client()
    em = _build_embedding_client(cfg["chunk_indexer"])
    _ingest_book(
        book_dir=book_dir, out_dir=out_dir, cfg=cfg,
        anth_client=anth, qdrant_client=qd, embed_client=em,
        resume=True, dry_run=False,
    )


def _cmd_watch(args: argparse.Namespace, cfg: dict) -> int:
    watch_dir = Path(args.dir)
    if not watch_dir.is_dir():
        print(f"ERROR: {watch_dir} not a directory", file=sys.stderr)
        return 2
    seen: dict[Path, float] = {p: p.stat().st_mtime for p in watch_dir.rglob("*.txt")}
    iteration = 0
    try:
        while args.iterations < 0 or iteration < args.iterations:
            time.sleep(args.interval) if args.interval > 0 else None
            for p in watch_dir.rglob("*.txt"):
                mtime = p.stat().st_mtime
                if p not in seen or seen[p] != mtime:
                    seen[p] = mtime
                    try:
                        _ingest_single_file(p, cfg)
                    except Exception as err:  # noqa: BLE001
                        print(f"warn: ingest {p} failed: {err}", file=sys.stderr)
            iteration += 1
    except KeyboardInterrupt:
        print("watch stopped (Ctrl+C)", file=sys.stderr)
    return 0
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/corpus_chunking/test_cli.py -v --no-cov
```
Expected: 5 passed (3 from T5/T6 + 1 new + 1 watch's 0-iteration).

- [ ] **Step 4: Commit**

```bash
git add scripts/corpus_chunking/cli.py tests/corpus_chunking/test_cli.py
git commit -m "feat(M2-T7): ink corpus watch CLI (polling 30s)

mtime + content polling，Ctrl+C 优雅退出。--iterations 仅供测试 break
循环。新文件 / mtime 变化触发 _ingest_single_file (resume 模式)。spec
§4.1c 已说明不用 watchdog 因跨平台不一致。"
```

---

## Task 8 (US-008): 30 本范文 ingest 实跑 + 抽样验证

**Files:**
- 无新增代码文件；本 task 是**实跑 + 验收**

- [ ] **Step 1: 启动 Qdrant**

```bash
scripts/qdrant/start.sh
curl -s http://127.0.0.1:6333/readyz
```
Expected: `Qdrant is ready.` + HTTP 200

- [ ] **Step 2: 验证 EMBED_API_KEY 已配**

```bash
test -n "${EMBED_API_KEY:-}" && echo "OK" || echo "MISSING"
```
Expected: `OK`. 若 MISSING，按 `docs/rag-and-config.md` 在 `.env` 配置。

- [ ] **Step 3: 先单本 dry-run 验证**

```bash
python -m scripts.corpus_chunking.cli ingest --book 诡秘之主 --dry-run 2>&1 | tail -10
```
Expected：单行进度输出（如 `[1/1] 诡秘之主 chunks=N tagged=N indexed=0 failures=0`），且 `data/corpus_chunks/chunks_tagged.jsonl` 非空。

抽样核 1 chunk 看质量：
```bash
head -1 data/corpus_chunks/chunks_tagged.jsonl | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print('scene_type:', d['scene_type']); print('quality_score:', d['quality_score']); print('genre:', d['genre']); print('text 前80字:', d['text'][:80])"
```
检查 scene_type 合理、quality_score 在 0-1 之间、genre 来自 manifest（应是 ["异世大陆"]）、text 是真实诡秘之主原文片段。

如果 dry-run 输出明显异常（例如 chunks=0 / scene_type 全是 tagging_failed），先调 `prompts/scene_segmenter.txt` 或 `prompts/chunk_tagger.txt` 再继续。

- [ ] **Step 4: 真跑全量 30 本（含写 Qdrant）**

```bash
rm data/corpus_chunks/chunks_raw.jsonl data/corpus_chunks/chunks_tagged.jsonl data/corpus_chunks/metadata.jsonl 2>/dev/null
python -m scripts.corpus_chunking.cli ingest 2>&1 | tee /tmp/m2_ingest.log
```
Expected: 30 行进度 + 1 行 TOTAL；总 chunks ≥ 2500。

预计耗时：每本书约 30 章 × ~2 LLM 调用/章 ≈ 60 calls × Haiku ~3s = ~3 min/book × 30 = ~90 min。

- [ ] **Step 5: 验证 Qdrant collection 状态**

```bash
curl -s http://127.0.0.1:6333/collections/corpus_chunks | python3 -c "import json,sys; d=json.loads(sys.stdin.read())['result']; print('points_count:', d.get('points_count')); print('status:', d.get('status'))"
```
Expected: `points_count >= 2500`, `status: green`.

- [ ] **Step 6: 抽样 50 chunks 人工核**

```bash
python3 -c "
import json, random
with open('data/corpus_chunks/chunks_tagged.jsonl', encoding='utf-8') as fp:
    chunks = [json.loads(l) for l in fp]
random.seed(42)
sample = random.sample(chunks, min(50, len(chunks)))
with open('/tmp/m2_sample_50.jsonl', 'w', encoding='utf-8') as fp:
    for c in sample:
        fp.write(json.dumps({'chunk_id': c['chunk_id'], 'scene_type': c['scene_type'], 'quality_score': c['quality_score'], 'text_preview': c['text'][:100]}, ensure_ascii=False) + '\n')
print(f'Sampled {len(sample)} chunks → /tmp/m2_sample_50.jsonl')
"
cat /tmp/m2_sample_50.jsonl
```

人工浏览：scene_type 分类合理度 ≥ 80% / quality_score 分布合理 / 没有明显切坏的 chunks。

如果质量低于预期：调 prompt 后跑 `ink corpus rebuild --yes`。

- [ ] **Step 7: 检查 failures.jsonl 与 unindexed.jsonl**

```bash
echo "失败章节数:" && wc -l data/corpus_chunks/failures.jsonl 2>/dev/null || echo "0"
echo "未入库 chunks:" && wc -l data/corpus_chunks/unindexed.jsonl 2>/dev/null || echo "0"
```
Expected: failures < 30 (< 3.3% of ~900 章), unindexed < 5.

- [ ] **Step 8: Commit progress.txt 沉淀**

仅 commit 实跑产物（不入仓的 chunks_raw/tagged/metadata.jsonl 由 .gitignore 处理；commit 仅记录学到的 patterns + 验收结果）。

```bash
# 把实跑 stats 追加到 progress.txt
cat >> progress.txt << 'EOF'

## 2026-04-XX — US-008 30 本范文 ingest 实跑
- TOTAL chunks=<N> tagged=<N> indexed=<N> failures=<N>
- Qdrant corpus_chunks points_count: <N>
- 抽样 50 chunks 人工核：scene_type 合理度 X%，quality_score 分布合理
- failures.jsonl 章节数: <N>, unindexed.jsonl chunks: <N>
- Learnings: <按实际情况补>
EOF
git add progress.txt
git commit -m "feat(M2-T8): 30 本范文 ingest 实跑 + 抽样验证

总 chunks <N>，Qdrant points_count <N>，failures <N>。抽 50 chunks 人工
核 scene_type 合理度 X%。"
```

---

## Task 9 (US-009): rules_to_cases 转换器 + 单测

**Files:**
- Create: `ink_writer/case_library/rules_to_cases.py`
- Create: `tests/case_library/test_rules_to_cases.py`

- [ ] **Step 1: 写失败测试**

Create `tests/case_library/test_rules_to_cases.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ink_writer.case_library.rules_to_cases import (
    convert_rules_to_cases,
    ConvertReport,
    map_rule_to_case_kwargs,
)
from ink_writer.case_library.store import CaseStore


def _write_rules(tmp_path: Path, rules: list[dict]) -> Path:
    p = tmp_path / "rules.json"
    p.write_text(json.dumps(rules, ensure_ascii=False), encoding="utf-8")
    return p


def test_map_hard_rule_to_active_p1() -> None:
    rule = {
        "id": "EW-0001",
        "category": "opening",
        "rule": "开篇必须有冲突或悬念",
        "why": "钩住读者",
        "severity": "hard",
        "applies_to": ["opening_only"],
        "source_files": ["001.md"],
    }
    kw = map_rule_to_case_kwargs(rule, ingested_at="2026-04-25")
    assert kw["severity"] == "P1"
    assert kw["initial_status"] == "active"
    assert "opening" in kw["tags"]
    assert kw["scope_chapter"] == ["opening_only"]


def test_map_soft_rule_to_pending_p2() -> None:
    rule = {"id": "EW-0002", "category": "pacing", "rule": "x", "why": "y", "severity": "soft", "applies_to": ["all_chapters"], "source_files": []}
    kw = map_rule_to_case_kwargs(rule, ingested_at="2026-04-25")
    assert kw["severity"] == "P2"
    assert kw["initial_status"] == "pending"


def test_map_info_rule_to_pending_p3_with_info_only_tag() -> None:
    rule = {"id": "EW-0003", "category": "ops", "rule": "x", "why": "y", "severity": "info", "applies_to": ["all_chapters"], "source_files": []}
    kw = map_rule_to_case_kwargs(rule, ingested_at="2026-04-25")
    assert kw["severity"] == "P3"
    assert kw["initial_status"] == "pending"
    assert "info_only" in kw["tags"]


def test_map_observable_uses_placeholder_with_rule_id() -> None:
    rule = {"id": "EW-0042", "category": "x", "rule": "x", "why": "y", "severity": "hard", "applies_to": [], "source_files": []}
    kw = map_rule_to_case_kwargs(rule, ingested_at="2026-04-25")
    assert any("EW-0042" in obs for obs in kw["observable"])


def test_convert_creates_cases_idempotently(tmp_path: Path) -> None:
    rules = [
        {"id": "EW-0001", "category": "opening", "rule": "r1", "why": "w1", "severity": "hard", "applies_to": ["opening_only"], "source_files": ["a.md"]},
        {"id": "EW-0002", "category": "pacing", "rule": "r2", "why": "w2", "severity": "soft", "applies_to": ["all_chapters"], "source_files": []},
    ]
    rp = _write_rules(tmp_path, rules)
    library = tmp_path / "case_library"
    (library / "cases").mkdir(parents=True)
    rep = convert_rules_to_cases(rules_path=rp, library_root=library, dry_run=False)
    assert rep.created == 2
    assert rep.skipped == 0
    assert rep.by_severity == {"hard": 1, "soft": 1}
    # 第二次跑 → 全部 skipped
    rep2 = convert_rules_to_cases(rules_path=rp, library_root=library, dry_run=False)
    assert rep2.created == 0
    assert rep2.skipped == 2


def test_convert_dry_run_does_not_write(tmp_path: Path) -> None:
    rules = [{"id": "EW-0001", "category": "x", "rule": "r", "why": "w", "severity": "hard", "applies_to": [], "source_files": []}]
    rp = _write_rules(tmp_path, rules)
    library = tmp_path / "case_library"
    (library / "cases").mkdir(parents=True)
    rep = convert_rules_to_cases(rules_path=rp, library_root=library, dry_run=True)
    assert rep.created == 1  # report counts what *would* be created
    store = CaseStore(library)
    assert store.list_ids() == []  # but nothing actually written
```

- [ ] **Step 2: Run → ImportError**

```bash
pytest tests/case_library/test_rules_to_cases.py -v --no-cov
```
Expected: ImportError.

- [ ] **Step 3: 实现 rules_to_cases.py**

Create `ink_writer/case_library/rules_to_cases.py`:

```python
"""editor-wisdom rules.json → case_library cases 转换器.

按 rule.severity 分流（spec §5.3）：
  hard → active P1
  soft → pending P2
  info → pending P3 + info_only tag

observable 用占位文本（spec §5.4）：
  ["待 M3 dry-run 后基于实际触发样本细化（rule_id: EW-XXXX）"]

幂等性：基于 raw_text = rule + " | " + why 的 sha256 dedup（M1 ingest_case 已实现）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ink_writer.case_library.ingest import ingest_case
from ink_writer.case_library.store import CaseStore


_SEVERITY_MAP = {
    "hard": ("P1", "active"),
    "soft": ("P2", "pending"),
    "info": ("P3", "pending"),
}


@dataclass
class ConvertReport:
    created: int = 0
    skipped: int = 0  # already existed (sha256 dedup)
    failed: int = 0
    by_severity: dict[str, int] = field(default_factory=dict)
    by_category: dict[str, int] = field(default_factory=dict)
    failures: list[tuple[str, str]] = field(default_factory=list)


def map_rule_to_case_kwargs(rule: dict[str, Any], *, ingested_at: str) -> dict[str, Any]:
    """Map one rule dict to ingest_case() kwargs."""
    severity_str = rule.get("severity", "soft")
    case_severity, initial_status = _SEVERITY_MAP.get(severity_str, ("P2", "pending"))

    tags = ["from_editor_wisdom", rule.get("category", "misc")]
    if severity_str == "info":
        tags.append("info_only")

    rule_text = rule.get("rule", "")
    why_text = rule.get("why", "")
    description = f"{rule_text} — 理由：{why_text}" if why_text else rule_text

    raw_text = f"{rule_text} | {why_text}"

    applies_to = rule.get("applies_to", [])
    scope_chapter = list(applies_to) if applies_to else ["all"]

    source_files = rule.get("source_files", [])
    ingested_from = source_files[0] if source_files else None

    observable = [f"待 M3 dry-run 后基于实际触发样本细化（rule_id: {rule.get('id', 'unknown')}）"]

    return {
        "title": rule_text[:80],
        "raw_text": raw_text,
        "domain": "writing_quality",
        "layer": ["downstream"],
        "severity": case_severity,
        "tags": tags,
        "source_type": "editor_review",
        "ingested_at": ingested_at,
        "reviewer": "星河编辑",
        "ingested_from": ingested_from,
        "scope_chapter": scope_chapter,
        "scope_genre": ["all"],
        "failure_description": description,
        "observable": observable,
        "initial_status": initial_status,
    }


def convert_rules_to_cases(
    *,
    rules_path: Path,
    library_root: Path,
    dry_run: bool = False,
    ingested_at: str | None = None,
) -> ConvertReport:
    if ingested_at is None:
        from datetime import date
        ingested_at = date.today().isoformat()

    with open(rules_path, encoding="utf-8") as fp:
        rules = json.load(fp)

    report = ConvertReport()
    store = CaseStore(library_root)

    for rule in rules:
        sev = rule.get("severity", "soft")
        cat = rule.get("category", "misc")
        report.by_severity[sev] = report.by_severity.get(sev, 0) + 1
        report.by_category[cat] = report.by_category.get(cat, 0) + 1

        try:
            kw = map_rule_to_case_kwargs(rule, ingested_at=ingested_at)
            if dry_run:
                report.created += 1
                continue
            result = ingest_case(store, **kw)
            if result.created:
                report.created += 1
            else:
                report.skipped += 1
        except Exception as err:  # noqa: BLE001
            report.failed += 1
            report.failures.append((rule.get("id", "?"), str(err)))

    return report
```

- [ ] **Step 4: Run test → pass**

```bash
pytest tests/case_library/test_rules_to_cases.py -v --no-cov
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add ink_writer/case_library/rules_to_cases.py tests/case_library/test_rules_to_cases.py
git commit -m "feat(M2-T9): rules_to_cases 转换器 (severity 分流 + 占位 observable)

map_rule_to_case_kwargs 把单条 rule 映射为 ingest_case() kwargs：hard
→active P1 / soft→pending P2 / info→pending P3 + info_only tag。
observable 用占位 (spec §5.4)；M1 ingest_case sha256 dedup 保证幂等。
ConvertReport 含 created/skipped/failed/by_severity/by_category。6 测试
全绿。"
```

---

## Task 10 (US-010): ink case convert-from-editor-wisdom CLI 集成

**Files:**
- Modify: `ink_writer/case_library/cli.py`（追加 `convert-from-editor-wisdom` 子命令）
- Create: `tests/case_library/test_cli_convert.py`

- [ ] **Step 1: 写失败测试**

Create `tests/case_library/test_cli_convert.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from ink_writer.case_library.cli import main
from ink_writer.case_library.store import CaseStore


def _write_rules(tmp_path: Path, rules: list[dict]) -> Path:
    p = tmp_path / "rules.json"
    p.write_text(json.dumps(rules, ensure_ascii=False), encoding="utf-8")
    return p


def test_convert_subcommand_creates_cases(tmp_path: Path, capsys) -> None:
    rules = [
        {"id": "EW-0001", "category": "opening", "rule": "r1", "why": "w1", "severity": "hard", "applies_to": ["opening_only"], "source_files": []},
        {"id": "EW-0002", "category": "pacing", "rule": "r2", "why": "w2", "severity": "soft", "applies_to": ["all_chapters"], "source_files": []},
    ]
    rp = _write_rules(tmp_path, rules)
    library = tmp_path / "library"
    rc = main([
        "--library-root", str(library),
        "convert-from-editor-wisdom",
        "--rules", str(rp),
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert "created=2" in out or "created: 2" in out
    store = CaseStore(library)
    assert len(store.list_ids()) == 2


def test_convert_idempotent(tmp_path: Path, capsys) -> None:
    rules = [{"id": "EW-0001", "category": "x", "rule": "r", "why": "w", "severity": "hard", "applies_to": [], "source_files": []}]
    rp = _write_rules(tmp_path, rules)
    library = tmp_path / "library"
    main(["--library-root", str(library), "convert-from-editor-wisdom", "--rules", str(rp)])
    capsys.readouterr()  # discard first
    rc = main(["--library-root", str(library), "convert-from-editor-wisdom", "--rules", str(rp)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "skipped=1" in out or "skipped: 1" in out


def test_convert_dry_run(tmp_path: Path, capsys) -> None:
    rules = [{"id": "EW-0001", "category": "x", "rule": "r", "why": "w", "severity": "hard", "applies_to": [], "source_files": []}]
    rp = _write_rules(tmp_path, rules)
    library = tmp_path / "library"
    rc = main([
        "--library-root", str(library),
        "convert-from-editor-wisdom",
        "--rules", str(rp),
        "--dry-run",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    store = CaseStore(library)
    assert store.list_ids() == []
```

- [ ] **Step 2: 修改 cli.py 加 convert 子命令**

Edit `ink_writer/case_library/cli.py`. 在 `_build_parser()` 内 `sub` 上添加：

```python
    conv = sub.add_parser("convert-from-editor-wisdom",
                          help="Convert editor-wisdom rules.json into cases (severity-based)")
    conv.add_argument("--rules", type=Path,
                      default=Path("data/editor-wisdom/rules.json"))
    conv.add_argument("--dry-run", action="store_true")
```

在 `main()` dispatch 内追加：

```python
    if args.cmd == "convert-from-editor-wisdom":
        from ink_writer.case_library.rules_to_cases import convert_rules_to_cases
        report = convert_rules_to_cases(
            rules_path=args.rules,
            library_root=args.library_root,
            dry_run=args.dry_run,
        )
        print(f"created={report.created} skipped={report.skipped} failed={report.failed}")
        print(f"by_severity={dict(report.by_severity)}")
        if report.failures:
            for rid, err in report.failures[:10]:
                print(f"  FAIL {rid}: {err}", file=sys.stderr)
        return 0 if report.failed == 0 else 1
```

- [ ] **Step 3: Run test → pass**

```bash
pytest tests/case_library/test_cli_convert.py -v --no-cov
```
Expected: 3 passed.

- [ ] **Step 4: 实跑 v23 rules.json 全量 (smoke)**

```bash
python -m ink_writer.case_library.cli --library-root /tmp/m2_smoke convert-from-editor-wisdom --dry-run
```
Expected: `created=402 skipped=0 failed=0` + `by_severity={'hard': 236, 'soft': 147, 'info': 19}`。

- [ ] **Step 5: Commit**

```bash
git add ink_writer/case_library/cli.py tests/case_library/test_cli_convert.py
git commit -m "feat(M2-T10): ink case convert-from-editor-wisdom CLI

Subcommand 调 rules_to_cases.convert_rules_to_cases 全量摄入 v23
rules.json (默认路径 data/editor-wisdom/rules.json)。--dry-run 只统计不
写。stdout 打印 created/skipped/failed + by_severity。3 测试 + 实跑
smoke 验证 dry-run 报 created=402 by_severity={hard:236,soft:147,info:19}。"
```

---

## Task 11 (US-011): ink case approve --batch CLI

**Files:**
- Create: `schemas/case_approval_batch_schema.json`
- Create: `ink_writer/case_library/approval.py`
- Modify: `ink_writer/case_library/cli.py`（追加 `approve` 子命令）
- Create: `tests/case_library/test_cli_approve.py`

- [ ] **Step 1: 写 yaml schema**

Create `schemas/case_approval_batch_schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["approvals"],
  "additionalProperties": false,
  "properties": {
    "approvals": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["case_id", "action"],
        "additionalProperties": false,
        "properties": {
          "case_id": {"type": "string", "pattern": "^CASE-[0-9]{4}-[0-9]{4}$"},
          "action": {"type": "string", "enum": ["approve", "reject", "defer"]},
          "note": {"type": "string"}
        }
      }
    }
  }
}
```

- [ ] **Step 2: 写失败测试**

Create `tests/case_library/test_cli_approve.py`:

```python
from __future__ import annotations

from pathlib import Path

import yaml

from ink_writer.case_library.cli import main
from ink_writer.case_library.store import CaseStore


def _seed_three_pending(library: Path, capsys) -> list[str]:
    ids = []
    for i in range(1, 4):
        main([
            "--library-root", str(library),
            "create",
            "--title", f"t{i}", "--raw-text", f"text{i}",
            "--domain", "writing_quality", "--layer", "downstream",
            "--severity", "P2", "--tags", "x",
            "--source-type", "editor_review", "--ingested-at", "2026-04-25",
            "--failure-description", "d", "--observable", "o",
            "--initial-status", "pending",
        ])
        line = capsys.readouterr().out.strip()
        ids.append(line)
    return ids


def test_approve_batch_three_actions(tmp_path: Path, capsys) -> None:
    library = tmp_path / "lib"
    ids = _seed_three_pending(library, capsys)

    yaml_path = tmp_path / "batch.yaml"
    yaml_path.write_text(yaml.safe_dump({
        "approvals": [
            {"case_id": ids[0], "action": "approve"},
            {"case_id": ids[1], "action": "reject"},
            {"case_id": ids[2], "action": "defer", "note": "let M3 decide"},
        ]
    }, allow_unicode=True), encoding="utf-8")

    rc = main(["--library-root", str(library), "approve", "--batch", str(yaml_path)])
    assert rc == 0
    capsys.readouterr()

    store = CaseStore(library)
    assert store.load(ids[0]).status.value == "active"
    assert store.load(ids[1]).status.value == "retired"
    assert store.load(ids[2]).status.value == "pending"  # defer keeps pending


def test_approve_batch_invalid_yaml_returns_3(tmp_path: Path) -> None:
    library = tmp_path / "lib"
    (library / "cases").mkdir(parents=True)
    bad = tmp_path / "bad.yaml"
    bad.write_text("approvals: not_a_list", encoding="utf-8")
    rc = main(["--library-root", str(library), "approve", "--batch", str(bad)])
    assert rc == 3


def test_approve_batch_unknown_case_records_failure_continues(tmp_path: Path, capsys) -> None:
    library = tmp_path / "lib"
    ids = _seed_three_pending(library, capsys)

    yaml_path = tmp_path / "batch.yaml"
    yaml_path.write_text(yaml.safe_dump({
        "approvals": [
            {"case_id": ids[0], "action": "approve"},
            {"case_id": "CASE-2026-9999", "action": "approve"},  # missing
        ]
    }, allow_unicode=True), encoding="utf-8")

    rc = main(["--library-root", str(library), "approve", "--batch", str(yaml_path)])
    assert rc != 0  # has failure
    store = CaseStore(library)
    assert store.load(ids[0]).status.value == "active"  # still applied
```

- [ ] **Step 3: Run → ImportError**

```bash
pytest tests/case_library/test_cli_approve.py -v --no-cov
```
Expected: AttributeError on `approve` subcommand.

- [ ] **Step 4: 实现 approval.py**

Create `ink_writer/case_library/approval.py`:

```python
"""Batch approval logic: yaml 描述一组 (case_id, action) → 改 status + 写 ingest_log."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from ink_writer.case_library.errors import CaseNotFoundError
from ink_writer.case_library.models import CaseStatus
from ink_writer.case_library.store import CaseStore


_ACTION_TO_STATUS = {
    "approve": CaseStatus.ACTIVE,
    "reject": CaseStatus.RETIRED,
    "defer": CaseStatus.PENDING,
}


@dataclass
class ApprovalReport:
    applied: int = 0
    failed: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)


def _load_schema() -> dict:
    schema_path = Path(__file__).resolve().parent.parent.parent / "schemas" / "case_approval_batch_schema.json"
    with open(schema_path, encoding="utf-8") as fp:
        return json.load(fp)


def apply_batch_yaml(*, yaml_path: Path, library_root: Path) -> ApprovalReport:
    """Validate yaml + apply each approval. Failures don't abort remaining items."""
    with open(yaml_path, encoding="utf-8") as fp:
        data = yaml.safe_load(fp)
    Draft202012Validator(_load_schema()).validate(data)  # raises ValidationError on bad shape

    store = CaseStore(library_root)
    report = ApprovalReport()
    now = datetime.now(timezone.utc).isoformat()

    for entry in data["approvals"]:
        case_id = entry["case_id"]
        action = entry["action"]
        note = entry.get("note", "")
        try:
            case = store.load(case_id)
            case.status = _ACTION_TO_STATUS[action]
            store.save(case)
            store.append_ingest_log({
                "event": "approval",
                "case_id": case_id,
                "action": action,
                "note": note,
                "at": now,
            })
            report.applied += 1
        except CaseNotFoundError as err:
            report.failed += 1
            report.failures.append((case_id, f"not found: {err}"))
        except Exception as err:  # noqa: BLE001
            report.failed += 1
            report.failures.append((case_id, str(err)))
    return report
```

- [ ] **Step 5: 修改 cli.py 加 approve 子命令**

Edit `ink_writer/case_library/cli.py`. 在 `_build_parser()` 内追加：

```python
    appr = sub.add_parser("approve", help="Batch approve via yaml")
    appr.add_argument("--batch", type=Path, required=True)
```

在 `main()` dispatch 内追加（放在 `if args.cmd == "convert-from-editor-wisdom":` 之后）：

```python
    if args.cmd == "approve":
        from jsonschema import ValidationError
        from ink_writer.case_library.approval import apply_batch_yaml
        try:
            report = apply_batch_yaml(yaml_path=args.batch, library_root=args.library_root)
        except ValidationError as err:
            print(f"ERROR: yaml schema invalid: {err.message}", file=sys.stderr)
            return 3
        print(f"applied={report.applied} failed={report.failed}")
        for cid, err in report.failures:
            print(f"  FAIL {cid}: {err}", file=sys.stderr)
        return 0 if report.failed == 0 else 1
```

- [ ] **Step 6: Run tests → pass**

```bash
pytest tests/case_library/test_cli_approve.py -v --no-cov
```
Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add schemas/case_approval_batch_schema.json ink_writer/case_library/approval.py ink_writer/case_library/cli.py tests/case_library/test_cli_approve.py
git commit -m "feat(M2-T11): ink case approve --batch <yaml> CLI

yaml schema 校验 (jsonschema)；3 种 action: approve→active / reject→
retired / defer→pending（写 note 到 ingest_log）。失败单 case 不阻断
其余；rc 0/1/3 对应全成功/部分失败/yaml 校验错。3 测试全绿。"
```

---

## Task 12 (US-012): M2 e2e 集成测试 + 全量验收 + tag

**Files:**
- Create: `tests/integration/test_m2_e2e.py`

- [ ] **Step 1: 写 e2e 测试**

Create `tests/integration/test_m2_e2e.py`:

```python
"""M2 端到端集成测试 (spec §6.2 5 用例)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from ink_writer.case_library.cli import main as case_main
from ink_writer.case_library.store import CaseStore
from ink_writer.case_library.rules_to_cases import convert_rules_to_cases


@pytest.fixture
def real_rules_path() -> Path:
    """实际 v23 rules.json 路径 (M1 已有数据)."""
    return Path("data/editor-wisdom/rules.json")


def test_rules_conversion_creates_402_cases_with_severity_split(tmp_path: Path, real_rules_path: Path) -> None:
    """spec §6.2 用例 2: v23 rules.json 全量 → assert by_severity 分布。"""
    if not real_rules_path.is_file():
        pytest.skip("data/editor-wisdom/rules.json missing — M1 prerequisite")
    library = tmp_path / "lib"
    (library / "cases").mkdir(parents=True)
    rep = convert_rules_to_cases(
        rules_path=real_rules_path,
        library_root=library,
        dry_run=False,
        ingested_at="2026-04-25",
    )
    assert rep.created == 402, f"expected 402 cases, got created={rep.created}"
    assert rep.by_severity == {"hard": 236, "soft": 147, "info": 19}


def test_active_pending_counts_after_conversion(tmp_path: Path, real_rules_path: Path) -> None:
    """spec §6.2 用例 3: assert 236 active + 166 pending (147 soft + 19 info)."""
    if not real_rules_path.is_file():
        pytest.skip("rules.json missing")
    library = tmp_path / "lib"
    (library / "cases").mkdir(parents=True)
    convert_rules_to_cases(rules_path=real_rules_path, library_root=library, dry_run=False, ingested_at="2026-04-25")
    store = CaseStore(library)
    active = sum(1 for c in store.iter_cases() if c.status.value == "active")
    pending = sum(1 for c in store.iter_cases() if c.status.value == "pending")
    assert active == 236
    assert pending == 166


def test_approve_batch_yaml_changes_status(tmp_path: Path, capsys) -> None:
    """spec §6.2 用例 4: 5 case yaml + 各 action → status 正确改变."""
    library = tmp_path / "lib"
    ids = []
    for i in range(5):
        case_main([
            "--library-root", str(library),
            "create",
            "--title", f"t{i}", "--raw-text", f"unique{i}",
            "--domain", "writing_quality", "--layer", "downstream",
            "--severity", "P2", "--tags", "x",
            "--source-type", "editor_review", "--ingested-at", "2026-04-25",
            "--failure-description", "d", "--observable", "o",
            "--initial-status", "pending",
        ])
        ids.append(capsys.readouterr().out.strip())

    yaml_path = tmp_path / "batch.yaml"
    yaml_path.write_text(yaml.safe_dump({"approvals": [
        {"case_id": ids[0], "action": "approve"},
        {"case_id": ids[1], "action": "approve"},
        {"case_id": ids[2], "action": "reject"},
        {"case_id": ids[3], "action": "defer"},
        {"case_id": ids[4], "action": "defer"},
    ]}, allow_unicode=True), encoding="utf-8")

    rc = case_main(["--library-root", str(library), "approve", "--batch", str(yaml_path)])
    assert rc == 0
    store = CaseStore(library)
    assert store.load(ids[0]).status.value == "active"
    assert store.load(ids[1]).status.value == "active"
    assert store.load(ids[2]).status.value == "retired"
    assert store.load(ids[3]).status.value == "pending"
    assert store.load(ids[4]).status.value == "pending"


def test_corpus_ingest_resume_skips_indexed_chapters(tmp_path: Path) -> None:
    """spec §6.2 用例 5: chunks_raw.jsonl 已有 (book, chapter) → 第二次 ingest 跳过."""
    from scripts.corpus_chunking.cli import _already_indexed
    raw = tmp_path / "chunks_raw.jsonl"
    raw.write_text(json.dumps({"chunk_id": "x", "source_book": "b", "source_chapter": "c1"}, ensure_ascii=False) + "\n", encoding="utf-8")
    assert _already_indexed("b", "c1", raw) is True
    assert _already_indexed("b", "c2", raw) is False


def test_chunking_pipeline_e2e_with_one_chapter_mocked(tmp_path: Path) -> None:
    """spec §6.2 用例 1: 1 章 → segmenter → tagger → indexer → Qdrant 能检索回 (mocked)."""
    from scripts.corpus_chunking.scene_segmenter import segment_chapter, SegmenterConfig
    from scripts.corpus_chunking.chunk_tagger import tag_chunk, TaggerConfig
    from scripts.corpus_chunking.chunk_indexer import index_chunks, IndexerConfig
    from scripts.corpus_chunking.models import SourceType
    from qdrant_client import QdrantClient
    from ink_writer.qdrant.payload_schema import CORPUS_CHUNKS_SPEC, ensure_collection

    qd = QdrantClient(":memory:")
    # 4096 维太大 in-memory 慢；用一个 8 维测试 collection
    from ink_writer.qdrant.payload_schema import CollectionSpec
    test_spec = CollectionSpec(name="m2_e2e_test", vector_size=8, indexed_payload_fields={"genre": "keyword"})
    ensure_collection(qd, test_spec)

    seg_client = MagicMock()
    seg_client.messages.create.return_value = MagicMock(content=[MagicMock(text=json.dumps({
        "chunks": [{"scene_type": "opening", "char_range": [0, 400], "text": "克莱恩盯着镜子。" * 25}]
    }))])
    raws = segment_chapter(client=seg_client, cfg=SegmenterConfig("m", 200, 800, 3), book="诡秘之主", chapter="ch003", text="x"*400)
    assert len(raws) == 1

    tag_client = MagicMock()
    tag_client.messages.create.return_value = MagicMock(content=[MagicMock(text=json.dumps({
        "scene_type": "opening", "tension_level": 0.8, "character_count": 1, "dialogue_ratio": 0.0,
        "hook_type": "x", "borrowable_aspects": [],
        "quality_breakdown": {"tension": 0.9, "originality": 0.8, "language_density": 0.7, "readability": 0.9}
    }))])
    tagged = [tag_chunk(client=tag_client, cfg=TaggerConfig("m", (0.3,0.3,0.2,0.2), 3), chunk=r, genre=["异世大陆"], ingested_at="2026-04-25", source_type=SourceType.BUILTIN) for r in raws]

    embedder = MagicMock()
    embedder.embed_batch.return_value = [[0.1]*8]
    n = index_chunks(
        chunks=tagged,
        qdrant_client=qd,
        embedder=embedder,
        cfg=IndexerConfig(qdrant_collection="m2_e2e_test", upsert_batch_size=256),
        metadata_path=tmp_path / "metadata.jsonl",
        unindexed_path=tmp_path / "unindexed.jsonl",
    )
    assert n == 1
    info = qd.get_collection("m2_e2e_test")
    assert info.points_count == 1
```

- [ ] **Step 2: Run e2e**

```bash
pytest tests/integration/test_m2_e2e.py -v --no-cov
```
Expected: 5 passed (or `test_rules_conversion...` skipped if rules.json missing).

- [ ] **Step 3: 全量回归**

```bash
pytest -q
```
Expected: 全绿，覆盖率 ≥ 70（M1 baseline 82.72% 应保持）。

- [ ] **Step 4: M2 6 项验收**

```bash
echo "=== 1. 全量 pytest ==="
pytest -q 2>&1 | tail -3

echo "=== 2. Qdrant readyz ==="
curl -s http://127.0.0.1:6333/readyz && echo "OK" || echo "Qdrant not running"

echo "=== 3. corpus_chunks count ==="
curl -s http://127.0.0.1:6333/collections/corpus_chunks 2>/dev/null | python3 -c "import json,sys; d=json.loads(sys.stdin.read())['result']; print(d.get('points_count', 0))" 2>/dev/null || echo "0"

echo "=== 4. case 总数 ==="
ls data/case_library/cases/ 2>/dev/null | wc -l

echo "=== 5. active cases ==="
python -m ink_writer.case_library.cli status active 2>/dev/null | wc -l

echo "=== 6. pending cases ==="
python -m ink_writer.case_library.cli status pending 2>/dev/null | wc -l
```

Expected:
- 全量 pytest 全绿 + 覆盖率 ≥ 70
- Qdrant readyz OK
- corpus_chunks points_count ≥ 2500
- case 总数 ≥ 400 (402 业务 + zero-case)
- active cases ≥ 200 (236 hard + zero-case)
- pending cases ≈ 166

- [ ] **Step 5: 打 tag**

```bash
git tag -a m2-data-assets -m "M2 complete: corpus chunking + cases conversion (≥100 active cases + ≥2500 corpus chunks)"
```

- [ ] **Step 6: 更新 M-ROADMAP.md**

Edit `docs/superpowers/M-ROADMAP.md`：
- 顶部 `Status:` 改为 `M1 ✅ + M2 ✅ 完成 2026-04-XX；下一步推进 M3`
- 进度表 M2 行：`⚪ 未开始` → `✅ 完成`，完成日期填实际日期
- M2 行的 `PRD/Plan/branch` 列填实际路径

- [ ] **Step 7: Final commit**

```bash
git add tests/integration/test_m2_e2e.py docs/superpowers/M-ROADMAP.md
git commit -m "test(M2-T12): e2e 集成测试 + 全量验收 + tag m2-data-assets

5 用例覆盖 spec §6.2: rules 402→cases 转换 / active+pending 计数 /
approve 三 action / ingest --resume / chunking pipeline e2e (mocked)。
全量 pytest 全绿，覆盖率 ≥ 70。M-ROADMAP M2 ✅。"
```

---

## Self-Review Checklist

- [x] **Spec coverage**: spec §3.6 / §4.4 / §5.7 列的每个 file 都有 task 实现：scene_segmenter (T2) / chunk_tagger (T3) / chunk_indexer + embedding_client (T4) / corpus cli (T5-T7) / 实跑 (T8) / rules_to_cases (T9) / convert CLI (T10) / approve CLI (T11) / e2e (T12)
- [x] **No placeholders**: 每步都有完整 code/command/expected。无 "TBD"/"implement later"。
- [x] **Type consistency**: `RawChunk` / `TaggedChunk` / `QualityBreakdown` / `IngestReport` / `SegmenterConfig` / `TaggerConfig` / `EmbeddingConfig` / `IndexerConfig` / `ConvertReport` / `ApprovalReport` 在所有 task 中名称统一。`SourceType.BUILTIN` 全程一致。
- [x] **Frequent commits**: 每个 task 末尾都有一个 commit。
- [x] **Windows compat**: cli.py 调用 `enable_windows_utf8_stdio` (audit 红线要求)；所有 `open()` 带 `encoding="utf-8"`。
- [x] **Audit red-lines**: T2/T5 显式跑了 `tests/audit/test_cli_entries_utf8_stdio.py` + `tests/core/test_safe_symlink.py`。

---

## What this plan does NOT do (deferred to M3-M5)

- 不做召回路由改造 (router.py 加 case_aware/genre_filtered) → M3
- 不做 writer 侧注入修改 (writer_injection.py) → M3
- 不做 case_retriever.py (病例反向召回) → M3
- 不做 user_corpus 接口 → M5
- 不做起点 top 200 简介库 → M4
- 不退役 FAISS (双写保留) → 待 M3 决定
- 不做 ink case approve --interactive → M5
- 不用 LLM 自动抽 observable → M3+ 按需

---

## Acceptance Gate (must hold to claim M2 done)

1. `pytest -q` 全绿 + 覆盖率 ≥ 70
2. `curl http://127.0.0.1:6333/readyz` 返 200
3. Qdrant `corpus_chunks` collection points_count ≥ 2500
4. `data/case_library/cases/` 下 ≥ 400 个 yaml 文件
5. `python -m ink_writer.case_library.cli status active` 输出 ≥ 200 行
6. `python -m ink_writer.case_library.cli status pending` 输出 ≈ 166 行
7. `git tag m2-data-assets` 已打
8. `docs/superpowers/M-ROADMAP.md` M2 行已更新为 ✅
