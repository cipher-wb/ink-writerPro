# Prose Directness Verification Report (US-011)

- Generated: 2026-04-20 10:54:26 UTC

- Direct Top-5: 西游：拦路人！, 状元郎, 我，枪神！, 重回1982小渔村, 1979黄金时代
- Rhetoric Top-5: 神明调查报告, 异度旅社, 亡灵法师，召唤055什么鬼？, 真君驾到, 仙业

> 方法论：以 `benchmark/reference_corpus` 最直白 Top-5 作为新机制期望达成的目标文风代理、最华丽 Top-5 作为未激活直白时易产出的AI 味反面代理；M-1 用 AI 味合成 fixture 量化 `simplify_text` 的实际缩短能力；M-5 读者盲测延至发版后（首版占位 LLM judge）。

## 验收指标总览

| 指标 | 描述 | 目标 | 实测 | 结果 |
|------|------|------|------|------|
| M-1 | AI 味 fixture 经 simplify_text 后字数缩短 | ≥20% | 26.91% | ✅ PASS |
| M-2 | 最直白 Top-5 × ch1-3 directness 5 维度平均 | ≥8 | 9.33 | ✅ PASS |
| M-3 | 最直白 Top-5 × ch1-3 黑名单命中中位数 | ≤3 | 2 | ✅ PASS |
| M-4 | 最直白 Top-5 句长中位数 vs benchmark IQR | [13.0, 17.62] | 17.0 | ✅ PASS |
| M-5 | 读者盲测直白分提升（首版 LLM judge） | ≥40% | deferred_to_live_run | ℹ️ INFO |
| M-6 | slow_build 场景 sensory-immersion 零退化 | retained | retained | ✅ PASS |
| M-7 | editor-wisdom simplicity 主题域 | ≥12 rules, recall ≥5 | 14 | ✅ PASS |

## M-1 字数缩短（simplify_text 机制验证）

- Fixture 原字数: **223**
- 精简后字数: **163**
- 缩短比例: **26.91%** (target ≥ 20%)
- 黑名单命中: 14 → 0
- 触发规则: `blacklist_abstract_drop, empty_paragraph_compress, long_sentence_split`
- Rolled back: False

## M-2/M-3/M-4 最直白 Top-5 实测

### Direct Top-5 chapter breakdown（n=15）

| Book | Ch | Overall | Severity | D1 | D2 | D3 | D4 | D5 | Hits |
|------|----|---------|----------|----|----|----|----|----|------|
| 西游：拦路人！ | 1 | 10.00 | green | 10.0 | 10.0 | 10.0 | 10.0 | 10.0 | 3 |
| 西游：拦路人！ | 2 | 9.87 | green | 10.0 | 10.0 | 10.0 | 9.7 | 9.7 | 2 |
| 西游：拦路人！ | 3 | 10.00 | green | 10.0 | 10.0 | 10.0 | 10.0 | 10.0 | 1 |
| 状元郎 | 1 | 9.83 | green | 10.0 | 10.0 | 10.0 | 9.1 | 10.0 | 2 |
| 状元郎 | 2 | 9.48 | yellow | 10.0 | 10.0 | 10.0 | 7.4 | 10.0 | 1 |
| 状元郎 | 3 | 9.48 | yellow | 10.0 | 10.0 | 10.0 | 7.4 | 10.0 | 1 |
| 我，枪神！ | 1 | 7.87 | red | 10.0 | 6.6 | 10.0 | 5.8 | 7.0 | 1 |
| 我，枪神！ | 2 | 8.66 | red | 10.0 | 9.7 | 10.0 | 5.3 | 8.3 | 2 |
| 我，枪神！ | 3 | 8.28 | red | 10.0 | 5.5 | 10.0 | 6.2 | 9.7 | 4 |
| 重回1982小渔村 | 1 | 9.76 | green | 10.0 | 10.0 | 10.0 | 8.8 | 10.0 | 0 |
| 重回1982小渔村 | 2 | 8.51 | red | 10.0 | 10.0 | 4.6 | 8.0 | 10.0 | 4 |
| 重回1982小渔村 | 3 | 9.52 | yellow | 10.0 | 7.6 | 10.0 | 10.0 | 10.0 | 2 |
| 1979黄金时代 | 1 | 8.67 | yellow | 8.2 | 7.9 | 7.3 | 10.0 | 10.0 | 5 |
| 1979黄金时代 | 2 | 10.00 | green | 10.0 | 10.0 | 10.0 | 10.0 | 10.0 | 0 |
| 1979黄金时代 | 3 | 10.00 | green | 10.0 | 10.0 | 10.0 | 10.0 | 10.0 | 4 |

### Rhetoric Top-5 chapter breakdown（对照）（n=15）

| Book | Ch | Overall | Severity | D1 | D2 | D3 | D4 | D5 | Hits |
|------|----|---------|----------|----|----|----|----|----|------|
| 神明调查报告 | 1 | 4.96 | red | 0.0 | 8.2 | 2.5 | 5.8 | 8.3 | 28 |
| 神明调查报告 | 2 | 8.66 | red | 10.0 | 10.0 | 4.5 | 8.8 | 10.0 | 10 |
| 神明调查报告 | 3 | 7.47 | red | 7.2 | 10.0 | 4.6 | 5.5 | 10.0 | 8 |
| 异度旅社 | 1 | 4.36 | red | 0.0 | 6.8 | 0.0 | 5.0 | 10.0 | 13 |
| 异度旅社 | 2 | 4.67 | red | 2.1 | 5.9 | 0.0 | 5.4 | 10.0 | 17 |
| 异度旅社 | 3 | 4.14 | red | 0.0 | 4.9 | 0.0 | 5.8 | 10.0 | 10 |
| 亡灵法师，召唤055什么鬼？ | 1 | 7.08 | red | 10.0 | 4.6 | 4.9 | 10.0 | 5.9 | 6 |
| 亡灵法师，召唤055什么鬼？ | 2 | 6.19 | red | 5.6 | 4.5 | 4.8 | 10.0 | 6.1 | 7 |
| 亡灵法师，召唤055什么鬼？ | 3 | 7.81 | red | 5.9 | 8.8 | 5.2 | 10.0 | 9.2 | 6 |
| 真君驾到 | 1 | 5.57 | red | 1.5 | 4.8 | 4.5 | 7.4 | 9.7 | 5 |
| 真君驾到 | 2 | 7.65 | red | 4.1 | 10.0 | 10.0 | 8.3 | 5.8 | 3 |
| 真君驾到 | 3 | 6.22 | red | 1.7 | 7.5 | 8.6 | 9.1 | 4.1 | 7 |
| 仙业 | 1 | 7.33 | red | 9.4 | 9.2 | 2.8 | 10.0 | 5.2 | 16 |
| 仙业 | 2 | 9.40 | yellow | 10.0 | 9.2 | 10.0 | 10.0 | 7.9 | 5 |
| 仙业 | 3 | 7.88 | red | 10.0 | 9.2 | 2.6 | 10.0 | 7.6 | 12 |

### M-2 5 维度分均

- D1_rhetoric_density: **9.88**
- D2_adj_verb_ratio: **9.15**
- D3_abstract_per_100_chars: **9.46**
- D4_sent_len_median: **8.51**
- D5_empty_paragraphs: **9.64**
- Overall 均分: **9.33**

### M-4 句长对齐

- Direct Top-5 句长中位数: **17.0** 词
- Benchmark P50: **15.0** 词
- 容差带: [13.0, 17.62]

## M-6 零退化验证（sensory-immersion-checker）

- directness 场景（combat/ch50）: sensory issue 被正确过滤
- slow_build 场景（ch50）: sensory issue 保留（零退化）
- default kwargs（无 scene_mode/chapter_no）: sensory issue 保留（向后兼容）

## M-7 editor-wisdom simplicity 召回

- simplicity 规则总数: **14**
- applies_to 覆盖: `['all_chapters', 'climax', 'combat', 'golden_three', 'high_point']`
- 召回下限（directness 场景）: ≥ 5（见 tests/editor_wisdom/test_simplicity_theme.py 锚定）

## M-5 读者盲测方法论（首版延至发版后）

首版用 LLM judge（Claude Sonnet 4.6）对 AI-heavy vs 最直白 Top-5 样本盲评 1-10 直白分，目标提升 ≥40%。发版后在真实项目内部 3 人盲测复核，写入 reports/prose-directness-reader-scores.json。

## Release Gate 判定

- 硬指标通过率: **6/6** （M-5 非阻断，延至发版后）
- Release gate: ✅ **GO** — US-012 可以 tag v22.0.0
