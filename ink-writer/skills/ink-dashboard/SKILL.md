---
name: ink-dashboard
description: 启动可视化小说管理面板（只读 Web Dashboard），实时查看项目状态、实体图谱与章节内容。
allowed-tools: Bash Read
---

# Ink Dashboard

## 目标

在本地启动一个 **只读** Web 面板，用于可视化查看当前小说项目的：
- 创作进度与 Strand 节奏分布
- 设定词典（角色/地点/势力等实体）
- 关系图谱
- 章节与大纲内容浏览
- 追读力分析数据

面板通过 `watchdog` 监听 `.ink/` 目录变更并实时刷新，不对项目做任何修改。

## 执行步骤

### Step 0：环境确认

```bash
export INK_DASHBOARD=1
source "${CLAUDE_PLUGIN_ROOT}/scripts/env-setup.sh"
```
<!-- windows-ps1-sibling -->
Windows（PowerShell，与上方 bash 块等价，由 ink-auto.ps1 / env-setup.ps1 提供）：

```powershell
. "$env:CLAUDE_PLUGIN_ROOT/scripts/env-setup.ps1"
```


### Step 1：安装依赖（首次）

```bash
python3 -m pip install -r "${DASHBOARD_DIR}/requirements.txt" --quiet
```

### Step 2：解析项目根目录并准备 Python 模块路径

```bash
# SCRIPTS_DIR, PROJECT_ROOT 已由 env-setup.sh 导出
echo "项目路径: ${PROJECT_ROOT}"

# 确保 `python3 -m dashboard.server` 可在任意工作目录下找到插件模块
if [ -n "${PYTHONPATH:-}" ]; then
  export PYTHONPATH="${CLAUDE_PLUGIN_ROOT}:${PYTHONPATH}"
else
  export PYTHONPATH="${CLAUDE_PLUGIN_ROOT}"
fi

# 前端 dist 不再提交到 Git，首次使用时自动构建
if [ ! -f "${DASHBOARD_DIR}/frontend/dist/index.html" ]; then
  echo "首次启动，构建前端..."
  (cd "${DASHBOARD_DIR}/frontend" && npm install --silent && npm run build)
fi
```

### Step 3：启动 Dashboard

```bash
python3 -m dashboard.server --project-root "${PROJECT_ROOT}"
```

启动后会自动打开浏览器访问 `http://127.0.0.1:8765`。

如不需要自动打开浏览器，使用：

```bash
python3 -m dashboard.server --project-root "${PROJECT_ROOT}" --no-browser
```

## 注意事项

- Dashboard 为纯只读面板，所有 API 仅 GET，不提供任何修改接口。
- 文件读取严格限制在 `PROJECT_ROOT` 范围内，防止路径穿越。
- 如需自定义端口，添加 `--port 9000` 参数。

## M5 Case 治理（M5 P3 必跑）

M5 标签页聚合 4 大指标（recurrence_rate / repair_speed_days / editor_score_trend / checker_accuracy），并展示 dry-run 切真推荐、pending 元规则与复发 case 列表。

```bash
# 启动 dashboard（带 M5 标签页）
python3 -m dashboard.server --project-root "${PROJECT_ROOT}" --m5

# 直接拉 JSON 后端数据
curl -s http://127.0.0.1:8765/api/m5-overview | jq

# 一次性周报（写到 reports/weekly/<year>-W<NN>.md，US-006 提供）
python3 -m ink_writer.dashboard report --week 17 --year 2026
```

<!-- windows-ps1-sibling -->
Windows（PowerShell，与上方 bash 块等价）：

```powershell
python3 -m dashboard.server --project-root $env:PROJECT_ROOT --m5
Invoke-RestMethod http://127.0.0.1:8765/api/m5-overview | ConvertTo-Json -Depth 8
python3 -m ink_writer.dashboard report --week 17 --year 2026
```

读法速记：
- `metrics.recurrence_rate` = `regressed / (resolved + regressed)`，0.0 = 没有 resolved case 或全部稳定。
- `dry_run.{m3,m4}.recommendation` = `continue`（观察期未满）/ `investigate`（通过率 < 60%）/ `switch`（可切真阻断）。
- `pending_meta_rules` 非空时跑 `ink meta-rule list --status pending` + `ink meta-rule approve MR-NNNN` 审批。
- `recurrent_cases` 含 case_id + recurrence_count，是 Layer 4 复发追踪的实时输出。
