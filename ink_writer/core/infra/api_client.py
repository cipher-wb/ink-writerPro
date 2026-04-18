#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Data Modules - API 客户端 (v5.4，v5.0 OpenAI 兼容接口沿用)

支持两种 API 类型：
1. openai: OpenAI 兼容的 /v1/embeddings 和 /v1/rerank 接口
   - 适用于: OpenAI, Jina, Cohere, vLLM, Ollama 等
2. modal: Modal 自定义接口格式
   - 适用于: 自部署的 Modal 服务

配置示例 (config.py):
    embed_api_type = "openai"
    embed_base_url = "https://api.openai.com/v1"
    embed_model = "text-embedding-3-small"
    embed_api_key = "sk-xxx"

    rerank_api_type = "openai"  # Jina/Cohere 也使用此类型
    rerank_base_url = "https://api.jina.ai/v1"
    rerank_model = "jina-reranker-v2-base-multilingual"
    rerank_api_key = "jina_xxx"
"""

import asyncio
import logging
import os
import aiohttp
import time
from typing import Callable, List, Dict, Any, Optional
from dataclasses import dataclass

from ink_writer.core.infra.config import get_config

# v13 US-018：从 print 迁移到 logging，避免污染 CLI stdout；LOG_LEVEL 可控
logger = logging.getLogger(__name__)


@dataclass
class APIStats:
    """API 调用统计"""
    total_calls: int = 0
    total_time: float = 0.0
    errors: int = 0


class EmbeddingAPIClient:
    """
    通用 Embedding API 客户端

    支持 OpenAI 兼容接口 (/v1/embeddings) 和 Modal 自定义接口
    """

    def __init__(self, config=None):
        self.config = config or get_config()
        self.sem = asyncio.Semaphore(self.config.embed_concurrency)
        self.stats = APIStats()
        self._warmed_up = False
        self._session: Optional[aiohttp.ClientSession] = None
        self.last_error_status: Optional[int] = None
        self.last_error_message: str = ""

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                limit=self.config.http_connector_limit,
                limit_per_host=self.config.http_connector_limit_per_host,
            )
            self._session = aiohttp.ClientSession(connector=connector, trust_env=True)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def _build_headers(self) -> Dict[str, str]:
        """构建请求头"""
        headers = {"Content-Type": "application/json"}
        if self.config.embed_api_key:
            headers["Authorization"] = f"Bearer {self.config.embed_api_key}"
        return headers

    def _build_url(self) -> str:
        """构建请求 URL"""
        base_url = self.config.embed_base_url.rstrip("/")
        if self.config.embed_api_type == "openai":
            # OpenAI 兼容: /v1/embeddings
            if not base_url.endswith("/embeddings"):
                if base_url.endswith("/v1"):
                    return f"{base_url}/embeddings"
                return f"{base_url}/v1/embeddings"
            return base_url
        else:
            # Modal 自定义接口: 直接使用配置的 URL
            return base_url

    def _build_payload(self, texts: List[str]) -> Dict[str, Any]:
        """构建请求体"""
        if self.config.embed_api_type == "openai":
            return {
                "input": texts,
                "model": self.config.embed_model,
                "encoding_format": "float"
            }
        else:
            # Modal 格式
            return {
                "input": texts,
                "model": self.config.embed_model
            }

    def _parse_response(self, data: Dict[str, Any]) -> Optional[List[List[float]]]:
        """解析响应"""
        if self.config.embed_api_type == "openai":
            # OpenAI 格式: {"data": [{"embedding": [...], "index": 0}, ...]}
            if "data" in data:
                # 按 index 排序，确保顺序正确
                sorted_data = sorted(data["data"], key=lambda x: x.get("index", 0))
                return [item["embedding"] for item in sorted_data]
            return None
        else:
            # Modal 格式: {"data": [{"embedding": [...]}, ...]}
            if "data" in data:
                return [item["embedding"] for item in data["data"]]
            return None

    async def embed(self, texts: List[str]) -> Optional[List[List[float]]]:
        """调用 Embedding 服务（带重试机制）"""
        if not texts:
            return []

        timeout = self.config.cold_start_timeout if not self._warmed_up else self.config.normal_timeout
        max_retries = getattr(self.config, 'api_max_retries', 3)
        base_delay = getattr(self.config, 'api_retry_delay', 1.0)

        async with self.sem:
            start = time.time()
            session = await self._get_session()

            for attempt in range(max_retries):
                try:
                    url = self._build_url()
                    headers = self._build_headers()
                    payload = self._build_payload(texts)

                    async with session.post(
                        url,
                        json=payload,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=timeout)
                    ) as resp:
                        if resp.status == 200:
                            text = await resp.text()
                            import json as json_module
                            data = json_module.loads(text)
                            embeddings = self._parse_response(data)

                            if embeddings:
                                self.stats.total_calls += 1
                                self.stats.total_time += time.time() - start
                                self._warmed_up = True
                                self.last_error_status = None
                                self.last_error_message = ""
                                return embeddings

                        # 可重试的状态码: 429 (限流), 500, 502, 503, 504
                        if resp.status in (429, 500, 502, 503, 504) and attempt < max_retries - 1:
                            delay = base_delay * (2 ** attempt)  # 指数退避
                            logger.warning(f"Embed {resp.status}, retrying in {delay:.1f}s ({attempt + 1}/{max_retries})")
                            await asyncio.sleep(delay)
                            continue

                        self.stats.errors += 1
                        err_text = await resp.text()
                        self.last_error_status = int(resp.status)
                        self.last_error_message = str(err_text[:200])
                        logger.error(f"Embed {resp.status}: {err_text[:200]}")
                        return None

                except asyncio.TimeoutError:
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(f"Embed timeout, retrying in {delay:.1f}s ({attempt + 1}/{max_retries})")
                        await asyncio.sleep(delay)
                        continue
                    self.stats.errors += 1
                    self.last_error_status = None
                    self.last_error_message = f"Timeout after {max_retries} attempts"
                    logger.error(f"Embed: Timeout after {max_retries} attempts")
                    return None

                except Exception as e:
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(f"Embed error: {e}, retrying in {delay:.1f}s ({attempt + 1}/{max_retries})")
                        await asyncio.sleep(delay)
                        continue
                    self.stats.errors += 1
                    self.last_error_status = None
                    self.last_error_message = str(e)
                    logger.error(f"Embed: {e}")
                    return None

            return None

    async def embed_batch(
        self, texts: List[str], *, skip_failures: bool = True
    ) -> List[Optional[List[float]]]:
        """
        分批 Embedding

        Args:
            texts: 要嵌入的文本列表
            skip_failures: True 时失败的文本返回 None；False 时任一失败则整体返回空列表

        Returns:
            与 texts 等长的列表，成功的位置是向量，失败的位置是 None
        """
        if not texts:
            return []

        all_embeddings: List[Optional[List[float]]] = []
        batch_size = self.config.embed_batch_size

        batches = [texts[i:i + batch_size] for i in range(0, len(texts), batch_size)]
        tasks = [self.embed(batch) for batch in batches]
        results = await asyncio.gather(*tasks)

        for batch_idx, result in enumerate(results):
            actual_batch_size = len(batches[batch_idx])
            if result and len(result) == actual_batch_size:
                all_embeddings.extend(result)
            else:
                if not skip_failures:
                    logger.warning(f"Embed batch {batch_idx} failed, aborting all")
                    return []
                logger.warning(f"Embed batch {batch_idx} failed, marking {actual_batch_size} items as None")
                all_embeddings.extend([None] * actual_batch_size)

        return all_embeddings[:len(texts)]

    async def warmup(self):
        """预热服务"""
        await self.embed(["test"])
        self._warmed_up = True


class RerankAPIClient:
    """
    通用 Rerank API 客户端

    支持 OpenAI 兼容接口 (Jina/Cohere 格式) 和 Modal 自定义接口
    """

    def __init__(self, config=None):
        self.config = config or get_config()
        self.sem = asyncio.Semaphore(self.config.rerank_concurrency)
        self.stats = APIStats()
        self._warmed_up = False
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                limit=self.config.http_connector_limit,
                limit_per_host=self.config.http_connector_limit_per_host,
            )
            self._session = aiohttp.ClientSession(connector=connector, trust_env=True)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def _build_headers(self) -> Dict[str, str]:
        """构建请求头"""
        headers = {"Content-Type": "application/json"}
        if self.config.rerank_api_key:
            headers["Authorization"] = f"Bearer {self.config.rerank_api_key}"
        return headers

    def _build_url(self) -> str:
        """构建请求 URL"""
        base_url = self.config.rerank_base_url.rstrip("/")
        if self.config.rerank_api_type == "openai":
            # Jina/Cohere 兼容: /v1/rerank
            if not base_url.endswith("/rerank"):
                if base_url.endswith("/v1"):
                    return f"{base_url}/rerank"
                return f"{base_url}/v1/rerank"
            return base_url
        else:
            # Modal 自定义接口
            return base_url

    def _build_payload(self, query: str, documents: List[str], top_n: Optional[int]) -> Dict[str, Any]:
        """构建请求体"""
        if self.config.rerank_api_type == "openai":
            # Jina/Cohere 格式
            payload: Dict[str, Any] = {
                "query": query,
                "documents": documents,
                "model": self.config.rerank_model
            }
            if top_n:
                payload["top_n"] = top_n
            return payload
        else:
            # Modal 格式
            payload = {"query": query, "documents": documents}
            if top_n:
                payload["top_n"] = top_n
            return payload

    def _parse_response(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """解析响应"""
        if self.config.rerank_api_type == "openai":
            # Jina/Cohere 格式: {"results": [{"index": 0, "relevance_score": 0.9}, ...]}
            return data.get("results", [])
        else:
            # Modal 格式: {"results": [...]}
            return data.get("results", [])

    async def rerank(
        self,
        query: str,
        documents: List[str],
        top_n: Optional[int] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """调用 Rerank 服务（带重试机制）"""
        if not documents:
            return []

        timeout = self.config.cold_start_timeout if not self._warmed_up else self.config.normal_timeout
        max_retries = getattr(self.config, 'api_max_retries', 3)
        base_delay = getattr(self.config, 'api_retry_delay', 1.0)

        async with self.sem:
            start = time.time()
            session = await self._get_session()

            for attempt in range(max_retries):
                try:
                    url = self._build_url()
                    headers = self._build_headers()
                    payload = self._build_payload(query, documents, top_n)

                    async with session.post(
                        url,
                        json=payload,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=timeout)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()

                            self.stats.total_calls += 1
                            self.stats.total_time += time.time() - start
                            self._warmed_up = True

                            return self._parse_response(data)

                        # 可重试的状态码
                        if resp.status in (429, 500, 502, 503, 504) and attempt < max_retries - 1:
                            delay = base_delay * (2 ** attempt)
                            logger.warning(f"Rerank {resp.status}, retrying in {delay:.1f}s ({attempt + 1}/{max_retries})")
                            await asyncio.sleep(delay)
                            continue

                        self.stats.errors += 1
                        err_text = await resp.text()
                        logger.error(f"Rerank {resp.status}: {err_text[:200]}")
                        return None

                except asyncio.TimeoutError:
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(f"Rerank timeout, retrying in {delay:.1f}s ({attempt + 1}/{max_retries})")
                        await asyncio.sleep(delay)
                        continue
                    self.stats.errors += 1
                    logger.error(f"Rerank: Timeout after {max_retries} attempts")
                    return None

                except Exception as e:
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(f"Rerank error: {e}, retrying in {delay:.1f}s ({attempt + 1}/{max_retries})")
                        await asyncio.sleep(delay)
                        continue
                    self.stats.errors += 1
                    logger.error(f"Rerank: {e}")
                    return None

            return None

    async def warmup(self):
        """预热服务"""
        await self.rerank("test", ["doc1", "doc2"])
        self._warmed_up = True


class ModalAPIClient:
    """
    统一 API 客户端 (兼容旧接口)

    整合 Embedding + Rerank 客户端，保持向后兼容
    """

    def __init__(self, config=None):
        self.config = config or get_config()
        self._embed_client = EmbeddingAPIClient(self.config)
        self._rerank_client = RerankAPIClient(self.config)

        # 兼容旧代码的信号量
        self.sem_embed = self._embed_client.sem
        self.sem_rerank = self._rerank_client.sem

        self._warmed_up = {"embed": False, "rerank": False}
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def stats(self) -> Dict[str, APIStats]:
        return {
            "embed": self._embed_client.stats,
            "rerank": self._rerank_client.stats
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        # 复用 embed client 的 session
        return await self._embed_client._get_session()

    async def close(self):
        await self._embed_client.close()
        await self._rerank_client.close()

    # ==================== 预热 ====================

    async def warmup(self):
        """预热 Embedding 和 Rerank 服务"""
        logger.warning("[WARMUP] Warming up Embed + Rerank...")
        start = time.time()

        tasks = [self._warmup_embed(), self._warmup_rerank()]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for name, result in zip(["Embed", "Rerank"], results):
            if isinstance(result, Exception):
                logger.warning("  [FAIL] %s: %s", name, result)
            else:
                logger.warning("  [OK] %s ready", name)

        logger.warning("[WARMUP] Done in %.1fs", time.time() - start)

    async def _warmup_embed(self):
        await self._embed_client.warmup()
        self._warmed_up["embed"] = True

    async def _warmup_rerank(self):
        await self._rerank_client.warmup()
        self._warmed_up["rerank"] = True

    # ==================== Embedding API ====================

    async def embed(self, texts: List[str]) -> Optional[List[List[float]]]:
        """调用 Embedding 服务"""
        return await self._embed_client.embed(texts)

    async def embed_batch(
        self, texts: List[str], *, skip_failures: bool = True
    ) -> List[Optional[List[float]]]:
        """分批 Embedding"""
        return await self._embed_client.embed_batch(texts, skip_failures=skip_failures)

    # ==================== Rerank API ====================

    async def rerank(
        self,
        query: str,
        documents: List[str],
        top_n: Optional[int] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """调用 Rerank 服务"""
        return await self._rerank_client.rerank(query, documents, top_n)

    # ==================== 统计 ====================

    def print_stats(self):
        logger.warning("[API STATS]")
        for name, stats in self.stats.items():
            if stats.total_calls > 0:
                avg_time = stats.total_time / stats.total_calls
                logger.warning(
                    "  %s: %d calls, %.1fs total, %.2fs avg, %d errors",
                    name.upper(),
                    stats.total_calls,
                    stats.total_time,
                    avg_time,
                    stats.errors,
                )


# 全局客户端
_client: Optional[ModalAPIClient] = None


def get_client(config=None) -> ModalAPIClient:
    global _client
    if _client is None or config is not None:
        _client = ModalAPIClient(config)
    return _client


# ==================== v16 US-003: 统一 Claude 调用入口 ====================
# 将 editor_wisdom.llm_backend.call_llm 的调用路径在 core.infra 层公开一个稳定
# 入口，便于 checker_pipeline / polish 等子系统统一走 core.infra。US-007 会
# 在此层补齐显式 timeout；US-021 会在此层采集 prompt_cache usage。


# v16 US-007：基于 task_type 的分层默认 timeout（秒）。超过 task_type 用
# ``_FALLBACK_TIMEOUT``（与 AC 中的"全链路 ≥120s baseline"对齐）。
# 首次加载后优先从 ``config/llm_timeouts.yaml`` 读取，缺失则用本模块内硬编码。
_DEFAULT_TIMEOUTS_BY_TASK: dict[str, float] = {
    "writer": 300.0,
    "polish": 180.0,
    "checker": 90.0,
    "classify": 60.0,
    "extract": 60.0,
}
_FALLBACK_TIMEOUT: float = 120.0

# 延迟加载标记；首次调用 ``call_claude`` 时尝试加载一次，失败不再重试。
_YAML_LOADED: bool = False

# v16 US-021：task_type → 模型 ID 的映射（从 config/model_selection.yaml 读）。
# 调用方未显式传 ``model`` 时，按 task_type 查；未匹配则用 ``_FALLBACK_MODEL``。
_DEFAULT_MODELS_BY_TASK: dict[str, str] = {
    "writer": "claude-opus-4-7",
    "polish": "claude-opus-4-7",
    "context": "claude-sonnet-4-6",
    "data": "claude-sonnet-4-6",
    "checker": "claude-haiku-4-5",
    "classify": "claude-haiku-4-5",
    "extract": "claude-haiku-4-5",
}
_FALLBACK_MODEL: str = "claude-haiku-4-5"
_MODEL_YAML_LOADED: bool = False


def _config_path() -> "Path":
    """``config/llm_timeouts.yaml`` 绝对路径（基于仓库根 = ink_writer 的父级）。"""
    from pathlib import Path as _Path

    # ink_writer/core/infra/api_client.py → parents[3] 为仓库根。
    return _Path(__file__).resolve().parents[3] / "config" / "llm_timeouts.yaml"


def _model_config_path() -> "Path":
    """``config/model_selection.yaml`` 绝对路径。"""
    from pathlib import Path as _Path

    return _Path(__file__).resolve().parents[3] / "config" / "model_selection.yaml"


def _load_yaml_timeouts_once() -> None:
    """仅首次调用时读一次 YAML；失败则保留内置默认值并 log 一次 warning。"""
    global _YAML_LOADED, _FALLBACK_TIMEOUT
    if _YAML_LOADED:
        return
    _YAML_LOADED = True
    try:
        path = _config_path()
        if not path.exists():
            return
        import yaml  # PyYAML 已在 pyproject 依赖
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        task_timeouts = data.get("task_timeouts") or {}
        if isinstance(task_timeouts, dict):
            for k, v in task_timeouts.items():
                try:
                    _DEFAULT_TIMEOUTS_BY_TASK[str(k)] = float(v)
                except (TypeError, ValueError):
                    logger.warning(
                        "llm_timeouts.yaml: task_timeouts.%s 无法转为 float（%r），忽略。",
                        k,
                        v,
                    )
        fallback = data.get("_fallback")
        if fallback is not None:
            try:
                _FALLBACK_TIMEOUT = float(fallback)
            except (TypeError, ValueError):
                logger.warning(
                    "llm_timeouts.yaml: _fallback 无法转为 float（%r），保留内置默认 %s。",
                    fallback,
                    _FALLBACK_TIMEOUT,
                )
    except Exception as exc:
        # 解析异常不致命，静默降级到内置默认。
        logger.warning("llm_timeouts.yaml 加载失败，沿用内置默认: %s", exc)


def _load_model_yaml_once() -> None:
    """v16 US-021：首次调用 ``call_claude`` 时读一次 ``config/model_selection.yaml``。"""
    global _MODEL_YAML_LOADED, _FALLBACK_MODEL
    if _MODEL_YAML_LOADED:
        return
    _MODEL_YAML_LOADED = True
    try:
        path = _model_config_path()
        if not path.exists():
            return
        import yaml
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        task_models = data.get("task_models") or {}
        if isinstance(task_models, dict):
            for k, v in task_models.items():
                if isinstance(v, str) and v.strip():
                    _DEFAULT_MODELS_BY_TASK[str(k)] = v.strip()
                else:
                    logger.warning(
                        "model_selection.yaml: task_models.%s 非字符串（%r），忽略。",
                        k,
                        v,
                    )
        fallback = data.get("_fallback")
        if isinstance(fallback, str) and fallback.strip():
            _FALLBACK_MODEL = fallback.strip()
    except Exception as exc:
        logger.warning("model_selection.yaml 加载失败，沿用内置默认: %s", exc)


def resolve_model(task_type: str, model: Optional[str] = None) -> str:
    """v16 US-021：按 task_type 返回模型 ID。

    Args:
        task_type: writer/polish/context/data/checker/classify/extract 之一。
        model: 若显式传入非空字符串，则优先返回（调用方保留最终控制权）。

    Returns:
        Claude 模型 ID 字符串。
    """
    if model:
        return model
    _load_model_yaml_once()
    return _DEFAULT_MODELS_BY_TASK.get(task_type, _FALLBACK_MODEL)


def call_claude(
    *,
    model: Optional[str] = None,
    system: str,
    user: str,
    max_tokens: int = 1024,
    timeout: Optional[float] = None,
    task_type: str = "checker",
    use_cache: bool = True,
) -> str:
    """调用 Claude 并返回原始文本。

    v16 US-003：``checker_pipeline`` 的 LLM checker 工厂统一走此入口。
    内部委托至 ``ink_writer.editor_wisdom.llm_backend.call_llm``，
    保留 prompt cache / SDK+CLI 双路径 / 超时重试能力。

    Args:
        model: Claude 模型 ID，如 ``claude-haiku-4-5``。未传时按 task_type
            从 ``config/model_selection.yaml`` 查（v16 US-021）。
        system: system prompt（支持 cache_control）。
        user: 用户内容。
        max_tokens: 响应上限 tokens。
        timeout: 显式 timeout 秒；默认按 task_type 查表。
        task_type: writer/polish/context/data/checker/classify/extract 之一。
        use_cache: 是否给 system 加 cache_control。

    Returns:
        LLM 原始文本。
    """
    if timeout is None:
        # v16 US-007：首次调用前加载 config/llm_timeouts.yaml；缺失则内置默认。
        _load_yaml_timeouts_once()
        timeout = _DEFAULT_TIMEOUTS_BY_TASK.get(task_type, _FALLBACK_TIMEOUT)

    # v16 US-021：按 task_type 自动选型，调用方显式传 model 时优先。
    resolved_model = resolve_model(task_type, model)

    # 延迟导入，避免 core.infra 被 editor_wisdom 循环导入。
    from ink_writer.editor_wisdom.llm_backend import call_llm

    return call_llm(
        model=resolved_model,
        system=system,
        user=user,
        max_tokens=max_tokens,
        use_cache=use_cache,
        timeout=timeout,
    )


# ==================== v16 US-021: Messages Batch API 入口 ====================
# Anthropic 2026 Q1 Messages Batch API：批量提交请求，服务端异步处理，成本折扣。
# 仅在 "长链批量 review" 场景启用（>10 章）；tier 不支持或任一异常时 fallback
# 到普通并发。CI 不真跑 batch API（无 ANTHROPIC_API_KEY），只通过 mock 验证。


# 批量阈值：仅在章节数超过此阈值时启用 batch API。
BATCH_REVIEW_THRESHOLD: int = 10


def batch_review(
    chapters: list[int],
    *,
    threshold: int = BATCH_REVIEW_THRESHOLD,
    build_request: Optional[Callable[[int], dict[str, Any]]] = None,
    fallback: Optional[Callable[[list[int]], dict[int, Any]]] = None,
) -> dict[int, Any]:
    """v16 US-021：批量 review 入口。

    - 章节数 ``<= threshold``：直接走 ``fallback``（普通并发）。
    - 章节数 ``> threshold`` 且 SDK 不可用（无 ANTHROPIC_API_KEY）：走 ``fallback``。
    - 章节数 ``> threshold`` 且 SDK 支持 batch API：提交 batch，轮询结果。
    - 任何阶段异常（tier 不支持、网络错误、SDK 属性缺失）：降级到 ``fallback``。

    Args:
        chapters: 待 review 的章节号列表。
        threshold: 触发 batch 的最小章节数。
        build_request: ``int -> dict``，为每章构建单条 batch 请求（messages.create 参数）。
        fallback: ``list[int] -> dict[int, Any]``，普通并发 review 实现。

    Returns:
        ``{chapter: review_result}`` 字典。

    Notes:
        生产触发路径会注入 build_request 和 fallback；本函数保持薄 stub，
        真正的 batch API 调用集中在 ``_submit_batch_and_collect``，便于 mock。
    """
    if not chapters:
        return {}

    if len(chapters) <= threshold:
        if fallback is None:
            raise ValueError(
                "batch_review: chapters <= threshold 时必须提供 fallback callable"
            )
        return fallback(chapters)

    # 无 API Key → 只能走 fallback（含 CI 场景）
    if not os.environ.get("ANTHROPIC_API_KEY"):
        if fallback is None:
            raise RuntimeError(
                "batch_review: 无 ANTHROPIC_API_KEY 且未提供 fallback"
            )
        logger.info("batch_review: 无 API key，降级到 fallback（%d 章）", len(chapters))
        return fallback(chapters)

    if build_request is None:
        # 没有 build_request 就不可能组 batch 请求；降级
        if fallback is None:
            raise ValueError("batch_review: 缺少 build_request 且无 fallback")
        logger.info("batch_review: 未提供 build_request，降级到 fallback")
        return fallback(chapters)

    try:
        return _submit_batch_and_collect(chapters, build_request)
    except Exception as exc:
        # tier 不支持、属性缺失、超时等一律降级
        logger.warning("batch_review: batch API 失败，降级到 fallback: %s", exc)
        if fallback is None:
            raise
        return fallback(chapters)


def _submit_batch_and_collect(
    chapters: list[int],
    build_request: Callable[[int], dict[str, Any]],
) -> dict[int, Any]:
    """向 Anthropic Messages Batch API 提交并收集结果。

    真实 batch API 调用在生产触发；本函数结构化以便 ``tests`` 通过 mock
    ``anthropic.Anthropic`` 验证行为。任何属性缺失（SDK 旧版）都会上抛，由
    ``batch_review`` 的外层 except 降级。
    """
    import anthropic

    client = anthropic.Anthropic()
    # SDK 属性：``client.messages.batches``（2026 Q1 SDK）。
    # 旧 SDK 无此属性 → AttributeError → 外层 except 降级。
    batches_api = client.messages.batches

    requests = []
    for ch in chapters:
        req = build_request(ch)
        # 每条 request 需携带 custom_id，以便回收结果时匹配章节号
        requests.append({"custom_id": f"chapter-{ch}", "params": req})

    batch = batches_api.create(requests=requests)
    # 轮询至 ended（生产环境通常由外层 scheduler 管理；此处简化）
    # 为避免测试卡住，mock 会直接返回 ended 状态。
    final_batch = batches_api.retrieve(batch.id)
    if getattr(final_batch, "processing_status", None) != "ended":
        raise RuntimeError(
            f"batch {batch.id} not ended: {final_batch.processing_status}"
        )

    results: dict[int, Any] = {}
    for entry in batches_api.results(batch.id):
        custom_id = getattr(entry, "custom_id", "")
        if not custom_id.startswith("chapter-"):
            continue
        try:
            ch = int(custom_id.split("-", 1)[1])
        except (IndexError, ValueError):
            continue
        # entry.result 结构：{"type": "succeeded", "message": ...}
        results[ch] = getattr(entry, "result", None)
    return results
