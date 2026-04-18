"""Tests for init_project.py — targeting untested lines to raise coverage ≥70%."""

import json
from unittest.mock import patch, MagicMock

import pytest

from init_project import (
    _read_text_if_exists,
    _write_text_if_missing,
    _split_genre_keys,
    _normalize_genre_key,
    _apply_label_replacements,
    _parse_tier_map,
    _render_team_rows,
    _ensure_state_schema,
    _build_master_outline,
    _inject_volume_rows,
    init_project,
)


# ── Helper functions ─────────────────────────────────────────────────────────


class TestReadTextIfExists:
    def test_returns_empty_when_file_missing(self, tmp_path):
        assert _read_text_if_exists(tmp_path / "nope.txt") == ""

    def test_returns_content_when_file_exists(self, tmp_path):
        f = tmp_path / "hello.txt"
        f.write_text("你好", encoding="utf-8")
        assert _read_text_if_exists(f) == "你好"


class TestWriteTextIfMissing:
    def test_writes_when_missing(self, tmp_path):
        p = tmp_path / "sub" / "new.txt"
        _write_text_if_missing(p, "content")
        assert p.read_text(encoding="utf-8") == "content"

    def test_skips_when_exists(self, tmp_path):
        p = tmp_path / "existing.txt"
        p.write_text("old", encoding="utf-8")
        _write_text_if_missing(p, "new")
        assert p.read_text(encoding="utf-8") == "old"


class TestSplitGenreKeys:
    def test_empty_string(self):
        assert _split_genre_keys("") == []

    def test_none_input(self):
        assert _split_genre_keys(None) == []

    def test_single_key(self):
        assert _split_genre_keys("修仙") == ["修仙"]

    def test_plus_separator(self):
        assert _split_genre_keys("都市脑洞+规则怪谈") == ["都市脑洞", "规则怪谈"]

    def test_fullwidth_plus(self):
        assert _split_genre_keys("修仙＋都市") == ["修仙", "都市"]

    def test_chinese_comma_separator(self):
        assert _split_genre_keys("修仙、都市") == ["修仙", "都市"]

    def test_yu_separator(self):
        assert _split_genre_keys("修仙与都市") == ["修仙", "都市"]


class TestNormalizeGenreKey:
    def test_known_alias(self):
        assert _normalize_genre_key("玄幻") == "修仙"

    def test_unknown_key_passthrough(self):
        assert _normalize_genre_key("科幻") == "科幻"

    def test_multiple_aliases(self):
        assert _normalize_genre_key("克系") == "克苏鲁"
        assert _normalize_genre_key("直播") == "直播文"


class TestApplyLabelReplacements:
    def test_empty_text(self):
        assert _apply_label_replacements("", {"k": "v"}) == ""

    def test_empty_replacements(self):
        assert _apply_label_replacements("hello", {}) == "hello"

    def test_replaces_matching_label(self):
        text = "- 体系类型：旧值\n- 其他：保留"
        result = _apply_label_replacements(text, {"体系类型": "新值"})
        assert "- 体系类型：新值" in result
        assert "- 其他：保留" in result

    def test_skips_empty_value(self):
        text = "- 姓名：原值"
        result = _apply_label_replacements(text, {"姓名": ""})
        assert result == text

    def test_preserves_leading_whitespace(self):
        text = "  - 姓名：旧"
        result = _apply_label_replacements(text, {"姓名": "新"})
        assert result == "  - 姓名：新"


class TestParseTierMap:
    def test_empty_string(self):
        assert _parse_tier_map("") == {}

    def test_single_tier(self):
        assert _parse_tier_map("小反派:张三") == {"小反派": "张三"}

    def test_multiple_tiers(self):
        result = _parse_tier_map("小反派:张三;中反派:李四;大反派:王五")
        assert result == {"小反派": "张三", "中反派": "李四", "大反派": "王五"}

    def test_skips_empty_parts(self):
        result = _parse_tier_map("小反派:张三;;")
        assert result == {"小反派": "张三"}

    def test_no_colon(self):
        # parts without ":" are silently skipped
        result = _parse_tier_map("无冒号;小反派:张三")
        assert result == {"小反派": "张三"}


class TestRenderTeamRows:
    def test_basic(self):
        rows = _render_team_rows(["Alice", "Bob"], ["主线", "副线"])
        assert len(rows) == 2
        assert "| Alice | 主线 |" in rows[0]
        assert "| Bob | 副线 |" in rows[1]

    def test_roles_shorter_than_names(self):
        rows = _render_team_rows(["A", "B", "C"], ["R1"])
        assert "| A | R1 |" in rows[0]
        assert "| B | 主线/副线 |" in rows[1]
        assert "| C | 主线/副线 |" in rows[2]


# ── State schema ─────────────────────────────────────────────────────────────


class TestEnsureStateSchema:
    def test_fills_defaults_on_empty_dict(self):
        state = _ensure_state_schema({})
        assert state["schema_version"] == 9
        assert "progress" in state
        assert state["progress"]["current_chapter"] == 0
        assert state["protagonist_state"]["name"] == ""
        assert state["protagonist_state"]["golden_finger"]["name"] == ""

    def test_preserves_existing_values(self):
        state = _ensure_state_schema({"schema_version": 5, "progress": {"current_chapter": 10}})
        assert state["schema_version"] == 5
        assert state["progress"]["current_chapter"] == 10


# ── Outline builders ─────────────────────────────────────────────────────────


class TestBuildMasterOutline:
    def test_single_volume(self):
        result = _build_master_outline(50)
        assert "第1卷" in result
        assert "第2卷" not in result

    def test_multiple_volumes(self):
        result = _build_master_outline(120, chapters_per_volume=50)
        assert "第1卷（第1-50章）" in result
        assert "第2卷（第51-100章）" in result
        assert "第3卷（第101-120章）" in result

    def test_zero_chapters(self):
        result = _build_master_outline(0)
        assert "第1卷" in result


class TestInjectVolumeRows:
    def test_no_header_returns_unchanged(self):
        text = "# 总纲\nsome content"
        assert _inject_volume_rows(text, 100) == text

    def test_injects_rows_after_header(self):
        text = "| 卷号 | 主题 | 章节 | 备注 | 状态 |\n|---|---|---|---|---|"
        result = _inject_volume_rows(text, 100, chapters_per_volume=50)
        assert "| 1 |" in result
        assert "| 2 |" in result

    def test_no_duplicate_injection(self):
        text = "| 卷号 | 主题 | 章节 | 备注 | 状态 |\n|---|---|---|---|---|\n| 1 | | 第1-50章 | | |"
        result = _inject_volume_rows(text, 50, chapters_per_volume=50)
        assert result.count("| 1 |") == 1


# ── init_project integration ─────────────────────────────────────────────────


@pytest.fixture
def _mock_externals():
    """Mock external dependencies of init_project to isolate filesystem tests."""
    with (
        patch("init_project.write_current_project_pointer", return_value=None),
        patch("init_project.is_git_available", return_value=False),
    ):
        yield


class TestInitProjectClaudePath:
    def test_rejects_claude_directory(self, tmp_path):
        claude_dir = tmp_path / ".claude" / "myproject"
        claude_dir.mkdir(parents=True, exist_ok=True)
        with pytest.raises(SystemExit, match="Refusing"):
            init_project(str(claude_dir), "书名", "修仙")


class TestInitProjectBasic:
    def test_creates_directory_structure(self, tmp_path, _mock_externals):
        proj = tmp_path / "proj"
        init_project(str(proj), "测试书", "修仙")
        assert (proj / ".ink" / "state.json").exists()
        assert (proj / ".ink" / "preferences.json").exists()
        assert (proj / ".ink" / "golden_three_plan.json").exists()
        assert (proj / "设定集" / "世界观.md").exists()
        assert (proj / "设定集" / "力量体系.md").exists()
        assert (proj / "设定集" / "主角卡.md").exists()
        assert (proj / "设定集" / "金手指设计.md").exists()
        assert (proj / "设定集" / "反派设计.md").exists()
        assert (proj / "大纲" / "总纲.md").exists()
        assert (proj / "大纲" / "爽点规划.md").exists()
        assert (proj / ".env.example").exists()

    def test_state_json_content(self, tmp_path, _mock_externals):
        proj = tmp_path / "proj"
        init_project(
            str(proj), "测试书", "修仙",
            protagonist_name="张三",
            golden_finger_name="鉴宝系统",
            golden_finger_type="系统流",
        )
        state = json.loads((proj / ".ink" / "state.json").read_text(encoding="utf-8"))
        assert state["project_info"]["title"] == "测试书"
        assert state["protagonist_state"]["name"] == "张三"
        assert state["protagonist_state"]["golden_finger"]["name"] == "鉴宝系统"


class TestInitProjectGoldenFingerNone:
    def test_golden_finger_type_wu(self, tmp_path, _mock_externals):
        proj = tmp_path / "proj"
        init_project(str(proj), "测试书", "修仙", golden_finger_type="无")
        state = json.loads((proj / ".ink" / "state.json").read_text(encoding="utf-8"))
        assert state["protagonist_state"]["golden_finger"]["name"] == "无金手指"
        assert state["protagonist_state"]["golden_finger"]["level"] == 0
        assert state["protagonist_state"]["golden_finger"]["cooldown"] == 0

    def test_golden_finger_type_none_english(self, tmp_path, _mock_externals):
        proj = tmp_path / "proj"
        init_project(str(proj), "测试书", "修仙", golden_finger_type="none")
        state = json.loads((proj / ".ink" / "state.json").read_text(encoding="utf-8"))
        assert state["protagonist_state"]["golden_finger"]["name"] == "无金手指"


class TestInitProjectExistingState:
    def test_existing_valid_state_preserved(self, tmp_path, _mock_externals):
        proj = tmp_path / "proj"
        ink_dir = proj / ".ink"
        ink_dir.mkdir(parents=True)
        existing = {"schema_version": 5, "project_info": {"created_at": "2025-01-01"}}
        (ink_dir / "state.json").write_text(json.dumps(existing), encoding="utf-8")
        init_project(str(proj), "测试书", "修仙")
        state = json.loads((ink_dir / "state.json").read_text(encoding="utf-8"))
        assert state["project_info"]["created_at"] == "2025-01-01"
        assert state["schema_version"] == 5

    def test_existing_corrupt_state_recovered(self, tmp_path, _mock_externals):
        proj = tmp_path / "proj"
        ink_dir = proj / ".ink"
        ink_dir.mkdir(parents=True)
        (ink_dir / "state.json").write_text("{invalid json", encoding="utf-8")
        init_project(str(proj), "测试书", "修仙")
        state = json.loads((ink_dir / "state.json").read_text(encoding="utf-8"))
        assert state["schema_version"] == 9

    def test_existing_preferences_corrupt_recovered(self, tmp_path, _mock_externals):
        proj = tmp_path / "proj"
        ink_dir = proj / ".ink"
        ink_dir.mkdir(parents=True)
        (ink_dir / "preferences.json").write_text("{bad", encoding="utf-8")
        init_project(str(proj), "测试书", "修仙")
        prefs = json.loads((ink_dir / "preferences.json").read_text(encoding="utf-8"))
        assert isinstance(prefs, dict)

    def test_existing_golden_three_plan_corrupt_recovered(self, tmp_path, _mock_externals):
        proj = tmp_path / "proj"
        ink_dir = proj / ".ink"
        ink_dir.mkdir(parents=True)
        (ink_dir / "golden_three_plan.json").write_text("{{", encoding="utf-8")
        init_project(str(proj), "测试书", "修仙")
        plan = json.loads((ink_dir / "golden_three_plan.json").read_text(encoding="utf-8"))
        assert isinstance(plan, dict)


class TestInitProjectGitInit:
    def test_git_init_when_available(self, tmp_path):
        proj = tmp_path / "proj"
        with (
            patch("init_project.write_current_project_pointer", return_value=None),
            patch("init_project.is_git_available", return_value=True),
            patch("init_project.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0)
            init_project(str(proj), "测试书", "修仙")
            # Should have called git init, git add, git commit
            assert mock_run.call_count == 3
            calls = [c[0][0] for c in mock_run.call_args_list]
            assert calls[0] == ["git", "init"]
            assert calls[1] == ["git", "add", "."]
            assert calls[2][0:2] == ["git", "commit"]

    def test_git_init_skipped_when_git_dir_exists(self, tmp_path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / ".git").mkdir()
        with (
            patch("init_project.write_current_project_pointer", return_value=None),
            patch("init_project.is_git_available", return_value=True),
            patch("init_project.subprocess.run") as mock_run,
        ):
            init_project(str(proj), "测试书", "修仙")
            mock_run.assert_not_called()

    def test_git_init_failure_non_fatal(self, tmp_path, capsys):
        proj = tmp_path / "proj"
        with (
            patch("init_project.write_current_project_pointer", return_value=None),
            patch("init_project.is_git_available", return_value=True),
            patch("init_project.subprocess.run", side_effect=__import__("subprocess").CalledProcessError(1, "git")),
        ):
            init_project(str(proj), "测试书", "修仙")
            captured = capsys.readouterr()
            assert "non-fatal" in captured.out

    def test_git_unavailable_message(self, tmp_path, capsys):
        proj = tmp_path / "proj"
        with (
            patch("init_project.write_current_project_pointer", return_value=None),
            patch("init_project.is_git_available", return_value=False),
        ):
            init_project(str(proj), "测试书", "修仙")
            captured = capsys.readouterr()
            assert "Git 不可用" in captured.out


class TestInitProjectPointer:
    def test_pointer_failure_non_fatal(self, tmp_path, capsys):
        proj = tmp_path / "proj"
        with (
            patch("init_project.write_current_project_pointer", side_effect=RuntimeError("boom")),
            patch("init_project.is_git_available", return_value=False),
        ):
            init_project(str(proj), "测试书", "修仙")
            captured = capsys.readouterr()
            assert "non-fatal" in captured.out

    def test_pointer_success_prints_path(self, tmp_path, capsys):
        proj = tmp_path / "proj"
        with (
            patch("init_project.write_current_project_pointer", return_value="/fake/pointer"),
            patch("init_project.is_git_available", return_value=False),
        ):
            init_project(str(proj), "测试书", "修仙")
            captured = capsys.readouterr()
            assert "pointer updated" in captured.out


def _mock_no_templates(original_fn):
    """Wrap _read_text_if_exists to return '' for any path under templates/output or templates/genres."""
    def wrapper(path):
        p = str(path)
        if "templates/output" in p or "templates/genres" in p or "golden-finger-templates" in p:
            return ""
        return original_fn(path)
    return wrapper


class TestInitProjectTemplatesFallback:
    """Test fallback content generation when template files don't exist."""

    def test_fallback_worldview_content(self, tmp_path, _mock_externals):
        proj = tmp_path / "proj"
        with patch("init_project._read_text_if_exists", side_effect=_mock_no_templates(_read_text_if_exists)):
            init_project(str(proj), "我的小说", "都市异能")
        content = (proj / "设定集" / "世界观.md").read_text(encoding="utf-8")
        assert "# 世界观" in content
        assert "我的小说" in content

    def test_fallback_power_system_content(self, tmp_path, _mock_externals):
        proj = tmp_path / "proj"
        with patch("init_project._read_text_if_exists", side_effect=_mock_no_templates(_read_text_if_exists)):
            init_project(str(proj), "我的小说", "修仙")
        content = (proj / "设定集" / "力量体系.md").read_text(encoding="utf-8")
        assert "# 力量体系" in content

    def test_fallback_protagonist_card(self, tmp_path, _mock_externals):
        proj = tmp_path / "proj"
        with patch("init_project._read_text_if_exists", side_effect=_mock_no_templates(_read_text_if_exists)):
            init_project(
                str(proj), "我的小说", "修仙",
                protagonist_name="李逍遥",
                protagonist_desire="长生",
                protagonist_flaw="优柔寡断",
            )
        content = (proj / "设定集" / "主角卡.md").read_text(encoding="utf-8")
        assert "李逍遥" in content
        assert "长生" in content
        assert "优柔寡断" in content

    def test_fallback_golden_finger_design(self, tmp_path, _mock_externals):
        proj = tmp_path / "proj"
        with patch("init_project._read_text_if_exists", side_effect=_mock_no_templates(_read_text_if_exists)):
            init_project(
                str(proj), "我的小说", "系统流",
                golden_finger_name="鉴宝面板",
                golden_finger_type="系统流",
            )
        content = (proj / "设定集" / "金手指设计.md").read_text(encoding="utf-8")
        assert "# 金手指设计" in content
        assert "鉴宝面板" in content

    def test_fallback_antagonist_design(self, tmp_path, _mock_externals):
        proj = tmp_path / "proj"
        with patch("init_project._read_text_if_exists", side_effect=_mock_no_templates(_read_text_if_exists)):
            init_project(str(proj), "我的小说", "修仙", antagonist_level="大宗师级")
        content = (proj / "设定集" / "反派设计.md").read_text(encoding="utf-8")
        assert "# 反派设计" in content
        assert "大宗师级" in content

    def test_fallback_outline_uses_build_master(self, tmp_path, _mock_externals):
        proj = tmp_path / "proj"
        with patch("init_project._read_text_if_exists", side_effect=_mock_no_templates(_read_text_if_exists)):
            init_project(str(proj), "我的小说", "修仙", target_chapters=120)
        content = (proj / "大纲" / "总纲.md").read_text(encoding="utf-8")
        assert "第1卷" in content
        assert "第3卷" in content

    def test_fallback_golden_finger_no_template_lib(self, tmp_path, _mock_externals):
        """Fallback golden finger content includes '未找到金手指模板库' when templates missing."""
        proj = tmp_path / "proj"
        with patch("init_project._read_text_if_exists", side_effect=_mock_no_templates(_read_text_if_exists)):
            init_project(str(proj), "我的小说", "修仙")
        content = (proj / "设定集" / "金手指设计.md").read_text(encoding="utf-8")
        assert "未找到金手指模板库" in content

    def test_unnamed_golden_finger_default(self, tmp_path, _mock_externals):
        """When no golden_finger_name and type is not '无', default to '未命名金手指'."""
        proj = tmp_path / "proj"
        init_project(str(proj), "测试书", "修仙")
        state = json.loads((proj / ".ink" / "state.json").read_text(encoding="utf-8"))
        assert state["protagonist_state"]["golden_finger"]["name"] == "未命名金手指"

    def test_golden_finger_name_set_directly(self, tmp_path, _mock_externals):
        """When golden_finger_name is set but type is not '无', name is used directly."""
        proj = tmp_path / "proj"
        init_project(str(proj), "测试书", "修仙", golden_finger_name="时空面板")
        state = json.loads((proj / ".ink" / "state.json").read_text(encoding="utf-8"))
        assert state["protagonist_state"]["golden_finger"]["name"] == "时空面板"


class TestInitProjectTeamContent:
    """Test co-protagonist team rows injection (lines 558-570)."""

    def test_team_rows_injected(self, tmp_path):
        """When team template exists and co_protagonists given, rows replace placeholder."""
        team_template = "# 主角组\n| 姓名 | 定位 | 备注 | 状态 | 弧线 |\n|---|---|---|---|---|\n| 主角A | | | | |\n| 主角B | | | | |"

        def mock_read(path):
            p = str(path)
            if "设定集-主角组" in p:
                return team_template
            if "templates/output" in p or "templates/genres" in p or "golden-finger-templates" in p:
                return ""
            return _read_text_if_exists(path)

        proj = tmp_path / "proj"
        with (
            patch("init_project.write_current_project_pointer", return_value=None),
            patch("init_project.is_git_available", return_value=False),
            patch("init_project._read_text_if_exists", side_effect=mock_read),
        ):
            init_project(
                str(proj), "测试书", "修仙",
                co_protagonists="张三,李四,王五",
                co_protagonist_roles="主线,副线",
            )
        content = (proj / "设定集" / "主角组.md").read_text(encoding="utf-8")
        assert "张三" in content
        assert "李四" in content
        assert "王五" in content
        assert "主角A" not in content


class TestInitProjectAntagonistTierMap:
    """Test antagonist tier map replacement (lines 645-661)."""

    def test_tier_map_replaces_rows(self, tmp_path):
        antagonist_template = (
            "# 反派设计\n"
            "| 层级 | 姓名 | 阶段 | 动机 | 结局 |\n"
            "|---|---|---|---|---|\n"
            "| 小反派 | | 前期 | | |\n"
            "| 中反派 | | 中期 | | |\n"
            "| 大反派 | | 后期 | | |"
        )

        def mock_read(path):
            p = str(path)
            if "设定集-反派设计" in p:
                return antagonist_template
            if "templates/output" in p or "templates/genres" in p or "golden-finger-templates" in p:
                return ""
            return _read_text_if_exists(path)

        proj = tmp_path / "proj"
        with (
            patch("init_project.write_current_project_pointer", return_value=None),
            patch("init_project.is_git_available", return_value=False),
            patch("init_project._read_text_if_exists", side_effect=mock_read),
        ):
            init_project(
                str(proj), "测试书", "修仙",
                antagonist_tiers="小反派:赵六;中反派:钱七;大反派:孙八",
            )
        content = (proj / "设定集" / "反派设计.md").read_text(encoding="utf-8")
        assert "赵六" in content
        assert "钱七" in content
        assert "孙八" in content


class TestInitProjectDuplicateGenreKey:
    """Test that duplicate genre keys after normalization are deduped (line 403)."""

    def test_dedup_genre_keys(self, tmp_path, _mock_externals):
        """'玄幻+修仙' both normalize to '修仙', should not produce duplicates."""
        proj = tmp_path / "proj"
        init_project(str(proj), "测试书", "玄幻+修仙")
        # Just verify it doesn't crash and state has the genre
        state = json.loads((proj / ".ink" / "state.json").read_text(encoding="utf-8"))
        assert state["project_info"]["genre"] == "玄幻+修仙"
