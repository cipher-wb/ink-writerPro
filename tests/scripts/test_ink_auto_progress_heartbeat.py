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


def test_parse_progress_handles_checker_started_completed():
    """parse_progress_output 必须解析 checker_started / checker_completed / checker_skipped 事件。

    这是 Step 3 内部 14 个 checker 的细粒度进度（task #22 新增）。
    没有这层，单章 30-60 分钟期间用户只看到"Step 3 审查"一直挂着。
    """
    src = _read(INK_AUTO_SH)
    m = re.search(
        r"^parse_progress_output\s*\(\s*\)\s*\{(.*?)^\}",
        src, re.MULTILINE | re.DOTALL,
    )
    assert m, "parse_progress_output 函数体应可解析"
    body = m.group(1)
    for event in ("checker_started", "checker_completed", "checker_skipped"):
        assert event in body, f"parse_progress_output 必须解析 {event} 事件"
    # 必须按 severity 着色
    assert "critical" in body and "🔴" in body, (
        "checker_completed 解析必须按 severity (critical/high/medium) 着色"
    )


def test_run_chapter_prompt_requires_two_layer_progress():
    """run_chapter prompt 必须命令 LLM 同时打 step 级 + checker 级进度（两层）。"""
    src = _read(INK_AUTO_SH)
    m = re.search(
        r"^run_chapter\s*\(\s*\)\s*\{(.*?)^\}",
        src, re.MULTILINE | re.DOTALL,
    )
    assert m
    body = m.group(1)
    assert "step_started" in body, "prompt 必须含 step_started 要求"
    assert "checker_started" in body, "prompt 必须含 checker_started 要求"
    assert "checker_completed" in body, "prompt 必须含 checker_completed 要求"
    assert "severity" in body, "prompt 必须说明 checker_completed 的 severity 字段"


def test_run_chapter_supports_fast_review_mode():
    """INK_AUTO_FAST_REVIEW=1 时跳过条件 checker（黄金三章除外）。"""
    src = _read(INK_AUTO_SH)
    assert "INK_AUTO_FAST_REVIEW" in src, (
        "ink-auto.sh 必须支持 INK_AUTO_FAST_REVIEW 环境变量"
    )
    # 黄金三章保护：ch > 3 才生效
    m = re.search(
        r"^run_chapter\s*\(\s*\)\s*\{(.*?)^\}",
        src, re.MULTILINE | re.DOTALL,
    )
    assert m
    body = m.group(1)
    assert re.search(r'INK_AUTO_FAST_REVIEW.*?ch\s*>\s*3', body, re.DOTALL), (
        "FAST_REVIEW 模式必须保护黄金三章（ch > 3 才跳过条件 checker）"
    )


def test_ink_write_skill_documents_checker_progress_protocol():
    """ink-write SKILL.md Step 3 章节必须文档化 checker 级 [INK-PROGRESS] 协议。"""
    skill_path = REPO_ROOT / "ink-writer" / "skills" / "ink-write" / "SKILL.md"
    src = skill_path.read_text(encoding="utf-8")
    assert "[INK-PROGRESS] checker_started" in src
    assert "[INK-PROGRESS] checker_completed" in src
    assert "[INK-PROGRESS] checker_skipped" in src


def test_heartbeat_includes_llm_process_metrics():
    """心跳必须含 LLM 子进程的 CPU%/RSS/ELAPSED 实时指标。

    cipher 实测 2026-04-29：claude -p 在 inline tool 调用期间不 flush stdout，
    log 末行/workflow step 都为空。但 LLM 进程 CPU/内存仍在变化，是最权威的
    "还活着"信号。
    """
    src = _read(INK_AUTO_SH)
    m = re.search(
        r"^_start_progress_heartbeat\s*\(\s*\)\s*\{(.*?)^\}",
        src, re.MULTILINE | re.DOTALL,
    )
    assert m
    body = m.group(1)
    # 必须用 ps + grep -E 组合找 LLM 进程（macOS BSD pgrep -f ERE 不接受 \| 转义）
    assert re.search(r'ps\s+-eo\s+pid,command', body), (
        "心跳必须用 ps -eo pid,command 列进程（跨 mac/linux 最可靠）"
    )
    assert 'grep -E "claude -p' in body, (
        "心跳必须用 grep -E + alternation 找 LLM CLI 进程；不能用 pgrep -f BRE 转义"
        "（macOS BSD pgrep 默认 ERE 但 \\| 在 ERE 下是字面字符，找不到进程）"
    )
    # 必须 ps 读 CPU/RSS/ELAPSED
    assert re.search(r'ps\s+-p.*?pcpu.*?rss.*?etime', body), (
        "心跳必须 ps 读 LLM 进程的 pcpu/rss/etime"
    )
    # 必须输出到心跳行
    assert "llm_status" in body or "%CPU" in body, (
        "心跳必须把进程指标输出到屏幕"
    )


def test_ink_auto_detects_linebuf_cmd():
    """ink-auto.sh 必须检测 stdbuf/gstdbuf/unbuffer 中至少一个，并用之包裹 LLM CLI。

    没行缓冲，claude -p 输出延迟到 step 完成才出现；用户体验黑屏 5-15 分钟。
    """
    src = _read(INK_AUTO_SH)
    assert "detect_linebuf_cmd" in src, (
        "必须有 detect_linebuf_cmd 函数检测行缓冲工具"
    )
    # 必须探测 3 种工具
    for tool in ("stdbuf", "gstdbuf", "unbuffer"):
        assert tool in src, f"detect_linebuf_cmd 必须探测 {tool}"
    # 必须传 LINEBUF_CMD 给 claude/gemini/codex
    assert "${LINEBUF_CMD:-} claude" in src, (
        "claude 调用必须用 ${LINEBUF_CMD} 包裹"
    )
    assert "${LINEBUF_CMD:-} gemini" in src, (
        "gemini 调用必须用 ${LINEBUF_CMD} 包裹"
    )
    assert "${LINEBUF_CMD:-} codex" in src, (
        "codex 调用必须用 ${LINEBUF_CMD} 包裹"
    )


def test_linebuf_fallback_when_unavailable():
    """三个 buf 工具都没装时必须能 fallback 裸跑（不 fail）。"""
    src = _read(INK_AUTO_SH)
    # 在 detect_linebuf_cmd 函数末尾必须有 echo "" fallback
    m = re.search(r"detect_linebuf_cmd\s*\(\s*\)\s*\{(.*?)\}", src, re.DOTALL)
    assert m
    body = m.group(1)
    assert 'echo ""' in body, (
        "三个 buf 工具都没装时必须 echo \"\"（让 LLM 裸跑），不能 exit"
    )
    # 用户提示信息必须告诉用户怎么装
    assert "brew install coreutils" in src or "gstdbuf" in src, (
        "必须告诉 macOS 用户怎么装 coreutils 拿 gstdbuf"
    )


def test_step_inference_from_artifacts():
    """心跳必须基于产物文件**主动推断**当前 step（不依赖 LLM 调 workflow start-step）。

    历史教训（cipher 实测 2026-04-30）：仅靠 workflow_state.json 的 current_task 显示
    step 不可靠——LLM 可能不调 workflow start-task。改为读产物文件兜底：
      - data_agent_timing 最近有 process-chapter ch=N → Step 5
      - .ink/tmp/data_agent_payload_chXXXX.json → Step 5 准备
      - .ink/tmp/review_bundle_chXXXX.json → Step 3
      - 正文/第NNNN章*.md → Step 2A 完成
      - 都没有 → Step 0-1
    """
    src = _read(INK_AUTO_SH)
    # 必须有"基于产物推断"标记
    assert "基于产物推断" in src or "[推断]" in src, (
        "心跳必须有 step 主动推断逻辑，不能只靠 workflow_state.json"
    )
    # 必须探测多种产物文件
    indicators = ["data_agent_payload", "review_bundle", "正文"]
    for kw in indicators:
        assert kw in src, f"step 推断必须检查产物 {kw}"


def test_data_agent_timing_filters_stale_records():
    """DataAgent timing 显示必须过滤陈旧记录（>5分钟前的不显示）。

    cipher 实测 2026-04-30 看到 '-28287s ago' 是上次跑（昨晚）留下的 timing，
    被错误展示成"刚才调的"。修：max_age 限制 5 分钟（300s）。
    """
    src = _read(INK_AUTO_SH)
    # 必须有 5 分钟过滤逻辑（300 秒）
    assert "300" in src, "DataAgent 显示必须过滤 >300s 的陈旧记录"
    # 不能用 timezone.utc（data_agent_timing 是本地时间无 tz）
    assert "datetime.now()" in src, (
        "DataAgent timing 时区计算必须用 datetime.now() 本地时间，"
        "不能强加 UTC（cipher 实测 -8h 偏移）"
    )


def test_step_inference_does_not_use_fresh_for_one_shot_artifacts():
    """review_bundle / data_agent_payload 不能用 fresh() 判断——
    它们是 Step 3/5 启动时一次性生成，整个 step 期间不再修改。
    用 fresh(600s) 会让心跳在长 step（如 25-30 分钟的 Step 3 审查）后期失明。

    cipher 实测 2026-04-30：Step 3 跑 30 分钟时心跳从'Step 3 审查中'
    跳回'Step 0-1'——因为 fresh(600s) 已超时。
    修：改用文件存在性 + 章号锁定（chXXXX 已包含在文件名中）。
    """
    src = _read(INK_AUTO_SH)
    m = re.search(
        r"^_start_progress_heartbeat\s*\(\s*\)\s*\{(.*?)^\}",
        src, re.MULTILINE | re.DOTALL,
    )
    assert m
    body = m.group(1)
    # review_bundle 必须用 .exists() 不能用 fresh()
    assert re.search(r"bundle_file\.exists\(\)", body), (
        "review_bundle 推断必须用 .exists()，不能用 fresh()"
        "（cipher 实测 fresh(600s) 在 Step 3 长审查后期失明）"
    )
    assert re.search(r"payload_file\.exists\(\)", body), (
        "data_agent_payload 推断同样不能用 fresh()"
    )
    # 不能再有 fresh(bundle_file) 这种调用
    assert "fresh(bundle_file)" not in body, "bundle_file 不能再走 fresh"
    assert "fresh(payload_file)" not in body, "payload_file 不能再走 fresh"


def test_step2b_skip_env_var_supported():
    """INK_AUTO_SKIP_STEP2B=1 必须能让 LLM 跳过 Step 2B 风格适配。

    cipher 实测 Step 2B 单次耗时 2-5min，但因 Step 2A 起草已含 style 规则，
    多数情况是空操作。开关让追求速度的用户可关。
    """
    src = _read(INK_AUTO_SH)
    assert "INK_AUTO_SKIP_STEP2B" in src, (
        "ink-auto.sh 必须支持 INK_AUTO_SKIP_STEP2B 环境变量"
    )
    assert "skip_step2b_clause" in src or "Step 2B 跳过模式" in src, (
        "run_chapter prompt 必须含 Step 2B 跳过指令分支"
    )

    # SKILL.md 也必须文档化跳过条件
    skill = REPO_ROOT / "ink-writer" / "skills" / "ink-write" / "SKILL.md"
    skill_src = skill.read_text(encoding="utf-8")
    assert "Step 2B 跳过条件" in skill_src or "INK_AUTO_SKIP_STEP2B" in skill_src, (
        "SKILL.md Step 2B 章节必须文档化跳过条件"
    )


def test_step4_incremental_polish_documented():
    """ink-write SKILL.md Step 4 必须明确"增量润色"指令——只改 critical/high 段落。"""
    skill = REPO_ROOT / "ink-writer" / "skills" / "ink-write" / "SKILL.md"
    src = skill.read_text(encoding="utf-8")
    # 找到 Step 4 章节
    m = re.search(r"### Step 4.*?(?=###\s|\Z)", src, re.DOTALL)
    assert m, "Step 4 章节应可定位"
    step4 = m.group(0)

    # 必须有"增量润色"或同义说法
    assert "增量润色" in step4 or "不要全章重写" in step4, (
        "Step 4 必须明确要求增量润色（不全章重写）"
    )
    # 必须提到 target_segments / line range
    assert "target_segments" in step4 or "line range" in step4, (
        "Step 4 必须要求 polish-agent 接收 target_segments 而不是整章"
    )
    # 必须有回退兜底说明（向后兼容）
    assert "回退兜底" in step4 or "向后兼容" in step4, (
        "Step 4 必须保留全章 polish 的兜底路径（向后兼容）"
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
