"""ink_writer.prompt_cache — Anthropic prompt cache 优化模块

将 system prompt 拆分为稳定段（cache-friendly）和易变段，
通过 cache_control 标注最大化缓存命中率。
"""

from ink_writer.prompt_cache.config import PromptCacheConfig, load_config
from ink_writer.prompt_cache.segmenter import (
    CacheableMessage,
    SegmentType,
    segment_system_prompt,
)
from ink_writer.prompt_cache.metrics import CacheMetricsTracker

__all__ = [
    "PromptCacheConfig",
    "load_config",
    "CacheableMessage",
    "SegmentType",
    "segment_system_prompt",
    "CacheMetricsTracker",
]
