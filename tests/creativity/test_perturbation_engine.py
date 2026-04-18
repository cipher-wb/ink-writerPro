"""v16 US-012：扰动引擎单元测试（含确定性 + 可复现）。"""

from __future__ import annotations

from ink_writer.creativity.perturbation_engine import (
    draw_perturbation_pairs,
    load_seeds,
    stable_hash,
)


_FAKE_SEEDS: list[dict] = [
    {"seed_id": "p1", "category": "profession", "value": "法医", "rarity": 3},
    {"seed_id": "p2", "category": "profession", "value": "殡仪", "rarity": 5},
    {"seed_id": "t1", "category": "taboo", "value": "摸死者", "rarity": 4},
    {"seed_id": "t2", "category": "taboo", "value": "睡棺", "rarity": 2},
    {"seed_id": "o1", "category": "object", "value": "铁锚", "rarity": 1},
    {"seed_id": "o2", "category": "object", "value": "黄铜钟", "rarity": 2},
    {"seed_id": "m1", "category": "mythology", "value": "三界志", "rarity": 5},
]


class TestStableHash:
    def test_deterministic(self):
        assert stable_hash("2026-04-18", "仙侠") == stable_hash("2026-04-18", "仙侠")

    def test_different_inputs_different_outputs(self):
        assert stable_hash("2026-04-18", "仙侠") != stable_hash("2026-04-19", "仙侠")
        assert stable_hash("2026-04-18", "仙侠") != stable_hash("2026-04-18", "都市")

    def test_returns_int(self):
        assert isinstance(stable_hash("a", "b"), int)


class TestDrawPairs:
    def test_reproducible_with_same_seed(self):
        rng_seed = stable_hash("2026-04-18", "仙侠")
        p1 = draw_perturbation_pairs(_FAKE_SEEDS, n_pairs=3, rng_seed=rng_seed)
        p2 = draw_perturbation_pairs(_FAKE_SEEDS, n_pairs=3, rng_seed=rng_seed)
        ids1 = [(p.seed_a["seed_id"], p.seed_b["seed_id"]) for p in p1]
        ids2 = [(p.seed_a["seed_id"], p.seed_b["seed_id"]) for p in p2]
        assert ids1 == ids2, "同 seed 必须输出完全一致"

    def test_different_seed_different_output(self):
        p1 = draw_perturbation_pairs(_FAKE_SEEDS, 5, rng_seed=1)
        p2 = draw_perturbation_pairs(_FAKE_SEEDS, 5, rng_seed=2)
        ids1 = [(p.seed_a["seed_id"], p.seed_b["seed_id"]) for p in p1]
        ids2 = [(p.seed_a["seed_id"], p.seed_b["seed_id"]) for p in p2]
        assert ids1 != ids2

    def test_different_categories_by_default(self):
        pairs = draw_perturbation_pairs(_FAKE_SEEDS, 10, rng_seed=42)
        for p in pairs:
            assert p.seed_a["category"] != p.seed_b["category"], (
                f"pair {p.seed_a['seed_id']}↔{p.seed_b['seed_id']} 同 category 违反默认约束"
            )

    def test_empty_seeds_returns_empty(self):
        assert draw_perturbation_pairs([], 3, rng_seed=1) == []

    def test_single_seed_returns_empty(self):
        assert draw_perturbation_pairs(_FAKE_SEEDS[:1], 3, rng_seed=1) == []

    def test_zero_pairs(self):
        assert draw_perturbation_pairs(_FAKE_SEEDS, 0, rng_seed=1) == []

    def test_rarity_weight_affects_distribution(self):
        # rarity=5 的稀缺 seed 权重 = 2^4 = 16；rarity=1 的权重 = 1。
        # 抽 200 对，统计 rarity=5 的 seed 出现次数应远超 rarity=1。
        pairs = draw_perturbation_pairs(_FAKE_SEEDS, 200, rng_seed=123)
        hits_r5 = sum(
            1 for p in pairs
            if p.seed_a.get("rarity") == 5 or p.seed_b.get("rarity") == 5
        )
        hits_r1 = sum(
            1 for p in pairs
            if p.seed_a.get("rarity") == 1 or p.seed_b.get("rarity") == 1
        )
        assert hits_r5 > hits_r1, (
            f"rarity 加权失效：r5={hits_r5} r1={hits_r1}"
        )

    def test_pair_to_dict(self):
        pairs = draw_perturbation_pairs(_FAKE_SEEDS, 1, rng_seed=1)
        d = pairs[0].to_dict()
        assert "seed_a" in d and "seed_b" in d


class TestLoadSeeds:
    def test_loads_real_file(self):
        seeds = load_seeds()
        # 仓库内置 skeleton 约 1012 seeds
        assert len(seeds) > 100, f"expected >100 seeds, got {len(seeds)}"
        assert all("seed_id" in s for s in seeds[:10])
