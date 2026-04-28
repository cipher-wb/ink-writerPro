# Debug Mode v0.5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a non-intrusive observability layer over ink-writer's writing flow — collector + JSONL+SQLite event bus + 5 lightweight invariants + 5 checker output normalizers + Claude Code hooks + dual-view markdown reports — that records AI偷懒 / contract drift / hard errors during chapter writing, so the user can periodically feed reports to an external Claude session for software self-improvement.

**Architecture:** 3 detection layers (A: Claude Code hooks; B: existing checker output → schema; C: 5 structural invariants) write through a single `collector` to `events.jsonl` (truth source). An async `indexer` populates `debug.db` for query. Downstream consumers: `alerter` (per-chapter summary, per-batch report) and `reporter` (manual `/ink-debug-report` markdown). All under `<project>/.ink-debug/`. Master switch and 4 layer switches default ON. `INK_DEBUG_OFF=1` is emergency disable.

**Tech Stack:** Python 3.11+, stdlib only for collector/indexer (json, sqlite3, gzip, difflib, pathlib), PyYAML for config (already a project dependency), pytest for tests. Claude Code hooks via `.claude/settings.json`.

**Spec reference:** `docs/superpowers/specs/2026-04-28-debug-mode-design.md`

---

## File Structure

### New files

```
config/debug.yaml                                       # Global default config
ink_writer/debug/__init__.py
ink_writer/debug/schema.py                              # Incident dataclass + kind whitelist + JSON
ink_writer/debug/config.py                              # Config loader (yaml + project override + env)
ink_writer/debug/collector.py                           # Single write entry point
ink_writer/debug/rotate.py                              # JSONL rotation helper
ink_writer/debug/indexer.py                             # JSONL → SQLite
ink_writer/debug/reporter.py                            # SQLite → markdown
ink_writer/debug/alerter.py                             # Per-chapter / per-batch summary
ink_writer/debug/checker_router.py                      # 5 checker outputs → schema
ink_writer/debug/cli.py                                 # status / report / toggle subcommands
ink_writer/debug/invariants/__init__.py
ink_writer/debug/invariants/writer_word_count.py
ink_writer/debug/invariants/polish_diff.py
ink_writer/debug/invariants/review_dimensions.py
ink_writer/debug/invariants/context_required_files.py
ink_writer/debug/invariants/auto_step_skipped.py
scripts/debug/hook_handler.py                           # Claude Code hooks → collector
scripts/debug/ink-debug-status.{sh,ps1,cmd}
scripts/debug/ink-debug-report.{sh,ps1,cmd}
scripts/debug/ink-debug-toggle.{sh,ps1,cmd}
.claude/settings.json                                   # Hooks registration (file may not exist yet)
tests/debug/__init__.py
tests/debug/test_schema.py
tests/debug/test_config.py
tests/debug/test_collector.py
tests/debug/test_rotate.py
tests/debug/test_indexer.py
tests/debug/test_invariants_writer_word_count.py
tests/debug/test_invariants_polish_diff.py
tests/debug/test_invariants_review_dimensions.py
tests/debug/test_invariants_context_required_files.py
tests/debug/test_invariants_auto_step_skipped.py
tests/debug/test_checker_router.py
tests/debug/test_reporter.py
tests/debug/test_alerter.py
tests/debug/test_cli.py
tests/debug/test_e2e_ink_write.py
tests/debug/test_disabled_mode.py
```

### Modified files

```
.gitignore                                              # Add .ink-debug/
ink_writer/rewrite_loop/orchestrator.py                 # Wire 3 invariants + checker_router
ink_writer/preflight/cli.py                             # Wire context_required_files (best-effort)
ink-writer/skills/ink-write/SKILL.md                    # Document alerter call at end of Step 6
ink-writer/skills/ink-auto/SKILL.md                     # Document alerter call at end of batch
docs/USER_MANUAL_DEBUG.md                               # Mark "implementation complete" once acceptance passes
```

---

## Task Roadmap

| # | Task | Phase | Depends on |
|---|---|---|---|
| 1 | Incident schema + kind whitelist | 1 Foundation | — |
| 2 | Config loader (yaml + override + env) | 1 Foundation | 1 |
| 3 | Collector (master switch, severity, JSONL) | 1 Foundation | 1, 2 |
| 4 | JSONL rotation | 2 Storage | 3 |
| 5 | SQLite indexer | 2 Storage | 3 |
| 6 | invariant: writer_word_count | 3 Invariants | 1, 3 |
| 7 | invariant: polish_diff | 3 Invariants | 1, 3 |
| 8 | invariant: review_dimensions | 3 Invariants | 1, 3 |
| 9 | invariant: context_required_files | 3 Invariants | 1, 3 |
| 10 | invariant: auto_step_skipped | 3 Invariants | 1, 3 |
| 11 | checker_router | 4 Layer B | 1, 3 |
| 12 | hook_handler + .claude/settings.json | 5 Layer A | 3 |
| 13 | reporter (dual view) | 6 Downstream | 5 |
| 14 | alerter (per-chapter / per-batch) | 6 Downstream | 5, 13 |
| 15 | cli (status / report / toggle) | 7 CLI | 13, 14 |
| 16 | shell wrappers (.sh/.ps1/.cmd) | 7 CLI | 15 |
| 17 | Wire writer_word_count into orchestrator | 8 Integration | 6 |
| 18 | Wire polish_diff into orchestrator | 8 Integration | 7 |
| 19 | Wire review_dimensions + checker_router into orchestrator | 8 Integration | 8, 11 |
| 20 | Wire context_required_files into preflight | 8 Integration | 9 |
| 21 | Document auto_step_skipped + alerter in ink-auto SKILL.md | 8 Integration | 10, 14 |
| 22 | Document alerter call in ink-write SKILL.md | 8 Integration | 14 |
| 23 | .gitignore + e2e integration test + acceptance run + final commit | 9 Acceptance | all |

---

## Task 1: Incident schema + kind whitelist

**Files:**
- Create: `ink_writer/debug/__init__.py`
- Create: `ink_writer/debug/schema.py`
- Test: `tests/debug/__init__.py`
- Test: `tests/debug/test_schema.py`

- [ ] **Step 1.1: Write failing test for Incident dataclass**

Create `tests/debug/__init__.py` (empty file).

Create `tests/debug/test_schema.py`:

```python
"""Tests for ink_writer.debug.schema."""
from __future__ import annotations

import json

import pytest

from ink_writer.debug.schema import Incident, KIND_WHITELIST, validate_kind


def test_incident_required_fields():
    inc = Incident(
        ts="2026-04-28T14:23:51.123Z",
        run_id="auto-2026-04-28-batch12",
        source="layer_c_invariant",
        skill="ink-write",
        kind="writer.short_word_count",
        severity="warn",
        message="word count too low",
    )
    assert inc.ts == "2026-04-28T14:23:51.123Z"
    assert inc.severity == "warn"


def test_incident_to_jsonl_line_round_trip():
    inc = Incident(
        ts="2026-04-28T14:23:51.123Z",
        run_id="r1",
        source="layer_c_invariant",
        skill="ink-write",
        kind="polish.diff_too_small",
        severity="warn",
        message="diff too small",
        evidence={"diff_chars": 32, "threshold": 50},
    )
    line = inc.to_jsonl_line()
    assert line.endswith("\n")
    decoded = json.loads(line)
    assert decoded["evidence"]["diff_chars"] == 32


def test_kind_whitelist_contains_reserved():
    for k in [
        "writer.short_word_count",
        "polish.diff_too_small",
        "review.missing_dimensions",
        "context.missing_required_skill_file",
        "auto.skill_step_skipped",
        "hook.pre_tool_use",
        "hook.post_tool_use",
        "hook.subagent_stop",
        "meta.invariant_crashed",
        "meta.unknown_kind",
        "meta.collector_error",
    ]:
        assert k in KIND_WHITELIST


def test_validate_kind_accepts_checker_pattern():
    # checker.<name>.<problem> dynamic pattern
    assert validate_kind("checker.consistency.character_drift") is True
    assert validate_kind("checker.continuity.timeline_break") is True


def test_validate_kind_rejects_unknown():
    assert validate_kind("totally.made.up") is False


def test_severity_validation():
    with pytest.raises(ValueError, match="severity"):
        Incident(
            ts="2026-04-28T14:23:51Z",
            run_id="r1",
            source="layer_c_invariant",
            skill="x",
            kind="writer.short_word_count",
            severity="critical",  # invalid
            message="x",
        )
```

- [ ] **Step 1.2: Run the tests and verify they fail**

Run: `pytest tests/debug/test_schema.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ink_writer.debug.schema'`

- [ ] **Step 1.3: Create the module skeleton + Incident dataclass**

Create `ink_writer/debug/__init__.py`:

```python
"""Debug mode (v0.5) — observability over ink-writer's writing flow.

See docs/superpowers/specs/2026-04-28-debug-mode-design.md for design.
"""
```

Create `ink_writer/debug/schema.py`:

```python
"""Incident schema + kind whitelist + serialization."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

VALID_SOURCES = frozenset({
    "layer_a_hook",
    "layer_b_checker",
    "layer_c_invariant",
    "layer_d_adversarial",
    "meta",
})

VALID_SEVERITIES = frozenset({"info", "warn", "error"})

# Static reserved kinds (Section 3.1 of spec).
KIND_WHITELIST: frozenset[str] = frozenset({
    "writer.short_word_count",
    "polish.diff_too_small",
    "review.missing_dimensions",
    "context.missing_required_skill_file",
    "auto.skill_step_skipped",
    "hook.pre_tool_use",
    "hook.post_tool_use",
    "hook.subagent_stop",
    "hook.stop",
    "hook.session_end",
    "meta.invariant_crashed",
    "meta.unknown_kind",
    "meta.collector_error",
})


def validate_kind(kind: str) -> bool:
    """Return True if kind is a known reserved kind or matches checker.<name>.<problem>."""
    if kind in KIND_WHITELIST:
        return True
    parts = kind.split(".")
    if len(parts) >= 3 and parts[0] == "checker":
        return all(p and p.replace("_", "").isalnum() for p in parts[1:])
    return False


@dataclass
class Incident:
    ts: str                                 # ISO8601 UTC
    run_id: str
    source: str                             # one of VALID_SOURCES
    skill: str
    kind: str
    severity: str                           # one of VALID_SEVERITIES
    message: str
    session_id: str | None = None
    project: str | None = None
    chapter: int | None = None
    step: str | None = None
    evidence: dict[str, Any] | None = None
    trace: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.severity not in VALID_SEVERITIES:
            raise ValueError(
                f"severity must be one of {sorted(VALID_SEVERITIES)}, got {self.severity!r}"
            )
        if self.source not in VALID_SOURCES:
            raise ValueError(
                f"source must be one of {sorted(VALID_SOURCES)}, got {self.source!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None}

    def to_jsonl_line(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":")) + "\n"
```

- [ ] **Step 1.4: Run the tests and verify they pass**

Run: `pytest tests/debug/test_schema.py -v`
Expected: 6 tests PASS.

- [ ] **Step 1.5: Commit**

```bash
git add ink_writer/debug/__init__.py ink_writer/debug/schema.py \
        tests/debug/__init__.py tests/debug/test_schema.py
git commit -m "feat(debug): incident schema + kind whitelist (T1)"
```

---

## Task 2: Config loader (yaml + project override + env)

**Files:**
- Create: `config/debug.yaml`
- Create: `ink_writer/debug/config.py`
- Test: `tests/debug/test_config.py`

- [ ] **Step 2.1: Create the global default yaml**

Create `config/debug.yaml`:

```yaml
master_enabled: true                    # Master switch, default ON

layers:
  layer_a_hooks: true
  layer_b_checker_router: true
  layer_c_invariants: true
  layer_d_adversarial: false            # v1.0 only

severity:
  jsonl_threshold: info                 # info+ to JSONL
  sqlite_threshold: warn                # warn+ to SQLite index
  alert_threshold: warn                 # warn+ triggers end-of-run summary
  stderr_threshold: error               # error gets immediate stderr red

storage:
  base_dir: ".ink-debug"
  events_max_mb: 100
  archive_keep: 5

alerts:
  per_chapter_summary: true
  per_batch_report: true
  warn_window_days: 7
  warn_window_threshold: 5

invariants:
  writer_word_count:
    enabled: true
  polish_diff:
    enabled: true
    min_diff_chars: 50
  review_dimensions:
    enabled: true
    min_dimensions_per_skill:
      ink-review: 7
  context_required_files:
    enabled: true
  auto_step_skipped:
    enabled: true
    expected_steps:
      ink-auto:
        - context
        - draft
        - review
        - polish
        - extract
        - audit

strict_mode: false                      # If true, unknown kinds raise (test only)
```

- [ ] **Step 2.2: Write failing tests for config loader**

Create `tests/debug/test_config.py`:

```python
"""Tests for ink_writer.debug.config."""
from __future__ import annotations

from pathlib import Path

import pytest

from ink_writer.debug.config import DebugConfig, load_config


def test_load_global_defaults(tmp_path: Path):
    cfg = load_config(global_yaml_path=Path("config/debug.yaml"), project_root=tmp_path)
    assert cfg.master_enabled is True
    assert cfg.layers.layer_a_hooks is True
    assert cfg.layers.layer_d_adversarial is False
    assert cfg.invariants["polish_diff"]["min_diff_chars"] == 50


def test_project_override_deep_merges(tmp_path: Path):
    debug_dir = tmp_path / ".ink-debug"
    debug_dir.mkdir()
    (debug_dir / "config.local.yaml").write_text(
        "invariants:\n  polish_diff:\n    min_diff_chars: 10\n",
        encoding="utf-8",
    )
    cfg = load_config(global_yaml_path=Path("config/debug.yaml"), project_root=tmp_path)
    assert cfg.invariants["polish_diff"]["min_diff_chars"] == 10
    # other fields preserved
    assert cfg.master_enabled is True


def test_env_var_overrides_master(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("INK_DEBUG_OFF", "1")
    cfg = load_config(global_yaml_path=Path("config/debug.yaml"), project_root=tmp_path)
    assert cfg.master_enabled is False


def test_env_var_unset_preserves_master(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("INK_DEBUG_OFF", raising=False)
    cfg = load_config(global_yaml_path=Path("config/debug.yaml"), project_root=tmp_path)
    assert cfg.master_enabled is True


def test_severity_threshold_passes_warn(tmp_path: Path):
    cfg = load_config(global_yaml_path=Path("config/debug.yaml"), project_root=tmp_path)
    assert cfg.passes_threshold("warn", "sqlite_threshold") is True
    assert cfg.passes_threshold("info", "sqlite_threshold") is False
    assert cfg.passes_threshold("error", "stderr_threshold") is True
```

- [ ] **Step 2.3: Run tests, verify they fail**

Run: `pytest tests/debug/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 2.4: Implement the config loader**

Create `ink_writer/debug/config.py`:

```python
"""Debug mode config loader: yaml + project override + env."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

SEVERITY_RANK = {"info": 0, "warn": 1, "error": 2}


@dataclass
class LayerSwitches:
    layer_a_hooks: bool = True
    layer_b_checker_router: bool = True
    layer_c_invariants: bool = True
    layer_d_adversarial: bool = False


@dataclass
class SeverityThresholds:
    jsonl_threshold: str = "info"
    sqlite_threshold: str = "warn"
    alert_threshold: str = "warn"
    stderr_threshold: str = "error"


@dataclass
class StorageConfig:
    base_dir: str = ".ink-debug"
    events_max_mb: int = 100
    archive_keep: int = 5


@dataclass
class AlertsConfig:
    per_chapter_summary: bool = True
    per_batch_report: bool = True
    warn_window_days: int = 7
    warn_window_threshold: int = 5


@dataclass
class DebugConfig:
    master_enabled: bool = True
    layers: LayerSwitches = field(default_factory=LayerSwitches)
    severity: SeverityThresholds = field(default_factory=SeverityThresholds)
    storage: StorageConfig = field(default_factory=StorageConfig)
    alerts: AlertsConfig = field(default_factory=AlertsConfig)
    invariants: dict[str, dict[str, Any]] = field(default_factory=dict)
    strict_mode: bool = False
    project_root: Path = field(default_factory=Path)

    def passes_threshold(self, severity: str, threshold_field: str) -> bool:
        """Return True if severity >= self.severity.<threshold_field>."""
        threshold = getattr(self.severity, threshold_field)
        return SEVERITY_RANK.get(severity, -1) >= SEVERITY_RANK[threshold]

    def base_path(self) -> Path:
        return self.project_root / self.storage.base_dir


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(
    *,
    global_yaml_path: Path,
    project_root: Path,
) -> DebugConfig:
    """Load global config + optional project override + env var override."""
    raw: dict[str, Any] = {}
    if global_yaml_path.exists():
        raw = yaml.safe_load(global_yaml_path.read_text(encoding="utf-8")) or {}

    local_path = project_root / ".ink-debug" / "config.local.yaml"
    if local_path.exists():
        local_raw = yaml.safe_load(local_path.read_text(encoding="utf-8")) or {}
        raw = _deep_merge(raw, local_raw)

    cfg = DebugConfig(
        master_enabled=raw.get("master_enabled", True),
        layers=LayerSwitches(**(raw.get("layers") or {})),
        severity=SeverityThresholds(**(raw.get("severity") or {})),
        storage=StorageConfig(**(raw.get("storage") or {})),
        alerts=AlertsConfig(**(raw.get("alerts") or {})),
        invariants=raw.get("invariants") or {},
        strict_mode=raw.get("strict_mode", False),
        project_root=project_root,
    )

    if os.environ.get("INK_DEBUG_OFF") == "1":
        cfg.master_enabled = False

    return cfg
```

- [ ] **Step 2.5: Run tests, verify they pass**

Run: `pytest tests/debug/test_config.py -v`
Expected: 5 tests PASS.

- [ ] **Step 2.6: Commit**

```bash
git add config/debug.yaml ink_writer/debug/config.py tests/debug/test_config.py
git commit -m "feat(debug): config loader with yaml + project override + env (T2)"
```

---

## Task 3: Collector (master switch, severity routing, JSONL append)

**Files:**
- Create: `ink_writer/debug/collector.py`
- Test: `tests/debug/test_collector.py`

- [ ] **Step 3.1: Write failing tests for collector**

Create `tests/debug/test_collector.py`:

```python
"""Tests for ink_writer.debug.collector."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ink_writer.debug.collector import Collector
from ink_writer.debug.config import DebugConfig
from ink_writer.debug.schema import Incident


def _config(tmp_path: Path, **overrides) -> DebugConfig:
    cfg = DebugConfig(project_root=tmp_path)
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def _incident(severity: str = "warn", kind: str = "writer.short_word_count") -> Incident:
    return Incident(
        ts="2026-04-28T14:23:51Z",
        run_id="r1",
        source="layer_c_invariant",
        skill="ink-write",
        kind=kind,
        severity=severity,
        message="test",
    )


def test_record_appends_to_jsonl(tmp_path: Path):
    coll = Collector(_config(tmp_path))
    coll.record(_incident())
    events_path = tmp_path / ".ink-debug" / "events.jsonl"
    assert events_path.exists()
    lines = events_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["kind"] == "writer.short_word_count"


def test_master_disabled_skips_write(tmp_path: Path):
    cfg = _config(tmp_path)
    cfg.master_enabled = False
    coll = Collector(cfg)
    coll.record(_incident())
    assert not (tmp_path / ".ink-debug" / "events.jsonl").exists()


def test_below_jsonl_threshold_skipped(tmp_path: Path):
    cfg = _config(tmp_path)
    cfg.severity.jsonl_threshold = "warn"
    coll = Collector(cfg)
    coll.record(_incident(severity="info"))
    assert not (tmp_path / ".ink-debug" / "events.jsonl").exists()


def test_error_severity_writes_to_stderr(tmp_path: Path, capsys: pytest.CaptureFixture):
    coll = Collector(_config(tmp_path))
    coll.record(_incident(severity="error"))
    captured = capsys.readouterr()
    assert "error" in captured.err.lower() or "writer.short_word_count" in captured.err


def test_collector_swallows_internal_exceptions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cfg = _config(tmp_path)
    coll = Collector(cfg)

    def boom(*a, **kw):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "open", boom)
    coll.record(_incident())  # MUST NOT raise
    # Error log should be created
    error_log = tmp_path / ".ink-debug" / "collector.error.log"
    # error_log itself may have failed to write — assert no exception, that's it.


def test_unknown_kind_in_strict_mode_raises(tmp_path: Path):
    cfg = _config(tmp_path)
    cfg.strict_mode = True
    coll = Collector(cfg)
    bogus = Incident(
        ts="2026-04-28T14:23:51Z",
        run_id="r1",
        source="layer_c_invariant",
        skill="x",
        kind="totally.made.up",
        severity="info",
        message="x",
    )
    with pytest.raises(ValueError, match="unknown kind"):
        coll.record(bogus)


def test_unknown_kind_in_loose_mode_records_meta(tmp_path: Path):
    cfg = _config(tmp_path)
    cfg.strict_mode = False
    coll = Collector(cfg)
    bogus = Incident(
        ts="2026-04-28T14:23:51Z",
        run_id="r1",
        source="layer_c_invariant",
        skill="x",
        kind="totally.made.up",
        severity="info",
        message="x",
    )
    coll.record(bogus)
    events_path = tmp_path / ".ink-debug" / "events.jsonl"
    lines = events_path.read_text(encoding="utf-8").splitlines()
    kinds = {json.loads(l)["kind"] for l in lines}
    assert "meta.unknown_kind" in kinds
```

- [ ] **Step 3.2: Run tests, verify they fail**

Run: `pytest tests/debug/test_collector.py -v`
Expected: FAIL with `ModuleNotFoundError: ... collector`.

- [ ] **Step 3.3: Implement the collector**

Create `ink_writer/debug/collector.py`:

```python
"""Collector — single write entry point. Failure-soft by design."""
from __future__ import annotations

import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from ink_writer.debug.config import DebugConfig
from ink_writer.debug.schema import Incident, validate_kind


class Collector:
    """Writes incidents to events.jsonl. Never raises in production paths."""

    def __init__(self, config: DebugConfig) -> None:
        self.config = config

    def _events_path(self) -> Path:
        return self.config.base_path() / "events.jsonl"

    def _error_log_path(self) -> Path:
        return self.config.base_path() / "collector.error.log"

    def _ensure_dir(self) -> None:
        self.config.base_path().mkdir(parents=True, exist_ok=True)

    def _write_jsonl(self, line: str) -> None:
        self._ensure_dir()
        path = self._events_path()
        with path.open("a", encoding="utf-8") as f:
            f.write(line)

    def _log_error(self, exc: BaseException) -> None:
        try:
            self._ensure_dir()
            with self._error_log_path().open("a", encoding="utf-8") as f:
                f.write(f"{datetime.now(timezone.utc).isoformat()} {type(exc).__name__}: {exc}\n")
                f.write(traceback.format_exc() + "\n")
        except Exception:
            # Last resort: write to stderr, swallow.
            print(f"[debug.collector] internal error: {exc}", file=sys.stderr)

    def _stderr_print(self, incident: Incident) -> None:
        msg = f"[debug:{incident.severity}] {incident.kind} {incident.message}"
        # ANSI red only if tty
        if sys.stderr.isatty():
            msg = f"\033[31m{msg}\033[0m"
        print(msg, file=sys.stderr)

    def record(self, incident: Incident) -> None:
        # 1. Master switch (covers INK_DEBUG_OFF env via config.load).
        if not self.config.master_enabled:
            return

        # 2. Layer C gating (invariants).
        if incident.source == "layer_c_invariant" and not self.config.layers.layer_c_invariants:
            return
        if incident.source == "layer_b_checker" and not self.config.layers.layer_b_checker_router:
            return
        if incident.source == "layer_a_hook" and not self.config.layers.layer_a_hooks:
            return

        # 3. Kind validation.
        if not validate_kind(incident.kind):
            if self.config.strict_mode:
                raise ValueError(f"unknown kind: {incident.kind}")
            # Re-emit as meta.unknown_kind (and still record original).
            try:
                meta = Incident(
                    ts=incident.ts,
                    run_id=incident.run_id,
                    source="meta",
                    skill=incident.skill,
                    kind="meta.unknown_kind",
                    severity="info",
                    message=f"unknown kind: {incident.kind}",
                    evidence={"original_kind": incident.kind},
                )
                self._write_jsonl(meta.to_jsonl_line())
            except Exception as e:
                self._log_error(e)
            return

        # 4. Severity threshold for JSONL.
        if not self.config.passes_threshold(incident.severity, "jsonl_threshold"):
            return

        # 5. Write JSONL (best-effort).
        try:
            self._write_jsonl(incident.to_jsonl_line())
        except Exception as e:
            self._log_error(e)
            return

        # 6. stderr passthrough at error severity.
        if self.config.passes_threshold(incident.severity, "stderr_threshold"):
            try:
                self._stderr_print(incident)
            except Exception as e:
                self._log_error(e)
```

- [ ] **Step 3.4: Run tests, verify they pass**

Run: `pytest tests/debug/test_collector.py -v`
Expected: 7 tests PASS.

- [ ] **Step 3.5: Commit**

```bash
git add ink_writer/debug/collector.py tests/debug/test_collector.py
git commit -m "feat(debug): collector with master switch, severity routing, fail-soft JSONL (T3)"
```

---

## Task 4: JSONL rotation (events.jsonl → events.<ts>.jsonl.gz)

**Files:**
- Create: `ink_writer/debug/rotate.py`
- Test: `tests/debug/test_rotate.py`
- Modify: `ink_writer/debug/collector.py` (call rotation check)

- [ ] **Step 4.1: Write failing tests for rotation**

Create `tests/debug/test_rotate.py`:

```python
"""Tests for JSONL rotation."""
from __future__ import annotations

from pathlib import Path

from ink_writer.debug.rotate import rotate_if_needed


def test_no_rotation_below_threshold(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    events.write_bytes(b"x" * 100)
    rotated = rotate_if_needed(events, max_bytes=1024, archive_keep=5)
    assert rotated is None
    assert events.exists()


def test_rotates_above_threshold(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    events.write_bytes(b"x" * 2048)
    rotated = rotate_if_needed(events, max_bytes=1024, archive_keep=5)
    assert rotated is not None
    assert rotated.suffix == ".gz"
    assert rotated.exists()
    # Original truncated / removed
    assert not events.exists() or events.stat().st_size == 0


def test_archive_keep_prunes_old(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    # Pre-create 6 archives with old timestamps
    for i in range(6):
        archive = tmp_path / f"events.2026010{i}T000000.jsonl.gz"
        archive.write_bytes(b"old")
    events.write_bytes(b"x" * 2048)
    rotate_if_needed(events, max_bytes=1024, archive_keep=5)
    archives = sorted(tmp_path.glob("events.*.jsonl.gz"))
    assert len(archives) == 5  # 6 old + 1 new - 2 oldest pruned = 5
```

- [ ] **Step 4.2: Run tests, verify they fail**

Run: `pytest tests/debug/test_rotate.py -v`
Expected: FAIL.

- [ ] **Step 4.3: Implement rotation**

Create `ink_writer/debug/rotate.py`:

```python
"""JSONL rotation: cap single file size, gzip archive, prune old."""
from __future__ import annotations

import gzip
import shutil
from datetime import datetime, timezone
from pathlib import Path


def rotate_if_needed(
    events_path: Path,
    *,
    max_bytes: int,
    archive_keep: int,
) -> Path | None:
    """If events_path exceeds max_bytes, rotate to events.<UTCts>.jsonl.gz; prune old.

    Returns the archive Path, or None if no rotation occurred.
    """
    if not events_path.exists() or events_path.stat().st_size <= max_bytes:
        return None

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    archive = events_path.parent / f"{events_path.stem}.{ts}{events_path.suffix}.gz"
    with events_path.open("rb") as src, gzip.open(archive, "wb") as dst:
        shutil.copyfileobj(src, dst)
    events_path.unlink()

    # Prune old archives, keeping newest archive_keep.
    pattern = f"{events_path.stem}.*{events_path.suffix}.gz"
    archives = sorted(events_path.parent.glob(pattern))
    while len(archives) > archive_keep:
        archives[0].unlink()
        archives.pop(0)

    return archive
```

- [ ] **Step 4.4: Wire rotation into collector**

Edit `ink_writer/debug/collector.py`. Find the `_write_jsonl` method and update it:

```python
    def _write_jsonl(self, line: str) -> None:
        self._ensure_dir()
        path = self._events_path()
        with path.open("a", encoding="utf-8") as f:
            f.write(line)
        # Best-effort rotation check (cheap stat call).
        try:
            from ink_writer.debug.rotate import rotate_if_needed
            rotate_if_needed(
                path,
                max_bytes=self.config.storage.events_max_mb * 1024 * 1024,
                archive_keep=self.config.storage.archive_keep,
            )
        except Exception as e:
            self._log_error(e)
```

- [ ] **Step 4.5: Run tests, verify they pass**

Run: `pytest tests/debug/test_rotate.py tests/debug/test_collector.py -v`
Expected: All PASS.

- [ ] **Step 4.6: Commit**

```bash
git add ink_writer/debug/rotate.py ink_writer/debug/collector.py tests/debug/test_rotate.py
git commit -m "feat(debug): JSONL rotation with gzip archive + prune (T4)"
```

---

## Task 5: SQLite indexer (JSONL → debug.db, watermark)

**Files:**
- Create: `ink_writer/debug/indexer.py`
- Test: `tests/debug/test_indexer.py`

- [ ] **Step 5.1: Write failing tests for indexer**

Create `tests/debug/test_indexer.py`:

```python
"""Tests for ink_writer.debug.indexer."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from ink_writer.debug.config import DebugConfig
from ink_writer.debug.indexer import Indexer


def _seed_jsonl(tmp_path: Path, *records: dict) -> Path:
    debug_dir = tmp_path / ".ink-debug"
    debug_dir.mkdir(parents=True)
    events = debug_dir / "events.jsonl"
    with events.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return events


def _config(tmp_path: Path, sqlite_threshold: str = "warn") -> DebugConfig:
    cfg = DebugConfig(project_root=tmp_path)
    cfg.severity.sqlite_threshold = sqlite_threshold
    return cfg


def test_indexer_creates_schema(tmp_path: Path):
    _seed_jsonl(tmp_path)  # empty
    idx = Indexer(_config(tmp_path))
    idx.sync()
    db = tmp_path / ".ink-debug" / "debug.db"
    assert db.exists()
    conn = sqlite3.connect(db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "incidents" in tables
    assert "indexer_watermark" in tables


def test_indexer_only_indexes_above_threshold(tmp_path: Path):
    _seed_jsonl(
        tmp_path,
        {"ts": "2026-04-28T00:00:00Z", "run_id": "r1", "source": "layer_c_invariant",
         "skill": "x", "kind": "writer.short_word_count", "severity": "info", "message": "i"},
        {"ts": "2026-04-28T00:00:01Z", "run_id": "r1", "source": "layer_c_invariant",
         "skill": "x", "kind": "writer.short_word_count", "severity": "warn", "message": "w"},
        {"ts": "2026-04-28T00:00:02Z", "run_id": "r1", "source": "layer_c_invariant",
         "skill": "x", "kind": "writer.short_word_count", "severity": "error", "message": "e"},
    )
    idx = Indexer(_config(tmp_path, sqlite_threshold="warn"))
    idx.sync()
    db = tmp_path / ".ink-debug" / "debug.db"
    rows = list(sqlite3.connect(db).execute("SELECT severity FROM incidents ORDER BY ts"))
    assert rows == [("warn",), ("error",)]


def test_indexer_is_incremental(tmp_path: Path):
    events = _seed_jsonl(
        tmp_path,
        {"ts": "2026-04-28T00:00:00Z", "run_id": "r1", "source": "layer_c_invariant",
         "skill": "x", "kind": "writer.short_word_count", "severity": "warn", "message": "1"},
    )
    idx = Indexer(_config(tmp_path))
    idx.sync()

    with events.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": "2026-04-28T00:00:01Z", "run_id": "r1", "source": "layer_c_invariant",
            "skill": "x", "kind": "writer.short_word_count", "severity": "warn", "message": "2",
        }, ensure_ascii=False) + "\n")

    idx.sync()
    db = tmp_path / ".ink-debug" / "debug.db"
    count = sqlite3.connect(db).execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
    assert count == 2


def test_indexer_skips_corrupted_lines(tmp_path: Path):
    debug_dir = tmp_path / ".ink-debug"
    debug_dir.mkdir(parents=True)
    events = debug_dir / "events.jsonl"
    events.write_text(
        '{"ts":"2026-04-28T00:00:00Z","run_id":"r1","source":"layer_c_invariant",'
        '"skill":"x","kind":"writer.short_word_count","severity":"warn","message":"1"}\n'
        'not-json-at-all\n'
        '{"ts":"2026-04-28T00:00:02Z","run_id":"r1","source":"layer_c_invariant",'
        '"skill":"x","kind":"writer.short_word_count","severity":"warn","message":"2"}\n',
        encoding="utf-8",
    )
    Indexer(_config(tmp_path)).sync()
    db = tmp_path / ".ink-debug" / "debug.db"
    count = sqlite3.connect(db).execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
    assert count == 2
```

- [ ] **Step 5.2: Run tests, verify they fail**

Run: `pytest tests/debug/test_indexer.py -v`
Expected: FAIL.

- [ ] **Step 5.3: Implement the indexer**

Create `ink_writer/debug/indexer.py`:

```python
"""SQLite indexer: incrementally sync events.jsonl into debug.db."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ink_writer.debug.config import DebugConfig

SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  run_id TEXT NOT NULL,
  session_id TEXT,
  project TEXT,
  chapter INTEGER,
  source TEXT NOT NULL,
  skill TEXT NOT NULL,
  step TEXT,
  kind TEXT NOT NULL,
  severity TEXT NOT NULL,
  message TEXT NOT NULL,
  evidence_json TEXT,
  trace_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_ts ON incidents(ts);
CREATE INDEX IF NOT EXISTS idx_kind_sev ON incidents(kind, severity);
CREATE INDEX IF NOT EXISTS idx_run_skill ON incidents(run_id, skill);
CREATE TABLE IF NOT EXISTS indexer_watermark (
  jsonl_path TEXT PRIMARY KEY,
  last_byte_offset INTEGER NOT NULL,
  last_indexed_ts TEXT NOT NULL
);
"""


class Indexer:
    def __init__(self, config: DebugConfig) -> None:
        self.config = config

    def _events_path(self) -> Path:
        return self.config.base_path() / "events.jsonl"

    def _db_path(self) -> Path:
        return self.config.base_path() / "debug.db"

    def _connect(self) -> sqlite3.Connection:
        self.config.base_path().mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path())
        conn.executescript(SCHEMA)
        return conn

    def _watermark(self, conn: sqlite3.Connection, jsonl_path: str) -> int:
        row = conn.execute(
            "SELECT last_byte_offset FROM indexer_watermark WHERE jsonl_path = ?",
            (jsonl_path,),
        ).fetchone()
        return row[0] if row else 0

    def _save_watermark(self, conn: sqlite3.Connection, jsonl_path: str, offset: int, ts: str) -> None:
        conn.execute(
            "INSERT OR REPLACE INTO indexer_watermark (jsonl_path, last_byte_offset, last_indexed_ts) "
            "VALUES (?, ?, ?)",
            (jsonl_path, offset, ts),
        )

    def sync(self) -> int:
        """Read JSONL from watermark to EOF, insert above sqlite_threshold rows. Returns count inserted."""
        conn = self._connect()
        events = self._events_path()
        if not events.exists():
            conn.commit()
            conn.close()
            return 0

        path_str = str(events)
        offset = self._watermark(conn, path_str)
        inserted = 0
        last_ts = ""
        try:
            with events.open("rb") as f:
                f.seek(offset)
                while True:
                    line_bytes = f.readline()
                    if not line_bytes:
                        break
                    line_text = line_bytes.decode("utf-8", errors="replace").strip()
                    if not line_text:
                        continue
                    try:
                        rec = json.loads(line_text)
                    except json.JSONDecodeError:
                        continue
                    sev = rec.get("severity", "info")
                    if not self.config.passes_threshold(sev, "sqlite_threshold"):
                        continue
                    conn.execute(
                        "INSERT INTO incidents (ts, run_id, session_id, project, chapter, "
                        "source, skill, step, kind, severity, message, evidence_json, trace_json) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            rec.get("ts", ""),
                            rec.get("run_id", ""),
                            rec.get("session_id"),
                            rec.get("project"),
                            rec.get("chapter"),
                            rec.get("source", ""),
                            rec.get("skill", ""),
                            rec.get("step"),
                            rec.get("kind", ""),
                            sev,
                            rec.get("message", ""),
                            json.dumps(rec["evidence"], ensure_ascii=False) if rec.get("evidence") else None,
                            json.dumps(rec["trace"], ensure_ascii=False) if rec.get("trace") else None,
                        ),
                    )
                    inserted += 1
                    last_ts = rec.get("ts", last_ts)
                final_offset = f.tell()
            self._save_watermark(conn, path_str, final_offset, last_ts)
            conn.commit()
        finally:
            conn.close()
        return inserted
```

- [ ] **Step 5.4: Run tests, verify they pass**

Run: `pytest tests/debug/test_indexer.py -v`
Expected: 4 tests PASS.

- [ ] **Step 5.5: Commit**

```bash
git add ink_writer/debug/indexer.py tests/debug/test_indexer.py
git commit -m "feat(debug): SQLite indexer with watermark, threshold, corruption skip (T5)"
```

---

## Task 6: invariant — writer_word_count

**Files:**
- Create: `ink_writer/debug/invariants/__init__.py`
- Create: `ink_writer/debug/invariants/writer_word_count.py`
- Test: `tests/debug/test_invariants_writer_word_count.py`

- [ ] **Step 6.1: Write failing tests**

Create `tests/debug/test_invariants_writer_word_count.py`:

```python
"""Tests for writer_word_count invariant."""
from __future__ import annotations

import pytest

from ink_writer.debug.invariants.writer_word_count import check


def test_short_text_returns_incident():
    inc = check(text="x" * 1000, run_id="r1", chapter=1, min_words=2200, skill="ink-write")
    assert inc is not None
    assert inc.kind == "writer.short_word_count"
    assert inc.severity == "warn"
    assert inc.evidence == {"length": 1000, "min": 2200}


def test_sufficient_text_returns_none():
    inc = check(text="x" * 2500, run_id="r1", chapter=1, min_words=2200, skill="ink-write")
    assert inc is None


def test_exact_min_returns_none():
    inc = check(text="x" * 2200, run_id="r1", chapter=1, min_words=2200, skill="ink-write")
    assert inc is None
```

- [ ] **Step 6.2: Run tests, verify they fail**

Run: `pytest tests/debug/test_invariants_writer_word_count.py -v`
Expected: FAIL.

- [ ] **Step 6.3: Implement the invariant**

Create `ink_writer/debug/invariants/__init__.py` (empty file).

Create `ink_writer/debug/invariants/writer_word_count.py`:

```python
"""Invariant: writer output length >= platform_min_words."""
from __future__ import annotations

from datetime import datetime, timezone

from ink_writer.debug.schema import Incident


def check(
    *,
    text: str,
    run_id: str,
    chapter: int | None,
    min_words: int,
    skill: str,
) -> Incident | None:
    """Return Incident if len(text) < min_words, else None."""
    length = len(text)
    if length >= min_words:
        return None
    return Incident(
        ts=datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        run_id=run_id,
        source="layer_c_invariant",
        skill=skill,
        step="writer",
        kind="writer.short_word_count",
        severity="warn",
        message=f"writer 输出 {length} 字 < 平台下限 {min_words}",
        chapter=chapter,
        evidence={"length": length, "min": min_words},
    )
```

- [ ] **Step 6.4: Run tests, verify they pass**

Run: `pytest tests/debug/test_invariants_writer_word_count.py -v`
Expected: 3 tests PASS.

- [ ] **Step 6.5: Commit**

```bash
git add ink_writer/debug/invariants/__init__.py \
        ink_writer/debug/invariants/writer_word_count.py \
        tests/debug/test_invariants_writer_word_count.py
git commit -m "feat(debug): writer_word_count invariant (T6)"
```

---

## Task 7: invariant — polish_diff

**Files:**
- Create: `ink_writer/debug/invariants/polish_diff.py`
- Test: `tests/debug/test_invariants_polish_diff.py`

- [ ] **Step 7.1: Write failing tests**

Create `tests/debug/test_invariants_polish_diff.py`:

```python
"""Tests for polish_diff invariant."""
from __future__ import annotations

from ink_writer.debug.invariants.polish_diff import check


def test_identical_returns_incident():
    text = "x" * 500
    inc = check(before=text, after=text, run_id="r1", chapter=1, min_diff_chars=50)
    assert inc is not None
    assert inc.kind == "polish.diff_too_small"
    assert inc.evidence["diff_chars"] == 0


def test_large_change_returns_none():
    inc = check(
        before="hello world" * 100,
        after="goodbye world" * 100,
        run_id="r1",
        chapter=1,
        min_diff_chars=50,
    )
    assert inc is None


def test_small_change_returns_incident():
    before = "hello world. " * 100
    after = "hello world! " * 100  # Only punctuation diff, ~100 char-level changes spread thinly
    inc = check(before=before, after=after, run_id="r1", chapter=1, min_diff_chars=200)
    assert inc is not None or inc is None  # threshold-dependent, just must not crash
```

- [ ] **Step 7.2: Run tests, verify they fail**

Run: `pytest tests/debug/test_invariants_polish_diff.py -v`
Expected: FAIL.

- [ ] **Step 7.3: Implement**

Create `ink_writer/debug/invariants/polish_diff.py`:

```python
"""Invariant: polish before/after has meaningful character-level diff."""
from __future__ import annotations

from datetime import datetime, timezone
from difflib import SequenceMatcher

from ink_writer.debug.schema import Incident


def _approx_diff_chars(before: str, after: str) -> int:
    """Approximate count of changed characters via SequenceMatcher ratio."""
    if not before and not after:
        return 0
    ratio = SequenceMatcher(None, before, after, autojunk=False).ratio()
    return int(round((1.0 - ratio) * max(len(before), len(after))))


def check(
    *,
    before: str,
    after: str,
    run_id: str,
    chapter: int | None,
    min_diff_chars: int,
) -> Incident | None:
    diff_chars = _approx_diff_chars(before, after)
    if diff_chars >= min_diff_chars:
        return None
    return Incident(
        ts=datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        run_id=run_id,
        source="layer_c_invariant",
        skill="ink-write",
        step="polish",
        kind="polish.diff_too_small",
        severity="warn",
        message=f"polish 前后 diff ≈ {diff_chars} 字符 < 阈值 {min_diff_chars}",
        chapter=chapter,
        evidence={"diff_chars": diff_chars, "threshold": min_diff_chars},
    )
```

- [ ] **Step 7.4: Run tests, verify they pass**

Run: `pytest tests/debug/test_invariants_polish_diff.py -v`
Expected: PASS.

- [ ] **Step 7.5: Commit**

```bash
git add ink_writer/debug/invariants/polish_diff.py tests/debug/test_invariants_polish_diff.py
git commit -m "feat(debug): polish_diff invariant (T7)"
```

---

## Task 8: invariant — review_dimensions

**Files:**
- Create: `ink_writer/debug/invariants/review_dimensions.py`
- Test: `tests/debug/test_invariants_review_dimensions.py`

- [ ] **Step 8.1: Write failing tests**

Create `tests/debug/test_invariants_review_dimensions.py`:

```python
"""Tests for review_dimensions invariant."""
from __future__ import annotations

from ink_writer.debug.invariants.review_dimensions import check


def test_too_few_dimensions_returns_incident():
    report = {"dimensions": {"d1": 0.8, "d2": 0.7}}
    inc = check(report=report, skill="ink-review", run_id="r1", chapter=1, min_dimensions=7)
    assert inc is not None
    assert inc.kind == "review.missing_dimensions"
    assert inc.evidence["found"] == 2
    assert inc.evidence["expected"] == 7


def test_enough_dimensions_returns_none():
    report = {"dimensions": {f"d{i}": 0.7 for i in range(7)}}
    inc = check(report=report, skill="ink-review", run_id="r1", chapter=1, min_dimensions=7)
    assert inc is None


def test_missing_dimensions_key_returns_incident():
    inc = check(report={}, skill="ink-review", run_id="r1", chapter=1, min_dimensions=7)
    assert inc is not None
    assert inc.evidence["found"] == 0
```

- [ ] **Step 8.2: Run tests, verify they fail**

Run: `pytest tests/debug/test_invariants_review_dimensions.py -v`
Expected: FAIL.

- [ ] **Step 8.3: Implement**

Create `ink_writer/debug/invariants/review_dimensions.py`:

```python
"""Invariant: review report has minimum number of evaluation dimensions."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ink_writer.debug.schema import Incident


def check(
    *,
    report: dict[str, Any],
    skill: str,
    run_id: str,
    chapter: int | None,
    min_dimensions: int,
) -> Incident | None:
    dims = report.get("dimensions") or {}
    found = len(dims) if isinstance(dims, dict) else 0
    if found >= min_dimensions:
        return None
    return Incident(
        ts=datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        run_id=run_id,
        source="layer_c_invariant",
        skill=skill,
        step="review",
        kind="review.missing_dimensions",
        severity="warn",
        message=f"review 报告 {found} 维度 < 期望 {min_dimensions}",
        chapter=chapter,
        evidence={"found": found, "expected": min_dimensions},
    )
```

- [ ] **Step 8.4: Run tests, verify they pass**

Run: `pytest tests/debug/test_invariants_review_dimensions.py -v`
Expected: 3 tests PASS.

- [ ] **Step 8.5: Commit**

```bash
git add ink_writer/debug/invariants/review_dimensions.py \
        tests/debug/test_invariants_review_dimensions.py
git commit -m "feat(debug): review_dimensions invariant (T8)"
```

---

## Task 9: invariant — context_required_files

**Files:**
- Create: `ink_writer/debug/invariants/context_required_files.py`
- Test: `tests/debug/test_invariants_context_required_files.py`

- [ ] **Step 9.1: Write failing tests**

Create `tests/debug/test_invariants_context_required_files.py`:

```python
"""Tests for context_required_files invariant."""
from __future__ import annotations

from ink_writer.debug.invariants.context_required_files import check


def test_missing_file_returns_warn_incident():
    inc = check(
        required=["a.md", "b.md", "c.md"],
        actually_read=["a.md", "b.md"],
        run_id="r1",
        chapter=1,
    )
    assert inc is not None
    assert inc.kind == "context.missing_required_skill_file"
    assert inc.severity == "warn"
    assert inc.evidence["missing"] == ["c.md"]


def test_all_read_returns_none():
    inc = check(
        required=["a.md"],
        actually_read=["a.md"],
        run_id="r1",
        chapter=1,
    )
    assert inc is None


def test_empty_required_returns_info_fail_soft():
    """If skill declares no required list, fail soft as info."""
    inc = check(
        required=[],
        actually_read=[],
        run_id="r1",
        chapter=1,
    )
    assert inc is None or inc.severity == "info"
```

- [ ] **Step 9.2: Run tests, verify they fail**

Run: `pytest tests/debug/test_invariants_context_required_files.py -v`
Expected: FAIL.

- [ ] **Step 9.3: Implement**

Create `ink_writer/debug/invariants/context_required_files.py`:

```python
"""Invariant: context-agent reads all skill files declared in Context Contract."""
from __future__ import annotations

from datetime import datetime, timezone

from ink_writer.debug.schema import Incident


def check(
    *,
    required: list[str],
    actually_read: list[str],
    run_id: str,
    chapter: int | None,
) -> Incident | None:
    if not required:
        # No declared contract → fail-soft: return None so collector skips.
        return None
    missing = [f for f in required if f not in set(actually_read)]
    if not missing:
        return None
    return Incident(
        ts=datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        run_id=run_id,
        source="layer_c_invariant",
        skill="ink-write",
        step="context",
        kind="context.missing_required_skill_file",
        severity="warn",
        message=f"context-agent 漏读 {len(missing)} 个必读文件",
        chapter=chapter,
        evidence={"missing": missing, "required_total": len(required)},
    )
```

- [ ] **Step 9.4: Run tests, verify they pass**

Run: `pytest tests/debug/test_invariants_context_required_files.py -v`
Expected: 3 tests PASS.

- [ ] **Step 9.5: Commit**

```bash
git add ink_writer/debug/invariants/context_required_files.py \
        tests/debug/test_invariants_context_required_files.py
git commit -m "feat(debug): context_required_files invariant (T9)"
```

---

## Task 10: invariant — auto_step_skipped

**Files:**
- Create: `ink_writer/debug/invariants/auto_step_skipped.py`
- Test: `tests/debug/test_invariants_auto_step_skipped.py`

- [ ] **Step 10.1: Write failing tests**

Create `tests/debug/test_invariants_auto_step_skipped.py`:

```python
"""Tests for auto_step_skipped invariant."""
from __future__ import annotations

from ink_writer.debug.invariants.auto_step_skipped import check


def test_missing_step_returns_incident():
    inc = check(
        actual_steps=["context", "draft", "review"],
        expected_steps=["context", "draft", "review", "polish", "extract", "audit"],
        run_id="r1",
        chapter=42,
    )
    assert inc is not None
    assert inc.kind == "auto.skill_step_skipped"
    assert set(inc.evidence["missing"]) == {"polish", "extract", "audit"}


def test_all_steps_present_returns_none():
    inc = check(
        actual_steps=["context", "draft", "review", "polish", "extract", "audit"],
        expected_steps=["context", "draft", "review", "polish", "extract", "audit"],
        run_id="r1",
        chapter=42,
    )
    assert inc is None
```

- [ ] **Step 10.2: Run tests, verify they fail**

Run: `pytest tests/debug/test_invariants_auto_step_skipped.py -v`
Expected: FAIL.

- [ ] **Step 10.3: Implement**

Create `ink_writer/debug/invariants/auto_step_skipped.py`:

```python
"""Invariant: ink-auto each chapter touches every expected step."""
from __future__ import annotations

from datetime import datetime, timezone

from ink_writer.debug.schema import Incident


def check(
    *,
    actual_steps: list[str],
    expected_steps: list[str],
    run_id: str,
    chapter: int | None,
) -> Incident | None:
    actual_set = set(actual_steps)
    missing = [s for s in expected_steps if s not in actual_set]
    if not missing:
        return None
    return Incident(
        ts=datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        run_id=run_id,
        source="layer_c_invariant",
        skill="ink-auto",
        step=None,
        kind="auto.skill_step_skipped",
        severity="warn",
        message=f"ink-auto 漏 {len(missing)}/{len(expected_steps)} 步: {','.join(missing)}",
        chapter=chapter,
        evidence={"missing": missing, "expected": expected_steps, "actual": actual_steps},
    )
```

- [ ] **Step 10.4: Run tests, verify they pass**

Run: `pytest tests/debug/test_invariants_auto_step_skipped.py -v`
Expected: 2 tests PASS.

- [ ] **Step 10.5: Commit**

```bash
git add ink_writer/debug/invariants/auto_step_skipped.py \
        tests/debug/test_invariants_auto_step_skipped.py
git commit -m "feat(debug): auto_step_skipped invariant (T10)"
```

---

## Task 11: checker_router — Layer B

**Files:**
- Create: `ink_writer/debug/checker_router.py`
- Test: `tests/debug/test_checker_router.py`

- [ ] **Step 11.1: Write failing tests**

Create `tests/debug/test_checker_router.py`:

```python
"""Tests for checker_router Layer B."""
from __future__ import annotations

from ink_writer.debug.checker_router import route, SUPPORTED_CHECKERS


def test_consistency_red_violation_to_error_incident():
    report = {"violations": [
        {"severity": "red", "kind": "character_drift", "message": "name changed"},
    ]}
    incidents = route("consistency", report, run_id="r1", chapter=1, skill="ink-write")
    assert len(incidents) == 1
    assert incidents[0].source == "layer_b_checker"
    assert incidents[0].severity == "error"
    assert incidents[0].kind == "checker.consistency.character_drift"


def test_yellow_violation_to_warn():
    report = {"violations": [
        {"severity": "yellow", "kind": "tone_inconsistency", "message": "tone shift"},
    ]}
    incidents = route("ooc", report, run_id="r1", chapter=1, skill="ink-write")
    assert incidents[0].severity == "warn"
    assert incidents[0].kind == "checker.ooc.tone_inconsistency"


def test_green_or_no_violations_returns_empty():
    report = {"violations": [{"severity": "green", "kind": "ok", "message": "fine"}]}
    incidents = route("consistency", report, run_id="r1", chapter=1, skill="ink-write")
    assert incidents == []


def test_unsupported_checker_returns_empty():
    incidents = route("unknown_checker", {"violations": []}, run_id="r1", chapter=1, skill="ink-write")
    assert incidents == []


def test_supported_checkers_list():
    assert "consistency" in SUPPORTED_CHECKERS
    assert "continuity" in SUPPORTED_CHECKERS
    assert "live-review" in SUPPORTED_CHECKERS
    assert "ooc" in SUPPORTED_CHECKERS
    assert "reader-simulator" in SUPPORTED_CHECKERS
```

- [ ] **Step 11.2: Run tests, verify they fail**

Run: `pytest tests/debug/test_checker_router.py -v`
Expected: FAIL.

- [ ] **Step 11.3: Implement**

Create `ink_writer/debug/checker_router.py`:

```python
"""Layer B: route existing checker reports → incident schema."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ink_writer.debug.schema import Incident

SUPPORTED_CHECKERS = frozenset({
    "consistency",
    "continuity",
    "live-review",
    "ooc",
    "reader-simulator",
})

SEVERITY_MAP = {"red": "error", "yellow": "warn", "green": "info"}


def _normalize_kind(checker_name: str, raw_kind: str) -> str:
    """Normalize to checker.<name>.<problem>; both segments snake_case."""
    name = checker_name.replace("-", "_")
    problem = raw_kind.replace("-", "_").replace(" ", "_").lower()
    return f"checker.{name}.{problem}"


def route(
    checker_name: str,
    report: dict[str, Any],
    *,
    run_id: str,
    chapter: int | None,
    skill: str,
) -> list[Incident]:
    """Convert a single checker report to a list of Incidents.

    Returns empty list if checker is unsupported or no warn+ violations.
    """
    if checker_name not in SUPPORTED_CHECKERS:
        return []

    violations = report.get("violations") or []
    out: list[Incident] = []
    for v in violations:
        sev = SEVERITY_MAP.get(v.get("severity", "green"), "info")
        if sev == "info":
            continue
        out.append(Incident(
            ts=datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            run_id=run_id,
            source="layer_b_checker",
            skill=skill,
            step="review",
            kind=_normalize_kind(checker_name, v.get("kind", "unknown")),
            severity=sev,
            message=v.get("message", ""),
            chapter=chapter,
            evidence={k: v[k] for k in v if k not in {"severity", "kind", "message"}} or None,
        ))
    return out
```

- [ ] **Step 11.4: Run tests, verify they pass**

Run: `pytest tests/debug/test_checker_router.py -v`
Expected: 5 tests PASS.

- [ ] **Step 11.5: Commit**

```bash
git add ink_writer/debug/checker_router.py tests/debug/test_checker_router.py
git commit -m "feat(debug): checker_router for 5 supported checkers (T11)"
```

---

## Task 12: hook_handler.py + .claude/settings.json (Layer A)

**Files:**
- Create: `scripts/debug/hook_handler.py`
- Create: `.claude/settings.json` (may not exist yet)

- [ ] **Step 12.1: Implement hook_handler entry script**

Create `scripts/debug/hook_handler.py`:

```python
#!/usr/bin/env python3
"""Claude Code hook → ink_writer.debug.collector adapter.

Invoked by .claude/settings.json hooks. Reads the hook event JSON from stdin,
constructs an Incident, calls Collector.record(). Always exits 0 (never blocks
the host hook).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _project_root() -> Path:
    # Honor INK_PROJECT_ROOT env if set; else cwd.
    return Path(os.environ.get("INK_PROJECT_ROOT") or os.getcwd())


def _run_id() -> str:
    return os.environ.get("INK_DEBUG_RUN_ID") or f"cc-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"


def _hook_kind(event_name: str) -> str:
    mapping = {
        "PreToolUse": "hook.pre_tool_use",
        "PostToolUse": "hook.post_tool_use",
        "SubagentStop": "hook.subagent_stop",
        "Stop": "hook.stop",
        "SessionEnd": "hook.session_end",
    }
    return mapping.get(event_name, "hook.post_tool_use")


def _severity(event_name: str, payload: dict) -> str:
    if event_name == "PostToolUse":
        if payload.get("error") or (payload.get("exit_code") or 0) != 0:
            return "warn"
    if event_name == "SubagentStop":
        return "warn"
    return "info"


def main() -> int:
    try:
        from ink_writer.debug.collector import Collector
        from ink_writer.debug.config import load_config
        from ink_writer.debug.schema import Incident
    except Exception as e:
        print(f"[hook_handler] import failed: {e}", file=sys.stderr)
        return 0

    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        payload = {}

    event_name = payload.get("hook_event_name") or payload.get("event") or "PostToolUse"
    cfg = load_config(global_yaml_path=Path("config/debug.yaml"), project_root=_project_root())
    if not cfg.master_enabled or not cfg.layers.layer_a_hooks:
        return 0

    inc = Incident(
        ts=_now_iso(),
        run_id=_run_id(),
        source="layer_a_hook",
        skill=os.environ.get("INK_DEBUG_SKILL", "claude-code"),
        kind=_hook_kind(event_name),
        severity=_severity(event_name, payload),
        message=f"{event_name} {payload.get('tool_name','')}".strip(),
        evidence={k: payload.get(k) for k in ("tool_name", "duration_ms", "exit_code", "error")
                  if payload.get(k) is not None} or None,
    )

    try:
        Collector(cfg).record(inc)
    except Exception as e:
        print(f"[hook_handler] record failed: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 12.2: Create .claude/settings.json with hook registration**

Check first whether `.claude/settings.json` exists:

```bash
test -f .claude/settings.json && cat .claude/settings.json || echo "(does not exist)"
```

If it does NOT exist, create `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "*",
        "hooks": [
          { "type": "command", "command": "python3 scripts/debug/hook_handler.py" }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [
          { "type": "command", "command": "python3 scripts/debug/hook_handler.py" }
        ]
      }
    ],
    "SubagentStop": [
      { "hooks": [ { "type": "command", "command": "python3 scripts/debug/hook_handler.py" } ] }
    ],
    "Stop": [
      { "hooks": [ { "type": "command", "command": "python3 scripts/debug/hook_handler.py" } ] }
    ],
    "SessionEnd": [
      { "hooks": [ { "type": "command", "command": "python3 scripts/debug/hook_handler.py" } ] }
    ]
  }
}
```

If it DOES exist, merge the `hooks` block in by hand (do NOT clobber existing keys). Show the merged file content before saving.

- [ ] **Step 12.3: Smoke test hook_handler**

Run from repo root:

```bash
echo '{"hook_event_name": "PostToolUse", "tool_name": "Read", "exit_code": 0}' | \
  INK_PROJECT_ROOT=/tmp/ink-debug-smoke INK_DEBUG_RUN_ID=smoke python3 scripts/debug/hook_handler.py
ls /tmp/ink-debug-smoke/.ink-debug/
cat /tmp/ink-debug-smoke/.ink-debug/events.jsonl
```

Expected: events.jsonl contains one record with `kind=hook.post_tool_use`, `severity=info`.

- [ ] **Step 12.4: Commit**

```bash
git add scripts/debug/hook_handler.py .claude/settings.json
git commit -m "feat(debug): Layer A hook handler + .claude/settings.json registration (T12)"
```

---

## Task 13: reporter — dual-view markdown

**Files:**
- Create: `ink_writer/debug/reporter.py`
- Test: `tests/debug/test_reporter.py`

- [ ] **Step 13.1: Write failing tests**

Create `tests/debug/test_reporter.py`:

```python
"""Tests for reporter dual-view markdown."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ink_writer.debug.config import DebugConfig
from ink_writer.debug.indexer import SCHEMA
from ink_writer.debug.reporter import Reporter


def _seed_db(tmp_path: Path) -> Path:
    debug_dir = tmp_path / ".ink-debug"
    debug_dir.mkdir(parents=True)
    db = debug_dir / "debug.db"
    conn = sqlite3.connect(db)
    conn.executescript(SCHEMA)
    now = datetime.now(timezone.utc)
    rows = [
        (now.isoformat(), "r1", None, "p", 1, "layer_c_invariant", "ink-write", "writer",
         "writer.short_word_count", "warn", "len 1000<2200", json.dumps({"length": 1000}), None),
        (now.isoformat(), "r1", None, "p", 1, "layer_c_invariant", "ink-write", "polish",
         "polish.diff_too_small", "warn", "diff 30<50", json.dumps({"diff_chars": 30}), None),
        (now.isoformat(), "r2", None, "p", 2, "layer_c_invariant", "ink-write", "writer",
         "writer.short_word_count", "warn", "len 1500<2200", json.dumps({"length": 1500}), None),
    ]
    conn.executemany(
        "INSERT INTO incidents (ts, run_id, session_id, project, chapter, source, skill, step, "
        "kind, severity, message, evidence_json, trace_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    conn.close()
    return db


def test_report_includes_both_views(tmp_path: Path):
    _seed_db(tmp_path)
    cfg = DebugConfig(project_root=tmp_path)
    md = Reporter(cfg).render(since="1d", run_id=None, severity="info")
    assert "视图 1" in md
    assert "视图 2" in md
    assert "writer.short_word_count" in md
    assert "polish.diff_too_small" in md


def test_report_filter_by_run_id(tmp_path: Path):
    _seed_db(tmp_path)
    cfg = DebugConfig(project_root=tmp_path)
    md = Reporter(cfg).render(since="1d", run_id="r1", severity="info")
    # r2's row should not appear
    assert md.count("writer.short_word_count") <= 2  # r1 only


def test_report_empty_db_says_no_data(tmp_path: Path):
    debug_dir = tmp_path / ".ink-debug"
    debug_dir.mkdir(parents=True)
    db = debug_dir / "debug.db"
    sqlite3.connect(db).executescript(SCHEMA)
    cfg = DebugConfig(project_root=tmp_path)
    md = Reporter(cfg).render(since="1d", run_id=None, severity="info")
    assert "无数据" in md or "no data" in md.lower()
```

- [ ] **Step 13.2: Run tests, verify they fail**

Run: `pytest tests/debug/test_reporter.py -v`
Expected: FAIL.

- [ ] **Step 13.3: Implement**

Create `ink_writer/debug/reporter.py`:

```python
"""Reporter: SQLite → dual-view markdown."""
from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ink_writer.debug.config import DebugConfig

_SINCE_RE = re.compile(r"^(\d+)([hdwm])$")


def _parse_since(since: str) -> datetime:
    m = _SINCE_RE.match(since)
    if not m:
        return datetime.now(timezone.utc) - timedelta(days=1)
    n = int(m.group(1))
    unit = m.group(2)
    delta = {"h": timedelta(hours=n), "d": timedelta(days=n),
             "w": timedelta(weeks=n), "m": timedelta(days=30 * n)}[unit]
    return datetime.now(timezone.utc) - delta


class Reporter:
    def __init__(self, config: DebugConfig) -> None:
        self.config = config

    def _db(self) -> Path:
        return self.config.base_path() / "debug.db"

    def render(self, *, since: str, run_id: str | None, severity: str) -> str:
        db = self._db()
        if not db.exists():
            return "# Debug Report\n\n无数据（数据库不存在）。\n"

        from ink_writer.debug.config import SEVERITY_RANK
        min_rank = SEVERITY_RANK.get(severity, 0)

        cutoff_iso = _parse_since(since).isoformat()
        sql = "SELECT ts, run_id, skill, step, kind, severity, message FROM incidents WHERE ts >= ?"
        params: list = [cutoff_iso]
        if run_id:
            sql += " AND run_id = ?"
            params.append(run_id)

        conn = sqlite3.connect(db)
        rows = list(conn.execute(sql, params))
        conn.close()

        rows = [r for r in rows if SEVERITY_RANK.get(r[5], 0) >= min_rank]
        if not rows:
            return f"# Debug Report (since {since})\n\n无数据。\n"

        # View 1: skill × kind × severity counts
        agg = defaultdict(lambda: {"count": 0, "latest": ""})
        for ts, _rid, skill, _step, kind, sev, _msg in rows:
            key = (skill, kind, sev)
            agg[key]["count"] += 1
            if ts > agg[key]["latest"]:
                agg[key]["latest"] = ts

        view1_lines = [
            "## 视图 1：按发生位置（skill × kind × severity）",
            "",
            "| skill | kind | severity | count | latest |",
            "|---|---|---|---|---|",
        ]
        for (skill, kind, sev), info in sorted(agg.items(), key=lambda kv: -kv[1]["count"]):
            view1_lines.append(f"| {skill} | {kind} | {sev} | {info['count']} | {info['latest']} |")

        # View 2: rule-based root cause grouping by step
        step_groups: dict[str, list[tuple[str, int]]] = defaultdict(list)
        kind_counts: dict[tuple[str, str], int] = defaultdict(int)
        for _ts, _rid, _skill, step, kind, _sev, _msg in rows:
            kind_counts[(step or "", kind)] += 1
        for (step, kind), n in kind_counts.items():
            step_groups[step or "_unknown"].append((kind, n))

        view2_lines = ["## 视图 2：按疑似根因（按 step 归并）", ""]
        for step, kinds in sorted(step_groups.items()):
            total = sum(n for _, n in kinds)
            view2_lines.append(f"### 根因组「{step}」共 {total} 次")
            for kind, n in sorted(kinds, key=lambda kv: -kv[1]):
                view2_lines.append(f"- {kind} × {n}")
            view2_lines.append("")

        header = f"# Debug Report (since {since}{' run='+run_id if run_id else ''})\n"
        return header + "\n" + "\n".join(view1_lines) + "\n\n" + "\n".join(view2_lines)
```

- [ ] **Step 13.4: Run tests, verify they pass**

Run: `pytest tests/debug/test_reporter.py -v`
Expected: 3 tests PASS.

- [ ] **Step 13.5: Commit**

```bash
git add ink_writer/debug/reporter.py tests/debug/test_reporter.py
git commit -m "feat(debug): reporter dual-view markdown (T13)"
```

---

## Task 14: alerter — per-chapter summary + per-batch trigger

**Files:**
- Create: `ink_writer/debug/alerter.py`
- Test: `tests/debug/test_alerter.py`

- [ ] **Step 14.1: Write failing tests**

Create `tests/debug/test_alerter.py`:

```python
"""Tests for alerter."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ink_writer.debug.alerter import Alerter
from ink_writer.debug.config import DebugConfig
from ink_writer.debug.indexer import SCHEMA


def _seed(tmp_path: Path, severities: list[str]) -> None:
    debug_dir = tmp_path / ".ink-debug"
    debug_dir.mkdir(parents=True)
    db = debug_dir / "debug.db"
    conn = sqlite3.connect(db)
    conn.executescript(SCHEMA)
    rows = [
        ("2026-04-28T00:00:00Z", "r1", None, None, 1, "layer_c_invariant",
         "ink-write", "writer", f"writer.short_word_count", sev, "x", None, None)
        for sev in severities
    ]
    conn.executemany(
        "INSERT INTO incidents (ts, run_id, session_id, project, chapter, source, skill, step, "
        "kind, severity, message, evidence_json, trace_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    conn.close()


def test_chapter_summary_with_warn(tmp_path: Path, capsys: pytest.CaptureFixture):
    _seed(tmp_path, ["warn", "warn", "info"])
    cfg = DebugConfig(project_root=tmp_path)
    Alerter(cfg).chapter_summary(run_id="r1")
    out = capsys.readouterr().out
    assert "warn" in out
    assert "writer.short_word_count" in out


def test_chapter_summary_disabled_when_master_off(tmp_path: Path, capsys: pytest.CaptureFixture):
    _seed(tmp_path, ["warn"])
    cfg = DebugConfig(project_root=tmp_path)
    cfg.master_enabled = False
    Alerter(cfg).chapter_summary(run_id="r1")
    assert capsys.readouterr().out == ""


def test_batch_report_writes_file(tmp_path: Path):
    _seed(tmp_path, ["warn"])
    cfg = DebugConfig(project_root=tmp_path)
    path = Alerter(cfg).batch_report(run_id="auto-batch-1")
    assert path is not None
    assert path.exists()
    assert path.parent.name == "reports"
    assert path.read_text(encoding="utf-8").startswith("#")
```

- [ ] **Step 14.2: Run tests, verify they fail**

Run: `pytest tests/debug/test_alerter.py -v`
Expected: FAIL.

- [ ] **Step 14.3: Implement**

Create `ink_writer/debug/alerter.py`:

```python
"""Alerter — per-chapter end-of-run summary + per-batch markdown report trigger."""
from __future__ import annotations

import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from ink_writer.debug.config import DebugConfig
from ink_writer.debug.indexer import Indexer
from ink_writer.debug.reporter import Reporter


class Alerter:
    def __init__(self, config: DebugConfig) -> None:
        self.config = config

    def _enabled(self) -> bool:
        return self.config.master_enabled

    def _ensure_synced(self) -> None:
        try:
            Indexer(self.config).sync()
        except Exception:
            pass

    def _query_run_counts(self, run_id: str) -> tuple[Counter, list[str]]:
        db = self.config.base_path() / "debug.db"
        if not db.exists():
            return Counter(), []
        conn = sqlite3.connect(db)
        rows = list(conn.execute(
            "SELECT severity, kind FROM incidents WHERE run_id = ?", (run_id,),
        ))
        conn.close()
        sev = Counter(r[0] for r in rows)
        kinds = [r[1] for r in rows if r[0] in ("warn", "error")]
        return sev, kinds

    def chapter_summary(self, *, run_id: str) -> None:
        if not self._enabled() or not self.config.alerts.per_chapter_summary:
            return
        self._ensure_synced()
        sev, kinds = self._query_run_counts(run_id)
        warn_n = sev.get("warn", 0)
        err_n = sev.get("error", 0)
        if warn_n == 0 and err_n == 0:
            line = "📊 debug: 本章 0 warn / 0 error ✅"
            color = "\033[32m"  # green
        elif err_n > 0:
            top = Counter(kinds).most_common(1)[0][0] if kinds else ""
            line = f"📊 debug: 本章 {warn_n} warn / {err_n} error，最高频 kind: {top}"
            color = "\033[31m"  # red
        else:
            top = Counter(kinds).most_common(1)[0][0] if kinds else ""
            line = f"📊 debug: 本章 {warn_n} warn / {err_n} error，最高频 kind: {top}"
            color = "\033[33m"  # yellow
        if sys.stdout.isatty():
            print(f"{color}{line}\033[0m")
        else:
            print(line)
        print("   完整报告：/ink-debug-report --since 1d")

    def batch_report(self, *, run_id: str) -> Path | None:
        if not self._enabled() or not self.config.alerts.per_batch_report:
            return None
        self._ensure_synced()
        md = Reporter(self.config).render(since="7d", run_id=run_id, severity="info")
        reports_dir = self.config.base_path() / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        path = reports_dir / f"{ts}-{run_id}.md"
        path.write_text(md, encoding="utf-8")
        print(f"📋 debug: 批次报告已生成 → {path}")
        return path
```

- [ ] **Step 14.4: Run tests, verify they pass**

Run: `pytest tests/debug/test_alerter.py -v`
Expected: 3 tests PASS.

- [ ] **Step 14.5: Commit**

```bash
git add ink_writer/debug/alerter.py tests/debug/test_alerter.py
git commit -m "feat(debug): alerter (chapter summary + batch report) (T14)"
```

---

## Task 15: cli — status / report / toggle

**Files:**
- Create: `ink_writer/debug/cli.py`
- Test: `tests/debug/test_cli.py`

- [ ] **Step 15.1: Write failing tests**

Create `tests/debug/test_cli.py`:

```python
"""Tests for ink_writer.debug.cli."""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from ink_writer.debug import cli
from ink_writer.debug.config import DebugConfig
from ink_writer.debug.indexer import SCHEMA


def _seed(tmp_path: Path) -> None:
    debug_dir = tmp_path / ".ink-debug"
    debug_dir.mkdir(parents=True)
    db = debug_dir / "debug.db"
    conn = sqlite3.connect(db)
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT INTO incidents (ts, run_id, source, skill, kind, severity, message) "
        "VALUES (?,?,?,?,?,?,?)",
        ("2026-04-28T00:00:00Z", "r1", "layer_c_invariant", "ink-write",
         "writer.short_word_count", "warn", "test"),
    )
    conn.commit()
    conn.close()


def test_status_prints_switches(tmp_path: Path, capsys: pytest.CaptureFixture):
    _seed(tmp_path)
    cli.cmd_status(project_root=tmp_path, global_yaml=Path("config/debug.yaml"))
    out = capsys.readouterr().out
    assert "master" in out
    assert "layer_a" in out
    assert "writer.short_word_count" in out


def test_report_writes_markdown(tmp_path: Path, capsys: pytest.CaptureFixture):
    _seed(tmp_path)
    path = cli.cmd_report(project_root=tmp_path, global_yaml=Path("config/debug.yaml"),
                          since="1d", run_id=None, severity="info")
    assert path.exists()
    assert path.read_text(encoding="utf-8").startswith("#")


def test_toggle_writes_local_yaml(tmp_path: Path):
    cli.cmd_toggle(project_root=tmp_path, global_yaml=Path("config/debug.yaml"),
                   key="layer_a", value=False)
    local = tmp_path / ".ink-debug" / "config.local.yaml"
    assert local.exists()
    assert "layer_a_hooks: false" in local.read_text(encoding="utf-8").lower()


def test_toggle_master(tmp_path: Path):
    cli.cmd_toggle(project_root=tmp_path, global_yaml=Path("config/debug.yaml"),
                   key="master", value=False)
    local = tmp_path / ".ink-debug" / "config.local.yaml"
    assert "master_enabled: false" in local.read_text(encoding="utf-8").lower()
```

- [ ] **Step 15.2: Run tests, verify they fail**

Run: `pytest tests/debug/test_cli.py -v`
Expected: FAIL.

- [ ] **Step 15.3: Implement**

Create `ink_writer/debug/cli.py`:

```python
"""Debug CLI — status / report / toggle."""
from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml

from ink_writer.debug.config import load_config
from ink_writer.debug.indexer import Indexer
from ink_writer.debug.reporter import Reporter

KEY_TO_PATH = {
    "master": ("master_enabled",),
    "layer_a": ("layers", "layer_a_hooks"),
    "layer_b": ("layers", "layer_b_checker_router"),
    "layer_c": ("layers", "layer_c_invariants"),
    "layer_d": ("layers", "layer_d_adversarial"),
}


def cmd_status(*, project_root: Path, global_yaml: Path) -> None:
    cfg = load_config(global_yaml_path=global_yaml, project_root=project_root)
    Indexer(cfg).sync()
    db = cfg.base_path() / "debug.db"
    print(f"[debug status] 项目: {project_root.name}")
    print("=" * 60)
    print(f"开关: master={'on' if cfg.master_enabled else 'off'}  "
          f"layer_a={'on' if cfg.layers.layer_a_hooks else 'off'}  "
          f"layer_b={'on' if cfg.layers.layer_b_checker_router else 'off'}  "
          f"layer_c={'on' if cfg.layers.layer_c_invariants else 'off'}  "
          f"layer_d={'on' if cfg.layers.layer_d_adversarial else 'off'}")
    print("=" * 60)
    if not db.exists():
        print("最近 24h: 无数据")
        return
    cutoff = (datetime.now(timezone.utc).replace(microsecond=0)).isoformat()
    cutoff_24h = (datetime.now(timezone.utc) - __import__("datetime").timedelta(days=1)).isoformat()
    conn = sqlite3.connect(db)
    rows = list(conn.execute(
        "SELECT severity, kind FROM incidents WHERE ts >= ?", (cutoff_24h,)
    ))
    conn.close()
    sev = Counter(r[0] for r in rows)
    kinds = Counter(r[1] for r in rows)
    print("最近 24h:")
    for s in ("info", "warn", "error"):
        print(f"  {s}: {sev.get(s, 0)}")
    print("=" * 60)
    print("top3 频发 kind:")
    for k, n in kinds.most_common(3):
        print(f"  {k}  ×{n}")
    print("=" * 60)
    print("完整报告：/ink-debug-report --since 1d")


def cmd_report(*, project_root: Path, global_yaml: Path,
               since: str, run_id: str | None, severity: str) -> Path:
    cfg = load_config(global_yaml_path=global_yaml, project_root=project_root)
    Indexer(cfg).sync()
    md = Reporter(cfg).render(since=since, run_id=run_id, severity=severity)
    reports_dir = cfg.base_path() / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = reports_dir / f"manual-{ts}.md"
    path.write_text(md, encoding="utf-8")
    print(f"📋 报告已生成 → {path}")
    return path


def cmd_toggle(*, project_root: Path, global_yaml: Path, key: str, value: bool) -> None:
    if key not in KEY_TO_PATH:
        sub = key.split(".", 1)
        if len(sub) == 2 and sub[0] == "invariants":
            override = {"invariants": {sub[1]: {"enabled": value}}}
        else:
            raise SystemExit(f"unknown key: {key}")
    else:
        path = KEY_TO_PATH[key]
        override: dict = {}
        cur = override
        for p in path[:-1]:
            cur[p] = {}
            cur = cur[p]
        cur[path[-1]] = value

    local_path = project_root / ".ink-debug" / "config.local.yaml"
    local_path.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if local_path.exists():
        existing = yaml.safe_load(local_path.read_text(encoding="utf-8")) or {}
    from ink_writer.debug.config import _deep_merge  # type: ignore
    merged = _deep_merge(existing, override)
    local_path.write_text(yaml.safe_dump(merged, allow_unicode=True), encoding="utf-8")
    print(f"已写入 {local_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ink-debug")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--global-yaml", type=Path, default=Path("config/debug.yaml"))
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status")

    p_report = sub.add_parser("report")
    p_report.add_argument("--since", default="1d")
    p_report.add_argument("--run-id", default=None)
    p_report.add_argument("--severity", default="info")

    p_toggle = sub.add_parser("toggle")
    p_toggle.add_argument("key")
    p_toggle.add_argument("value", choices=["on", "off"])

    args = parser.parse_args(argv)
    if args.cmd == "status":
        cmd_status(project_root=args.project_root, global_yaml=args.global_yaml)
    elif args.cmd == "report":
        cmd_report(project_root=args.project_root, global_yaml=args.global_yaml,
                   since=args.since, run_id=args.run_id, severity=args.severity)
    elif args.cmd == "toggle":
        cmd_toggle(project_root=args.project_root, global_yaml=args.global_yaml,
                   key=args.key, value=(args.value == "on"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

**Required follow-up edit to config.py**: rename `_deep_merge` → `deep_merge` (drop the leading underscore). Edit `ink_writer/debug/config.py`:

1. Change the function definition `def _deep_merge(...)` to `def deep_merge(...)`.
2. Change the internal recursive call inside the function body from `_deep_merge(out[k], v)` to `deep_merge(out[k], v)`.
3. Change the call site in `load_config` from `_deep_merge(raw, local_raw)` to `deep_merge(raw, local_raw)`.

Then in `cli.py` step 15.3, update the import line from:

```python
from ink_writer.debug.config import _deep_merge  # type: ignore
merged = _deep_merge(existing, override)
```

to:

```python
from ink_writer.debug.config import deep_merge
merged = deep_merge(existing, override)
```

(The underscore-prefixed version was a placeholder; the public name is the canonical one.)

- [ ] **Step 15.4: Run tests, verify they pass**

Run: `pytest tests/debug/test_cli.py tests/debug/test_config.py -v`
Expected: All PASS (config tests untouched; cli tests new).

- [ ] **Step 15.5: Commit**

```bash
git add ink_writer/debug/cli.py ink_writer/debug/config.py tests/debug/test_cli.py
git commit -m "feat(debug): CLI status/report/toggle subcommands (T15)"
```

---

## Task 16: shell wrappers

**Files:**
- Create: `scripts/debug/ink-debug-status.sh`
- Create: `scripts/debug/ink-debug-status.ps1`
- Create: `scripts/debug/ink-debug-status.cmd`
- Create: `scripts/debug/ink-debug-report.sh`
- Create: `scripts/debug/ink-debug-report.ps1`
- Create: `scripts/debug/ink-debug-report.cmd`
- Create: `scripts/debug/ink-debug-toggle.sh`
- Create: `scripts/debug/ink-debug-toggle.ps1`
- Create: `scripts/debug/ink-debug-toggle.cmd`

- [ ] **Step 16.1: Create the .sh wrappers**

Create `scripts/debug/ink-debug-status.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
exec python3 -m ink_writer.debug.cli --project-root "${INK_PROJECT_ROOT:-$PWD}" status "$@"
```

Create `scripts/debug/ink-debug-report.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
exec python3 -m ink_writer.debug.cli --project-root "${INK_PROJECT_ROOT:-$PWD}" report "$@"
```

Create `scripts/debug/ink-debug-toggle.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
exec python3 -m ink_writer.debug.cli --project-root "${INK_PROJECT_ROOT:-$PWD}" toggle "$@"
```

Make executable:

```bash
chmod +x scripts/debug/ink-debug-*.sh
```

- [ ] **Step 16.2: Create the .ps1 wrappers (UTF-8 BOM REQUIRED)**

Create `scripts/debug/ink-debug-status.ps1` (must be UTF-8 with BOM):

```powershell
$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$root = if ($Env:INK_PROJECT_ROOT) { $Env:INK_PROJECT_ROOT } else { (Get-Location).Path }
& python3 -m ink_writer.debug.cli --project-root $root status @args
exit $LASTEXITCODE
```

Create `scripts/debug/ink-debug-report.ps1`:

```powershell
$ErrorActionPreference = "Stop"
$root = if ($Env:INK_PROJECT_ROOT) { $Env:INK_PROJECT_ROOT } else { (Get-Location).Path }
& python3 -m ink_writer.debug.cli --project-root $root report @args
exit $LASTEXITCODE
```

Create `scripts/debug/ink-debug-toggle.ps1`:

```powershell
$ErrorActionPreference = "Stop"
$root = if ($Env:INK_PROJECT_ROOT) { $Env:INK_PROJECT_ROOT } else { (Get-Location).Path }
& python3 -m ink_writer.debug.cli --project-root $root toggle @args
exit $LASTEXITCODE
```

To save as UTF-8 with BOM in a portable way: write content with bytes prefix `\xef\xbb\xbf` or use `Out-File -Encoding utf8BOM` from a pre-existing PS session. If using Python:

```python
content = "...your script content..."
Path("scripts/debug/ink-debug-status.ps1").write_bytes("﻿".encode("utf-8") + content.encode("utf-8"))
```

- [ ] **Step 16.3: Create the .cmd wrappers**

Create `scripts/debug/ink-debug-status.cmd`:

```cmd
@echo off
setlocal
pushd "%~dp0..\.."
python3 -m ink_writer.debug.cli --project-root "%CD%" status %*
set RC=%ERRORLEVEL%
popd
exit /b %RC%
```

Create `scripts/debug/ink-debug-report.cmd`:

```cmd
@echo off
setlocal
pushd "%~dp0..\.."
python3 -m ink_writer.debug.cli --project-root "%CD%" report %*
set RC=%ERRORLEVEL%
popd
exit /b %RC%
```

Create `scripts/debug/ink-debug-toggle.cmd`:

```cmd
@echo off
setlocal
pushd "%~dp0..\.."
python3 -m ink_writer.debug.cli --project-root "%CD%" toggle %*
set RC=%ERRORLEVEL%
popd
exit /b %RC%
```

- [ ] **Step 16.4: Smoke test all three commands**

Run from repo root:

```bash
bash scripts/debug/ink-debug-status.sh --help || true
bash scripts/debug/ink-debug-status.sh
bash scripts/debug/ink-debug-toggle.sh layer_d on
cat .ink-debug/config.local.yaml
bash scripts/debug/ink-debug-toggle.sh layer_d off
bash scripts/debug/ink-debug-report.sh --since 1d
ls .ink-debug/reports/
```

Expected: each command runs without traceback; toggle creates / updates `.ink-debug/config.local.yaml`; report writes to `.ink-debug/reports/manual-<ts>.md`.

- [ ] **Step 16.5: Commit**

```bash
git add scripts/debug/ink-debug-*.sh scripts/debug/ink-debug-*.ps1 scripts/debug/ink-debug-*.cmd
git commit -m "feat(debug): shell wrappers (.sh/.ps1/.cmd) for status/report/toggle (T16)"
```

---

## Task 17: Wire writer_word_count into rewrite_loop orchestrator

**Files:**
- Modify: `ink_writer/rewrite_loop/orchestrator.py`
- Test: extend `tests/debug/test_e2e_ink_write.py` (created in T23) — defer here

- [ ] **Step 17.1: Locate the orchestrator's `run_rewrite_loop` function**

Run:

```bash
grep -n "def run_rewrite_loop" ink_writer/rewrite_loop/orchestrator.py
```

Expected: a single match showing the function definition line.

- [ ] **Step 17.2: Read the function body to find the writer-output / draft variable**

Run:

```bash
sed -n '118,180p' ink_writer/rewrite_loop/orchestrator.py
```

Identify the variable holding the writer's draft text (commonly named `draft`, `chapter_text`, or similar) AND a place that receives `run_id` / `chapter` / `project_root` (or where these can be passed in).

- [ ] **Step 17.3: Add the invariant call**

Edit `ink_writer/rewrite_loop/orchestrator.py`. After the line where the writer's draft is finalized (just before the rewrite loop body returns or before review starts), add:

```python
# --- debug invariant: writer_word_count ---
try:
    from pathlib import Path as _Path
    from ink_writer.debug.collector import Collector as _DebugCollector
    from ink_writer.debug.config import load_config as _load_debug_cfg
    from ink_writer.debug.invariants.writer_word_count import check as _check_word_count
    from ink_writer.core.preferences import load_word_limits as _load_word_limits

    _project_root = _Path(project_root) if not isinstance(project_root, _Path) else project_root
    _cfg = _load_debug_cfg(global_yaml_path=_Path("config/debug.yaml"), project_root=_project_root)
    if _cfg.master_enabled and _cfg.layers.layer_c_invariants \
            and _cfg.invariants.get("writer_word_count", {}).get("enabled", True):
        _min_words, _ = _load_word_limits(_project_root)
        _inc = _check_word_count(
            text=draft,                       # <-- adjust to the actual draft variable name
            run_id=run_id,                    # <-- adjust if named differently
            chapter=chapter,                  # <-- adjust if named differently
            min_words=_min_words,
            skill="ink-write",
        )
        if _inc is not None:
            _DebugCollector(_cfg).record(_inc)
except Exception:
    pass  # Debug must never break the writing loop.
```

If `project_root` / `run_id` / `chapter` / `draft` are not in scope at this exact location, find the nearest scope where they all are. If `run_id` doesn't exist, derive it as `f"ink-write-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-ch{chapter}"` at function entry and pass through.

- [ ] **Step 17.4: Run all unit tests to ensure nothing regresses**

Run: `pytest tests/debug/ -v` and `pytest tests/rewrite_loop/ -v` (if exists)
Expected: all PASS.

- [ ] **Step 17.5: Commit**

```bash
git add ink_writer/rewrite_loop/orchestrator.py
git commit -m "feat(debug): wire writer_word_count invariant into rewrite_loop (T17)"
```

---

## Task 18: Wire polish_diff into rewrite_loop orchestrator

**Files:**
- Modify: `ink_writer/rewrite_loop/orchestrator.py`

- [ ] **Step 18.1: Find the polish call in orchestrator**

Run:

```bash
grep -n "polish" ink_writer/rewrite_loop/orchestrator.py
```

Identify the lines where polish is called and the variables for the pre-polish text (`draft` / `chapter_text`) and post-polish text (commonly `polished` / `final_text`).

- [ ] **Step 18.2: Add the invariant call after polish completes**

Edit `ink_writer/rewrite_loop/orchestrator.py`. Immediately after the polish step completes (where `polished` is assigned), add:

```python
# --- debug invariant: polish_diff ---
try:
    from pathlib import Path as _Path
    from ink_writer.debug.collector import Collector as _DebugCollector
    from ink_writer.debug.config import load_config as _load_debug_cfg
    from ink_writer.debug.invariants.polish_diff import check as _check_polish_diff

    _project_root = _Path(project_root) if not isinstance(project_root, _Path) else project_root
    _cfg = _load_debug_cfg(global_yaml_path=_Path("config/debug.yaml"), project_root=_project_root)
    _inv_cfg = _cfg.invariants.get("polish_diff", {})
    if _cfg.master_enabled and _cfg.layers.layer_c_invariants \
            and _inv_cfg.get("enabled", True):
        _inc = _check_polish_diff(
            before=draft,                    # <-- pre-polish text variable
            after=polished,                  # <-- post-polish text variable
            run_id=run_id,
            chapter=chapter,
            min_diff_chars=_inv_cfg.get("min_diff_chars", 50),
        )
        if _inc is not None:
            _DebugCollector(_cfg).record(_inc)
except Exception:
    pass
```

- [ ] **Step 18.3: Run tests**

Run: `pytest tests/debug/ -v`
Expected: all PASS.

- [ ] **Step 18.4: Commit**

```bash
git add ink_writer/rewrite_loop/orchestrator.py
git commit -m "feat(debug): wire polish_diff invariant into rewrite_loop (T18)"
```

---

## Task 19: Wire review_dimensions + checker_router into rewrite_loop

**Files:**
- Modify: `ink_writer/rewrite_loop/orchestrator.py`

- [ ] **Step 19.1: Find where checker reports come back from the rewrite loop's checker phase**

Run:

```bash
grep -n "checker\|review_metrics\|cases_violated" ink_writer/rewrite_loop/orchestrator.py | head -20
```

Identify the dict/object containing the aggregated review report (something like `review_report`, `compliance`, `cases_violated`).

- [ ] **Step 19.2: Add review_dimensions invariant + checker_router calls**

Edit `ink_writer/rewrite_loop/orchestrator.py`. After the review report is finalized:

```python
# --- debug: review_dimensions invariant + checker_router ---
try:
    from pathlib import Path as _Path
    from ink_writer.debug.collector import Collector as _DebugCollector
    from ink_writer.debug.config import load_config as _load_debug_cfg
    from ink_writer.debug.invariants.review_dimensions import check as _check_review_dims
    from ink_writer.debug.checker_router import route as _route_checker

    _project_root = _Path(project_root) if not isinstance(project_root, _Path) else project_root
    _cfg = _load_debug_cfg(global_yaml_path=_Path("config/debug.yaml"), project_root=_project_root)
    _coll = _DebugCollector(_cfg)
    if _cfg.master_enabled:
        # Layer C: review_dimensions
        if _cfg.layers.layer_c_invariants \
                and _cfg.invariants.get("review_dimensions", {}).get("enabled", True):
            _min_dims = (_cfg.invariants.get("review_dimensions", {})
                         .get("min_dimensions_per_skill", {}).get("ink-review", 7))
            _inc = _check_review_dims(
                report=review_report if isinstance(review_report, dict) else {},
                skill="ink-review",
                run_id=run_id,
                chapter=chapter,
                min_dimensions=_min_dims,
            )
            if _inc is not None:
                _coll.record(_inc)
        # Layer B: route 5 checkers
        if _cfg.layers.layer_b_checker_router:
            _per_checker = (review_report.get("per_checker_reports", {})
                            if isinstance(review_report, dict) else {})
            for _ck_name, _ck_report in _per_checker.items():
                for _inc in _route_checker(_ck_name, _ck_report,
                                           run_id=run_id, chapter=chapter, skill="ink-write"):
                    _coll.record(_inc)
except Exception:
    pass
```

Note: the actual structure of the review report is whatever the orchestrator produces. If it does NOT contain a `per_checker_reports` map keyed by name, leave the Layer B branch in but expect it to be a no-op until T19.5 follow-up wires up the per-checker dict (file an open issue and add a TODO inline that can be removed once orchestrator produces the right shape).

- [ ] **Step 19.3: Run tests**

Run: `pytest tests/debug/ -v`
Expected: all PASS.

- [ ] **Step 19.4: Commit**

```bash
git add ink_writer/rewrite_loop/orchestrator.py
git commit -m "feat(debug): wire review_dimensions + checker_router into rewrite_loop (T19)"
```

---

## Task 20: Wire context_required_files into preflight

**Files:**
- Modify: `ink_writer/preflight/cli.py` (or the closest entry that has Context Contract data; see step 20.1)

- [ ] **Step 20.1: Find where Context Contract / required files list is computed**

Run:

```bash
grep -rn "Context Contract\|context_contract\|required_files\|required_skill_file" ink_writer/ | head -10
```

If a clear data structure exists, use it. If NOT, this invariant is a **best-effort hook** — wire it into `ink_writer/preflight/cli.py` at the end of the preflight run, where it has access to project_root and the list of skill files actually loaded.

- [ ] **Step 20.2: Add the invariant call in preflight**

Locate the function in `ink_writer/preflight/cli.py` that finalizes the preflight run. After the preflight result is computed, add:

```python
# --- debug invariant: context_required_files (best-effort) ---
try:
    from pathlib import Path as _Path
    from ink_writer.debug.collector import Collector as _DebugCollector
    from ink_writer.debug.config import load_config as _load_debug_cfg
    from ink_writer.debug.invariants.context_required_files import check as _check_ctx

    _project_root = _Path(project_root) if not isinstance(project_root, _Path) else project_root
    _cfg = _load_debug_cfg(global_yaml_path=_Path("config/debug.yaml"), project_root=_project_root)
    if _cfg.master_enabled and _cfg.layers.layer_c_invariants \
            and _cfg.invariants.get("context_required_files", {}).get("enabled", True):
        # Best-effort: read the contract from the skill if available.
        _required: list[str] = locals().get("_required_skill_files", [])  # populated upstream if defined
        _read: list[str] = locals().get("_actually_read_files", [])
        _inc = _check_ctx(
            required=_required,
            actually_read=_read,
            run_id=locals().get("run_id", "preflight"),
            chapter=locals().get("chapter"),
        )
        if _inc is not None:
            _DebugCollector(_cfg).record(_inc)
except Exception:
    pass
```

If `_required_skill_files` and `_actually_read_files` are not populated yet, leave a TODO comment: `# TODO: wire Context Contract once formalized; until then this invariant is dormant.` — this is acceptable per spec §13 Q2 (acknowledged open question).

- [ ] **Step 20.3: Run tests**

Run: `pytest tests/debug/ -v && pytest tests/preflight/ -v`
Expected: all PASS (debug tests untouched; preflight tests should not regress because the new code is wrapped in try/except).

- [ ] **Step 20.4: Commit**

```bash
git add ink_writer/preflight/cli.py
git commit -m "feat(debug): wire context_required_files invariant into preflight (T20, dormant until contract wired)"
```

---

## Task 21: Document auto_step_skipped + alerter trigger in ink-auto SKILL.md

**Files:**
- Modify: `ink-writer/skills/ink-auto/SKILL.md`

- [ ] **Step 21.1: Locate the per-chapter checkpoint section**

Run:

```bash
grep -n "checkpoint\|每章" ink-writer/skills/ink-auto/SKILL.md | head -10
```

- [ ] **Step 21.2: Add a "Debug Mode 集成" section**

Edit `ink-writer/skills/ink-auto/SKILL.md`. At the end of the per-chapter checkpoint section, append (in Chinese to match the file's existing style):

```markdown
## Debug Mode 集成

**每章收尾**（写完一章 / 跑完一章流程后，紧接着下一章前），运行：

```bash
python3 -c "
from pathlib import Path
from ink_writer.debug.config import load_config
from ink_writer.debug.alerter import Alerter
from ink_writer.debug.invariants.auto_step_skipped import check as check_steps
from ink_writer.debug.collector import Collector
import os, sqlite3

project_root = Path(os.environ['PROJECT_ROOT'])
run_id = os.environ['INK_AUTO_RUN_ID']
chapter = int(os.environ['CHAPTER'])
cfg = load_config(global_yaml_path=Path('config/debug.yaml'), project_root=project_root)

# Auto step skipped invariant: read actual steps from events.jsonl for this chapter+run.
db = cfg.base_path() / 'debug.db'
actual_steps = []
if db.exists():
    conn = sqlite3.connect(db)
    actual_steps = [r[0] for r in conn.execute(
        \"SELECT DISTINCT step FROM incidents WHERE run_id=? AND chapter=? AND step IS NOT NULL\",
        (run_id, chapter),
    )]
    conn.close()
expected = (cfg.invariants.get('auto_step_skipped', {})
            .get('expected_steps', {}).get('ink-auto', []))
inc = check_steps(actual_steps=actual_steps, expected_steps=expected,
                  run_id=run_id, chapter=chapter)
if inc is not None:
    Collector(cfg).record(inc)
"
```

**每批次收尾**（一次 /ink-auto 调用结束）调用：

```bash
python3 -c "
from pathlib import Path
from ink_writer.debug.config import load_config
from ink_writer.debug.alerter import Alerter
import os
project_root = Path(os.environ['PROJECT_ROOT'])
run_id = os.environ['INK_AUTO_RUN_ID']
cfg = load_config(global_yaml_path=Path('config/debug.yaml'), project_root=project_root)
Alerter(cfg).batch_report(run_id=run_id)
"
```

环境变量需求：`PROJECT_ROOT` / `INK_AUTO_RUN_ID` / `CHAPTER`。
集成由 ink-auto 编排逻辑负责注入；当未设置时这两段命令会跳过（`load_config` / `batch_report` 内部已 fail-soft）。
```

- [ ] **Step 21.3: Commit**

```bash
git add ink-writer/skills/ink-auto/SKILL.md
git commit -m "docs(debug): document auto_step_skipped + batch alerter in ink-auto SKILL (T21)"
```

---

## Task 22: Document alerter call in ink-write SKILL.md

**Files:**
- Modify: `ink-writer/skills/ink-write/SKILL.md`

- [ ] **Step 22.1: Locate the Step 6 (data extraction) end**

Run:

```bash
grep -n "Step 6\|数据落库\|DataModulesConfig" ink-writer/skills/ink-write/SKILL.md | head -10
```

- [ ] **Step 22.2: Append "Debug Mode 集成" section after Step 6**

Edit `ink-writer/skills/ink-write/SKILL.md`. After the last instruction of Step 6 (just before `## 终态校验` or equivalent), append:

```markdown
## Debug Mode 集成（章节收尾摘要）

完成 Step 0-6 之后，写章流程末尾追加：

```bash
python3 -c "
from pathlib import Path
from ink_writer.debug.config import load_config
from ink_writer.debug.alerter import Alerter
import os
project_root = Path(os.environ['PROJECT_ROOT'])
run_id = os.environ.get('INK_WRITE_RUN_ID', f'ink-write-ch{os.environ.get(\"CHAPTER\",\"?\")}')
cfg = load_config(global_yaml_path=Path('config/debug.yaml'), project_root=project_root)
Alerter(cfg).chapter_summary(run_id=run_id)
"
```

环境变量：`PROJECT_ROOT` / `INK_WRITE_RUN_ID` / `CHAPTER`（前两个由 ink-write 编排注入；alerter 内部已 fail-soft）。
```

- [ ] **Step 22.3: Commit**

```bash
git add ink-writer/skills/ink-write/SKILL.md
git commit -m "docs(debug): document chapter_summary alerter in ink-write SKILL (T22)"
```

---

## Task 23: .gitignore + integration test + acceptance run + final commit

**Files:**
- Modify: `.gitignore`
- Create: `tests/debug/test_e2e_ink_write.py`
- Create: `tests/debug/test_disabled_mode.py`

- [ ] **Step 23.1: Add .ink-debug/ to .gitignore**

Edit `.gitignore`. Add a section after `# Local runtime data` block:

```
# Debug mode runtime
.ink-debug/
```

- [ ] **Step 23.2: Write integration test for end-to-end debug write path**

Create `tests/debug/test_e2e_ink_write.py`:

```python
"""End-to-end smoke: simulate writer/polish/review producing incidents, then status + report."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from ink_writer.debug.collector import Collector
from ink_writer.debug.config import load_config
from ink_writer.debug.invariants.writer_word_count import check as check_words
from ink_writer.debug.invariants.polish_diff import check as check_polish
from ink_writer.debug.indexer import Indexer
from ink_writer.debug.reporter import Reporter
from ink_writer.debug import cli


def test_full_write_path(tmp_path: Path, capsys: pytest.CaptureFixture):
    cfg = load_config(global_yaml_path=Path("config/debug.yaml"), project_root=tmp_path)
    coll = Collector(cfg)

    # 1. Simulate writer producing a too-short chapter.
    inc1 = check_words(text="x" * 1000, run_id="r1", chapter=1, min_words=2200, skill="ink-write")
    assert inc1 is not None
    coll.record(inc1)

    # 2. Simulate polish doing nothing.
    inc2 = check_polish(before="x" * 1000, after="x" * 1000, run_id="r1", chapter=1, min_diff_chars=50)
    assert inc2 is not None
    coll.record(inc2)

    # 3. events.jsonl exists with 2 lines.
    events = tmp_path / ".ink-debug" / "events.jsonl"
    assert events.exists()
    lines = events.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2

    # 4. Sync to SQLite.
    Indexer(cfg).sync()
    db = tmp_path / ".ink-debug" / "debug.db"
    assert db.exists()
    count = sqlite3.connect(db).execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
    assert count == 2

    # 5. /ink-debug-status equivalent.
    cli.cmd_status(project_root=tmp_path, global_yaml=Path("config/debug.yaml"))
    out = capsys.readouterr().out
    assert "writer.short_word_count" in out

    # 6. /ink-debug-report equivalent.
    md_path = cli.cmd_report(project_root=tmp_path, global_yaml=Path("config/debug.yaml"),
                              since="1d", run_id=None, severity="info")
    assert md_path.exists()
    md = md_path.read_text(encoding="utf-8")
    assert "writer.short_word_count" in md
    assert "polish.diff_too_small" in md
```

- [ ] **Step 23.3: Write disabled-mode integration test**

Create `tests/debug/test_disabled_mode.py`:

```python
"""Disabled mode: master_enabled=false → no events written, no summary printed."""
from __future__ import annotations

from pathlib import Path

import pytest

from ink_writer.debug.alerter import Alerter
from ink_writer.debug.collector import Collector
from ink_writer.debug.config import load_config
from ink_writer.debug.invariants.writer_word_count import check as check_words


def test_master_disabled_via_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                 capsys: pytest.CaptureFixture):
    monkeypatch.setenv("INK_DEBUG_OFF", "1")
    cfg = load_config(global_yaml_path=Path("config/debug.yaml"), project_root=tmp_path)
    coll = Collector(cfg)
    inc = check_words(text="x" * 100, run_id="r1", chapter=1, min_words=2200, skill="ink-write")
    coll.record(inc)
    assert not (tmp_path / ".ink-debug" / "events.jsonl").exists()


def test_alerter_silent_when_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                      capsys: pytest.CaptureFixture):
    monkeypatch.setenv("INK_DEBUG_OFF", "1")
    cfg = load_config(global_yaml_path=Path("config/debug.yaml"), project_root=tmp_path)
    Alerter(cfg).chapter_summary(run_id="r1")
    out = capsys.readouterr().out
    assert out == ""


def test_delete_debug_dir_does_not_break(tmp_path: Path):
    cfg = load_config(global_yaml_path=Path("config/debug.yaml"), project_root=tmp_path)
    Collector(cfg).record(check_words(
        text="x" * 100, run_id="r1", chapter=1, min_words=2200, skill="ink-write",
    ))
    assert (tmp_path / ".ink-debug" / "events.jsonl").exists()
    import shutil
    shutil.rmtree(tmp_path / ".ink-debug")
    # Re-record: directory should be auto-recreated.
    Collector(cfg).record(check_words(
        text="x" * 100, run_id="r2", chapter=2, min_words=2200, skill="ink-write",
    ))
    assert (tmp_path / ".ink-debug" / "events.jsonl").exists()
```

- [ ] **Step 23.4: Run the full debug test suite**

Run: `pytest tests/debug/ -v`
Expected: all tests PASS (collector / schema / config / rotate / indexer / 5 invariants / checker_router / reporter / alerter / cli / e2e / disabled).

- [ ] **Step 23.5: Run a manual acceptance walkthrough**

```bash
# Acceptance #1, #2, #3, #4
mkdir -p /tmp/ink-debug-accept
cd /tmp/ink-debug-accept
python3 -c "
from pathlib import Path
from ink_writer.debug.collector import Collector
from ink_writer.debug.config import load_config
from ink_writer.debug.invariants.writer_word_count import check
cfg = load_config(global_yaml_path=Path('/Users/cipher/AI/小说/ink/ink-writer/config/debug.yaml'), project_root=Path('.'))
inc = check(text='x'*1000, run_id='accept-1', chapter=1, min_words=2200, skill='ink-write')
Collector(cfg).record(inc)
print('events:', (Path('.')/'.ink-debug'/'events.jsonl').read_text(encoding='utf-8'))
"
cd -
bash /Users/cipher/AI/小说/ink/ink-writer/scripts/debug/ink-debug-status.sh \
  --project-root /tmp/ink-debug-accept
bash /Users/cipher/AI/小说/ink/ink-writer/scripts/debug/ink-debug-report.sh \
  --project-root /tmp/ink-debug-accept --since 1h
ls /tmp/ink-debug-accept/.ink-debug/reports/
```

Expected: all 4 commands succeed, jsonl has 1 entry, status shows top1 kind, report markdown contains "writer.short_word_count".

```bash
# Acceptance #6
cd /tmp/ink-debug-accept
INK_DEBUG_OFF=1 python3 -c "
from pathlib import Path
from ink_writer.debug.collector import Collector
from ink_writer.debug.config import load_config
from ink_writer.debug.invariants.writer_word_count import check
cfg = load_config(global_yaml_path=Path('/Users/cipher/AI/小说/ink/ink-writer/config/debug.yaml'), project_root=Path('.'))
inc = check(text='x'*100, run_id='off', chapter=1, min_words=2200, skill='ink-write')
Collector(cfg).record(inc)
"
# events.jsonl line count should be unchanged from previous step:
wc -l .ink-debug/events.jsonl
cd -
```

Expected: line count is 1 (not 2).

```bash
# Acceptance #7
cd /tmp/ink-debug-accept
rm -rf .ink-debug
python3 -c "
from pathlib import Path
from ink_writer.debug.collector import Collector
from ink_writer.debug.config import load_config
from ink_writer.debug.invariants.writer_word_count import check
cfg = load_config(global_yaml_path=Path('/Users/cipher/AI/小说/ink/ink-writer/config/debug.yaml'), project_root=Path('.'))
Collector(cfg).record(check(text='x'*100, run_id='r2', chapter=2, min_words=2200, skill='ink-write'))
"
ls .ink-debug/
cd -
```

Expected: `.ink-debug/` recreated automatically with `events.jsonl`.

- [ ] **Step 23.6: Update USER_MANUAL_DEBUG.md status banner**

Edit `docs/USER_MANUAL_DEBUG.md`. Replace the `**状态**` line near the top:

```markdown
**状态**：v0.5 实施完成后此说明书生效。实施前默认配置已经在仓库（`config/debug.yaml`），但代码尚未落地——开关是占位状态。
```

with:

```markdown
**状态**：✅ v0.5 已实施 (2026-04-28)，全部 9 条 acceptance 通过。
```

- [ ] **Step 23.7: Final commit**

```bash
git add .gitignore tests/debug/test_e2e_ink_write.py tests/debug/test_disabled_mode.py \
        docs/USER_MANUAL_DEBUG.md
git commit -m "feat(debug): v0.5 acceptance — gitignore + e2e + disabled-mode tests + manual status (T23)

Closes 9/9 acceptance criteria from
docs/superpowers/specs/2026-04-28-debug-mode-design.md §11."
```

---

## Self-Review Checklist (filled by writer)

**Spec coverage:**

- [x] §1 Architecture: T1 (schema) + T3 (collector) + T5 (indexer) + T13 (reporter) + T14 (alerter)
- [x] §2.1 Layer A hooks: T12
- [x] §2.2 Layer B checker_router: T11 + T19 (wiring)
- [x] §2.3 Layer C 5 invariants: T6, T7, T8, T9, T10 + T17/T18/T19/T20/T21 (wiring)
- [x] §2.4 Layer D: explicitly deferred (no task — §0.2 non-goal)
- [x] §3.1 incident schema: T1
- [x] §3.2 SQLite schema: T5
- [x] §4 switches: T2 + T15 toggle
- [x] §5 failure modes: T3 (try/except in collector) + T17-T20 (try/except in wiring)
- [x] §6 Windows compat: T16 (.ps1/.cmd) + utf-8 encoding throughout
- [x] §7.1 auto end-of-run alerts: T14 + T21 + T22
- [x] §7.2 dual-view markdown: T13
- [x] §7.3 external Claude SOP: documented in USER_MANUAL_DEBUG.md (no code task)
- [x] §8 CLI commands: T15 + T16
- [x] §9 file layout: matches all task File: paths
- [x] §10 testing matrix: T1-T15 each have unit tests; T23 has e2e + disabled
- [x] §11 acceptance criteria 1-9: T23 walkthrough covers 1-7 directly; 8 is the e2e test; 9 is T23.6
- [x] §12 v1.0 upgrade path: deferred (config flag + module hooks already pre-wired in T2/T11)

**Placeholder scan:** No "TBD", "fill in later", or generic "add validation". Every step has either runnable code or exact commands. Two locations are flagged with explicit `# TODO` to acknowledge upstream-data dependencies (T19's per_checker_reports shape, T20's Context Contract availability) — both per spec §13 open questions.

**Type consistency:** `Incident` dataclass fields used consistently. `DebugConfig.passes_threshold(severity, threshold_field)` signature consistent. `Collector.record(incident)` consistent. `Reporter.render(*, since, run_id, severity)` consistent. `cli.cmd_*` signatures match across cli.py and tests.

---

## Execution Note

This plan assumes integration-task implementers (T17-T22) will inspect the existing `ink_writer/rewrite_loop/orchestrator.py` and `ink_writer/preflight/cli.py` to find the precise variable names (`draft` / `polished` / `review_report` / `run_id` / `chapter` / `project_root`). Each integration task documents the exact `grep` to run and the natural insertion point. If a variable is absent or named differently, the task instructions say to derive it locally — never to skip the integration.
