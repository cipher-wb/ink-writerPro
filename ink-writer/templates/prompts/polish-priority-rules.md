<!-- version: 1.1.0 | changelog: add P0 logic fix and P0.5 outline compliance fix -->

## 修复优先级规则

| 优先级 | 处理规则 |
|--------|---------|
| `P0 逻辑修复` | 最高优先级；logic-checker 的 medium/low 问题，在所有其他修复之前执行。修复约束：数字只改数字、空间只加过渡句、物品加状态描写，不改周围叙事 |
| `P0.5 大纲合规修复` | 次高优先级；outline-compliance-checker 的 medium/low 问题。修复约束：不改变剧情走向，只补充展开/强化可识别度/调整位置 |
| `critical` | 必须修复；无法修复必须记录 deviation 与原因 |
| `high` | 必须优先处理；无法修复记录 deviation |
| `medium` | 视篇幅和收益处理 |
| `low` | 可择优处理 |

## 类型对应修复动作

- `ARITHMETIC_ERROR`（P0）：只改错误数字，保持周围叙事不变
- `ACTION_CONFLICT`（P0）：调整动作顺序或补充过渡动作，不删除情节段落
- `ATTRIBUTE_MISMATCH`（P0）：统一为首次出现或角色档案的权威属性值
- `SPATIAL_JUMP`（P0）：添加移动过渡句，不删除原有内容
- `OBJECT_DISCONTINUITY`（P0）：添加物品状态变化描写
- `SENSORY_CONFLICT`（P0）：调整感官描写与环境匹配
- `DIALOGUE_ATTRIBUTION`（P0）：补充说话人标记，不改对话内容
- `CAUSAL_GAP`（P0）：补充动机/信息铺垫句，不改决策结果
- `GOAL_UNDERDEVELOPED`（P0.5）：补充核心事件细节展开，不改剧情走向
- `FORESHADOW_VAGUE`（P0.5）：强化伏笔关键词可识别度
- `HOOK_MISPLACED`（P0.5）：将钩子内容移至章末 500 字内
- `POWER_CONFLICT`：能力回落到合法境界，或补出"获得路径+代价"
- `OOC`：恢复角色话术、风险偏好、决策边界
- `TIMELINE_ISSUE`：补足时间流逝锚点
- `LOCATION_ERROR`：补移动过程与空间锚点
- `PACING_IMBALANCE`：增加缺失推进事件或删冗余说明段
- `CONTINUITY_BREAK`：补衔接句与过渡动作
