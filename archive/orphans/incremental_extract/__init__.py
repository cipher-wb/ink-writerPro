"""ink_writer.incremental_extract — 增量数据提取模块

将 data-agent 的全量实体提取优化为 diff 模式：
- 对比 chapter N vs chapter N-1 的实体状态
- 仅提取新增/变更的实体和关系
- 跳过未变化的实体，减少 LLM 提取开销
"""

from ink_writer.incremental_extract.differ import (
    EntityDiff,
    DiffResult,
    compute_entity_diff,
)
from ink_writer.incremental_extract.config import IncrementalExtractConfig, load_config

__all__ = [
    "EntityDiff",
    "DiffResult",
    "compute_entity_diff",
    "IncrementalExtractConfig",
    "load_config",
]
