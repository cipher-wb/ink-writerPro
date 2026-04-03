# Installing ink-writer for Codex CLI

通过 Codex 原生 skill 发现机制启用 ink-writer。克隆仓库并创建符号链接即可。

## 前置条件

- Git
- Python 3.10+
- Codex CLI（启用 multi_agent 特性）

## 安装步骤

1. **克隆仓库：**
   ```bash
   git clone https://github.com/cipher-wb/ink-writerPro.git ~/.codex/ink-writer
   ```

2. **安装 Python 依赖：**
   ```bash
   pip install -r ~/.codex/ink-writer/requirements.txt
   ```

3. **创建 skills 符号链接：**
   ```bash
   mkdir -p ~/.agents/skills
   ln -s ~/.codex/ink-writer/ink-writer/skills ~/.agents/skills/ink-writer
   ```

   **Windows (PowerShell)：**
   ```powershell
   New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.agents\skills"
   cmd /c mklink /J "$env:USERPROFILE\.agents\skills\ink-writer" "$env:USERPROFILE\.codex\ink-writer\ink-writer\skills"
   ```

4. **启用多 Agent 支持**（可选，用于 ink-write 的子 Agent 派发）：

   编辑 `~/.codex/config.toml`：
   ```toml
   [features]
   multi_agent = true
   ```

5. **设置环境变量：**

   在 shell 配置中添加：
   ```bash
   export INK_PLUGIN_ROOT="$HOME/.codex/ink-writer/ink-writer"
   export CLAUDE_PLUGIN_ROOT="$INK_PLUGIN_ROOT"  # 兼容 skill 中的路径引用
   ```

6. **重启 Codex CLI** 以发现新 skills。

## 验证

```bash
ls -la ~/.agents/skills/ink-writer
```

应显示指向 ink-writer skills 目录的符号链接。

## 使用

进入你的小说项目目录（包含 `.ink/state.json`），Codex 会自动发现并提供 ink-writer 的 skills。

可用 skills：
- `ink-init` — 初始化新项目
- `ink-plan` — 规划卷/章大纲
- `ink-auto` — **主力命令**——批量写 N 章 + 自动审查修复 + 自动规划
- `ink-write` — 写作单章
- ~~`ink-5`~~ — ⚠️ 已弃用，请使用 `ink-auto 5` 替代
- `ink-review` — 质量审查
- `ink-macro-review` — 宏观审查
- `ink-query` — 查询项目状态
- `ink-audit` — 数据审计
- `ink-resolve` — 实体消歧
- `ink-resume` — 中断恢复
- `ink-learn` — 模式提取
- `ink-dashboard` — 可视化面板
- `ink-migrate` — 旧项目迁移（v8.x → v9.0）

工具映射参考：`ink-writer/references/codex-tools.md`

## 更新

```bash
cd ~/.codex/ink-writer && git pull
```

Skills 通过符号链接即时更新。

## 卸载

```bash
rm ~/.agents/skills/ink-writer
rm -rf ~/.codex/ink-writer
```
