# Step 1.5 Contract Template

## 目标

把 `extract_chapter_context.py` 的上下文与 guidance 收束成“可执行合同”，直接驱动 Step 2A。

## 必填输出结构（Scene-Sequel 最小闭环）

- 目标（20字内）
- 阻力（20字内）
- 代价（20字内）
- 本章变化（30字内，优先可量化：关系/资源/风险/地位/能力）
- 未闭合问题（30字内，后段或章末）
- 核心冲突一句话
- 开头类型（冲突/悬疑/动作/对话/氛围）
- 情绪节奏（低→高/高→低/低→高→低/平稳）
- 信息密度（low/medium/high）
- 是否过渡章（true/false，必须按大纲判定，不按字数判定）
- 追读力设计（钩子类型/强度、微兑现清单、爽点模式）
- `character_progression_summary`（FIX-18 P5c）：出场角色在本章之前的多维度演进切片（≤5 行/角色，字段 `chapter_no/dimension/from_value/to_value/cause`）。writer-agent 据此感知配角立场/关系/境界/知识/情绪/目标的漂移，避免"掉线"或行为与既定演进冲突。若无记录，输出占位符 `[本章之前无角色演进记录]`。

过渡章判定规则（强制）：
- 依据章纲/卷纲中的章节功能标签与目标（铺垫/转场/承接/回收等）。
- 若大纲未显式标注，由”本章核心目标是否以推进主冲突为主”判定。
- 禁止使用字数阈值判定过渡章。

**过渡章判定优先级（铁律）**：
1. 大纲/章纲显式标注 `is_transition: true` → 一定是过渡章
2. 大纲/章纲显式标注核心目标为”主冲突推进” → 一定不是过渡章
3. 大纲未标注 → **触发大纲补充流程**（提示用户通过 `/ink-plan` 补充标注），而非自行判定
4. 紧急情况（ink-auto无人值守时无法补充）→ 以”核心目标是否推进主冲突”为判定依据，并标注 `[自动判定，建议人工确认]`

## 差异化检查

- 钩子类型优先避免与最近 3 章重复。
- 开头类型优先避免与最近 3 章重复。
- 爽点模式优先避免与最近 5 章重复。

若必须重复，必须记录 Override 理由，并至少变更以下一项：
- 对象
- 代价
- 结果

### Override Contract 规范

每个 Override 必须记录为以下格式并写入 index.db 的 override_contracts 表：

```json
{
  "override_id": "OVR-{chapter}-{sequence}",
  "chapter": 30,
  "type": "hook_repeat | micropayoff_deficit | strand_imbalance | coolpoint_deficit",
  "severity_overridden": "high",
  "rationale": "TRANSITIONAL_SETUP | CHARACTER_CREDIBILITY | PLOT_NECESSITY",
  "description": "具体描述被覆盖的约束",
  "repayment_plan": "在第 35 章前补偿 2 个微兑现",
  "due_chapter": 35,
  "status": "active | repaid | overdue"
}
```

#### 到期与清算机制

1. **到期预警**：当 current_chapter >= due_chapter - 10 时，Context Agent 必须在上下文中标注 `[债务预警] Override OVR-{id} 将在第 {due_chapter} 章到期`
2. **逾期升级**：当 current_chapter > due_chapter 且 status 仍为 active：
   - 债务自动升级为 `overdue`
   - severity 提升一级（medium -> high, high -> critical）
   - 下一章的 reader-pull-checker 将此作为硬约束检查
3. **强制清算**：每 25 章执行一次债务审计，列出所有 active/overdue 债务
4. **利息上限**：任何单条债务的利息不超过原始值的 3 倍（防止爆炸性增长）

## 题材快速调用（仅命中时）

命中题材：`esports` / `livestream` / `cosmic-horror`

执行：
1. 从 `writing/genre-hook-payoff-library.md` 选 1 条期待锚点（优先章末，也可后段）。
2. 选 1-2 条微兑现，优先与本章核心冲突同方向。

## 读取优先级

1. 必读：`writing_guidance.guidance_items`
2. 条件必读：`rag_assist`（`invoked=true` 且 `hits` 非空）
3. 选读：`reader_signal`、`genre_profile.reference_hints`
