# Checker 统一输出 Schema

所有审查 Agent 应遵循此统一输出格式，便于自动化汇总和趋势分析。

说明：
- 单章写作场景默认使用 `chapter` 字段。
- 若需要兼容区间统计，可在聚合层补充 `start_chapter/end_chapter`，不要求单个 checker 必填。
- 允许扩展字段，但不得删除或替代本文件定义的必填字段。

## 标准 JSON Schema

```json
{
  "agent": "checker-name",
  "chapter": 100,
  "overall_score": 85,
  "pass": true,
  "issues": [
    {
      "id": "ISSUE_001",
      "type": "问题类型",
      "severity": "critical|high|medium|low",
      "location": "位置描述",
      "description": "问题描述",
      "suggestion": "修复建议",
      "can_override": false
    }
  ],
  "metrics": {},
  "summary": "简短总结"
}
```

## 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `agent` | string | ✅ | Agent 名称 |
| `chapter` | int | ✅ | 章节号 |
| `overall_score` | int | ✅ | 总分 (0-100) |
| `pass` | bool | ✅ | 是否通过 |
| `issues` | array | ✅ | 问题列表 |
| `metrics` | object | ✅ | Agent 特定指标 |
| `summary` | string | ✅ | 简短总结 |

扩展字段约定（可选）：
- 可附加 checker 私有字段（如 `hard_violations`、`soft_suggestions`、`override_eligible`）。
- 私有字段用于增强解释，不用于替代 `issues`。

## 问题严重度定义

| severity | 含义 | 处理方式 |
|----------|------|----------|
| `critical` | 严重问题，必须修复 | 润色步骤必须修复 |
| `high` | 高优先级问题 | 优先修复 |
| `medium` | 中等问题 | 建议修复 |
| `low` | 轻微问题 | 可选修复 |

## 各 Checker 特定 metrics

### reader-pull-checker
```json
{
  "metrics": {
    "hook_present": true,
    "hook_type": "危机钩",
    "hook_strength": "strong",
    "prev_hook_fulfilled": true,
    "micropayoff_count": 2,
    "micropayoffs": ["能力兑现", "认可兑现"],
    "is_transition": false,
    "debt_balance": 0.0
  }
}
```

### high-point-checker
```json
{
  "metrics": {
    "cool_point_count": 2,
    "cool_point_types": ["装逼打脸", "越级反杀"],
    "density_score": 8,
    "type_diversity": 0.8,
    "milestone_present": false
  }
}
```

### consistency-checker
```json
{
  "metrics": {
    "power_violations": 0,
    "location_errors": 1,
    "timeline_issues": 0,
    "entity_conflicts": 0
  }
}
```

### ooc-checker
```json
{
  "metrics": {
    "severe_ooc": 0,
    "moderate_ooc": 1,
    "minor_ooc": 2,
    "speech_violations": 0,
    "character_development_valid": true
  }
}
```

### continuity-checker
```json
{
  "metrics": {
    "transition_grade": "B",
    "active_threads": 3,
    "dormant_threads": 1,
    "forgotten_foreshadowing": 0,
    "logic_holes": 0,
    "outline_deviations": 0,
    "evidence_source": "recent_full_texts",
    "evidence_count": 4,
    "evidence_missing_count": 0,
    "layer5_issues": 3,
    "missing_full_text_chapters": []
  }
}
```

> **US-005 扩展字段**（continuity-checker 专用，additive，旧快照缺省）：
> - `evidence_source`: `"recent_full_texts"`（正常）/ `"degraded:no_full_texts"`（旧快照兜底）/ `"n1_no_prior"`（N=1 无前置）
> - `evidence_count`: 带 `evidence` 字段的第五层 issue 条数
> - `evidence_missing_count`: 命中第五层但缺 evidence 的 issue 数（应为 0，非 0 阻塞通过）
> - `layer5_issues`: 第五层（前三章全文回溯）命中的 issue 总数
> - `missing_full_text_chapters`: 本次 review 中 `recent_full_texts[k].missing=true` 的章节号数组
>
> **Issue 级扩展字段**（US-005）：第五层命中的每条 `issues[]` 条目允许附加 `evidence:{source_chapter:int, excerpt:str}` 字段，语义详见 `ink-writer/agents/continuity-checker.md` 第五层。

### pacing-checker
```json
{
  "metrics": {
    "dominant_strand": "quest",
    "quest_ratio": 0.6,
    "fire_ratio": 0.25,
    "constellation_ratio": 0.15,
    "consecutive_quest": 3,
    "fire_gap": 4,
    "constellation_gap": 8,
    "fatigue_risk": "low"
  }
}
```

### reader-simulator
```json
{
  "metrics": {
    "immersion_score": 78,
    "emotion_curve_health": "有波动但中段偏平",
    "dropout_risk_zones": ["600-900字"],
    "highest_emotion_point": "第1500字（反转揭示）",
    "lowest_emotion_point": "第700字（解释段）",
    "next_chapter_drive": "strong",
    "reader_persona": "修仙长线读者",
    "info_overload_segments": 1,
    "empathy_score": 80
  },
  "reader_verdict": {
    "hook_strength": 8,
    "curiosity_continuation": 7,
    "emotional_reward": 9,
    "protagonist_pull": 8,
    "cliffhanger_drive": 9,
    "filler_risk": 2,
    "repetition_risk": 1,
    "total": 48,
    "verdict": "pass"
  }
}
```

> **reader_verdict 为必填扩展字段**（v9.0 起）。所有模式（快速/完整）都必须输出。
> - `total` = 正向5维之和 - 反向2维之和，范围 -20~50
> - `verdict`: `pass`(≥32) / `enhance`(25-31) / `rewrite`(<25)

### emotion-curve-checker
```json
{
  "metrics": {
    "scene_count": 5,
    "avg_valence": 0.3,
    "avg_arousal": 0.6,
    "emotion_variance": 0.25,
    "flat_segments": 1,
    "target_similarity": 0.82,
    "peak_scene": 3,
    "trough_scene": 1
  }
}
```

### anti-detection-checker
```json
{
  "metrics": {
    "sentence_length_cv": 0.42,
    "repeated_pattern_count": 2,
    "connective_frequency": 0.08,
    "dialogue_ratio": 0.35,
    "info_density_score": 72,
    "causal_chain_score": 80,
    "composite_score": 78
  }
}
```

### proofreading-checker
```json
{
  "metrics": {
    "rhetoric_score": 75,
    "paragraph_score": 80,
    "pronoun_score": 70,
    "anachronism_score": 90,
    "style_consistency_score": 82
  }
}
```

### golden-three-checker
```json
{
  "metrics": {
    "ten_second_scan": 8,
    "promise_visibility": 7,
    "micropayoff_count": 3,
    "hook_reply_hit": true,
    "closure_detected": true,
    "traction_score": 85
  }
}
```

### thread-lifecycle-tracker
```json
{
  "metrics": {
    "foreshadow": {
      "total_active": 12,
      "total_overdue": 2,
      "total_silent": 1,
      "overdue_critical": 1,
      "overdue_high": 1,
      "overdue_medium": 0,
      "density_warning": false
    },
    "plotline": {
      "total_active": 6,
      "total_inactive": 1,
      "inactive_critical": 0,
      "inactive_high": 1,
      "inactive_medium": 0,
      "density_warning": false
    }
  }
}
```

### editor-wisdom-checker
```json
{
  "metrics": {
    "rules_triggered": 5,
    "critical_violations": 1,
    "high_violations": 2,
    "medium_violations": 2,
    "rule_categories": ["开篇", "对话", "节奏"]
  }
}
```

## 汇总格式

Step 3 完成后，输出汇总 JSON：

```json
{
  "chapter": 100,
  "checkers": {
    "reader-pull-checker": {"score": 85, "pass": true, "critical": 0, "high": 1},
    "high-point-checker": {"score": 80, "pass": true, "critical": 0, "high": 0},
    "consistency-checker": {"score": 90, "pass": true, "critical": 0, "high": 0},
    "ooc-checker": {"score": 75, "pass": true, "critical": 0, "high": 1},
    "continuity-checker": {"score": 85, "pass": true, "critical": 0, "high": 0},
    "pacing-checker": {"score": 80, "pass": true, "critical": 0, "high": 0},
    "emotion-curve-checker": {"score": 78, "pass": true, "critical": 0, "high": 0},
    "anti-detection-checker": {"score": 82, "pass": true, "critical": 0, "high": 1},
    "proofreading-checker": {"score": 88, "pass": true, "critical": 0, "high": 0},
    "thread-lifecycle-tracker": {"score": 75, "pass": true, "critical": 0, "high": 1},
    "golden-three-checker": {"score": 85, "pass": true, "critical": 0, "high": 0},
    "reader-simulator": {"score": 80, "pass": true, "critical": 0, "high": 0},
    "editor-wisdom-checker": {"score": 77, "pass": true, "critical": 0, "high": 1}
  },
  "overall": {
    "score": 82.5,
    "pass": true,
    "critical_total": 0,
    "high_total": 2,
    "can_proceed": true
  }
}
```
