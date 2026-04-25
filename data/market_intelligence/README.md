# market_intelligence

存放 M4 P0 上游策划层 checker 的数据资产。

## qidian_top200.jsonl

`genre-novelty-checker` 的真相源（起点月票榜 top200 简介库）。每行一个 JSON
记录，schema：

```json
{
  "rank": 1,
  "title": "...",
  "author": "...",
  "url": "https://www.qidian.com/book/...",
  "genre_tags": ["玄幻", "东方玄幻"],
  "intro_one_liner": "首句 / 钩子简介",
  "intro_full": "完整简介",
  "fetched_at": "2026-04-25T..."
}
```

抓取脚本：[`scripts/market_intelligence/fetch_qidian_top200.py`](../../scripts/market_intelligence/fetch_qidian_top200.py)。

### 当前状态：`[manual-fallback-needed]`

US-007 实跑时起点 `/rank/yuepiao/pageN/` 返回 HTTP 202 + JavaScript 反爬挑战
（probe.js / buid 注入），无 JS 引擎的纯 HTTP 抓取拿不到榜单数据。jsonl
文件保留为空让 `genre-novelty-checker` 的 `empty top200 → score=1.0 skipped`
分支兜底，US-014 e2e 用 fixture 跑通策划链路（不阻塞 M4 验收）。

后续手动补齐路径（任选其一）：

1. 用 Playwright / Selenium / Puppeteer 等带 JS 引擎的浏览器自动化框架
   重写 `_fetch_rank_page`。
2. 改抓 RSS / 第三方榜单 API（番茄 / 七猫 / NovelRank 等）。
3. 人工从浏览器导出 top200 列表后通过本脚本的 `_fetch_one_book` 批量抓详情。

## llm_naming_blacklist.json

`naming-style-checker` 的真相源（高频 AI 起名词典）。schema 见 PRD US-008。
