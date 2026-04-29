"""ink-auto.sh 进度心跳 + 异常透出 + step 协议覆盖回归

背景（2026-04-29 用户痛点）：
  跑 ink-auto 时只能看到 "[1/5] 第1章 开始写作..."，等 1 小时不知道在干嘛。
  - init 阶段（5-15 分钟）：黑屏
  - plan 阶段（20-60 分钟）：黑屏
  - write 阶段（5-30 分钟）：黑屏
  - API 限流/网络异常埋在 log 里没人看

修复方向（任务 #15）：
  A) 心跳：ink-auto.sh 在 LLM 子进程跑期间，每 30s 主动观测产物 + log
  B) Step 协议覆盖：ink-init / ink-plan SKILL.md 加 [INK-PROGRESS] 协议
  C) 失败时透出 log 中的 API/网络异常关键词

本测试守护：
  1. _start_progress_heartbeat / _stop_progress_heartbeat 函数存在
  2. run_cli_process 接受 op 参数（init/plan/write）并启动心跳
  3. _HEARTBEAT_ALERT_REGEX 包含关键的 API 异常关键词
  4. get_step_name 已扩展覆盖 ink-init / ink-plan 的 step_id
  5. ink-init / ink-plan SKILL.md 含 [INK-PROGRESS] 协议章节
  6. 失败日志同时打字面 marker（机器可读）+ 中文 ❌（人类可读）+ log 末尾透出
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INK_AUTO_SH = REPO_ROOT / "ink-writer" / "scripts" / "ink-auto.sh"
INK_PLAN_SKILL = REPO_ROOT / "ink-writer" / "skills" / "ink-plan" / "SKILL.md"
INK_INIT_SKILL = REPO_ROOT / "ink-writer" / "skills" / "ink-init" / "SKILL.md"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ───────────────────────────────────────────────────────────────
# A) 心跳函数存在 + 接入 run_cli_process
# ───────────────────────────────────────────────────────────────


def test_progress_heartbeat_functions_defined():
    """ink-auto.sh 必须定义 _start_progress_heartbeat / _stop_progress_heartbeat。"""
    src = _read(INK_AUTO_SH)
    assert re.search(r"^_start_progress_heartbeat\s*\(\s*\)\s*\{", src, re.MULTILINE), (
        "_start_progress_heartbeat 函数必须定义"
    )
    assert re.search(r"^_stop_progress_heartbeat\s*\(\s*\)\s*\{", src, re.MULTILINE), (
        "_stop_progress_heartbeat 函数必须定义"
    )


def test_run_cli_process_accepts_op_parameter():
    """run_cli_process 必须接受第 4 个参数 op (init/plan/write) 并启动心跳。"""
    src = _read(INK_AUTO_SH)
    # 接受 op 参数
    assert re.search(r'op="\$\{4:-', src), (
        "run_cli_process 必须支持第 4 个参数 op，决定心跳监测什么产物"
    )
    # 启动心跳
    assert "_start_progress_heartbeat" in src, (
        "run_cli_process 必须调 _start_progress_heartbeat"
    )
    assert "_stop_progress_heartbeat" in src, (
        "run_cli_process 必须在结束时调 _stop_progress_heartbeat"
    )


def test_init_plan_write_callers_pass_op_arg():
    """init / plan / write 三个调用点必须显式传 op 参数。"""
    src = _read(INK_AUTO_SH)
    # init 路径（_v27_init_if_needed）必须传 "init"
    assert re.search(
        r'run_cli_process\s+"\$init_prompt"\s+"\$init_log".*?"init"',
        src, re.DOTALL,
    ), "v27 init 调用必须把 \"init\" 作为 op 参数传入"
    # plan 路径（auto_plan_volume / auto_generate_outline）必须传 "plan"
    assert src.count('"plan"') >= 2, (
        "auto_plan_volume + auto_generate_outline 调用必须把 \"plan\" 作为 op 参数传入"
    )
    # write 路径（run_chapter / retry_chapter）必须传 "write"
    assert src.count('"write"') >= 2, (
        "run_chapter + retry_chapter 调用必须把 \"write\" 作为 op 参数传入"
    )


# ───────────────────────────────────────────────────────────────
# C) 异常关键词正则覆盖关键 API 错误信号
# ───────────────────────────────────────────────────────────────


def test_alert_regex_covers_critical_signals():
    """_HEARTBEAT_ALERT_REGEX 必须含 API 限流 / 网络 / 服务故障的关键词。"""
    src = _read(INK_AUTO_SH)
    m = re.search(r"_HEARTBEAT_ALERT_REGEX='([^']+)'", src)
    assert m, "_HEARTBEAT_ALERT_REGEX 必须定义"
    regex = m.group(1).lower()

    must_have = [
        "rate.?limit",   # OpenAI / Anthropic 限流
        "429",           # HTTP 限流
        "503",           # 服务不可用
        "504",           # 网关超时
        "timeout",       # 通用超时
        "overloaded",    # Anthropic 过载
        "connection.?refused",  # 网络
    ]
    for keyword in must_have:
        assert keyword in regex, (
            f"_HEARTBEAT_ALERT_REGEX 必须包含 {keyword!r}（API/网络异常关键词）"
        )


def test_failure_log_keeps_machine_marker_and_adds_human_readable():
    """失败时必须同时打字面 [ink-auto] llm_exit= marker（机器可读契约）+ 中文 ❌（人类可读）。

    既守护 US-012 历史契约，又改善小白用户体验。
    """
    src = _read(INK_AUTO_SH)
    # 字面 marker（既有契约，回归测试守着）
    assert "[ink-auto] llm_exit=" in src, (
        "保留 [ink-auto] llm_exit= 字面 marker（US-012 守护）"
    )
    # 人类可读
    assert "❌ LLM 子进程" in src, (
        "失败时必须打 ❌ 中文行让用户秒懂"
    )
    # 失败时透出 log 末尾
    assert "log 末尾" in src or "log 中检测到" in src, (
        "失败时必须把 log 中的异常信号透出，避免用户'只看到 exit 1 不知道为啥'"
    )


# ───────────────────────────────────────────────────────────────
# B) get_step_name 覆盖 ink-init / ink-plan
# ───────────────────────────────────────────────────────────────


def test_step_name_covers_ink_init_steps():
    src = _read(INK_AUTO_SH)
    m = re.search(r"^get_step_name\s*\(\s*\)\s*\{(.*?)^\}", src, re.MULTILINE | re.DOTALL)
    assert m, "get_step_name 函数必须定义"
    body = m.group(1)
    for sid in ['"Step 0.4"', '"Step 0.5"', '"Step 1.5"', '"Step 1.6"', '"Step 1.7"']:
        assert sid in body, f"get_step_name 必须识别 ink-init 的 step_id {sid}"


def test_step_name_covers_ink_plan_steps():
    src = _read(INK_AUTO_SH)
    m = re.search(r"^get_step_name\s*\(\s*\)\s*\{(.*?)^\}", src, re.MULTILINE | re.DOTALL)
    assert m
    body = m.group(1)
    # ink-plan 独有的 step
    for sid in ['"Step 4.5"', '"Step 7"', '"Step 8"', '"Step 99"', '"Step 99.5"']:
        assert sid in body, f"get_step_name 必须识别 ink-plan 的 step_id {sid}"


# ───────────────────────────────────────────────────────────────
# B) ink-plan / ink-init SKILL.md 含进度协议章节
# ───────────────────────────────────────────────────────────────


def test_ink_plan_skill_has_progress_protocol():
    src = _read(INK_PLAN_SKILL)
    assert "进度输出规范" in src, "ink-plan SKILL.md 必须含 [进度输出规范] 章节"
    assert "[INK-PROGRESS] step_started" in src, (
        "ink-plan SKILL.md 必须示范 [INK-PROGRESS] step_started 用法"
    )
    assert "[INK-PROGRESS] step_completed" in src, (
        "ink-plan SKILL.md 必须示范 [INK-PROGRESS] step_completed 用法"
    )


def test_ink_init_skill_has_progress_protocol():
    src = _read(INK_INIT_SKILL)
    assert "进度输出规范" in src, "ink-init SKILL.md 必须含 [进度输出规范] 章节"
    assert "[INK-PROGRESS] step_started" in src, (
        "ink-init SKILL.md 必须示范 [INK-PROGRESS] step_started 用法"
    )
    assert "[INK-PROGRESS] step_completed" in src, (
        "ink-init SKILL.md 必须示范 [INK-PROGRESS] step_completed 用法"
    )


def test_init_heartbeat_observes_multi_signals():
    """init 心跳必须观测 4 个信号（不能只看 state.json）：
    1. .ink/ 目录文件总数 + 字节
    2. 设定集/ 大纲/ 等其他 init 产物目录
    3. 最新创建/修改文件名
    4. log 末行（LLM 进展）
    """
    src = _read(INK_AUTO_SH)
    # 抠 _start_progress_heartbeat 函数体
    m = re.search(
        r"^_start_progress_heartbeat\s*\(\s*\)\s*\{(.*?)^\}",
        src, re.MULTILINE | re.DOTALL,
    )
    assert m
    body = m.group(1)
    # init 分支
    init_block = re.search(
        r'init\)(.*?);;', body, re.DOTALL,
    )
    assert init_block, "心跳必须有 init 分支"
    init_code = init_block.group(1)

    # 必须观测 设定集 + 大纲 + .ink
    assert "设定集" in init_code, "init 心跳必须观测 设定集/ 目录"
    assert "大纲" in init_code, "init 心跳必须观测 大纲/ 目录"
    assert ".ink" in init_code, "init 心跳必须观测 .ink/ 目录"
    # 文件计数 + 字节
    assert "total_files" in init_code or "find" in init_code, (
        "init 心跳必须计文件数"
    )
    # log 末行
    assert "last_log_line" in init_code, "init 心跳必须输出 log 末行"
    # awk 兼容 mac/linux（不能用 tac 命令——macOS 默认没装）
    assert "awk" in init_code, "log 末行必须用 awk"
    assert not re.search(r'\$\(\s*tac\s', init_code), (
        "不能用 tac 命令调用（macOS 默认没装）"
    )


def test_plan_heartbeat_observes_chapter_count_and_log():
    """plan 心跳必须显示已生成章纲数（grep "## 第N章" 计数）+ log 末行。"""
    src = _read(INK_AUTO_SH)
    m = re.search(
        r"^_start_progress_heartbeat\s*\(\s*\)\s*\{(.*?)^\}",
        src, re.MULTILINE | re.DOTALL,
    )
    assert m
    body = m.group(1)
    plan_block = re.search(r'plan\)(.*?);;', body, re.DOTALL)
    assert plan_block, "心跳必须有 plan 分支"
    plan_code = plan_block.group(1)

    # 已生成章节数
    assert "ch_count" in plan_code or "第" in plan_code, (
        "plan 心跳必须 grep 章节标题数已写章纲数"
    )
    # log 末行
    assert "last_log_line" in plan_code, "plan 心跳必须输出 log 末行"
    # 兼容 mac（命令调用层面不能用 tac，注释/字符串里 OK）
    assert not re.search(r'\$\(\s*tac\s', plan_code), (
        "plan 心跳不能用 tac 命令（macOS 没装）"
    )


def test_write_heartbeat_observes_step_progress_and_log():
    """write 心跳必须显示：字数（中文字符）+ 当前 step + 已完成 step 数 + log 末行。"""
    src = _read(INK_AUTO_SH)
    m = re.search(
        r"^_start_progress_heartbeat\s*\(\s*\)\s*\{(.*?)^\}",
        src, re.MULTILINE | re.DOTALL,
    )
    assert m
    body = m.group(1)
    write_block = re.search(r'write\)(.*?);;', body, re.DOTALL)
    assert write_block, "心跳必须有 write 分支"
    write_code = write_block.group(1)

    # 中文字符数（wc -m）而不是字节
    assert "wc -m" in write_code, "write 心跳必须用 wc -m 显示中文字符数"
    # 已完成 step 数
    assert "completed_steps" in write_code or "completed" in write_code, (
        "write 心跳必须显示 13 步流程的已完成数"
    )
    # log 末行
    assert "last_log_line" in write_code, "write 心跳必须输出 log 末行"


def test_run_chapter_prompt_forces_progress_markers():
    """run_chapter 的 prompt 必须强约束 LLM echo [INK-PROGRESS] 标记。

    历史 bug：仅靠 SKILL.md 提及不够，LLM 大概率忽略；必须在每次启动子进程
    的 prompt 里直接命令。
    """
    src = _read(INK_AUTO_SH)
    m = re.search(
        r"^run_chapter\s*\(\s*\)\s*\{(.*?)^\}",
        src, re.MULTILINE | re.DOTALL,
    )
    assert m
    body = m.group(1)
    assert "[INK-PROGRESS]" in body, (
        "run_chapter prompt 必须含 [INK-PROGRESS] 字面要求"
    )
    assert "硬要求" in body or "必须" in body, (
        "prompt 必须用强约束语气（硬要求/必须）让 LLM 不省略进度标记"
    )
    # 必须列出 13 个 step_id
    assert "Step 2A" in body and "Step 3" in body and "Step 6" in body, (
        "prompt 必须列出 ink-write 的具体 step_id 让 LLM 知道用什么名字"
    )


def test_init_plan_prompts_also_force_progress_markers():
    """init / plan 的 prompt 也应有 [INK-PROGRESS] 强约束（不只是 write）。"""
    src = _read(INK_AUTO_SH)
    # 抠 _v27_init_if_needed 函数体
    m_init = re.search(
        r"^_v27_init_if_needed\s*\(\s*\)\s*\{(.*?)^\}",
        src, re.MULTILINE | re.DOTALL,
    )
    assert m_init
    init_body = m_init.group(1)
    assert "[INK-PROGRESS]" in init_body, (
        "v27 init prompt 必须强约束 LLM 打 [INK-PROGRESS]"
    )

    # 抠 auto_plan_volume 函数体
    m_plan = re.search(
        r"^auto_plan_volume\s*\(\s*\)\s*\{(.*?)^\}",
        src, re.MULTILINE | re.DOTALL,
    )
    assert m_plan
    plan_body = m_plan.group(1)
    assert "[INK-PROGRESS]" in plan_body, (
        "auto_plan_volume prompt 必须强约束 LLM 打 [INK-PROGRESS]"
    )


def test_bash_syntax_check():
    """语法守护——心跳函数等不能引入 bash 解析错误。"""
    import shutil
    import subprocess
    if shutil.which("bash") is None:
        import pytest
        pytest.skip("需要 bash")
    result = subprocess.run(
        ["bash", "-n", str(INK_AUTO_SH)],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert result.returncode == 0, f"ink-auto.sh 语法失败:\n{result.stderr}"
