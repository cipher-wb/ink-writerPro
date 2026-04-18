#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Style Sampler - 风格样本管理模块

管理高质量章节片段作为风格参考：
- 风格样本存储
- 按场景类型分类
- 样本选择策略
"""

import json
import sqlite3
import time
import re
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict, field
from datetime import datetime
from enum import Enum
from contextlib import contextmanager

from ink_writer.core.infra.config import get_config
from ink_writer.core.infra.observability import safe_append_perf_timing, safe_log_tool_call
from ink_writer.core.extract.anti_ai_lint import anti_ai_lint_text


class SceneType(Enum):
    """场景类型"""
    BATTLE = "战斗"
    DIALOGUE = "对话"
    DESCRIPTION = "描写"
    TRANSITION = "过渡"
    EMOTION = "情感"
    TENSION = "紧张"
    COMEDY = "轻松"


@dataclass
class StyleSample:
    """风格样本"""
    id: str
    chapter: int
    scene_type: str
    content: str
    score: float
    tags: List[str]
    features: Dict[str, Any] = field(default_factory=dict)
    lint: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""


class StyleSampler:
    """风格样本管理器"""

    def __init__(self, config=None):
        self.config = config or get_config()
        self._init_db()

    def _init_db(self):
        """初始化数据库"""
        self.config.ensure_dirs()
        with self._get_conn() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS samples (
                    id TEXT PRIMARY KEY,
                    chapter INTEGER,
                    scene_type TEXT,
                    content TEXT,
                    score REAL,
                    tags TEXT,
                    features_json TEXT,
                    lint_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_samples_type ON samples(scene_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_samples_score ON samples(score DESC)")
            self._ensure_column(cursor, "samples", "features_json", "TEXT")
            self._ensure_column(cursor, "samples", "lint_json", "TEXT")

            conn.commit()

    @contextmanager
    def _get_conn(self):
        """获取数据库连接（确保关闭，避免 Windows 下文件句柄泄漏导致无法清理临时目录）"""
        db_path = self.config.ink_dir / "style_samples.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
        finally:
            conn.close()

    def _ensure_column(self, cursor, table_name: str, column_name: str, column_def: str) -> None:
        rows = cursor.execute(f"PRAGMA table_info({table_name})").fetchall()
        existing = {str(row[1]) for row in rows if len(row) > 1}
        if column_name in existing:
            return
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")

    # ==================== 样本管理 ====================

    def add_sample(self, sample: StyleSample) -> bool:
        """添加风格样本"""
        sample.features = sample.features or self._extract_sample_features(sample.content, sample.scene_type)
        sample.lint = sample.lint or anti_ai_lint_text(sample.content)
        if not sample.lint.get("passed", False):
            return False

        with self._get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO samples
                    (id, chapter, scene_type, content, score, tags, features_json, lint_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    sample.id,
                    sample.chapter,
                    sample.scene_type,
                    sample.content,
                    sample.score,
                    json.dumps(sample.tags, ensure_ascii=False),
                    json.dumps(sample.features, ensure_ascii=False),
                    json.dumps(sample.lint, ensure_ascii=False),
                    sample.created_at or datetime.now().isoformat()
                ))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def get_samples_by_type(
        self,
        scene_type: str,
        limit: int = 5,
        min_score: float = 0.0
    ) -> List[StyleSample]:
        """按场景类型获取样本"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, chapter, scene_type, content, score, tags, features_json, lint_json, created_at
                FROM samples
                WHERE scene_type = ? AND score >= ?
                ORDER BY score DESC
                LIMIT ?
            """, (scene_type, min_score, limit))

            return [self._row_to_sample(row) for row in cursor.fetchall()]

    def get_best_samples(self, limit: int = 10) -> List[StyleSample]:
        """获取最高分样本"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, chapter, scene_type, content, score, tags, features_json, lint_json, created_at
                FROM samples
                ORDER BY score DESC
                LIMIT ?
            """, (limit,))

            return [self._row_to_sample(row) for row in cursor.fetchall()]

    def _row_to_sample(self, row) -> StyleSample:
        """将数据库行转换为样本对象"""
        return StyleSample(
            id=row[0],
            chapter=row[1],
            scene_type=row[2],
            content=row[3],
            score=row[4],
            tags=json.loads(row[5]) if row[5] else [],
            features=json.loads(row[6]) if len(row) > 6 and row[6] else {},
            lint=json.loads(row[7]) if len(row) > 7 and row[7] else {},
            created_at=row[8] if len(row) > 8 else row[6]
        )

    # ==================== 样本提取 ====================

    def extract_candidates(
        self,
        chapter: int,
        content: str,
        review_score: float,
        scenes: List[Dict]
    ) -> List[StyleSample]:
        """
        从章节中提取风格样本候选

        只有高分章节 (review_score >= 80) 才提取样本
        """
        if review_score < 80:
            return []

        candidates = []

        for scene in scenes:
            scene_type = self._classify_scene_type(scene)
            scene_content = scene.get("content", "")

            # 跳过过短的场景
            if len(scene_content) < 200:
                continue

            lint = self.lint_text(scene_content)
            if not lint.get("passed", False):
                continue

            # 创建样本
            sample = StyleSample(
                id=f"ch{chapter}_s{scene.get('index', 0)}",
                chapter=chapter,
                scene_type=scene_type,
                content=scene_content[:2000],  # 限制长度
                score=review_score / 100.0,
                tags=self._extract_tags(scene_content),
                features=self._extract_sample_features(scene_content, scene_type),
                lint=lint,
            )
            candidates.append(sample)

        return candidates

    def _classify_scene_type(self, scene: Dict) -> str:
        """分类场景类型"""
        summary = scene.get("summary", "").lower()
        content = scene.get("content", "").lower()

        # 简单关键词分类
        battle_keywords = ["战斗", "攻击", "出手", "拳", "剑", "杀", "打", "斗"]
        dialogue_keywords = ["说道", "问道", "笑道", "冷声", "对话"]
        emotion_keywords = ["心中", "感觉", "情", "泪", "痛", "喜"]
        tension_keywords = ["危险", "紧张", "恐惧", "压力"]

        text = summary + content

        if any(kw in text for kw in battle_keywords):
            return SceneType.BATTLE.value
        elif any(kw in text for kw in tension_keywords):
            return SceneType.TENSION.value
        elif any(kw in text for kw in dialogue_keywords):
            return SceneType.DIALOGUE.value
        elif any(kw in text for kw in emotion_keywords):
            return SceneType.EMOTION.value
        else:
            return SceneType.DESCRIPTION.value

    def _extract_tags(self, content: str) -> List[str]:
        """提取内容标签"""
        tags = []

        # 简单标签提取
        if "战斗" in content or "攻击" in content:
            tags.append("战斗")
        if "修炼" in content or "突破" in content:
            tags.append("修炼")
        if "对话" in content or "说道" in content:
            tags.append("对话")
        if "描写" in content or "景色" in content:
            tags.append("描写")

        return tags[:5]

    def _extract_sample_features(self, content: str, scene_type: str = "") -> Dict[str, Any]:
        """提取样本的可比较特征。"""
        text = str(content or "")
        compact = re.sub(r"\s+", "", text)
        sentences = [seg.strip() for seg in re.split(r"[。！？!?；;\n]+", text) if seg.strip()]
        sentence_lengths = [len(re.sub(r"\s+", "", seg)) for seg in sentences if seg]
        avg_sentence_len = (
            round(sum(sentence_lengths) / len(sentence_lengths), 2) if sentence_lengths else 0.0
        )
        dialogue_chars = sum(len(match.group(0)) for match in re.finditer(r"“[^”]*”", text))
        dialogue_ratio = round(dialogue_chars / max(1, len(compact)), 4)
        paragraph_count = len([seg for seg in re.split(r"\n{2,}", text) if seg.strip()])

        keyword_counts = {}
        for token in re.findall(r"[\u4e00-\u9fff]{2,4}", compact):
            if len(token) < 2:
                continue
            keyword_counts[token] = keyword_counts.get(token, 0) + 1
        top_terms = [
            token
            for token, _ in sorted(keyword_counts.items(), key=lambda item: item[1], reverse=True)[:8]
        ]

        return {
            "scene_type": scene_type,
            "length": len(compact),
            "sentence_count": len(sentences),
            "avg_sentence_len": avg_sentence_len,
            "dialogue_ratio": dialogue_ratio,
            "paragraph_count": paragraph_count,
            "top_terms": top_terms,
        }

    def lint_text(self, text: str) -> Dict[str, Any]:
        """运行 Anti-AI lint。"""
        return anti_ai_lint_text(text)

    # ==================== 样本选择 ====================

    def select_samples_for_chapter(
        self,
        chapter_outline: str,
        target_types: List[str] = None,
        max_samples: int = 3
    ) -> List[StyleSample]:
        """
        为章节写作选择合适的风格样本

        基于大纲分析需要什么类型的样本
        """
        if target_types is None:
            # 根据大纲推断需要的场景类型
            target_types = self._infer_scene_types(chapter_outline)

        target_profile = self._infer_target_profile(chapter_outline, target_types)
        candidate_pool: List[StyleSample] = []
        for scene_type in target_types:
            candidate_pool.extend(self.get_samples_by_type(scene_type, limit=max_samples * 4, min_score=0.8))

        if not candidate_pool:
            candidate_pool = self.get_best_samples(limit=max_samples * 5)

        scored = sorted(
            candidate_pool,
            key=lambda sample: self._score_sample_for_target(sample, target_profile),
            reverse=True,
        )
        chosen: List[StyleSample] = []
        seen_ids = set()
        for sample in scored:
            if sample.id in seen_ids:
                continue
            if not (sample.lint or {}).get("passed", True):
                continue
            chosen.append(sample)
            seen_ids.add(sample.id)
            if len(chosen) >= max_samples:
                break

        return chosen

    def _infer_scene_types(self, outline: str) -> List[str]:
        """从大纲推断需要的场景类型"""
        types = []

        if any(kw in outline for kw in ["战斗", "对决", "比试", "交手"]):
            types.append(SceneType.BATTLE.value)

        if any(kw in outline for kw in ["对话", "谈话", "商议", "讨论"]):
            types.append(SceneType.DIALOGUE.value)

        if any(kw in outline for kw in ["情感", "感情", "心理"]):
            types.append(SceneType.EMOTION.value)

        if not types:
            types = [SceneType.DESCRIPTION.value]

        return types

    def _infer_target_profile(self, outline: str, target_types: List[str]) -> Dict[str, Any]:
        outline = str(outline or "")
        outline_terms = set(re.findall(r"[\u4e00-\u9fff]{2,4}", outline))
        if SceneType.DIALOGUE.value in target_types:
            dialogue_ratio = 0.42
            avg_sentence_len = 15.0
        elif SceneType.BATTLE.value in target_types:
            dialogue_ratio = 0.12
            avg_sentence_len = 14.0
        elif SceneType.EMOTION.value in target_types:
            dialogue_ratio = 0.28
            avg_sentence_len = 20.0
        else:
            dialogue_ratio = 0.18
            avg_sentence_len = 22.0

        return {
            "scene_types": target_types,
            "dialogue_ratio": dialogue_ratio,
            "avg_sentence_len": avg_sentence_len,
            "outline_terms": outline_terms,
        }

    def _score_sample_for_target(self, sample: StyleSample, target_profile: Dict[str, Any]) -> float:
        features = sample.features or self._extract_sample_features(sample.content, sample.scene_type)
        lint = sample.lint or self.lint_text(sample.content)
        if not lint.get("passed", False):
            return -1.0

        score = float(sample.score)
        if sample.scene_type in set(target_profile.get("scene_types", [])):
            score += 0.25

        sample_dialogue = float(features.get("dialogue_ratio", 0.0) or 0.0)
        target_dialogue = float(target_profile.get("dialogue_ratio", 0.0) or 0.0)
        score += max(0.0, 0.18 - abs(sample_dialogue - target_dialogue))

        sample_sentence_len = float(features.get("avg_sentence_len", 0.0) or 0.0)
        target_sentence_len = float(target_profile.get("avg_sentence_len", 0.0) or 0.0)
        if target_sentence_len > 0:
            score += max(0.0, 0.14 - (abs(sample_sentence_len - target_sentence_len) / target_sentence_len))

        sample_terms = set(features.get("top_terms", []) or [])
        outline_terms = set(target_profile.get("outline_terms", set()) or set())
        term_overlap = len(sample_terms & outline_terms)
        score += min(0.16, term_overlap * 0.04)

        score += float(lint.get("score", 0.0)) * 0.15
        return score

    # ==================== Benchmark Style RAG ====================

    def get_benchmark_samples(
        self,
        genre: str = "",
        scene_type: str = "",
        emotion: str = "",
        max_samples: int = 3,
    ) -> List[Dict[str, Any]]:
        """从 benchmark/style_rag.db 检索标杆风格样本"""
        # 定位 style_rag.db
        rag_db_path = Path(__file__).parent.parent.parent.parent / "benchmark" / "style_rag.db"
        if not rag_db_path.exists():
            return []

        try:
            conn = sqlite3.connect(str(rag_db_path))
            where_clauses = []
            params: list = []

            if genre:
                where_clauses.append("book_genre LIKE ?")
                params.append(f"%{genre}%")
            if scene_type:
                where_clauses.append("scene_type = ?")
                params.append(scene_type)
            if emotion:
                where_clauses.append("emotion = ?")
                params.append(emotion)

            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
            params.append(max_samples)

            rows = conn.execute(f"""
                SELECT book_title, book_genre, scene_type, emotion,
                       content, word_count, avg_sentence_length,
                       dialogue_ratio, exclamation_density, quality_score
                FROM style_fragments
                WHERE {where_sql}
                ORDER BY quality_score DESC
                LIMIT ?
            """, params).fetchall()

            conn.close()

            results = []
            for row in rows:
                # 截取前300字作为参考（避免执行包过大）
                content_excerpt = row[4][:300]
                if len(row[4]) > 300:
                    # 找到最近的句号截断
                    last_period = content_excerpt.rfind('。')
                    if last_period > 100:
                        content_excerpt = content_excerpt[:last_period + 1]
                    content_excerpt += "……"

                results.append({
                    "book_title": row[0],
                    "book_genre": row[1],
                    "scene_type": row[2],
                    "emotion": row[3],
                    "content_excerpt": content_excerpt,
                    "word_count": row[5],
                    "avg_sentence_length": row[6],
                    "dialogue_ratio": round(row[7], 3),
                    "exclamation_density": row[8],
                    "quality_score": row[9],
                })

            return results

        except Exception:
            return []

    def select_benchmark_for_chapter(
        self,
        chapter_outline: str,
        genre: str = "",
        max_samples: int = 3,
    ) -> List[Dict[str, Any]]:
        """为章节写作选择标杆风格参考样本"""
        # 推断场景类型和情绪
        scene_types = self._infer_scene_types(chapter_outline)
        scene_type = scene_types[0] if scene_types else ""

        # 推断情绪
        emotion = ""
        emotion_keywords = {
            "紧张": ["危险", "战斗", "死", "逃", "追"],
            "热血": ["突破", "爆发", "觉醒", "逆转", "反击"],
            "悲伤": ["死", "离别", "失去", "牺牲"],
            "温馨": ["温暖", "关心", "陪伴", "家"],
        }
        for emo, keywords in emotion_keywords.items():
            if any(kw in chapter_outline for kw in keywords):
                emotion = emo
                break

        samples = self.get_benchmark_samples(
            genre=genre,
            scene_type=scene_type,
            emotion=emotion,
            max_samples=max_samples,
        )

        # 如果精确匹配不足，放宽条件
        if len(samples) < max_samples:
            fallback = self.get_benchmark_samples(
                genre=genre,
                scene_type=scene_type,
                max_samples=max_samples - len(samples),
            )
            existing_titles = {s["book_title"] for s in samples}
            for s in fallback:
                if s["book_title"] not in existing_titles:
                    samples.append(s)
                    if len(samples) >= max_samples:
                        break

        return samples

    # ==================== 统计 ====================

    def get_stats(self) -> Dict[str, Any]:
        """获取样本统计"""
        with self._get_conn() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM samples")
            total = cursor.fetchone()[0]

            cursor.execute("""
                SELECT scene_type, COUNT(*) as count
                FROM samples
                GROUP BY scene_type
            """)
            by_type = {row[0]: row[1] for row in cursor.fetchall()}

            cursor.execute("SELECT AVG(score) FROM samples")
            avg_score = cursor.fetchone()[0] or 0

            cursor.execute("SELECT lint_json FROM samples")
            lint_passed = 0
            for (raw_lint,) in cursor.fetchall():
                if not raw_lint:
                    continue
                try:
                    lint = json.loads(raw_lint)
                except json.JSONDecodeError:
                    continue
                if lint.get("passed", False):
                    lint_passed += 1

            return {
                "total": total,
                "by_type": by_type,
                "avg_score": round(avg_score, 3),
                "lint_passed": lint_passed,
            }


# ==================== CLI 接口 ====================

def main():
    import argparse
    import sys
    from ink_writer.core.cli.cli_output import print_success, print_error
    from ink_writer.core.cli.cli_args import normalize_global_project_root, load_json_arg
    from ink_writer.core.index.index_manager import IndexManager

    parser = argparse.ArgumentParser(description="Style Sampler CLI")
    parser.add_argument("--project-root", type=str, help="项目根目录")

    subparsers = parser.add_subparsers(dest="command")

    # 获取统计
    subparsers.add_parser("stats")

    # 列出样本
    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--type", help="按类型过滤")
    list_parser.add_argument("--limit", type=int, default=10)

    # 提取样本
    extract_parser = subparsers.add_parser("extract")
    extract_parser.add_argument("--chapter", type=int, required=True)
    extract_parser.add_argument("--score", type=float, required=True)
    extract_parser.add_argument("--scenes", required=True, help="JSON 格式的场景列表")

    # 选择样本（自身产出）
    select_parser = subparsers.add_parser("select")
    select_parser.add_argument("--outline", required=True, help="章节大纲")
    select_parser.add_argument("--max", type=int, default=3)

    # 选择标杆样本（Style RAG）
    bench_parser = subparsers.add_parser("benchmark")
    bench_parser.add_argument("--outline", required=True, help="章节大纲")
    bench_parser.add_argument("--genre", default="", help="题材过滤")
    bench_parser.add_argument("--max", type=int, default=3)

    argv = normalize_global_project_root(sys.argv[1:])
    args = parser.parse_args(argv)
    command_started_at = time.perf_counter()

    # 初始化
    config = None
    if args.project_root:
        # 允许传入“工作区根目录”，统一解析到真正的 book project_root（必须包含 .ink/state.json）
        from project_locator import resolve_project_root
        from ink_writer.core.infra.config import DataModulesConfig

        try:
            resolved_root = resolve_project_root(args.project_root)
        except FileNotFoundError:
            resolved_root = Path(args.project_root).expanduser().resolve()
        config = DataModulesConfig.from_project_root(resolved_root)

    sampler = StyleSampler(config)
    logger = IndexManager(config)
    tool_name = f"style_sampler:{args.command or 'unknown'}"

    def _append_timing(success: bool, *, error_code: str | None = None, error_message: str | None = None, chapter: int | None = None):
        elapsed_ms = int((time.perf_counter() - command_started_at) * 1000)
        safe_append_perf_timing(
            sampler.config.project_root,
            tool_name=tool_name,
            success=success,
            elapsed_ms=elapsed_ms,
            chapter=chapter,
            error_code=error_code,
            error_message=error_message,
        )

    def emit_success(data=None, message: str = "ok", chapter: int | None = None):
        print_success(data, message=message)
        safe_log_tool_call(logger, tool_name=tool_name, success=True)
        _append_timing(True, chapter=chapter)

    def emit_error(code: str, message: str, suggestion: str | None = None, chapter: int | None = None):
        print_error(code, message, suggestion=suggestion)
        safe_log_tool_call(
            logger,
            tool_name=tool_name,
            success=False,
            error_code=code,
            error_message=message,
        )
        _append_timing(False, error_code=code, error_message=message, chapter=chapter)

    if args.command == "stats":
        stats = sampler.get_stats()
        emit_success(stats, message="stats")

    elif args.command == "list":
        if args.type:
            samples = sampler.get_samples_by_type(args.type, args.limit)
        else:
            samples = sampler.get_best_samples(args.limit)
        emit_success([s.__dict__ for s in samples], message="samples")

    elif args.command == "extract":
        scenes = load_json_arg(args.scenes)
        candidates = sampler.extract_candidates(
            chapter=args.chapter,
            content="",
            review_score=args.score,
            scenes=scenes,
        )

        added = []
        skipped = []
        for c in candidates:
            if sampler.add_sample(c):
                added.append(c.id)
            else:
                skipped.append(c.id)
        emit_success({"added": added, "skipped": skipped}, message="extracted", chapter=args.chapter)

    elif args.command == "select":
        samples = sampler.select_samples_for_chapter(args.outline, max_samples=args.max)
        emit_success([s.__dict__ for s in samples], message="selected")

    elif args.command == "benchmark":
        samples = sampler.select_benchmark_for_chapter(
            chapter_outline=args.outline,
            genre=args.genre,
            max_samples=args.max,
        )
        emit_success(samples, message="benchmark_selected")

    else:
        emit_error("UNKNOWN_COMMAND", "未指定有效命令", suggestion="请查看 --help")


if __name__ == "__main__":
    main()
