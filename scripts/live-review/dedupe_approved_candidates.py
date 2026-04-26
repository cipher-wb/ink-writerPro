#!/usr/bin/env python3
"""§M-7 后处理：在 approved 候选间做 bge cosine 去重，自动 keep 长版本，reject 其他。

设计：
- 仅对 ``approved=True`` 候选做内部 pairwise 去重（已 reject/null 不动）。
- bge-small-zh-v1.5 embedding cosine > threshold（默认 0.85）视为重复。
- Union-Find 把所有重复对合并成 cluster；每 cluster 自动 keep "rule 最长" 的一条
  （tie-break：原数组下标最小），其他成员 ``approved=False`` 并写 ``dedupe_reason``
  指向 keep 的 ID。
- ``--dry-run``（默认）只生成 markdown 报告不动文件；``--apply`` 真改 candidates.json。

CLI:
    python3 scripts/live-review/dedupe_approved_candidates.py \\
        --candidates data/live-review/rule_candidates.json \\
        --report reports/live-review-dedupe-<timestamp>.md
    # 看完报告满意后追加 --apply 真写盘

退出码:
    0  成功（dry-run 或 apply 都返回 0）
    1  candidates 文件解析失败 / IO 失败
    2  candidates 文件不存在
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_DEFAULT_CANDIDATES = _REPO_ROOT / "data" / "live-review" / "rule_candidates.json"
_BGE_MODEL_NAME = "BAAI/bge-small-zh-v1.5"


class DedupeError(RuntimeError):
    pass


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Dedupe approved live-review rule candidates by bge cosine similarity.",
    )
    p.add_argument("--candidates", default=str(_DEFAULT_CANDIDATES),
                   help="rule_candidates.json 路径")
    p.add_argument("--threshold", type=float, default=0.85,
                   help="cosine 去重阈值（>该值视为重复，默认 0.85）")
    p.add_argument("--report",
                   default=str(_REPO_ROOT / "reports" /
                               f"live-review-dedupe-{datetime.now(tz=UTC).strftime('%Y%m%d-%H%M%S')}.md"),
                   help="markdown 报告输出路径")
    p.add_argument("--apply", action="store_true",
                   help="真写盘（不带 = dry-run）")
    return p


class _UnionFind:
    """简单 union-find：把相似 pair 合并成 cluster。"""
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]  # path compression
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def _compute_pairs(texts: list[str], threshold: float) -> list[tuple[int, int, float]]:
    """跑 bge cosine，返回 (i, j, sim) 列表（i<j 上三角，sim>threshold）。"""
    try:
        import numpy as np  # noqa: PLC0415
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415
    except ImportError as exc:
        raise DedupeError(
            f"需要 sentence-transformers + numpy: {exc}"
        ) from exc

    model = SentenceTransformer(_BGE_MODEL_NAME)
    emb = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    emb = np.asarray(emb, dtype=np.float32)
    sim = emb @ emb.T
    n = sim.shape[0]
    np.fill_diagonal(sim, 0)
    pairs: list[tuple[int, int, float]] = []
    for i in range(n):
        for j in range(i + 1, n):
            s = float(sim[i, j])
            if s > threshold:
                pairs.append((i, j, s))
    pairs.sort(key=lambda x: -x[2])
    return pairs


def _form_clusters(
    n: int, pairs: list[tuple[int, int, float]]
) -> dict[int, list[int]]:
    """把 pair 用 union-find 拢成 cluster，返回 root_idx → [member_idx, ...]."""
    uf = _UnionFind(n)
    for i, j, _ in pairs:
        uf.union(i, j)
    clusters: dict[int, list[int]] = {}
    for i in range(n):
        if any(i in (a, b) for a, b, _ in pairs):
            r = uf.find(i)
            clusters.setdefault(r, []).append(i)
    return clusters


def _pick_keeper(members: list[int], approved: list[dict]) -> int:
    """每 cluster 选 keep：rule 最长 + tie-break 数组下标最小。"""
    return max(members, key=lambda i: (len(approved[i]["rule"]), -i))


def _render_report(
    *,
    threshold: float,
    total_approved: int,
    pairs: list[tuple[int, int, float]],
    clusters: dict[int, list[int]],
    approved: list[dict],
    keeper_per_cluster: dict[int, int],
    apply_mode: bool,
) -> str:
    lines: list[str] = []
    lines.append("# Live-Review Dedupe Report")
    lines.append("")
    lines.append(f"- Generated: {datetime.now(tz=UTC).isoformat()}")
    lines.append(f"- Mode: {'APPLY (写盘)' if apply_mode else 'DRY-RUN (只看报告)'}")
    lines.append(f"- Threshold (cosine): {threshold}")
    lines.append(f"- Approved candidates total: {total_approved}")
    lines.append(f"- Similar pairs (>{threshold}): {len(pairs)}")
    lines.append(f"- Clusters formed: {len(clusters)}")
    n_to_reject = sum(len(m) - 1 for m in clusters.values())
    n_kept = total_approved - n_to_reject
    lines.append(f"- After dedupe: keep {n_kept} / reject {n_to_reject}")
    lines.append("")
    lines.append("## Clusters")
    lines.append("")
    sorted_clusters = sorted(
        clusters.values(),
        key=lambda m: -len(m),
    )
    for cidx, members in enumerate(sorted_clusters, 1):
        keeper = keeper_per_cluster[id(members)] if id(members) in keeper_per_cluster else _pick_keeper(members, approved)
        lines.append(f"### Cluster {cidx} ({len(members)} members)")
        lines.append("")
        for m in sorted(members, key=lambda i: (i != keeper, i)):
            tag = "✅ KEEP" if m == keeper else "❌ reject"
            c = approved[m]
            lines.append(f"- {tag} `{c['id']}` `[{c['category']}/{c['severity']}]` "
                         f"({len(c['rule'])} chars)")
            lines.append(f"  > {c['rule']}")
        lines.append("")
    if not clusters:
        lines.append("_No clusters formed; all approved candidates are unique._")
        lines.append("")
    return "\n".join(lines) + "\n"


def run(*, candidates_path: Path, report_path: Path,
        threshold: float, apply_mode: bool) -> tuple[int, int]:
    if not candidates_path.is_file():
        raise FileNotFoundError(f"candidates not found: {candidates_path}")
    try:
        cands = json.loads(candidates_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DedupeError(f"candidates parse failed: {exc}") from exc
    if not isinstance(cands, list):
        raise DedupeError("candidates root must be a JSON array")

    approved_indices = [i for i, c in enumerate(cands) if c.get("approved") is True]
    approved = [cands[i] for i in approved_indices]
    if not approved:
        raise DedupeError("no approved candidates to dedupe")
    total_approved = len(approved)

    print(f"[dedupe] approved total: {total_approved}", file=sys.stderr)
    print("[dedupe] computing bge cosine...", file=sys.stderr)
    pairs = _compute_pairs([c["rule"] for c in approved], threshold)
    print(f"[dedupe] pairs > {threshold}: {len(pairs)}", file=sys.stderr)

    clusters = _form_clusters(total_approved, pairs)
    print(f"[dedupe] clusters: {len(clusters)}", file=sys.stderr)

    keeper_per_cluster: dict[int, int] = {}
    rejected_count = 0
    for members in clusters.values():
        keeper = _pick_keeper(members, approved)
        keeper_per_cluster[id(members)] = keeper
        for m in members:
            if m == keeper:
                continue
            rejected_count += 1
            if apply_mode:
                # 修改原 cands 数组（通过 approved_indices 映射回原下标）
                orig_idx = approved_indices[m]
                cands[orig_idx]["approved"] = False
                cands[orig_idx]["dedupe_reason"] = (
                    f"dup of {approved[keeper]['id']} (cosine>{threshold})"
                )

    report = _render_report(
        threshold=threshold,
        total_approved=total_approved,
        pairs=pairs,
        clusters=clusters,
        approved=approved,
        keeper_per_cluster=keeper_per_cluster,
        apply_mode=apply_mode,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    print(f"[dedupe] report → {report_path}", file=sys.stderr)

    if apply_mode:
        candidates_path.write_text(
            json.dumps(cands, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"[dedupe] APPLY: {rejected_count} rejected → {candidates_path}",
              file=sys.stderr)
    else:
        print(f"[dedupe] DRY-RUN: would reject {rejected_count} (no write)",
              file=sys.stderr)

    return total_approved, rejected_count


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        total, rejected = run(
            candidates_path=Path(args.candidates),
            report_path=Path(args.report),
            threshold=float(args.threshold),
            apply_mode=bool(args.apply),
        )
    except FileNotFoundError as exc:
        print(f"[dedupe] not found: {exc}", file=sys.stderr)
        return 2
    except DedupeError as exc:
        print(f"[dedupe] FAIL: {exc}", file=sys.stderr)
        return 1
    final = total - rejected
    print(f"[dedupe] OK total={total} reject={rejected} keep={final}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
