# 阶段 3D：边缘场景找坑清单

> 本文件专门记录潜在 bug 与风险，不包含可执行测试代码。  
> 风险等级：🔴卡死/数据丢失；🟡报错/功能不可用；🟢体验问题。  
> 执行状态：本阶段仅编写清单，未执行测试。

### EDGE-001: 蓝本文件不存在
- **场景**: 用户传入 `--blueprint missing.md` 或 v27 转换时蓝本路径已被移动。
- **触发方式**: 执行 `python ink-writer/scripts/blueprint_to_quick_draft.py --input missing.md --output out.json`。
- **当前行为预测**: `_main` 捕获 `OSError`，stderr 输出 `BLUEPRINT_IO_ERROR`，退出码 3。
- **是否是 bug**: 否
- **风险等级**: 🟡报错/功能不可用
- **建议修复方向**: 保持当前 fail-fast；上层 v27 可补充更友好的用户提示。
- **覆盖**: → `ink_writer/core/auto/blueprint_to_quick_draft.py:_main:181`

### EDGE-002: 输出 quick draft 权限不足
- **场景**: 输出目录不可写或输出文件被权限限制。
- **触发方式**: 将 `--output` 指向只读目录，再执行蓝本转换 CLI。
- **当前行为预测**: `Path(args.output).write_text` 在 try 块外，`PermissionError` 不会被 `_main` 转成 `BLUEPRINT_IO_ERROR`，进程可能以 traceback 退出。
- **是否是 bug**: 是
- **风险等级**: 🟡报错/功能不可用
- **建议修复方向**: 把输出写入纳入 `try/except OSError`，返回稳定退出码与错误前缀。
- **覆盖**: → `ink_writer/core/auto/blueprint_to_quick_draft.py:_main:202`

### EDGE-003: 蓝本为 UTF-8 BOM 或 GBK 编码
- **场景**: 用户从 Windows/网页复制蓝本，保存为 UTF-8 BOM 或 GBK。
- **触发方式**: 用 GBK 编码写 `quick_blueprint.md` 后调用 `parse_blueprint`。
- **当前行为预测**: GBK 会在 `read_text(encoding="utf-8")` 抛 `UnicodeDecodeError`；BOM 可能让首行标题带 BOM，但 section 仍可能正常。
- **是否是 bug**: 待定
- **风险等级**: 🟡报错/功能不可用
- **建议修复方向**: 明确只支持 UTF-8，或增加 `utf-8-sig`/GBK 探测并输出迁移提示。
- **覆盖**: → `ink_writer/core/auto/blueprint_to_quick_draft.py:parse_blueprint:50`

### EDGE-004: Debug 全局配置缺失
- **场景**: `config/debug.yaml` 不存在，用户仍执行 `/ink-debug-status` 或 `/ink-debug-report`。
- **触发方式**: 指定不存在的 `--global-yaml` 执行 `python -m ink_writer.debug.cli status`。
- **当前行为预测**: `_safe_load_yaml` 返回 `None`，`load_config` 使用默认配置继续。
- **是否是 bug**: 否
- **风险等级**: 🟢体验问题
- **建议修复方向**: status 输出可附带“使用默认配置”的弱提示。
- **覆盖**: → `ink_writer/debug/config.py:_safe_load_yaml:87`, `ink_writer/debug/config.py:load_config:103`

### EDGE-005: Debug 配置字段类型错误
- **场景**: `layers` 被写成字符串，或 `severity` 字段写成列表。
- **触发方式**: 在 `config.local.yaml` 写入 `layers: off`，再执行 debug CLI。
- **当前行为预测**: `LayerSwitches(**(raw.get("layers") or {}))` 对字符串解包会抛 `TypeError`，CLI 失败。
- **是否是 bug**: 是
- **风险等级**: 🟡报错/功能不可用
- **建议修复方向**: 对每个 dataclass 配置段先做 `isinstance(value, dict)`，非法类型 fail-soft 回默认并写 stderr。
- **覆盖**: → `ink_writer/debug/config.py:load_config:103`

### EDGE-006: Debug 配置字段未知
- **场景**: 用户在 `severity` 下写入未知键 `json_threshold`。
- **触发方式**: `config.local.yaml` 写 `severity: {json_threshold: warn}` 后执行 debug CLI。
- **当前行为预测**: `SeverityThresholds(**raw["severity"])` 遇未知 kwarg 抛 `TypeError`。
- **是否是 bug**: 是
- **风险等级**: 🟡报错/功能不可用
- **建议修复方向**: dataclass 构造前过滤未知键，并把忽略字段写入 debug config warning。
- **覆盖**: → `ink_writer/debug/config.py:load_config:119`

### EDGE-007: WebSearch 或市场趋势网络中断
- **场景**: Quick Step 0 双平台榜单 WebSearch 超时或不可用。
- **触发方式**: 断网后执行 `/ink-init --quick`。
- **当前行为预测**: 阶段 1 记录 Quick Step 0 依赖 WebSearch 并缓存市场趋势；若 LLM 编排没有兜底，可能退化为无榜单方案或卡在等待。
- **是否是 bug**: 待定
- **风险等级**: 🟡报错/功能不可用
- **建议修复方向**: 在 Skill prompt 中要求 15s 超时后使用本地缓存或明确降级，不把网络失败伪装成完整市场调研。
- **覆盖**: → `ink-writer/skills/ink-init/SKILL.md:Quick Step 0 WebSearch:74`

### EDGE-008: AI checker 返回非 JSON 或 Markdown 包裹 JSON
- **场景**: planning review、audit 或 checker 期望 JSON，AI 返回普通 Markdown。
- **触发方式**: 模拟 checker 输出 ````json` 代码块缺右括号，或完全自然语言。
- **当前行为预测**: 解析层可能抛错或把报告当作无问题，取决于具体 checker；阶段 1 已把 report scanning 的 fail-soft 分支列为关键路径。
- **是否是 bug**: 待定
- **风险等级**: 🟡报错/功能不可用
- **建议修复方向**: 所有 AI JSON 入口统一走容错 JSON 提取器，失败时生成 structured incident 和 blocked/report。
- **覆盖**: → `ink_writer/core/cli/checkpoint_utils.py:report_has_issues:90`

### EDGE-009: 外部 Claude/Gemini/Codex 子进程超时
- **场景**: `/ink-auto` 子进程长时间无输出，watchdog 到期。
- **触发方式**: 用假命令替代 Claude CLI，使其 sleep 超过 watchdog。
- **当前行为预测**: 阶段 1 显示 `run_cli_process` 负责 watchdog 和日志；超时应记录日志并返回失败，但主流程可能因关键步骤失败退出。
- **是否是 bug**: 待定
- **风险等级**: 🟡报错/功能不可用
- **建议修复方向**: 将 timeout 类型写入 call trace，并区分可重试步骤与必须阻断步骤。
- **覆盖**: → `ink-writer/scripts/ink-auto.sh:run_cli_process:773`, `ink-writer/scripts/ink-auto.sh:_start_cli_watchdog:745`

### EDGE-010: Debug Collector 并发写 `events.jsonl`
- **场景**: Hook 与写章 invariant 同时记录事件。
- **触发方式**: 多进程同时调用 `Collector.record` 写同一项目的 `.ink-debug/events.jsonl`。
- **当前行为预测**: `_write_jsonl` 用普通 append，无显式文件锁；小行追加通常可用，但跨平台不保证多进程行级原子。
- **是否是 bug**: 待定
- **风险等级**: 🟡报错/功能不可用
- **建议修复方向**: 复用 `_compat.locking` 或采用 SQLite 直接写入队列，保证跨平台行完整性。
- **覆盖**: → `ink_writer/debug/collector.py:_write_jsonl:29`

### EDGE-011: workflow_state 并发写入
- **场景**: `/ink-auto` 正在更新任务状态，用户同时执行 `/ink-resume` 或 `workflow clear`。
- **触发方式**: 两个终端同时操作同一项目 `.ink/workflow_state.json`。
- **当前行为预测**: `load_state`/`save_state` 若无锁，后写覆盖先写，可能丢失失败步骤或 current_task。
- **是否是 bug**: 待定
- **风险等级**: 🔴卡死/数据丢失
- **建议修复方向**: 对 workflow_state 引入文件锁和原子写；clear/fail 前校验 revision。
- **覆盖**: → `ink-writer/scripts/workflow_manager.py:clear_current_task:854`, `ink-writer/scripts/workflow_manager.py:load_state:895`

### EDGE-012: 交互 bootstrap 中途 Ctrl+C
- **场景**: v27 空目录 7 题问答输入到一半，用户按 Ctrl+C。
- **触发方式**: 运行 `bash interactive_bootstrap.sh .ink-auto-blueprint.md` 后中断。
- **当前行为预测**: trap 调 `cleanup_on_interrupt` 删除半成品并 exit 130。
- **是否是 bug**: 否
- **风险等级**: 🟢体验问题
- **建议修复方向**: 保持当前行为；可追加“未初始化项目”的提示。
- **覆盖**: → `ink-writer/scripts/interactive_bootstrap.sh:cleanup_on_interrupt:12`

### EDGE-013: 蓝本极长导致后续 context 膨胀
- **场景**: 用户把完整 20 万字设定集放进一个蓝本 md。
- **触发方式**: v27 扫描到超大蓝本并转换为 quick draft。
- **当前行为预测**: `parse_blueprint` 会完整读入内存，`to_quick_draft` 保留长字段，下游 LLM prompt 可能超过 context window。
- **是否是 bug**: 待定
- **风险等级**: 🟡报错/功能不可用
- **建议修复方向**: 对蓝本总字数和单字段字数设置软/硬上限，超限时摘要或拒绝。
- **覆盖**: → `ink_writer/core/auto/blueprint_to_quick_draft.py:parse_blueprint:50`

### EDGE-014: 蓝本必填字段为空
- **场景**: section 标题存在，但正文为空。
- **触发方式**: `### 核心冲突` 后直接进入下一节。
- **当前行为预测**: `_clean_body` 返回 `None`，`validate` 报缺必填字段。
- **是否是 bug**: 否
- **风险等级**: 🟡报错/功能不可用
- **建议修复方向**: 当前行为可接受；错误信息可附模板示例。
- **覆盖**: → `ink_writer/core/auto/blueprint_to_quick_draft.py:_clean_body:90`, `ink_writer/core/auto/blueprint_to_quick_draft.py:validate:106`

### EDGE-015: 纯 Unicode 标题和角色名
- **场景**: 书名、角色名、路径全是中文或全角符号。
- **触发方式**: `ink.py init <中文路径> 雾港问心录 都市悬疑 --protagonist-name 许照`。
- **当前行为预测**: Python `Path` 与 UTF-8 写文件应正常；shell 入口在 Windows 需依赖 UTF-8 stdio helper。
- **是否是 bug**: 否
- **风险等级**: 🟢体验问题
- **建议修复方向**: 保持跨平台 smoke 测试；Windows sibling 继续强制 UTF-8。
- **覆盖**: → `ink-writer/scripts/ink.py:main:24`

### EDGE-016: 中英混排与 Emoji 写入 Markdown/JSON
- **场景**: 主角名为 `Alex许照✨`，书名含 Emoji。
- **触发方式**: 执行 init 并检查 `state.json`、`设定集/主角卡.md`。
- **当前行为预测**: `ensure_ascii=False` 的 JSON 和 UTF-8 Markdown 可保存；但文件名清理策略可能不一致。
- **是否是 bug**: 待定
- **风险等级**: 🟢体验问题
- **建议修复方向**: 明确哪些字段允许 Emoji，哪些字段用于文件名前必须 sanitize。
- **覆盖**: → `ink-writer/scripts/init_project.py:main:871`

### EDGE-017: CLI 缺失必填参数
- **场景**: 用户直接运行 `ink.py init`，未给 project_dir/title/genre。
- **触发方式**: `python ink-writer/scripts/ink.py init`。
- **当前行为预测**: argparse 输出 usage 并以非 0 退出。
- **是否是 bug**: 否
- **风险等级**: 🟡报错/功能不可用
- **建议修复方向**: slash command 层避免让用户直接撞 argparse；文档给最小命令样例。
- **覆盖**: → `ink-writer/scripts/init_project.py:main:871`

### EDGE-018: 重复或冲突的 `--project-root`
- **场景**: 用户或 wrapper 重复传入两个不同 `--project-root`。
- **触发方式**: `python ink.py --project-root A --project-root B where`。
- **当前行为预测**: argparse 通常采用最后一个值；用户可能不知道实际使用的是 B。
- **是否是 bug**: 待定
- **风险等级**: 🟢体验问题
- **建议修复方向**: 对关键路径参数增加冲突检测，或在 `where`/preflight 输出来源。
- **覆盖**: → `ink_writer/core/cli/ink.py:main:426`

### EDGE-019: checkpoint 章节号为 0 或负数
- **场景**: 外部脚本传 `--chapter 0` 或 `--chapter -5`。
- **触发方式**: `python ink.py checkpoint-level --chapter 0`。
- **当前行为预测**: `chapter % 200 == 0` 对 0 成立，会返回 Tier3；负数也可能触发取模分支，语义错误。
- **是否是 bug**: 是
- **风险等级**: 🟡报错/功能不可用
- **建议修复方向**: 在 CLI 层或 `determine_checkpoint` 开头拒绝 `chapter < 1`。
- **覆盖**: → `ink_writer/core/cli/checkpoint_utils.py:determine_checkpoint:30`

### EDGE-020: Debug CLI key 与配置禁用冲突
- **场景**: `INK_DEBUG_OFF=1` 时用户执行 `toggle layer_c on`。
- **触发方式**: 设置环境变量后运行 `python -m ink_writer.debug.cli toggle layer_c on`。
- **当前行为预测**: toggle 会写 local config，但 `load_config` 最后仍因 env 把 master 关掉，用户以为已开启但事件不记录。
- **是否是 bug**: 待定
- **风险等级**: 🟢体验问题
- **建议修复方向**: toggle/status 明确显示 env override 优先级。
- **覆盖**: → `ink_writer/debug/config.py:load_config:130`, `ink_writer/debug/cli.py:cmd_toggle:73`

### EDGE-021: 路径含空格
- **场景**: 项目位于 `/Users/me/AI 小说/ink book`。
- **触发方式**: 执行 `ink.py --project-root "/Users/me/AI 小说/ink book" where` 与 debug CLI。
- **当前行为预测**: Python 子进程参数列表可正常处理；bash prompt 拼接路径的地方仍可能受影响。
- **是否是 bug**: 待定
- **风险等级**: 🟢体验问题
- **建议修复方向**: 所有 shell 入口使用数组传参，不用字符串拼接 prompt 表达路径。
- **覆盖**: → `ink-writer/scripts/ink.py:main:24`

### EDGE-022: 路径含中文
- **场景**: 项目位于 `/Users/cipher/AI/小说/ink/某本书`。
- **触发方式**: 执行 init、where、debug report。
- **当前行为预测**: macOS 下正常；Windows 依赖 `enable_windows_utf8_stdio` 与 PowerShell sibling。
- **是否是 bug**: 否
- **风险等级**: 🟢体验问题
- **建议修复方向**: 保留跨平台路径 fixture，发布前在 Windows smoke 中跑一次。
- **覆盖**: → `ink-writer/scripts/ink.py:main:39`

### EDGE-023: 从嵌套 cwd 使用相对路径
- **场景**: 用户在 `正文/` 子目录执行相对路径命令。
- **触发方式**: `cd <project>/正文 && python <repo>/ink-writer/scripts/ink.py --project-root .. where`。
- **当前行为预测**: `Path.resolve` 应定位父项目；未传 `--project-root` 时依赖 project locator，可能找不到或找错。
- **是否是 bug**: 待定
- **风险等级**: 🟡报错/功能不可用
- **建议修复方向**: 所有 slash command 优先注入绝对 `PROJECT_ROOT`，CLI 输出 resolve 后路径。
- **覆盖**: → `ink-writer/scripts/ink.py:main:24`

### EDGE-024: 项目根是软链接
- **场景**: `~/current-book` symlink 到真实项目目录。
- **触发方式**: 用 symlink 路径执行 `ink.py --project-root ~/current-book where`。
- **当前行为预测**: `resolve()` 后路径与用户输入不同；缓存、默认项目指针或日志可能混用真实路径和 symlink 路径。
- **是否是 bug**: 待定
- **风险等级**: 🟢体验问题
- **建议修复方向**: 统一内部使用 resolved path，UI 同时显示原始输入和 resolved path。
- **覆盖**: → `ink-writer/scripts/ink.py:main:24`

### EDGE-025: macOS 下用户传 Windows 反斜杠路径
- **场景**: 用户复制文档中的 `C:\Users\me\book` 到 macOS shell。
- **触发方式**: `python ink.py --project-root 'C:\Users\me\book' where`。
- **当前行为预测**: macOS 将其视为普通相对路径字符串，可能创建或查找奇怪目录。
- **是否是 bug**: 待定
- **风险等级**: 🟢体验问题
- **建议修复方向**: 在非 Windows 平台检测 `^[A-Za-z]:\\` 并提示路径格式不匹配。
- **覆盖**: → `ink_writer/core/cli/ink.py:cmd_where:221`, `ink_writer/core/cli/ink.py:main:426`

### EDGE-026: AI 生成内容含 Markdown 控制字符破坏章节结构
- **场景**: AI 正文中输出 `---`、多级标题、代码块围栏，破坏预期章节模板。
- **触发方式**: 让 writer 返回带大量 `###`、````、YAML front matter 的正文。
- **当前行为预测**: 若 verify 只看字数和基础格式，可能把结构破坏的正文写入 `正文/第N章.md`。
- **是否是 bug**: 待定
- **风险等级**: 🟡报错/功能不可用
- **建议修复方向**: 增加章节 Markdown 结构 lint，正文区与元数据区分离。
- **覆盖**: → `ink-writer/scripts/ink-auto.sh:verify_chapter:591`

### EDGE-027: AI 生成内容超长被截断
- **场景**: writer 返回超过模型或 CLI 输出限制，末尾缺失章末钩子。
- **触发方式**: 让章节生成目标字数异常大，或外部 CLI 截断 stdout。
- **当前行为预测**: 如果 verify 主要依赖字数区间，截断但仍达下限的正文可能通过。
- **是否是 bug**: 待定
- **风险等级**: 🟡报错/功能不可用
- **建议修复方向**: verify 增加章节闭合信号、章末钩子、最后一句完整性检查。
- **覆盖**: → `ink-writer/scripts/ink-auto.sh:verify_chapter:591`

### EDGE-028: AI 返回空内容或全空白
- **场景**: writer 子进程成功退出但输出为空。
- **触发方式**: mock 外部 CLI 返回 exit 0 且 stdout 为空。
- **当前行为预测**: 字数 hard 区间应拦截；若写入空文件再检查，可能留下半成品。
- **是否是 bug**: 待定
- **风险等级**: 🟡报错/功能不可用
- **建议修复方向**: 写文件前先检查非空；失败时不要覆盖现有章节，记录 retry。
- **覆盖**: → `ink-writer/scripts/ink-auto.sh:verify_chapter:591`

### EDGE-029: 多次调用 AI 累积上下文导致 token 爆炸
- **场景**: 长篇项目到中后期，context pack 累积角色、伏笔、前情过多。
- **触发方式**: 连续写到 100+ 章并保留大量审查报告、记忆摘要。
- **当前行为预测**: ContextManager/RAG 可能装入过多内容；外部模型调用超 context 或降质。
- **是否是 bug**: 待定
- **风险等级**: 🟡报错/功能不可用
- **建议修复方向**: 对每类上下文设 token budget，并在 debug 中记录实际注入长度。
- **覆盖**: → `ink_writer/core/context/context_manager.py:assemble_context:158`, `ink_writer/core/context/context_manager.py:_compact_json_text:1338`

### EDGE-030: 生成内容覆盖用户手写章节
- **场景**: 用户手工修改 `正文/第12章.md` 后再次 `/ink-auto` 或 resume。
- **触发方式**: 在 workflow_state 指向第 12 章时手改正文，再执行恢复/重跑。
- **当前行为预测**: 如果写章步骤直接覆盖同名文件，用户改动可能丢失；cleanup 分支虽有备份，但正常重写路径未必备份。
- **是否是 bug**: 是
- **风险等级**: 🔴卡死/数据丢失
- **建议修复方向**: 写章前检测目标文件已存在且非本轮产物；强制备份或要求确认。
- **覆盖**: → `ink-writer/scripts/ink-auto.sh:run_chapter:947`, `ink-writer/scripts/workflow_manager.py:cleanup_artifacts:784`

### EDGE-031: blueprint scanner 选择最大但不是用户想要的蓝本
- **场景**: 空目录里有 `旧设定.md` 和 `新书蓝本.md`，旧设定更大。
- **触发方式**: v27 `/ink-auto` 自动扫描目录。
- **当前行为预测**: `find_blueprint` 按 `st_size` 取最大，可能误选旧设定。
- **是否是 bug**: 待定
- **风险等级**: 🟡报错/功能不可用
- **建议修复方向**: 支持显式文件名优先、交互确认，或按字段完整度评分而不是按大小。
- **覆盖**: → `ink_writer/core/auto/blueprint_scanner.py:find_blueprint:31`

## 类别覆盖索引

| 必需类别 | 覆盖条目 |
|---|---|
| 输入文件不存在 / 权限不足 / 编码异常 | EDGE-001, EDGE-002, EDGE-003 |
| 配置缺失 / 配置类型错误 / 配置字段未知 | EDGE-004, EDGE-005, EDGE-006 |
| 网络中断 / API 超时 / API 返回异常格式 | EDGE-007, EDGE-008, EDGE-009 |
| 并发写同一文件 / 中途 Ctrl+C | EDGE-010, EDGE-011, EDGE-012 |
| 极长输入 / 空输入 / 纯 Unicode / 中英混排 / Emoji | EDGE-013, EDGE-014, EDGE-015, EDGE-016 |
| CLI 参数冲突 / 缺失必填 / 格式错误 / 重复 | EDGE-017, EDGE-018, EDGE-019, EDGE-020 |
| 路径含空格 / 中文 / 相对路径 / 软链接 / Windows 反斜杠 | EDGE-021, EDGE-022, EDGE-023, EDGE-024, EDGE-025 |
| 写作工具特有 AI 输出风险 | EDGE-026, EDGE-027, EDGE-028, EDGE-029, EDGE-030 |

## 阶段 0/1 报告勘误

无。本文件包含若干“待定”项，这些是后续阶段 5-9 需要用测试基线或复现来确认的风险，不是对阶段 0/1 的勘误。
