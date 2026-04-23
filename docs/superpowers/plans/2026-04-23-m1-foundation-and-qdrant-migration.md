# M1 Foundation & Qdrant Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 spec §9 M1：Case Library 基础设施 + Qdrant 替换 FAISS + Preflight Health Checker + reference_corpus 软链接修复，端到端打通"病例创建—查询—健康检查—infra 自愈"闭环。

**Architecture:** 三个新 Python 子包（`ink_writer/case_library/`, `ink_writer/qdrant/`, `ink_writer/preflight/`）+ 一组运维脚本（`scripts/qdrant/`, `scripts/maintenance/`）。Case 数据物理形态：一案一 YAML 文件 + sqlite 倒排索引 + jsonl 全量打包，权威数据是 YAML。Qdrant 走单机 docker，与现有 Qwen+jina API 兼容，FAISS 双写 7 天后退役。

**Tech Stack:** Python 3.12+ / pytest / jsonschema 4.26（已有）/ qdrant-client（新增）/ sqlite3（stdlib）/ pyyaml 6.0（已有）/ Docker (Qdrant 服务)。

**Reference spec:** `docs/superpowers/specs/2026-04-23-case-library-driven-quality-overhaul-design.md` §1-§3, §8, §9 M1。

---

## File Structure

### 新增 Python 模块

| 文件 | 职责 |
|---|---|
| `ink_writer/case_library/__init__.py` | 包导出：`Case`, `CaseStore`, `CaseIndex`, 常量 |
| `ink_writer/case_library/models.py` | `Case` dataclass + 枚举（Status/Severity/Domain/Layer/SourceType）|
| `ink_writer/case_library/schema.py` | JSON Schema 加载 + `validate_case_dict()` |
| `ink_writer/case_library/store.py` | YAML 文件 CRUD + jsonl 打包 + ingest_log 追加 |
| `ink_writer/case_library/index.py` | sqlite 倒排索引（tag/genre/layer/status → case_id）|
| `ink_writer/case_library/ingest.py` | `ingest_from_text(raw_text, source)` 幂等去重摄入 |
| `ink_writer/case_library/cli.py` | `ink case list/show/create/status/rebuild-index` |
| `ink_writer/case_library/errors.py` | `CaseValidationError`, `CaseNotFoundError`, `DuplicateCaseError` |
| `ink_writer/qdrant/__init__.py` | 包导出 |
| `ink_writer/qdrant/client.py` | `get_qdrant_client()` 单例 + 重试封装 |
| `ink_writer/qdrant/payload_schema.py` | collection 定义（`editor_wisdom_rules`, `corpus_chunks`） + payload 字段 |
| `ink_writer/qdrant/errors.py` | `QdrantUnreachableError` |
| `ink_writer/preflight/__init__.py` | 包导出 |
| `ink_writer/preflight/checker.py` | `run_preflight()` 跑 6 项检查 + 返回 `PreflightReport` |
| `ink_writer/preflight/checks.py` | 6 个独立 check 函数 |
| `ink_writer/preflight/cli.py` | `ink preflight` 子命令 |
| `ink_writer/preflight/errors.py` | `PreflightError` |

### 新增运维脚本

| 文件 | 职责 |
|---|---|
| `scripts/maintenance/fix_reference_corpus_symlinks.py` | 删除断链 + 硬拷贝原文（方案 A）|
| `scripts/qdrant/docker-compose.yml` | Qdrant 单机服务定义 |
| `scripts/qdrant/start.sh` | macOS/Linux 启动脚本 |
| `scripts/qdrant/start.ps1` | Windows PowerShell 启动脚本（UTF-8 BOM）|
| `scripts/qdrant/stop.sh` | 停止脚本 |
| `scripts/qdrant/stop.ps1` | 停止脚本（Windows）|
| `scripts/qdrant/README.md` | Qdrant 运维说明 |
| `scripts/qdrant/migrate_faiss_to_qdrant.py` | FAISS 数据迁移脚本（一次性 + 双写支持）|
| `scripts/case_library/init_zero_case.py` | 创建 CASE-2026-0000 |

### 新增 Schema / 数据

| 文件 | 职责 |
|---|---|
| `schemas/case_schema.json` | Case YAML 的 JSON Schema |
| `data/case_library/cases/.gitkeep` | 占位让 git 追踪空目录 |
| `data/case_library/cases/CASE-2026-0000.yaml` | 零号 infra_health 病例（由脚本生成）|

### 新增测试

| 文件 | 职责 |
|---|---|
| `tests/case_library/__init__.py` | — |
| `tests/case_library/conftest.py` | fixtures: `tmp_case_dir`, `sample_case_dict` |
| `tests/case_library/test_schema.py` | JSON Schema 校验 |
| `tests/case_library/test_models.py` | Case dataclass 序列化/反序列化 |
| `tests/case_library/test_store.py` | YAML CRUD + 幂等 |
| `tests/case_library/test_index.py` | sqlite 倒排查询 |
| `tests/case_library/test_ingest.py` | hash 去重 |
| `tests/case_library/test_cli.py` | CLI 子命令 |
| `tests/qdrant/__init__.py` | — |
| `tests/qdrant/conftest.py` | fixture: `qdrant_test_collection`（用 in-memory client）|
| `tests/qdrant/test_client.py` | client 连接 + 重试 |
| `tests/qdrant/test_payload_schema.py` | collection 定义 + 字段 |
| `tests/preflight/__init__.py` | — |
| `tests/preflight/conftest.py` | fixtures |
| `tests/preflight/test_checks.py` | 6 项检查独立测试 |
| `tests/preflight/test_checker.py` | `run_preflight()` 整合 |
| `tests/preflight/test_cli.py` | CLI 子命令 |
| `tests/maintenance/__init__.py` | — |
| `tests/maintenance/test_fix_reference_corpus_symlinks.py` | 修复脚本测试 |
| `tests/scripts/test_migrate_faiss_to_qdrant.py` | 迁移脚本测试 |
| `tests/integration/test_m1_e2e.py` | M1 端到端：preflight 报错 → 自动建 case → ink case list 能查到 |

### 修改

| 文件 | 改动 |
|---|---|
| `pytest.ini` | `testpaths` 追加 `tests/case_library tests/qdrant tests/preflight tests/maintenance` |
| `requirements.txt` | 追加 `qdrant-client~=1.12` |
| `ink-writer/skills/ink-write/SKILL.md` | 新增 Step 0 调 preflight；Windows PowerShell sibling 块 |

---

## Task Sequence Overview

```
Task 1   reference_corpus 软链接修复（独立、最快价值）
Task 2   测试基础设施（pytest.ini + requirements.txt + 目录骨架）
Task 3   Case Schema (JSON Schema)
Task 4   Case Models (dataclass)
Task 5   Case Store (YAML CRUD + jsonl 打包 + ingest_log)
Task 6   Case Index (sqlite 倒排)
Task 7   Case Ingest（幂等 hash 去重）
Task 8   Case CLI (ink case)
Task 9   CASE-2026-0000 零号病例
Task 10  Qdrant Docker 部署 + 启动脚本
Task 11  Qdrant 客户端封装 (ink_writer/qdrant/client.py)
Task 12  Qdrant Payload Schema (collection 定义)
Task 13  FAISS → Qdrant 迁移脚本（含双写）
Task 14  Preflight 6 个独立 check 函数
Task 15  Preflight checker + 自动建 infra_health case
Task 16  Preflight CLI + 集成到 ink-write SKILL.md
Task 17  M1 端到端集成测试 + 验收
```

---

## Task 1: 修复 reference_corpus 软链接（方案 A 硬拷贝）

**Files:**
- Create: `scripts/maintenance/fix_reference_corpus_symlinks.py`
- Create: `tests/maintenance/__init__.py`
- Create: `tests/maintenance/test_fix_reference_corpus_symlinks.py`

**Why:** spec §9 M1；当前 `benchmark/reference_corpus/<书名>/chapters/*.txt` 是绝对路径软链接指向 `/Users/cipher/AI/ink/...`（无"小说"层级），项目搬迁后全部断链。原文在 `benchmark/corpus/` 下完整存在，方案 A 硬拷贝最稳。

- [ ] **Step 1: 创建测试目录骨架**

```bash
mkdir -p tests/maintenance && touch tests/maintenance/__init__.py
```

- [ ] **Step 2: 写失败测试 — 模拟断链 + 验证修复结果**

Create `tests/maintenance/test_fix_reference_corpus_symlinks.py`:

```python
"""Tests for fix_reference_corpus_symlinks.

Strategy: build a tiny fake project layout in tmp_path mirroring the real
problem (benchmark/reference_corpus/<book>/chapters/*.txt symlinks pointing
to a non-existent absolute path; benchmark/corpus/<book>/chapters/*.txt
exists with real content), then run the fixer and assert all targets are
now real files with identical bytes.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.maintenance.fix_reference_corpus_symlinks import (
    fix_reference_corpus_symlinks,
    FixReport,
)


@pytest.fixture
def fake_corpus_layout(tmp_path: Path) -> Path:
    benchmark = tmp_path / "benchmark"
    book = "诡秘之主"
    real_dir = benchmark / "corpus" / book / "chapters"
    real_dir.mkdir(parents=True)
    (real_dir / "ch001.txt").write_text("克莱恩盯着镜子。", encoding="utf-8")
    (real_dir / "ch002.txt").write_text("第二章内容。", encoding="utf-8")

    ref_dir = benchmark / "reference_corpus" / book / "chapters"
    ref_dir.mkdir(parents=True)
    # Broken absolute symlink (mimics the production bug).
    broken_target = "/nonexistent/path/ch001.txt"
    (ref_dir / "ch001.txt").symlink_to(broken_target)
    (ref_dir / "ch002.txt").symlink_to(broken_target)

    # manifest.json for completeness (the real fixer ignores it).
    (benchmark / "reference_corpus" / book / "manifest.json").write_text(
        '{"book_id":"x","title":"诡秘之主","chapters_count":2}',
        encoding="utf-8",
    )
    return benchmark


def test_fix_replaces_broken_symlinks_with_hard_copies(fake_corpus_layout: Path) -> None:
    report = fix_reference_corpus_symlinks(
        reference_root=fake_corpus_layout / "reference_corpus",
        corpus_root=fake_corpus_layout / "corpus",
    )
    ch1 = fake_corpus_layout / "reference_corpus" / "诡秘之主" / "chapters" / "ch001.txt"
    assert ch1.is_file() and not ch1.is_symlink()
    assert ch1.read_text(encoding="utf-8") == "克莱恩盯着镜子。"
    assert isinstance(report, FixReport)
    assert report.fixed_count == 2
    assert report.skipped_count == 0
    assert report.missing_source_count == 0


def test_fix_skips_already_real_files(fake_corpus_layout: Path) -> None:
    target = fake_corpus_layout / "reference_corpus" / "诡秘之主" / "chapters" / "ch001.txt"
    target.unlink()
    target.write_text("已经是真实文件", encoding="utf-8")

    report = fix_reference_corpus_symlinks(
        reference_root=fake_corpus_layout / "reference_corpus",
        corpus_root=fake_corpus_layout / "corpus",
    )
    assert report.skipped_count == 1
    assert target.read_text(encoding="utf-8") == "已经是真实文件"


def test_fix_records_missing_source(fake_corpus_layout: Path) -> None:
    (fake_corpus_layout / "corpus" / "诡秘之主" / "chapters" / "ch001.txt").unlink()
    report = fix_reference_corpus_symlinks(
        reference_root=fake_corpus_layout / "reference_corpus",
        corpus_root=fake_corpus_layout / "corpus",
    )
    assert report.missing_source_count == 1
    # ch002 still gets fixed.
    assert report.fixed_count == 1
```

- [ ] **Step 3: Run test to confirm it fails**

```bash
pytest tests/maintenance/test_fix_reference_corpus_symlinks.py -v
```
Expected: `ModuleNotFoundError: No module named 'scripts.maintenance.fix_reference_corpus_symlinks'`.

- [ ] **Step 4: Implement the fixer**

Create `scripts/maintenance/__init__.py` (empty):
```bash
mkdir -p scripts/maintenance && touch scripts/maintenance/__init__.py
```

Create `scripts/maintenance/fix_reference_corpus_symlinks.py`:

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fix broken absolute symlinks in benchmark/reference_corpus/.

Cause: project was relocated (e.g., /Users/cipher/AI/ → /Users/cipher/AI/小说/...)
but absolute symlinks were not regenerated. Strategy: hard-copy the real file
from benchmark/corpus/<book>/chapters/*.txt over the symlink. See spec §9 M1
and §1.3 (CASE-2026-0000 motivation).
"""
from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class FixReport:
    fixed_count: int = 0
    skipped_count: int = 0
    missing_source_count: int = 0
    fixed_paths: List[Path] = field(default_factory=list)
    missing_paths: List[Path] = field(default_factory=list)


def _iter_chapter_files(reference_root: Path):
    for book_dir in sorted(p for p in reference_root.iterdir() if p.is_dir()):
        chapters_dir = book_dir / "chapters"
        if not chapters_dir.is_dir():
            continue
        for chapter in sorted(chapters_dir.iterdir()):
            if chapter.suffix != ".txt":
                continue
            yield book_dir.name, chapter


def fix_reference_corpus_symlinks(
    reference_root: Path,
    corpus_root: Path,
) -> FixReport:
    """Replace broken symlinks with hard copies from corpus_root.

    Args:
        reference_root: e.g., benchmark/reference_corpus/
        corpus_root:    e.g., benchmark/corpus/

    Returns:
        FixReport summarising the fix run.
    """
    report = FixReport()
    for book, chapter_path in _iter_chapter_files(reference_root):
        if chapter_path.is_file() and not chapter_path.is_symlink():
            report.skipped_count += 1
            continue
        source = corpus_root / book / "chapters" / chapter_path.name
        if not source.is_file():
            report.missing_source_count += 1
            report.missing_paths.append(chapter_path)
            continue
        if chapter_path.is_symlink() or chapter_path.exists():
            chapter_path.unlink()
        shutil.copy2(source, chapter_path)
        report.fixed_count += 1
        report.fixed_paths.append(chapter_path)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reference-root",
        type=Path,
        default=Path("benchmark/reference_corpus"),
    )
    parser.add_argument(
        "--corpus-root",
        type=Path,
        default=Path("benchmark/corpus"),
    )
    args = parser.parse_args(argv)
    report = fix_reference_corpus_symlinks(args.reference_root, args.corpus_root)
    print(
        f"fixed={report.fixed_count} "
        f"skipped={report.skipped_count} "
        f"missing_source={report.missing_source_count}"
    )
    if report.missing_source_count:
        for p in report.missing_paths:
            print(f"  MISSING SOURCE: {p}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run tests to confirm pass**

```bash
pytest tests/maintenance/test_fix_reference_corpus_symlinks.py -v
```
Expected: 3 passed.

- [ ] **Step 6: Run the fixer against the real project**

```bash
python scripts/maintenance/fix_reference_corpus_symlinks.py
```
Expected output: `fixed=N skipped=0 missing_source=0` where N matches the chapter count (≈ 30 books × ~30 chapters).

Verify a sample by reading bytes:
```bash
head -c 80 benchmark/reference_corpus/诡秘之主/chapters/ch001.txt
```
Expected: real Chinese prose (not a "No such file" error).

- [ ] **Step 7: Commit**

```bash
git add scripts/maintenance/__init__.py scripts/maintenance/fix_reference_corpus_symlinks.py tests/maintenance/__init__.py tests/maintenance/test_fix_reference_corpus_symlinks.py benchmark/reference_corpus/
git commit -m "fix(M1-T1): repair reference_corpus broken absolute symlinks

Replace broken absolute-path symlinks (left over from project relocation)
with hard copies from benchmark/corpus/. Resolves CASE-2026-0000
motivation (silent corpus degradation). Tests cover broken-symlink fix,
already-real-file skip, and missing-source recording."
```

---

## Task 2: 测试基础设施（pytest.ini + requirements + 目录骨架）

**Files:**
- Modify: `pytest.ini` (testpaths)
- Modify: `requirements.txt` (qdrant-client)
- Create: `tests/case_library/__init__.py`
- Create: `tests/qdrant/__init__.py`
- Create: `tests/preflight/__init__.py`
- Create: `ink_writer/case_library/__init__.py`
- Create: `ink_writer/qdrant/__init__.py`
- Create: `ink_writer/preflight/__init__.py`

- [ ] **Step 1: Add testpaths**

Edit `pytest.ini`. Append `tests/case_library tests/qdrant tests/preflight tests/maintenance` to the `testpaths` line (keep order, separate with single space).

After edit, the relevant fragment must read (single line, do NOT line-wrap):
```
testpaths = tests/data_modules tests/migration tests/baseline tests/audit tests/hooks tests/pacing tests/emotion tests/style_rag tests/anti_detection tests/cultural tests/memory_arch tests/semantic_recall tests/foreshadow tests/voice_fingerprint tests/plotline tests/thread_lifecycle tests/skill_systems tests/prompts tests/parallel tests/prompt_cache tests/checker_pipeline tests/incremental_extract tests/benchmark tests/ink_init tests/harness tests/editor_wisdom tests/integration tests/docs tests/infra tests/creativity tests/quality_metrics tests/reflection tests/review tests/release tests/propagation tests/progression tests/core tests/scripts tests/skills tests/prose tests/case_library tests/qdrant tests/preflight tests/maintenance
```

- [ ] **Step 2: Add qdrant-client to requirements.txt**

Append a single line at the end of `requirements.txt`:
```
qdrant-client~=1.12            # Vector DB（M1 起替换 FAISS，详见 docs/superpowers/specs/2026-04-23-...md §8）
```

- [ ] **Step 3: Install the new dependency locally**

```bash
pip install "qdrant-client~=1.12"
```
Expected: install ok, version 1.12.x.

Verify:
```bash
python -c "import qdrant_client; print(qdrant_client.__version__)"
```
Expected: prints a version starting with `1.12.`.

- [ ] **Step 4: Create empty package skeletons**

```bash
mkdir -p ink_writer/case_library ink_writer/qdrant ink_writer/preflight
touch ink_writer/case_library/__init__.py ink_writer/qdrant/__init__.py ink_writer/preflight/__init__.py
mkdir -p tests/case_library tests/qdrant tests/preflight
touch tests/case_library/__init__.py tests/qdrant/__init__.py tests/preflight/__init__.py
```

- [ ] **Step 5: Smoke-run pytest to ensure nothing broke**

```bash
pytest -q --no-cov
```
Expected: existing test suite passes (or shows only pre-existing failures unrelated to M1). The new empty test dirs collect 0 tests but do not error.

- [ ] **Step 6: Commit**

```bash
git add pytest.ini requirements.txt ink_writer/case_library/__init__.py ink_writer/qdrant/__init__.py ink_writer/preflight/__init__.py tests/case_library/__init__.py tests/qdrant/__init__.py tests/preflight/__init__.py
git commit -m "chore(M1-T2): scaffold case_library/qdrant/preflight packages

- pytest.ini: register new test dirs.
- requirements.txt: add qdrant-client~=1.12.
- Create empty package and test skeletons."
```

---

## Task 3: Case Schema (JSON Schema) + 校验

**Files:**
- Create: `schemas/case_schema.json`
- Create: `ink_writer/case_library/schema.py`
- Create: `ink_writer/case_library/errors.py`
- Create: `tests/case_library/test_schema.py`
- Create: `tests/case_library/conftest.py`

- [ ] **Step 1: Write the failing test**

Create `tests/case_library/conftest.py`:

```python
"""Shared fixtures for case_library tests."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def sample_case_dict() -> dict:
    """A minimum-valid Case dict matching schemas/case_schema.json."""
    return {
        "case_id": "CASE-2026-0001",
        "title": "主角接到电话 3 秒就不慌，反应不真实",
        "status": "active",
        "severity": "P1",
        "domain": "writing_quality",
        "layer": ["downstream"],
        "tags": ["reader_immersion", "protagonist_reaction"],
        "scope": {
            "genre": ["all"],
            "chapter": ["all"],
        },
        "source": {
            "type": "editor_review",
            "raw_text": "主角接到电话3秒就不慌了",
            "ingested_at": "2026-04-23",
        },
        "failure_pattern": {
            "description": "突发事件→主角理性恢复之间缺情绪缓冲",
            "observable": [
                "突发事件后到理性反应之间字符数 < 200",
            ],
        },
        "bound_assets": {},
        "resolution": {},
        "evidence_links": [],
    }


@pytest.fixture
def tmp_case_dir(tmp_path: Path) -> Path:
    d = tmp_path / "case_library" / "cases"
    d.mkdir(parents=True)
    return d
```

Create `tests/case_library/test_schema.py`:

```python
from __future__ import annotations

import pytest

from ink_writer.case_library.errors import CaseValidationError
from ink_writer.case_library.schema import validate_case_dict


def test_minimum_valid_case_passes(sample_case_dict: dict) -> None:
    validate_case_dict(sample_case_dict)  # no raise


def test_missing_required_case_id_raises(sample_case_dict: dict) -> None:
    sample_case_dict.pop("case_id")
    with pytest.raises(CaseValidationError, match="case_id"):
        validate_case_dict(sample_case_dict)


def test_invalid_status_raises(sample_case_dict: dict) -> None:
    sample_case_dict["status"] = "not-a-status"
    with pytest.raises(CaseValidationError, match="status"):
        validate_case_dict(sample_case_dict)


def test_invalid_severity_raises(sample_case_dict: dict) -> None:
    sample_case_dict["severity"] = "P9"
    with pytest.raises(CaseValidationError, match="severity"):
        validate_case_dict(sample_case_dict)


def test_invalid_domain_raises(sample_case_dict: dict) -> None:
    sample_case_dict["domain"] = "marketing"
    with pytest.raises(CaseValidationError, match="domain"):
        validate_case_dict(sample_case_dict)


def test_layer_must_be_array(sample_case_dict: dict) -> None:
    sample_case_dict["layer"] = "downstream"
    with pytest.raises(CaseValidationError, match="layer"):
        validate_case_dict(sample_case_dict)


def test_case_id_pattern_enforced(sample_case_dict: dict) -> None:
    sample_case_dict["case_id"] = "case-2026-1"
    with pytest.raises(CaseValidationError, match="case_id"):
        validate_case_dict(sample_case_dict)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/case_library/test_schema.py -v --no-cov
```
Expected: `ModuleNotFoundError: No module named 'ink_writer.case_library.schema'`.

- [ ] **Step 3: Create the JSON Schema file**

Create `schemas/case_schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://ink-writer/case_schema",
  "title": "Case",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "case_id",
    "title",
    "status",
    "severity",
    "domain",
    "layer",
    "tags",
    "scope",
    "source",
    "failure_pattern"
  ],
  "properties": {
    "case_id": {
      "type": "string",
      "pattern": "^CASE-[0-9]{4}-[0-9]{4}$"
    },
    "title": {"type": "string", "minLength": 1, "maxLength": 200},
    "status": {
      "type": "string",
      "enum": ["pending", "active", "resolved", "regressed", "retired"]
    },
    "severity": {
      "type": "string",
      "enum": ["P0", "P1", "P2", "P3"]
    },
    "domain": {
      "type": "string",
      "enum": ["writing_quality", "infra_health"]
    },
    "layer": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "string",
        "enum": ["upstream", "downstream", "reference_gap", "infra_health"]
      }
    },
    "tags": {
      "type": "array",
      "items": {"type": "string"}
    },
    "scope": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "genre": {"type": "array", "items": {"type": "string"}},
        "chapter": {"type": "array", "items": {"type": "string"}},
        "trigger": {"type": "string"}
      }
    },
    "source": {
      "type": "object",
      "additionalProperties": false,
      "required": ["type", "raw_text", "ingested_at"],
      "properties": {
        "type": {
          "type": "string",
          "enum": ["editor_review", "self_audit", "regression", "infra_check"]
        },
        "reviewer": {"type": "string"},
        "raw_text": {"type": "string", "minLength": 1},
        "ingested_at": {"type": "string", "format": "date"},
        "ingested_from": {"type": "string"}
      }
    },
    "failure_pattern": {
      "type": "object",
      "additionalProperties": false,
      "required": ["description", "observable"],
      "properties": {
        "description": {"type": "string", "minLength": 1},
        "observable": {
          "type": "array",
          "minItems": 1,
          "items": {"type": "string"}
        }
      }
    },
    "bound_assets": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "rules": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["rule_id"],
            "properties": {
              "rule_id": {"type": "string"},
              "excerpt": {"type": "string"}
            }
          }
        },
        "corpus_chunks": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["chunk_id"],
            "properties": {
              "chunk_id": {"type": "string"},
              "reason": {"type": "string"}
            }
          }
        },
        "checkers": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["checker_id"],
            "properties": {
              "checker_id": {"type": "string"},
              "version": {"type": "string"},
              "created_for_this_case": {"type": "boolean"}
            }
          }
        }
      }
    },
    "resolution": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "introduced_at": {"type": "string", "format": "date"},
        "validation_chapters": {"type": "array", "items": {"type": "string"}},
        "regressed_at": {"type": ["string", "null"], "format": "date"},
        "related_cases": {"type": "array", "items": {"type": "string"}}
      }
    },
    "evidence_links": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["chapter", "case_status_in_chapter"],
        "properties": {
          "chapter": {"type": "string"},
          "evidence_chain": {"type": "string"},
          "case_status_in_chapter": {
            "type": "string",
            "enum": ["passed", "failed", "warned", "skipped"]
          }
        }
      }
    }
  }
}
```

- [ ] **Step 4: Implement errors and schema validator**

Create `ink_writer/case_library/errors.py`:

```python
"""Case library exceptions."""
from __future__ import annotations


class CaseLibraryError(Exception):
    """Base class for case library errors."""


class CaseValidationError(CaseLibraryError):
    """Raised when a case dict fails JSON Schema validation."""


class CaseNotFoundError(CaseLibraryError):
    """Raised when a case_id does not exist in the library."""


class DuplicateCaseError(CaseLibraryError):
    """Raised when ingesting raw_text whose hash matches an existing case."""
```

Create `ink_writer/case_library/schema.py`:

```python
"""Case JSON Schema loader and validator.

The schema lives in ``schemas/case_schema.json`` at the repo root. We load it
once on first use and cache it. Validation errors are raised as
:class:`CaseValidationError` with the JSON pointer of the offending field
included in the message so that CLI consumers can show useful diagnostics.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema
from jsonschema import Draft202012Validator

from ink_writer.case_library.errors import CaseValidationError


def _repo_root() -> Path:
    # ink_writer/case_library/schema.py → repo root is parent.parent.parent
    return Path(__file__).resolve().parent.parent.parent


@lru_cache(maxsize=1)
def _load_schema() -> dict[str, Any]:
    schema_path = _repo_root() / "schemas" / "case_schema.json"
    with open(schema_path, encoding="utf-8") as fp:
        return json.load(fp)


def validate_case_dict(case: dict[str, Any]) -> None:
    """Validate ``case`` against the Case JSON Schema.

    Raises:
        CaseValidationError: with an error message containing the JSON path of
            the first offending field.
    """
    schema = _load_schema()
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(case), key=lambda e: list(e.absolute_path))
    if not errors:
        return
    first = errors[0]
    pointer = "/" + "/".join(str(p) for p in first.absolute_path) if first.absolute_path else "/"
    raise CaseValidationError(f"{pointer}: {first.message}")
```

- [ ] **Step 5: Run tests to verify pass**

```bash
pytest tests/case_library/test_schema.py -v --no-cov
```
Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add schemas/case_schema.json ink_writer/case_library/schema.py ink_writer/case_library/errors.py tests/case_library/conftest.py tests/case_library/test_schema.py
git commit -m "feat(M1-T3): Case JSON Schema + validator

Schemas/case_schema.json captures the spec §3.2 schema (status/severity/
domain/layer enums + case_id pattern + required fields + bound_assets and
evidence_links structure). validate_case_dict raises CaseValidationError
with JSON pointer on the offending field."
```

---

## Task 4: Case Models (dataclass)

**Files:**
- Create: `ink_writer/case_library/models.py`
- Create: `tests/case_library/test_models.py`

- [ ] **Step 1: Write the failing test**

Create `tests/case_library/test_models.py`:

```python
from __future__ import annotations

from datetime import date

import pytest

from ink_writer.case_library.models import (
    Case,
    CaseStatus,
    CaseSeverity,
    CaseDomain,
    CaseLayer,
    SourceType,
)


def test_case_round_trip(sample_case_dict: dict) -> None:
    case = Case.from_dict(sample_case_dict)
    assert case.case_id == "CASE-2026-0001"
    assert case.status is CaseStatus.ACTIVE
    assert case.severity is CaseSeverity.P1
    assert case.domain is CaseDomain.WRITING_QUALITY
    assert CaseLayer.DOWNSTREAM in case.layer
    assert case.source.type is SourceType.EDITOR_REVIEW
    round_tripped = case.to_dict()
    # Optional fields preserved.
    assert round_tripped["tags"] == sample_case_dict["tags"]
    assert round_tripped["status"] == "active"


def test_case_unknown_status_rejected() -> None:
    with pytest.raises(ValueError):
        CaseStatus("unknown")


def test_case_to_dict_omits_empty_optional_blocks(sample_case_dict: dict) -> None:
    sample_case_dict["bound_assets"] = {}
    sample_case_dict["resolution"] = {}
    sample_case_dict["evidence_links"] = []
    case = Case.from_dict(sample_case_dict)
    out = case.to_dict()
    # Empty bound_assets/resolution/evidence_links are still preserved as the
    # canonical empty values, so re-validation works.
    assert out["bound_assets"] == {}
    assert out["resolution"] == {}
    assert out["evidence_links"] == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/case_library/test_models.py -v --no-cov
```
Expected: ImportError on `ink_writer.case_library.models`.

- [ ] **Step 3: Implement models**

Create `ink_writer/case_library/models.py`:

```python
"""Case dataclasses + enums.

The on-disk format is YAML; the in-memory format uses :class:`Case` (a
frozen dataclass over typed sub-records). Conversion helpers preserve all
fields needed by ``schemas/case_schema.json`` and survive YAML round-trip.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional


class CaseStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    RESOLVED = "resolved"
    REGRESSED = "regressed"
    RETIRED = "retired"


class CaseSeverity(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class CaseDomain(str, Enum):
    WRITING_QUALITY = "writing_quality"
    INFRA_HEALTH = "infra_health"


class CaseLayer(str, Enum):
    UPSTREAM = "upstream"
    DOWNSTREAM = "downstream"
    REFERENCE_GAP = "reference_gap"
    INFRA_HEALTH = "infra_health"


class SourceType(str, Enum):
    EDITOR_REVIEW = "editor_review"
    SELF_AUDIT = "self_audit"
    REGRESSION = "regression"
    INFRA_CHECK = "infra_check"


@dataclass
class Scope:
    genre: list[str] = field(default_factory=lambda: ["all"])
    chapter: list[str] = field(default_factory=lambda: ["all"])
    trigger: Optional[str] = None


@dataclass
class Source:
    type: SourceType
    raw_text: str
    ingested_at: str  # ISO date "YYYY-MM-DD"
    reviewer: Optional[str] = None
    ingested_from: Optional[str] = None


@dataclass
class FailurePattern:
    description: str
    observable: list[str]


@dataclass
class Case:
    case_id: str
    title: str
    status: CaseStatus
    severity: CaseSeverity
    domain: CaseDomain
    layer: list[CaseLayer]
    tags: list[str]
    scope: Scope
    source: Source
    failure_pattern: FailurePattern
    bound_assets: dict[str, Any] = field(default_factory=dict)
    resolution: dict[str, Any] = field(default_factory=dict)
    evidence_links: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Case":
        return cls(
            case_id=data["case_id"],
            title=data["title"],
            status=CaseStatus(data["status"]),
            severity=CaseSeverity(data["severity"]),
            domain=CaseDomain(data["domain"]),
            layer=[CaseLayer(item) for item in data["layer"]],
            tags=list(data.get("tags", [])),
            scope=Scope(**data.get("scope", {})),
            source=Source(
                type=SourceType(data["source"]["type"]),
                raw_text=data["source"]["raw_text"],
                ingested_at=data["source"]["ingested_at"],
                reviewer=data["source"].get("reviewer"),
                ingested_from=data["source"].get("ingested_from"),
            ),
            failure_pattern=FailurePattern(
                description=data["failure_pattern"]["description"],
                observable=list(data["failure_pattern"]["observable"]),
            ),
            bound_assets=dict(data.get("bound_assets", {})),
            resolution=dict(data.get("resolution", {})),
            evidence_links=list(data.get("evidence_links", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "case_id": self.case_id,
            "title": self.title,
            "status": self.status.value,
            "severity": self.severity.value,
            "domain": self.domain.value,
            "layer": [layer.value for layer in self.layer],
            "tags": list(self.tags),
            "scope": {
                "genre": list(self.scope.genre),
                "chapter": list(self.scope.chapter),
            },
            "source": {
                "type": self.source.type.value,
                "raw_text": self.source.raw_text,
                "ingested_at": self.source.ingested_at,
            },
            "failure_pattern": {
                "description": self.failure_pattern.description,
                "observable": list(self.failure_pattern.observable),
            },
            "bound_assets": dict(self.bound_assets),
            "resolution": dict(self.resolution),
            "evidence_links": list(self.evidence_links),
        }
        if self.scope.trigger is not None:
            out["scope"]["trigger"] = self.scope.trigger
        if self.source.reviewer is not None:
            out["source"]["reviewer"] = self.source.reviewer
        if self.source.ingested_from is not None:
            out["source"]["ingested_from"] = self.source.ingested_from
        return out
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/case_library/test_models.py -v --no-cov
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add ink_writer/case_library/models.py tests/case_library/test_models.py
git commit -m "feat(M1-T4): Case dataclass + enums

Case + Scope + Source + FailurePattern dataclasses with from_dict /
to_dict helpers. Enums for Status/Severity/Domain/Layer/SourceType match
schemas/case_schema.json."
```

---

## Task 5: Case Store (YAML CRUD + jsonl 打包 + ingest_log)

**Files:**
- Create: `ink_writer/case_library/store.py`
- Create: `tests/case_library/test_store.py`

- [ ] **Step 1: Write the failing test**

Create `tests/case_library/test_store.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ink_writer.case_library.errors import CaseNotFoundError, CaseValidationError
from ink_writer.case_library.models import Case
from ink_writer.case_library.store import CaseStore


def test_save_then_load(tmp_case_dir: Path, sample_case_dict: dict) -> None:
    store = CaseStore(tmp_case_dir.parent)
    case = Case.from_dict(sample_case_dict)
    store.save(case)
    loaded = store.load("CASE-2026-0001")
    assert loaded.case_id == "CASE-2026-0001"
    assert loaded.title == sample_case_dict["title"]


def test_save_writes_yaml_with_utf8(tmp_case_dir: Path, sample_case_dict: dict) -> None:
    store = CaseStore(tmp_case_dir.parent)
    case = Case.from_dict(sample_case_dict)
    store.save(case)
    path = tmp_case_dir / "CASE-2026-0001.yaml"
    text = path.read_text(encoding="utf-8")
    # Chinese characters survive (YAML default: utf-8 with allow_unicode).
    assert "主角接到电话" in text
    parsed = yaml.safe_load(text)
    assert parsed["case_id"] == "CASE-2026-0001"


def test_load_missing_raises(tmp_case_dir: Path) -> None:
    store = CaseStore(tmp_case_dir.parent)
    with pytest.raises(CaseNotFoundError):
        store.load("CASE-2026-9999")


def test_save_invalid_case_raises(tmp_case_dir: Path, sample_case_dict: dict) -> None:
    store = CaseStore(tmp_case_dir.parent)
    case = Case.from_dict(sample_case_dict)
    case.case_id = "bad-id"  # Violates pattern
    with pytest.raises(CaseValidationError):
        store.save(case)


def test_list_returns_all_case_ids(tmp_case_dir: Path, sample_case_dict: dict) -> None:
    store = CaseStore(tmp_case_dir.parent)
    store.save(Case.from_dict(sample_case_dict))
    second = dict(sample_case_dict)
    second["case_id"] = "CASE-2026-0002"
    second["title"] = "第二个病例"
    store.save(Case.from_dict(second))
    ids = store.list_ids()
    assert sorted(ids) == ["CASE-2026-0001", "CASE-2026-0002"]


def test_pack_jsonl_emits_one_line_per_case(tmp_case_dir: Path, sample_case_dict: dict) -> None:
    store = CaseStore(tmp_case_dir.parent)
    store.save(Case.from_dict(sample_case_dict))
    second = dict(sample_case_dict)
    second["case_id"] = "CASE-2026-0002"
    store.save(Case.from_dict(second))
    out = tmp_case_dir.parent / "cases.jsonl"
    store.pack_jsonl(out)
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


def test_append_ingest_log(tmp_case_dir: Path) -> None:
    store = CaseStore(tmp_case_dir.parent)
    store.append_ingest_log({
        "event": "ingest",
        "case_id": "CASE-2026-0001",
        "raw_text_hash": "abc123",
        "at": "2026-04-23T10:00:00Z",
    })
    log = (tmp_case_dir.parent / "ingest_log.jsonl").read_text(encoding="utf-8")
    assert '"abc123"' in log
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/case_library/test_store.py -v --no-cov
```
Expected: ImportError on `ink_writer.case_library.store`.

- [ ] **Step 3: Implement the store**

Create `ink_writer/case_library/store.py`:

```python
"""YAML case store: file-per-case + ingest log + jsonl packer.

Layout (rooted at ``library_root``)::

    library_root/
        cases/
            CASE-YYYY-NNNN.yaml
        cases.jsonl       (optional, produced by pack_jsonl())
        ingest_log.jsonl  (append-only audit log)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from ink_writer.case_library.errors import CaseNotFoundError
from ink_writer.case_library.models import Case
from ink_writer.case_library.schema import validate_case_dict


class CaseStore:
    """File-per-case YAML store rooted at ``library_root``."""

    def __init__(self, library_root: Path) -> None:
        self.library_root = Path(library_root)
        self.cases_dir = self.library_root / "cases"
        self.cases_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, case_id: str) -> Path:
        return self.cases_dir / f"{case_id}.yaml"

    def save(self, case: Case) -> Path:
        data = case.to_dict()
        validate_case_dict(data)  # Re-validate before write.
        path = self._path_for(case.case_id)
        with open(path, "w", encoding="utf-8") as fp:
            yaml.safe_dump(
                data,
                fp,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
            )
        return path

    def load(self, case_id: str) -> Case:
        path = self._path_for(case_id)
        if not path.is_file():
            raise CaseNotFoundError(case_id)
        with open(path, encoding="utf-8") as fp:
            data = yaml.safe_load(fp)
        validate_case_dict(data)
        return Case.from_dict(data)

    def list_ids(self) -> list[str]:
        return [p.stem for p in self.cases_dir.glob("CASE-*.yaml")]

    def iter_cases(self):
        for case_id in sorted(self.list_ids()):
            yield self.load(case_id)

    def pack_jsonl(self, out_path: Path) -> int:
        count = 0
        with open(out_path, "w", encoding="utf-8") as fp:
            for case in self.iter_cases():
                fp.write(json.dumps(case.to_dict(), ensure_ascii=False))
                fp.write("\n")
                count += 1
        return count

    def append_ingest_log(self, event: dict[str, Any]) -> None:
        path = self.library_root / "ingest_log.jsonl"
        with open(path, "a", encoding="utf-8") as fp:
            fp.write(json.dumps(event, ensure_ascii=False))
            fp.write("\n")
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/case_library/test_store.py -v --no-cov
```
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add ink_writer/case_library/store.py tests/case_library/test_store.py
git commit -m "feat(M1-T5): CaseStore YAML CRUD + jsonl packer + ingest log

CaseStore writes one yaml per case (allow_unicode, sort_keys=False),
re-validates against the JSON Schema on save and load, supports list_ids,
iter_cases, pack_jsonl (full export), and append_ingest_log (audit
trail)."
```

---

## Task 6: Case Index (sqlite 倒排查询)

**Files:**
- Create: `ink_writer/case_library/index.py`
- Create: `tests/case_library/test_index.py`

- [ ] **Step 1: Write the failing test**

Create `tests/case_library/test_index.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from ink_writer.case_library.index import CaseIndex
from ink_writer.case_library.models import Case
from ink_writer.case_library.store import CaseStore


@pytest.fixture
def populated_store(tmp_case_dir: Path, sample_case_dict: dict) -> CaseStore:
    store = CaseStore(tmp_case_dir.parent)
    store.save(Case.from_dict(sample_case_dict))
    second = dict(sample_case_dict)
    second["case_id"] = "CASE-2026-0002"
    second["status"] = "pending"
    second["severity"] = "P0"
    second["layer"] = ["upstream"]
    second["tags"] = ["plot_pacing", "golden_finger"]
    second["scope"] = {"genre": ["xuanhuan"], "chapter": ["opening_only"]}
    store.save(Case.from_dict(second))
    return store


def test_build_index_creates_sqlite(populated_store: CaseStore) -> None:
    index = CaseIndex(populated_store.library_root / "index.sqlite")
    index.build(populated_store)
    assert (populated_store.library_root / "index.sqlite").is_file()


def test_query_by_tag(populated_store: CaseStore) -> None:
    index = CaseIndex(populated_store.library_root / "index.sqlite")
    index.build(populated_store)
    assert index.query_by_tag("reader_immersion") == ["CASE-2026-0001"]
    assert index.query_by_tag("golden_finger") == ["CASE-2026-0002"]


def test_query_by_layer(populated_store: CaseStore) -> None:
    index = CaseIndex(populated_store.library_root / "index.sqlite")
    index.build(populated_store)
    assert index.query_by_layer("downstream") == ["CASE-2026-0001"]
    assert index.query_by_layer("upstream") == ["CASE-2026-0002"]


def test_query_by_genre(populated_store: CaseStore) -> None:
    index = CaseIndex(populated_store.library_root / "index.sqlite")
    index.build(populated_store)
    assert index.query_by_genre("xuanhuan") == ["CASE-2026-0002"]
    assert index.query_by_genre("all") == ["CASE-2026-0001"]


def test_query_by_status(populated_store: CaseStore) -> None:
    index = CaseIndex(populated_store.library_root / "index.sqlite")
    index.build(populated_store)
    assert index.query_by_status("active") == ["CASE-2026-0001"]
    assert index.query_by_status("pending") == ["CASE-2026-0002"]


def test_rebuild_is_idempotent(populated_store: CaseStore) -> None:
    index = CaseIndex(populated_store.library_root / "index.sqlite")
    index.build(populated_store)
    index.build(populated_store)
    assert index.query_by_tag("reader_immersion") == ["CASE-2026-0001"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/case_library/test_index.py -v --no-cov
```
Expected: ImportError on `ink_writer.case_library.index`.

- [ ] **Step 3: Implement the index**

Create `ink_writer/case_library/index.py`:

```python
"""sqlite inverted index over a CaseStore.

Tables (no FK to keep schema portable; rebuilt on demand):

    cases(case_id PRIMARY KEY, title, status, severity, domain)
    case_tags(case_id, tag)
    case_layers(case_id, layer)
    case_genres(case_id, genre)
    case_chapters(case_id, chapter)

Build is destructive (DROP + CREATE); call ``build()`` after any save.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from ink_writer.case_library.store import CaseStore


_SCHEMA = """
DROP TABLE IF EXISTS cases;
DROP TABLE IF EXISTS case_tags;
DROP TABLE IF EXISTS case_layers;
DROP TABLE IF EXISTS case_genres;
DROP TABLE IF EXISTS case_chapters;

CREATE TABLE cases (
    case_id TEXT PRIMARY KEY,
    title   TEXT NOT NULL,
    status  TEXT NOT NULL,
    severity TEXT NOT NULL,
    domain  TEXT NOT NULL
);

CREATE TABLE case_tags (
    case_id TEXT NOT NULL,
    tag     TEXT NOT NULL
);
CREATE INDEX idx_case_tags_tag ON case_tags(tag);

CREATE TABLE case_layers (
    case_id TEXT NOT NULL,
    layer   TEXT NOT NULL
);
CREATE INDEX idx_case_layers_layer ON case_layers(layer);

CREATE TABLE case_genres (
    case_id TEXT NOT NULL,
    genre   TEXT NOT NULL
);
CREATE INDEX idx_case_genres_genre ON case_genres(genre);

CREATE TABLE case_chapters (
    case_id TEXT NOT NULL,
    chapter TEXT NOT NULL
);
CREATE INDEX idx_case_chapters_chapter ON case_chapters(chapter);
"""


class CaseIndex:
    def __init__(self, sqlite_path: Path) -> None:
        self.sqlite_path = Path(sqlite_path)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.sqlite_path)

    def build(self, store: CaseStore) -> int:
        count = 0
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            for case in store.iter_cases():
                conn.execute(
                    "INSERT INTO cases(case_id,title,status,severity,domain) VALUES (?,?,?,?,?)",
                    (case.case_id, case.title, case.status.value, case.severity.value, case.domain.value),
                )
                conn.executemany(
                    "INSERT INTO case_tags(case_id,tag) VALUES (?,?)",
                    [(case.case_id, tag) for tag in case.tags],
                )
                conn.executemany(
                    "INSERT INTO case_layers(case_id,layer) VALUES (?,?)",
                    [(case.case_id, layer.value) for layer in case.layer],
                )
                conn.executemany(
                    "INSERT INTO case_genres(case_id,genre) VALUES (?,?)",
                    [(case.case_id, g) for g in case.scope.genre],
                )
                conn.executemany(
                    "INSERT INTO case_chapters(case_id,chapter) VALUES (?,?)",
                    [(case.case_id, ch) for ch in case.scope.chapter],
                )
                count += 1
            conn.commit()
        return count

    def _query_one_column(self, table: str, column: str, value: str) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT DISTINCT case_id FROM {table} WHERE {column}=? ORDER BY case_id",
                (value,),
            ).fetchall()
        return [r[0] for r in rows]

    def query_by_tag(self, tag: str) -> list[str]:
        return self._query_one_column("case_tags", "tag", tag)

    def query_by_layer(self, layer: str) -> list[str]:
        return self._query_one_column("case_layers", "layer", layer)

    def query_by_genre(self, genre: str) -> list[str]:
        return self._query_one_column("case_genres", "genre", genre)

    def query_by_chapter(self, chapter: str) -> list[str]:
        return self._query_one_column("case_chapters", "chapter", chapter)

    def query_by_status(self, status: str) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT case_id FROM cases WHERE status=? ORDER BY case_id",
                (status,),
            ).fetchall()
        return [r[0] for r in rows]
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/case_library/test_index.py -v --no-cov
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add ink_writer/case_library/index.py tests/case_library/test_index.py
git commit -m "feat(M1-T6): CaseIndex sqlite inverted index

Inverted indices over tag/layer/genre/chapter/status. build() is
destructive (DROP+CREATE) so it stays idempotent and authoritative-data
remains the YAML files."
```

---

## Task 7: Case Ingest（幂等 hash 去重）

**Files:**
- Create: `ink_writer/case_library/ingest.py`
- Create: `tests/case_library/test_ingest.py`

- [ ] **Step 1: Write the failing test**

Create `tests/case_library/test_ingest.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from ink_writer.case_library.errors import DuplicateCaseError
from ink_writer.case_library.ingest import IngestResult, ingest_case
from ink_writer.case_library.store import CaseStore


def test_ingest_creates_case(tmp_case_dir: Path) -> None:
    store = CaseStore(tmp_case_dir.parent)
    result = ingest_case(
        store,
        title="主角当摄像头",
        raw_text="主角全程在看别人打架，毫无参与感。",
        domain="writing_quality",
        layer=["downstream"],
        severity="P1",
        tags=["protagonist_passive"],
        source_type="editor_review",
        ingested_at="2026-04-23",
        failure_description="主角无主动行为",
        observable=["主角主动决策点数=0"],
    )
    assert isinstance(result, IngestResult)
    assert result.created is True
    assert result.case_id.startswith("CASE-2026-")
    assert store.load(result.case_id).title == "主角当摄像头"


def test_ingest_same_text_is_deduplicated(tmp_case_dir: Path) -> None:
    store = CaseStore(tmp_case_dir.parent)
    kwargs = dict(
        store=store,
        title="主角当摄像头",
        raw_text="主角全程在看别人打架，毫无参与感。",
        domain="writing_quality",
        layer=["downstream"],
        severity="P1",
        tags=["protagonist_passive"],
        source_type="editor_review",
        ingested_at="2026-04-23",
        failure_description="主角无主动行为",
        observable=["主角主动决策点数=0"],
    )
    first = ingest_case(**kwargs)
    second = ingest_case(**kwargs)
    assert first.created is True
    assert second.created is False
    assert second.case_id == first.case_id


def test_ingest_appends_ingest_log(tmp_case_dir: Path) -> None:
    store = CaseStore(tmp_case_dir.parent)
    ingest_case(
        store,
        title="t",
        raw_text="some unique text",
        domain="writing_quality",
        layer=["downstream"],
        severity="P2",
        tags=["x"],
        source_type="editor_review",
        ingested_at="2026-04-23",
        failure_description="d",
        observable=["o1"],
    )
    log = (tmp_case_dir.parent / "ingest_log.jsonl").read_text(encoding="utf-8")
    assert "ingest" in log
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/case_library/test_ingest.py -v --no-cov
```
Expected: ImportError.

- [ ] **Step 3: Implement ingest**

Create `ink_writer/case_library/ingest.py`:

```python
"""Idempotent case ingestion.

Dedup key: SHA-256 of raw_text. The first call creates a new case (allocating
the next available case_id of form ``CASE-YYYY-NNNN``). Subsequent calls with
the same raw_text return the existing case_id without modification.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ink_writer.case_library.models import (
    Case,
    CaseDomain,
    CaseLayer,
    CaseSeverity,
    CaseStatus,
    FailurePattern,
    Scope,
    Source,
    SourceType,
)
from ink_writer.case_library.store import CaseStore


@dataclass
class IngestResult:
    case_id: str
    created: bool
    raw_text_hash: str


def _hash_raw_text(raw_text: str) -> str:
    return hashlib.sha256(raw_text.encode("utf-8")).hexdigest()


def _find_existing_by_hash(store: CaseStore, raw_text_hash: str) -> str | None:
    for case in store.iter_cases():
        existing_hash = _hash_raw_text(case.source.raw_text)
        if existing_hash == raw_text_hash:
            return case.case_id
    return None


def _allocate_case_id(store: CaseStore, year: int) -> str:
    prefix = f"CASE-{year:04d}-"
    used = sorted(
        int(cid[len(prefix):]) for cid in store.list_ids() if cid.startswith(prefix)
    )
    next_n = (used[-1] + 1) if used else 1
    return f"{prefix}{next_n:04d}"


def ingest_case(
    store: CaseStore,
    *,
    title: str,
    raw_text: str,
    domain: str,
    layer: list[str],
    severity: str,
    tags: list[str],
    source_type: str,
    ingested_at: str,
    failure_description: str,
    observable: list[str],
    reviewer: str | None = None,
    ingested_from: str | None = None,
    scope_genre: list[str] | None = None,
    scope_chapter: list[str] | None = None,
    initial_status: str = "active",
) -> IngestResult:
    raw_hash = _hash_raw_text(raw_text)
    existing = _find_existing_by_hash(store, raw_hash)
    if existing is not None:
        return IngestResult(case_id=existing, created=False, raw_text_hash=raw_hash)

    year = int(ingested_at.split("-")[0])
    case_id = _allocate_case_id(store, year)
    case = Case(
        case_id=case_id,
        title=title,
        status=CaseStatus(initial_status),
        severity=CaseSeverity(severity),
        domain=CaseDomain(domain),
        layer=[CaseLayer(item) for item in layer],
        tags=list(tags),
        scope=Scope(
            genre=list(scope_genre or ["all"]),
            chapter=list(scope_chapter or ["all"]),
        ),
        source=Source(
            type=SourceType(source_type),
            raw_text=raw_text,
            ingested_at=ingested_at,
            reviewer=reviewer,
            ingested_from=ingested_from,
        ),
        failure_pattern=FailurePattern(
            description=failure_description,
            observable=list(observable),
        ),
    )
    store.save(case)
    store.append_ingest_log({
        "event": "ingest",
        "case_id": case_id,
        "raw_text_hash": raw_hash,
        "at": datetime.now(timezone.utc).isoformat(),
    })
    return IngestResult(case_id=case_id, created=True, raw_text_hash=raw_hash)
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/case_library/test_ingest.py -v --no-cov
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add ink_writer/case_library/ingest.py tests/case_library/test_ingest.py
git commit -m "feat(M1-T7): idempotent case ingestion with sha256 dedup

ingest_case() allocates next CASE-YYYY-NNNN id, dedupes by raw_text
SHA-256 (returns existing id with created=False on hit), persists via
CaseStore, and appends a structured event to ingest_log.jsonl."
```

---

## Task 8: Case CLI (`ink case`)

**Files:**
- Create: `ink_writer/case_library/cli.py`
- Create: `tests/case_library/test_cli.py`

- [ ] **Step 1: Write the failing test**

Create `tests/case_library/test_cli.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from ink_writer.case_library.cli import main


def _run(args: list[str], capsys) -> str:
    rc = main(args)
    out = capsys.readouterr().out
    assert rc == 0, f"non-zero exit {rc}; stdout={out}"
    return out


def test_cli_create_then_list_then_show(tmp_path: Path, capsys) -> None:
    library_root = tmp_path / "case_library"
    common = ["--library-root", str(library_root)]

    out = _run(common + [
        "create",
        "--title", "测试病例",
        "--raw-text", "编辑说写得不像人话",
        "--domain", "writing_quality",
        "--layer", "downstream",
        "--severity", "P2",
        "--tags", "ai_smell",
        "--source-type", "editor_review",
        "--ingested-at", "2026-04-23",
        "--failure-description", "句式机械",
        "--observable", "破折号 / 章计数 > 5",
    ], capsys)
    assert "CASE-2026-0001" in out

    out = _run(common + ["list"], capsys)
    assert "CASE-2026-0001" in out

    out = _run(common + ["show", "CASE-2026-0001"], capsys)
    assert "测试病例" in out


def test_cli_status_filters_by_status(tmp_path: Path, capsys) -> None:
    library_root = tmp_path / "case_library"
    common = ["--library-root", str(library_root)]
    _run(common + [
        "create", "--title", "x", "--raw-text", "a",
        "--domain", "writing_quality", "--layer", "downstream",
        "--severity", "P2", "--tags", "t",
        "--source-type", "editor_review", "--ingested-at", "2026-04-23",
        "--failure-description", "d", "--observable", "o",
    ], capsys)
    out = _run(common + ["status", "active"], capsys)
    assert "CASE-2026-0001" in out
    out = _run(common + ["status", "resolved"], capsys)
    assert "CASE-2026-0001" not in out


def test_cli_rebuild_index_creates_sqlite(tmp_path: Path, capsys) -> None:
    library_root = tmp_path / "case_library"
    common = ["--library-root", str(library_root)]
    _run(common + [
        "create", "--title", "x", "--raw-text", "a",
        "--domain", "writing_quality", "--layer", "downstream",
        "--severity", "P2", "--tags", "t",
        "--source-type", "editor_review", "--ingested-at", "2026-04-23",
        "--failure-description", "d", "--observable", "o",
    ], capsys)
    _run(common + ["rebuild-index"], capsys)
    assert (library_root / "index.sqlite").is_file()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/case_library/test_cli.py -v --no-cov
```
Expected: ImportError.

- [ ] **Step 3: Implement CLI**

Create `ink_writer/case_library/cli.py`:

```python
"""`ink case` CLI: list / show / create / status / rebuild-index.

Single dispatcher kept inside the package so it can be wired into a future
top-level `ink` command. ``main(argv)`` returns 0 on success, non-zero on
error; never raises (tests rely on this contract).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ink_writer.case_library.errors import CaseNotFoundError, CaseValidationError
from ink_writer.case_library.index import CaseIndex
from ink_writer.case_library.ingest import ingest_case
from ink_writer.case_library.store import CaseStore


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ink case", description="Case library CLI")
    parser.add_argument(
        "--library-root",
        type=Path,
        default=Path("data/case_library"),
        help="Root directory for the case library (default: data/case_library)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="List all case ids")

    show = sub.add_parser("show", help="Show a single case as YAML")
    show.add_argument("case_id")

    status = sub.add_parser("status", help="Filter cases by status")
    status.add_argument("status", choices=["pending", "active", "resolved", "regressed", "retired"])

    create = sub.add_parser("create", help="Create a new case")
    create.add_argument("--title", required=True)
    create.add_argument("--raw-text", required=True)
    create.add_argument("--domain", required=True, choices=["writing_quality", "infra_health"])
    create.add_argument("--layer", required=True, action="append")
    create.add_argument("--severity", required=True, choices=["P0", "P1", "P2", "P3"])
    create.add_argument("--tags", required=True, action="append")
    create.add_argument("--source-type", required=True,
                        choices=["editor_review", "self_audit", "regression", "infra_check"])
    create.add_argument("--ingested-at", required=True)
    create.add_argument("--failure-description", required=True)
    create.add_argument("--observable", required=True, action="append")
    create.add_argument("--reviewer", default=None)
    create.add_argument("--ingested-from", default=None)
    create.add_argument("--scope-genre", action="append")
    create.add_argument("--scope-chapter", action="append")
    create.add_argument("--initial-status", default="active",
                        choices=["pending", "active"])

    sub.add_parser("rebuild-index", help="Rebuild the sqlite inverted index")
    return parser


def _cmd_list(store: CaseStore) -> int:
    for case_id in sorted(store.list_ids()):
        print(case_id)
    return 0


def _cmd_show(store: CaseStore, case_id: str) -> int:
    try:
        case = store.load(case_id)
    except CaseNotFoundError:
        print(f"ERROR: case not found: {case_id}", file=sys.stderr)
        return 2
    import yaml
    print(yaml.safe_dump(case.to_dict(), allow_unicode=True, sort_keys=False))
    return 0


def _cmd_status(store: CaseStore, status: str) -> int:
    for case in sorted(store.iter_cases(), key=lambda c: c.case_id):
        if case.status.value == status:
            print(case.case_id)
    return 0


def _cmd_create(store: CaseStore, args: argparse.Namespace) -> int:
    try:
        result = ingest_case(
            store,
            title=args.title,
            raw_text=args.raw_text,
            domain=args.domain,
            layer=args.layer,
            severity=args.severity,
            tags=args.tags,
            source_type=args.source_type,
            ingested_at=args.ingested_at,
            failure_description=args.failure_description,
            observable=args.observable,
            reviewer=args.reviewer,
            ingested_from=args.ingested_from,
            scope_genre=args.scope_genre,
            scope_chapter=args.scope_chapter,
            initial_status=args.initial_status,
        )
    except CaseValidationError as err:
        print(f"ERROR: validation failed: {err}", file=sys.stderr)
        return 3
    if result.created:
        print(result.case_id)
    else:
        print(f"{result.case_id} (already existed; raw_text dedup)")
    return 0


def _cmd_rebuild_index(store: CaseStore) -> int:
    index = CaseIndex(store.library_root / "index.sqlite")
    n = index.build(store)
    print(f"indexed={n}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    store = CaseStore(args.library_root)
    if args.cmd == "list":
        return _cmd_list(store)
    if args.cmd == "show":
        return _cmd_show(store, args.case_id)
    if args.cmd == "status":
        return _cmd_status(store, args.status)
    if args.cmd == "create":
        return _cmd_create(store, args)
    if args.cmd == "rebuild-index":
        return _cmd_rebuild_index(store)
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/case_library/test_cli.py -v --no-cov
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add ink_writer/case_library/cli.py tests/case_library/test_cli.py
git commit -m "feat(M1-T8): ink case CLI (list/show/create/status/rebuild-index)

main(argv) returns int (never raises) so it is composable. Each
subcommand maps 1:1 to a Store/Index method. --library-root is
configurable so tests run in tmp_path."
```

---

## Task 9: CASE-2026-0000 零号病例（infra_health）

**Files:**
- Create: `scripts/case_library/__init__.py`
- Create: `scripts/case_library/init_zero_case.py`
- Create: `tests/case_library/test_zero_case.py`

- [ ] **Step 1: Write the failing test**

Create `tests/case_library/test_zero_case.py`:

```python
from __future__ import annotations

from pathlib import Path

from scripts.case_library.init_zero_case import init_zero_case
from ink_writer.case_library.models import CaseDomain, CaseLayer, CaseStatus
from ink_writer.case_library.store import CaseStore


def test_zero_case_is_infra_health_active(tmp_path: Path) -> None:
    library_root = tmp_path / "case_library"
    init_zero_case(library_root)
    store = CaseStore(library_root)
    case = store.load("CASE-2026-0000")
    assert case.case_id == "CASE-2026-0000"
    assert case.domain is CaseDomain.INFRA_HEALTH
    assert CaseLayer.INFRA_HEALTH in case.layer
    assert case.status is CaseStatus.ACTIVE
    assert case.severity.value == "P0"


def test_zero_case_init_is_idempotent(tmp_path: Path) -> None:
    library_root = tmp_path / "case_library"
    init_zero_case(library_root)
    init_zero_case(library_root)  # second call no-op
    ids = CaseStore(library_root).list_ids()
    assert ids.count("CASE-2026-0000") == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/case_library/test_zero_case.py -v --no-cov
```
Expected: ImportError.

- [ ] **Step 3: Implement init_zero_case**

```bash
mkdir -p scripts/case_library && touch scripts/case_library/__init__.py
```

Create `scripts/case_library/init_zero_case.py`:

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Create CASE-2026-0000 (the infra_health zero-case).

Documents the reference_corpus broken-symlink incident that motivated the
preflight health checker. Idempotent: re-running is a no-op.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ink_writer.case_library.errors import CaseNotFoundError
from ink_writer.case_library.models import (
    Case,
    CaseDomain,
    CaseLayer,
    CaseSeverity,
    CaseStatus,
    FailurePattern,
    Scope,
    Source,
    SourceType,
)
from ink_writer.case_library.store import CaseStore


_ZERO_CASE_ID = "CASE-2026-0000"


def init_zero_case(library_root: Path) -> bool:
    """Create the zero-case if missing.

    Returns:
        True if created, False if already existed.
    """
    store = CaseStore(library_root)
    try:
        store.load(_ZERO_CASE_ID)
        return False
    except CaseNotFoundError:
        pass

    case = Case(
        case_id=_ZERO_CASE_ID,
        title="reference_corpus 软链接全部失效（项目搬迁后）",
        status=CaseStatus.ACTIVE,
        severity=CaseSeverity.P0,
        domain=CaseDomain.INFRA_HEALTH,
        layer=[CaseLayer.INFRA_HEALTH],
        tags=["reference_corpus", "symlink", "silent_degradation"],
        scope=Scope(genre=["all"], chapter=["all"]),
        source=Source(
            type=SourceType.INFRA_CHECK,
            raw_text=(
                "Project moved from /Users/cipher/AI/ink to /Users/cipher/AI/小说/ink; "
                "absolute-path symlinks under benchmark/reference_corpus/*/chapters/*.txt "
                "all broke and writer agents silently saw an empty corpus."
            ),
            ingested_at="2026-04-23",
            reviewer="self",
            ingested_from="benchmark/reference_corpus/",
        ),
        failure_pattern=FailurePattern(
            description=(
                "Corpus chapter files are unreadable (broken symlinks) yet no "
                "preflight check raises an alert; downstream retrieval silently "
                "returns 0 chunks."
            ),
            observable=[
                "broken symlink count under reference_corpus/*/chapters > 0",
                "corpus_root readable file count < min_files threshold",
            ],
        ),
        bound_assets={
            "checkers": [
                {
                    "checker_id": "preflight-reference-corpus-readable",
                    "version": "v1",
                    "created_for_this_case": True,
                }
            ]
        },
    )
    store.save(case)
    store.append_ingest_log({
        "event": "init_zero_case",
        "case_id": _ZERO_CASE_ID,
        "at": "2026-04-23T00:00:00Z",
    })
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--library-root",
        type=Path,
        default=Path("data/case_library"),
    )
    args = parser.parse_args(argv)
    created = init_zero_case(args.library_root)
    print("created" if created else "already_exists")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/case_library/test_zero_case.py -v --no-cov
```
Expected: 2 passed.

- [ ] **Step 5: Generate the real zero-case**

```bash
python scripts/case_library/init_zero_case.py
ls data/case_library/cases/
```
Expected: prints `created`; `CASE-2026-0000.yaml` exists.

- [ ] **Step 6: Commit**

```bash
git add scripts/case_library/__init__.py scripts/case_library/init_zero_case.py tests/case_library/test_zero_case.py data/case_library/cases/CASE-2026-0000.yaml
git commit -m "feat(M1-T9): seed CASE-2026-0000 (infra_health zero-case)

Documents the reference_corpus broken-symlink incident that triggered the
case-driven approach. Idempotent init script + test."
```

---

## Task 10: Qdrant Docker 部署 + 启动脚本

**Files:**
- Create: `scripts/qdrant/docker-compose.yml`
- Create: `scripts/qdrant/start.sh`
- Create: `scripts/qdrant/stop.sh`
- Create: `scripts/qdrant/start.ps1`
- Create: `scripts/qdrant/stop.ps1`
- Create: `scripts/qdrant/README.md`

**Note:** This task does not require pytest — it is infrastructure. Verification is by `curl` against the running service.

- [ ] **Step 1: Write docker-compose.yml**

Create `scripts/qdrant/docker-compose.yml`:

```yaml
version: "3.8"

services:
  qdrant:
    image: qdrant/qdrant:v1.12.4
    container_name: ink-writer-qdrant
    restart: unless-stopped
    ports:
      - "6333:6333"  # REST + dashboard
      - "6334:6334"  # gRPC
    volumes:
      - ./storage:/qdrant/storage
    environment:
      QDRANT__LOG_LEVEL: INFO
```

- [ ] **Step 2: Write start.sh (macOS/Linux)**

Create `scripts/qdrant/start.sh`:

```bash
#!/usr/bin/env bash
# Start the Qdrant service via docker compose.
set -euo pipefail

cd "$(dirname "$0")"
docker compose up -d
echo "Waiting for Qdrant to become ready..."
for i in {1..30}; do
  if curl -sf http://127.0.0.1:6333/readyz >/dev/null; then
    echo "Qdrant is ready."
    exit 0
  fi
  sleep 1
done
echo "Qdrant did not become ready within 30s." >&2
exit 1
```

```bash
chmod +x scripts/qdrant/start.sh
```

- [ ] **Step 3: Write stop.sh**

Create `scripts/qdrant/stop.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
docker compose down
```

```bash
chmod +x scripts/qdrant/stop.sh
```

- [ ] **Step 4: Write start.ps1 (Windows; UTF-8 BOM required)**

Create `scripts/qdrant/start.ps1`. **Save the file with UTF-8 BOM** (PS 5.1 requires BOM to read non-ASCII correctly; see CLAUDE.md Windows compat section). Content:

```powershell
# Start the Qdrant service via docker compose.
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
docker compose up -d
Write-Host "Waiting for Qdrant to become ready..."
for ($i=0; $i -lt 30; $i++) {
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:6333/readyz" -TimeoutSec 2
        if ($r.StatusCode -eq 200) {
            Write-Host "Qdrant is ready."
            exit 0
        }
    } catch {
        Start-Sleep -Seconds 1
    }
}
Write-Error "Qdrant did not become ready within 30s."
exit 1
```

- [ ] **Step 5: Write stop.ps1**

Create `scripts/qdrant/stop.ps1` (UTF-8 BOM):

```powershell
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
docker compose down
```

- [ ] **Step 6: Write README**

Create `scripts/qdrant/README.md`:

```markdown
# Qdrant Service for ink-writer

Single-node Qdrant via docker compose. M1 onwards replaces FAISS for
vector storage. Persists to `./storage/`.

## Start

macOS / Linux:
```bash
scripts/qdrant/start.sh
```

Windows (PowerShell 5.1+):
```powershell
scripts\qdrant\start.ps1
```

## Stop

```bash
scripts/qdrant/stop.sh
```
```powershell
scripts\qdrant\stop.ps1
```

## Endpoints

- REST + dashboard: http://127.0.0.1:6333
- gRPC: 127.0.0.1:6334

## Storage

`scripts/qdrant/storage/` is mounted into the container. **Do not commit**;
add to `.gitignore`.
```

- [ ] **Step 7: Add storage to .gitignore**

Append to `.gitignore` (create if missing):

```
scripts/qdrant/storage/
```

Verify by:
```bash
grep -n "scripts/qdrant/storage" .gitignore
```
Expected: matching line printed.

- [ ] **Step 8: Start Qdrant and verify**

```bash
scripts/qdrant/start.sh
curl -s http://127.0.0.1:6333/readyz
```
Expected: `Qdrant is ready.` then `all shards are ready` (or empty 200 OK).

```bash
curl -s http://127.0.0.1:6333/collections
```
Expected: JSON like `{"result":{"collections":[]},"status":"ok","time":...}`.

- [ ] **Step 9: Commit**

```bash
git add scripts/qdrant/docker-compose.yml scripts/qdrant/start.sh scripts/qdrant/stop.sh scripts/qdrant/start.ps1 scripts/qdrant/stop.ps1 scripts/qdrant/README.md .gitignore
git commit -m "infra(M1-T10): Qdrant docker compose + start/stop scripts

Single-node Qdrant 1.12.4 on ports 6333/6334. macOS/Linux .sh +
Windows .ps1 (UTF-8 BOM) for symmetric entry per CLAUDE.md Windows
compat rules. storage/ ignored."
```

---

## Task 11: Qdrant 客户端封装

**Files:**
- Create: `ink_writer/qdrant/client.py`
- Create: `ink_writer/qdrant/errors.py`
- Create: `tests/qdrant/conftest.py`
- Create: `tests/qdrant/test_client.py`

- [ ] **Step 1: Write the failing test**

Create `tests/qdrant/conftest.py`:

```python
"""Qdrant test fixtures.

Use the in-memory client (`:memory:`) for unit tests so they never need a
running Qdrant container. Integration tests against a real container are
marked separately and not in this task.
"""
from __future__ import annotations

import pytest
from qdrant_client import QdrantClient


@pytest.fixture
def in_memory_client() -> QdrantClient:
    return QdrantClient(":memory:")
```

Create `tests/qdrant/test_client.py`:

```python
from __future__ import annotations

import pytest
from qdrant_client.http.exceptions import ResponseHandlingException

from ink_writer.qdrant.client import QdrantConfig, get_client_from_config
from ink_writer.qdrant.errors import QdrantUnreachableError


def test_in_memory_client_via_helper() -> None:
    config = QdrantConfig(memory=True)
    client = get_client_from_config(config)
    # Simple ping: list collections should not raise.
    assert client.get_collections().collections == []


def test_unreachable_raises() -> None:
    config = QdrantConfig(host="127.0.0.1", port=1, timeout=0.5)  # port 1 is closed
    with pytest.raises(QdrantUnreachableError):
        get_client_from_config(config)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/qdrant/test_client.py -v --no-cov
```
Expected: ImportError.

- [ ] **Step 3: Implement client + errors**

Create `ink_writer/qdrant/errors.py`:

```python
"""Qdrant errors."""
from __future__ import annotations


class QdrantError(Exception):
    """Base class for Qdrant errors."""


class QdrantUnreachableError(QdrantError):
    """Raised when the Qdrant service cannot be reached within the timeout."""
```

Create `ink_writer/qdrant/client.py`:

```python
"""Thin wrapper around qdrant-client for ink-writer.

Two production modes:
- HTTP (default; talks to a running ``scripts/qdrant/start.sh`` instance)
- :memory: (used by unit tests; no docker required)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from ink_writer.qdrant.errors import QdrantUnreachableError


@dataclass
class QdrantConfig:
    host: str = "127.0.0.1"
    port: int = 6333
    timeout: float = 5.0
    memory: bool = False
    api_key: Optional[str] = None


def get_client_from_config(config: QdrantConfig) -> QdrantClient:
    if config.memory:
        return QdrantClient(":memory:")
    try:
        client = QdrantClient(
            host=config.host,
            port=config.port,
            timeout=config.timeout,
            api_key=config.api_key,
        )
        # Force a round-trip so unreachable hosts surface immediately.
        client.get_collections()
        return client
    except (ResponseHandlingException, UnexpectedResponse, ConnectionError, OSError) as err:
        raise QdrantUnreachableError(
            f"Qdrant at {config.host}:{config.port} unreachable: {err}"
        ) from err


_singleton: Optional[QdrantClient] = None


def get_qdrant_client(config: Optional[QdrantConfig] = None) -> QdrantClient:
    """Return a process-wide singleton client. ``config`` honored on first call."""
    global _singleton
    if _singleton is None:
        _singleton = get_client_from_config(config or QdrantConfig())
    return _singleton


def reset_singleton_for_tests() -> None:
    global _singleton
    _singleton = None
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/qdrant/test_client.py -v --no-cov
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add ink_writer/qdrant/client.py ink_writer/qdrant/errors.py tests/qdrant/conftest.py tests/qdrant/test_client.py
git commit -m "feat(M1-T11): Qdrant client wrapper with reachability probe

QdrantConfig (host/port/timeout/memory/api_key); get_client_from_config()
forces a get_collections() round-trip so unreachable hosts surface as
QdrantUnreachableError immediately. Singleton helper + reset hook."
```

---

## Task 12: Qdrant Payload Schema (collection 定义)

**Files:**
- Create: `ink_writer/qdrant/payload_schema.py`
- Create: `tests/qdrant/test_payload_schema.py`

- [ ] **Step 1: Write the failing test**

Create `tests/qdrant/test_payload_schema.py`:

```python
from __future__ import annotations

from ink_writer.qdrant.payload_schema import (
    CollectionSpec,
    EDITOR_WISDOM_RULES_SPEC,
    CORPUS_CHUNKS_SPEC,
    ensure_collection,
)


def test_collection_specs_have_expected_names_and_dims() -> None:
    assert EDITOR_WISDOM_RULES_SPEC.name == "editor_wisdom_rules"
    assert EDITOR_WISDOM_RULES_SPEC.vector_size == 4096
    assert CORPUS_CHUNKS_SPEC.name == "corpus_chunks"
    assert CORPUS_CHUNKS_SPEC.vector_size == 4096


def test_corpus_chunks_payload_has_filter_fields() -> None:
    assert "genre" in CORPUS_CHUNKS_SPEC.indexed_payload_fields
    assert "scene_type" in CORPUS_CHUNKS_SPEC.indexed_payload_fields
    assert "quality_score" in CORPUS_CHUNKS_SPEC.indexed_payload_fields
    assert "source_type" in CORPUS_CHUNKS_SPEC.indexed_payload_fields


def test_ensure_collection_creates_then_skips(in_memory_client) -> None:
    spec = CollectionSpec(
        name="test_collection",
        vector_size=8,
        indexed_payload_fields={"x": "keyword"},
    )
    created1 = ensure_collection(in_memory_client, spec)
    created2 = ensure_collection(in_memory_client, spec)
    assert created1 is True
    assert created2 is False
    assert any(c.name == "test_collection"
               for c in in_memory_client.get_collections().collections)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/qdrant/test_payload_schema.py -v --no-cov
```
Expected: ImportError.

- [ ] **Step 3: Implement payload schema**

Create `ink_writer/qdrant/payload_schema.py`:

```python
"""Qdrant collection definitions for ink-writer.

Two production collections are defined upfront so M2's chunker and the
FAISS migration script (Task 13) target stable names:

- editor_wisdom_rules: 80+ atomic rules from data/editor-wisdom/rules.json
- corpus_chunks: scene-level chunks produced in M2

Embedding dim = 4096 (Qwen3-Embedding-8B). Cosine distance.

``indexed_payload_fields`` triggers Qdrant's payload index so post-filter
queries (genre / scene_type / quality_score / source_type) stay fast.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from qdrant_client import QdrantClient
from qdrant_client.http import models as rest


@dataclass(frozen=True)
class CollectionSpec:
    name: str
    vector_size: int
    indexed_payload_fields: Mapping[str, str] = field(default_factory=dict)
    distance: rest.Distance = rest.Distance.COSINE


_QWEN3_EMBEDDING_DIM = 4096

EDITOR_WISDOM_RULES_SPEC = CollectionSpec(
    name="editor_wisdom_rules",
    vector_size=_QWEN3_EMBEDDING_DIM,
    indexed_payload_fields={
        "category": "keyword",
        "applies_to": "keyword",
        "scoring_dimensions": "keyword",
    },
)


CORPUS_CHUNKS_SPEC = CollectionSpec(
    name="corpus_chunks",
    vector_size=_QWEN3_EMBEDDING_DIM,
    indexed_payload_fields={
        "genre": "keyword",
        "scene_type": "keyword",
        "quality_score": "float",
        "source_type": "keyword",
        "source_book": "keyword",
        "case_ids": "keyword",
    },
)


_FIELD_TYPE_MAP = {
    "keyword": rest.PayloadSchemaType.KEYWORD,
    "float": rest.PayloadSchemaType.FLOAT,
    "integer": rest.PayloadSchemaType.INTEGER,
    "bool": rest.PayloadSchemaType.BOOL,
}


def ensure_collection(client: QdrantClient, spec: CollectionSpec) -> bool:
    """Create the collection + payload indices if missing.

    Returns:
        True if newly created, False if it already existed.
    """
    existing = {c.name for c in client.get_collections().collections}
    if spec.name in existing:
        return False
    client.create_collection(
        collection_name=spec.name,
        vectors_config=rest.VectorParams(
            size=spec.vector_size,
            distance=spec.distance,
        ),
    )
    for field_name, field_type in spec.indexed_payload_fields.items():
        client.create_payload_index(
            collection_name=spec.name,
            field_name=field_name,
            field_schema=_FIELD_TYPE_MAP[field_type],
        )
    return True
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/qdrant/test_payload_schema.py -v --no-cov
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add ink_writer/qdrant/payload_schema.py tests/qdrant/test_payload_schema.py
git commit -m "feat(M1-T12): Qdrant collection specs + ensure_collection helper

EDITOR_WISDOM_RULES_SPEC and CORPUS_CHUNKS_SPEC freeze production
collection names + payload index fields (genre/scene_type/quality_score/
source_type/case_ids on chunks). ensure_collection is idempotent."
```

---

## Task 13: FAISS → Qdrant 迁移脚本（含双写）

**Files:**
- Create: `scripts/qdrant/migrate_faiss_to_qdrant.py`
- Create: `tests/scripts/test_migrate_faiss_to_qdrant.py`

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_migrate_faiss_to_qdrant.py`:

```python
from __future__ import annotations

from pathlib import Path

import faiss
import numpy as np
import pytest

from scripts.qdrant.migrate_faiss_to_qdrant import (
    MigrationReport,
    migrate_faiss_index,
)
from ink_writer.qdrant.client import get_client_from_config, QdrantConfig
from ink_writer.qdrant.payload_schema import CollectionSpec


@pytest.fixture
def fake_faiss_dir(tmp_path: Path):
    dim = 8
    n = 5
    rng = np.random.default_rng(seed=42)
    vectors = rng.random((n, dim), dtype=np.float32)
    index = faiss.IndexFlatIP(dim)
    index.add(vectors)
    faiss.write_index(index, str(tmp_path / "index.faiss"))

    metadata = [
        {"id": f"R-{i:03d}", "category": "opening", "text": f"rule {i}"}
        for i in range(n)
    ]
    import json
    with open(tmp_path / "metadata.jsonl", "w", encoding="utf-8") as fp:
        for row in metadata:
            fp.write(json.dumps(row, ensure_ascii=False))
            fp.write("\n")
    return tmp_path, dim, vectors, metadata


def test_migration_uploads_all_vectors(fake_faiss_dir) -> None:
    src_dir, dim, vectors, metadata = fake_faiss_dir
    spec = CollectionSpec(
        name="test_migration",
        vector_size=dim,
        indexed_payload_fields={"category": "keyword"},
    )
    client = get_client_from_config(QdrantConfig(memory=True))
    report = migrate_faiss_index(
        client=client,
        spec=spec,
        faiss_index_path=src_dir / "index.faiss",
        metadata_jsonl=src_dir / "metadata.jsonl",
    )
    assert isinstance(report, MigrationReport)
    assert report.uploaded == len(metadata)
    info = client.get_collection("test_migration")
    assert info.points_count == len(metadata)


def test_migration_is_idempotent(fake_faiss_dir) -> None:
    src_dir, dim, _, metadata = fake_faiss_dir
    spec = CollectionSpec(
        name="test_migration_idem",
        vector_size=dim,
        indexed_payload_fields={"category": "keyword"},
    )
    client = get_client_from_config(QdrantConfig(memory=True))
    migrate_faiss_index(client, spec, src_dir / "index.faiss", src_dir / "metadata.jsonl")
    migrate_faiss_index(client, spec, src_dir / "index.faiss", src_dir / "metadata.jsonl")
    info = client.get_collection("test_migration_idem")
    assert info.points_count == len(metadata)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/scripts/test_migrate_faiss_to_qdrant.py -v --no-cov
```
Expected: ImportError on `scripts.qdrant.migrate_faiss_to_qdrant`.

- [ ] **Step 3: Implement migration script**

Create `scripts/qdrant/__init__.py`:
```bash
touch scripts/qdrant/__init__.py
```

Create `scripts/qdrant/migrate_faiss_to_qdrant.py`:

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Migrate a FAISS index + metadata.jsonl into a Qdrant collection.

Pairs with ink_writer/qdrant/payload_schema.py CollectionSpec. Idempotent:
re-running upserts the same point ids (no duplication).

The metadata.jsonl format is one JSON object per line. Each object MUST
contain an ``id`` field used as the Qdrant point id; remaining fields are
written verbatim into the payload.
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import faiss
import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.http import models as rest

from ink_writer.qdrant.client import QdrantConfig, get_client_from_config
from ink_writer.qdrant.payload_schema import (
    CORPUS_CHUNKS_SPEC,
    EDITOR_WISDOM_RULES_SPEC,
    CollectionSpec,
    ensure_collection,
)


@dataclass
class MigrationReport:
    collection: str
    uploaded: int
    skipped: int = 0


def _load_metadata(jsonl_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open(jsonl_path, encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _stable_uuid_from_id(string_id: str) -> str:
    """Map an arbitrary string id to a deterministic UUID5.

    Qdrant accepts either int or UUID strings as point ids; UUID5 keeps the
    mapping stable across runs (so re-running the script is idempotent).
    """
    return str(uuid.uuid5(uuid.NAMESPACE_URL, string_id))


def migrate_faiss_index(
    client: QdrantClient,
    spec: CollectionSpec,
    faiss_index_path: Path,
    metadata_jsonl: Path,
    batch_size: int = 256,
) -> MigrationReport:
    ensure_collection(client, spec)

    index = faiss.read_index(str(faiss_index_path))
    n = index.ntotal
    metadata = _load_metadata(metadata_jsonl)
    if len(metadata) != n:
        raise ValueError(
            f"FAISS ntotal={n} != metadata rows={len(metadata)}; refusing to migrate."
        )

    vectors = np.zeros((n, index.d), dtype=np.float32)
    index.reconstruct_n(0, n, vectors)

    uploaded = 0
    for start in range(0, n, batch_size):
        end = min(start + batch_size, n)
        points = []
        for i in range(start, end):
            row = metadata[i]
            string_id = str(row.get("id"))
            if not string_id or string_id == "None":
                raise ValueError(f"metadata row {i} missing 'id' field")
            payload = {k: v for k, v in row.items() if k != "id"}
            payload["original_id"] = string_id
            points.append(
                rest.PointStruct(
                    id=_stable_uuid_from_id(string_id),
                    vector=vectors[i].tolist(),
                    payload=payload,
                )
            )
        client.upsert(collection_name=spec.name, points=points)
        uploaded += len(points)

    return MigrationReport(collection=spec.name, uploaded=uploaded)


_PRESETS = {
    "editor_wisdom_rules": EDITOR_WISDOM_RULES_SPEC,
    "corpus_chunks": CORPUS_CHUNKS_SPEC,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", choices=sorted(_PRESETS.keys()), required=True)
    parser.add_argument("--faiss-index", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--qdrant-host", default="127.0.0.1")
    parser.add_argument("--qdrant-port", type=int, default=6333)
    args = parser.parse_args(argv)

    client = get_client_from_config(
        QdrantConfig(host=args.qdrant_host, port=args.qdrant_port)
    )
    report = migrate_faiss_index(
        client=client,
        spec=_PRESETS[args.preset],
        faiss_index_path=args.faiss_index,
        metadata_jsonl=args.metadata,
    )
    print(f"collection={report.collection} uploaded={report.uploaded}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/scripts/test_migrate_faiss_to_qdrant.py -v --no-cov
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/qdrant/__init__.py scripts/qdrant/migrate_faiss_to_qdrant.py tests/scripts/test_migrate_faiss_to_qdrant.py
git commit -m "feat(M1-T13): FAISS → Qdrant migration script

migrate_faiss_index reads a FAISS index + metadata.jsonl, ensures the
target collection (matching CollectionSpec dimensions and payload
indices), and upserts points in batches. Idempotent via UUID5 derived
from original metadata 'id'."
```

---

## Task 14: Preflight 6 个独立 check 函数

**Files:**
- Create: `ink_writer/preflight/checks.py`
- Create: `ink_writer/preflight/errors.py`
- Create: `tests/preflight/test_checks.py`

- [ ] **Step 1: Write the failing test**

Create `tests/preflight/test_checks.py`:

```python
from __future__ import annotations

import os
from pathlib import Path

import pytest

from ink_writer.preflight.checks import (
    CheckResult,
    check_case_library_loadable,
    check_editor_wisdom_index_loadable,
    check_embedding_api_reachable,
    check_qdrant_connection,
    check_reference_corpus_readable,
    check_rerank_api_reachable,
)


def _build_fake_corpus(root: Path, books: int, chapters: int) -> Path:
    rc = root / "reference_corpus"
    rc.mkdir(parents=True)
    for b in range(books):
        cdir = rc / f"book{b:02d}" / "chapters"
        cdir.mkdir(parents=True)
        for c in range(chapters):
            (cdir / f"ch{c:03d}.txt").write_text(f"book{b} chapter{c}", encoding="utf-8")
    return rc


def test_reference_corpus_pass(tmp_path: Path) -> None:
    rc = _build_fake_corpus(tmp_path, books=2, chapters=3)
    result = check_reference_corpus_readable(rc, min_files=5)
    assert isinstance(result, CheckResult)
    assert result.passed is True


def test_reference_corpus_fail_when_below_min(tmp_path: Path) -> None:
    rc = _build_fake_corpus(tmp_path, books=1, chapters=2)
    result = check_reference_corpus_readable(rc, min_files=5)
    assert result.passed is False
    assert "below" in result.detail.lower()


def test_reference_corpus_fail_when_broken_symlink(tmp_path: Path) -> None:
    rc = _build_fake_corpus(tmp_path, books=1, chapters=2)
    broken = rc / "book00" / "chapters" / "ch_broken.txt"
    broken.symlink_to("/nonexistent/path.txt")
    result = check_reference_corpus_readable(rc, min_files=1)
    assert result.passed is False
    assert "broken" in result.detail.lower()


def test_case_library_loadable_pass(tmp_path: Path) -> None:
    library = tmp_path / "case_library"
    (library / "cases").mkdir(parents=True)
    result = check_case_library_loadable(library)
    assert result.passed is True


def test_case_library_loadable_fail_when_missing(tmp_path: Path) -> None:
    result = check_case_library_loadable(tmp_path / "nope")
    assert result.passed is False


def test_editor_wisdom_index_loadable_pass(tmp_path: Path) -> None:
    p = tmp_path / "rules.json"
    p.write_text('[{"id":"R-001","text":"x"}]', encoding="utf-8")
    result = check_editor_wisdom_index_loadable(p)
    assert result.passed is True


def test_editor_wisdom_index_loadable_fail_when_missing(tmp_path: Path) -> None:
    result = check_editor_wisdom_index_loadable(tmp_path / "missing.json")
    assert result.passed is False


def test_qdrant_connection_pass_with_in_memory_client(in_memory_client) -> None:
    result = check_qdrant_connection(client=in_memory_client)
    assert result.passed is True


def test_embedding_api_reachable_no_key(monkeypatch) -> None:
    monkeypatch.delenv("EMBED_API_KEY", raising=False)
    result = check_embedding_api_reachable()
    assert result.passed is False
    assert "EMBED_API_KEY" in result.detail


def test_rerank_api_reachable_no_key(monkeypatch) -> None:
    monkeypatch.delenv("RERANK_API_KEY", raising=False)
    result = check_rerank_api_reachable()
    assert result.passed is False
    assert "RERANK_API_KEY" in result.detail
```

Note: this test file imports `in_memory_client` from `tests/qdrant/conftest.py`. Pytest auto-discovers it only if the fixture is also visible to `tests/preflight/`. Add a re-export in `tests/preflight/conftest.py`:

Create `tests/preflight/conftest.py`:

```python
"""Re-use the qdrant in-memory client fixture for preflight tests."""
from tests.qdrant.conftest import in_memory_client  # noqa: F401  (pytest fixture)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/preflight/test_checks.py -v --no-cov
```
Expected: ImportError.

- [ ] **Step 3: Implement errors and checks**

Create `ink_writer/preflight/errors.py`:

```python
"""Preflight errors."""
from __future__ import annotations


class PreflightError(Exception):
    """Raised when one or more preflight checks fail and writing must abort."""

    def __init__(self, failed_check_names: list[str], message: str) -> None:
        super().__init__(message)
        self.failed_check_names = list(failed_check_names)
```

Create `ink_writer/preflight/checks.py`:

```python
"""Six preflight checks for ink-write startup.

Each check returns a :class:`CheckResult` (passed bool + human-readable
detail). Failures are aggregated by ``run_preflight`` (Task 15) and become
infra_health cases.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from qdrant_client import QdrantClient

from ink_writer.qdrant.client import QdrantConfig, get_client_from_config
from ink_writer.qdrant.errors import QdrantUnreachableError


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


def check_reference_corpus_readable(
    reference_root: Path,
    *,
    min_files: int = 100,
) -> CheckResult:
    """Pass iff the corpus has ≥ min_files readable .txt files and zero broken symlinks."""
    name = "reference_corpus_readable"
    if not reference_root.is_dir():
        return CheckResult(name, False, f"{reference_root} does not exist")
    readable = 0
    broken: list[Path] = []
    for path in reference_root.rglob("*.txt"):
        if path.is_symlink() and not path.exists():
            broken.append(path)
            continue
        if path.is_file():
            readable += 1
    if broken:
        return CheckResult(
            name,
            False,
            f"{len(broken)} broken symlink(s) under {reference_root}; first: {broken[0]}",
        )
    if readable < min_files:
        return CheckResult(
            name,
            False,
            f"readable file count {readable} below min_files={min_files}",
        )
    return CheckResult(name, True, f"{readable} files readable")


def check_case_library_loadable(library_root: Path) -> CheckResult:
    name = "case_library_loadable"
    if not library_root.is_dir():
        return CheckResult(name, False, f"{library_root} does not exist")
    cases_dir = library_root / "cases"
    if not cases_dir.is_dir():
        return CheckResult(name, False, f"{cases_dir} missing")
    return CheckResult(name, True, f"{len(list(cases_dir.glob('CASE-*.yaml')))} cases on disk")


def check_editor_wisdom_index_loadable(rules_path: Path) -> CheckResult:
    name = "editor_wisdom_index_loadable"
    if not rules_path.is_file():
        return CheckResult(name, False, f"{rules_path} missing")
    try:
        with open(rules_path, encoding="utf-8") as fp:
            data = json.load(fp)
    except json.JSONDecodeError as err:
        return CheckResult(name, False, f"{rules_path} not valid JSON: {err}")
    return CheckResult(name, True, f"{len(data)} rules indexed")


def check_qdrant_connection(
    *,
    client: Optional[QdrantClient] = None,
    config: Optional[QdrantConfig] = None,
) -> CheckResult:
    name = "qdrant_connection"
    try:
        cli = client if client is not None else get_client_from_config(config or QdrantConfig())
        cli.get_collections()
        return CheckResult(name, True, "qdrant reachable")
    except QdrantUnreachableError as err:
        return CheckResult(name, False, str(err))
    except Exception as err:  # noqa: BLE001 — preflight must never propagate
        return CheckResult(name, False, f"unexpected error: {err}")


def check_embedding_api_reachable() -> CheckResult:
    name = "embedding_api_reachable"
    if not os.environ.get("EMBED_API_KEY"):
        return CheckResult(name, False, "EMBED_API_KEY not set")
    return CheckResult(name, True, "EMBED_API_KEY present")


def check_rerank_api_reachable() -> CheckResult:
    name = "rerank_api_reachable"
    if not os.environ.get("RERANK_API_KEY"):
        return CheckResult(name, False, "RERANK_API_KEY not set")
    return CheckResult(name, True, "RERANK_API_KEY present")
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/preflight/test_checks.py -v --no-cov
```
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add ink_writer/preflight/errors.py ink_writer/preflight/checks.py tests/preflight/test_checks.py tests/preflight/conftest.py
git commit -m "feat(M1-T14): six preflight check functions

reference_corpus_readable / case_library_loadable /
editor_wisdom_index_loadable / qdrant_connection /
embedding_api_reachable / rerank_api_reachable. Each returns
CheckResult(name, passed, detail) — never raises."
```

---

## Task 15: Preflight checker + 自动建 infra_health case

**Files:**
- Create: `ink_writer/preflight/checker.py`
- Create: `tests/preflight/test_checker.py`

- [ ] **Step 1: Write the failing test**

Create `tests/preflight/test_checker.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from ink_writer.case_library.store import CaseStore
from ink_writer.preflight.checker import (
    PreflightConfig,
    PreflightReport,
    run_preflight,
)
from ink_writer.preflight.errors import PreflightError


def _make_config(tmp_path: Path) -> PreflightConfig:
    library_root = tmp_path / "case_library"
    (library_root / "cases").mkdir(parents=True)
    rules = tmp_path / "rules.json"
    rules.write_text("[]", encoding="utf-8")
    rc = tmp_path / "reference_corpus"
    rc.mkdir()
    return PreflightConfig(
        reference_root=rc,
        case_library_root=library_root,
        editor_wisdom_rules_path=rules,
        qdrant_in_memory=True,
        require_embedding_key=False,
        require_rerank_key=False,
        min_corpus_files=0,  # tests don't seed real chapters
    )


def test_all_pass_returns_clean_report(tmp_path: Path) -> None:
    cfg = _make_config(tmp_path)
    report = run_preflight(cfg)
    assert isinstance(report, PreflightReport)
    assert report.all_passed is True
    assert all(r.passed for r in report.results)


def test_failed_check_creates_infra_case(tmp_path: Path) -> None:
    cfg = _make_config(tmp_path)
    cfg.editor_wisdom_rules_path = tmp_path / "missing.json"  # force fail
    with pytest.raises(PreflightError):
        run_preflight(cfg, raise_on_fail=True, auto_create_infra_cases=True)
    store = CaseStore(cfg.case_library_root)
    ids = store.list_ids()
    # At least one new infra_health case was created.
    new_cases = [
        store.load(i) for i in ids
        if i != "CASE-2026-0000"
    ]
    assert any(
        c.domain.value == "infra_health"
        and "editor_wisdom_index_loadable" in c.title
        for c in new_cases
    )


def test_failed_check_without_raise_returns_failed_report(tmp_path: Path) -> None:
    cfg = _make_config(tmp_path)
    cfg.editor_wisdom_rules_path = tmp_path / "missing.json"
    report = run_preflight(cfg, raise_on_fail=False, auto_create_infra_cases=False)
    assert report.all_passed is False
    assert any(not r.passed for r in report.results)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/preflight/test_checker.py -v --no-cov
```
Expected: ImportError.

- [ ] **Step 3: Implement checker**

Create `ink_writer/preflight/checker.py`:

```python
"""Aggregate the six preflight checks into one report.

Failures can:
1. Optionally create infra_health cases (one per failed check, deduped by
   raw_text hash so re-running does not pile up duplicates).
2. Optionally raise PreflightError so ink-write can abort cleanly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ink_writer.case_library.ingest import ingest_case
from ink_writer.case_library.store import CaseStore
from ink_writer.preflight.checks import (
    CheckResult,
    check_case_library_loadable,
    check_editor_wisdom_index_loadable,
    check_embedding_api_reachable,
    check_qdrant_connection,
    check_reference_corpus_readable,
    check_rerank_api_reachable,
)
from ink_writer.preflight.errors import PreflightError
from ink_writer.qdrant.client import QdrantConfig


@dataclass
class PreflightConfig:
    reference_root: Path
    case_library_root: Path
    editor_wisdom_rules_path: Path
    qdrant_config: Optional[QdrantConfig] = None
    qdrant_in_memory: bool = False
    require_embedding_key: bool = True
    require_rerank_key: bool = True
    min_corpus_files: int = 100


@dataclass
class PreflightReport:
    results: list[CheckResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def failed(self) -> list[CheckResult]:
        return [r for r in self.results if not r.passed]


def _today_iso() -> str:
    from datetime import date
    return date.today().isoformat()


def _create_infra_case_for(check: CheckResult, store: CaseStore) -> None:
    raw_text = f"preflight check failed: {check.name}: {check.detail}"
    ingest_case(
        store,
        title=f"preflight failure: {check.name}",
        raw_text=raw_text,
        domain="infra_health",
        layer=["infra_health"],
        severity="P0",
        tags=["preflight", check.name],
        source_type="infra_check",
        ingested_at=_today_iso(),
        failure_description=check.detail,
        observable=[f"{check.name}.passed == False"],
    )


def run_preflight(
    config: PreflightConfig,
    *,
    raise_on_fail: bool = False,
    auto_create_infra_cases: bool = False,
) -> PreflightReport:
    qdrant_cfg = config.qdrant_config
    if config.qdrant_in_memory:
        qdrant_cfg = QdrantConfig(memory=True)

    results: list[CheckResult] = [
        check_reference_corpus_readable(
            config.reference_root,
            min_files=config.min_corpus_files,
        ),
        check_case_library_loadable(config.case_library_root),
        check_editor_wisdom_index_loadable(config.editor_wisdom_rules_path),
        check_qdrant_connection(config=qdrant_cfg),
    ]
    if config.require_embedding_key:
        results.append(check_embedding_api_reachable())
    if config.require_rerank_key:
        results.append(check_rerank_api_reachable())

    report = PreflightReport(results=results)
    if not report.all_passed:
        if auto_create_infra_cases:
            store = CaseStore(config.case_library_root)
            for failed in report.failed:
                _create_infra_case_for(failed, store)
        if raise_on_fail:
            failed_names = [r.name for r in report.failed]
            raise PreflightError(failed_names, f"preflight failed: {failed_names}")
    return report
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/preflight/test_checker.py -v --no-cov
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add ink_writer/preflight/checker.py tests/preflight/test_checker.py
git commit -m "feat(M1-T15): preflight checker aggregates 6 checks + auto infra cases

run_preflight returns a PreflightReport (results + all_passed). When
auto_create_infra_cases=True each failure ingests a new infra_health
case (sha256 dedup keeps repeated failures from piling up). When
raise_on_fail=True, raises PreflightError so ink-write can abort cleanly."
```

---

## Task 16: Preflight CLI + 集成到 ink-write SKILL.md

**Files:**
- Create: `ink_writer/preflight/cli.py`
- Create: `tests/preflight/test_cli.py`
- Modify: `ink-writer/skills/ink-write/SKILL.md`

- [ ] **Step 1: Write the failing test**

Create `tests/preflight/test_cli.py`:

```python
from __future__ import annotations

from pathlib import Path

from ink_writer.preflight.cli import main


def test_cli_runs_in_minimal_mode(tmp_path: Path, capsys, monkeypatch) -> None:
    library_root = tmp_path / "case_library"
    (library_root / "cases").mkdir(parents=True)
    rules = tmp_path / "rules.json"
    rules.write_text("[]", encoding="utf-8")
    rc = tmp_path / "reference_corpus"
    rc.mkdir()

    rc_arg = ["--reference-root", str(rc)]
    cl_arg = ["--case-library-root", str(library_root)]
    rl_arg = ["--editor-wisdom-rules", str(rules)]
    flags = ["--qdrant-in-memory", "--no-require-embedding-key",
             "--no-require-rerank-key", "--min-corpus-files", "0"]
    rc_code = main(rc_arg + cl_arg + rl_arg + flags)
    out = capsys.readouterr().out
    assert rc_code == 0
    assert "all_passed=True" in out


def test_cli_failed_returns_nonzero(tmp_path: Path, capsys) -> None:
    library_root = tmp_path / "case_library"
    (library_root / "cases").mkdir(parents=True)
    rc = tmp_path / "reference_corpus"
    rc.mkdir()

    rc_arg = ["--reference-root", str(rc)]
    cl_arg = ["--case-library-root", str(library_root)]
    rl_arg = ["--editor-wisdom-rules", str(tmp_path / "missing.json")]
    flags = ["--qdrant-in-memory", "--no-require-embedding-key",
             "--no-require-rerank-key", "--min-corpus-files", "0",
             "--auto-create-infra-cases"]
    rc_code = main(rc_arg + cl_arg + rl_arg + flags)
    out = capsys.readouterr().out
    assert rc_code != 0
    assert "all_passed=False" in out
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/preflight/test_cli.py -v --no-cov
```
Expected: ImportError.

- [ ] **Step 3: Implement CLI**

Create `ink_writer/preflight/cli.py`:

```python
"""`ink preflight` CLI."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ink_writer.preflight.checker import PreflightConfig, run_preflight


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ink preflight", description=__doc__)
    p.add_argument("--reference-root", type=Path,
                   default=Path("benchmark/reference_corpus"))
    p.add_argument("--case-library-root", type=Path,
                   default=Path("data/case_library"))
    p.add_argument("--editor-wisdom-rules", type=Path,
                   default=Path("data/editor-wisdom/rules.json"))
    p.add_argument("--qdrant-in-memory", action="store_true",
                   help="Use in-memory qdrant (for tests)")
    p.add_argument("--qdrant-host", default="127.0.0.1")
    p.add_argument("--qdrant-port", type=int, default=6333)
    p.add_argument("--require-embedding-key", dest="require_embedding_key",
                   action="store_true", default=True)
    p.add_argument("--no-require-embedding-key", dest="require_embedding_key",
                   action="store_false")
    p.add_argument("--require-rerank-key", dest="require_rerank_key",
                   action="store_true", default=True)
    p.add_argument("--no-require-rerank-key", dest="require_rerank_key",
                   action="store_false")
    p.add_argument("--min-corpus-files", type=int, default=100)
    p.add_argument("--auto-create-infra-cases", action="store_true")
    p.add_argument("--raise-on-fail", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    cfg = PreflightConfig(
        reference_root=args.reference_root,
        case_library_root=args.case_library_root,
        editor_wisdom_rules_path=args.editor_wisdom_rules,
        qdrant_in_memory=args.qdrant_in_memory,
        require_embedding_key=args.require_embedding_key,
        require_rerank_key=args.require_rerank_key,
        min_corpus_files=args.min_corpus_files,
    )
    if not args.qdrant_in_memory:
        from ink_writer.qdrant.client import QdrantConfig
        cfg.qdrant_config = QdrantConfig(host=args.qdrant_host, port=args.qdrant_port)

    try:
        report = run_preflight(
            cfg,
            raise_on_fail=args.raise_on_fail,
            auto_create_infra_cases=args.auto_create_infra_cases,
        )
    except Exception as err:  # noqa: BLE001 — CLI must never raise
        print(f"all_passed=False error={err}")
        return 2

    print(f"all_passed={report.all_passed}")
    for r in report.results:
        flag = "OK " if r.passed else "FAIL"
        print(f"  [{flag}] {r.name}: {r.detail}")
    return 0 if report.all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/preflight/test_cli.py -v --no-cov
```
Expected: 2 passed.

- [ ] **Step 5: Wire preflight into ink-write SKILL.md**

Open `ink-writer/skills/ink-write/SKILL.md`, find the first executable step under "Project Root Guard"/setup. Insert a new section **immediately after** the env-setup invocation block:

```markdown
## Step 0 — Preflight Health Check（M1 起强制）

环境设置后立即执行 preflight，确保参考库可读、case_library 加载成功、Qdrant 可达、embedding/rerank API key 存在。任一失败 → 阻断写作并自动建立 infra_health 病例（参见 docs/superpowers/specs/2026-04-23-...md §2.6）。

```bash
python -m ink_writer.preflight.cli --auto-create-infra-cases --raise-on-fail
```
<!-- windows-ps1-sibling -->
Windows（PowerShell 5.1+）：

```powershell
python -m ink_writer.preflight.cli --auto-create-infra-cases --raise-on-fail
```

退出码非 0 时**不要继续后续 step**；先解决报告中标记 FAIL 的项（或运行 `ink case list` 查看已自动登记的病例）。
```

- [ ] **Step 6: Verify ink-write SKILL.md change**

```bash
grep -n "ink_writer.preflight.cli" ink-writer/skills/ink-write/SKILL.md
```
Expected: at least 2 lines (bash + powershell).

- [ ] **Step 7: Commit**

```bash
git add ink_writer/preflight/cli.py tests/preflight/test_cli.py ink-writer/skills/ink-write/SKILL.md
git commit -m "feat(M1-T16): ink preflight CLI + wire into ink-write SKILL.md

main(argv) returns 0/1/2 (success/preflight-fail/error). ink-write SKILL.md
gains a Step 0 that runs --auto-create-infra-cases --raise-on-fail with
a Windows PowerShell sibling block per CLAUDE.md."
```

---

## Task 17: M1 端到端集成测试 + 验收

**Files:**
- Create: `tests/integration/test_m1_e2e.py`

- [ ] **Step 1: Write the integration test**

Create `tests/integration/test_m1_e2e.py`:

```python
"""M1 end-to-end: preflight failure → infra case auto-created → ink case list shows it.

This covers the full M1 contract: when reference_corpus is broken (or any
other infra fault), preflight aborts ink-write AND logs a structured
infra_health case so the operator can see and fix it.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ink_writer.case_library.cli import main as case_main
from ink_writer.case_library.store import CaseStore
from ink_writer.preflight.cli import main as preflight_main


def test_preflight_fail_creates_infra_case_visible_via_cli(tmp_path: Path, capsys) -> None:
    library_root = tmp_path / "case_library"
    (library_root / "cases").mkdir(parents=True)
    rc = tmp_path / "reference_corpus"
    # Intentionally do NOT create rc → forces check_reference_corpus_readable to fail.

    pre_args = [
        "--reference-root", str(rc),
        "--case-library-root", str(library_root),
        "--editor-wisdom-rules", str(tmp_path / "missing.json"),
        "--qdrant-in-memory",
        "--no-require-embedding-key",
        "--no-require-rerank-key",
        "--min-corpus-files", "0",
        "--auto-create-infra-cases",
    ]
    rc_code = preflight_main(pre_args)
    out = capsys.readouterr().out
    assert rc_code != 0
    assert "all_passed=False" in out

    # Now `ink case list` must show the auto-created infra cases.
    list_rc = case_main(["--library-root", str(library_root), "list"])
    out2 = capsys.readouterr().out
    assert list_rc == 0
    case_ids = [line.strip() for line in out2.splitlines() if line.strip().startswith("CASE-")]
    assert len(case_ids) >= 1

    # Each new case is infra_health with severity P0.
    store = CaseStore(library_root)
    for cid in case_ids:
        case = store.load(cid)
        assert case.domain.value == "infra_health"
        assert case.severity.value == "P0"


def test_preflight_pass_creates_no_new_cases(tmp_path: Path, capsys) -> None:
    library_root = tmp_path / "case_library"
    (library_root / "cases").mkdir(parents=True)
    rc = tmp_path / "reference_corpus"
    rc.mkdir()
    rules = tmp_path / "rules.json"
    rules.write_text("[]", encoding="utf-8")

    pre_args = [
        "--reference-root", str(rc),
        "--case-library-root", str(library_root),
        "--editor-wisdom-rules", str(rules),
        "--qdrant-in-memory",
        "--no-require-embedding-key",
        "--no-require-rerank-key",
        "--min-corpus-files", "0",
        "--auto-create-infra-cases",
    ]
    rc_code = preflight_main(pre_args)
    out = capsys.readouterr().out
    assert rc_code == 0
    assert "all_passed=True" in out

    list_rc = case_main(["--library-root", str(library_root), "list"])
    out2 = capsys.readouterr().out
    assert list_rc == 0
    assert not out2.strip(), f"expected no cases listed, got: {out2!r}"
```

- [ ] **Step 2: Run integration test**

```bash
pytest tests/integration/test_m1_e2e.py -v --no-cov
```
Expected: 2 passed.

- [ ] **Step 3: Run the full M1 test suite (smoke check)**

```bash
pytest tests/case_library tests/qdrant tests/preflight tests/maintenance tests/scripts/test_migrate_faiss_to_qdrant.py tests/integration/test_m1_e2e.py -v --no-cov
```
Expected: All M1 tests pass (∼ 35-40 tests across the new dirs).

- [ ] **Step 4: Real-world preflight smoke (against the actual project)**

This step verifies the script runs against real paths. Requires Qdrant running locally (Task 10) and the .env populated (or use `--no-require-embedding-key --no-require-rerank-key` to skip API checks).

```bash
scripts/qdrant/start.sh
python -m ink_writer.preflight.cli --auto-create-infra-cases --no-require-embedding-key --no-require-rerank-key
```
Expected: `all_passed=True` (assuming Task 1 already fixed the symlinks). Each check prints `[OK ]` plus a one-line detail.

- [ ] **Step 5: Run full project pytest (regression check)**

```bash
pytest -q
```
Expected: prior test suite + all M1 tests pass; coverage ≥ 70 (existing pytest.ini gate). If coverage drops below 70 because the new packages skew the denominator, add the new modules to `.coveragerc`'s explicit `source` list (this should not be needed because the new tests cover the new code).

- [ ] **Step 6: Final commit + tag**

```bash
git add tests/integration/test_m1_e2e.py
git commit -m "test(M1-T17): end-to-end M1 integration test + acceptance

Asserts preflight failure auto-creates infra_health P0 cases visible via
ink case list, and that a clean preflight does not pile up cases. Full
M1 suite green."

git tag -a m1-foundation -m "M1 complete: case_library + qdrant + preflight + symlink fix"
```

---

## Self-Review Checklist (run before declaring M1 plan complete)

- [x] **Spec coverage:** Each spec §9 M1 bullet maps to a task in this plan:
  - case schema 定稿 → Task 3
  - data/case_library/ + sqlite 索引 → Tasks 5, 6
  - ink case CLI → Task 8
  - Qdrant docker 部署 + 健康检查 → Task 10
  - FAISS → Qdrant 迁移脚本 → Task 13
  - Qdrant payload schema → Task 12
  - CASE-2026-0000 → Task 9
  - preflight health checker (6 项) → Tasks 14, 15
  - 修复 reference_corpus 软链接 → Task 1
  - preflight 集成到 ink-write SKILL.md → Task 16
- [x] **No placeholders:** every step shows full code or full command + expected output. No "TODO", "TBD", "implement later".
- [x] **Type consistency:** `Case`, `CaseStore`, `CaseIndex`, `CaseConfig`, `PreflightConfig`, `CollectionSpec` names match across tasks; `case_id` pattern enforced uniformly; `CaseSeverity.P0` etc. used consistently.
- [x] **Frequent commits:** every task ends with one commit; each test–implement cycle commits at the end of the task.
- [x] **Windows compat:** `.ps1` siblings shipped for `start/stop` (Task 10) and explicitly mentioned in SKILL.md sibling block (Task 16); all Python files use `open(... encoding="utf-8")`.

---

## What this plan does NOT do (deferred to M2-M5)

- Does not run `chunker` / segmenter (M2)
- Does not invoke writer-self-check or new checkers (M3)
- Does not add `genre-novelty-checker` etc. (M4)
- Does not retire FAISS (M2 finishes that during dual-write window)
- Does not promote any pending case to active beyond the zero-case (M2)

---

## Acceptance Gate (must hold to claim M1 done)

1. `pytest -q` passes; coverage ≥ 70.
2. `scripts/qdrant/start.sh` brings Qdrant up; `curl http://127.0.0.1:6333/readyz` returns 200.
3. `python scripts/maintenance/fix_reference_corpus_symlinks.py` reports `missing_source=0` against the live `benchmark/reference_corpus/`.
4. `python -m ink_writer.preflight.cli --no-require-embedding-key --no-require-rerank-key` returns `all_passed=True`.
5. `python scripts/case_library/init_zero_case.py` creates `data/case_library/cases/CASE-2026-0000.yaml` (or reports `already_exists`).
6. `ink-writer/skills/ink-write/SKILL.md` Step 0 references `python -m ink_writer.preflight.cli`.
