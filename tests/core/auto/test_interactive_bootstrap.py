import subprocess
from pathlib import Path


def test_bootstrap_writes_blueprint_with_all_7_answers(tmp_path: Path) -> None:
    out = tmp_path / "bp.md"
    answers = "\n".join([
        "仙侠",          # 1 题材
        "寒门弟子；过度自尊不会服软",  # 2 主角
        "信息",          # 3 GF type
        "每读懂他人遗书借走立遗嘱者绝学三天",  # 4 GF line
        "弃徒带真凶回师门",  # 5 conflict
        "qidian",        # 6 platform
        "2",             # 7 aggression
    ]) + "\n"
    result = subprocess.run(
        ["bash", "ink-writer/scripts/interactive_bootstrap.sh", str(out)],
        input=answers, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    body = out.read_text(encoding="utf-8")
    assert "题材方向" in body and "仙侠" in body
    assert "金手指类型" in body and "信息" in body
    assert "qidian" in body


def test_bootstrap_uses_defaults_for_platform_and_aggression(tmp_path: Path) -> None:
    out = tmp_path / "bp.md"
    answers = "\n".join([
        "都市", "社畜逆袭", "信息", "二十字之内的爆点", "复仇主线",
        "",  # default platform
        "",  # default aggression
    ]) + "\n"
    result = subprocess.run(
        ["bash", "ink-writer/scripts/interactive_bootstrap.sh", str(out)],
        input=answers, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    body = out.read_text(encoding="utf-8")
    assert "qidian" in body
    assert "\n2\n" in body  # aggression default


def test_bootstrap_rejects_empty_required(tmp_path: Path) -> None:
    out = tmp_path / "bp.md"
    # First answer is empty, second is filled — should re-prompt and use second
    answers = "\n".join([
        "",              # 1 empty (re-prompt)
        "仙侠",          # 1 retry
        "寒门弟子",
        "信息",
        "二十字之内的爆点",
        "弃徒",
        "qidian",
        "2",
    ]) + "\n"
    result = subprocess.run(
        ["bash", "ink-writer/scripts/interactive_bootstrap.sh", str(out)],
        input=answers, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "必填" in result.stderr
    body = out.read_text(encoding="utf-8")
    assert "仙侠" in body
