# Qdrant（ink-writer）

Qdrant 向量数据库单机 Docker 部署。M1 起替换原 FAISS 索引，承载 `editor_wisdom_rules`（编辑智慧规则）与 `corpus_chunks`（场景级语料切片）两个 collection。

详细设计：`docs/superpowers/specs/2026-04-23-case-library-driven-quality-overhaul-design.md` §8。

## 前置

- Docker Desktop / Docker Engine（`docker compose` v2 子命令可用）
- 端口 6333（REST）、6334（gRPC）空闲

## 启动 / 停止

### Mac / Linux

```bash
scripts/qdrant/start.sh         # 启动并等待 ready（最多 30s）
scripts/qdrant/stop.sh          # 停止容器（storage 保留）
```

### Windows

```powershell
.\scripts\qdrant\start.ps1      # PowerShell（UTF-8 BOM，PS 5.1 兼容）
.\scripts\qdrant\stop.ps1
```

双击 `start.cmd` / `stop.cmd` 亦可（内部转发到 PowerShell）。

## 端点

| 用途 | 地址 |
|------|------|
| REST API | `http://127.0.0.1:6333` |
| gRPC | `127.0.0.1:6334` |
| ready probe | `http://127.0.0.1:6333/readyz` |
| 健康检查 collections | `GET http://127.0.0.1:6333/collections` |

启动脚本会轮询 `GET /readyz` 至 200 或超时（30s）。

## 持久化

数据保存在 `scripts/qdrant/storage/`（由 `docker-compose.yml` 的 volume mount 映射到容器内 `/qdrant/storage`）。该目录已加入 `.gitignore`，**请勿提交**。清空本地数据：先 `stop.sh` 再 `rm -rf scripts/qdrant/storage/`。

## 镜像与版本

- 镜像：`qdrant/qdrant:v1.12.4`
- 容器名：`ink-writer-qdrant`
- `restart: unless-stopped`：主机重启后自动拉起；手动 `stop` 后不会被拉起。
