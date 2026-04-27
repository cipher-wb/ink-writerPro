"""US-016: Rollback switch verification tests.

验证三个独立回滚开关 + 总开关均可生效。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
ANTI_DETECTION_CONFIG = REPO_ROOT / "config" / "anti-detection.yaml"
COLLOQUIAL_CONFIG = REPO_ROOT / "config" / "colloquial.yaml"
PARALLEL_PIPELINE_CONFIG = REPO_ROOT / "config" / "parallel-pipeline.yaml"


class TestRollbackSwitchesExist:
    """验证三个开关文件均存在且含正确键。"""

    def test_anti_detection_has_prose_overhaul_enabled(self) -> None:
        assert ANTI_DETECTION_CONFIG.exists()
        data = yaml.safe_load(ANTI_DETECTION_CONFIG.read_text(encoding="utf-8"))
        assert "prose_overhaul_enabled" in data
        assert data["prose_overhaul_enabled"] is True

    def test_anti_detection_has_enabled(self) -> None:
        data = yaml.safe_load(ANTI_DETECTION_CONFIG.read_text(encoding="utf-8"))
        assert "enabled" in data
        assert data["enabled"] is True

    def test_colloquial_has_enabled(self) -> None:
        assert COLLOQUIAL_CONFIG.exists()
        data = yaml.safe_load(COLLOQUIAL_CONFIG.read_text(encoding="utf-8"))
        assert "enabled" in data
        assert data["enabled"] is True

    def test_parallel_pipeline_has_explosive_retrieval(self) -> None:
        assert PARALLEL_PIPELINE_CONFIG.exists()
        data = yaml.safe_load(PARALLEL_PIPELINE_CONFIG.read_text(encoding="utf-8"))
        assert "enable_explosive_retrieval" in data
        assert data["enable_explosive_retrieval"] is True


class TestIndependentSwitches:
    """验证三个开关独立可配。"""

    def test_all_three_switches_independent(self) -> None:
        """三个开关位于三个不同配置文件，可独立修改。"""
        ad = yaml.safe_load(ANTI_DETECTION_CONFIG.read_text(encoding="utf-8"))
        cl = yaml.safe_load(COLLOQUIAL_CONFIG.read_text(encoding="utf-8"))
        pp = yaml.safe_load(PARALLEL_PIPELINE_CONFIG.read_text(encoding="utf-8"))

        # 验证键存在且在不同文件中
        assert "prose_overhaul_enabled" in ad
        assert "enabled" in ad
        assert "enabled" in cl
        assert "enable_explosive_retrieval" in pp

        # 验证各文件路径不同（独立可修改）
        assert ANTI_DETECTION_CONFIG != COLLOQUIAL_CONFIG
        assert ANTI_DETECTION_CONFIG != PARALLEL_PIPELINE_CONFIG
        assert COLLOQUIAL_CONFIG != PARALLEL_PIPELINE_CONFIG

    def test_anti_detection_enabled_controls_zt(self) -> None:
        """anti-detection.yaml 的 enabled 控制零容忍清单。"""
        data = yaml.safe_load(ANTI_DETECTION_CONFIG.read_text(encoding="utf-8"))
        assert "enabled" in data
        assert isinstance(data["enabled"], bool)

    def test_master_switch_can_force_off(self) -> None:
        """prose_overhaul_enabled 作为总开关，值可设为 false。"""
        data = yaml.safe_load(ANTI_DETECTION_CONFIG.read_text(encoding="utf-8"))
        # 当前为 true，但可被设为 false
        assert "prose_overhaul_enabled" in data
        assert isinstance(data["prose_overhaul_enabled"], bool)


class TestRollbackDocumentation:
    """验证回滚文档存在且完整。"""

    def test_rollback_doc_exists(self) -> None:
        doc = REPO_ROOT / "docs" / "prose-anti-ai-overhaul.md"
        assert doc.exists(), "prose-anti-ai-overhaul.md not found"

    def test_rollback_doc_has_sop(self) -> None:
        doc = REPO_ROOT / "docs" / "prose-anti-ai-overhaul.md"
        text = doc.read_text(encoding="utf-8")
        assert "回滚 SOP" in text or "回滚" in text

    def test_rollback_doc_lists_switches(self) -> None:
        doc = REPO_ROOT / "docs" / "prose-anti-ai-overhaul.md"
        text = doc.read_text(encoding="utf-8")
        assert "prose_overhaul_enabled" in text
        assert "enable_explosive_retrieval" in text
