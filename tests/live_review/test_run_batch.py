"""US-LR-006: run_batch.py 全量批跑 + 断点续跑 + 失败可跳过。

5 用例覆盖 4 场景 (b 拆为 b1/b2 两子场景):
- (a) 5 文件全 mock 齐 + 无 --skip-failed → 5 jsonl + _failed 不存在 + exit 0
- (b1) 1 文件无 mock + --skip-failed → 4 jsonl + _failed.jsonl 1 条 + exit 0
- (b2) 1 文件无 mock + 非 --skip-failed → exit 1
- (c) --resume：先 --limit 3、再不限 → 第二次仅处理新增 2 个
- (d) --limit 2 → 仅前 2 个被处理
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "live-review" / "run_batch.py"
SCHEMA_PATH = REPO_ROOT / "schemas" / "live_review_extracted.schema.json"

ALL_BVIDS = ["BV1AAA", "BV1BBB", "BV1CCC", "BV1DDD", "BV1EEE"]
FAIL_BVID = "BV1CCC"


def _minimal_record(idx: int = 0) -> dict:
    return {
        "novel_idx": idx,
        "line_start": 1,
        "line_end": 5,
        "title_guess": "占位",
        "title_confidence": 0.5,
        "genre_guess": ["其他"],
        "score": None,
        "score_raw": "n/a",
        "score_signal": "unknown",
        "verdict": "unknown",
        "overall_comment": "synth-mock",
        "comments": [],
    }


@pytest.fixture
def mock_batch_dir(fixtures_dir: Path) -> Path:
    return fixtures_dir / "mock_batch"


@pytest.fixture
def complete_mock_dir(tmp_path: Path, mock_batch_dir: Path) -> Path:
    """复制 mock_batch 4 mock + 合成缺失的 BV1CCC.json，得到完整 5 mock 目录。"""
    dst = tmp_path / "mocks_complete"
    dst.mkdir()
    for src in mock_batch_dir.glob("*.json"):
        shutil.copy(src, dst / src.name)
    (dst / f"{FAIL_BVID}.json").write_text(
        json.dumps([_minimal_record(0)], ensure_ascii=False),
        encoding="utf-8",
    )
    return dst


@pytest.fixture
def schema_validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )


def test_a_all_mocks_present_produces_5_jsonl(
    tmp_path, mock_batch_dir, complete_mock_dir, schema_validator
):
    out = tmp_path / "out"
    proc = _run([
        "--input-dir", str(mock_batch_dir),
        "--output-dir", str(out),
        "--mock-llm-dir", str(complete_mock_dir),
    ])
    assert proc.returncode == 0, f"stderr={proc.stderr}\nstdout={proc.stdout}"
    for bvid in ALL_BVIDS:
        jsonl = out / f"{bvid}.jsonl"
        assert jsonl.exists(), f"missing {jsonl}"
        for line in jsonl.read_text(encoding="utf-8").strip().splitlines():
            errors = list(schema_validator.iter_errors(json.loads(line)))
            assert errors == [], f"{bvid}: {[e.message for e in errors]}"
    assert not (out / "_failed.jsonl").exists()


def test_b1_one_missing_mock_with_skip_failed_exits_0(tmp_path, mock_batch_dir):
    out = tmp_path / "out"
    proc = _run([
        "--input-dir", str(mock_batch_dir),
        "--output-dir", str(out),
        "--mock-llm-dir", str(mock_batch_dir),
        "--skip-failed",
    ])
    assert proc.returncode == 0, f"stderr={proc.stderr}\nstdout={proc.stdout}"
    for bvid in [b for b in ALL_BVIDS if b != FAIL_BVID]:
        assert (out / f"{bvid}.jsonl").exists(), f"missing {bvid}.jsonl"
    assert not (out / f"{FAIL_BVID}.jsonl").exists()
    failed = out / "_failed.jsonl"
    assert failed.exists()
    failures = [
        json.loads(line)
        for line in failed.read_text(encoding="utf-8").strip().splitlines()
    ]
    assert len(failures) == 1
    assert failures[0]["bvid"] == FAIL_BVID
    assert "error" in failures[0]
    assert "traceback" in failures[0]


def test_b2_one_missing_mock_no_skip_failed_exits_1(tmp_path, mock_batch_dir):
    out = tmp_path / "out"
    proc = _run([
        "--input-dir", str(mock_batch_dir),
        "--output-dir", str(out),
        "--mock-llm-dir", str(mock_batch_dir),
    ])
    assert proc.returncode == 1, f"stderr={proc.stderr}\nstdout={proc.stdout}"


def test_c_resume_skips_existing_jsonl(tmp_path, mock_batch_dir, complete_mock_dir):
    out = tmp_path / "out"
    # 第一次 --limit 3 跑前 3 个
    proc1 = _run([
        "--input-dir", str(mock_batch_dir),
        "--output-dir", str(out),
        "--mock-llm-dir", str(complete_mock_dir),
        "--limit", "3",
    ])
    assert proc1.returncode == 0, f"stderr={proc1.stderr}\nstdout={proc1.stdout}"
    first_done = sorted(p.stem for p in out.glob("BV*.jsonl"))
    assert first_done == ["BV1AAA", "BV1BBB", "BV1CCC"], first_done

    # 第二次 --resume 不限 → 仅处理新增 2 个 (BV1DDD, BV1EEE)
    proc2 = _run([
        "--input-dir", str(mock_batch_dir),
        "--output-dir", str(out),
        "--mock-llm-dir", str(complete_mock_dir),
        "--resume",
    ])
    assert proc2.returncode == 0, f"stderr={proc2.stderr}\nstdout={proc2.stdout}"
    final_done = sorted(p.stem for p in out.glob("BV*.jsonl"))
    assert final_done == ALL_BVIDS
    # 第二次日志应含 BV1DDD/BV1EEE done + BV1AAA/BB/CC skipped
    assert "BV1DDD" in proc2.stdout
    assert "BV1EEE" in proc2.stdout
    assert "skipped" in proc2.stdout.lower()


def test_d_limit_2_processes_only_first_two(tmp_path, mock_batch_dir, complete_mock_dir):
    out = tmp_path / "out"
    proc = _run([
        "--input-dir", str(mock_batch_dir),
        "--output-dir", str(out),
        "--mock-llm-dir", str(complete_mock_dir),
        "--limit", "2",
    ])
    assert proc.returncode == 0, f"stderr={proc.stderr}\nstdout={proc.stdout}"
    done = sorted(p.stem for p in out.glob("BV*.jsonl"))
    assert done == ["BV1AAA", "BV1BBB"]


# === 并发 worker 测试（M-2 之后新增；改 run_batch.py 加 --workers 后） ===


def test_e_workers_4_all_mocks_present_produces_5_jsonl(
    tmp_path, mock_batch_dir, complete_mock_dir, schema_validator
):
    """4 worker 并发跑 5 mock fixture，全 5 jsonl 生成且 schema 校验通过。"""
    out = tmp_path / "out"
    proc = _run([
        "--input-dir", str(mock_batch_dir),
        "--output-dir", str(out),
        "--mock-llm-dir", str(complete_mock_dir),
        "--workers", "4",
    ])
    assert proc.returncode == 0, f"stderr={proc.stderr}\nstdout={proc.stdout}"
    done = sorted(p.stem for p in out.glob("BV*.jsonl"))
    assert done == ALL_BVIDS
    # _failed.jsonl 不应存在
    assert not (out / "_failed.jsonl").exists()
    # 各 jsonl schema 全过
    for bvid in ALL_BVIDS:
        with open(out / f"{bvid}.jsonl", encoding="utf-8") as f:
            for line in f:
                schema_validator.validate(json.loads(line))


def test_f_workers_4_with_one_missing_mock_skip_failed(tmp_path, mock_batch_dir):
    """4 worker 并发：故意缺 1 mock 文件 + --skip-failed → 4 成功 + 1 失败入 _failed.jsonl + exit 0。"""
    out = tmp_path / "out"
    # 不传 complete_mock_dir，直接用 mock_batch_dir（缺 BV1CCC.json）
    proc = _run([
        "--input-dir", str(mock_batch_dir),
        "--output-dir", str(out),
        "--mock-llm-dir", str(mock_batch_dir),
        "--skip-failed",
        "--workers", "4",
    ])
    assert proc.returncode == 0, f"stderr={proc.stderr}\nstdout={proc.stdout}"
    done = sorted(p.stem for p in out.glob("BV*.jsonl"))
    # BV1CCC.jsonl 不应生成
    assert "BV1CCC" not in done
    assert len(done) == 4  # 其余 4 成功
    # _failed.jsonl 应存在且含 BV1CCC
    failed = out / "_failed.jsonl"
    assert failed.exists()
    failed_lines = [json.loads(line) for line in failed.read_text(encoding="utf-8").splitlines()]
    failed_bvids = [f["bvid"] for f in failed_lines]
    assert "BV1CCC" in failed_bvids


def test_g_workers_2_resume_with_partial_existing(tmp_path, mock_batch_dir, complete_mock_dir):
    """2 worker 并发 + --resume：已存在 BV1AAA.jsonl 时跳过它，仅处理另外 4 个。"""
    out = tmp_path / "out"
    out.mkdir()
    # 预先放一个空 BV1AAA.jsonl 模拟已存在
    (out / "BV1AAA.jsonl").write_text("", encoding="utf-8")

    proc = _run([
        "--input-dir", str(mock_batch_dir),
        "--output-dir", str(out),
        "--mock-llm-dir", str(complete_mock_dir),
        "--resume",
        "--workers", "2",
    ])
    assert proc.returncode == 0, f"stderr={proc.stderr}\nstdout={proc.stdout}"
    # BV1AAA 应被 skip 不被覆盖
    assert (out / "BV1AAA.jsonl").read_text(encoding="utf-8") == ""
    # 其他 4 个应有内容
    done = sorted(p.stem for p in out.glob("BV*.jsonl"))
    assert done == ALL_BVIDS  # 5 文件存在
    for bvid in ["BV1BBB", "BV1CCC", "BV1DDD", "BV1EEE"]:
        assert (out / f"{bvid}.jsonl").stat().st_size > 0
    assert "BV1AAA" in proc.stdout
    assert "skip" in proc.stdout.lower()
