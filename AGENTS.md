# Ink Writer Pro - Agent 指南

## 编辑智慧模块

基于编辑星河 288 份金牌编辑建议的本地 RAG 系统，为写作流水线提供硬约束和质量门禁。

详细文档：[docs/editor-wisdom-integration.md](docs/editor-wisdom-integration.md)

### Top 3 注意事项

1. **配置优先**：所有行为受 `config/editor-wisdom.yaml` 控制，`enabled: false` 可完全关闭模块，各 inject_into 标志可分别关闭 context/writer/polish 注入
2. **黄金三章双重标准**：第 1-3 章使用 `golden_three_threshold`（默认 0.85）而非 `hard_gate_threshold`（默认 0.75），且额外检查 opening/hook/golden_finger/character 四个类别
3. **修复循环有上限**：checker 分数低于阈值时触发 polish → re-check 循环，最多 3 次检查 + 2 次修复，超限后生成 `blocked.md` 阻止章节发出
