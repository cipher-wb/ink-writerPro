<!-- version: 1.0.0 | changelog: initial extraction from polish-agent -->

## 修复优先级规则

| 优先级 | 处理规则 |
|--------|---------|
| `critical` | 必须修复；无法修复必须记录 deviation 与原因 |
| `high` | 必须优先处理；无法修复记录 deviation |
| `medium` | 视篇幅和收益处理 |
| `low` | 可择优处理 |

## 类型对应修复动作

- `POWER_CONFLICT`：能力回落到合法境界，或补出"获得路径+代价"
- `OOC`：恢复角色话术、风险偏好、决策边界
- `TIMELINE_ISSUE`：补足时间流逝锚点
- `LOCATION_ERROR`：补移动过程与空间锚点
- `PACING_IMBALANCE`：增加缺失推进事件或删冗余说明段
- `CONTINUITY_BREAK`：补衔接句与过渡动作
