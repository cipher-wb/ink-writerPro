---
name: market-trends-cache
description: 起点中文网 + 番茄小说双平台榜单缓存目录，供 ink-init --quick 反向建模使用。
type: reference
version: v1.0
---

# Market Trends Cache

## 用途

Quick 模式在方案生成前，通过 WebSearch 拉取起点中文网和番茄小说的当日榜单，做反向建模——显式规避两平台共通 Top 5 热门套路关键词。

本目录只存放 **当日缓存**（跨日重新搜索），保留最近 **90 天**；超期缓存由 `ink-init` 在启动时静默清理。

## 固定检索源（不可配置）

| 平台 | 榜单类型 | 检索语（硬编码） |
|------|----------|------------------|
| 起点中文网 | 月票榜 | `起点中文网 月票榜 2026 热门 题材` |
| 起点中文网 | 分类月榜 | `起点 分类 月榜` |
| 番茄小说 | 爆款/套路 | `番茄小说 爆款 套路 2026` |
| 番茄小说 | 免费热门新书 | `番茄免费小说 热门 新书` |

两平台并行搜索，单次总延迟上限 **15s**；超时走 fallback。

## 缓存文件命名规则

```
data/market-trends/cache-YYYYMMDD.md
```

- `YYYYMMDD` 为 UTC+8 当日日期，如 `cache-20260417.md`。
- 当日同一份缓存被同一会话多次命中 → 直接复用，不重复 WebSearch。
- 跨日 → 重新搜索并落盘当日文件；90 天外旧文件清理。

## 缓存文件格式

每份缓存为 Markdown，必含以下板块：

```markdown
---
date: 2026-04-17
source_platforms: [qidian, fanqie]
fetch_status: ok | partial | fallback
fallback_from: cache-YYYYMMDD.md   # 仅 fetch_status=fallback 时出现
---

## 起点中文网 Top 10

1. 《书名 A》— 题材 / 简评
2. …（共 10 本）

## 番茄小说 Top 10

1. 《书名 X》— 题材 / 简评
2. …（共 10 本）

## 起点 热门套路关键词（5-8 条）

- 签到流
- 诸天万界
- …

## 番茄 热门套路关键词（5-8 条）

- 无敌流
- 赘婿
- …

## 两平台共通套路列表（反向规避目标）

- 签到
- 赘婿
- 无敌
- 系统
- 重生
（Quick Step 1 必须规避此列表 Top 5；单平台榜单不强制规避）
```

## Fallback 规则

- WebSearch 失败或超时（>15s）→ 尝试读取最近 **7 天内** 任一 `cache-*.md`。
- 命中则输出提示：`⚠️ 使用 N 天前榜单数据（cache-YYYYMMDD.md）`。
- 7 天内均无缓存 → 降级为 `fetch_status: none`，Quick Step 1 跳过反向规避步骤，并在创意指纹「反向规避」字段标注 `无当日数据`。

## 消费者

- `ink-writer/skills/ink-init/SKILL.md` Quick Step 0 WebSearch 子步骤：抓取并落盘。
- Quick Step 1 生成 3 套方案时读取「两平台共通套路列表」做规避。
- Quick Step 2 「🧬 创意指纹」板块消费「反向规避」字段展示给用户（见 US-008）。

## 不计入本目录

- `/ink-seeds` 相关种子库缓存 → `references/creativity/anti-trope-seeds*.json`。
- 编辑智慧 RAG 索引 → `data/editor-wisdom/`。
- 命名词库 → `data/naming/`。
