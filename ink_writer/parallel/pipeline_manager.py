"""章节级并发管线编排器。

将 ink-auto 的串行写作升级为 N 章并发流水线：
- 多个 CLI 进程同时写作不同章节
- 检查点在批次完成后统一运行
- 支持故障隔离：单章失败不影响其他进行中的章节

⚠️ **v13 US-023（FIX-02B）诚实降级声明**：
   当前仅 `parallel=1`（串行）安全。`parallel>1` 为实验特性：
   ChapterLockManager 尚未接入（原 docstring 声称接入为虚假陈述），
   多个 CLI 子进程并发写 `state.json` / `index.db` 存在数据损坏风险。
   真并发集成见 `tasks/design-fix-04-step3-gate-orchestrator.md` 后续迭代。
   即日起 `parallel>1` 会触发 RuntimeWarning；用户若坚持使用属自担风险。

TODO: 参考 tasks/design-fix-04-step3-gate-orchestrator.md Phase B/C，
      接入 ChapterLockManager（threading.local → asyncio.Lock）解除此限制。
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
import warnings
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class ChapterStatus(Enum):
    PENDING = "pending"
    WRITING = "writing"
    VERIFYING = "verifying"
    DONE = "done"
    FAILED = "failed"
    RETRYING = "retrying"
    TIMEOUT_FAILED = "timeout_failed"  # v13 US-013


@dataclass
class ChapterResult:
    chapter: int
    status: ChapterStatus
    start_time: float = 0.0
    end_time: float = 0.0
    word_count: int = 0
    log_file: str = ""
    error: str = ""

    @property
    def elapsed(self) -> float:
        if self.end_time >= self.start_time and self.end_time > 0:
            return self.end_time - self.start_time
        return 0.0


@dataclass
class PipelineConfig:
    project_root: Path
    plugin_root: Path
    parallel: int = 4
    cooldown: int = 10
    checkpoint_cooldown: int = 15
    platform: str = "claude"
    max_retries: int = 1
    # v13 US-013：单章超时（秒）。默认 1800（30min），可通过 INK_CHAPTER_TIMEOUT 环境变量覆盖
    chapter_timeout_s: int = int(os.environ.get("INK_CHAPTER_TIMEOUT", 1800))

    @property
    def scripts_dir(self) -> Path:
        return self.plugin_root / "scripts"

    @property
    def log_dir(self) -> Path:
        d = self.project_root / ".ink" / "logs" / "auto"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def ink_py(self) -> str:
        return str(self.scripts_dir / "ink.py")


@dataclass
class PipelineReport:
    results: list[ChapterResult] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0
    parallel: int = 1

    @property
    def completed(self) -> int:
        return sum(1 for r in self.results if r.status == ChapterStatus.DONE)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status == ChapterStatus.FAILED)

    @property
    def serial_total(self) -> float:
        return sum(r.elapsed for r in self.results if r.status == ChapterStatus.DONE)

    @property
    def wall_time(self) -> float:
        return self.end_time - self.start_time if self.end_time > 0 else 0.0

    @property
    def speedup(self) -> float:
        if self.wall_time <= 0:
            return 0.0
        return self.serial_total / self.wall_time

    def to_dict(self) -> dict:
        return {
            "parallel": self.parallel,
            "completed": self.completed,
            "failed": self.failed,
            "wall_time_s": round(self.wall_time, 1),
            "serial_total_s": round(self.serial_total, 1),
            "speedup": round(self.speedup, 2),
            "chapters": [
                {
                    "chapter": r.chapter,
                    "status": r.status.value,
                    "elapsed_s": round(r.elapsed, 1),
                    "word_count": r.word_count,
                    "error": r.error,
                }
                for r in self.results
            ],
        }


class PipelineManager:
    """N 章并发管线编排器。

    使用方式:
        config = PipelineConfig(project_root=..., plugin_root=..., parallel=4)
        mgr = PipelineManager(config)
        report = asyncio.run(mgr.run(total_chapters=20))
    """

    def __init__(self, config: PipelineConfig):
        self.config = config
        self._interrupted = False
        # v13 US-023（FIX-02B）：parallel>1 是实验特性（ChapterLockManager 未接入），
        # 显式警告用户有数据竞争风险
        if config.parallel > 1:
            warnings.warn(
                f"PipelineManager: parallel={config.parallel} > 1 is experimental. "
                f"ChapterLockManager is not yet integrated; concurrent state.json / "
                f"index.db writes may corrupt data. Recommend parallel=1 for production. "
                f"See tasks/design-fix-04-step3-gate-orchestrator.md for planned fix.",
                RuntimeWarning,
                stacklevel=2,
            )

    async def run(self, total_chapters: int) -> PipelineReport:
        """运行并发管线，写 total_chapters 章。"""
        report = PipelineReport(
            start_time=time.time(), parallel=self.config.parallel
        )

        start_chapter = await self._get_current_chapter()
        chapters_to_write = list(
            range(start_chapter + 1, start_chapter + total_chapters + 1)
        )

        # 按批次处理：每批 parallel 章并发
        batch_idx = 0
        while chapters_to_write and not self._interrupted:
            batch = chapters_to_write[: self.config.parallel]
            chapters_to_write = chapters_to_write[len(batch) :]
            batch_idx += 1

            # 1) 确保所有大纲就绪（串行，因为大纲生成需要前序上下文）
            for ch in batch:
                if self._interrupted:
                    break
                if not await self._check_outline(ch):
                    if not await self._auto_generate_outline(ch):
                        result = ChapterResult(
                            chapter=ch,
                            status=ChapterStatus.FAILED,
                            error="大纲生成失败",
                        )
                        report.results.append(result)
                        self._interrupted = True
                        break

            if self._interrupted:
                break

            # 2) 清理 workflow 残留
            await self._clear_workflow()

            # 3) 并发写作本批次所有章节（v13 US-013：每章 asyncio.wait_for 包超时）
            tasks = [
                asyncio.wait_for(
                    self._write_single_chapter(ch, batch_idx, i + 1, len(batch)),
                    timeout=self.config.chapter_timeout_s,
                )
                for i, ch in enumerate(batch)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            batch_failed = False
            for i, result in enumerate(results):
                # v13 US-013：TimeoutError 单独标记 TIMEOUT_FAILED，不阻塞其它章
                if isinstance(result, asyncio.TimeoutError):
                    ch_result = ChapterResult(
                        chapter=batch[i],
                        status=ChapterStatus.TIMEOUT_FAILED,
                        error=f"章节超时（>{self.config.chapter_timeout_s}s）",
                        start_time=time.time(),
                        end_time=time.time(),
                    )
                    report.results.append(ch_result)
                    batch_failed = True
                elif isinstance(result, Exception):
                    ch_result = ChapterResult(
                        chapter=batch[i],
                        status=ChapterStatus.FAILED,
                        error=str(result),
                    )
                    report.results.append(ch_result)
                    batch_failed = True
                else:
                    report.results.append(result)
                    if result.status == ChapterStatus.FAILED:
                        batch_failed = True

            if batch_failed:
                self._interrupted = True
                break

            # 4) 批次完成后运行检查点（最后一章触发）
            last_ch = batch[-1]
            await self._run_checkpoint(last_ch)

            # 5) 完结检测
            final_ch = await self._get_final_chapter()
            if final_ch > 0 and last_ch >= final_ch:
                break

        report.end_time = time.time()
        return report

    async def _write_single_chapter(
        self, chapter: int, batch: int, pos: int, batch_size: int
    ) -> ChapterResult:
        """写作单章：write → verify → retry(if needed)。"""
        result = ChapterResult(
            chapter=chapter,
            status=ChapterStatus.WRITING,
            start_time=time.time(),
        )
        padded = f"{chapter:04d}"
        log_file = str(
            self.config.log_dir
            / f"ch{padded}-p{batch}-{time.strftime('%Y%m%d-%H%M%S')}.log"
        )
        result.log_file = log_file

        prompt = (
            f'使用 Skill 工具加载 "ink-write" 并完整执行所有步骤（Step 0 到 Step 6）。'
            f"项目目录: {self.config.project_root}。"
            f"禁止省略任何步骤，禁止提问，全程自主执行。完成后输出 INK_DONE。失败则输出 INK_FAILED。"
        )

        exit_code = await self._run_cli(prompt, log_file)

        await asyncio.sleep(self.config.cooldown)

        if await self._verify_chapter(chapter):
            result.status = ChapterStatus.DONE
            result.word_count = await self._get_word_count(chapter)
            result.end_time = time.time()
            return result

        # 重试一次
        result.status = ChapterStatus.RETRYING
        retry_log = str(
            self.config.log_dir
            / f"ch{padded}-retry-{time.strftime('%Y%m%d-%H%M%S')}.log"
        )
        retry_prompt = (
            f'使用 Skill 工具加载 "ink-resume"，'
            f"恢复第{chapter}章的写作并完成所有剩余步骤。"
            f"项目目录: {self.config.project_root}。"
            f"禁止提问，全程自主执行。完成后输出 INK_DONE。"
        )
        await self._run_cli(retry_prompt, retry_log)
        await asyncio.sleep(self.config.cooldown)

        if await self._verify_chapter(chapter):
            result.status = ChapterStatus.DONE
            result.word_count = await self._get_word_count(chapter)
            result.end_time = time.time()
            return result

        result.status = ChapterStatus.FAILED
        result.error = "写作+重试均未通过验证"
        result.end_time = time.time()
        return result

    async def _run_cli(self, prompt: str, log_file: str) -> int:
        """异步启动 CLI 进程。"""
        platform = self.config.platform
        if platform == "claude":
            cmd = [
                "claude", "-p", prompt,
                "--permission-mode", "bypassPermissions",
                "--no-session-persistence",
            ]
        elif platform == "gemini":
            cmd = ["gemini", "--yolo"]
        elif platform == "codex":
            cmd = ["codex", "--approval-mode", "full-auto", prompt]
        else:
            raise ValueError(f"不支持的平台: {platform}")

        with open(log_file, "w") as lf:
            if platform == "gemini":
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=lf,
                    stderr=asyncio.subprocess.STDOUT,
                )
                proc.stdin.write(prompt.encode())
                proc.stdin.close()
                await proc.wait()
            else:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=lf,
                    stderr=asyncio.subprocess.STDOUT,
                )
                await proc.wait()

        return proc.returncode or 0

    async def _get_current_chapter(self) -> int:
        result = await self._ink_py("state", "get-progress")
        try:
            return int(result.strip())
        except (ValueError, AttributeError):
            return 0

    async def _get_final_chapter(self) -> int:
        try:
            result = await self._ink_py("state", "get-final-chapter")
            return int(result.strip())
        except Exception:
            return 0

    async def _check_outline(self, chapter: int) -> bool:
        try:
            await self._ink_py("check-outline", "--chapter", str(chapter))
            return True
        except Exception:
            return False

    async def _auto_generate_outline(self, chapter: int) -> bool:
        vol = await self._get_volume_for_chapter(chapter)
        if not vol:
            return False
        log_file = str(
            self.config.log_dir
            / f"plan-vol{vol}-{time.strftime('%Y%m%d-%H%M%S')}.log"
        )
        prompt = (
            f'使用 Skill 工具加载 "ink-plan"。'
            f"为第{vol}卷生成完整详细大纲（节拍表+时间线+章纲）。"
            f"项目目录: {self.config.project_root}。"
            f"禁止提问，自动选择第{vol}卷，全程自主执行。完成后输出 INK_PLAN_DONE。"
        )
        await self._run_cli(prompt, log_file)
        await asyncio.sleep(self.config.checkpoint_cooldown)
        return await self._check_outline(chapter)

    async def _get_volume_for_chapter(self, chapter: int) -> Optional[str]:
        """Parse volume outlines to determine which volume a chapter belongs to."""
        try:
            outline_dir = self.config.project_root / "大纲"
            for f in sorted(outline_dir.glob("第*卷-*.md")):
                # e.g. "第1卷-节拍表.md" -> "1"
                import re
                m = re.match(r"第(\d+)卷-", f.name)
                if m:
                    vol = m.group(1)
                    # Read 节拍表 to get chapter range
                    if f.name.endswith("-节拍表.md"):
                        content = f.read_text(encoding="utf-8")
                        chs = [int(x) for x in re.findall(r"第(\d+)章", content)]
                        if chs:
                            ch_min, ch_max = min(chs), max(chs)
                            if ch_min <= chapter <= ch_max:
                                return vol
                    # Fallback: assume this volume covers unknown chapters
                    return vol
            return "1"  # Default to volume 1
        except Exception:
            return "1"

    async def _clear_workflow(self) -> None:
        try:
            await self._ink_py("workflow", "clear")
        except Exception:
            pass

    async def _verify_chapter(self, chapter: int) -> bool:
        padded = f"{chapter:04d}"
        text_dir = self.config.project_root / "正文"
        import glob

        matches = glob.glob(str(text_dir / f"第{padded}章*.md"))
        if not matches:
            return False
        filepath = Path(matches[0])
        if not filepath.exists() or filepath.stat().st_size == 0:
            return False
        char_count = len(filepath.read_text(encoding="utf-8"))
        if char_count < 2200:
            return False

        summary_file = (
            self.config.project_root / ".ink" / "summaries" / f"ch{padded}.md"
        )
        if not summary_file.exists():
            return False

        return True

    async def _get_word_count(self, chapter: int) -> int:
        padded = f"{chapter:04d}"
        text_dir = self.config.project_root / "正文"
        import glob

        matches = glob.glob(str(text_dir / f"第{padded}章*.md"))
        if not matches:
            return 0
        try:
            return len(Path(matches[0]).read_text(encoding="utf-8"))
        except Exception:
            return 0

    async def _run_checkpoint(self, chapter: int) -> None:
        try:
            result = await self._ink_py(
                "checkpoint-level", "--chapter", str(chapter)
            )
            cp = json.loads(result)
            if not cp.get("review"):
                return
        except Exception:
            return

        audit_depth = cp.get("audit")
        macro_tier = cp.get("macro")

        if audit_depth:
            await self._run_skill_process("ink-audit", f"审计深度：{audit_depth}")

        if macro_tier:
            await self._run_skill_process(
                "ink-macro-review", f"审查层级：{macro_tier}"
            )

        review_range = cp.get("review_range", [max(1, chapter - 4), chapter])
        start, end = review_range[0], review_range[1]
        await self._run_skill_process(
            "ink-review",
            f"审查范围：第{start}章到第{end}章。审查深度：Core",
        )

    async def _run_skill_process(self, skill: str, detail: str) -> None:
        log_file = str(
            self.config.log_dir
            / f"{skill}-{time.strftime('%Y%m%d-%H%M%S')}.log"
        )
        prompt = (
            f'使用 Skill 工具加载 "{skill}"。{detail}。'
            f"项目目录: {self.config.project_root}。"
            f"全程自主执行，禁止提问。完成后输出 INK_DONE。"
        )
        await self._run_cli(prompt, log_file)
        await asyncio.sleep(self.config.checkpoint_cooldown)

    async def _ink_py(self, *args: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "python3", "-X", "utf8",
            self.config.ink_py,
            "--project-root", str(self.config.project_root),
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"ink.py {' '.join(args)} 失败: {stderr.decode()}"
            )
        return stdout.decode()
