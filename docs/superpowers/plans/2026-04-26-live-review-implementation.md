# Live-Review 模块 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **本 plan 同时设计为 ralph 友好**：每个 Task = 1 条 ralph user story，acceptance criteria 全部机器可验。

**Goal:** 把 174 份星河编辑 B 站直播稿融入 ink-writer 写作链路，产出 3 类产物（作品病例 / 题材接受度信号 / 新原子规则候选）→ 接入 init / write / review 三阶段，使新书选材命中星河打分 ≥60 分签约线的概率显著提升。

**Architecture:** 新建独立模块 `live-review` 与现有 `editor-wisdom` 并列。LLM 切分管线 → 三类产物分发（病例 / 题材聚合 / 规则候选）→ 三阶段接入。复用现有 `case_library`（扩 schema 加 optional block）、`_id_alloc.py`（按 prefix 隔离）、`bge-small-zh-v1.5` 向量检索栈。规则候选回流 `editor-wisdom/rules.json` 走人工闸；live_review 病例驱动现有 `polish-agent` 修复循环。

**Tech Stack:** Python 3.11 / pytest / ruff / FAISS + BAAI/bge-small-zh-v1.5（已装）/ Anthropic SDK / PyYAML / jsonschema / claude-sonnet-4-6（默认 model）

**Source Spec:** `docs/superpowers/specs/2026-04-26-live-review-integration-design.md`（已 commit @ 611ccd1）

---

## Discovered Constraints（实施前对现有代码契约的关键发现，修正 spec 部分细节）

| 现有契约 | spec 原描述 | 修正后实施细节 |
|---|---|---|
| `schemas/case_schema.json:case_id.pattern` 当前是 `^CASE-([0-9]{4}\|LEARN\|PROMOTE)-(M[0-9]+-)?[0-9]{4}$` | spec 说 `CASE-LR-2026-NNNN` | **必须扩 pattern**：加 `\|LR` 分支让 `CASE-LR-NNNN` 与 `CASE-LR-2026-NNNN` 都能匹配，最终 pattern: `^CASE-([0-9]{4}\|LEARN\|PROMOTE\|LR)-(M[0-9]+-)?[0-9]{4}$`（保留 4-digit year 段位置可空）。**实际生成形式定为 `CASE-LR-2026-NNNN`**：传 `prefix="CASE-LR-2026-"` 给 `allocate_case_id`，输出 `CASE-LR-2026-0001` 形式。 |
| `schemas/case_schema.json:domain.enum` 当前是 `["writing_quality", "infra_health"]` | spec 说 `domain: live_review` | **扩 enum 加 `live_review`**：最终 `["writing_quality", "infra_health", "live_review"]` |
| `schemas/case_schema.json:layer.enum` 当前是 `["upstream", "downstream", "reference_gap", "infra_health"]` | spec §3.2 推导规则用 `[planning, golden_three, chapter, character]`（这些值现 schema **不接受**）| **改用现有 enum 映射**：opening/hook/golden_finger/genre/taboo/character → `[upstream]`；pacing/highpoint → `[upstream, downstream]`；simplicity → `[downstream]`；ops/misc → `[upstream]`。**不扩 layer enum**。 |
| `schemas/case_schema.json:source.type.enum` 当前是 `["editor_review", "self_audit", "regression", "infra_check"]` | spec 说 `source.type: live_review_extraction` | **不扩 enum**，复用现有 `editor_review`（语义贴合）；用 `source.ingested_from` 标记具体来自哪个 jsonl |
| `schemas/case_schema.json:additionalProperties: false` | spec 说"加 live_review_meta 可选 block" | **必须把 `live_review_meta` 显式加进 properties**（schema 严格模式不允许未声明字段） |
| `pytest.ini:testpaths` 显式列举所有目录 | spec 默认假设新建 dir 自动收录 | **US-LR-001 acceptance 必须含**：把 `tests/live_review` 追加进 testpaths（追加单词，不重排其他目录避免 diff 噪音） |
| `pytest.ini:--cov-fail-under=70` 总覆盖率门禁 | 未提 | 新模块代码全部需要测试覆盖；新文件不允许把总覆盖率拉到 70 以下 |
| `_id_alloc.py:allocate_case_id(cases_dir, prefix)` | spec 说"复用，传 prefix=CASE-LR-" | **传完整年份前缀** `prefix="CASE-LR-2026-"`；counter file 自动 `.id_alloc_case_lr_2026.cnt` |

---

## File Structure

### Files to Create

```
schemas/
├── live_review_extracted.schema.json          # jsonl 中间产物 schema
└── live_review_genre_acceptance.schema.json   # 题材聚合产物 schema

config/
└── live-review.yaml                           # 总配置

ink_writer/live_review/                        # 新模块
├── __init__.py
├── case_id.py                                 # allocate_live_review_id 薄封装
├── config.py                                  # config 加载
├── extractor.py                               # LLM 切分核心 + mock 接口
├── genre_retrieval.py                         # 语义检索器
├── init_injection.py                          # ink-init Step 99.5 入口
├── checker.py                                 # ink-review Step 3.6 入口
└── _vector_index.py                           # bge-small-zh-v1.5 索引封装（复用 editor-wisdom 模型）

scripts/live-review/
├── prompts/
│   └── extract_v1.txt                         # LLM 切分 prompt
├── extract_one.py                             # 单文件 / 多文件冒烟
├── run_batch.py                               # 全量批跑（断点续跑）
├── validate_jsonl_batch.py                    # schema 校验 + 统计报告
├── jsonl_to_cases.py                          # jsonl → CASE-LR-*.yaml
├── aggregate_genre.py                         # cases → genre_acceptance.json
├── extract_rule_candidates.py                 # jsonl → rule_candidates.json (LLM)
├── review_rule_candidates.py                  # 交互式审核 CLI
├── promote_approved_rules.py                  # 提交 approved 到 rules.json
├── build_vector_index.py                      # 构建 live_review faiss 索引
├── smoke_test.py                              # 端到端冒烟
└── check_links.py                             # md 内部链接检查（US-LR-014 用）

ink-writer/agents/
└── live-review-checker.md                     # 第 34 个 checker agent spec

data/live-review/
├── extracted/                                 # 留空目录（运行时填充）
├── sample_bvids.txt                           # §M-2 用的 5 个 BV ID 清单（实施时手挑）
└── vector_index/                              # 留空目录（§M-8 填充）

docs/
└── live-review-integration.md                 # 用户文档

tests/live_review/
├── __init__.py
├── conftest.py                                # 共享 fixture
├── fixtures/
│   ├── raw_BV12yBoBAEEn.txt                  # 真实直播稿前 200 行 + 后 200 行截取
│   ├── mock_extract_BV12yBoBAEEn.json        # 3 本小说预期输出
│   ├── mock_extract_5_files/*.json           # 5 份 mock 输出
│   ├── mock_batch/*.txt + *.json             # batch test 用
│   ├── sample_5_files.jsonl                  # jsonl_to_cases fixture
│   ├── sample_30_cases/*.yaml                # aggregate_genre fixture
│   ├── sample_chapter_violating.txt          # checker fixture
│   ├── mock_live_review_checker_response.json
│   ├── mock_rule_extract.json
│   ├── sample_rule_candidates.json
│   └── existing_rules_fixture.json           # 复制自 data/editor-wisdom/rules.json
├── test_schema_validation.py
├── test_case_id.py
├── test_config.py
├── test_extractor_mock.py
├── test_extract_one_smoke.py
├── test_extract_many.py
├── test_validate_jsonl_batch.py
├── test_run_batch.py
├── test_jsonl_to_cases.py
├── test_aggregate_genre.py
├── test_extract_rule_candidates.py
├── test_review_rule_candidates.py
├── test_promote_approved_rules.py
├── test_genre_retrieval.py
├── test_init_injection.py
├── test_skill_step_99_5.py
├── test_checker.py
├── test_review_step_3_6.py
├── test_smoke.py
└── test_docs.py

tests/case_library/
└── test_schema_backward_compat.py             # 410 份病例 schema 1.1 向后兼容
```

### Files to Modify

```
schemas/case_schema.json                       # +case_id pattern / +domain enum / +live_review_meta block
pytest.ini                                     # +tests/live_review 进 testpaths
ink-writer/skills/ink-init/SKILL.md           # +Step 99.5 调 init_injection.check_genre
ink-writer/skills/ink-review/SKILL.md         # +Step 3.6 调 live-review-checker
CLAUDE.md                                      # +live-review 模块说明（Top 3 注意事项后段）
```

---

## Task Plan

下面 14 个 Task 按 priority 严格依赖顺序排列，每 Task 末尾 `- [ ] 提交 Task N` 步骤完成后 `passes: true` 在 ralph 中可标记。任一 Task 失败时停止后续 Task。

---

### Task 1: US-LR-001 — Schema 定义 + 410 份病例向后兼容

**Files:**
- Create: `schemas/live_review_extracted.schema.json`
- Create: `schemas/live_review_genre_acceptance.schema.json`
- Modify: `schemas/case_schema.json`
- Modify: `pytest.ini` (testpaths 末尾加 `tests/live_review`)
- Create: `tests/live_review/__init__.py`（空文件）
- Create: `tests/live_review/conftest.py`
- Create: `tests/live_review/test_schema_validation.py`
- Create: `tests/case_library/test_schema_backward_compat.py`

#### Step 1: 写 `schemas/live_review_extracted.schema.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://ink-writer/live_review_extracted",
  "title": "Live Review Extracted Novel",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version", "bvid", "source_path", "source_line_total", "extracted_at",
    "model", "extractor_version", "novel_idx", "line_start", "line_end",
    "title_guess", "title_confidence", "genre_guess", "score_raw", "score_signal",
    "verdict", "overall_comment", "comments"
  ],
  "properties": {
    "schema_version": {"const": "1.0"},
    "bvid": {"type": "string", "pattern": "^BV[A-Za-z0-9]+$"},
    "source_path": {"type": "string", "minLength": 1},
    "source_line_total": {"type": "integer", "minimum": 1},
    "extracted_at": {"type": "string", "format": "date-time"},
    "model": {"type": "string"},
    "extractor_version": {"type": "string", "pattern": "^[0-9]+\\.[0-9]+\\.[0-9]+$"},
    "novel_idx": {"type": "integer", "minimum": 0},
    "line_start": {"type": "integer", "minimum": 1},
    "line_end": {"type": "integer", "minimum": 1},
    "title_guess": {"type": "string", "minLength": 1, "maxLength": 200},
    "title_confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    "genre_guess": {"type": "array", "items": {"type": "string"}, "minItems": 1},
    "score": {"type": ["integer", "null"], "minimum": 0, "maximum": 100},
    "score_raw": {"type": "string"},
    "score_signal": {"type": "string", "enum": ["explicit_number", "sign_phrase", "fuzzy", "unknown"]},
    "verdict": {"type": "string", "enum": ["pass", "fail", "borderline", "unknown"]},
    "overall_comment": {"type": "string", "minLength": 1},
    "comments": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["dimension", "severity", "content", "raw_quote", "raw_line_range"],
        "properties": {
          "dimension": {"type": "string", "enum": ["opening", "hook", "character", "pacing", "highpoint", "golden_finger", "taboo", "genre", "ops", "simplicity", "misc"]},
          "severity": {"type": "string", "enum": ["negative", "positive", "neutral"]},
          "content": {"type": "string", "minLength": 1},
          "raw_quote": {"type": "string"},
          "raw_line_range": {
            "type": "array",
            "minItems": 2,
            "maxItems": 2,
            "items": {"type": "integer", "minimum": 1}
          }
        }
      }
    }
  }
}
```

#### Step 2: 写 `schemas/live_review_genre_acceptance.schema.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://ink-writer/live_review_genre_acceptance",
  "title": "Live Review Genre Acceptance Stats",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "updated_at", "total_novels_analyzed", "min_cases_per_genre", "genres"],
  "properties": {
    "schema_version": {"const": "1.0"},
    "updated_at": {"type": "string", "format": "date-time"},
    "total_novels_analyzed": {"type": "integer", "minimum": 0},
    "min_cases_per_genre": {"type": "integer", "minimum": 1},
    "genres": {
      "type": "object",
      "additionalProperties": {
        "type": "object",
        "additionalProperties": false,
        "required": ["case_count", "score_mean", "verdict_pass_rate", "common_complaints", "case_ids"],
        "properties": {
          "case_count": {"type": "integer", "minimum": 1},
          "score_mean": {"type": ["number", "null"]},
          "score_median": {"type": ["number", "null"]},
          "score_p25": {"type": ["number", "null"]},
          "score_p75": {"type": ["number", "null"]},
          "verdict_pass_rate": {"type": "number", "minimum": 0.0, "maximum": 1.0},
          "common_complaints": {
            "type": "array",
            "items": {
              "type": "object",
              "additionalProperties": false,
              "required": ["dimension", "frequency", "examples"],
              "properties": {
                "dimension": {"type": "string"},
                "frequency": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "examples": {"type": "array", "items": {"type": "string"}}
              }
            }
          },
          "case_ids": {"type": "array", "items": {"type": "string", "pattern": "^CASE-LR-[0-9]{4}-[0-9]{4}$"}, "minItems": 1}
        }
      }
    }
  }
}
```

#### Step 3: 修改 `schemas/case_schema.json`

3 处修改（保持其他字段不动）：

```diff
   "properties": {
     "case_id": {
       "type": "string",
-      "pattern": "^CASE-([0-9]{4}|LEARN|PROMOTE)-(M[0-9]+-)?[0-9]{4}$"
+      "pattern": "^CASE-([0-9]{4}|LEARN|PROMOTE|LR)-(M[0-9]+-)?[0-9]{4}$"
     },
     "title": {"type": "string", "minLength": 1, "maxLength": 200},
     "status": {...},
     "severity": {...},
     "domain": {
       "type": "string",
-      "enum": ["writing_quality", "infra_health"]
+      "enum": ["writing_quality", "infra_health", "live_review"]
     },
     ...
+    "live_review_meta": {
+      "type": "object",
+      "additionalProperties": false,
+      "required": ["source_bvid", "source_line_range", "score_raw", "score_signal", "verdict", "title_guess", "genre_guess", "overall_comment", "comments"],
+      "properties": {
+        "source_bvid": {"type": "string", "pattern": "^BV[A-Za-z0-9]+$"},
+        "source_line_range": {"type": "array", "minItems": 2, "maxItems": 2, "items": {"type": "integer", "minimum": 1}},
+        "score": {"type": ["integer", "null"], "minimum": 0, "maximum": 100},
+        "score_raw": {"type": "string"},
+        "score_signal": {"type": "string", "enum": ["explicit_number", "sign_phrase", "fuzzy", "unknown"]},
+        "verdict": {"type": "string", "enum": ["pass", "fail", "borderline", "unknown"]},
+        "title_guess": {"type": "string", "minLength": 1, "maxLength": 200},
+        "genre_guess": {"type": "array", "items": {"type": "string"}, "minItems": 1},
+        "overall_comment": {"type": "string", "minLength": 1},
+        "comments": {
+          "type": "array",
+          "items": {
+            "type": "object",
+            "additionalProperties": false,
+            "required": ["dimension", "severity", "content"],
+            "properties": {
+              "dimension": {"type": "string"},
+              "severity": {"type": "string", "enum": ["negative", "positive", "neutral"]},
+              "content": {"type": "string"},
+              "raw_quote": {"type": "string"}
+            }
+          }
+        }
+      }
+    }
   }
```

注意：在 case_schema.json 顶层加 `"$schema_version": "1.1"` **不可行**——它是 JSON Schema spec 自有字段。改用 `"description": "schema_version 1.1: added live_review domain + live_review_meta block"` 注释方式。

#### Step 4: 修改 `pytest.ini`

```diff
 testpaths = tests/data_modules ... tests/learn tests/_compat
+testpaths = tests/data_modules ... tests/learn tests/_compat tests/live_review
```

（实操：在 testpaths 行末尾追加 ` tests/live_review`，不动其他）

#### Step 5: 写 `tests/live_review/__init__.py`

空文件。

#### Step 6: 写 `tests/live_review/conftest.py`

```python
"""共享 fixtures for live_review tests."""
from __future__ import annotations
import json
from pathlib import Path
import pytest


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def schemas_dir() -> Path:
    return Path(__file__).parents[2] / "schemas"


@pytest.fixture
def load_schema(schemas_dir):
    def _load(name: str) -> dict:
        with open(schemas_dir / name, encoding="utf-8") as f:
            return json.load(f)
    return _load
```

#### Step 7: 写 `tests/live_review/test_schema_validation.py`

```python
"""US-LR-001: live_review_extracted + genre_acceptance schemas valid."""
from __future__ import annotations
import json
import pytest
from jsonschema import Draft202012Validator, ValidationError


def test_extracted_schema_self_valid(load_schema):
    schema = load_schema("live_review_extracted.schema.json")
    Draft202012Validator.check_schema(schema)


def test_genre_acceptance_schema_self_valid(load_schema):
    schema = load_schema("live_review_genre_acceptance.schema.json")
    Draft202012Validator.check_schema(schema)


def _minimal_extracted() -> dict:
    return {
        "schema_version": "1.0",
        "bvid": "BV12yBoBAEEn",
        "source_path": "/tmp/raw.txt",
        "source_line_total": 1000,
        "extracted_at": "2026-04-27T10:00:00Z",
        "model": "claude-sonnet-4-6",
        "extractor_version": "1.0.0",
        "novel_idx": 0,
        "line_start": 100,
        "line_end": 200,
        "title_guess": "都市重生律师文",
        "title_confidence": 0.7,
        "genre_guess": ["都市"],
        "score": 68,
        "score_raw": "68 吧是吧",
        "score_signal": "explicit_number",
        "verdict": "borderline",
        "overall_comment": "节奏不错但金手指出现太晚",
        "comments": [
            {
                "dimension": "pacing",
                "severity": "negative",
                "content": "开篇拖沓",
                "raw_quote": "拖沓兄弟",
                "raw_line_range": [110, 117],
            }
        ],
    }


def test_extracted_minimal_valid(load_schema):
    Draft202012Validator(load_schema("live_review_extracted.schema.json")).validate(_minimal_extracted())


def test_extracted_score_null_allowed(load_schema):
    data = _minimal_extracted()
    data["score"] = None
    data["score_signal"] = "unknown"
    data["verdict"] = "unknown"
    Draft202012Validator(load_schema("live_review_extracted.schema.json")).validate(data)


def test_extracted_invalid_dimension_rejected(load_schema):
    data = _minimal_extracted()
    data["comments"][0]["dimension"] = "not_a_real_dim"
    with pytest.raises(ValidationError):
        Draft202012Validator(load_schema("live_review_extracted.schema.json")).validate(data)


def test_extracted_score_out_of_range_rejected(load_schema):
    data = _minimal_extracted()
    data["score"] = 200
    with pytest.raises(ValidationError):
        Draft202012Validator(load_schema("live_review_extracted.schema.json")).validate(data)


def test_extracted_unknown_top_field_rejected(load_schema):
    data = _minimal_extracted()
    data["foo"] = "bar"
    with pytest.raises(ValidationError):
        Draft202012Validator(load_schema("live_review_extracted.schema.json")).validate(data)


def _minimal_genre_acceptance() -> dict:
    return {
        "schema_version": "1.0",
        "updated_at": "2026-04-27T10:00:00Z",
        "total_novels_analyzed": 1500,
        "min_cases_per_genre": 3,
        "genres": {
            "都市": {
                "case_count": 5,
                "score_mean": 65.0,
                "verdict_pass_rate": 0.6,
                "common_complaints": [],
                "case_ids": ["CASE-LR-2026-0001"],
            }
        },
    }


def test_genre_acceptance_minimal_valid(load_schema):
    Draft202012Validator(load_schema("live_review_genre_acceptance.schema.json")).validate(_minimal_genre_acceptance())


def test_genre_acceptance_invalid_case_id_rejected(load_schema):
    data = _minimal_genre_acceptance()
    data["genres"]["都市"]["case_ids"] = ["CASE-2026-0001"]  # 非 CASE-LR- 前缀
    with pytest.raises(ValidationError):
        Draft202012Validator(load_schema("live_review_genre_acceptance.schema.json")).validate(data)
```

#### Step 8: 写 `tests/case_library/test_schema_backward_compat.py`

```python
"""US-LR-001: case_schema.json bump 1.0→1.1 后，全部 410+ 现存 case yaml 仍解析通过。"""
from __future__ import annotations
import json
from pathlib import Path
import pytest
import yaml
from jsonschema import Draft202012Validator, ValidationError


REPO_ROOT = Path(__file__).parents[2]
CASES_DIR = REPO_ROOT / "data" / "case_library" / "cases"
SCHEMA_PATH = REPO_ROOT / "schemas" / "case_schema.json"


@pytest.fixture(scope="module")
def case_validator():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _iter_case_files():
    if not CASES_DIR.exists():
        return
    for path in sorted(CASES_DIR.rglob("*.yaml")):
        if path.name.startswith("."):
            continue  # 跳 hidden / counter file
        yield path


def test_all_existing_cases_still_validate(case_validator):
    """遍历全部存在的 yaml，schema 1.1 须严格全过。"""
    failures = []
    count = 0
    for path in _iter_case_files():
        count += 1
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            failures.append(f"{path.name}: YAML parse error: {e}")
            continue
        if data is None:
            failures.append(f"{path.name}: empty yaml")
            continue
        errors = list(case_validator.iter_errors(data))
        if errors:
            failures.append(f"{path.name}: {[e.message for e in errors[:3]]}")
    assert count > 0, f"no case yaml found under {CASES_DIR}"
    assert not failures, f"{len(failures)}/{count} cases failed schema 1.1 validation:\n" + "\n".join(failures[:20])


def test_new_live_review_case_validates(case_validator):
    """新增 schema 1.1 字段的 sample 病例须通过。"""
    sample = {
        "case_id": "CASE-LR-2026-0001",
        "title": "都市/重生/律师 (borderline / 68分)",
        "status": "active",
        "severity": "P2",
        "domain": "live_review",
        "layer": ["upstream"],
        "tags": ["live_review", "都市"],
        "scope": {"genre": ["都市"], "trigger": "投稿前 3 章被星河审稿"},
        "source": {
            "type": "editor_review",
            "raw_text": "68 吧是吧 / 设定太复杂",
            "ingested_at": "2026-04-27",
            "ingested_from": "data/live-review/extracted/BV12yBoBAEEn.jsonl",
        },
        "failure_pattern": {
            "description": "开篇 800 字铺设定，金手指第 5 章才出，节奏拖沓",
            "observable": ["前 800 字无核心冲突", "金手指出场超过 3 章"],
        },
        "live_review_meta": {
            "source_bvid": "BV12yBoBAEEn",
            "source_line_range": [105, 192],
            "score": 68,
            "score_raw": "68 吧是吧",
            "score_signal": "explicit_number",
            "verdict": "borderline",
            "title_guess": "都市重生律师文",
            "genre_guess": ["都市", "重生"],
            "overall_comment": "节奏不错但金手指出现太晚",
            "comments": [
                {"dimension": "pacing", "severity": "negative", "content": "开篇拖沓"}
            ],
        },
    }
    errs = list(case_validator.iter_errors(sample))
    assert not errs, [e.message for e in errs]


def test_invalid_domain_still_rejected(case_validator):
    """domain enum 之外的值仍应被拒绝（防止过度宽松）。"""
    sample = {
        "case_id": "CASE-2026-0001", "title": "x", "status": "active", "severity": "P0",
        "domain": "totally_made_up_domain", "layer": ["upstream"], "tags": [],
        "scope": {}, "source": {"type": "self_audit", "raw_text": "x", "ingested_at": "2026-04-27"},
        "failure_pattern": {"description": "x", "observable": ["x"]},
    }
    errs = list(case_validator.iter_errors(sample))
    assert any("domain" in str(e.path) or "live_review" in e.message for e in errs)
```

#### Step 9: 跑测试验证全过

```bash
python3 -m pytest tests/live_review/test_schema_validation.py tests/case_library/test_schema_backward_compat.py --no-cov -q
```

预期：3 + 2 + 1 = 全 PASS

#### Step 10: 跑 ruff 检查

```bash
ruff check schemas/ tests/live_review/ tests/case_library/test_schema_backward_compat.py
```

预期：无新增错误

#### Step 11: 提交 Task 1

```bash
git add schemas/ pytest.ini tests/live_review/ tests/case_library/test_schema_backward_compat.py
git commit -m "feat: US-LR-001 - schema 定义 + 410 份病例向后兼容

- 新建 schemas/live_review_extracted.schema.json (jsonl 中间产物)
- 新建 schemas/live_review_genre_acceptance.schema.json (题材聚合)
- case_schema.json: case_id pattern 加 |LR 分支；domain enum 加 live_review；
  增加可选 live_review_meta block (含 source_bvid/score/comments 等 9 字段)
- pytest.ini testpaths 末尾加 tests/live_review
- 新增 tests/live_review/conftest.py + test_schema_validation.py (9 用例)
- 新增 tests/case_library/test_schema_backward_compat.py (3 用例 — 遍历 410+ 份)"
```

---

### Task 2: US-LR-002 — ID 分配器封装 + 配置文件

**Files:**
- Create: `ink_writer/live_review/__init__.py`
- Create: `ink_writer/live_review/case_id.py`
- Create: `ink_writer/live_review/config.py`
- Create: `config/live-review.yaml`
- Create: `tests/live_review/test_case_id.py`
- Create: `tests/live_review/test_config.py`

#### Step 1: 写 `ink_writer/live_review/__init__.py`

```python
"""Live-Review 模块 — 174 份星河直播稿融入 ink-writer 创作链路。

详见 docs/superpowers/specs/2026-04-26-live-review-integration-design.md。
"""
```

#### Step 2: 写 `ink_writer/live_review/case_id.py`

```python
"""Live-review 病例 ID 分配（薄封装于 case_library._id_alloc.allocate_case_id）。"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path

from ink_writer.case_library._id_alloc import allocate_case_id

_DEFAULT_PREFIX_TEMPLATE = "CASE-LR-{year}-"


def allocate_live_review_id(cases_dir: Path, year: int | None = None) -> str:
    """分配下一个 ``CASE-LR-{year}-NNNN`` 病例 ID。

    Args:
        cases_dir: 病例 yaml 写盘目标目录（实际是 ``data/case_library/cases/live_review``）。
        year: 4 位年份；None 时取当前 UTC 年。

    底层复用 ``case_library._id_alloc.allocate_case_id``，counter file 路径
    形如 ``cases_dir/.id_alloc_case_lr_2026.cnt``，与现有 ``CASE-`` / ``CASE-LEARN-``
    / ``CASE-PROMOTE-`` 自动隔离不串号。
    """
    if year is None:
        year = datetime.utcnow().year
    prefix = _DEFAULT_PREFIX_TEMPLATE.format(year=year)
    return allocate_case_id(cases_dir, prefix=prefix)


__all__ = ["allocate_live_review_id"]
```

#### Step 3: 写 `config/live-review.yaml`

```yaml
# Live-Review 模块配置（174 份星河直播稿融入 ink-writer 创作链路）
# Spec: docs/superpowers/specs/2026-04-26-live-review-integration-design.md
enabled: true
model: claude-sonnet-4-6
extractor_version: "1.0.0"

batch:
  input_dir: "~/Desktop/星河审稿"
  output_dir: "data/live-review/extracted"
  resume_from_jsonl: true
  skip_failed: true
  log_progress: true

# review 门禁
hard_gate_threshold: 0.65
golden_three_threshold: 0.75

# init 注入
init_genre_warning_threshold: 60
init_top_k: 3

# 聚合
min_cases_per_genre: 3

# 注入开关（独立可关）
inject_into:
  init: true
  review: true
```

#### Step 4: 写 `ink_writer/live_review/config.py`

```python
"""Live-review 配置加载（带默认值 fallback + enabled=false 强制 inject_into 全 false）。"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


_DEFAULT_CONFIG_PATH = Path("config/live-review.yaml")


@dataclass(frozen=True)
class BatchConfig:
    input_dir: str = "~/Desktop/星河审稿"
    output_dir: str = "data/live-review/extracted"
    resume_from_jsonl: bool = True
    skip_failed: bool = True
    log_progress: bool = True


@dataclass(frozen=True)
class InjectConfig:
    init: bool = True
    review: bool = True


@dataclass(frozen=True)
class LiveReviewConfig:
    enabled: bool = True
    model: str = "claude-sonnet-4-6"
    extractor_version: str = "1.0.0"
    batch: BatchConfig = field(default_factory=BatchConfig)
    hard_gate_threshold: float = 0.65
    golden_three_threshold: float = 0.75
    init_genre_warning_threshold: int = 60
    init_top_k: int = 3
    min_cases_per_genre: int = 3
    inject_into: InjectConfig = field(default_factory=InjectConfig)


def load_config(path: Path | None = None) -> LiveReviewConfig:
    """从 yaml 加载配置；缺字段走默认；enabled=false 强制 inject_into 全 false。"""
    p = path if path is not None else _DEFAULT_CONFIG_PATH
    if not p.exists():
        return LiveReviewConfig()
    raw: dict[str, Any] = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    batch_raw = raw.get("batch", {}) or {}
    inject_raw = raw.get("inject_into", {}) or {}
    enabled = bool(raw.get("enabled", True))
    inject = InjectConfig(
        init=bool(inject_raw.get("init", True)) and enabled,
        review=bool(inject_raw.get("review", True)) and enabled,
    )
    return LiveReviewConfig(
        enabled=enabled,
        model=str(raw.get("model", "claude-sonnet-4-6")),
        extractor_version=str(raw.get("extractor_version", "1.0.0")),
        batch=BatchConfig(
            input_dir=str(batch_raw.get("input_dir", "~/Desktop/星河审稿")),
            output_dir=str(batch_raw.get("output_dir", "data/live-review/extracted")),
            resume_from_jsonl=bool(batch_raw.get("resume_from_jsonl", True)),
            skip_failed=bool(batch_raw.get("skip_failed", True)),
            log_progress=bool(batch_raw.get("log_progress", True)),
        ),
        hard_gate_threshold=float(raw.get("hard_gate_threshold", 0.65)),
        golden_three_threshold=float(raw.get("golden_three_threshold", 0.75)),
        init_genre_warning_threshold=int(raw.get("init_genre_warning_threshold", 60)),
        init_top_k=int(raw.get("init_top_k", 3)),
        min_cases_per_genre=int(raw.get("min_cases_per_genre", 3)),
        inject_into=inject,
    )


__all__ = ["LiveReviewConfig", "BatchConfig", "InjectConfig", "load_config"]
```

#### Step 5: 写 `tests/live_review/test_case_id.py`

```python
"""US-LR-002: live_review case ID 分配 — prefix 隔离 + 并发安全。"""
from __future__ import annotations
import multiprocessing as mp
from pathlib import Path

import pytest

from ink_writer.live_review.case_id import allocate_live_review_id
from ink_writer.case_library._id_alloc import allocate_case_id


def _alloc_worker(cases_dir_str: str, year: int) -> str:
    return allocate_live_review_id(Path(cases_dir_str), year=year)


def test_basic_allocate_format(tmp_path):
    cid = allocate_live_review_id(tmp_path, year=2026)
    assert cid == "CASE-LR-2026-0001"


def test_sequential_allocate_increment(tmp_path):
    ids = [allocate_live_review_id(tmp_path, year=2026) for _ in range(3)]
    assert ids == ["CASE-LR-2026-0001", "CASE-LR-2026-0002", "CASE-LR-2026-0003"]


def test_concurrent_allocate_no_gap(tmp_path):
    """4 worker spawn 同时分配，序列严格 0001..0004 无空洞。"""
    ctx = mp.get_context("spawn")
    with ctx.Pool(processes=4) as pool:
        ids = pool.starmap(_alloc_worker, [(str(tmp_path), 2026)] * 4)
    assert sorted(ids) == ["CASE-LR-2026-0001", "CASE-LR-2026-0002", "CASE-LR-2026-0003", "CASE-LR-2026-0004"]


def test_prefix_isolation_with_legacy_case_alloc(tmp_path):
    """同进程交替分配 CASE-LR- 与 CASE- 不串号；counter file 各自隔离。"""
    lr1 = allocate_live_review_id(tmp_path, year=2026)
    case1 = allocate_case_id(tmp_path, prefix="CASE-2026-")
    lr2 = allocate_live_review_id(tmp_path, year=2026)
    case2 = allocate_case_id(tmp_path, prefix="CASE-2026-")
    assert lr1 == "CASE-LR-2026-0001"
    assert lr2 == "CASE-LR-2026-0002"
    assert case1 == "CASE-2026-0001"
    assert case2 == "CASE-2026-0002"
    # counter files 各自存在
    assert (tmp_path / ".id_alloc_case_lr_2026.cnt").exists()
    assert (tmp_path / ".id_alloc_case_2026.cnt").exists()


def test_year_isolation(tmp_path):
    """不同年份 prefix 各自隔离 counter。"""
    a = allocate_live_review_id(tmp_path, year=2026)
    b = allocate_live_review_id(tmp_path, year=2027)
    assert a == "CASE-LR-2026-0001"
    assert b == "CASE-LR-2027-0001"
```

#### Step 6: 写 `tests/live_review/test_config.py`

```python
"""US-LR-002: live-review.yaml 配置加载。"""
from __future__ import annotations
from pathlib import Path

import pytest

from ink_writer.live_review.config import load_config, LiveReviewConfig


def test_load_default_when_missing(tmp_path):
    cfg = load_config(tmp_path / "nonexistent.yaml")
    assert cfg.enabled is True
    assert cfg.model == "claude-sonnet-4-6"
    assert cfg.hard_gate_threshold == 0.65
    assert cfg.batch.resume_from_jsonl is True
    assert cfg.inject_into.init is True


def test_load_full_yaml(tmp_path):
    p = tmp_path / "lr.yaml"
    p.write_text(
        "enabled: true\n"
        "model: claude-haiku-4-5\n"
        "hard_gate_threshold: 0.70\n"
        "init_top_k: 5\n"
        "batch:\n  resume_from_jsonl: false\n",
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg.model == "claude-haiku-4-5"
    assert cfg.hard_gate_threshold == 0.70
    assert cfg.init_top_k == 5
    assert cfg.batch.resume_from_jsonl is False
    # 未提供字段回落默认
    assert cfg.batch.skip_failed is True
    assert cfg.golden_three_threshold == 0.75


def test_disabled_forces_inject_false(tmp_path):
    """enabled=false 时 inject_into.init/review 强制 false 即使 yaml 写 true。"""
    p = tmp_path / "lr.yaml"
    p.write_text(
        "enabled: false\n"
        "inject_into:\n  init: true\n  review: true\n",
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg.enabled is False
    assert cfg.inject_into.init is False
    assert cfg.inject_into.review is False


def test_partial_yaml_falls_through_defaults(tmp_path):
    """缺字段全部回落默认值，不抛 KeyError。"""
    p = tmp_path / "lr.yaml"
    p.write_text("model: custom-model\n", encoding="utf-8")
    cfg = load_config(p)
    assert cfg.model == "custom-model"
    assert cfg.hard_gate_threshold == 0.65
    assert cfg.batch.input_dir == "~/Desktop/星河审稿"


def test_real_config_file_loads():
    """实际 config/live-review.yaml 应能成功加载（实施时已写）。"""
    cfg = load_config(Path("config/live-review.yaml"))
    assert isinstance(cfg, LiveReviewConfig)
    assert cfg.enabled is True
```

#### Step 7: 跑测试验证全过

```bash
python3 -m pytest tests/live_review/test_case_id.py tests/live_review/test_config.py --no-cov -q
```

预期：5 + 5 = 10 PASS

#### Step 8: 跑 ruff

```bash
ruff check ink_writer/live_review/ tests/live_review/test_case_id.py tests/live_review/test_config.py
```

预期：无新增错误

#### Step 9: 提交 Task 2

```bash
git add ink_writer/live_review/__init__.py ink_writer/live_review/case_id.py ink_writer/live_review/config.py config/live-review.yaml tests/live_review/test_case_id.py tests/live_review/test_config.py
git commit -m "feat: US-LR-002 - ID 分配器封装 + 配置文件

- ink_writer/live_review/case_id.py: allocate_live_review_id (薄封装 _id_alloc)
- ink_writer/live_review/config.py: dataclass-based config + enabled=false 强制
  inject_into 全 false 语义
- config/live-review.yaml: 默认配置（Sonnet 4.6 + 阈值 0.65/0.75 + min_cases 3）
- tests: 10 用例（4 worker spawn 并发 + prefix 隔离 + 年份隔离 + config 默认/覆盖/disabled 强制）"
```

---

### Task 3: US-LR-003 — LLM 切分 prompt + extractor + mock 单测

**Files:**
- Create: `scripts/live-review/prompts/extract_v1.txt`
- Create: `ink_writer/live_review/extractor.py`
- Create: `tests/live_review/fixtures/raw_BV12yBoBAEEn.txt`（截取真实直播稿）
- Create: `tests/live_review/fixtures/mock_extract_BV12yBoBAEEn.json`（手编 3 本预期）
- Create: `tests/live_review/test_extractor_mock.py`

#### Step 1: 写 `scripts/live-review/prompts/extract_v1.txt`

```text
你是起点中文网编辑星河直播审稿数据的结构化抽取助手。

输入：一份 B 站直播录像字幕文本（口语化短句、无段落分隔，3.5 小时长度，
含 10+ 篇小说投稿的逐稿点评 + 打分 + 写邮件回复）。

任务：按"每本被点评的小说一个对象"切分该字幕文本，识别每本小说的：
1. 起止行号（line_start / line_end，1-based 含端点）
2. 标题/题材猜测（title_guess / genre_guess）
3. 评分（score 0-100，找不到明确数值则 null）
4. 评分原话（score_raw）+ 评分信号类型（score_signal）
5. 综合判定（verdict: pass=>=60 / fail=<60 / borderline=55-65 / unknown）
6. 整体评价（overall_comment 1-3 句）
7. 维度点评数组（comments，每条含 dimension/severity/content/raw_quote/raw_line_range）

输出格式：严格 JSON Array（不带任何 markdown 代码块包裹），元素 schema 见下方
schemas/live_review_extracted.schema.json 描述。

切分启发式（按重要性）：
- 主播说"下一篇"/"下一本"/"OK 下一个"/"先看下一个"/"邮件标题是 X"/"投稿作品 N" → 切边界
- 提到新书名 / 新题材 / 新主角名 → 通常切边界
- 主播读一段后立刻吐槽切换 → 跟前一本同段
- 含明确分数（"68 分"/"70+"）通常出现在某本结尾

score_signal 判定：
- "68 分" / "70 分以上" → explicit_number
- "可以签约" / "一眼签约" / "不能签约" → sign_phrase
- "实力还行" / "再写写看" / "可以再加把劲" → fuzzy
- 全程没说分数 → unknown

dimension 严格枚举：opening / hook / character / pacing / highpoint /
golden_finger / taboo / genre / ops / simplicity / misc

severity 严格枚举：negative / positive / neutral

few-shot 示例：
（此处实施时填入 5 个 few-shot — 切分边界识别 / 标题识别 / 打分识别 /
维度归类 / 模糊场景，每个示例长 30-80 行；ralph 实施时可直接基于 spec §1.2
sample 数据 BV11YFEzkEVu/BV12yBoBAEEn 真实片段编写）

特别注意：
- 输出**纯 JSON**，不含 ```json``` 代码块
- bvid / source_path / extracted_at / model / extractor_version / source_line_total
  字段由调用方注入，你不必填
- novel_idx 从 0 开始递增
- title_confidence 0.0-1.0，确定标题给 0.9，"应该是个律师文"这类只猜到题材的给 0.4
- raw_line_range 必须落在 [line_start, line_end] 区间内
```

注：实施时 5 个 few-shot 例子可基于 `~/Desktop/星河审稿/BV12yBoBAEEn_raw.txt` 等真实样本手工编写。**必填**——不可留 placeholder。

#### Step 2: 写 `ink_writer/live_review/extractor.py`

```python
"""LLM 切分核心 — 抽取直播稿为结构化小说点评。"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

_PROMPT_PATH = Path("scripts/live-review/prompts/extract_v1.txt")
_SCHEMA_PATH = Path("schemas/live_review_extracted.schema.json")


class ExtractionError(Exception):
    """LLM 输出不合法 / 解析失败 / schema 校验失败。"""


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _load_schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def _build_record(
    bvid: str,
    source_path: str,
    source_line_total: int,
    model: str,
    extractor_version: str,
    novel: dict,
) -> dict:
    """合并 LLM 返回的 novel 对象与调用方上下文为完整 jsonl 记录。"""
    return {
        "schema_version": "1.0",
        "bvid": bvid,
        "source_path": source_path,
        "source_line_total": source_line_total,
        "extracted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": model,
        "extractor_version": extractor_version,
        **novel,  # novel_idx / line_start / line_end / title_guess / ... / comments
    }


def extract_from_text(
    raw_text: str,
    bvid: str,
    source_path: str,
    *,
    model: str = "claude-sonnet-4-6",
    extractor_version: str = "1.0.0",
    mock_response: list[dict] | None = None,
    llm_call=None,
) -> list[dict]:
    """从直播稿文本抽取结构化小说点评列表。

    Args:
        raw_text: 直播稿全文。
        bvid: B 站视频 ID（从文件名 ``BV*_raw.txt`` 提取）。
        source_path: 原文件绝对路径（写入 jsonl 字段）。
        model: LLM model id。
        extractor_version: 调用方版本（写入 jsonl）。
        mock_response: 测试用 — 直接以此为 LLM 输出，跳过真实调用。
        llm_call: 测试用 — 注入自定义 LLM 调用函数 ``f(prompt, raw_text, model) -> str``。
                  默认为 None 时调用 anthropic SDK；mock_response 不为 None 时忽略此参数。

    Returns:
        list of jsonl record dict；每个对应一本被点评小说。

    Raises:
        ExtractionError: LLM 输出非 JSON / 缺字段 / schema 校验失败。
    """
    source_line_total = raw_text.count("\n") + 1

    if mock_response is not None:
        novels = mock_response
    elif llm_call is not None:
        prompt = _load_prompt()
        try:
            output = llm_call(prompt, raw_text, model)
            novels = json.loads(output)
        except json.JSONDecodeError as e:
            raise ExtractionError(f"LLM output is not valid JSON: {e}") from e
        except Exception as e:
            raise ExtractionError(f"LLM call failed: {e}") from e
    else:
        # 真实 anthropic 调用 — 实施时填入
        try:
            import anthropic
        except ImportError as e:
            raise ExtractionError("anthropic SDK not installed; install or pass mock_response") from e
        prompt = _load_prompt()
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=model,
            max_tokens=64000,
            messages=[{"role": "user", "content": f"{prompt}\n\n=== 直播稿全文 ===\n{raw_text}"}],
        )
        text = resp.content[0].text  # type: ignore[attr-defined]
        try:
            novels = json.loads(text)
        except json.JSONDecodeError as e:
            raise ExtractionError(f"LLM output is not valid JSON: {e}\nText preview: {text[:200]}") from e

    if not isinstance(novels, list):
        raise ExtractionError(f"Expected JSON array, got {type(novels).__name__}")

    schema = _load_schema()
    validator = Draft202012Validator(schema)
    records = []
    for i, novel in enumerate(novels):
        record = _build_record(bvid, source_path, source_line_total, model, extractor_version, novel)
        errors = list(validator.iter_errors(record))
        if errors:
            raise ExtractionError(
                f"novel #{i} (title={novel.get('title_guess', '?')!r}) failed schema: "
                f"{[e.message for e in errors[:3]]}"
            )
        records.append(record)
    return records


__all__ = ["extract_from_text", "ExtractionError"]
```

#### Step 3: 写 `tests/live_review/fixtures/raw_BV12yBoBAEEn.txt`

实施时**截取真实直播稿前 200 行 + 后 200 行**：

```bash
head -200 ~/Desktop/星河审稿/BV12yBoBAEEn_raw.txt > /tmp/head.txt
tail -200 ~/Desktop/星河审稿/BV12yBoBAEEn_raw.txt > /tmp/tail.txt
cat /tmp/head.txt <(echo '...（中略）...') /tmp/tail.txt > tests/live_review/fixtures/raw_BV12yBoBAEEn.txt
```

（注：fixture 文件可作为二进制资产 commit；不需要 schema 校验本身）

#### Step 4: 写 `tests/live_review/fixtures/mock_extract_BV12yBoBAEEn.json`

```json
[
  {
    "novel_idx": 0,
    "line_start": 5,
    "line_end": 100,
    "title_guess": "都市重生律师文",
    "title_confidence": 0.7,
    "genre_guess": ["都市", "重生", "职业流"],
    "score": 68,
    "score_raw": "68 吧是吧",
    "score_signal": "explicit_number",
    "verdict": "borderline",
    "overall_comment": "拉扯部分写得不错但金手指出现太晚，设定堆积过密",
    "comments": [
      {"dimension": "pacing", "severity": "negative", "content": "前 800 字铺设定，拖沓", "raw_quote": "我觉得拖沓兄弟", "raw_line_range": [10, 15]},
      {"dimension": "golden_finger", "severity": "negative", "content": "金手指第 5 章才出", "raw_quote": "他后面那些设定我怕还是写的太复杂", "raw_line_range": [78, 82]},
      {"dimension": "character", "severity": "positive", "content": "拉扯写得有水平", "raw_quote": "拉扯大概的拉扯水平很高", "raw_line_range": [50, 53]}
    ]
  },
  {
    "novel_idx": 1,
    "line_start": 105,
    "line_end": 250,
    "title_guess": "校园甜宠题材",
    "title_confidence": 0.5,
    "genre_guess": ["校园", "甜宠"],
    "score": null,
    "score_raw": "我知道我不能签约",
    "score_signal": "sign_phrase",
    "verdict": "fail",
    "overall_comment": "题材选择有问题，这种很少签",
    "comments": [
      {"dimension": "genre", "severity": "negative", "content": "校园甜宠在星河直播投稿池接受度低", "raw_quote": "我很少签这种设定类的书啊", "raw_line_range": [110, 115]}
    ]
  },
  {
    "novel_idx": 2,
    "line_start": 260,
    "line_end": 380,
    "title_guess": "无敌流玄幻",
    "title_confidence": 0.8,
    "genre_guess": ["玄幻", "无敌流"],
    "score": null,
    "score_raw": "实力还行，可以再写写",
    "score_signal": "fuzzy",
    "verdict": "unknown",
    "overall_comment": "实力够但需要打磨开头节奏",
    "comments": [
      {"dimension": "opening", "severity": "negative", "content": "开篇 200 字应见冲突", "raw_quote": "开头要快一点", "raw_line_range": [265, 270]}
    ]
  }
]
```

#### Step 5: 写 `tests/live_review/test_extractor_mock.py`

```python
"""US-LR-003: LLM extractor — mock 模式 + 错误路径覆盖。"""
from __future__ import annotations
import json
from pathlib import Path

import pytest

from ink_writer.live_review.extractor import extract_from_text, ExtractionError


def _load_mock(fixtures_dir: Path) -> list[dict]:
    return json.loads((fixtures_dir / "mock_extract_BV12yBoBAEEn.json").read_text(encoding="utf-8"))


def test_extract_with_mock_returns_3_records(fixtures_dir):
    raw = (fixtures_dir / "raw_BV12yBoBAEEn.txt").read_text(encoding="utf-8")
    mock = _load_mock(fixtures_dir)
    records = extract_from_text(
        raw,
        bvid="BV12yBoBAEEn",
        source_path="/tmp/raw.txt",
        mock_response=mock,
    )
    assert len(records) == 3
    assert all(r["bvid"] == "BV12yBoBAEEn" for r in records)
    assert all(r["schema_version"] == "1.0" for r in records)


def test_extract_records_have_full_metadata(fixtures_dir):
    raw = (fixtures_dir / "raw_BV12yBoBAEEn.txt").read_text(encoding="utf-8")
    mock = _load_mock(fixtures_dir)
    records = extract_from_text(
        raw,
        bvid="BV12yBoBAEEn",
        source_path="/abs/path",
        model="claude-sonnet-4-6",
        extractor_version="1.0.0",
        mock_response=mock,
    )
    for r in records:
        assert r["model"] == "claude-sonnet-4-6"
        assert r["extractor_version"] == "1.0.0"
        assert r["source_path"] == "/abs/path"
        assert "extracted_at" in r and r["extracted_at"].endswith("Z")


def test_extract_records_score_signal_diversity(fixtures_dir):
    """fixture 故意覆盖 explicit_number / sign_phrase / fuzzy 三类。"""
    raw = (fixtures_dir / "raw_BV12yBoBAEEn.txt").read_text(encoding="utf-8")
    records = extract_from_text(raw, bvid="BV12yBoBAEEn", source_path="/x", mock_response=_load_mock(fixtures_dir))
    signals = {r["score_signal"] for r in records}
    assert signals == {"explicit_number", "sign_phrase", "fuzzy"}


def test_extract_invalid_json_raises(fixtures_dir):
    """LLM 返回非 JSON 必须 fail-loud，不 silent fallback。"""
    raw = "x"

    def bad_llm(prompt, text, model):
        return "this is not json {{{ broken"

    with pytest.raises(ExtractionError, match="not valid JSON"):
        extract_from_text(raw, bvid="BV1x", source_path="/x", llm_call=bad_llm)


def test_extract_non_array_raises(fixtures_dir):
    raw = "x"

    def bad_llm(prompt, text, model):
        return '{"not": "an array"}'

    with pytest.raises(ExtractionError, match="Expected JSON array"):
        extract_from_text(raw, bvid="BV1x", source_path="/x", llm_call=bad_llm)


def test_extract_schema_violation_raises(fixtures_dir):
    """LLM 漏字段必须 fail-loud。"""
    raw = "x"

    def bad_llm(prompt, text, model):
        return json.dumps([{
            "novel_idx": 0,
            # 缺 line_start / line_end / title_guess / ...
        }])

    with pytest.raises(ExtractionError, match="failed schema"):
        extract_from_text(raw, bvid="BV1x", source_path="/x", llm_call=bad_llm)


def test_extract_score_out_of_range_raises(fixtures_dir):
    raw = "x"

    def bad_llm(prompt, text, model):
        return json.dumps([{
            "novel_idx": 0, "line_start": 1, "line_end": 10,
            "title_guess": "x", "title_confidence": 0.5, "genre_guess": ["x"],
            "score": 999, "score_raw": "x", "score_signal": "explicit_number",
            "verdict": "pass", "overall_comment": "x", "comments": [],
        }])

    with pytest.raises(ExtractionError, match="failed schema"):
        extract_from_text(raw, bvid="BV1x", source_path="/x", llm_call=bad_llm)
```

#### Step 6: 跑测试

```bash
python3 -m pytest tests/live_review/test_extractor_mock.py --no-cov -q
```

预期：7 PASS

#### Step 7: 跑 ruff

```bash
ruff check ink_writer/live_review/extractor.py tests/live_review/test_extractor_mock.py
```

#### Step 8: 提交 Task 3

```bash
git add scripts/live-review/prompts/extract_v1.txt ink_writer/live_review/extractor.py tests/live_review/fixtures/raw_BV12yBoBAEEn.txt tests/live_review/fixtures/mock_extract_BV12yBoBAEEn.json tests/live_review/test_extractor_mock.py
git commit -m "feat: US-LR-003 - LLM 切分 prompt + extractor + mock 单测

- scripts/live-review/prompts/extract_v1.txt: 含 schema 描述 + 5 个 few-shot
- ink_writer/live_review/extractor.py: extract_from_text() 支持 mock_response/
  llm_call 注入；fail-loud 三种异常（非 JSON / 非 Array / schema 违反）
- fixtures: raw_BV12yBoBAEEn.txt (前 200 + 后 200 行截取) + mock_extract.json
  (3 本小说覆盖 3 类 score_signal)
- tests: 7 用例（mock 跑通 / 元数据注入 / 信号多样性 / 4 类异常 fail-loud）"
```

---

### Task 4 ~ 14：剩余 11 个 US

由于篇幅限制，以下 Task 4-14 采用**紧凑骨架格式**（每 Task 含完整 Files / 关键代码片段 / 测试用例 / 提交命令）。每 Task 仍遵循 TDD 5 步：写测试 → 验失败 → 写实现 → 验通过 → commit。

**实施时 ralph 应展开每 Task 内每步的具体代码** — 该展开严格基于：
1. spec §5 中对应 US 的 acceptance criteria（已机器可验）
2. spec §3 中对应 schema 字段
3. 本 plan 已展开的 Task 1-3 代码风格

---

### Task 4: US-LR-004 — 单文件冒烟脚本 extract_one.py

**Files:**
- Create: `scripts/live-review/extract_one.py`
- Create: `tests/live_review/test_extract_one_smoke.py`

**关键实现要点:**
- argparse 参数: `--bvid` / `--input` / `--out` / `--model` / `--mock-llm <fixture.json>`
- 主流程：读 raw.txt → 调 `extractor.extract_from_text(raw, bvid, source_path, mock_response=load(mock_llm) if mock_llm else None)` → 写 jsonl（一行一 record）
- bvid 默认从 `--input` 文件名正则提取：`re.match(r'^(BV[\w]+)_raw\.txt$', basename)`
- 退出码：成功 0 / extractor 异常 1 / 文件不存在 2

**关键测试用例:**
1. `test_extract_one_with_mock_creates_jsonl`：用 `--mock-llm fixtures/mock_extract_BV12yBoBAEEn.json` 跑 → assert jsonl 文件存在 + 3 行 + 全 schema 校验通过
2. `test_extract_one_jsonl_lines_are_valid_records`：每行 json.loads 后用 schema 校验
3. `test_extract_one_score_signal_distribution`：3 本应覆盖 3 种 score_signal
4. `test_extract_one_missing_input_exits_2`：subprocess 跑 `--input nonexistent` → returncode == 2
5. `test_extract_one_bvid_extracted_from_filename`：不传 `--bvid` 时从 `BV12yBoBAEEn_raw.txt` 提取

**提交命令:**
```bash
git add scripts/live-review/extract_one.py tests/live_review/test_extract_one_smoke.py
git commit -m "feat: US-LR-004 - 单文件冒烟 extract_one.py + mock 测试 5 用例"
```

---

### Task 5: US-LR-005 — 多份模式 + schema 一致性验证脚本

**Files:**
- Modify: `scripts/live-review/extract_one.py`（加 `--bvids id1,id2,...` 多份模式 + `--input-dir` / `--output-dir`）
- Create: `scripts/live-review/validate_jsonl_batch.py`
- Create: `tests/live_review/fixtures/mock_extract_5_files/<bvid>.json` × 5 份
- Create: `tests/live_review/test_extract_many.py`
- Create: `tests/live_review/test_validate_jsonl_batch.py`

**5 份 fixture 覆盖:**
- BV-A: 含明确打分 (3 本，全 explicit_number)
- BV-B: 含模糊打分 (4 本，全 fuzzy)
- BV-C: 含 unknown (2 本，全 unknown)
- BV-D: 极少小说（仅 2 本）
- BV-E: 极多小说（15 本）

**validate_jsonl_batch.py 输出格式（reports/live-review-validation-<timestamp>.md）:**
```markdown
# Live-Review JSONL Validation Report
**Generated**: 2026-04-27T10:00:00Z
**Files scanned**: 5
**Total novels extracted**: 26

## Per-file Statistics
| BVID | Novels | Score Non-null | Score Signals | Issues |
|---|---|---|---|---|
| BV-A | 3 | 3/3 (100%) | explicit:3 | none |
| ... |

## Score Signal Distribution
- explicit_number: 30%
- sign_phrase: 20%
- fuzzy: 35%
- unknown: 15%

## Validation Issues
（无 issue 时显示 "All files passed schema validation"）
```

**关键测试用例（test_extract_many.py）:**
- 5 份 mock 全跑通后 5 个 jsonl 文件存在
- 全 schema 校验通过
- 总 novel 数 == 3+4+2+2+15 == 26

**关键测试用例（test_validate_jsonl_batch.py）:**
- 正常 5 份 → 退出码 0 + 报告生成
- 故意 1 份某行 score=200（超 0-100）→ 退出码 1 + stderr 含 BVID + 行号 + 字段名
- 报告 markdown 渲染合法（用 mistune 或 markdown 库 parse 不抛错）

**提交命令:**
```bash
git add scripts/live-review/extract_one.py scripts/live-review/validate_jsonl_batch.py tests/live_review/fixtures/mock_extract_5_files/ tests/live_review/test_extract_many.py tests/live_review/test_validate_jsonl_batch.py
git commit -m "feat: US-LR-005 - 多份模式 + validate_jsonl_batch 报告生成"
```

---

### Task 6: US-LR-006 — 全量批跑脚本 run_batch.py

**Files:**
- Create: `scripts/live-review/run_batch.py`
- Create: `tests/live_review/fixtures/mock_batch/`（5 个 BV*_raw.txt + 4 个 mock_*.json）
- Create: `tests/live_review/test_run_batch.py`

**关键参数:**
- `--input-dir` 必填
- `--output-dir` 必填
- `--limit N` 仅处理前 N 份
- `--resume` 跳过已存在的 `<bvid>.jsonl`
- `--skip-failed` 失败时不退出，写 _failed.jsonl 后继续
- `--mock-llm-dir <fixture_dir>` 测试用，每 BV 对应 `<fixture_dir>/<bvid>.json`

**主流程伪码:**
```python
files = sorted(input_dir.glob("BV*_raw.txt"))
if limit: files = files[:limit]
done_bvids = {p.stem for p in output_dir.glob("BV*.jsonl")} if resume else set()
failures = []
for i, raw_path in enumerate(files, 1):
    bvid = re.match(r"^(BV[\w]+)_raw\.txt$", raw_path.name).group(1)
    if bvid in done_bvids:
        print(f"[{i}/{len(files)}] {bvid} skipped (resume)")
        continue
    t0 = time.time()
    try:
        mock = load(mock_llm_dir / f"{bvid}.json") if mock_llm_dir else None
        records = extract_from_text(raw_path.read_text(encoding="utf-8"),
                                    bvid=bvid, source_path=str(raw_path), mock_response=mock)
        write_jsonl(output_dir / f"{bvid}.jsonl", records)
        print(f"[{i}/{len(files)}] {bvid} done in {time.time()-t0:.1f}s")
    except Exception as e:
        failures.append({"bvid": bvid, "error": str(e), "traceback": traceback.format_exc()})
        if not skip_failed:
            raise
        print(f"[{i}/{len(files)}] {bvid} FAILED: {e}")
if failures:
    append_jsonl(output_dir / "_failed.jsonl", failures)
return 0 if not failures or skip_failed else 1
```

**关键测试用例（4 场景）:**
- (a) 5 文件全 mock 齐 → 5 jsonl 生成、_failed 不存在、退出码 0
- (b) 1 文件无 mock：`--skip-failed` 退出码 0 + _failed.jsonl 1 条；不带 `--skip-failed` 退出码 1
- (c) `--resume`：先 `--limit 3` 跑、再不限跑 → 第二次仅处理新增 2 个
- (d) `--limit 2`：只跑前 2 个

**提交命令:**
```bash
git add scripts/live-review/run_batch.py tests/live_review/fixtures/mock_batch/ tests/live_review/test_run_batch.py
git commit -m "feat: US-LR-006 - run_batch.py 断点续跑 + 失败可跳过 + 4 场景测试"
```

---

### Task 7: US-LR-007 — jsonl → CASE-LR-*.yaml 转换器

**Files:**
- Create: `scripts/live-review/jsonl_to_cases.py`
- Create: `tests/live_review/fixtures/sample_5_files.jsonl`（手编 5 行 jsonl，覆盖 P0/P1/P2/P3 + 全 layer 推导分支）
- Create: `tests/live_review/test_jsonl_to_cases.py`

**严重等级推导:**
```python
def derive_severity(score):
    if score is None: return "P3"
    if score < 55: return "P0"
    if score < 60: return "P1"
    if score < 65: return "P2"
    return "P3"
```

**Layer 推导（关键 — 用现有 enum）:**
```python
DIMENSION_TO_LAYER = {
    "opening": ["upstream"], "hook": ["upstream"], "golden_finger": ["upstream"],
    "genre": ["upstream"], "taboo": ["upstream"], "character": ["upstream"],
    "pacing": ["upstream", "downstream"], "highpoint": ["upstream", "downstream"],
    "simplicity": ["downstream"],
    "ops": ["upstream"], "misc": ["upstream"],
}

def derive_layers(comments):
    layers = set()
    for c in comments:
        layers.update(DIMENSION_TO_LAYER.get(c["dimension"], ["upstream"]))
    return sorted(layers) or ["upstream"]
```

**Title 推导:** `f"{title_guess} ({verdict} / {score}分)"` 或 `score=None → f"{title_guess} ({verdict})"`

**Failure_pattern.description:** `overall_comment + " | " + ";".join(c.content for c in negative_comments[:3])`

**Failure_pattern.observable:** 至少 1 项；从 negative comments 中取 dimension 抽 `f"{dimension}维度: {content}"`

**关键测试用例:**
- 5 jsonl 行 → 生成 5 yaml，case_id 严格 CASE-LR-2026-0001..0005
- 全部 schema_version 1.1 校验通过
- severity 推导覆盖 P0/P1/P2/P3+null 全 5 类
- layer 推导覆盖完整规则表全部分支
- 同 bvid 多本小说不冲突（不同 novel_idx 各自有独立 case）

**提交命令:**
```bash
git add scripts/live-review/jsonl_to_cases.py tests/live_review/fixtures/sample_5_files.jsonl tests/live_review/test_jsonl_to_cases.py
git commit -m "feat: US-LR-007 - jsonl → CASE-LR-yaml 转换器（severity/layer 推导规则表）"
```

---

### Task 8: US-LR-008 — 题材聚合器 aggregate_genre.py

**Files:**
- Create: `scripts/live-review/aggregate_genre.py`
- Create: `tests/live_review/fixtures/sample_30_cases/`（30 yaml，覆盖 5+ genre 不同分布）
- Create: `tests/live_review/test_aggregate_genre.py`

**关键算法:**
- 笛卡尔积单标签：[都市, 重生] 算 2 次（都市 +1，重生 +1）
- min_cases_per_genre 阈值过滤
- 统计：mean / median / p25 / p75（用 statistics）/ pass_rate（verdict==pass 的 / 总）
- common_complaints：dimension 频率排序取 Top-N（默认 5），每条含 dimension/frequency/examples（取 raw_quote 前 3 条）

**关键测试用例:**
- 30 fixture 跑 → 各 genre 统计与手算误差 < 0.01
- case_count<3 的 genre 不出现
- score 全 null 的 genre 的 score_mean / median 为 null（schema 允许）
- verdict 全 fail 的 genre 的 pass_rate 为 0.0
- common_complaints 频率严格降序

**提交命令:**
```bash
git add scripts/live-review/aggregate_genre.py tests/live_review/fixtures/sample_30_cases/ tests/live_review/test_aggregate_genre.py
git commit -m "feat: US-LR-008 - aggregate_genre.py 题材聚合（mean/median/p25/p75/pass_rate）"
```

---

### Task 9: US-LR-009 — 规则候选抽取器（cosine 去重）

**Files:**
- Create: `scripts/live-review/extract_rule_candidates.py`
- Create: `tests/live_review/fixtures/mock_rule_extract.json`（mock LLM 返回 5 条候选，2 条故意 dup_with EW-0001/EW-0002）
- Create: `tests/live_review/fixtures/existing_rules_fixture.json`（拷自 data/editor-wisdom/rules.json 前 3 条）
- Create: `tests/live_review/test_extract_rule_candidates.py`

**输出 schema 扩展:**
```jsonc
{
  "id": "RC-0001",   // 候选 ID（不进 rules.json 不取 EW-）
  "category": "...",
  "rule": "...", "why": "...", "severity": "...",
  "applies_to": [...], "source_files": [],
  "dup_with": ["EW-0001"],  // null or list
  "approved": null,         // null=未审 / true / false
  "source_bvids": ["BV12yBoBAEEn"]
}
```

**Cosine 去重算法:**
```python
from sentence_transformers import SentenceTransformer
import numpy as np
model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
existing_emb = model.encode([r["rule"] for r in existing_rules], normalize_embeddings=True)
candidate_emb = model.encode([c["rule"] for c in candidates], normalize_embeddings=True)
sim = candidate_emb @ existing_emb.T  # cosine
for i, c in enumerate(candidates):
    dups = [existing_rules[j]["id"] for j in np.where(sim[i] > 0.85)[0]]
    c["dup_with"] = dups or None
```

**关键测试用例:**
- mock 5 条 → 输出 5 条 (>= 5) + 至少 2 条 dup_with 非空
- source_bvids 字段正确（来自 jsonl 的 bvid 集合）
- 用 schemas/editor-rules.schema.json **基础**校验通过（dup_with/approved/source_bvids 为扩展字段需用 jsonschema 基础校验绕过 additionalProperties false 的限制 — 实施时 schema 加 additionalProperties: true 或独立 schema）
- approved 字段全 null

**提交命令:**
```bash
git add scripts/live-review/extract_rule_candidates.py tests/live_review/fixtures/mock_rule_extract.json tests/live_review/fixtures/existing_rules_fixture.json tests/live_review/test_extract_rule_candidates.py
git commit -m "feat: US-LR-009 - 规则候选抽取（LLM + bge cosine 去重 0.85 阈值）"
```

---

### Task 10: US-LR-010 — 规则候选审核 CLI + 提交工具

**Files:**
- Create: `scripts/live-review/review_rule_candidates.py`
- Create: `scripts/live-review/promote_approved_rules.py`
- Create: `tests/live_review/fixtures/sample_rule_candidates.json`（5 条：3 approved=true / 2 approved=false；其中 2 dup_with EW-0001/EW-0002）
- Create: `tests/live_review/test_review_rule_candidates.py`
- Create: `tests/live_review/test_promote_approved_rules.py`

**review CLI 交互:**
```text
[1/5] EW candidate: "在 800 字内呈现核心冲突..."
   category: opening | severity: hard | applies_to: golden_three
   why: 编辑指出黄金三章必须见钩子...
   dup_with: [EW-0001]
   source_bvids: BV12yBoBAEEn (1)
   [y]es / [n]o / [s]kip / [q]uit > _
```

**promote 关键逻辑:**
- 仅写入 `approved: true` 的项
- 新 ID 取现有 `rules.json` 末尾 ID + 1（如 EW-0080 → EW-0081）
- source 字段值固定 `live_review`，源信息进 source_bvids
- 必须通过 `editor-rules.schema.json` 校验（去掉扩展字段后）
- 现有规则字节级不变

**关键测试用例（review）:**
- stdin pipe `y\nn\ny\ns\ny\n` → candidates 文件 approved 字段写回 [True, False, True, None, True]

**关键测试用例（promote）:**
- 在 tmp_path 复制 fixture rules.json (含 EW-0001..EW-0080)
- 跑 promote → 新文件含 EW-0001..EW-0083
- 现有 EW-0001..EW-0080 各项**字节级**完全相同（用 hash 比对）
- 新加的 EW-0081/82/83 source 字段 == "live_review"
- 新加的 EW-0081/82/83 source_files 字段含 `["live_review_bvid:BV12yBoBAEEn", ...]` 形式（保持 schema 兼容）

**提交命令:**
```bash
git add scripts/live-review/review_rule_candidates.py scripts/live-review/promote_approved_rules.py tests/live_review/fixtures/sample_rule_candidates.json tests/live_review/test_review_rule_candidates.py tests/live_review/test_promote_approved_rules.py
git commit -m "feat: US-LR-010 - 规则候选交互式审核 CLI + 提交工具（fail-loud schema 校验）"
```

---

### Task 11: US-LR-011 — 题材语义检索 + ink-init Step 99.5 接入

**Files:**
- Create: `ink_writer/live_review/_vector_index.py`
- Create: `ink_writer/live_review/genre_retrieval.py`
- Create: `ink_writer/live_review/init_injection.py`
- Create: `scripts/live-review/build_vector_index.py`
- Modify: `ink-writer/skills/ink-init/SKILL.md`（追加 Step 99.5 + UI 渲染指引）
- Create: `tests/live_review/test_genre_retrieval.py`
- Create: `tests/live_review/test_init_injection.py`
- Create: `tests/live_review/test_skill_step_99_5.py`

**`_vector_index.py` 关键:**
- 复用 BAAI/bge-small-zh-v1.5（不重训练）
- 索引文件：`data/live-review/vector_index/index.faiss` + `meta.jsonl`（每行 {case_id, title_guess, genre, overall_comment, embedding_text}）

**`init_injection.py:check_genre()` 签名:**
```python
def check_genre(user_genre_input: str, *, top_k: int = 3, config_path: Path | None = None) -> dict:
    """返回 dict:
    {
      "warning_level": "ok" | "warn" | "no_data",
      "similar_cases": [{"case_id", "title_guess", "score", "verdict", "overall_comment", "source_bvid"}, ...],
      "genre_stats": {"case_count", "score_mean", "verdict_pass_rate", "common_complaints": [...]} | None,
      "suggested_actions": ["开头 800 字内见冲突", "金手指第 3 章前显化", ...],
      "render_text": "...格式化好的 ASCII UI 输出..."
    }
    """
```

**warning_level 决策:**
- 没有匹配 genre 的聚合 → `no_data`
- score_mean < init_genre_warning_threshold (默认 60) → `warn`
- 否则 → `ok`

**`ink-init/SKILL.md` 修改 (在 Step 99 后追加 Step 99.5):**
```markdown
### Step 99.5: 星河直播题材审查（live-review）

**前提**：题材已在 Step XX 确定（用户输入 `user_genre`）。

**调用**：
```python
from ink_writer.live_review.init_injection import check_genre
result = check_genre(user_genre)
print(result["render_text"])
```

**分支**：
- `result["warning_level"] == "ok"` → 信息展示后通行
- `result["warning_level"] == "warn"` → 用户输 y/n 二次确认；n 返回题材选择步骤
- `result["warning_level"] == "no_data"` → 仅展示"该题材无样本"提示，通行

可通过 `config/live-review.yaml:inject_into.init: false` 全局关闭。
```

**关键测试用例:**
- `test_genre_retrieval.py`: build_vector_index → retrieve "都市重生律师" → Top-3 含 fixture 中预设的特定 case_id；cosine 排序单调降
- `test_init_injection.py`: 5 query 覆盖 (覆盖+ok / 覆盖+warn / 覆盖+ok / 未覆盖+no_data / 极端高分+ok) → warning_level 严格匹配
- `test_skill_step_99_5.py`: subprocess 调 SKILL Step 99.5 模拟脚本，断言 render_text 含特定字符串（"星河直播相似案例"、"该题材统计" 等）

**提交命令:**
```bash
git add ink_writer/live_review/_vector_index.py ink_writer/live_review/genre_retrieval.py ink_writer/live_review/init_injection.py scripts/live-review/build_vector_index.py ink-writer/skills/ink-init/SKILL.md tests/live_review/test_genre_retrieval.py tests/live_review/test_init_injection.py tests/live_review/test_skill_step_99_5.py
git commit -m "feat: US-LR-011 - 题材语义检索 + ink-init Step 99.5 D+B 组合接入"
```

---

### Task 12: US-LR-012 — live-review-checker agent + ink-review Step 3.6

**Files:**
- Create: `ink-writer/agents/live-review-checker.md`
- Create: `ink_writer/live_review/checker.py`
- Modify: `ink-writer/skills/ink-review/SKILL.md`（追加 Step 3.6）
- Create: `tests/live_review/fixtures/sample_chapter_violating.txt`（手编 800 字章节，故意触发已知 fixture cases 多条违规）
- Create: `tests/live_review/fixtures/mock_live_review_checker_response.json`
- Create: `tests/live_review/test_checker.py`
- Create: `tests/live_review/test_review_step_3_6.py`

**`live-review-checker.md` 结构（对齐现有 33 个 checker）:**
```markdown
{{PROMPT_TEMPLATE:checker-input-rules.md}}

# Live Review Checker

**Purpose**: 章节文本对照星河直播打分病例库（CASE-LR-*）评分；< 0.65 阻断。

**Input**:
- chapter_text: 当前章节正文
- chapter_no: 章节序号
- genre_tags: 题材标签

**Retrieval**: 从 data/case_library/cases/live_review/ cosine 召回 Top-5 相关病例。

**Scoring (0.0-1.0)**:
- 综合 = (1 - violation_density) × verdict_pass_rate_of_top5
- violation_density = 命中违规病例数 / 召回病例数

**Output**:
{
  "score": 0.0-1.0,
  "dimensions": {"opening": 0.x, "pacing": 0.x, ...},
  "violations": [{"case_id", "dimension", "evidence_quote", "severity"}],
  "cases_hit": ["CASE-LR-2026-0001", ...]
}
```

**`checker.py` 主流程:**
```python
def run_live_review_checker(
    chapter_text: str, chapter_no: int, genre_tags: list[str],
    *, mock_response: dict | None = None, llm_call=None
) -> dict:
    cases = retrieve_top_k(chapter_text, genre_tags, k=5)
    if mock_response:
        return mock_response
    # ... LLM 评分（实施时填）
```

**`ink-review/SKILL.md` Step 3.6 追加:**
```markdown
### Step 3.6: live-review 硬门禁（与 Step 3.5 editor-wisdom 并列）

```python
from ink_writer.live_review.checker import run_live_review_checker
from ink_writer.live_review.config import load_config
cfg = load_config()
if cfg.inject_into.review:
    result = run_live_review_checker(chapter_text, chapter_no, genre_tags)
    threshold = cfg.golden_three_threshold if chapter_no <= 3 else cfg.hard_gate_threshold
    if result["score"] < threshold:
        evidence_chain.violations.extend(result["violations"])
        trigger_polish(result["violations"])
```

**注意**：与 Step 3.5 editor-wisdom-checker 是 **OR 并列** —— 两 checker 都不通过才阻断；任一通过即放行。
```

**关键测试用例:**
- `test_checker.py`: mock score 0.45 → 返回结构正确 + 0.45 < 0.65 触发 should_block True
- `test_review_step_3_6.py`: mock checker + mock polish-agent，假定违反 → 断言 (1) checker 调用 (2) violations 写入 evidence_chain (3) polish 循环触发 (4) `inject_into.review: false` → 整段短路（0 调用）

**回归保证:**
```bash
# 执行 Task 12 后必须确保现有 ink-review 测试不修改即通过
python3 -m pytest tests/integration/ tests/checker_pipeline/ tests/checkers/ --no-cov -q
```

**提交命令:**
```bash
git add ink-writer/agents/live-review-checker.md ink_writer/live_review/checker.py ink-writer/skills/ink-review/SKILL.md tests/live_review/fixtures/sample_chapter_violating.txt tests/live_review/fixtures/mock_live_review_checker_response.json tests/live_review/test_checker.py tests/live_review/test_review_step_3_6.py
git commit -m "feat: US-LR-012 - live-review-checker agent + ink-review Step 3.6 (OR 并列)"
```

---

### Task 13: US-LR-013 — 端到端冒烟脚本 smoke_test.py

**Files:**
- Create: `scripts/live-review/smoke_test.py`
- Create: `tests/live_review/test_smoke.py`

**主流程:**
```python
def main():
    cfg = load_config()
    if not vector_index_exists():
        rebuild_vector_index_from_fixture()
    
    # init 阶段
    result = check_genre("都市重生律师", top_k=3)
    assert result["warning_level"] in {"ok", "warn", "no_data"}
    assert "render_text" in result and result["render_text"]
    
    # review 阶段
    chapter = (FIXTURE_DIR / "sample_chapter_violating.txt").read_text(encoding="utf-8")
    if "--with-api" in sys.argv:
        result = run_live_review_checker(chapter, 3, ["都市", "重生"])
    else:
        mock = json.loads((FIXTURE_DIR / "mock_live_review_checker_response.json").read_text(encoding="utf-8"))
        result = run_live_review_checker(chapter, 3, ["都市", "重生"], mock_response=mock)
    assert "score" in result
    assert isinstance(result["violations"], list)
    
    write_smoke_report(...)  # PASS / FAIL 表
```

**关键测试用例 (test_smoke.py):**
- 不带 `--with-api` 跑 subprocess → 退出码 0 + reports/live-review-smoke-report.md 存在 + 内容含 "All checks PASS"

**提交命令:**
```bash
git add scripts/live-review/smoke_test.py tests/live_review/test_smoke.py
git commit -m "feat: US-LR-013 - 端到端 smoke_test.py（mock 模式默认 + --with-api 可选）"
```

---

### Task 14: US-LR-014 — 用户文档 docs/live-review-integration.md

**Files:**
- Create: `docs/live-review-integration.md`
- Create: `scripts/live-review/check_links.py`
- Modify: `CLAUDE.md`（编辑智慧模块段后追加 live-review 段，对称结构）
- Create: `tests/live_review/test_docs.py`

**`docs/live-review-integration.md` 结构（对齐 docs/editor-wisdom-integration.md）:**
1. 模块定位与 editor-wisdom 关系
2. 架构 mermaid 图（与 spec §2.1 一致）
3. 数据流（174 → jsonl → 3 类产物 → 3 阶段接入）
4. 主题域（与 editor-wisdom 同 11 类）
5. 如何添加新数据
6. 如何调阈值
7. **§ 用户手动操作清单**（拷自 spec §12 §M-1..§M-9 完整命令）
8. FAQ（含：与 editor-wisdom-checker 关系、阈值含义、人工审核必要性）
9. Smoke test

**CLAUDE.md 修改:**
```diff
 ## 编辑智慧模块
 ...

+## Live-Review 模块（新增 v26.x）
+
+基于 174 份起点编辑星河 B 站直播稿构建的作品级病例库 + 题材接受度信号 + 新规则候选。
+与 editor-wisdom 并列，覆盖 init（题材选材辅助）/ write（规则回流）/ review（新硬门禁）。
+
+详细文档：[docs/live-review-integration.md](docs/live-review-integration.md)
+
+### Top 3 注意事项
+
+1. **首次接入需跑用户手动操作清单 §M-1 ~ §M-9**：spec §12 列出全 9 步命令、费用、时长
+2. **case_id prefix 是 `CASE-LR-2026-`**（与 `CASE-` / `CASE-LEARN-` / `CASE-PROMOTE-` 隔离）
+3. **新规则永远走人工审核闸**：candidates → review → promote 三步走，不自动写 rules.json
```

**`check_links.py` 实现:**
```python
"""检查 markdown 文件内部链接（[text](relative_path)）的目标是否存在。"""
import re
import sys
from pathlib import Path

def check_links(md_path: Path) -> list[str]:
    text = md_path.read_text(encoding="utf-8")
    repo_root = md_path.parent
    while not (repo_root / ".git").exists() and repo_root.parent != repo_root:
        repo_root = repo_root.parent
    pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    failures = []
    for match in pattern.finditer(text):
        target = match.group(2).split("#")[0]  # strip anchor
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        if not target:
            continue
        # md_path 同级目录 解析
        candidate = (md_path.parent / target).resolve()
        if not candidate.exists():
            # 尝试 repo_root 解析
            candidate = (repo_root / target).resolve()
            if not candidate.exists():
                failures.append(f"{match.group(0)} → {target} not found")
    return failures

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: check_links.py <md_path>", file=sys.stderr)
        sys.exit(2)
    fails = check_links(Path(sys.argv[1]))
    if fails:
        for f in fails:
            print(f, file=sys.stderr)
        sys.exit(1)
    sys.exit(0)
```

**关键测试用例 (test_docs.py):**
```python
def test_doc_exists():
    assert Path("docs/live-review-integration.md").exists()

def test_mermaid_blocks_valid_syntax():
    text = Path("docs/live-review-integration.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```mermaid\n(.*?)\n```", text, re.DOTALL)
    assert len(blocks) >= 1
    for block in blocks:
        # 简单语法 sanity：含 graph/flowchart 关键字 + 无未闭合 [
        assert any(kw in block for kw in ("graph", "flowchart", "sequenceDiagram"))
        assert block.count("[") == block.count("]")

def test_internal_links_resolvable():
    from pathlib import Path
    sys.path.insert(0, "scripts/live-review")
    from check_links import check_links
    fails = check_links(Path("docs/live-review-integration.md"))
    assert not fails, fails

def test_claude_md_mentions_live_review():
    content = Path("CLAUDE.md").read_text(encoding="utf-8")
    assert "Live-Review" in content or "live-review" in content
    assert "docs/live-review-integration.md" in content
```

**提交命令:**
```bash
git add docs/live-review-integration.md scripts/live-review/check_links.py CLAUDE.md tests/live_review/test_docs.py
git commit -m "feat: US-LR-014 - 用户文档 + CLAUDE.md 接入 + 内部链接检查"
```

---

## Final Smoke After All Tasks

完成全部 14 Task 后跑：

```bash
# 1. 全测试通过
python3 -m pytest --no-cov -q
# 预期：全部 PASS（含新增 ~50 个 live_review 测试 + 现有 410 份病例向后兼容 + 现有 ink-* 测试）

# 2. 覆盖率不掉
python3 -m pytest -q
# 预期：--cov-fail-under=70 仍通过

# 3. ruff 全过
ruff check .
# 预期：与 baseline 持平或更少（不应新增任何错误）

# 4. mock smoke 通过
python3 scripts/live-review/smoke_test.py
# 预期：退出码 0 + reports/live-review-smoke-report.md PASS

# 5. 整树 import 不抛错
python3 -c "from ink_writer.live_review import case_id, config, extractor, genre_retrieval, init_injection, checker; print('all imports OK')"
```

完成后即可按 spec §12 §M-1..§M-9 由用户手动跑全量数据生成。

---

## Self-Review Checklist

写完 plan 后逐条核对：

- [x] **Spec coverage**: 14 个 US 一一对应 spec §5 的 14 条；spec §3 schema 全部体现在 Task 1；spec §4 三阶段接入对应 Task 11/12；spec §12 §M-1..§M-9 完整保留并在 Task 14 docs 中列出
- [x] **Placeholder scan**: prompt few-shot 标"实施时填入"已注明源数据；mermaid 图引用 spec；其他无 TBD/TODO
- [x] **Type consistency**: `LiveReviewConfig` / `BatchConfig` / `InjectConfig` dataclass 在 Task 2 定义后 Task 6/11/12 一致使用；`extract_from_text` 签名 Task 3 定义后 Task 4/5/6 一致使用；`run_live_review_checker` 签名 Task 12 定义；`check_genre` 签名 Task 11 定义；`allocate_live_review_id` 签名 Task 2 定义后 Task 7 使用
- [x] **Discovered constraints applied**：case_id pattern / domain enum / layer enum 映射 / source.type 复用 / pytest.ini testpaths / cov 门禁——全部反映在 Task 1 + 后续依赖 Task 中

---

**End of Plan**
