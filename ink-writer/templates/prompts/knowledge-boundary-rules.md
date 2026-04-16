<!-- version: 1.0.0 | changelog: initial extraction from writer-agent (2x) + consistency-checker -->

## 知识边界执行规则

执行包中"知识盲区清单（Knowledge Gate）"列出了本章出场实体的主角知情状态。

- **❌ 未知实体**：在主角内心独白、行为描写、对话中 → 只能使用 `known_descriptor`（如"那个猫女"、"手上的神秘印记"），**严禁使用 canonical_name**
- **✅ 已知实体**：可以正常使用 canonical_name
- **全知旁白例外**：若叙述视角切换为全知第三人称（段落开头有视角切换词，如"另一边"、"此刻远处"），可使用真名，但必须与主角 POV 段落有明确分隔
- **本章首次知晓**：若执行包标注某实体"本章习得（chapter_learned = 本章）"，则知识获取情节之前用 `known_descriptor`，情节发生后方可用 canonical_name
