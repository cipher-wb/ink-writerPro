# 全局 Severity 标准

> 所有 Checker 必须遵循此标准，确保跨 Checker 的问题优先级一致。

## Severity 定义

| 等级 | 定义 | 处理要求 | 示例 |
|------|------|---------|------|
| **critical** | 导致章节无法发布的硬伤 | 必须修复后才能通过审查，不可 Override | 时间倒流、死人复活、能力越权 |
| **high** | 严重影响阅读体验的问题 | 必须修复，可用 Override Contract 延期 | 伏笔矛盾、角色 OOC、钩子完全缺失 |
| **medium** | 影响质量但不致命 | 建议修复，可用 Override Contract 承诺后续补偿 | 微兑现不足、节奏略缓、段落过长 |
| **low** | 可改善的细节 | 可选修复，记录但不阻断 | 用词重复、标点习惯、过渡句可优化 |

---

## 跨 Checker 统一映射

### 时间逻辑问题

| 问题 | consistency | continuity | 统一标准 |
|------|-----------|-----------|---------|
| 倒计时算术错误 | critical | — | **critical** |
| 时间回跳（无闪回标记） | critical | C 级 → **critical** | **critical** |
| 大跨度时间跳跃无过渡 | high | — | **high** |
| 时间模糊但不矛盾 | low | — | **low** |

### 角色行为问题

| 问题 | ooc | continuity | 统一标准 |
|------|-----|-----------|---------|
| 性格根本性矛盾 | 严重 → **critical** | — | **critical** |
| 行为动机不充分 | 中度 → **high** | 逻辑漏洞 → **high** | **high** |
| 轻微性格偏差 | 轻微 → **medium** | — | **medium** |

### 伏笔管理问题

| 问题 | continuity | reader-pull | 统一标准 |
|------|-----------|------------|---------|
| 核心伏笔遗忘（>30 章） | high | — | **high** |
| 支线伏笔遗忘（>50 章） | medium | SOFT → **medium** | **medium** |
| 装饰伏笔遗忘 | low | — | **low** |
| 活跃悬念（有效未闭合） | — | 正常（非问题） | **正常** |

### 读者体验问题

| 问题 | reader-pull | high-point | 统一标准 |
|------|-----------|-----------|---------|
| 章末无任何钩子 | HARD → **critical** | — | **critical** |
| 连续 3 章无爽点 | — | high | **high** |
| 微兑现不足 | SOFT → **medium** | — | **medium** |
| 爽点模式重复 | — | medium | **medium** |

### Anti-AI 问题

| 问题 | 统一标准 |
|------|---------|
| 全文对话风格完全一致 | **high** |
| risk_score > 60 | **high** |
| risk_score 30-60 | **medium** |
| risk_score < 30 | **low** |

---

## Checker 输出格式规范

所有 Checker 必须使用统一的 issues 数组格式：

```json
{
  "agent": "checker-name",
  "chapter": 42,
  "overall_score": 85,
  "pass": true,
  "issues": [
    {
      "id": "CHECKER_ISSUE_001",
      "severity": "critical | high | medium | low",
      "type": "问题分类",
      "location": "具体位置",
      "description": "问题描述",
      "can_override": false,
      "fix_suggestion": "修复建议"
    }
  ],
  "metrics": {},
  "summary": "..."
}
```

**禁止**：
- 使用非标准 severity 值（如"严重""C 级""HARD""SOFT"）
- 在 issues 之外维护独立的 soft_suggestions 数组
- 使用 dimensions 结构替代 issues 数组
