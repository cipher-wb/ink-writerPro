# JSON 输出规则（所有 LLM checker agent 统一引用）

本文件定义所有 checker agent 的 LLM 输出 JSON 格式要求，
适用于 glm-4.6 / deepseek-v4-pro / claude 系列等所有模型。

## 硬规则（Hard Rules）

1. **禁止 markdown fence**：不要用 \`\`\`json ... \`\`\` 包裹输出，直接输出裸 JSON。
2. **仅输出 JSON**：不要在 JSON 前后附加解释、说明或补充文字。
3. **字段必填**：每个 JSON 对象的全部字段都必须存在，不得省略。
4. **类型精确**：int 用整数（不加引号），float 用浮点数，string 用双引号。

## JSON Schema 示例

```json
[
  {
    "chapter_idx": 1,
    "agency_score": 0.72,
    "reason": "主角主动潜入敌营并做出关键决策"
  },
  {
    "chapter_idx": 2,
    "agency_score": 0.35,
    "reason": "被动卷入外部事件，无自主决策"
  }
]
```

- `chapter_idx`: int，必须与输入的章序号一致
- `agency_score`: float，0.0~1.0
- `reason`: string，≤60 字中文说明

## 重试指令（Retry Instruction）

若前一次输出的 JSON 无法被解析（格式错误 / 多余文本 / markdown fence），
下一次重试时必须严格输出裸 JSON，不添加任何其他文本：

> Your previous output was not valid JSON. Output ONLY the raw JSON array
> — no markdown fences, no explanation, no additional text. Start with `[`
> and end with `]`.
