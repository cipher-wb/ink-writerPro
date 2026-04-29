# 配置 Embedding / Rerank API（5 分钟搞定）

> 给 cipher 的小白指南。一次配完，所有小说项目共用。

## 为什么要配？

软件写章节时需要"语义搜索"过去的内容（前文设定、相似爆款案例、伏笔标记）。这件事靠两个外部 API 做：

- **Embedding**：把文字转成向量。**用 ModelScope（阿里魔搭）免费**。
- **Rerank**：对搜索结果重排序。**用 Jina 免费档**。

不配的话，软件 preflight 会硬阻断，你跑 `/ink-auto` 会直接报错。

---

## 步骤 1：注册 ModelScope，拿 EMBED token

1. 打开 https://modelscope.cn ，**手机号注册**（淘宝/支付宝可登）
2. 右上角头像 → **个人中心** → 左侧 **访问令牌**
3. 点"创建 SDK 令牌"，**复制 token**（形如 `ms-xxxxxxxx...`）

## 步骤 2：注册 Jina，拿 RERANK key

1. 打开 https://jina.ai ，**邮箱注册**（用 Google 账号也行）
2. 登录后 → 顶部 **API Key** → 默认会有一个 **Free** key
3. 点击复制（形如 `jina_xxxxxxxx...`）

## 步骤 3：把两个 key 落到全局 .env

打开 Mac 终端，跑：

```bash
# 创建目录（已有就跳过）
mkdir -p ~/.claude/ink-writer/

# 复制模板过去
cp /Users/cipher/AI/小说/ink/ink-writer/templates/dotenv-template.env ~/.claude/ink-writer/.env

# 用 VS Code / Cursor 打开编辑（或者 nano / vim 也行）
open ~/.claude/ink-writer/.env
```

把 `EMBED_API_KEY=` 后面的占位符**整段替换**成你刚拿到的 ModelScope token。
把 `RERANK_API_KEY=` 后面的占位符**整段替换**成你刚拿到的 Jina key。

例子（不要照搬，用你自己的）：
```
EMBED_API_KEY=ms-1234567890abcdef
RERANK_API_KEY=jina_abcdef123456
```

保存关闭。

## 步骤 4：跑验证脚本，确认 key 真能用

```bash
bash /Users/cipher/AI/小说/ink/ink-writer/scripts/check-embedding-api.sh
```

预期输出：
```
✅ .env 存在
✅ EMBED_API_KEY 已设置
✅ Embedding API 调通（向量维度 = 4096）
✅ RERANK_API_KEY 已设置
✅ Rerank API 调通
═══════════════════════════════════════
  ✅ 全部通过，可以放心跑 /ink-auto
═══════════════════════════════════════
```

如果某一步红了，脚本会告诉你具体修法（一般就是 token 写错了或者额度问题）。

## 步骤 5：回去跑你的 /ink-auto

```bash
cd /Users/cipher/ai/小说/农村养殖场
# /ink-writer:ink-auto 5  （在 Claude Code 里）
```

预检里 `rag_embedding_api` 那一行应该变 OK 了。

---

## FAQ

**Q：每本小说都要配吗？**
A：不用。`~/.claude/ink-writer/.env` 是全局的，所有书共用。某本书有特殊配置时可在那本书的根目录放一份 `.env`（项目级优先）。

**Q：ModelScope 免费额度够吗？**
A：每天写 5-10 章绰绰有余。新人额度通常每月几十万 token。

**Q：用别的 embedding（比如 OpenAI）行吗？**
A：行，但要同时改 `EMBED_BASE_URL` / `EMBED_MODEL` / `EMBED_API_KEY` 三个值，让它们指向新的提供商和模型。

**Q：万一以后这些服务挂了怎么办？**
A：软件设计上 RAG 是"增强"——挂了会回退到 BM25 关键词搜索，效果差点但能跑。但当前 preflight 卡了硬约束，要等后续把硬约束改成软警告。
