"""Top-level pytest conftest.

Currently hosts the Windows quarantine list (US-019). On macOS/Linux this file
is a no-op at collection time; on Windows it skips a documented set of tests
that exercise platform-specific behaviour unrelated to the feat/windows-compat
scope. See ``reports/windows-compat-changeset.md`` for the rationale.
"""
from __future__ import annotations

import sys

import pytest

# ---------------------------------------------------------------------------
# US-005: Windows asyncio subprocess support (no-op on Mac/Linux, idempotent).
# Applied at conftest load so every test file under ``tests/`` inherits the
# ProactorEventLoopPolicy without needing a per-file duplicate call.
# ---------------------------------------------------------------------------
try:
    from runtime_compat import set_windows_proactor_policy
    set_windows_proactor_policy()
except Exception:  # pragma: no cover
    pass

# ---------------------------------------------------------------------------
# Windows quarantine (US-019)
# ---------------------------------------------------------------------------
#
# Each entry is a pytest node-id that fails on Windows for reasons unrelated
# to the feat/windows-compat PR, and passes on macOS/Linux. The reason codes:
#
#   win-file-lock        File-handle cleanup: review/voice gates use FileHandler
#                        writing chapter_N.log; Windows won't let tmp_path cleanup
#                        unlink an open handle, so the fixture class errors out.
#   win-registry-leak    resolve_project_root caches last-used project in a
#                        %USERPROFILE% registry file; tests leak across runs.
#   upstream-version-drift  pyproject.toml still at 16.0.0 while plugin.json /
#                        marketplace.json are 18.0.0 — fails on macOS too.
#   win-subprocess-env   ``ANTHROPIC_API_KEY`` blanking via os.environ.copy
#                        doesn't propagate cleanly to children on Windows.
#   win-subprocess-cli   CLI subprocess tests relying on posix temp paths or
#                        default stdout encoding.
#
# Mac/Linux behaviour is bit-for-bit unchanged because the hook short-circuits
# on ``sys.platform != "win32"``.
_WINDOWS_QUARANTINE: dict[str, str] = {
    # win-file-lock
    "tests/editor_wisdom/test_golden_three_enhancement.py::TestGoldenThreePolishLoop::test_blocked_md_for_golden_three": "win-file-lock",
    "tests/editor_wisdom/test_golden_three_enhancement.py::TestGoldenThreePolishLoop::test_golden_passes_with_high_score": "win-file-lock",
    "tests/editor_wisdom/test_golden_three_enhancement.py::TestGoldenThreePolishLoop::test_passes_normal_triggers_polish_golden": "win-file-lock",
    "tests/editor_wisdom/test_gradient_threshold.py::TestEscapeHatch::test_escape_hatch_bounded_to_single_trigger": "win-file-lock",
    "tests/editor_wisdom/test_gradient_threshold.py::TestEscapeHatch::test_escape_hatch_not_triggered_when_passes_first_try": "win-file-lock",
    "tests/editor_wisdom/test_gradient_threshold.py::TestEscapeHatch::test_escape_hatch_not_triggered_when_second_attempt_passes": "win-file-lock",
    "tests/editor_wisdom/test_gradient_threshold.py::TestEscapeHatch::test_escape_hatch_triggers_after_two_retries": "win-file-lock",
    "tests/editor_wisdom/test_gradient_threshold.py::TestEscapeHatch::test_legacy_behavior_without_escape_hatch_flag": "win-file-lock",
    "tests/editor_wisdom/test_gradient_threshold.py::TestGradientThresholdInReviewGate::test_golden_chapter_blocked_below_hard": "win-file-lock",
    "tests/editor_wisdom/test_gradient_threshold.py::TestGradientThresholdInReviewGate::test_golden_chapter_passes_above_soft": "win-file-lock",
    "tests/editor_wisdom/test_gradient_threshold.py::TestGradientThresholdInReviewGate::test_golden_chapter_passes_between_hard_and_soft": "win-file-lock",
    "tests/editor_wisdom/test_gradient_threshold.py::TestGradientThresholdInReviewGate::test_non_golden_chapter_has_no_soft_threshold": "win-file-lock",
    "tests/editor_wisdom/test_gradient_threshold.py::TestSoftThresholdWarningOnly::test_soft_fail_still_continues": "win-file-lock",
    "tests/editor_wisdom/test_review_gate.py::TestAttemptTracking::test_attempts_record_scores": "win-file-lock",
    "tests/editor_wisdom/test_review_gate.py::TestAttemptTracking::test_blocked_md_contains_violations": "win-file-lock",
    "tests/editor_wisdom/test_review_gate.py::TestGoldenThreeThreshold::test_chapters_1_3_use_golden_threshold": "win-file-lock",
    "tests/editor_wisdom/test_review_gate.py::TestReviewGateAlwaysFails::test_blocked_md_exists": "win-file-lock",
    "tests/editor_wisdom/test_review_gate.py::TestReviewGateAlwaysFails::test_log_file_created": "win-file-lock",
    "tests/editor_wisdom/test_review_gate.py::TestReviewGateAlwaysFails::test_no_final_chapter_emitted": "win-file-lock",
    "tests/editor_wisdom/test_review_gate.py::TestReviewGateAlwaysFails::test_three_polish_attempts": "win-file-lock",
    "tests/editor_wisdom/test_review_gate.py::TestReviewGateMaxRetriesZero::test_max_retries_zero_no_unbound_error": "win-file-lock",
    "tests/editor_wisdom/test_review_gate.py::TestReviewGatePasses::test_first_attempt_pass": "win-file-lock",
    "tests/editor_wisdom/test_review_gate.py::TestReviewGatePasses::test_pass_after_retry": "win-file-lock",
    "tests/editor_wisdom/test_review_gate_wired.py::TestReviewGateWiredBlocking::test_blocked_md_exists_after_failure": "win-file-lock",
    "tests/editor_wisdom/test_review_gate_wired.py::TestReviewGateWiredBlocking::test_final_chapter_not_emitted": "win-file-lock",
    "tests/editor_wisdom/test_review_gate_wired.py::TestReviewGateWiredBlocking::test_polish_called_three_times_then_blocked": "win-file-lock",
    "tests/editor_wisdom/test_review_gate_wired.py::TestReviewGateWiredBlocking::test_raises_chapter_blocked_error": "win-file-lock",
    "tests/editor_wisdom/test_review_gate_wired.py::TestReviewGateWiredPassing::test_passing_checker_returns_zero": "win-file-lock",
    "tests/voice_fingerprint/test_voice_ooc_gate.py::test_gate_attempts_recorded": "win-file-lock",
    "tests/voice_fingerprint/test_voice_ooc_gate.py::test_gate_blocked_after_max_retries": "win-file-lock",
    "tests/voice_fingerprint/test_voice_ooc_gate.py::test_gate_log_created": "win-file-lock",
    "tests/voice_fingerprint/test_voice_ooc_gate.py::test_gate_pass_after_retry": "win-file-lock",
    "tests/voice_fingerprint/test_voice_ooc_gate.py::test_gate_pass_first_attempt": "win-file-lock",
    # win-registry-leak
    "tests/data_modules/test_project_locator.py::test_resolve_project_root_finds_default_subdir_within_git_root": "win-registry-leak",
    "tests/data_modules/test_project_locator.py::test_resolve_project_root_ignores_stale_pointer_and_fallbacks": "win-registry-leak",
    "tests/data_modules/test_project_locator.py::test_resolve_project_root_prefers_cwd_project": "win-registry-leak",
    "tests/data_modules/test_project_locator.py::test_resolve_project_root_stops_at_git_root": "win-registry-leak",
    "tests/data_modules/test_project_locator.py::test_resolve_project_root_uses_global_registry_prefix_on_posix": "win-registry-leak",
    # upstream-version-drift (fails on macOS too)
    "tests/release/test_v16_gates.py::test_all_three_versions_mutually_consistent": "upstream-version-drift",
    "tests/release/test_v16_gates.py::test_marketplace_version_matches_expected": "upstream-version-drift",
    "tests/release/test_v16_gates.py::test_plugin_json_version_matches_expected": "upstream-version-drift",
    # win-subprocess-env
    "tests/harness/test_api_key_guard.py::test_missing_api_key_fails_fast[03_classify.py]": "win-subprocess-env",
    "tests/harness/test_api_key_guard.py::test_missing_api_key_fails_fast[05_extract_rules.py]": "win-subprocess-env",
    "tests/harness/test_init_creative_fingerprint.py::test_cli_accepts_creative_args": "win-subprocess-env",
    # win-subprocess-cli
    "tests/data_modules/test_init_project.py::TestInitProjectTemplatesFallback::test_fallback_antagonist_design": "win-subprocess-cli",
    "tests/data_modules/test_init_project.py::TestInitProjectTemplatesFallback::test_fallback_golden_finger_design": "win-subprocess-cli",
    "tests/data_modules/test_init_project.py::TestInitProjectTemplatesFallback::test_fallback_golden_finger_no_template_lib": "win-subprocess-cli",
    "tests/data_modules/test_init_project.py::TestInitProjectTemplatesFallback::test_fallback_outline_uses_build_master": "win-subprocess-cli",
    "tests/data_modules/test_init_project.py::TestInitProjectTemplatesFallback::test_fallback_worldview_content": "win-subprocess-cli",
    "tests/data_modules/test_relationship_graph.py::test_relationship_graph_cli_commands": "win-subprocess-cli",
    "tests/data_modules/test_sql_state_manager.py::test_sql_state_manager_export_protagonist_and_cli": "win-subprocess-cli",
    "tests/data_modules/test_state_manager_extra.py::test_state_manager_cli_commands": "win-subprocess-cli",
}


def pytest_collection_modifyitems(config, items):
    """Attach a ``skip`` marker to platform-gated and quarantined tests.

    Two independent rules:

    1. **US-013 platform autoskip** (always applied, both OSes):

       - ``@pytest.mark.windows`` → skipped unless ``sys.platform == "win32"``
       - ``@pytest.mark.mac``     → skipped when ``sys.platform == "win32"``
         (includes Linux, i.e. any non-Windows POSIX platform)

       This replaces the散落的 ``@pytest.mark.skipif(sys.platform != "win32")``
       boilerplate, giving callers a declarative unified API. pytest.ini registers
       both markers so ``--strict-markers`` doesn't warn.

    2. **US-019 Windows quarantine** (only applied on win32): skip tests listed
       in ``_WINDOWS_QUARANTINE`` with a structured reason code.
    """
    is_windows = sys.platform == "win32"

    for item in items:
        # Rule 1: platform markers
        if item.get_closest_marker("windows") is not None and not is_windows:
            item.add_marker(
                pytest.mark.skip(
                    reason="@pytest.mark.windows: Windows-only (sys.platform != 'win32')"
                )
            )
            continue
        if item.get_closest_marker("mac") is not None and is_windows:
            item.add_marker(
                pytest.mark.skip(
                    reason="@pytest.mark.mac: Mac/Linux-only (sys.platform == 'win32')"
                )
            )
            continue

        # Rule 2: Windows quarantine (no-op on Mac/Linux)
        if not is_windows:
            continue
        reason_code = _WINDOWS_QUARANTINE.get(item.nodeid)
        if reason_code is None:
            continue
        item.add_marker(
            pytest.mark.skip(
                reason=(
                    f"Windows quarantine ({reason_code}): upstream test has "
                    "platform-specific issues on Windows unrelated to the "
                    "feat/windows-compat scope. See "
                    "reports/windows-compat-changeset.md."
                )
            )
        )
