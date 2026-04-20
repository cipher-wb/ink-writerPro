#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""US-014 端到端 smoke harness（Mac + Windows 双端共享核心）。

被 scripts/e2e_smoke.sh 与 scripts/e2e_smoke.ps1 以子进程方式调用：

    python e2e_smoke_harness.py --log reports/e2e-smoke-mac.log

步骤：
  1) init   : 走 init_project.init_project() 直接构造带中文 + 空格的项目目录
  2) write  : 合成 N 章 fake 正文（UTF-8）、写入 index.db chapters 表、推进 state.json
  3) verify : index.db 完整性 + 章节文件 + recent_full_texts 装填 + state/db 一致
  4) cleanup: 默认清理临时项目（--keep 可保留调试）

首版按 PRD 退化路径：跳过 LLM 实调用——用本模块直接合成章节内容替代
`ink-write`/`ink-auto` 的 writer-agent，验证的是数据流水线（初始化 → 正文文件 →
index.db → context pack 装填）本身的跨平台健康度。真实 LLM 驱动的写作链路由
ink-auto/ralph loop 在 PR 集成阶段单独验证。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_HARNESS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _HARNESS_DIR.parent
_INK_SCRIPTS = _REPO_ROOT / "ink-writer" / "scripts"

# runtime_compat + init_project 都在 ink-writer/scripts/，提前注入 sys.path。
for candidate in (_INK_SCRIPTS, _REPO_ROOT):
    sp = str(candidate)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from runtime_compat import enable_windows_utf8_stdio  # noqa: E402

enable_windows_utf8_stdio(skip_in_pytest=True)


@dataclass
class StepResult:
    step: str
    status: str  # "ok" | "fail"
    detail: str = ""
    extra: Dict[str, Any] = None  # type: ignore[assignment]

    def to_line(self) -> str:
        extra = f" extra={json.dumps(self.extra, ensure_ascii=False)}" if self.extra else ""
        return f"[e2e-smoke] step={self.step} status={self.status} detail={self.detail}{extra}"


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _snapshot_pointer_files() -> Dict[Path, Optional[bytes]]:
    """init_project 会写 `.claude/.ink-current-project` 与用户级 registry。
    smoke 只是临时项目——snapshot 旧内容，结束后无论成败都还原回去，
    避免污染用户的 `current_project` 指向。"""
    candidates: List[Path] = []
    ws_pointer = _REPO_ROOT / ".claude" / ".ink-current-project"
    candidates.append(ws_pointer)
    try:
        from project_locator import _get_user_claude_root  # noqa: WPS433

        user_registry = _get_user_claude_root() / "ink-writer" / "registry.json"
        candidates.append(user_registry)
    except Exception:  # noqa: BLE001
        pass
    snapshot: Dict[Path, Optional[bytes]] = {}
    for path in candidates:
        snapshot[path] = path.read_bytes() if path.exists() else None
    return snapshot


def _restore_pointer_files(snapshot: Dict[Path, Optional[bytes]]) -> None:
    for path, payload in snapshot.items():
        if payload is None:
            if path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass
            continue
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        except OSError:
            pass


def _chinese_chapter_body(chapter: int) -> str:
    """合成稳定、可读的中文章节正文（~250 字）。"""
    lines = [
        f"# 第{chapter:04d}章 测试章节",
        "",
        "这是跨平台端到端 smoke 测试的合成正文——并非真实的小说内容，",
        "仅用于验证章节文件读写、索引装填与 recent_full_texts 链路在 Mac 与 Windows 双端均可行。",
        "正文主体需要包含足够的 UTF-8 汉字以模拟真实章节的编码挑战：",
        "江流天地外，山色有无中。斜阳照墟落，穷巷牛羊归。",
        "云想衣裳花想容，春风拂槛露华浓。若非群玉山头见，会向瑶台月下逢。",
        "",
        f"（本段由 scripts/e2e_smoke_harness.py 在第 {chapter} 章位置自动生成，",
        "不参与任何线上写作链路。）",
    ]
    return "\n".join(lines) + "\n"


def create_temp_project_root(parent: Optional[Path] = None) -> Path:
    """创建带空格 + 中文的临时项目父目录；内部子目录名亦含中文。

    形如：`/tmp/ink smoke 测试-20260420T...-xxxx/测试项目`
    """
    base = parent or Path(tempfile.gettempdir())
    base.mkdir(parents=True, exist_ok=True)
    holder = Path(
        tempfile.mkdtemp(
            prefix=f"ink smoke 测试-{_utc_stamp()}-",
            dir=str(base),
        )
    )
    project_dir = holder / "测试项目"
    return project_dir


def _write_state_progress(state_path: Path, chapter: int) -> None:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    progress = state.get("progress") or {}
    progress["current_chapter"] = chapter
    progress["last_updated"] = _utc_stamp()
    state["progress"] = progress
    state_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def run_init(project_dir: Path) -> StepResult:
    """Step 1 — 通过 init_project.init_project 生成项目骨架。"""
    project_dir.parent.mkdir(parents=True, exist_ok=True)

    # 预先创建 .git 目录，让 init_project 跳过 git init（smoke 不需要 git 提交）
    (project_dir / ".git").mkdir(parents=True, exist_ok=True)

    from init_project import init_project  # noqa: WPS433 — 惰性导入，避免初始化副作用

    init_project(
        str(project_dir),
        "跨平台 Smoke 测试",
        "都市脑洞",
        protagonist_name="苏启言",
        target_words=60_000,
        target_chapters=20,
        golden_finger_type="无金手指",
        style_voice="V1",
    )

    must_exist = [
        project_dir / ".ink" / "state.json",
        project_dir / "大纲" / "总纲.md",
        project_dir / "设定集" / "世界观.md",
    ]
    missing = [str(p.relative_to(project_dir)) for p in must_exist if not p.exists()]
    if missing:
        return StepResult("init", "fail", detail=f"missing={missing}")

    return StepResult(
        "init",
        "ok",
        detail=f"project_dir={project_dir}",
        extra={"files_created": [str(p.relative_to(project_dir)) for p in must_exist]},
    )


def run_write(project_dir: Path, chapters: int) -> StepResult:
    """Step 2 — 合成 N 章 fake 正文并写入 index.db，推进 state.json。

    这是 LLM 调用的 mock 替身（PRD 允许）：真实链路中 writer-agent 会产出正文，
    此处用 _chinese_chapter_body(ch) 合成稳定内容，模拟『章节产物已落盘』状态，
    下游 verify 才能检验 recent_full_texts / index 装填是否正确。
    """
    from ink_writer.core.index.index_manager import IndexManager
    from ink_writer.core.index.index_types import ChapterMeta
    from ink_writer.core.infra.config import DataModulesConfig

    config = DataModulesConfig.from_project_root(project_dir)
    index = IndexManager(config)

    chapters_dir = project_dir / "正文"
    chapters_dir.mkdir(parents=True, exist_ok=True)

    written: List[str] = []
    for ch in range(1, chapters + 1):
        body = _chinese_chapter_body(ch)
        fname = chapters_dir / f"第{ch:04d}章.md"
        fname.write_text(body, encoding="utf-8")
        word_count = len(body)
        meta = ChapterMeta(
            chapter=ch,
            title=f"第{ch:04d}章 测试章节",
            location="测试场景",
            word_count=word_count,
            characters=["苏启言"],
            summary=f"Smoke harness 合成章节（第 {ch} 章）。",
        )
        index.add_chapter(meta)
        written.append(str(fname.relative_to(project_dir)))

    _write_state_progress(project_dir / ".ink" / "state.json", chapters)

    return StepResult(
        "write",
        "ok",
        detail=f"chapters_written={chapters}",
        extra={"files": written},
    )


def run_verify(project_dir: Path, chapters: int) -> StepResult:
    """Step 3 — 验证 db 完整性 / 章节文件 / recent_full_texts / state-db 一致。"""
    from chapter_paths import find_chapter_file
    from ink_writer.core.context.context_manager import ContextManager
    from ink_writer.core.index.index_manager import IndexManager
    from ink_writer.core.infra.config import DataModulesConfig

    config = DataModulesConfig.from_project_root(project_dir)

    # 3.1 index.db 完整性
    index = IndexManager(config)
    integ = index.check_integrity()
    if not integ.get("ok"):
        return StepResult(
            "verify", "fail", detail=f"index integrity failed: {integ.get('detail')}"
        )

    # 3.2 章节文件全数可解析
    missing_files: List[int] = []
    for ch in range(1, chapters + 1):
        path = find_chapter_file(project_dir, ch)
        if path is None or not path.exists():
            missing_files.append(ch)
    if missing_files:
        return StepResult(
            "verify", "fail", detail=f"missing chapter files: {missing_files}"
        )

    # 3.3 state.current_chapter 与 db max(chapter) 一致
    state = json.loads((project_dir / ".ink" / "state.json").read_text(encoding="utf-8"))
    state_chapter = state.get("progress", {}).get("current_chapter", 0)
    db_rows = index.get_recent_chapters(limit=chapters + 5)
    db_chapter = max((row["chapter"] for row in db_rows), default=0)
    if state_chapter != db_chapter or db_chapter != chapters:
        return StepResult(
            "verify",
            "fail",
            detail=(
                f"state/db mismatch: state={state_chapter} "
                f"db={db_chapter} expected={chapters}"
            ),
        )

    # 3.4 recent_full_texts 能装填前 N 章（query chapter=N+1）
    ctx = ContextManager(config=config)
    recent_full_texts = ctx._load_recent_full_texts(chapter=chapters + 1, window=chapters)
    if len(recent_full_texts) != chapters:
        return StepResult(
            "verify",
            "fail",
            detail=(
                f"recent_full_texts length {len(recent_full_texts)} != {chapters}"
            ),
        )
    bad = [
        entry
        for entry in recent_full_texts
        if entry.get("missing") or not (entry.get("text") or "").strip()
    ]
    if bad:
        return StepResult(
            "verify",
            "fail",
            detail=f"recent_full_texts contains missing/empty entries: {bad}",
        )

    return StepResult(
        "verify",
        "ok",
        detail="all checks passed",
        extra={
            "index_tables": integ.get("table_count"),
            "state_chapter": state_chapter,
            "db_chapter": db_chapter,
            "recent_full_texts_count": len(recent_full_texts),
        },
    )


def run_cleanup(project_dir: Path, *, keep: bool) -> StepResult:
    if keep:
        return StepResult(
            "cleanup",
            "ok",
            detail=f"kept (--keep) at {project_dir}",
        )
    parent_holder = project_dir.parent
    shutil.rmtree(parent_holder, ignore_errors=True)
    removed = not parent_holder.exists()
    return StepResult(
        "cleanup",
        "ok" if removed else "fail",
        detail=f"removed={parent_holder}" if removed else f"still exists: {parent_holder}",
    )


def _default_log_path(platform_hint: str) -> Path:
    tag = "windows" if platform_hint == "windows" else "mac"
    reports_dir = _REPO_ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    return reports_dir / f"e2e-smoke-{tag}.log"


def _platform_hint() -> str:
    return "windows" if sys.platform == "win32" else "mac"


def run_smoke(
    *,
    project_dir: Optional[Path] = None,
    chapters: int = 3,
    keep: bool = False,
    log_path: Optional[Path] = None,
    stdout=sys.stdout,
    temp_parent: Optional[Path] = None,
) -> Dict[str, Any]:
    """主流程（可被 pytest 直接调用，也可被 __main__ 走 CLI 入口复用）。"""
    chapters = max(1, int(chapters))
    project_dir = project_dir or create_temp_project_root(parent=temp_parent)
    log_path = log_path or _default_log_path(_platform_hint())
    log_path.parent.mkdir(parents=True, exist_ok=True)

    results: List[StepResult] = []

    def _emit(result: StepResult) -> None:
        line = result.to_line()
        print(line, file=stdout, flush=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(
            f"\n========== e2e-smoke {_utc_stamp()} platform={_platform_hint()} "
            f"chapters={chapters} project_dir={project_dir} ==========\n"
        )

    pointer_snapshot = _snapshot_pointer_files()
    try:
        steps = [
            ("init", lambda: run_init(project_dir)),
            ("write", lambda: run_write(project_dir, chapters)),
            ("verify", lambda: run_verify(project_dir, chapters)),
        ]
        overall_ok = True
        for _name, fn in steps:
            try:
                result = fn()
            except Exception as exc:  # noqa: BLE001
                result = StepResult(
                    _name,
                    "fail",
                    detail=f"{type(exc).__name__}: {exc}",
                    extra={"traceback": traceback.format_exc().splitlines()[-6:]},
                )
            results.append(result)
            _emit(result)
            if result.status != "ok":
                overall_ok = False
                break

        cleanup_result = run_cleanup(project_dir, keep=keep)
        results.append(cleanup_result)
        _emit(cleanup_result)

        summary = StepResult(
            "summary",
            "ok" if overall_ok else "fail",
            detail=f"platform={_platform_hint()} chapters={chapters}",
            extra={"steps": [asdict(r) for r in results]},
        )
        _emit(summary)
        return {
            "ok": overall_ok,
            "log_path": str(log_path),
            "project_dir": str(project_dir),
            "steps": [asdict(r) for r in results],
        }
    finally:
        _restore_pointer_files(pointer_snapshot)


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ink-writer Mac+Windows 端到端 smoke 测试")
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=None,
        help="临时项目目录（默认随机生成带中文+空格的路径）",
    )
    parser.add_argument(
        "--chapters",
        type=int,
        default=3,
        help="合成章节数（默认 3）",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="保留临时项目（默认清理）",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=None,
        help="日志文件路径（默认 reports/e2e-smoke-{mac,windows}.log）",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    result = run_smoke(
        project_dir=args.project_dir,
        chapters=args.chapters,
        keep=args.keep,
        log_path=args.log,
    )
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
