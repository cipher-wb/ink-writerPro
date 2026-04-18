"""v16 US-012：扰动引擎（Layer 3）。

从 anti-trope-seeds.json 按 rarity 加权随机抽 n 对"稀缺元素对"，供 Quick Mode
注入差异化创意。使用 ``stable_hash(timestamp, genre)`` 产生确定性 seed，保证
同入参可复现同输出。
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_DEFAULT_SEEDS_PATH = (
    Path(__file__).resolve().parents[2]
    / "ink-writer" / "skills" / "ink-init" / "references"
    / "creativity" / "anti-trope-seeds.json"
)


@dataclass
class PerturbationPair:
    seed_a: dict
    seed_b: dict

    def to_dict(self) -> dict:
        return {"seed_a": self.seed_a, "seed_b": self.seed_b}


def stable_hash(timestamp: str, genre: str) -> int:
    """确定性 seed：同 (timestamp, genre) 必得同值，跨 session 可复现。"""
    key = f"{timestamp}|{genre}".encode("utf-8")
    h = hashlib.sha256(key).digest()
    return int.from_bytes(h[:8], "big", signed=False)


def load_seeds(path: Optional[Path] = None) -> list[dict]:
    p = path or _DEFAULT_SEEDS_PATH
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return list(data.get("seeds", []))


def _rarity_weight(seed: dict) -> float:
    """rarity 1-5，高 rarity 稀缺 → 加大权重。这里用简单 2^(rarity-1)。"""
    try:
        r = int(seed.get("rarity", 1))
    except (TypeError, ValueError):
        r = 1
    r = max(1, min(5, r))
    return 2 ** (r - 1)


def draw_perturbation_pairs(
    seeds: list[dict],
    n_pairs: int,
    rng_seed: int,
    *,
    enforce_different_categories: bool = True,
) -> list[PerturbationPair]:
    """从 seeds 抽 n_pairs 对，按 rarity 加权。

    - 同 ``rng_seed`` 必得同输出（确定性）。
    - 默认每对的两个 seed 来自不同 category（提升扰动新鲜度）。
    - seeds 不足 2 条返回空列表。
    """
    if len(seeds) < 2 or n_pairs <= 0:
        return []

    rng = random.Random(rng_seed)
    weights = [_rarity_weight(s) for s in seeds]

    pairs: list[PerturbationPair] = []
    for _ in range(n_pairs):
        a = rng.choices(seeds, weights=weights, k=1)[0]
        b = a
        tries = 0
        while b is a or (
            enforce_different_categories
            and b.get("category") == a.get("category")
        ):
            b = rng.choices(seeds, weights=weights, k=1)[0]
            tries += 1
            if tries > 50:
                # 极端情况（seeds 只剩单一 category）：放宽约束
                b = rng.choices(seeds, weights=weights, k=1)[0]
                break
        pairs.append(PerturbationPair(seed_a=a, seed_b=b))
    return pairs


__all__ = [
    "PerturbationPair",
    "stable_hash",
    "load_seeds",
    "draw_perturbation_pairs",
]
