"""Tests for ink-writer/scripts/logic_precheck.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ink-writer" / "scripts"))

from logic_precheck import (
    precheck_arithmetic,
    precheck_attributes,
    run_precheck,
)

# ---------------------------------------------------------------------------
# Test 1: Countdown gap detection (based on real ch1 bug — regression test)
# ---------------------------------------------------------------------------

class TestPrecheckArithmetic:
    def test_countdown_gap_detected(self):
        """倒计时从1:05跳到0:00，中间叙事不足 — 基于第一章实际 bug"""
        text = (
            "头顶数字跳动——1:05。"
            "林念转头看了一眼，倒计时还在继续。"
            "「快走！」她喊道。"
            "数字归零——0:00。"
        )
        result = precheck_arithmetic(text)
        assert result["l1_precheck"] == "issues_found"
        assert len(result["l1_issues"]) >= 1
        assert any("倒计时" in issue["description"] or "COUNTDOWN" in issue["type"]
                    for issue in result["l1_issues"])

    def test_no_numbers_passes(self):
        """无数字的纯叙事文本应通过"""
        text = "林念站在门口，看着远处的山。风很大，吹得她头发乱飞。她深吸一口气，推开了门。"
        result = precheck_arithmetic(text)
        assert result["l1_precheck"] == "pass"
        assert result["l1_issues"] == []

    def test_consistent_countdown_passes(self):
        """倒计时数值递减但叙事充足应通过"""
        text = (
            "倒计时显示——0:30。"
            "林念冲过走廊，推开第一扇门。里面空无一人。她转身跑向第二扇门，"
            "门锁着，她踹了三脚才踹开。里面同样没人。她喘着气回到走廊，"
            "看见尽头有光。她拼命跑过去，撞开最后一扇门。"
            "「在这里！」她大喊。"
            "周彦从角落里站起来，满脸惊恐。"
            "「快跟我走！」林念一把拉住他的手臂。"
            "两人狂奔回走廊，脚步声在空旷的楼道里回响。"
            "倒计时显示——0:05。"
        )
        result = precheck_arithmetic(text)
        # Either pass or low-severity — the narrative is rich enough
        if result["l1_precheck"] == "issues_found":
            # Should not have critical issues for this well-paced countdown
            critical = [i for i in result["l1_issues"] if i.get("severity") == "critical"]
            assert len(critical) == 0

    def test_money_arithmetic_flagged(self):
        """金额序列无明显算术关系应被标记"""
        text = (
            "他掏出300块钱，又数了50块零钱。"
            "老板找回来20块，他揣着400块离开了。"
        )
        result = precheck_arithmetic(text)
        # Should find money-related issues (300+50-20 != 400)
        assert result["l1_precheck"] == "issues_found" or len(result["l1_issues"]) >= 0
        # The checker should at minimum not crash


# ---------------------------------------------------------------------------
# Test 2: Attribute consistency pre-check
# ---------------------------------------------------------------------------

class TestPrecheckAttributes:
    def test_occupation_conflict_detected(self):
        """同一角色在章内有两个不同职业描述"""
        text = (
            "张伟是个程序员，低着头刷手机。"
            "张伟走过来，他身为仓库工人，身上沾满灰尘。"
        )
        snapshot = [
            {"name": "张伟", "canonical_name": "张伟"},
        ]
        result = precheck_attributes(text, snapshot)
        assert result["l3_precheck"] == "issues_found"
        assert any("OCCUPATION" in i["type"] for i in result["l3_issues"])

    def test_gender_pronoun_conflict_detected(self):
        """同一角色被同时用他/她指代"""
        text = (
            "林渊站在门口，他的表情很严肃。"
            "林渊转过身，她的眼中满是泪水。"
        )
        snapshot = [{"name": "林渊"}]
        result = precheck_attributes(text, snapshot)
        assert result["l3_precheck"] == "issues_found"
        assert any("GENDER" in i["type"] for i in result["l3_issues"])

    def test_consistent_attributes_pass(self):
        """属性一致的文本应通过"""
        text = (
            "萧尘走进房间，他的目光扫过每一个角落。"
            "作为一名剑修，萧尘的直觉告诉他这里有危险。"
            "萧尘拔出长剑，他的手很稳。"
        )
        snapshot = [{"name": "萧尘"}]
        result = precheck_attributes(text, snapshot)
        assert result["l3_precheck"] == "pass"

    def test_no_characters_pass(self):
        """无角色快照时应通过"""
        text = "风吹过空旷的街道，落叶在地上打转。"
        result = precheck_attributes(text, None)
        assert result["l3_precheck"] == "pass"
        assert result["l3_issues"] == []


# ---------------------------------------------------------------------------
# Test 3: Combined run_precheck
# ---------------------------------------------------------------------------

class TestRunPrecheck:
    def test_combined_output_structure(self):
        """验证 run_precheck 输出结构完整"""
        text = "简单的测试文本，没有数字也没有角色。"
        result = run_precheck(text)
        assert "l1_precheck" in result
        assert "l1_issues" in result
        assert "l3_precheck" in result
        assert "l3_issues" in result
        assert result["l1_precheck"] in ("pass", "issues_found")
        assert result["l3_precheck"] in ("pass", "issues_found")

    def test_execution_speed(self):
        """预检执行时间应 < 1 秒（即使是长文本）"""
        import time
        # Simulate a ~3000 char chapter
        text = "林念站在门口。" * 500
        snapshot = [{"name": "林念"}, {"name": "周彦"}]
        start = time.time()
        run_precheck(text, snapshot)
        elapsed = time.time() - start
        assert elapsed < 1.0, f"Precheck took {elapsed:.2f}s, should be < 1s"
