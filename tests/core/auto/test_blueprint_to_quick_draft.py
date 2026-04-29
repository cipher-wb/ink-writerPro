# tests/core/auto/test_blueprint_to_quick_draft.py
from pathlib import Path
import pytest
from ink_writer.core.auto.blueprint_to_quick_draft import (
    parse_blueprint,
    validate,
    to_quick_draft,
    BlueprintValidationError,
)
from tests.core.auto._blueprint_fixtures import (
    write_full_blueprint,
    write_minimal_blueprint,
    write_blueprint_missing_required,
    write_blueprint_with_gf_blacklist_word,
)


def test_parse_full_blueprint_extracts_known_sections(tmp_path: Path) -> None:
    bp = tmp_path / "bp.md"
    write_full_blueprint(bp)
    parsed = parse_blueprint(bp)
    assert parsed["平台"] == "qidian"
    assert parsed["激进度档位"] == "2"
    assert parsed["题材方向"] == "仙侠"
    assert parsed["主角人设"].startswith("寒门弟子")
    assert parsed["金手指类型"] == "信息"
    assert parsed["能力一句话"].startswith("每读懂他人遗书")
    # AUTO sentinel preserved as literal
    assert parsed["书名"] == "AUTO"


def test_parse_minimal_blueprint_marks_empty_optional_as_none(tmp_path: Path) -> None:
    bp = tmp_path / "bp.md"
    write_minimal_blueprint(bp)
    parsed = parse_blueprint(bp)
    assert parsed.get("书名") in (None, "")
    assert parsed["题材方向"] == "仙侠"


def test_validate_passes_for_complete_minimal(tmp_path: Path) -> None:
    bp = tmp_path / "bp.md"
    write_minimal_blueprint(bp)
    parsed = parse_blueprint(bp)
    validate(parsed)  # no raise


def test_validate_rejects_missing_required_field(tmp_path: Path) -> None:
    bp = tmp_path / "bp.md"
    write_blueprint_missing_required(bp)
    parsed = parse_blueprint(bp)
    with pytest.raises(BlueprintValidationError) as exc:
        validate(parsed)
    assert "主角人设" in str(exc.value)


def test_validate_rejects_gf_blacklist_word(tmp_path: Path) -> None:
    bp = tmp_path / "bp.md"
    write_blueprint_with_gf_blacklist_word(bp)
    parsed = parse_blueprint(bp)
    with pytest.raises(BlueprintValidationError) as exc:
        validate(parsed)
    assert "修为暴涨" in str(exc.value)


def test_to_quick_draft_qidian_defaults_for_missing_chapter_count(tmp_path: Path) -> None:
    bp = tmp_path / "bp.md"
    write_minimal_blueprint(bp)
    parsed = parse_blueprint(bp)
    draft = to_quick_draft(parsed)
    assert draft["platform"] == "qidian"
    assert draft["target_chapters"] == 600
    assert draft["chapter_words"] == 3000
    assert draft["aggression_level"] == 2


def test_to_quick_draft_fanqie_defaults(tmp_path: Path) -> None:
    bp = tmp_path / "bp.md"
    bp.write_text(
        "# 蓝本\n## 一、项目元信息\n### 平台\nfanqie\n### 激进度档位\n3\n"
        "## 二、故事核心\n### 题材方向\n都市\n### 核心冲突\n复仇\n"
        "## 三、主角设定\n### 主角人设\n社畜逆袭\n"
        "## 四、金手指\n### 金手指类型\n信息\n### 能力一句话\n二十字之内的爆点\n",
        encoding="utf-8",
    )
    parsed = parse_blueprint(bp)
    draft = to_quick_draft(parsed)
    assert draft["platform"] == "fanqie"
    assert draft["target_chapters"] == 800
    assert draft["chapter_words"] == 1500
    assert draft["aggression_level"] == 3


def test_to_quick_draft_marks_missing_optional_for_quick_engine(tmp_path: Path) -> None:
    bp = tmp_path / "bp.md"
    write_minimal_blueprint(bp)
    parsed = parse_blueprint(bp)
    draft = to_quick_draft(parsed)
    assert "__missing__" in draft
    # Optional fields not provided in minimal blueprint
    assert "书名" in draft["__missing__"]
    assert "女主姓名" in draft["__missing__"]


def test_cli_invocation_writes_draft_json(tmp_path: Path) -> None:
    import subprocess
    import json
    import sys

    bp = tmp_path / "bp.md"
    write_minimal_blueprint(bp)
    out = tmp_path / "draft.json"
    result = subprocess.run(
        [sys.executable, "-m", "ink_writer.core.auto.blueprint_to_quick_draft",
         "--input", str(bp), "--output", str(out)],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    assert "BLUEPRINT_OK" in result.stdout
    draft = json.loads(out.read_text(encoding="utf-8"))
    assert draft["platform"] == "qidian"
    assert draft["题材方向"] == "仙侠"


def test_cli_returns_exit2_on_invalid_blueprint(tmp_path: Path) -> None:
    import subprocess
    import sys

    bp = tmp_path / "bp.md"
    write_blueprint_missing_required(bp)
    out = tmp_path / "draft.json"
    result = subprocess.run(
        [sys.executable, "-m", "ink_writer.core.auto.blueprint_to_quick_draft",
         "--input", str(bp), "--output", str(out)],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 2
    assert "BLUEPRINT_INVALID" in result.stderr


def test_cli_returns_exit3_on_io_error(tmp_path: Path) -> None:
    import subprocess
    import sys

    # Input file does not exist → OSError → exit 3
    bp = tmp_path / "nonexistent.md"
    out = tmp_path / "draft.json"
    result = subprocess.run(
        [sys.executable, "-m", "ink_writer.core.auto.blueprint_to_quick_draft",
         "--input", str(bp), "--output", str(out)],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 3
    assert "BLUEPRINT_IO_ERROR" in result.stderr
