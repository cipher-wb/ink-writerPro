# 决策文档：ink-writer vs webnovel-writer Skill 系统

> **决策：合并。ink-writer 为唯一保留系统，webnovel-writer 废弃。**
>
> 日期：2026-04-16 | 状态：已批准 | 关联 US：US-403

---

## 1. 背景

项目中并存两套 Skill 系统：

| 维度 | ink-writer | webnovel-writer |
|------|-----------|-----------------|
| 位置 | `ink-writer/skills/` (本地开发) | `~/.claude/plugins/marketplaces/webnovel-writer-marketplace/` |
| Skill 数 | 14 | 8 |
| Agent 数 | 19 | 8 |
| 核心代码行 | ~6,000+ | ~2,200 |
| 数据目录 | `.ink/` | `.webnovel/` |

## 2. 对比分析

### 2.1 功能覆盖

webnovel-writer 的全部 8 个 Skill 在 ink-writer 中均有对应，且 ink-writer 版本更深入：

| Skill 对 | 重叠度 | ink-writer 独有 |
|----------|--------|-----------------|
| write | ~40% | Canary Scan、计算型闸门、Anti-detection 硬门禁、Editor Wisdom 门禁、Golden Three、Style RAG、`--batch` |
| review | ~65% | Sufficiency Gate、reader-simulator、proofreading-checker、anti-detection-checker、Editor Wisdom 门禁、auto re-review |
| init | ~85% | golden_three_plan.json、preferences.json、额外 4 个反套路库 |
| plan | ~90% | 里程碑检查点 |
| query | ~75% | 全局健康度报告、跨卷伏笔追踪 |
| resume | ~95% | 仅路径差异 |
| learn | ~30% | Auto-extract、趋势报告、风格指纹 |
| dashboard | ~90% | 前端自动构建 |

ink-writer 独有 6 个 Skill（`audit`、`auto`、`fix`、`macro-review`、`migrate`、`resolve`），webnovel-writer 无对应。

### 2.2 Agent 覆盖

ink-writer 19 个 Agent 完整覆盖 webnovel-writer 的 8 个，额外增加 11 个（writer-agent、polish-agent、proofreading-checker、reader-simulator、anti-detection-checker、golden-three-checker、editor-wisdom-checker、emotion-curve-checker、foreshadow-tracker、plotline-tracker、thread-lifecycle-tracker）。

### 2.3 共享底层

两套系统共享相同的 `data_modules` 核心（30+ 文件），`core-constraints.md`、`strand-weave-pattern.md`、`cool-points-guide.md` 等参考文件字节级一致。ink-writer 额外增加 `anti_ai_lint`、`checkpoint_utils`、`golden_three`、`memory_compressor`、`style_anchor` 等模块。

### 2.4 迁移基础设施

已存在 `ink-writer/scripts/migrate_webnovel_to_ink.sh`，支持：
- `.webnovel/` → `.ink/` 目录重命名
- 卷子目录扁平化
- 完整性校验

## 3. 决策理由

### 选择合并（废弃 webnovel-writer）的原因

1. **ink-writer 是完全超集**：功能、Agent、参考文件均完整覆盖，无功能损失
2. **维护成本翻倍**：两套系统共享底层但各自演进，每次改进须同步两处，已产生分叉
3. **质量差距显著**：ink-writer 经过 Phase 0-3 深度优化（钩子引擎、爽点调度、情绪心电图、Anti-detection 硬门禁、Editor Wisdom RAG），webnovel-writer 无这些能力
4. **迁移成本极低**：迁移脚本已就绪，仅需目录重命名 + 扁平化
5. **用户体验统一**：消除"用哪个"的困惑

### 未选择保留双系统的原因

- webnovel-writer 的 `--fast`/`--minimal` 模式可以作为 ink-write 的参数实现，无需独立系统
- 两套系统的 Skill 注册增加 Claude Code 技能列表冗余（14 + 8 = 22 个技能）

## 4. 迁移方案

### 4.1 时间线

| 阶段 | 时间 | 操作 |
|------|------|------|
| **Phase A — 公告** | 立即 | 在 webnovel-writer 各 Skill 头部加废弃警告 |
| **Phase B — 功能回移** | v13.0.0 前 | 将 webnovel-writer 的 `--fast`/`--minimal` 模式移植到 ink-write |
| **Phase C — 硬废弃** | v13.0.0 | 从 settings.json 移除 webnovel-writer 注册；保留迁移脚本 |
| **Phase D — 清理** | v14.0.0 | 删除 webnovel-writer marketplace 目录 |

### 4.2 现有项目迁移

```bash
# 一键迁移
bash ink-writer/scripts/migrate_webnovel_to_ink.sh /path/to/your/novel

# 迁移后验证
cd /path/to/your/novel
/ink-query   # 检查项目状态
```

### 4.3 功能回移清单

从 webnovel-writer 回移到 ink-writer 的功能：

| 功能 | 来源 | 目标 | 状态 |
|------|------|------|------|
| `--fast` 模式（跳过 Step 2B） | webnovel-write | ink-write | 待实现 |
| `--minimal` 模式（3 checker） | webnovel-write | ink-write | 待实现 |
| 内联环境变量设置（无需 env-setup.sh） | 各 webnovel skill | 作为降级方案 | 低优先 |

## 5. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 现有 webnovel-writer 项目迁移失败 | 迁移脚本已含校验步骤；迁移前自动备份 |
| 用户习惯 `/webnovel-*` 命令 | Phase A 废弃警告中明确给出等价 `/ink-*` 命令 |
| ink-write 缺少轻量模式 | Phase B 在 v13.0.0 前回移 `--fast`/`--minimal` |

## 6. 验收标准

- [x] 本决策文档已审批
- [ ] Phase A：webnovel-writer Skill 加废弃警告（v13.0.0 前）
- [ ] Phase B：ink-write 支持 `--fast`/`--minimal`（v13.0.0 前）
- [ ] Phase C：settings.json 移除注册（v13.0.0）
- [ ] Phase D：清理目录（v14.0.0）
